import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import sys
import uuid

from .processes import project_env, run_command
from .results import normalize_acton, normalize_forge, normalize_mewt, result, validate_invariant
from .storage import CampaignError, child, digest, file_hash, read_json, replace_bytes, write_json


def expand(argv, ctx):
    values = {'{worktree}': str(ctx['worktree']), '{output}': str(ctx['output']), '{campaign}': str(ctx['run']), '{python}': sys.executable}
    if ctx.get('pin'):
        values.update({'{fork_block}': str(ctx['pin'].get('number', ctx['pin'].get('seqno'))), '{fork_hash}': str(ctx['pin'].get('hash', ctx['pin'].get('root_hash')))})
    output = []
    for arg in argv:
        for token, value in values.items():
            arg = arg.replace(token, value)
        output.append(arg)
    return output


_DEFAULT_TIMEOUT = object()


def execute(ctx, argv, label, timeout=_DEFAULT_TIMEOUT, progress_paths=()):
    lane = ctx['lane']
    directory = ctx['output'] / 'commands' / (label + '-' + uuid.uuid4().hex[:8])
    if timeout is _DEFAULT_TIMEOUT:
        timeout = lane.get('timeout', 300)
    receipt = run_command(expand(argv, ctx), ctx['worktree'], ctx['env'], directory, timeout, lane.get('idle_timeout', 300), ctx['run'] / 'cancel', owner_run=ctx['run'], progress_paths=progress_paths)
    receipt['logs'] = str(directory.relative_to(ctx['run']).as_posix())
    output = '\n'.join((directory / name).read_text(encoding='utf-8') for name in ('stdout.log', 'stderr.log'))
    receipt['output'] = output
    return receipt


def test_once(ctx, label):
    lane = ctx['lane']
    build = execute(ctx, lane['build'], label + '-build')
    if build['status'] != 'exited':
        return {'status': 'timed_out' if build['status'] in ('stalled', 'timed_out') else 'tool_error', 'build': build}
    if build['exit_code']:
        return {'status': 'invalid', 'build': build}
    argv = lane['test']
    if lane.get('fork', {}).get('test_mode') == 'forge':
        argv = argv + ['--rpc-url', ctx['env']['MUTATION_RPC_URL'], '--fork-block-number', str(ctx['pin']['number'])]
    test = execute(ctx, argv, label + '-test')
    if test['status'] != 'exited':
        status = 'timed_out' if test['status'] in ('stalled', 'timed_out') else 'tool_error'
    elif test['exit_code'] == 0 and re.search(lane['pass_regex'], test['output']):
        status = 'survived'
    elif test['exit_code'] != 0 and re.search(lane['failure_regex'], test['output']):
        status = 'killed'
    else:
        status = 'tool_error'
    artifacts = {}
    captures = {}
    for rel in lane.get('compiled_artifacts', []):
        path = child(ctx['worktree'], rel)
        if not path.is_file():
            raise CampaignError('expected compiled artifact absent: ' + rel)
        artifacts[rel] = file_hash(path)
        saved = child(ctx['run'], 'compiled/' + uuid.uuid4().hex[:12] + path.suffix)
        saved.parent.mkdir(parents=True, exist_ok=True)
        replace_bytes(ctx['run'], saved.relative_to(ctx['run']).as_posix(), path.read_bytes())
        captures[saved.relative_to(ctx['run']).as_posix()] = artifacts[rel]
    return {'status': status, 'build': build, 'test': test, 'compiled_artifacts': artifacts, 'compiled_captures': captures}


def apply_and_test(ctx, mutation, label):
    relative = mutation['path']
    if relative not in ctx['lane']['targets']:
        raise CampaignError('mutation is outside selected targets')
    target = child(ctx['worktree'], relative)
    original = target.read_bytes()
    if 'content_path' in mutation:
        content = child(ctx['output'], mutation['content_path']).read_bytes()
    else:
        before, after = mutation['before'].encode(), mutation['after'].encode()
        if original.count(before) != 1 or before == after:
            raise CampaignError('mutant replacement is ambiguous or unchanged')
        content = original.replace(before, after, 1)
    if content == original:
        raise CampaignError('unchanged mutant cannot calibrate a run')
    output = ctx['output'] / 'applied' / digest({'id': mutation.get('id', label), 'label': label})[:20]
    output.mkdir(parents=True, exist_ok=True)
    saved = output / Path(relative).name
    saved.write_bytes(content)
    try:
        replace_bytes(ctx['worktree'], relative, content)
        outcome = test_once(ctx, label)
    finally:
        replace_bytes(ctx['worktree'], relative, original)
    record = {'native_id': str(mutation.get('id', label)), 'path': relative, 'status': outcome['status'], 'original_sha256': hashlib.sha256(original).hexdigest(), 'mutated_sha256': hashlib.sha256(content).hexdigest(), 'mutated_source': saved.relative_to(ctx['run']).as_posix(), 'outcome': outcome}
    write_json(output / 'record.json', record)
    return record


