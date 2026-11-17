"""Bounded native Codex read APIs; no thread/turn creation, raw history store or model calls."""
import ctypes
import json
import os
from pathlib import Path
import queue
import signal
import stat
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True

from store import require


def safe_path(value):
    """Inspect components without following a redirect into foreign storage."""
    path = Path(os.path.abspath(os.fspath(value)))
    if os.name == "nt":
        require(len(path.drive) == 2 and path.drive.endswith(":"), "remote/device paths are forbidden")
        require(all(":" not in part for part in path.parts[1:]), "named streams are forbidden")
    for item in (*reversed(path.parents), path):
        try: info = item.lstat()
        except FileNotFoundError: break
        require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400),
                "links/junctions/reparse points are forbidden")
    return path


def create_job():
    from ctypes import wintypes as w
    class Basic(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong), ("flags", w.DWORD),
                    ("min_working", ctypes.c_size_t), ("max_working", ctypes.c_size_t), ("active", w.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", ctypes.c_ulonglong * 6), ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    job = kernel.CreateJobObjectW(None, None)
    if not job: raise OSError("cannot create owned job")
    info = Extended()
    info.basic.flags = 0x2000  # Kill every member when its sole owner closes the handle.
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        close_job(job)
        raise OSError("cannot configure owned job")
    return job


def assign_job(job, process):
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    if not kernel.AssignProcessToJobObject(job, int(process._handle)):
        raise OSError("cannot establish process ownership")


def close_job(job):
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle(job)


class Client:
    METHODS = {"initialize", "thread/list", "thread/read", "thread/items/list"}

    def __init__(self, command, project, deadline, budget=None):
        self.command, self.project, self.deadline, self.budget = command, project, deadline, budget
        self.process = self.job = None
        self.assigned = False
        self.inbox = queue.Queue(maxsize=8)
        self.failure = None
        self.reader = None
        self.counter = self.bytes = 0
        self.native_pid = None

    def __enter__(self):
        try:
            require(time.monotonic() < self.deadline, "lookup budget exhausted before startup")
            if os.name == "nt": self.job = create_job()
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--owned-launcher"] if self.job else self.command
            self.process = subprocess.Popen(command, cwd=self.project, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, start_new_session=os.name != "nt",
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if self.job:
                assign_job(self.job, self.process)
                self.assigned = True
            self.reader = threading.Thread(target=self.read, daemon=True)
            self.reader.start()
            if self.job:
                self.send({"command": self.command})
                ready = self.receive()
                require(ready.get("_ownedReady") is True, "owned launcher did not initialize")
                self.native_pid = ready.get("native_pid")
            else: self.native_pid = self.process.pid
            self.request("initialize", {"clientInfo": {"name": "project-experience-recall", "version": "2"}})
            self.send({"method": "initialized", "params": {}})
            return self
        except BaseException as error:
            self.close()
            error.recall_processes = self.cleanup_record()
            raise

    def read(self):
        try:
            pending = b""
            while True:
                available = min(8192, 4 * 1024 * 1024 - self.bytes)
                if self.budget: available = min(available, self.budget.remaining())
                require(available > 0, "native output budget exhausted")
                chunk = self.process.stdout.read1(available)
                if not chunk: break
                self.bytes += len(chunk)
                if self.budget: self.budget.check(len(chunk))
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    require(len(line) + 1 <= 1024 * 1024, "native line budget exhausted")
                    packet = json.loads(line)
                    require(isinstance(packet, dict), "invalid native response")
                    self.inbox.put_nowait(packet)
                require(len(pending) < 1024 * 1024, "native line budget exhausted")
        except (OSError, ValueError, RecursionError, queue.Full): self.failure = "invalid-or-excessive-native-output"
        finally:
            if self.failure is None: self.failure = "native-stream-closed"

    def receive(self):
        while time.monotonic() < self.deadline:
            try: return self.inbox.get(timeout=min(0.1, max(0.001, self.deadline - time.monotonic())))
            except queue.Empty:
                require(self.failure is None, "native history unavailable")
        raise TimeoutError("native history deadline exhausted")

    def send(self, value):
        self.process.stdin.write((json.dumps(value) + "\n").encode())
        self.process.stdin.flush()

    def request(self, method, params):
        require(method in self.METHODS, "only native read methods are permitted")
        if method == "thread/list":
            require(params.get("cwd") == str(self.project) and params.get("useStateDbOnly") is True,
                    "exact project and read-only history metadata are required")
        self.counter += 1
        request_id = self.counter
        self.send({"id": request_id, "method": method, "params": params})
        while True:
            packet = self.receive()
            if packet.get("id") == request_id:
                require("error" not in packet and isinstance(packet.get("result"), dict), "native read request refused")
                return packet["result"]

    def close(self):
        if self.process:
            if os.name == "nt":
                if self.job and self.assigned: close_job(self.job)
                elif self.process.poll() is None: self.process.kill()  # Launcher still gated; it has no children.
            else:
                try: os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            self.process.wait(timeout=2)
            for stream in (self.process.stdin, self.process.stdout):
                if stream: stream.close()
        if self.job and not self.assigned: close_job(self.job)
        self.job = None
        if self.reader: self.reader.join(timeout=0.2)

    def cleanup_record(self):
        return {"owned_pids": [p for p in (getattr(self.process, "pid", None), self.native_pid) if p],
                "owned_process_exited": self.process is None or self.process.poll() is not None}

    def __exit__(self, kind, error, traceback):
        self.close()
        if error is not None: error.recall_processes = self.cleanup_record()


def find_codex(explicit, project):
    if explicit:
        require(Path(explicit).is_absolute(), "native executable must be absolute")
        executable = safe_path(explicit)
        require(executable.is_file() and not executable.is_relative_to(project), "native executable must be installed outside project")
        return executable
    # Do not search PATH: an untrusted repository can shadow that executable.
    root = Path.home() / "AppData/Local/OpenAI/Codex/bin"
    require(root.is_dir(), "native Codex installation unavailable; reports remain usable")
    safe_path(root)
    choices = [safe_path(p / "codex.exe") for p in sorted(root.iterdir())[:16] if (p / "codex.exe").is_file()]
    require(choices, "native Codex executable unavailable")
    return max(choices, key=lambda p: p.stat().st_mtime_ns)


def same_project(metadata, project):
    try:
        cwd = metadata.get("cwd")
        return (isinstance(cwd, str) and Path(cwd).is_absolute()
                and Path(os.path.abspath(cwd)) == project and safe_path(cwd) == project)
    except (OSError, ValueError, TypeError): return False


def history(project, query, budget, explicit=None):
    executable = find_codex(explicit, project)
    records, listed, seen_items = [], {}, set()
    coverage = {"status": "available", "partial": True, "metadata_pages": 0, "chats_read": 0}
    current = os.environ.get("CODEX_THREAD_ID")
    with Client([str(executable), "-c", "features.apps=false", "app-server"], project, budget.deadline, budget) as client:
        coverage["owned_pid"] = getattr(getattr(client, "process", None), "pid", None)
        cursors = {False: None, True: None}
        seen_cursors = set()
        for archived in (False, True, False):
            cursor = cursors[archived]
            if (archived, cursor) in seen_cursors: continue
            seen_cursors.add((archived, cursor))
            params = {"cwd": str(project), "useStateDbOnly": True, "limit": 20, "archived": archived,
                      "sortKey": "updated_at", "sortDirection": "desc", "excludedThreadIds": [current] if current else []}
            if cursor: params["cursor"] = cursor
            page = client.request("thread/list", params)
            coverage["metadata_pages"] += 1
            cursors[archived] = page.get("nextCursor")
            for item in page.get("data", [])[:20]:
                if isinstance(item, dict) and item.get("id") and item["id"] != current and not item.get("parentThreadId") and same_project(item, project):
                    listed[item["id"]] = item
        def score(item):
            title = str(item.get("name") or item.get("preview") or "").casefold()
            return (-sum(word in title for word in query), -int(item.get("updatedAt") or 0), item["id"])
        for item in sorted(listed.values(), key=score)[:6]:
            identity = item["id"]
            metadata = client.request("thread/read", {"threadId": identity, "includeTurns": False}).get("thread", {})
            if metadata.get("id") != identity or not same_project(metadata, project): continue
            coverage["chats_read"] += 1
            for limit, direction in ((16, "desc"), (4, "asc")):
                page = client.request("thread/items/list", {"threadId": identity, "limit": limit, "sortDirection": direction})
                for entry in page.get("data", [])[:limit]:
                    message = entry.get("item", {})
                    kind = message.get("type")
                    if kind not in ("userMessage", "agentMessage"): continue
                    key = (identity, message.get("id"))
                    if key in seen_items: continue
                    seen_items.add(key)
                    if kind == "agentMessage": text = message.get("text", "")
                    else: text = "\n".join(p.get("text", "") for p in message.get("content", []) if p.get("type") == "text")
                    if isinstance(text, str):
                        records.append({"text": text[:16000], "source": {"kind": "chat", "thread_id": identity,
                                        "turn_id": entry.get("turnId"), "item_id": message.get("id"), "message_type": kind}})
    if hasattr(client, "cleanup_record"): coverage.update(client.cleanup_record())
    else: coverage["owned_process_exited"] = True
    return records, coverage


def launch_owned():
    # Parent assigns this trusted gated launcher before supplying any native command.
    config = json.loads(sys.stdin.buffer.readline(65537))
    command = config["command"]
    require(isinstance(command, list) and all(isinstance(p, str) for p in command), "invalid launcher command")
    process = subprocess.Popen(command, stdin=sys.stdin.buffer, stdout=sys.stdout.buffer, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    print(json.dumps({"_ownedReady": True, "native_pid": process.pid}), flush=True)
    return process.wait()


if __name__ == "__main__":
    require(sys.argv[1:] == ["--owned-launcher"], "internal owned launcher only")
    raise SystemExit(launch_owned())
