import ctypes
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from .storage import CampaignError, child, load_campaign, now, read_json, redact, write_json


def identity(pid):
    try:
        if os.name == 'nt':
            from ctypes import wintypes as w
            k = ctypes.WinDLL('kernel32', use_last_error=True)
            k.OpenProcess.restype = w.HANDLE
            k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
            k.GetProcessTimes.argtypes = [w.HANDLE, *([ctypes.POINTER(w.FILETIME)] * 4)]
            k.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
            k.CloseHandle.argtypes = [w.HANDLE]
            h = k.OpenProcess(0x1000, False, int(pid))
            if not h:
                return None
            try:
                code = w.DWORD()
                if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:
                    return None
                times = [w.FILETIME() for _ in range(4)]
                if not k.GetProcessTimes(h, *[ctypes.byref(x) for x in times]):
                    return None
                birth = str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
            finally:
                k.CloseHandle(h)
        else:
            fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
            if fields[0] == 'Z':
                return None
            birth = fields[19]
        return {'pid': int(pid), 'birth': birth}
    except (OSError, ValueError, IndexError):
        return None


def stop_owned(record):
    if not record or identity(record['pid']) != {k: record[k] for k in ('pid', 'birth')}:
        return False
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(record['pid']), '/T', '/F'], capture_output=True, timeout=30)
    else:
        os.killpg(record['pid'], signal.SIGKILL)
    return True


class WindowsJob:
    def __init__(self, process):
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_ = [('per_process', ctypes.c_int64), ('per_job', ctypes.c_int64), ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t), ('active', w.DWORD), ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_mem', ctypes.c_size_t), ('job_mem', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        info = Extended(); info.basic.flags = 0x2000  # Kill the owned tree when its supervisor dies.
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)) or not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            self.close()
            raise CampaignError('Windows Job Object containment unavailable; workload was not released')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle); self.handle = None


def project_env(root, additions=None):
    root = Path(root).absolute()
    env = os.environ.copy()
    dirs = {'HOME': 'home', 'USERPROFILE': 'home', 'APPDATA': 'home/AppData/Roaming', 'LOCALAPPDATA': 'home/AppData/Local', 'XDG_CONFIG_HOME': 'config', 'XDG_CACHE_HOME': 'cache', 'XDG_DATA_HOME': 'data', 'XDG_STATE_HOME': 'state', 'TMP': 'tmp', 'TEMP': 'tmp', 'TMPDIR': 'tmp', 'npm_config_cache': 'cache/npm', 'PIP_CACHE_DIR': 'cache/pip', 'SVM_HOME': 'cache/svm', 'FOUNDRY_CACHE_PATH': 'cache/foundry', 'CARGO_HOME': 'cache/cargo'}
    for key, rel in dirs.items():
        p = child(root, rel); p.mkdir(parents=True, exist_ok=True); env[key] = str(p)
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', CI='1', NO_COLOR='1', GIT_TERMINAL_PROMPT='0')
    env.update(additions or {})
    return env