def require_help(ctx, prefix, tail, flags):
    receipt = execute(ctx, prefix + tail, 'help', 30)
    if receipt['status'] != 'exited' or any(flag not in receipt['output'] for flag in flags):
        raise CampaignError('installed tool does not confirm required CLI capabilities: ' + ', '.join(flags))
    return receipt


def oracle_command(ctx):
    config = ctx['output'] / 'oracle.json'
    ctx['oracle_root'] = child(ctx['run'], 'oracles/' + ctx['lane']['id'] + '-' + uuid.uuid4().hex[:8])
    write_json(config, {'run': str(ctx['run']), 'worktree': str(ctx['worktree']), 'output': str(ctx['oracle_root']), 'lane': ctx['lane']})
    script = Path(__file__).resolve().parents[1] / 'test_oracle.py'
    return shlex.join([sys.executable.replace('\\', '/'), str(script).replace('\\', '/'), str(config).replace('\\', '/')])


def native_inventory(database):
    if not database.is_file():
        raise CampaignError('native campaign database missing')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        return {str(x[0]) for x in db.execute('SELECT id FROM mutants')}


def selected_path(ctx, value):
    path = Path(value)
    if path.is_absolute():
        try:
            value = path.relative_to(ctx['worktree']).as_posix()
        except ValueError as exc:
            raise CampaignError('native source path is outside the lane worktree') from exc
    else:
        value = value.replace('\\', '/')
    child(ctx['worktree'], value)
    if value not in ctx['lane']['targets']:
        raise CampaignError('native source path is outside frozen targets: ' + value)
    return value


def bind_oracles(ctx, raw, normalized):
    baseline = read_json(ctx['run'] / 'snapshot.json')['files']
    probes = [(p, read_json(p)) for p in ctx['oracle_root'].glob('*/record.json')]
    rows = {str(r['mutant']['id']): r for r in raw['results']}
    records = normalized['records']
    for record in records:
        row = rows[record['native_id']]; native = row['mutant']
        relative = selected_path(ctx, row['target']['path']); record['path'] = relative
        original = child(ctx['worktree'], relative).read_bytes()
        if hashlib.sha256(original).hexdigest() != baseline[relative]['sha256'] or row['target']['file_hash'] != baseline[relative]['sha256']:
            raise CampaignError('native target is not the frozen current-byte source')
        offset = native['byte_offset']; old, new = native['old_text'].encode(), native['new_text'].encode()
        if type(offset) is not int or offset < 0 or original[offset:offset + len(old)] != old or old == new:
            raise CampaignError('native patch offset/content does not match snapshot')
        expected = dict((p, baseline[p]['sha256']) for p in ctx['lane']['targets'])
        expected[relative] = hashlib.sha256(original[:offset] + new + original[offset + len(old):]).hexdigest()
        if record['status'] == 'skipped':
            continue
        matches = [(p, v) for p, v in probes if v.get('changed') and v.get('source_hashes') == expected]
        if not matches:
            raise CampaignError('native mutant has no matching applied-source oracle: ' + record['native_id'])
        completed = [(p, v) for p, v in matches if v['status'] != 'running']
        if record['status'] == 'timed_out' and not completed:
            p, witness = matches[0]
        else:
            statuses = {v['status'] for _, v in completed}
            if len(statuses) != 1 or 'tool_error' in statuses or not completed:
                raise CampaignError('native mutant has conflicting or incomplete test oracle outcomes')
            p, witness = completed[0]
            if record['status'] not in (witness['status'], 'tool_error') and not (record['native_status'] == 'TestFail' and witness['status'] == 'invalid'):
                raise CampaignError('native outcome disagrees with applied-source test oracle')
            record['status'] = witness['status']
        record.update(oracle_record=p.relative_to(ctx['run']).as_posix(), oracle_sha256=file_hash(p), original_sha256=baseline[relative]['sha256'], mutated_sha256=expected[relative])
    return result(records, normalized['raw_score'])


