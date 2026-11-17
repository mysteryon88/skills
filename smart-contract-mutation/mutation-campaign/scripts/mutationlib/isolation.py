import hashlib
import os
from pathlib import Path
import re
import subprocess
import uuid

from .storage import CampaignError, child, digest, file_hash, now, read_json, replace_bytes, write_json


RESERVED = ('.mutation', '.worktree')
LANGUAGES = {'solidity', 'tact', 'tolk', 'func'}
TOOLS = {'forge', 'slither', 'mewt', 'muton', 'acton', 'universal', 'replay'}


def git(root, *args, data=None, env=None):
    e = os.environ.copy()
    e.update(GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    if env:
        e.update(env)
    p = subprocess.run(['git', '-C', str(root), *args], input=data, capture_output=True, env=e, timeout=120)
    if p.returncode:
        raise CampaignError('Git operation failed: ' + p.stderr.decode('utf-8', 'replace')[:500])
    return p.stdout


def validate_scope(project, scope):
    if scope.get('schema') != 1 or not scope.get('coordinator') or not isinstance(scope.get('lanes'), list) or not scope['lanes']:
        raise CampaignError('scope requires schema 1, coordinator identity and nonempty lanes')
    ids = set()
    for lane in scope['lanes']:
        ident = lane.get('id', '')
        if not re.fullmatch('[a-z][a-z0-9-]{0,47}', ident) or ident in ids:
            raise CampaignError('lane ID must be unique portable lowercase name')
        ids.add(ident)
        if lane.get('language') not in LANGUAGES or lane.get('tool') not in TOOLS:
            raise CampaignError('unsupported executable language or engine')
        if not lane.get('rationale') or not lane.get('targets'):
            raise CampaignError('targets and tool rationale must be frozen')
        fork = lane.get('fork')
        if fork and (fork.get('kind') not in ('evm', 'ton') or fork.get('test_mode') not in ('forge', 'env') or not fork.get('rpc_envs') or (fork['kind'] == 'ton' and fork['test_mode'] != 'env') or (fork['test_mode'] == 'env' and not fork.get('binding_evidence'))):
            raise CampaignError('fork needs protocol, RPC environment names and verified forge/env binding')
        if any(re.search(r'(KEY|TOKEN|SECRET|PASSWORD|RPC_URL|AUTH)', key, re.I) for key in lane.get('env', {})):
            raise CampaignError('secret environment values must use inherit_env references, not literal scope values')
        if any(not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', key) or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', value) for key, value in lane.get('inherit_env', {}).items()):
            raise CampaignError('inherit_env maps environment names to existing environment names')
        private_env = {'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TMP', 'TEMP', 'TMPDIR', 'NPM_CONFIG_CACHE', 'PIP_CACHE_DIR', 'SVM_HOME', 'FOUNDRY_CACHE_PATH', 'CARGO_HOME', 'PYTHONPYCACHEPREFIX', 'CODEX_HOME'}
        if any(key.upper() in private_env or key.upper().startswith('XDG_') for key in lane.get('env', {}).keys() | lane.get('inherit_env', {}).keys()):
            raise CampaignError('lane environment cannot override project-local home/cache/temp containment')
        reserved = {'--db', '--test.cmd', '--test-cmd', '--output-dir', '--mutantdir', '--mutation-jobs', '--mutation-workers', '--test.timeout', '--mutation-timeout', '--timeout', '--mutate', '--mutate-path', '--mutate-contract', '--fork-url', '--rpc-url', '--fork-block-number', '--root'}
        for arg in lane.get('extra_args', []) + lane.get('calibration_args', []):
            if not isinstance(arg, str) or arg.split('=', 1)[0].lower() in reserved:
                raise CampaignError('extra arguments cannot override frozen scope, oracle, output, resource or fork bindings')
        for relative in lane['targets']:
            if relative.split('/')[0] in RESERVED or not child(project, relative).is_file():
                raise CampaignError('target must be a current regular source file')
        for key in ('build', 'test'):
            argv = lane.get(key)
            if not isinstance(argv, list) or not argv or any(not isinstance(v, str) or not v for v in argv):
                raise CampaignError(key + ' must be a nonempty argv array')
        for key in ('pass_regex', 'failure_regex'):
            if not lane.get(key):
                raise CampaignError(key + ' must establish executed tests/assertion failures')
            re.compile(lane[key])
        for key, default in [('internal_workers', 1), ('memory_mb', 1024), ('timeout', 300), ('idle_timeout', 300)]:
            value = lane.get(key, default)
            if type(value) not in (int, float) or not 0 < value < 1e9:
                raise CampaignError(key + ' must be a positive finite number')
        for key in ('internal_workers', 'memory_mb'):
            if type(lane.get(key, 1)) is not int:
                raise CampaignError(key + ' must be an integer')
        calibration = lane.get('calibration', {})
        if not all(calibration.get(k) for k in ('path', 'before', 'after', 'specification')):
            raise CampaignError('calibration needs applied-source canary and expected-behavior evidence')
        if calibration['path'] not in lane['targets'] or calibration['before'] == calibration['after']:
            raise CampaignError('calibration must change a selected source file')
    for lane in scope['lanes']:
        if any(x not in ids or x == lane['id'] for x in lane.get('needs', [])):
            raise CampaignError('invalid lane dependencies')
    pending = {x['id']: set(x.get('needs', [])) for x in scope['lanes']}
    done = set()
    while pending:
        ready = [k for k, v in pending.items() if v <= done]
        if not ready:
            raise CampaignError('cyclic lane dependencies')
        for k in ready:
            done.add(k); del pending[k]
    lineage_fields = ('parent_campaign', 'parent_reason', 'parent_lineage')
    if any(key in scope for key in lineage_fields):
        reference = scope.get('parent_lineage', '')
        match = re.fullmatch(r'worktree/([a-z][a-z0-9-]{0,47})/parent-lineage\.json', reference)
        if not all(scope.get(key) for key in lineage_fields) or not re.fullmatch('[0-9a-f]{16}', scope['parent_campaign']) or len(scope['parent_reason'].strip()) < 16 or not match or match.group(1) not in ids:
            raise CampaignError('successor scope needs a valid parent campaign, concrete reason and lane-bound lineage receipt')


