from __future__ import annotations

import hashlib
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path


class GitCommandError(RuntimeError):
    pass


class GitBudgetExceeded(GitCommandError):
    pass


class _GitOutputBudget:
    def __init__(self, capacity: int):
        self._capacity = max(0, capacity)
        self._consumed = 0
        self._lock = threading.Lock()

    def consume(self, actual: int) -> bool:
        if actual < 0:
            raise ValueError("Git output byte count was invalid")
        with self._lock:
            if self._consumed + actual > self._capacity:
                return False
            self._consumed += actual
            return True

    @property
    def consumed(self) -> int:
        with self._lock:
            return self._consumed


def _git_pipe_buffer_sizes(capacity: int) -> tuple[int, int]:
    capacity = max(0, capacity)
    if capacity <= 1:
        return (1, 1)
    stdout_size = min(65_536, (capacity + 1) // 2)
    stderr_size = min(65_536, capacity - stdout_size)
    return (stdout_size, stderr_size)


@dataclass(frozen=True)
class RefRecord:
    name: str
    object_id: str
    object_type: str
    peeled_id: str | None
    peeled_type: str | None


@dataclass(frozen=True)
class BlobLocation:
    path: str | None = None
    commit: str | None = None
    ref: str | None = None
    mode: str | None = None


@dataclass
class HistoryBlob:
    object_id: str
    size: int
    data: bytes | None
    locations: list[BlobLocation] = field(default_factory=list)


@dataclass(frozen=True)
class HistoryGap:
    evidence: str
    object_id: str | None = None
    size: int | None = None


@dataclass
class HistorySnapshot:
    blobs: list[HistoryBlob]
    gaps: list[HistoryGap]


def _sanitized_git_environment(*, literal_pathspecs: bool = True) -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith("GIT_")
        and not name.upper().startswith("SSH_")
        and name.upper() != "GCM_INTERACTIVE"
    }
    environment.update(
        {
            "GCM_INTERACTIVE": "Never",
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    if literal_pathspecs:
        environment["GIT_LITERAL_PATHSPECS"] = "1"
    return environment


class GitRepository:
    def __init__(
        self,
        root: Path,
        timeout_seconds: int = 30,
        *,
        deadline: float | None = None,
        max_git_commands: int = 64,
        max_total_bytes: int = 268_435_456,
        max_work_units: int = 1_000_000,
        max_locations: int = 250_000,
    ):
        self.root = Path(root).resolve()
        self._deadline = (
            time.monotonic() + max(0, timeout_seconds)
            if deadline is None
            else deadline
        )
        self._max_git_commands = max_git_commands
        self._commands_used = 0
        self._max_total_bytes = max_total_bytes
        self._bytes_used = 0
        self._max_work_units = max_work_units
        self._work_units_used = 0
        self._max_locations = max_locations
        self._locations_used = 0
        self.missing_objects: list[str] = []
        self.root = Path(
            self.run("rev-parse", "--show-toplevel").decode("utf-8").strip()
        ).resolve()
        self.object_format = (
            self.run("rev-parse", "--show-object-format")
            .decode("ascii", errors="strict")
            .strip()
        )
        if self.object_format not in {"sha1", "sha256"}:
            raise GitCommandError("Git object format is unsupported")

    @property
    def commands_used(self) -> int:
        return self._commands_used

    def check_budget(self) -> None:
        if time.monotonic() >= self._deadline:
            raise GitBudgetExceeded("audit deadline exhausted")

    def try_consume_bytes(self, size: int) -> bool:
        self.check_budget()
        if size < 0 or self._bytes_used + size > self._max_total_bytes:
            return False
        self._bytes_used += size
        return True

    @staticmethod
    def _terminate_and_reap(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
        process.wait()

    def _run_bounded_process(
        self,
        command: list[str],
        *,
        input_bytes: bytes | None,
        literal_pathspecs: bool = True,
        ok_returncodes: tuple[int, ...] = (0,),
    ) -> bytes:
        process = subprocess.Popen(
            command,
            cwd=self.root,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_sanitized_git_environment(
                literal_pathspecs=literal_pathspecs
            ),
            shell=False,
            bufsize=0,
        )
        assert process.stdout is not None
        assert process.stderr is not None
        events: queue.Queue[
            tuple[str, bytes | None, BaseException | None]
        ] = queue.Queue(maxsize=2)
        output_capacity = self._max_total_bytes - self._bytes_used
        output_budget = _GitOutputBudget(output_capacity)
        output_budget_exhausted = threading.Event()

        def drain(name: str, stream: object, buffer_size: int) -> None:
            buffer = bytearray(buffer_size)
            try:
                while True:
                    if output_budget_exhausted.is_set():
                        break
                    actual = stream.readinto(buffer)  # type: ignore[attr-defined]
                    if actual is None or actual == 0:
                        break
                    if actual < 0 or actual > len(buffer):
                        raise ValueError("Git command output read was invalid")
                    if not output_budget.consume(actual):
                        output_budget_exhausted.set()
                        events.put(
                            (
                                name,
                                None,
                                GitBudgetExceeded(
                                    "audit total-byte budget exhausted by Git output"
                                ),
                            )
                        )
                        break
                    if name == "stdout":
                        events.put((name, bytes(memoryview(buffer)[:actual]), None))
            except (OSError, TypeError, ValueError) as error:
                events.put((name, None, error))
            finally:
                try:
                    stream.close()  # type: ignore[attr-defined]
                finally:
                    events.put((name, None, None))

        stdout_buffer_size, stderr_buffer_size = _git_pipe_buffer_sizes(
            output_capacity
        )
        readers = [
            threading.Thread(
                target=drain,
                args=("stdout", process.stdout, stdout_buffer_size),
            ),
            threading.Thread(
                target=drain,
                args=("stderr", process.stderr, stderr_buffer_size),
            ),
        ]
        for reader in readers:
            reader.start()

        writer: threading.Thread | None = None
        if input_bytes is not None:
            assert process.stdin is not None

            def write_input() -> None:
                try:
                    remaining = memoryview(input_bytes)
                    while remaining:
                        written = process.stdin.write(remaining)
                        if written is None or written <= 0:
                            break
                        remaining = remaining[written:]
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    try:
                        process.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass

            writer = threading.Thread(target=write_input)
            writer.start()

        stdout = bytearray()
        finished: set[str] = set()
        failure: GitCommandError | None = None
        while len(finished) < 2:
            if failure is None and time.monotonic() >= self._deadline:
                failure = GitBudgetExceeded("audit deadline exhausted")
                self._terminate_and_reap(process)
            try:
                name, chunk, read_error = events.get(timeout=0.05)
            except queue.Empty:
                continue
            if read_error is not None and failure is None:
                failure = (
                    read_error
                    if isinstance(read_error, GitBudgetExceeded)
                    else GitCommandError("Git command output could not be read")
                )
                self._terminate_and_reap(process)
                continue
            if chunk is None:
                finished.add(name)
                continue
            if failure is not None:
                continue
            stdout.extend(chunk)

        for reader in readers:
            reader.join()
        if writer is not None:
            writer.join()
        self._bytes_used += output_budget.consumed
        if process.poll() is None:
            remaining = self._deadline - time.monotonic()
            try:
                process.wait(timeout=max(0, remaining))
            except subprocess.TimeoutExpired:
                failure = GitBudgetExceeded("audit deadline exhausted")
                self._terminate_and_reap(process)
        if failure is not None:
            raise failure
        if process.returncode not in ok_returncodes:
            raise GitCommandError("Git command failed")
        return bytes(stdout)

    def consume_work(
        self,
        units: int = 1,
        *,
        retained_bytes: int = 0,
        locations: int = 0,
    ) -> None:
        self.check_budget()
        if units < 0 or self._work_units_used + units > self._max_work_units:
            raise GitBudgetExceeded("audit work-unit budget exhausted")
        if locations < 0 or self._locations_used + locations > self._max_locations:
            raise GitBudgetExceeded("audit location budget exhausted")
        if retained_bytes < 0 or not self.try_consume_bytes(retained_bytes):
            raise GitBudgetExceeded("audit total-byte budget exhausted")
        self._work_units_used += units
        self._locations_used += locations

    def run(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        literal_pathspecs: bool = True,
        ok_returncodes: tuple[int, ...] = (0,),
    ) -> bytes:
        self.check_budget()
        if self._commands_used >= self._max_git_commands:
            raise GitBudgetExceeded("Git command budget exhausted")
        self._commands_used += 1
        command = [
            "git",
            "--no-optional-locks",
            *(["--literal-pathspecs"] if literal_pathspecs else []),
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "credential.interactive=false",
            *args,
        ]
        return self._run_bounded_process(
            command,
            input_bytes=input_bytes,
            literal_pathspecs=literal_pathspecs,
            ok_returncodes=ok_returncodes,
        )

    def status_entries(self) -> dict[str, list[str]]:
        tracked = self._nul_paths(self.run("ls-files", "--cached", "-z"))
        untracked = self._nul_paths(
            self.run("ls-files", "--others", "--exclude-standard", "-z")
        )
        ignored = self._nul_paths(
            self.run("ls-files", "--others", "--ignored", "--exclude-standard", "-z")
        )
        return {
            "tracked": sorted(tracked),
            "untracked": sorted(untracked),
            "ignored": sorted(ignored),
        }

    def ref_snapshot(self) -> list[RefRecord]:
        output = self.run(
            "for-each-ref",
            "--format=%(refname)%00%(objectname)%00%(objecttype)%00%(*objectname)%00%(*objecttype)",
        )
        records: list[RefRecord] = []
        for line in output.splitlines():
            self.consume_work(retained_bytes=len(line))
            parts = line.split(b"\0")
            if len(parts) != 5:
                raise GitCommandError("Git ref metadata was malformed")
            name, object_id, object_type, peeled_id, peeled_type = (
                part.decode("utf-8", errors="surrogateescape") for part in parts
            )
            records.append(
                RefRecord(
                    name=name,
                    object_id=object_id,
                    object_type=object_type,
                    peeled_id=peeled_id or None,
                    peeled_type=peeled_type or None,
                )
            )
        return sorted(records, key=lambda record: record.name)

    def refs(self) -> list[str]:
        return [record.name for record in self.ref_snapshot()]

    def is_shallow(self) -> bool:
        return self.run("rev-parse", "--is-shallow-repository").strip() == b"true"

    def hash_blob(self, data: bytes) -> str:
        digest = hashlib.new(self.object_format)
        digest.update(f"blob {len(data)}\0".encode("ascii"))
        digest.update(data)
        return digest.hexdigest()

    def history_snapshot(
        self, refs: list[RefRecord], *, max_blob_bytes: int
    ) -> HistorySnapshot:
        listed = self._text_lines(
            self.run(
                "rev-list",
                "--objects",
                "--all",
                "--reverse",
                "--topo-order",
                "--missing=print",
                "--no-object-names",
            )
        )
        missing = {line[1:] for line in listed if line.startswith("?")}
        object_order = list(dict.fromkeys(line for line in listed if not line.startswith("?")))
        gaps = [
            HistoryGap(
                evidence="reachable Git object is missing locally and was not fetched",
                object_id=object_id,
            )
            for object_id in sorted(missing)
        ]
        self.missing_objects = sorted(missing)
        if not object_order:
            return HistorySnapshot(blobs=[], gaps=gaps)

        metadata = self._batch_check(object_order)
        metadata_by_id = {
            object_id: (object_type, size)
            for object_id, object_type, size in metadata
        }
        known_ids = set(metadata_by_id)
        for object_id in object_order:
            self.consume_work()
            if object_id not in known_ids and object_id not in missing:
                gaps.append(
                    HistoryGap(
                        evidence="reachable Git object metadata is unavailable",
                        object_id=object_id,
                    )
                )

        structure_ids = [
            object_id
            for object_id in object_order
            if metadata_by_id.get(object_id, (None, 0))[0]
            in {"commit", "tree", "tag"}
        ]
        blob_ids = sorted(
            object_id
            for object_id, (object_type, _) in metadata_by_id.items()
            if object_type == "blob"
        )
        requested: list[str] = []
        unavailable_content: set[str] = set()
        for object_id in structure_ids + blob_ids:
            self.consume_work()
            object_type, size = metadata_by_id[object_id]
            if object_type == "blob" and size > max_blob_bytes:
                gaps.append(
                    HistoryGap(
                        evidence="reachable blob exceeds the configured scan limit",
                        object_id=object_id,
                        size=size,
                    )
                )
                unavailable_content.add(object_id)
                continue
            if not self.try_consume_bytes(size):
                gaps.append(
                    HistoryGap(
                        evidence="audit total-byte budget exhausted before object content read",
                        object_id=object_id,
                        size=size,
                    )
                )
                unavailable_content.add(object_id)
                continue
            requested.append(object_id)

        contents = self._batch_read(requested) if requested else {}
        for object_id in requested:
            self.consume_work()
            if object_id not in contents:
                _, size = metadata_by_id[object_id]
                gaps.append(
                    HistoryGap(
                        evidence="reachable Git object content is unavailable",
                        object_id=object_id,
                        size=size,
                    )
                )
                unavailable_content.add(object_id)

        tree_entries: dict[str, tuple[tuple[str, str, str], ...]] = {}
        flattened_roots: dict[str, tuple[tuple[str, str, str], ...]] = {}

        def flatten_tree(tree_id: str) -> tuple[tuple[str, str, str], ...]:
            cached = flattened_roots.get(tree_id)
            if cached is not None:
                return cached
            if tree_id not in contents:
                return ()
            flattened: list[tuple[str, str, str]] = []
            stack: list[tuple[str, str]] = [(tree_id, "")]
            while stack:
                self.consume_work()
                current_tree, prefix = stack.pop()
                entries = tree_entries.get(current_tree)
                if entries is None:
                    tree_data = contents.get(current_tree)
                    if tree_data is None:
                        continue
                    entries = tuple(self._parse_tree(tree_data))
                    tree_entries[current_tree] = entries
                for mode, name, object_id in reversed(entries):
                    self.consume_work()
                    path = f"{prefix}/{name}" if prefix else name
                    self.consume_work(
                        retained_bytes=len(
                            path.encode("utf-8", errors="surrogateescape")
                        )
                    )
                    if mode == "40000":
                        stack.append((object_id, path))
                    elif (
                        mode != "160000"
                        and metadata_by_id.get(object_id, (None, 0))[0] == "blob"
                    ):
                        self.consume_work(retained_bytes=len(mode))
                        flattened.append((path, object_id, mode))
            flattened_roots[tree_id] = tuple(sorted(flattened))
            return flattened_roots[tree_id]

        locations: dict[str, list[BlobLocation]] = {
            object_id: [] for object_id in blob_ids
        }
        seen_path_locations: set[tuple[str, str, str]] = set()
        seen_commit_roots: set[str] = set()

        def add_location(blob_id: str, location: BlobLocation) -> None:
            retained_bytes = sum(
                len(value.encode("utf-8", errors="surrogateescape"))
                for value in (location.path, location.commit, location.ref, location.mode)
                if value is not None
            )
            self.consume_work(retained_bytes=retained_bytes, locations=1)
            locations.setdefault(blob_id, []).append(location)

        for commit_id in object_order:
            self.consume_work()
            if metadata_by_id.get(commit_id, (None, 0))[0] != "commit":
                continue
            commit_data = contents.get(commit_id)
            if commit_data is None:
                continue
            tree_id = self._commit_tree(commit_data)
            if tree_id in seen_commit_roots:
                continue
            seen_commit_roots.add(tree_id)
            for path, blob_id, mode in flatten_tree(tree_id):
                self.consume_work()
                key = (blob_id, path, mode)
                if key in seen_path_locations:
                    continue
                seen_path_locations.add(key)
                add_location(blob_id, BlobLocation(path=path, commit=commit_id, mode=mode))

        for ref in refs:
            self.consume_work()
            target_id = ref.peeled_id or ref.object_id
            target_type = ref.peeled_type or ref.object_type
            if target_type == "blob":
                add_location(target_id, BlobLocation(ref=ref.name))
            elif target_type == "tree":
                for path, blob_id, mode in flatten_tree(target_id):
                    self.consume_work()
                    add_location(blob_id, BlobLocation(path=path, ref=ref.name, mode=mode))

        blobs: list[HistoryBlob] = []
        for object_id in blob_ids:
            self.consume_work()
            _, size = metadata_by_id[object_id]
            blob_locations = locations.get(object_id, [])
            if not blob_locations:
                gaps.append(
                    HistoryGap(
                        evidence="reachable blob provenance could not be derived",
                        object_id=object_id,
                        size=size,
                    )
                )
                blob_locations = [BlobLocation()]
            blobs.append(
                HistoryBlob(
                    object_id=object_id,
                    size=size,
                    data=(
                        None
                        if object_id in unavailable_content
                        else contents.get(object_id)
                    ),
                    locations=sorted(
                        set(blob_locations),
                        key=lambda item: (
                            item.path or "",
                            item.commit or "",
                            item.ref or "",
                            item.mode or "",
                        ),
                    ),
                )
            )
        return HistorySnapshot(blobs=blobs, gaps=gaps)

    def reachable_blobs(self) -> list[tuple[str, str, int]]:
        snapshot = self.history_snapshot(
            self.ref_snapshot(), max_blob_bytes=2**63 - 1
        )
        return sorted(
            (blob.object_id, location.path, blob.size)
            for blob in snapshot.blobs
            for location in blob.locations
            if location.path is not None
        )

    def read_blob(self, object_id: str) -> bytes:
        return self.run("cat-file", "blob", object_id)

    def _batch_check(self, object_ids: list[str]) -> list[tuple[str, str, int]]:
        output = self.run(
            "cat-file",
            "--batch-check=%(objectname) %(objecttype) %(objectsize)",
            input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
        )
        metadata: list[tuple[str, str, int]] = []
        for line in self._text_lines(output):
            self.consume_work()
            parts = line.split(" ")
            if len(parts) == 2 and parts[1] == "missing":
                continue
            if len(parts) != 3:
                raise GitCommandError("Git object metadata was malformed")
            object_id, object_type, size = parts
            metadata.append((object_id, object_type, int(size)))
        return metadata

    def _batch_read(self, object_ids: list[str]) -> dict[str, bytes]:
        output = self.run(
            "cat-file",
            "--batch",
            input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
        )
        contents: dict[str, bytes] = {}
        offset = 0
        for expected_id in object_ids:
            self.consume_work()
            line_end = output.find(b"\n", offset)
            if line_end < 0:
                break
            header = output[offset:line_end].decode("ascii", errors="strict").split(" ")
            offset = line_end + 1
            if len(header) == 2 and header[1] == "missing":
                continue
            if len(header) != 3:
                raise GitCommandError("Git object batch output was malformed")
            object_id, _, size_text = header
            size = int(size_text)
            end = offset + size
            if (
                object_id != expected_id
                or end >= len(output)
                or output[end : end + 1] != b"\n"
            ):
                raise GitCommandError("Git object batch output was malformed")
            contents[object_id] = output[offset:end]
            offset = end + 1
        return contents

    def _parse_tree(self, data: bytes) -> list[tuple[str, str, str]]:
        hash_size = 20 if self.object_format == "sha1" else 32
        entries: list[tuple[str, str, str]] = []
        offset = 0
        while offset < len(data):
            self.consume_work()
            space = data.find(b" ", offset)
            nul = data.find(b"\0", space + 1)
            if space < 0 or nul < 0 or nul + 1 + hash_size > len(data):
                raise GitCommandError("Git tree object was malformed")
            mode = data[offset:space].decode("ascii")
            name = data[space + 1 : nul].decode("utf-8", errors="surrogateescape")
            object_id = data[nul + 1 : nul + 1 + hash_size].hex()
            self.consume_work(retained_bytes=len(name.encode("utf-8", errors="surrogateescape")))
            entries.append((mode.lstrip("0"), name, object_id))
            offset = nul + 1 + hash_size
        return entries

    @staticmethod
    def _commit_tree(data: bytes) -> str:
        first_line = data.split(b"\n", 1)[0]
        prefix = b"tree "
        if not first_line.startswith(prefix):
            raise GitCommandError("Git commit object was malformed")
        return first_line[len(prefix) :].decode("ascii", errors="strict")

    def _nul_paths(self, output: bytes) -> list[str]:
        paths: list[str] = []
        for entry in output.split(b"\0"):
            if not entry:
                continue
            self.consume_work(retained_bytes=len(entry))
            paths.append(entry.decode("utf-8", errors="surrogateescape"))
        return paths

    def _text_lines(self, output: bytes) -> list[str]:
        lines: list[str] = []
        for line in output.splitlines():
            self.consume_work(retained_bytes=len(line))
            lines.append(line.decode("utf-8", errors="surrogateescape"))
        return lines