def run_engine(ctx, calibration=False):
    lane = ctx['lane']; tool = lane['tool']
    if tool == 'replay':
        mutants = lane.get('mutants', [])[:1] if calibration else lane.get('mutants', [])
        if not mutants:
            raise CampaignError('replay scope contains no mutants')
        return result([apply_and_test(ctx, m, 'native-' + str(i)) for i, m in enumerate(mutants)], {'formula': 'killed / (killed + survived)', 'value': None, 'generation': 'explicit source patches; not a native generator'})
    prefix = lane.get('executable') or [dict(forge='forge', slither='slither-mutate', mewt='mewt', muton='muton', acton='acton', universal='mutate')[tool]]
    if not isinstance(prefix, list) or not prefix:
        raise CampaignError('engine executable must be an argv prefix')
    targets = lane.get('calibration_targets', lane['targets']) if calibration else lane['targets']
    if any(x not in lane['targets'] for x in targets):
        raise CampaignError('native calibration target outside frozen scope')
    extra = lane.get('calibration_args', lane.get('extra_args', [])) if calibration else lane.get('extra_args', [])
    if tool == 'forge':
        require_help(ctx, prefix, ['test', '--help'], ['--mutate', '--mutation-jobs', '--mutation-timeout', '--json'])
        test_argv = expand(lane['test'], ctx)
        test_prefix = expand(prefix + ['test'], ctx)
        if test_argv[:len(test_prefix)] != test_prefix:
            raise CampaignError('Foundry native mutation must use the same executable and test command as the baseline')
        shared_args = test_argv[len(test_prefix):]
        if ctx.get('pin') and any(arg in ('--rpc-url', '--fork-url', '--fork-block-number') for arg in shared_args):
            raise CampaignError('remove explicit fork flags from the Foundry test argv; the frozen campaign pin is applied by the controller')
        extra_args = merge_forge_test_args(extra, shared_args)
        cmd = prefix + ['test', '--mutate', *targets, '--mutation-jobs', str(lane.get('internal_workers', 1)), '--mutation-timeout', str(lane.get('mutant_timeout', 60)), '--json', *[arg for arg in extra_args if arg != '--json']]
        if ctx.get('pin'):
            cmd += ['--rpc-url', ctx['env']['MUTATION_RPC_URL'], '--fork-block-number', str(ctx['pin']['number'])]
    elif tool in ('mewt', 'muton'):
        require_help(ctx, prefix, ['run', '--help'], ['--test.cmd', '--test.timeout', '--db'])
        database = ctx['output'] / 'native.sqlite'
        cmd = prefix + ['run', *targets, '--test.cmd', oracle_command(ctx), '--test.timeout', str(lane.get('mutant_timeout', 60)), '--db', str(database), '--comprehensive', *extra]
    elif tool == 'acton':
        require_help(ctx, prefix, ['test', '--help'], ['--mutate', '--mutate-contract', '--mutation-workers', '--mutation-timeout', '--no-studio-reporting'])
        if not lane.get('contract'):
            raise CampaignError('Acton route needs configured contract name')
        cmd = prefix + ['test', '--mutate', '--mutate-contract', lane['contract'], '--mutation-workers', str(lane.get('internal_workers', 1)), '--mutation-timeout', str(lane.get('mutant_timeout', 60)), '--no-studio-reporting', *extra]
    elif tool == 'slither':
        require_help(ctx, prefix, ['--help'], ['--test-cmd', '--output-dir', '--timeout'])
        if len(targets) != 1:
            raise CampaignError('Slither route currently requires one explicit target')
        cmd = prefix + [targets[0], '--test-cmd', oracle_command(ctx), '--output-dir', str(ctx['output'] / 'native'), '--timeout', str(lane.get('mutant_timeout', 60)), '--comprehensive', '-vv', *extra]
    elif tool == 'universal':
        require_help(ctx, prefix, ['--help'], ['--noCheck', '--mutantDir'])
        if len(targets) != 1 or not lane.get('language_evidence'):
            raise CampaignError('Universal route requires one source and verified installed language/rule evidence')
        directory = ctx['output'] / 'generated'
        directory.mkdir()
        language = {'solidity': 'solidity', 'func': 'func', 'tact': 'tact', 'tolk': 'tolk'}[lane['language']]
        generation = execute(ctx, prefix + [targets[0], language, '--noCheck', '--mutantDir', str(directory), *extra], 'generate', timeout=lane.get('timeout', 300) if calibration else None, progress_paths=[directory])
        if generation['status'] != 'exited' or generation['exit_code']:
            raise CampaignError('Universal generation failed; language capability remains unverified')
        files = sorted(directory.glob(Path(targets[0]).stem + '.mutant.*' + Path(targets[0]).suffix))
        if not files:
            raise CampaignError('Universal generator produced no recognized mutants')
        # Compile each generated candidate ourselves; invalid builds never count as kills.
        records = [apply_and_test(ctx, {'id': f.name, 'path': targets[0], 'content_path': f.relative_to(ctx['output']).as_posix()}, 'um-' + str(i)) for i, f in enumerate(files)]
        normalized = result(records, {'formula': 'native analyze_mutants is not used; each generated file is compiled/tested by this controller', 'value': None})
        normalized['generation_receipt'] = {k: v for k, v in generation.items() if k != 'output'}
        return normalized
    else:
        raise CampaignError('unknown engine')
    originals = {p: child(ctx['worktree'], p).read_bytes() for p in lane['targets']}
    acton_before = set(ctx['worktree'].glob('build/mutation-sessions/*.jsonl'))
    try:
        timeout = lane.get('timeout', 300) if calibration else None
        progress_paths = [ctx['env']['TMP']] if tool == 'forge' else []
        if not calibration:
            if tool in ('mewt', 'muton'):
                progress_paths = [database]
            elif tool == 'acton':
                progress_paths = [ctx['worktree'] / 'build/mutation-sessions']
            elif tool == 'slither':
                progress_paths = [ctx['output'] / 'native']
        receipt = execute(ctx, cmd, 'engine', timeout=timeout, progress_paths=progress_paths)
    finally:
        for path, content in originals.items():
            replace_bytes(ctx['worktree'], path, content)
    if receipt['status'] != 'exited' or receipt['exit_code']:
        detail = (receipt.get('output') or '')[:4000]
        raise CampaignError('native engine did not complete: ' + receipt['status'] + ' exit ' + str(receipt['exit_code']) + ('\n' + detail if detail else ''))
    if tool == 'forge':
        stdout = ctx['run'] / receipt['logs'] / 'stdout.log'
        normalized = normalize_forge(read_json(stdout))
    elif tool in ('mewt', 'muton'):
        collected = execute(ctx, prefix + ['results', '--all', '--format', 'json', '--db', str(database)], 'collect')
        if collected['status'] != 'exited' or collected['exit_code']:
            raise CampaignError('native results collection failed')
        raw = read_json(ctx['run'] / collected['logs'] / 'stdout.log')
        normalized = normalize_mewt(raw, native_inventory(database), lane['failure_regex'], lane['pass_regex'])
        normalized = bind_oracles(ctx, raw, normalized)
        normalized['collection_receipt'] = {k: v for k, v in collected.items() if k != 'output'}
        normalized['native_artifacts'] = {database.relative_to(ctx['run']).as_posix(): file_hash(database)}
    elif tool == 'acton':
        paths = set(ctx['worktree'].glob('build/mutation-sessions/*.jsonl')) - acton_before
        if len(paths) != 1:
            raise CampaignError('cannot identify exactly one new Acton session artifact')
        raw = next(iter(paths)).read_text(encoding='utf-8')
        (ctx['output'] / 'acton.jsonl').write_text(raw, encoding='utf-8')
        normalized = normalize_acton([json.loads(x) for x in raw.splitlines() if x.strip()])
        normalized['native_artifacts'] = {(ctx['output'] / 'acton.jsonl').relative_to(ctx['run']).as_posix(): file_hash(ctx['output'] / 'acton.jsonl')}
    else:
        normalized = normalize_slither(ctx, receipt['output'])
    for record in normalized['records']:
        record['path'] = selected_path(ctx, record['path'])
    normalized['engine_receipt'] = {k: v for k, v in receipt.items() if k != 'output'}
    return normalized