def inventory(project, includes):
    raw = git(project, 'ls-files', '--stage', '-z')
    modes = {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        meta, name = record.split(b'\t', 1)
        mode, _, stage = meta.split()
        path = name.decode('utf-8')
        if mode in (b'160000', b'120000') or stage != b'0':
            raise CampaignError('submodule, link or unmerged index requires explicit materialization: ' + path)
        if path.split('/')[0] in RESERVED:
            raise CampaignError('reserved campaign directory is tracked')
        modes[path] = mode.decode()
    paths = set(modes)
    paths.update(x.decode('utf-8') for x in git(project, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if x)
    paths.update(includes)
    result = {}
    for name in sorted(paths):
        if name.split('/')[0] in RESERVED:
            continue
        p = child(project, name)
        if not p.exists():
            if name in includes:
                raise CampaignError('required ignored input is absent: ' + name)
            continue
        if not p.is_file():
            raise CampaignError('snapshot input is not a regular file: ' + name)
        mode = ('100755' if p.stat().st_mode & 0o111 else '100644') if os.name != 'nt' else modes.get(name, '100644')
        result[name] = {'sha256': file_hash(p), 'size': p.stat().st_size, 'mode': mode}
    return result


def snapshot(project, run, includes):
    project, run = Path(project), Path(run)
    status = git(project, 'status', '--porcelain=v1', '-z', '-uall')
    index = git(project, 'ls-files', '--stage', '-z')
    head = git(project, 'rev-parse', 'HEAD').decode().strip()
    files = inventory(project, includes)
    repo = child(run, 'repository.git')
    git(run, 'init', '--bare', '--quiet', str(repo))
    env = {'GIT_DIR': str(repo), 'GIT_INDEX_FILE': str(run / 'snapshot-index'), 'GIT_AUTHOR_NAME': 'Mutation snapshot', 'GIT_AUTHOR_EMAIL': 'snapshot@localhost.invalid', 'GIT_COMMITTER_NAME': 'Mutation snapshot', 'GIT_COMMITTER_EMAIL': 'snapshot@localhost.invalid', 'GIT_AUTHOR_DATE': '2000-01-01T00:00:00Z', 'GIT_COMMITTER_DATE': '2000-01-01T00:00:00Z'}
    git(run, 'read-tree', '--empty', env=env)
    entries = []
    for name, info in files.items():
        content = child(project, name).read_bytes()
        if hashlib.sha256(content).hexdigest() != info['sha256']:
            raise CampaignError('source changed during snapshot: ' + name)
        blob = git(run, 'hash-object', '-w', '--no-filters', '--stdin', data=content, env=env).strip()
        entries.append(info['mode'].encode() + b' ' + blob + b'\t' + name.encode() + b'\0')
    git(run, 'update-index', '-z', '--index-info', data=b''.join(entries), env=env)
    tree = git(run, 'write-tree', env=env).decode().strip()
    commit = git(run, 'commit-tree', tree, '-m', 'Current source snapshot', env=env).decode().strip()
    if files != inventory(project, includes) or status != git(project, 'status', '--porcelain=v1', '-z', '-uall') or index != git(project, 'ls-files', '--stage', '-z') or head != git(project, 'rev-parse', 'HEAD').decode().strip():
        raise CampaignError('source/index changed during snapshot; retry after edits settle')
    provenance = {'source_head': head, 'status_sha256': hashlib.sha256(status).hexdigest(), 'index_sha256': hashlib.sha256(index).hexdigest(), 'files': files, 'snapshot_tree': tree, 'snapshot_commit': commit, 'includes': includes, 'ignored_policy': 'Git ignored files omitted unless explicitly included', 'created_at': now()}
    write_json(run / 'snapshot.json', provenance)
    return provenance


def verify_materialized(worktree, provenance):
    for relative, info in provenance['files'].items():
        path = child(worktree, relative)
        if not path.is_file() or file_hash(path) != info['sha256'] or (os.name != 'nt' and bool(path.stat().st_mode & 0o111) != (info['mode'] == '100755')):
            raise CampaignError('worktree differs from current-byte snapshot: ' + relative)


def lane_worktree(run, lane_id):
    run = Path(run)
    state = read_json(run / 'state.json')
    worktree = child(Path(state['project']) / '.worktree', 'mutation-' + state['id'] + '/' + lane_id)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    git(run, '--git-dir', str(run / 'repository.git'), '-c', 'core.hooksPath=' + str(run / 'empty-hooks'), 'worktree', 'add', '--no-checkout', '--detach', str(worktree), state['snapshot_commit'])
    git(worktree, 'read-tree', state['snapshot_commit'])
    provenance = read_json(run / 'snapshot.json')
    for relative, info in provenance['files'].items():
        content = git(run, '--git-dir', str(run / 'repository.git'), 'show', state['snapshot_commit'] + ':' + relative)
        replace_bytes(worktree, relative, content)
        if os.name != 'nt':
            os.chmod(child(worktree, relative), 0o755 if info['mode'] == '100755' else 0o644)
    verify_materialized(worktree, provenance)
    return worktree


def init_campaign(project, scope):
    project = Path(project).resolve()
    validate_scope(project, scope)
    inventory(project, scope.get('include_ignored', []))
    for name in RESERVED:
        path = child(project, name)
        if path.exists() and not (path / '.gitignore').is_file():
            raise CampaignError('reserved directory already exists without campaign ignore sentinel: ' + name)
        path.mkdir(exist_ok=True)
        sentinel = child(path, '.gitignore')
        if sentinel.exists() and sentinel.read_text(encoding='utf-8') != '*\n':
            raise CampaignError('reserved directory has a foreign ignore sentinel')
        sentinel.write_text('*\n', encoding='utf-8', newline='\n')
    ident = uuid.uuid4().hex[:16]
    run = child(project / '.mutation', ident)
    run.mkdir()
    write_json(run / 'scope.json', scope)
    provenance = snapshot(project, run, scope.get('include_ignored', []))
    state = {'schema': 1, 'id': ident, 'campaign': str(run), 'project': str(project), 'scope_sha256': digest(scope), 'snapshot_commit': provenance['snapshot_commit'], 'snapshot_sha256': file_hash(run / 'snapshot.json'), 'status': 'ready', 'created_at': now(), 'lanes': {}, 'outbox': None}
    write_json(run / 'state.json', state)
    for lane in scope['lanes']:
        worktree = lane_worktree(run, lane['id'])
        state['lanes'][lane['id']] = {'worktree': str(worktree), 'status': 'pending', 'attempts': 0}
    write_json(run / 'state.json', state)
    return run
