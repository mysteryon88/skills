"""Bounded file snapshots and recoverable whole-bundle switches; no code execution."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import time
from urllib.parse import unquote


class Refusal(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refusal(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}", value), "unsafe identifier")
    require(value.split(".")[0].upper() not in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}, "reserved identifier")
    return value


def relative(value):
    require(isinstance(value, str) and value and "\\" not in value and ":" not in value, "unsafe relative path")
    parts = value.split("/")
    require(not PurePosixPath(value).is_absolute() and all(p not in ("", ".", "..") for p in parts), "unsafe relative path")
    for part in parts:
        require(not part.endswith((" ", ".")) and not any(ord(c) < 32 for c in part), "unsafe path component")
        identifier(part.split(".")[0])
    return value


def safe_path(value):
    path = Path(os.path.abspath(os.fspath(value)))
    for item in (*reversed(path.parents), path):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400), "links/junctions/reparse points are forbidden")
    return path.resolve()


class Budget:
    def __init__(self):
        self.deadline = time.monotonic() + 30
        self.bytes = 0
        self.files = 0

    def check(self, size=0):
        self.bytes += size
        require(time.monotonic() <= self.deadline, "local operation time budget exhausted")
        require(self.bytes <= 32 * 1024 * 1024, "local operation byte budget exhausted")

    def read(self, path, limit=8 * 1024 * 1024):
        path = safe_path(path)
        require(path.is_file() and stat.S_ISREG(path.stat().st_mode), "required ordinary file is missing")
        require(path.stat().st_size <= limit, "file exceeds byte limit")
        with path.open("rb") as stream:
            body = stream.read(limit + 1)
        require(len(body) <= limit, "file exceeds byte limit")
        self.check(len(body))
        return body

    def json(self, path):
        def pairs(items):
            value = {}
            for key, item in items:
                require(key not in value, "duplicate JSON key")
                value[key] = item
            return value
        return json.loads(self.read(path, 1024 * 1024).decode("utf-8-sig"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refusal("nonfinite JSON number")))


def atomic_json(path, value):
    payload = canonical(value) + b"\n"
    require(len(payload) <= 1024 * 1024, "retained JSON record exceeds 1 MiB; previous record preserved")
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = safe_path(path.parent / "tmp")
    scratch.mkdir(exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="json-", dir=scratch)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def locked(path):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        stream.write(b"\0")
        stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise Refusal("another controller operation holds the lock") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def reject_named_streams(path):
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    class StreamData(ctypes.Structure):
        _fields_ = [("size", ctypes.c_longlong), ("name", wintypes.WCHAR * 296)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    first, next_stream, close = kernel.FindFirstStreamW, kernel.FindNextStreamW, kernel.FindClose
    first.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(StreamData), wintypes.DWORD]
    first.restype = wintypes.HANDLE
    next_stream.argtypes = [wintypes.HANDLE, ctypes.POINTER(StreamData)]
    next_stream.restype = wintypes.BOOL
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    data = StreamData()
    handle = first(str(path), 0, ctypes.byref(data), 0)
    if handle == ctypes.c_void_p(-1).value:
        require(ctypes.get_last_error() == 38, "cannot enumerate file streams; snapshot refused")
        return
    try:
        while True:
            require(data.name == "::$DATA", "named NTFS stream present; refusing a lossy snapshot/switch")
            if not next_stream(handle, ctypes.byref(data)):
                require(ctypes.get_last_error() == 38, "cannot enumerate file streams; snapshot refused")
                break
    finally:
        close(handle)


def scan(root, budget):
    root = safe_path(root)
    require(root.is_dir(), "bundle directory is missing")
    reject_named_streams(root)
    files = {}
    def refuse_walk_error(error):
        raise Refusal("cannot enumerate bundle directory: " + str(error)) from error
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=refuse_walk_error):
        budget.check()
        require(not set(dirs + names).intersection({".git", "__pycache__", ".pytest_cache"}), "excluded nonversioned data is present; refusing a lossy bundle switch")
        for name in dirs + names:
            reject_named_streams(safe_path(Path(directory) / name))
        dirs.sort()
        for name in sorted(names):
            file = Path(directory) / name
            key = relative(file.relative_to(root).as_posix())
            require(name.lower() not in ("auth.json", "credentials.json", "id_rsa") and not name.lower().endswith((".pem", ".key")), "secret-like file is not a skill component")
            budget.files += 1
            require(budget.files <= 2000, "local operation file budget exhausted")
            files[key] = budget.read(file)
    require(files, "empty bundle")
    require(len({p.casefold() for p in files}) == len(files), "case-colliding bundle paths")
    return files


def manifest(files):
    return {name: hashlib.sha256(body).hexdigest() for name, body in sorted(files.items())}


def scalar(value):
    """Parse only the documented string-scalar subset; full semantics use the native loader."""
    value = value.strip()
    if value.startswith('"'):
        parsed = json.loads(value)
        require(isinstance(parsed, str), "metadata scalar must be a string")
        return parsed
    if value.startswith("'"):
        require(re.fullmatch(r"'(?:[^']|'')*'", value), "invalid quoted metadata scalar")
        return value[1:-1].replace("''", "'")
    value = re.sub(r"\s+#.*$", "", value).strip()
    require(value and ": " not in value and value[0] not in "!&*|>{[" and value.lower() not in ("true", "false", "null", "~"), "unsupported metadata scalar")
    return value


def invocation_metadata(text, name):
    blocks = {}
    block = None
    for line in text.replace("\r\n", "\n").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            require(line in ("interface:", "policy:") and line[:-1] not in blocks, "unsupported or duplicate invocation metadata block")
            block = line[:-1]
            blocks[block] = {}
            continue
        match = re.fullmatch(r"  ([a-z_]+):[ \t]+(.+)", line)
        require(block is not None and match is not None, "invalid invocation metadata mapping")
        key, value = match.groups()
        require(key not in blocks[block], "duplicate invocation metadata field")
        if block == "policy":
            require(key == "allow_implicit_invocation" and value in ("true", "false"), "unsupported invocation policy")
            blocks[block][key] = value == "true"
        else:
            require(key in ("display_name", "short_description", "default_prompt", "icon_small", "icon_large", "brand_color"), "unsupported invocation interface field")
            blocks[block][key] = scalar(value)
    interface = blocks.get("interface", {})
    require(isinstance(interface.get("default_prompt"), str) and "$" + name in interface["default_prompt"], "missing actual interface/default_prompt metadata")


def validate(files, name):
    """Validate the supported metadata subset and resolve references without executing files."""
    prefix = name + "/"
    require(prefix + "SKILL.md" in files and prefix + "agents/openai.yaml" in files, "missing skill metadata dependency")
    text = files[prefix + "SKILL.md"].decode("utf-8").replace("\r\n", "\n")
    header = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    require(header is not None, "missing YAML frontmatter")
    pairs = re.findall(r"(?m)^(name|description):[ \t]+([^\r\n]+)$", header.group(1))
    require(len(pairs) == 2 and len(dict(pairs)) == 2, "missing or duplicate skill metadata")
    fields = {key: scalar(value) for key, value in pairs}
    require(fields["name"] == name, "skill name does not match target")
    require(len(fields["description"]) >= 10, "missing skill trigger description")
    metadata = files[prefix + "agents/openai.yaml"].decode("utf-8")
    invocation_metadata(metadata, name)
    for path, body in files.items():
        if not path.startswith(prefix) or not path.endswith(".md"):
            continue
        text = body.decode("utf-8")
        refs = re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", text)
        # Inline helper references must travel with the bundle too.
        refs += re.findall(r"`(scripts/[A-Za-z0-9_./-]+\.(?:py|sh|js))`", text)
        for ref in refs:
            ref = unquote(ref.strip("<>"))
            if ref.startswith(("https://", "http://", "mailto:", "#")):
                continue
            require(":" not in ref and "\\" not in ref and not ref.startswith("/"), "unsafe local reference")
            parts = list(PurePosixPath(path).parent.parts)
            for part in ref.split("#", 1)[0].split("/"):
                if part == "..":
                    require(parts, "reference escapes bundle dependencies")
                    parts.pop()
                elif part not in ("", "."):
                    parts.append(part)
            require("/".join(parts) in files, "missing local reference/helper dependency: " + ref)


class Store:
    def __init__(self, root):
        self.root = safe_path(root)
        self.budget = Budget()

    def read(self, name):
        return self.budget.json(self.root / name)

    def write(self, name, value):
        atomic_json(self.root / name, value)

    def collect(self, policy, source=None):
        files = {policy["name"] + "/" + k: v for k, v in scan(source or policy["target"], self.budget).items()}
        for name, path in policy["dependencies"].items():
            files.update({name + "/" + k: v for k, v in scan(path, self.budget).items()})
        return files

    def snapshot(self, files):
        listing = manifest(files)
        version = digest(listing)
        root = safe_path(self.root / "versions" / version)
        if root.exists():
            self.version(version)
            return version
        root.mkdir(parents=True)
        for key, body in files.items():
            target = safe_path(root / "files" / relative(key))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        atomic_json(root / "manifest.json", listing)
        return version

    def version(self, version):
        require(isinstance(version, str) and re.fullmatch(r"[0-9a-f]{64}", version), "invalid version digest")
        root = safe_path(self.root / "versions" / version)
        expected = self.budget.json(root / "manifest.json")
        files = scan(root / "files", self.budget)
        require(manifest(files) == expected and digest(expected) == version, "snapshot was modified or is incomplete")
        return files

    def target_hash(self, path):
        return digest(manifest(scan(path, self.budget))) if Path(path).exists() else None

    def recover(self, state):
        journal_path = self.root / "transaction.json"
        if not journal_path.exists():
            return {"recovered": False}
        tx = self.read("transaction.json")
        policy = self.read("policy.json")
        target = safe_path(policy["target"])
        require(tx["target"] == str(target), "transaction target mismatch")
        scratch = safe_path(tx["scratch"])
        require(scratch.parent == safe_path(tempfile.gettempdir()) and scratch.name.startswith("reflect-switch-"), "unsafe transaction scratch")
        old, new = scratch / "old", scratch / "new"
        live_hash, old_hash, new_hash = [self.target_hash(p) for p in (target, old, new)]
        require(live_hash in (None, tx["old_hash"], tx["new_hash"]) and old_hash in (None, tx["old_hash"]) and new_hash in (None, tx["new_hash"]), "transaction contains externally modified data; preserved for reconciliation")
        if state["active"] == tx["to"]:
            require(live_hash == tx["new_hash"], "committed target is missing; preserve transaction for reconciliation")
        else:
            require(state["active"] == tx["from"], "transaction active version mismatch")
            if live_hash == tx["new_hash"]:
                require(old_hash == tx["old_hash"] and new_hash is None, "cannot safely undo transaction")
                os.replace(target, new)
                live_hash = None
            if live_hash is None:
                require(old_hash == tx["old_hash"], "original bundle is missing; preserve transaction")
                os.replace(old, target)
            require(self.target_hash(target) == tx["old_hash"], "recovery could not restore original bundle")
        # Only expected, hash-checked temporary payloads are removed.
        for path, expected in ((old, tx["old_hash"]), (new, tx["new_hash"])):
            if path.exists():
                require(self.target_hash(path) == expected, "temporary payload changed; preserved")
                shutil.rmtree(path)
        scratch.rmdir()
        journal_path.unlink()
        return {"recovered": True, "active": state["active"]}

    def switch(self, policy, state, version, next_state):
        require(not (self.root / "transaction.json").exists(), "recover the pending transaction first")
        target = safe_path(policy["target"])
        current = self.collect(policy)
        require(digest(manifest(current)) == state["active"], "active bundle or dependency changed; refusing overwrite")
        files = self.version(version)
        prefix = policy["name"] + "/"
        old_files = {k[len(prefix):]: v for k, v in current.items() if k.startswith(prefix)}
        new_files = {k[len(prefix):]: v for k, v in files.items() if k.startswith(prefix)}
        require({k: v for k, v in files.items() if not k.startswith(prefix)} == {k: v for k, v in current.items() if not k.startswith(prefix)}, "dependencies changed since snapshot")
        scratch = Path(tempfile.mkdtemp(prefix="reflect-switch-"))
        try:
            require(target.stat().st_dev == scratch.stat().st_dev, "system TEMP and target must be on the same filesystem; switch disabled")
            new, old = scratch / "new", scratch / "old"
            new.mkdir()
            for key, body in new_files.items():
                path = new / relative(key)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            tx = {"target": str(target), "scratch": str(scratch), "from": state["active"], "to": version,
                  "old_hash": digest(manifest(old_files)), "new_hash": digest(manifest(new_files))}
            self.write("transaction.json", tx)
            require(digest(manifest(self.collect(policy))) == state["active"], "active bundle changed before commit")
            os.replace(target, old)
            os.replace(new, target)
            require(self.target_hash(target) == tx["new_hash"], "installed payload was modified during switching")
            self.write("state.json", next_state)
            self.recover(next_state)
        except BaseException:
            if (self.root / "transaction.json").exists():
                self.recover(self.read("state.json"))
            elif scratch.exists():
                shutil.rmtree(scratch)
            raise