def merge_forge_test_args(extra, shared):
    """Keep test selection/configuration identical without duplicating exact options."""
    def groups(args):
        result = []
        index = 0
        while index < len(args):
            group = [args[index]]
            if args[index].startswith('-') and index + 1 < len(args) and not args[index + 1].startswith('-'):
                group.append(args[index + 1]); index += 1
            result.append(group); index += 1
        return result
    common = groups(shared)
    if any(group not in common for group in groups(extra)):
        raise CampaignError('Foundry extra_args must exactly match baseline test argv; move test/configuration flags there')
    return [arg for group in common if group[0] != '--json' for arg in group]


def normalize_slither(ctx, output):
    pattern = re.compile(r'(Revert|Comment|Tweak) mutants: (\d+) uncaught of (\d+)')
    groups = pattern.findall(output)
    empty = re.findall(r'Zero (Revert|Comment|Tweak) mutants analyzed', output)
    if len(groups) + len(empty) != 3 or 'Finished mutation testing assessment' not in output:
        raise CampaignError('unknown/truncated Slither summary; no machine-readable inventory is available')
    total = sum(int(g[2]) for g in groups)
    survived = sum(int(g[1]) for g in groups)
    probes = []
    for path in sorted(ctx['oracle_root'].glob('*/record.json')):
        record = read_json(path)
        if record.get('changed'):
            relative = ctx['lane']['targets'][0]
            record.update(original_sha256=read_json(ctx['run'] / 'snapshot.json')['files'][relative]['sha256'], mutated_sha256=record['source_hashes'][relative])
            record.update(oracle_record=path.relative_to(ctx['run']).as_posix(), oracle_sha256=file_hash(path))
            probes.append(record)
    if len(probes) != total or sum(r['status'] == 'survived' for r in probes) != survived:
        raise CampaignError('Slither summary/probe reconciliation failed; inspect line endings or missing tool records')
    normalized = result(probes, {'formula': 'per category uncaught / compiling candidates; behavioral score is reported separately', 'value': [{'category': g[0], 'uncaught': int(g[1]), 'compiling': int(g[2])} for g in groups]})
    normalized['inventory_limit'] = 'Only evaluated compiling mutants have native count evidence. Slither can skip candidates; no exhaustive generated inventory is exposed.'
    normalized['counts']['invalid'] = output.count('COMPILATION FAILURE')
    return normalized


