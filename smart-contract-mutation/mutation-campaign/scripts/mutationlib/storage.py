import contextlib
import codecs
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import uuid
from datetime import datetime, timezone


class CampaignError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def file_hash(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def binary_file(path):
    path = Path(path)
    if path.suffix.lower() in ('.sqlite', '.boc', '.bin', '.wasm'):
        return True
    decoder = codecs.getincrementaldecoder('utf-8')()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            if b'\0' in chunk:
                return True
            try:
                decoder.decode(chunk)
            except UnicodeDecodeError:
                return True
    try:
        decoder.decode(b'', final=True)
    except UnicodeDecodeError:
        return True
    return False


def credential_path(path):
    path = Path(path)
    return path.name.lower() == 'auth.json' or path.name.lower().startswith('.env') or path.suffix.lower() in ('.key', '.pem', '.pfx', '.p12')


def test_path(path):
    path = PurePosixPath(path)
    name = path.name.lower()
    if set(path.parts) & {'test', 'tests', 'spec', 'specs'} or name.endswith('.t.sol'):
        return True
    suffix = path.suffix.lower()
    stem = name[:-len(suffix)] if suffix else name
    return stem in ('test', 'spec') or stem.startswith(('test_', 'test-', 'spec_', 'spec-')) or stem.endswith(('_test', '.test', '_spec', '.spec'))


def linked(path):
    try:
        s = Path(path).lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(s.st_mode) or bool(getattr(s, 'st_file_attributes', 0) & 0x400)


def child(root, relative):
    root = Path(root).absolute()
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative or '\x00' in relative:
        raise CampaignError('expected a portable project-relative path')
    parts = PurePosixPath(relative).parts
    if PurePosixPath(relative).is_absolute() or any(p in ('.', '..', '.git') for p in parts):
        raise CampaignError('path escapes project or addresses Git metadata')
    path = root
    if any(linked(p) for p in (root, *root.parents)):
        raise CampaignError('redirected root is forbidden')
    for part in parts:
        path = path / part
        if linked(path):
            raise CampaignError('symlink, junction or reparse path is unsupported: ' + relative)
    if not path.resolve().is_relative_to(root.resolve()):
        raise CampaignError('path escapes project')
    return path


def replace_bytes(root, relative, data):
    """Replace a checked owned file, without writing through destination hard links."""
    path = child(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    name = '.replace-' + uuid.uuid4().hex
    if os.name != 'nt':
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory = os.open(Path(root).absolute(), flags)
        try:
            for part in PurePosixPath(relative).parts[:-1]:
                next_directory = os.open(part, flags, dir_fd=directory)
                os.close(directory); directory = next_directory
            fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode, dir_fd=directory)
            try:
                with os.fdopen(fd, 'wb') as out:
                    out.write(data); out.flush(); os.fsync(out.fileno())
                child(root, relative)
                os.replace(name, path.name, src_dir_fd=directory, dst_dir_fd=directory)
            finally:
                try:
                    os.unlink(name, dir_fd=directory)
                except FileNotFoundError:
                    pass
        finally:
            os.close(directory)
    else:
        fd, temporary = tempfile.mkstemp(prefix=name, dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(data); out.flush(); os.fsync(out.fileno())
            child(root, relative)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def read_json(path):
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise CampaignError('duplicate JSON key: ' + k)
            d[k] = v
        return d
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs)


def write_json(path, value):
    path = Path(path)
    child(path.parent, path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(value, f, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextlib.contextmanager
def lock(path, wait=False):
    path = Path(path)
    child(path.parent, path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as f:
        # Native locks can extend past EOF; writing a seed before ownership races.
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except OSError as exc:
            raise CampaignError('another controller owns this campaign') from exc
        try:
            yield
        finally:
            f.seek(0)
            if os.name == 'nt':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def redact(text, env=None):
    text = str(text)
    for key, value in (env or os.environ).items():
        if len(value) >= 6 and re.search(r'(KEY|TOKEN|SECRET|PASSWORD|RPC_URL|AUTH)', key, re.I):
            text = text.replace(value, '<redacted>')
    return re.sub(r'https?://[^\s\"\'<>]+', '<rpc-or-source-url-redacted>', text)


def journal(run, kind, **fields):
    entry = {'at': now(), 'kind': kind, **fields}
    with (Path(run) / 'events.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n'); f.flush(); os.fsync(f.fileno())


def load_campaign(run):
    run = Path(run).absolute()
    if run.parent.name != '.mutation' or not re.fullmatch('[0-9a-f]{16}', run.name):
        raise CampaignError('campaign must be an initialized project/.mutation/ID directory')
    child(run.parent.parent, '.mutation/' + run.name)
    state = read_json(child(run, 'state.json'))
    scope = read_json(child(run, 'scope.json'))
    if digest(scope) != state['scope_sha256']:
        raise CampaignError('frozen scope changed; initialize an explicit scope revision')
    project = run.parent.parent
    if state.get('id') != run.name or Path(state['campaign']).absolute() != run or Path(state['project']).absolute() != project:
        raise CampaignError('campaign path binding mismatch')
    snapshot = child(run, 'snapshot.json')
    if state.get('snapshot_sha256') != file_hash(snapshot) or state['snapshot_commit'] != read_json(snapshot)['snapshot_commit']:
        raise CampaignError('snapshot binding changed or obsolete development state; initialize a new campaign')
    lane_ids = [lane['id'] for lane in scope['lanes']]
    if len(set(lane_ids)) != len(lane_ids) or set(state['lanes']) != set(lane_ids):
        raise CampaignError('campaign lane inventory mismatch')
    for ident, lane in state['lanes'].items():
        if not re.fullmatch('[a-z][a-z0-9-]{0,47}', ident):
            raise CampaignError('invalid stored lane identity')
        expected = child(project, '.worktree/mutation-' + run.name + '/' + ident)
        if Path(lane['worktree']).absolute() != expected:
            raise CampaignError('stored lane path is outside its owned worktree')
    return state, scope


def update_state(run, update):
    with lock(Path(run) / 'state.lock', wait=True):
        state, _ = load_campaign(run)
        update(state)
        write_json(Path(run) / 'state.json', state)
        return state