def guard(request_path):
    request_path = Path(request_path)
    request = read_json(request_path)
    deadline = time.monotonic() + 10
    ready = request_path.parent / 'release'
    while not ready.exists():
        if identity(request['owner']['pid']) != request['owner'] or time.monotonic() > deadline:
            return 125
        time.sleep(.02)
    source = open(request['stdin_path'], 'rb') if request.get('stdin_path') else None
    try:
        argv = []
        for arg in request['argv']:
            if isinstance(arg, dict):
                name = arg.get('env', '')
                if set(arg) != {'env'} or not re.fullmatch('MUTATION_SECRET_ARG_[0-9]+', name):
                    raise CampaignError('invalid private argv reference')
                arg = os.environ[name]
            argv.append(arg)
        proc = subprocess.Popen(argv, cwd=request['cwd'], stdin=source if source else subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    finally:
        if source:
            source.close()
    while proc.poll() is None:
        if identity(request['owner']['pid']) != request['owner']:
            if os.name != 'nt':
                os.killpg(os.getpgrp(), signal.SIGKILL)
            proc.kill()
            return 125
        time.sleep(.05)
    write_json(request_path.parent / 'workload-exit.json', {'exit_code': proc.returncode})
    # Retain the group leader until the controller closes the whole owned tree.
    while identity(request['owner']['pid']) == request['owner']:
        time.sleep(.05)
    if os.name != 'nt':
        os.killpg(os.getpgrp(), signal.SIGKILL)
    return 125


def require_forge_cache_confinement(argv):
    executable = str(argv[0]).replace('\\', '/').rsplit('/', 1)[-1].rsplit('.', 1)[0].lower() if argv else ''
    if os.name != 'nt' or executable != 'forge':
        return
    args = argv[1:]
    option_args = args[:args.index('--')] if '--' in args else args
    if args in (['--version'], ['-V'], ['version']) or '--help' in option_args or '-h' in option_args:
        return
    # shortcut: native Windows cache confinement is unverified; add version-scoped scout evidence before allowing workloads.
    raise CampaignError('native Windows Forge workload blocked because its global cache cannot be proven project-local; run the controller in existing WSL2 or provide independently verified cache-confinement support')


def register_process(run, process, owner, log_dir):
    state, _ = load_campaign(run)
    entry = {'campaign': state['id'], 'scope_sha256': state['scope_sha256'], 'snapshot_sha256': state['snapshot_sha256'], 'process': process, 'owner': owner, 'logs': Path(log_dir).relative_to(run).as_posix()}
    # Only this explicit controller file authorizes recovery cleanup; tool artifacts do not.
    registry = child(run, 'process-registry.jsonl')
    fd = os.open(registry, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(entry, separators=(',', ':')) + '\n').encode())
    finally:
        os.close(fd)