def context(run, lane, worktree, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    ctx = {'run': Path(run), 'lane': lane, 'worktree': Path(worktree), 'output': output}
    additions = {k: expand([v], ctx)[0] for k, v in lane.get('env', {}).items()}
    for key, source in lane.get('inherit_env', {}).items():
        if source not in os.environ:
            raise CampaignError('required inherited environment variable is missing: ' + source)
        additions[key] = os.environ[source]
    workers = str(lane.get('internal_workers', 1))
    additions.update(RAYON_NUM_THREADS=workers, OMP_NUM_THREADS=workers, TOKIO_WORKER_THREADS=workers)
    # A shallow per-lane home avoids Windows MAX_PATH inside nested native oracles.
    ctx['env'] = project_env(Path(run) / 'env' / lane['id'], additions)
    if os.name == 'nt' and lane['tool'] == 'muton':
        git = shutil.which('git')
        shell_dir = Path(git).resolve().parent.parent / 'bin' if git else None
        if shell_dir and (shell_dir / 'sh.exe').is_file():
            ctx['env']['PATH'] = str(shell_dir) + os.pathsep + ctx['env'].get('PATH', '')
    pin_file = Path(run) / 'lanes' / lane['id'] / 'fork.json'
    if lane.get('fork') and pin_file.exists():
        configure_fork(ctx, read_json(pin_file))
    return ctx


def configure_fork(ctx, pin):
    ctx['pin'] = pin
    endpoint = os.environ[pin['endpoint_env']]
    ctx['env'].update(MUTATION_RPC_URL=endpoint, MUTATION_FORK_BLOCK=str(pin.get('number', pin.get('seqno'))), MUTATION_FORK_HASH=str(pin.get('hash', pin.get('root_hash'))))
    if pin['kind'] == 'evm':
        ctx['env'].update(ETH_RPC_URL=endpoint, FOUNDRY_FORK_BLOCK_NUMBER=str(pin['number']))
    else:
        ctx['env']['MUTATION_TON_BLOCK'] = json.dumps({k: pin[k] for k in ('workchain', 'shard', 'seqno', 'root_hash', 'file_hash')})


def ensure_fork(ctx):
    from .rpc import pin_from_scope
    config = ctx['lane'].get('fork')
    if not config:
        return
    path = ctx['run'] / 'lanes' / ctx['lane']['id'] / 'fork.json'
    pin = pin_from_scope(config, read_json(path) if path.exists() else None)
    write_json(path, pin); configure_fork(ctx, pin)
