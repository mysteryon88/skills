import os
from pathlib import Path

from .isolation import git, init_campaign
from .storage import CampaignError, child, credential_path, digest, file_hash, load_campaign, now, read_json, replace_bytes, test_path, write_json


CONTRACT_SUFFIXES = {'.sol', '.tact', '.tolk', '.fc', '.func'}


def _log_references(value):
    if isinstance(value, dict):
        if isinstance(value.get('logs'), str):
            yield value['logs']
        for key, item in value.items():
            if key != 'logs':
                yield from _log_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _log_references(item)


def create_successor(parent, lane_id, destination, scope, repair_paths, specifications, reason):
    """Freeze an explicit test/config repair as a new campaign with linked failure evidence."""
    parent = Path(parent).absolute(); state, parent_scope = load_campaign(parent)
    if lane_id not in state['lanes'] or state['lanes'][lane_id]['status'] != 'blocked':
        raise CampaignError('baseline-repair successor requires a blocked parent lane')
    lane = next(item for item in parent_scope['lanes'] if item['id'] == lane_id)
    progress_path = child(parent, 'lanes/' + lane_id + '/progress.json')
    if not progress_path.is_file():
        raise CampaignError('blocked parent lane has no failure progress receipt')
    progress = read_json(progress_path)
    if progress.get('status') != 'blocked' or not progress.get('reason'):
        raise CampaignError('parent failure receipt is incomplete')
    baseline_path = child(parent, 'lanes/' + lane_id + '/baseline.json')
    baseline = read_json(baseline_path) if baseline_path.is_file() else None
    if not isinstance(reason, str) or len(reason.strip()) < 16:
        raise CampaignError('successor needs a concrete repair reason')
    repair_paths = list(dict.fromkeys(repair_paths)); specifications = list(dict.fromkeys(specifications))
    if not repair_paths or not specifications:
        raise CampaignError('successor needs named repair files and frozen specification references')
    manifest = read_json(parent / 'snapshot.json'); original_files = manifest['files']
    worktree = Path(state['lanes'][lane_id]['worktree'])
    repairs = []
    for relative in repair_paths:
        source = child(worktree, relative)
        if credential_path(relative):
            raise CampaignError('credential files cannot be used as repair inputs')
        if relative in lane['targets']:
            raise CampaignError('repair cannot change a selected contract target')
        if Path(relative).suffix.lower() in CONTRACT_SUFFIXES and not test_path(relative):
            raise CampaignError('repair cannot change production contract source')
        if not source.is_file():
            raise CampaignError('repair input must be a regular worktree file: ' + relative)
        before = original_files.get(relative, {}).get('sha256')
        after = file_hash(source)
        if before == after:
            raise CampaignError('declared repair has no source change: ' + relative)
        repairs.append({'path': relative, 'before_sha256': before, 'after_sha256': after})
    if set(repair_paths) & set(specifications):
        raise CampaignError('a frozen specification cannot also be edited as a repair')
    specification_records = []
    for relative in specifications:
        if credential_path(relative):
            raise CampaignError('credential files cannot be used as specifications')
        if relative not in original_files:
            raise CampaignError('specification reference is not part of the parent snapshot: ' + relative)
        specification_records.append({'path': relative, 'sha256': original_files[relative]['sha256']})

    project = Path(state['project']).absolute()
    destination = Path(destination).absolute()
    try:
        relative_destination = destination.relative_to(parent).as_posix()
    except ValueError as exc:
        raise CampaignError('successor project must stay inside the owned parent campaign') from exc
    if not relative_destination.startswith('successors/') or destination.exists():
        raise CampaignError('successor destination must be a new path under the parent campaign successors/')
    child(parent, relative_destination)
    if not isinstance(scope, dict) or scope.get('schema') != 1:
        raise CampaignError('successor scope must be a schema 1 object')
    scope = dict(scope)
    scope.update(parent_campaign=state['id'], parent_reason=reason.strip(), parent_lineage=f'worktree/{lane_id}/parent-lineage.json')
    destination.mkdir(parents=True)

    for relative in sorted(original_files):
        content = git(parent, '--git-dir', str(parent / 'repository.git'), 'show', manifest['snapshot_commit'] + ':' + relative)
        replace_bytes(destination, relative, content)
        if os.name != 'nt':
            os.chmod(child(destination, relative), 0o755 if original_files[relative]['mode'] == '100755' else 0o644)
    for relative in repair_paths:
        replace_bytes(destination, relative, child(worktree, relative).read_bytes())
        if os.name != 'nt':
            os.chmod(child(destination, relative), 0o755 if child(worktree, relative).stat().st_mode & 0o111 else 0o644)

    evidence = {}
    def copy_evidence(source, reference):
        data = source.read_bytes(); replace_bytes(destination, reference, data)
        bundle_reference = f'worktree/{lane_id}/' + reference
        evidence[bundle_reference] = file_hash(destination / reference)
        return evidence[bundle_reference], bundle_reference

    parent_evidence_sha, parent_evidence_ref = copy_evidence(progress_path, 'parent-evidence/progress.json')
    failure_artifact = None
    failure_path = progress.get('failure_evidence', {}).get('path') if isinstance(progress.get('failure_evidence'), dict) else None
    if failure_path:
        expected_attempt = progress.get('attempt_path', '') + '/baseline.json'
        if failure_path != expected_attempt or not failure_path.startswith('lanes/' + lane_id + '/attempt-'):
            raise CampaignError('parent failure artifact is outside its recorded lane attempt')
        source = child(parent, failure_path)
        if source.is_file():
            sha, reference = copy_evidence(source, 'parent-evidence/current-failure.json')
            failure_artifact = {'path': reference, 'sha256': sha}
    if baseline is not None and not progress.get('attempt_path'):
        copy_evidence(baseline_path, 'parent-evidence/lane-baseline-summary.json')
    copied_logs = []
    log_refs = list(dict.fromkeys(_log_references(progress)))
    if not log_refs and not progress.get('attempt_path'):
        log_refs = list(dict.fromkeys(_log_references(baseline or progress)))
    for index, relative in enumerate(log_refs):
        if credential_path(relative):
            raise CampaignError('credential paths cannot be copied into successor evidence')
        log_dir = child(parent, relative)
        if not log_dir.is_dir():
            continue
        copied = {'parent_path': relative, 'files': {}}
        for name in ('request.json', 'receipt.json', 'stdout.log', 'stderr.log', 'workload-exit.json'):
            source = child(parent, relative + '/' + name)
            if source.is_file():
                if credential_path(source):
                    raise CampaignError('credential files cannot be copied into successor evidence')
                target = f'parent-evidence/commands/{index}/{name}'
                sha, bundle_reference = copy_evidence(source, target)
                copied['files'][name] = {'path': bundle_reference, 'sha256': sha}
        if copied['files']:
            copied_logs.append(copied)

    for index, record in enumerate(repairs):
        original = original_files.get(record['path'])
        if original:
            content = git(parent, '--git-dir', str(parent / 'repository.git'), 'show', manifest['snapshot_commit'] + ':' + record['path'])
            record['before_path'] = f'worktree/{lane_id}/parent-evidence/repairs/{index}/before'
            replace_bytes(destination, f'parent-evidence/repairs/{index}/before', content)
            record['before_capture_sha256'] = file_hash(destination / f'parent-evidence/repairs/{index}/before')
            evidence[record['before_path']] = record['before_capture_sha256']
        record['after_path'] = f'worktree/{lane_id}/parent-evidence/repairs/{index}/after'
        replace_bytes(destination, f'parent-evidence/repairs/{index}/after', child(worktree, record['path']).read_bytes())
        record['after_capture_sha256'] = file_hash(destination / f'parent-evidence/repairs/{index}/after')
        evidence[record['after_path']] = record['after_capture_sha256']
    for index, record in enumerate(specification_records):
        relative = record['path']
        content = git(parent, '--git-dir', str(parent / 'repository.git'), 'show', manifest['snapshot_commit'] + ':' + relative)
        local_path = f'parent-evidence/specifications/{index}/' + Path(relative).name
        record['evidence_path'] = f'worktree/{lane_id}/' + local_path
        replace_bytes(destination, local_path, content)
        evidence[record['evidence_path']] = file_hash(destination / local_path)

    lineage = {
        'schema': 1, 'created_at': now(), 'parent_campaign': state['id'],
        'parent_campaign_path': os.path.relpath(parent, destination).replace(os.sep, '/'),
        'parent_scope_sha256': state['scope_sha256'], 'parent_snapshot_sha256': state['snapshot_sha256'],
        'parent_lane': lane_id, 'parent_failure': {'path': parent_evidence_ref, 'sha256': parent_evidence_sha}, 'failure_artifact': failure_artifact,
        'blocked_reason': progress['reason'], 'repair_reason': reason.strip(), 'repairs': repairs,
        'specifications': specification_records, 'commands': copied_logs, 'evidence': evidence,
        'successor_scope_sha256': digest(scope),
    }
    write_json(destination / 'parent-lineage.json', lineage)
    write_json(destination / 'scope.json', scope)
    git(destination, 'init', '--quiet')
    required_paths = list(original_files) + repair_paths + ['scope.json', 'parent-lineage.json']
    required_paths.extend(path.removeprefix(f'worktree/{lane_id}/') for path in evidence)
    if required_paths:
        git(destination, 'add', '-f', '--pathspec-from-file=-', '--pathspec-file-nul', data=b''.join(path.encode('utf-8') + b'\0' for path in dict.fromkeys(required_paths)), env={'GIT_LITERAL_PATHSPECS': '1'})
    git(destination, 'add', '-A')
    executable_paths = set(path for path, info in original_files.items() if info['mode'] == '100755')
    executable_paths.update(record['path'] for record in repairs if original_files.get(record['path'], {}).get('mode') == '100755')
    for relative in sorted(executable_paths):
        git(destination, 'update-index', '--chmod=+x', '--', relative, env={'GIT_LITERAL_PATHSPECS': '1'})
    git(destination, '-c', 'user.name=Mutation successor', '-c', 'user.email=mutation-successor@localhost.invalid', 'commit', '--quiet', '-m', 'Baseline repair successor inputs')
    run = init_campaign(destination, scope)
    return {'campaign': str(run), 'project': str(destination), 'parent_campaign': state['id'], 'lineage': str(destination / 'parent-lineage.json')}