def run_command(argv, cwd, env, log_dir, timeout, idle_timeout, cancel_path, input_text=None, owner_run=None, progress_paths=()):
    require_forge_cache_confinement(argv)
    env = dict(env)
    secrets = [value for key, value in env.items() if len(value) >= 6 and re.search(r'(KEY|TOKEN|SECRET|PASSWORD|RPC_URL|AUTH)', key, re.I)]
    stored_argv = []
    for i, arg in enumerate(argv):
        if re.search(r'https?://', arg) or any(value in arg for value in secrets):
            name = 'MUTATION_SECRET_ARG_' + str(i); env[name] = arg
            stored_argv.append({'env': name})
        else:
            stored_argv.append(arg)
    if Path(argv[0]).name.lower() in ('wsl', 'wsl.exe'):
        raise CampaignError('Run the controller under WSL for Linux tools; Windows wsl.exe is not process-tree containment')
    log_dir = Path(log_dir).absolute(); log_dir.mkdir(parents=True, exist_ok=False)
    request = {'argv': stored_argv, 'cwd': str(Path(cwd).absolute()), 'owner': identity(os.getpid())}
    if input_text is not None:
        source = log_dir / 'stdin.txt'
        source.write_text(input_text, encoding='utf-8', newline='\n')
        request['stdin_path'] = str(source)
    write_json(log_dir / 'request.json', request)
    guard_script = Path(__file__).resolve().parents[1] / 'process_guard.py'
    started = time.monotonic()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    proc = subprocess.Popen([sys.executable, '-B', str(guard_script), str(log_dir / 'request.json')], cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags, start_new_session=os.name != 'nt')
    owned = identity(proc.pid)
    job = None
    threads = []
    last_output = [started]
    def progress_signature():
        signature = []
        for value in progress_paths:
            path = Path(value)
            try:
                stat = path.stat()
                children = ()
                if path.is_dir():
                    children = tuple(sorted((entry.name, entry.stat().st_mtime_ns, entry.stat().st_size) for entry in path.iterdir()))
                signature.append((str(path), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, children))
            except OSError:
                signature.append((str(path), None))
        return tuple(signature)
    last_signature = progress_signature()
    receipt = {'argv': [redact(x, env) for x in argv], 'pid': proc.pid, 'process': owned, 'started_at': now(), 'status': 'running', 'exit_code': None}
    write_json(log_dir / 'process.json', owned)
    write_json(log_dir / 'receipt.json', receipt)
    def copy_stream(stream, target):
        with target.open('w', encoding='utf-8', newline='\n') as out:
            while True:
                data = stream.readline()
                if not data:
                    break
                last_output[0] = time.monotonic()
                out.write(redact(data.decode('utf-8', 'replace'), env)); out.flush()
        stream.close()
    try:
        if not owned:
            raise CampaignError('cannot establish process identity')
        if os.name == 'nt':
            job = WindowsJob(proc)
        if owner_run:
            register_process(Path(owner_run), owned, request['owner'], log_dir)
        for stream, name in ((proc.stdout, 'stdout.log'), (proc.stderr, 'stderr.log')):
            t = threading.Thread(target=copy_stream, args=(stream, log_dir / name), daemon=True); t.start(); threads.append(t)
        (log_dir / 'release').write_text('owned\n', encoding='ascii')
        while proc.poll() is None:
            elapsed = time.monotonic() - started
            signature = progress_signature()
            if signature != last_signature:
                last_signature = signature
                last_output[0] = time.monotonic()
            if (log_dir / 'workload-exit.json').exists():
                receipt['status'] = 'exited'; break
            if Path(cancel_path).exists():
                receipt['status'] = 'cancelled'; break
            if timeout is not None and elapsed > timeout:
                receipt['status'] = 'timed_out'; break
            if idle_timeout and time.monotonic() - last_output[0] > idle_timeout:
                receipt['status'] = 'stalled'; break
            time.sleep(.05)
        if receipt['status'] == 'running':
            receipt['status'] = 'exited'
    finally:
        if job:
            job.close()
        elif owned:
            stop_owned(owned)
        elif proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait()
        for t in threads:
            t.join(timeout=10)
        for stream in (proc.stdout, proc.stderr):
            if stream and not stream.closed:
                stream.close()
        exit_code = read_json(log_dir / 'workload-exit.json')['exit_code'] if receipt['status'] == 'exited' and (log_dir / 'workload-exit.json').exists() else proc.returncode
        receipt.update(exit_code=exit_code, finished_at=now(), duration_seconds=round(time.monotonic() - started, 3))
        write_json(log_dir / 'receipt.json', receipt)
    return receipt


def resource_budget(lanes):
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count() or 1
    available = None
    try:
        if os.name == 'nt':
            class Memory(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(x, ctypes.c_uint64) for x in ('total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended')]
            m = Memory(); m.length = ctypes.sizeof(m)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                available = m.available // 1048576
        else:
            text = Path('/proc/meminfo').read_text()
            available = int(next(x.split()[1] for x in text.splitlines() if x.startswith('MemAvailable:'))) // 1024
            limit = Path('/sys/fs/cgroup/memory.max')
            if limit.exists() and limit.read_text().strip().isdigit():
                available = min(available, (int(limit.read_text()) - int(Path('/sys/fs/cgroup/memory.current').read_text())) // 1048576)
    except (OSError, ValueError, StopIteration):
        available = None
    workers = max(x.get('internal_workers', 1) for x in lanes)
    ram = max(x.get('memory_mb', 1024) for x in lanes)
    slots = 1 if available is None else max(1, min(len(lanes), cpus // workers, max(0, available - 512) // ram))
    return {'logical_cpus': cpus, 'available_memory_mb': available, 'reserved_memory_mb': 512, 'lane_slots': slots, 'max_internal_workers': workers, 'lane_memory_mb': ram}
