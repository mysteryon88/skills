from __future__ import annotations

import hashlib
import os
import platform
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import JsonSecurityError, RendererError
from .json_safe import canonical_json_bytes, load_json_file

_PROXY_VARIABLES = {
    "ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "NO_PROXY",
    "all_proxy", "http_proxy", "https_proxy", "ftp_proxy", "no_proxy",
}
_MAX_DIAGNOSTIC_BYTES = 1024 * 1024
_INKSCAPE_EXECUTABLE_NAMES = {"inkscape", "inkscape.com", "inkscape.exe"}
_LOCK_KEYS = {"schema_version", "lock_id", "renderer"}
_RENDERER_KEYS = {"basename", "platforms"}
_PLATFORM_KEYS = {"platform", "version_prefixes", "sha256"}


@dataclass(frozen=True, slots=True)
class RendererIdentity:
    name: str
    version: str
    lock_id: str
    executable_sha256: str
    executable: str


@dataclass(frozen=True, slots=True)
class RendererLock:
    lock_id: str
    basename: str
    version_prefixes: tuple[str, ...]
    sha256: str | None
    platform: str


class _WindowsJob:
    """Best-effort Windows process-tree containment using a kill-on-close Job Object."""

    def __init__(self) -> None:
        self.handle: int | None = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise RendererError("failed to create Windows renderer Job Object")

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(handle)
            raise RendererError("failed to configure Windows renderer Job Object")
        self.handle = int(handle)
        self._kernel32 = kernel32

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        if os.name == "nt" and self.handle is not None:
            process_handle = getattr(process, "_handle", None)
            if process_handle is None or not self._kernel32.AssignProcessToJobObject(self.handle, int(process_handle)):
                self.close()
                raise RendererError("failed to assign renderer to Windows Job Object")

    def terminate(self) -> None:
        if os.name == "nt" and self.handle is not None:
            self._kernel32.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        if os.name == "nt" and self.handle is not None:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RendererError(f"cannot open renderer executable safely: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RendererError("renderer executable is not a regular file")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise RendererError("renderer executable changed while hashing")
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _platform_name() -> str:
    value = platform.system().lower()
    return {"windows": "windows", "darwin": "macos", "linux": "linux"}.get(value, value or "unknown")


def _load_lock(path: Path, *, expected_lock_id: str) -> RendererLock:
    try:
        value, _raw = load_json_file(path, maximum=128 * 1024, label="dependencies.lock.json")
    except JsonSecurityError as exc:
        raise RendererError(str(exc)) from exc
    if not isinstance(value, dict) or set(value) != _LOCK_KEYS or value["schema_version"] != 2:
        raise RendererError("dependency lock has an invalid schema or unknown keys")
    lock_id = value["lock_id"]
    if lock_id != expected_lock_id:
        raise RendererError(f"renderer lock mismatch: project expects {expected_lock_id!r}, release provides {lock_id!r}")
    renderer = value["renderer"]
    if not isinstance(renderer, dict) or set(renderer) != _RENDERER_KEYS:
        raise RendererError("dependency lock renderer object is invalid")
    if renderer["basename"] != "inkscape":
        raise RendererError("public workflow only permits the 'inkscape' renderer basename")
    entries = renderer["platforms"]
    if not isinstance(entries, list) or not entries:
        raise RendererError("dependency lock has no platform entries")
    current = _platform_name()
    matches = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _PLATFORM_KEYS:
            raise RendererError("dependency lock platform entry has invalid keys")
        if entry["platform"] in {current, "any"}:
            matches.append(entry)
    if len(matches) != 1:
        raise RendererError(f"dependency lock must contain exactly one matching platform entry for {current!r}")
    selected = matches[0]
    prefixes = selected["version_prefixes"]
    if not isinstance(prefixes, list) or not prefixes or any(not isinstance(item, str) or not item for item in prefixes):
        raise RendererError("locked version_prefixes must be a non-empty string array")
    digest = selected["sha256"]
    if digest is not None and (not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
        raise RendererError("locked renderer SHA-256 is invalid")
    return RendererLock(lock_id, "inkscape", tuple(prefixes), digest, current)


class InkscapeRenderer:
    name = "inkscape"

    def __init__(
        self,
        executable: Path,
        *,
        lock: RendererLock,
        runtime_root: Path,
        project_root: Path | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        executable = Path(executable)
        if executable.name.lower() not in _INKSCAPE_EXECUTABLE_NAMES:
            raise RendererError("renderer executable basename must be 'inkscape'")
        if not executable.is_absolute():
            raise RendererError("renderer executable must be an absolute path")
        try:
            mode = executable.lstat().st_mode
        except OSError as exc:
            raise RendererError(f"renderer executable is unavailable: {executable}") from exc
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode) or not os.access(executable, os.X_OK):
            raise RendererError("renderer executable must be an executable regular non-symlink file")
        self.executable = executable.resolve(strict=True)
        if project_root is not None:
            try:
                self.executable.relative_to(Path(project_root).resolve(strict=True))
            except ValueError:
                pass
            else:
                raise RendererError("renderer executable must not reside inside the untrusted project directory")
        if not 0 < timeout_seconds <= 600:
            raise RendererError("renderer timeout must be between 0 and 600 seconds")
        self.timeout_seconds = float(timeout_seconds)
        self.runtime_root = Path(runtime_root)
        self.lock_id = lock.lock_id
        self.executable_sha256 = _sha256_file(self.executable)
        if lock.sha256 is not None and self.executable_sha256 != lock.sha256:
            raise RendererError(
                f"renderer hash mismatch: expected {lock.sha256}, found {self.executable_sha256}; "
                "use renderer-info and update-renderer-lock with a manually reviewed trusted executable"
            )
        self._prepare_runtime_root()
        completed = self._run([str(self.executable), "--version"], cwd=self.runtime_root)
        actual = completed.stdout.decode("utf-8", "replace").strip()
        if not any(actual.startswith(prefix) for prefix in lock.version_prefixes):
            raise RendererError(
                f"renderer version mismatch: allowed prefixes={list(lock.version_prefixes)!r}, found={actual!r}; "
                "review the binary and create a separate updated lock file"
            )
        self.version = actual

    @property
    def identity(self) -> RendererIdentity:
        return RendererIdentity(
            self.name, self.version, self.lock_id, self.executable_sha256, str(self.executable)
        )

    def _prepare_runtime_root(self) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        if self.runtime_root.is_symlink() or not self.runtime_root.is_dir():
            raise RendererError("renderer runtime root must be a non-symlink directory")
        try:
            self.runtime_root.chmod(0o700)
        except OSError:
            pass
        for name in ("home", "config", "cache", "data", "runtime", "tmp", "logs"):
            path = self.runtime_root / name
            path.mkdir(exist_ok=True)
            if path.is_symlink() or not path.is_dir():
                raise RendererError(f"unsafe renderer runtime directory: {path}")
            try:
                path.chmod(0o700)
            except OSError:
                pass

    def _environment(self) -> dict[str, str]:
        env: dict[str, str] = {
            "HOME": str(self.runtime_root / "home"),
            "XDG_CONFIG_HOME": str(self.runtime_root / "config"),
            "XDG_CACHE_HOME": str(self.runtime_root / "cache"),
            "XDG_DATA_HOME": str(self.runtime_root / "data"),
            "XDG_RUNTIME_DIR": str(self.runtime_root / "runtime"),
            "TMPDIR": str(self.runtime_root / "tmp"),
            "TEMP": str(self.runtime_root / "tmp"),
            "TMP": str(self.runtime_root / "tmp"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", os.defpath),
        }
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
            value = os.environ.get(key)
            if value:
                env[key] = value
        for key in _PROXY_VARIABLES:
            env.pop(key, None)
        return env

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[bytes], job: _WindowsJob | None) -> None:
        if os.name == "posix":
            # start_new_session=True makes the renderer PID its process-group ID.
            # A renderer can exit on SIGTERM while leaving a helper that ignores
            # SIGTERM behind, so always follow the grace period with SIGKILL for
            # any surviving group members instead of trusting only the parent.
            process_group = process.pid
            try:
                os.killpg(process_group, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                return
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                return
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                pass
        elif job is not None:
            job.terminate()
        elif process.poll() is None:
            process.kill()

    def _run(self, args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
        logs = self.runtime_root / "logs"
        stdout_fd, stdout_name = tempfile.mkstemp(prefix="stdout-", dir=logs)
        stderr_fd, stderr_name = tempfile.mkstemp(prefix="stderr-", dir=logs)
        os.close(stdout_fd)
        os.close(stderr_fd)
        stdout_path = Path(stdout_name)
        stderr_path = Path(stderr_name)
        process: subprocess.Popen[bytes] | None = None
        job: _WindowsJob | None = None
        try:
            try:
                with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
                    creationflags = 0
                    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
                    try:
                        process = subprocess.Popen(
                            args,
                            cwd=cwd,
                            env=self._environment(),
                            stdin=subprocess.DEVNULL,
                            stdout=stdout_handle,
                            stderr=stderr_handle,
                            shell=False,
                            start_new_session=(os.name == "posix"),
                            creationflags=creationflags,
                        )
                        if os.name == "nt":
                            job = _WindowsJob()
                            job.assign(process)
                    except OSError as exc:
                        raise RendererError(f"failed to start renderer: {exc}") from exc

                    deadline = time.monotonic() + self.timeout_seconds
                    while process.poll() is None:
                        if time.monotonic() >= deadline:
                            self._terminate_process_tree(process, job)
                            raise RendererError(f"renderer timed out after {self.timeout_seconds:g} seconds")
                        for log_path in (stdout_path, stderr_path):
                            try:
                                if log_path.stat().st_size > _MAX_DIAGNOSTIC_BYTES:
                                    self._terminate_process_tree(process, job)
                                    raise RendererError("renderer diagnostic output exceeded the bounded limit")
                            except FileNotFoundError:
                                pass
                        time.sleep(0.02)
            except KeyboardInterrupt:
                if process is not None:
                    self._terminate_process_tree(process, job)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                raise
            finally:
                if process is not None and process.poll() is None:
                    self._terminate_process_tree(process, job)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                if job is not None:
                    job.close()  # kill-on-close also removes residual helpers

            stdout = stdout_path.read_bytes()[:_MAX_DIAGNOSTIC_BYTES]
            stderr = stderr_path.read_bytes()[:_MAX_DIAGNOSTIC_BYTES]
            if process is None:
                raise RendererError("renderer process was not created")
            if process.returncode != 0:
                diagnostic = stderr.decode("utf-8", "replace")[-4096:].strip()
                raise RendererError(f"renderer exited with status {process.returncode}: {diagnostic}")
            return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        finally:
            stdout_path.unlink(missing_ok=True)
            stderr_path.unlink(missing_ok=True)

    def render(self, svg: Path, raw_png: Path, width: int, height: int) -> None:
        if isinstance(width, bool) or isinstance(height, bool) or not isinstance(width, int) or not isinstance(height, int):
            raise RendererError("render dimensions must be integers")
        if not 1 <= width <= 4096 or not 1 <= height <= 4096:
            raise RendererError("render dimensions are outside the supported range")
        svg = Path(svg)
        raw_png = Path(raw_png)
        if not svg.is_file() or svg.is_symlink():
            raise RendererError("renderer input must be a regular non-symlink SVG")
        raw_png.parent.mkdir(parents=True, exist_ok=True)
        if raw_png.parent.is_symlink() or not raw_png.parent.is_dir():
            raise RendererError("renderer output parent must be a non-symlink directory")
        if raw_png.exists() or raw_png.is_symlink():
            raise RendererError("renderer raw output path must not already exist")
        self._run(
            [
                str(self.executable), str(svg), "--export-type=png", f"--export-filename={raw_png}",
                f"--export-width={width}", f"--export-height={height}", "--export-area-page",
                "--export-background-opacity=0",
            ],
            cwd=self.runtime_root,
        )
        if not raw_png.is_file() or raw_png.is_symlink():
            raise RendererError("renderer reported success without a regular output file")


def load_locked_renderer(
    repository_root: Path,
    runtime_root: Path,
    *,
    expected_lock_id: str,
    project_root: Path | None = None,
) -> InkscapeRenderer:
    lock = _load_lock(Path(repository_root) / "dependencies.lock.json", expected_lock_id=expected_lock_id)
    resolved = shutil.which(lock.basename)
    if resolved is None:
        raise RendererError("locked renderer 'inkscape' was not found on PATH; nothing was installed")
    return InkscapeRenderer(
        Path(resolved).absolute(),
        lock=lock,
        runtime_root=runtime_root,
        project_root=project_root,
    )


def renderer_info(repository_root: Path, runtime_root: Path, *, expected_lock_id: str) -> RendererIdentity:
    return load_locked_renderer(
        repository_root, runtime_root, expected_lock_id=expected_lock_id, project_root=None
    ).identity


def create_updated_lock(executable: Path, output: Path, *, lock_id: str) -> dict[str, Any]:
    executable = Path(executable)
    if not executable.is_absolute():
        raise RendererError("trusted renderer path must be absolute")
    if executable.name.lower() not in _INKSCAPE_EXECUTABLE_NAMES:
        raise RendererError("trusted renderer basename must be inkscape")
    try:
        mode = executable.lstat().st_mode
    except OSError as exc:
        raise RendererError(f"trusted renderer is unavailable: {executable}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode) or not os.access(executable, os.X_OK):
        raise RendererError("trusted renderer must be an executable regular non-symlink file")
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise RendererError("update-renderer-lock refuses to overwrite an existing file")
    with tempfile.TemporaryDirectory(prefix="iconforge-renderer-probe-") as temporary:
        dummy_lock = RendererLock(lock_id, "inkscape", ("Inkscape ",), None, _platform_name())
        renderer = InkscapeRenderer(executable, lock=dummy_lock, runtime_root=Path(temporary))
        value = {
            "schema_version": 2,
            "lock_id": lock_id,
            "renderer": {
                "basename": "inkscape",
                "platforms": [
                    {
                        "platform": _platform_name(),
                        "version_prefixes": [renderer.version],
                        "sha256": renderer.executable_sha256,
                    }
                ],
            },
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(value))
    return value
