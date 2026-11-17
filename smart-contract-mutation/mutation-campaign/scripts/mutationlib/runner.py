from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import json
from pathlib import Path
import subprocess
import sqlite3
import sys
import uuid

from .engines import apply_and_test, context, ensure_fork, execute, run_engine, test_once
from .isolation import git
from .processes import identity, resource_budget, stop_owned
from .results import capture_invariant, report, require_nonempty_campaign, validate_invariant
from .storage import CampaignError, child, digest, file_hash, journal, load_campaign, lock, now, read_json, redact, replace_bytes, update_state, write_json


def lane_run(run, lane, saved, scope_hash):
    ident = lane['id']; base = child(run, 'lanes/' + ident)
    progress = read_json(base / 'progress.json') if (base / 'progress.json').exists() else saved
    attempt = max(saved['attempts'], progress.get('attempts', 0)) + 1
    output = base / ('attempt-' + str(attempt) + '-' + uuid.uuid4().hex[:8])
    ctx = context(run, lane, Path(saved['worktree']), output)
    attempt_ref = output.relative_to(run).as_posix()
    current = dict(saved, status='running', attempts=attempt, attempt_path=attempt_ref, failure_evidence=None)
    write_json(base / 'progress.json', current)
    original_manifest = read_json(run / 'snapshot.json')
    originals = {}
    try:
        for p in lane['targets']:
            target = child(ctx['worktree'], p)
            if file_hash(target) != original_manifest['files'][p]['sha256']:
                if not saved.get('recovering') or progress.get('status') != 'running':
                    raise CampaignError('target changed outside controller; preserve proposed production changes separately')
                content = git(run, '--git-dir', str(run / 'repository.git'), 'show', original_manifest['snapshot_commit'] + ':' + p)
                replace_bytes(ctx['worktree'], p, content)
                journal(run, 'restore-interrupted-target', lane=ident, path=p)
            originals[p] = target.read_bytes()
        for i, argv in enumerate(lane.get('setup', [])):
            r = execute(ctx, argv, 'setup-' + str(i))
            if r['status'] != 'exited' or r['exit_code']:
                current['failure_evidence'] = {'kind': 'setup', 'commands': [{'logs': r['logs'], 'status': r['status'], 'exit_code': r['exit_code']}]}
                raise CampaignError('project-local setup failed; initial evidence retained')
        ensure_fork(ctx)
        baseline = test_once(ctx, 'baseline')
        write_json(output / 'baseline.json', baseline)
        write_json(base / 'baseline.json', baseline)
        if baseline['status'] != 'survived':
            current['failure_evidence'] = {'kind': 'baseline', 'path': attempt_ref + '/baseline.json', 'status': baseline['status'], 'commands': _command_evidence(baseline)}
            raise CampaignError('baseline failed or did not prove nonempty test execution; inspect build/test receipts')
        if lane.get('invariant'):
            telemetry = child(ctx['worktree'], lane['invariant']['receipt'])
            data = read_json(telemetry)
            baseline['invariant'] = capture_invariant(run, lane, ctx['worktree'], output)
            write_json(base / 'baseline.json', baseline)
            validate_invariant(data, ctx['worktree'], scope_hash)
        else:
            write_json(base / 'baseline.json', baseline)
        if (run / 'cancel').exists():
            raise CampaignError('cancelled')
        ensure_fork(ctx)
        canary = apply_and_test(ctx, lane['calibration'], 'canary')
        if canary['status'] != 'killed':
            raise CampaignError('applied-source canary was not assertion-killed; diagnose wiring/cache/reachability first')
        native_ctx = context(run, lane, ctx['worktree'], output / 'native-calibration')
        ensure_fork(native_ctx)
        native_calibration = run_engine(native_ctx, calibration=True)
        ensure_fork(native_ctx)
        if not sum(native_calibration['counts'].values()) or not native_calibration['counts']['killed'] or native_calibration['counts']['tool_error']:
            raise CampaignError('native calibration all-survive, empty or tool-error outcome; diagnose before full campaign')
        calibration = {'scope_sha256': scope_hash, 'canary': canary, 'native': native_calibration, 'at': now()}
        write_json(base / 'calibration.json', calibration)
        ensure_fork(ctx)
        full_ctx = context(run, lane, ctx['worktree'], output / 'full')
        data = run_engine(full_ctx)
        ensure_fork(full_ctx)
        require_nonempty_campaign(data)
        if data['counts']['tool_error']:
            raise CampaignError('native runner errors require diagnosis; they are not test kills')
        write_json(base / 'results.json', data)
        current.update(status='completed', reason='calibrated selected run completed', finished_at=now())
    except (CampaignError, OSError, ValueError, KeyError, sqlite3.Error) as exc:
        if current['failure_evidence'] is None:
            current['failure_evidence'] = {'kind': 'runner', 'commands': _command_evidence_from_directory(output), 'reason': redact(str(exc), ctx['env'])}
        current.update(status='cancelled' if (run / 'cancel').exists() else 'blocked', reason=redact(str(exc), ctx['env']), finished_at=now())
    finally:
        for relative, content in originals.items():
            replace_bytes(ctx['worktree'], relative, content)
        write_json(base / 'progress.json', current)
    return current


def _command_evidence(value):
    output = []
    if isinstance(value, dict):
        if isinstance(value.get('logs'), str):
            output.append({'logs': value['logs']})
        for key, item in value.items():
            if key != 'logs':
                output.extend(_command_evidence(item))
    elif isinstance(value, list):
        for item in value:
            output.extend(_command_evidence(item))
    return output


def _command_evidence_from_directory(output):
    commands = []
    run = output.parents[2]
    phases = (output, output / 'native-calibration', output / 'full')
    receipts = sorted(receipt for phase in phases for receipt in (phase / 'commands').glob('*/receipt.json'))
    for receipt in receipts:
        try:
            value = read_json(receipt)
            commands.append({'logs': receipt.parent.relative_to(run).as_posix(), 'status': value.get('status'), 'exit_code': value.get('exit_code')})
        except (OSError, ValueError, KeyError):
            continue
    return commands


def completion_event_id(state, run):
    outcomes = {}
    for ident, lane in state['lanes'].items():
        result = run / 'lanes' / ident / 'results.json'
        outcomes[ident] = {'status': lane['status'], 'attempts': lane.get('attempts', 0), 'attempt_path': lane.get('attempt_path'), 'failure_evidence': lane.get('failure_evidence'), 'result': file_hash(result) if result.exists() else None}
    return digest({'campaign': state['id'], 'outcomes': outcomes})[:32]


def cleanup_processes(run):
    run = Path(run); state, _ = load_campaign(run)
    stopped = []
    registry = child(run, 'process-registry.jsonl')
    if not registry.exists():
        return stopped
    for line in registry.read_text(encoding='utf-8').splitlines():
        entry = json.loads(line)
        if any(entry.get(k) != state[k] for k in ('scope_sha256', 'snapshot_sha256')) or entry.get('campaign') != state['id']:
            raise CampaignError('process registry campaign binding mismatch')
        directory = child(run, entry['logs'])
        if read_json(child(directory, 'request.json'))['owner'] != entry['owner'] or read_json(child(directory, 'process.json')) != entry['process']:
            raise CampaignError('owned launch receipt mismatch')
        if stop_owned(entry['process']):
            stopped.append(entry['process']['pid'])
    return stopped


def supervise(run, recover=False):
    run = Path(run).absolute()
    with lock(run / 'controller.lock'):
        state, scope = load_campaign(run)
        if state['status'] == 'verified-complete':
            return {'status': state['status'], 'campaign': str(run)}
        write_json(run / 'supervisor.json', identity(os.getpid()))
        if recover:
            stopped = cleanup_processes(run)
            if (run / 'cancel').exists():
                (run / 'cancel').unlink()
            journal(run, 'recovery', stopped_pids=stopped)
            for ident, lane in state['lanes'].items():
                if lane['status'] in ('running', 'blocked', 'cancelled', 'retry-exhausted'):
                    lane.update(status='pending', recovering=True)
        elif state['status'] in ('running', 'cancelled'):
            raise CampaignError('interrupted/cancelled campaign needs explicit resume')
        state['status'] = 'running'
        budget = resource_budget(scope['lanes'])
        write_json(run / 'resources.json', budget)
        state = update_state(run, lambda current: current.update(status='running', lanes=state['lanes']))
        journal(run, 'started', supervisor=identity(os.getpid()), resources=budget)
        pending = [lane for lane in scope['lanes'] if state['lanes'][lane['id']]['status'] != 'completed']
        while pending and not (run / 'cancel').exists():
            ready = [l for l in pending if all(state['lanes'][n]['status'] == 'completed' for n in l.get('needs', []))]
            if not ready:
                for lane in pending:
                    state['lanes'][lane['id']].update(status='blocked', reason='dependency did not complete')
                break
            wave = ready[:budget['lane_slots']]
            for lane in wave:
                state['lanes'][lane['id']]['status'] = 'running'
            state = update_state(run, lambda current: current.update(lanes=state['lanes']))
            with ThreadPoolExecutor(max_workers=budget['lane_slots']) as pool:
                futures = {pool.submit(lane_run, run, lane, state['lanes'][lane['id']], state['scope_sha256']): lane for lane in wave}
                for future in as_completed(futures):
                    lane = futures[future]; ident = lane['id']
                    try:
                        state['lanes'][ident] = future.result()
                    except Exception as exc:
                        state['lanes'][ident].update(status='blocked', reason=redact(str(exc)))
                    pending.remove(lane)
                    state = update_state(run, lambda current: current['lanes'].update({ident: state['lanes'][ident]}))
                    journal(run, 'lane-finished', lane=ident, status=state['lanes'][ident]['status'])
        state['status'] = 'cancelled' if (run / 'cancel').exists() else 'needs-analysis'
        event_id = completion_event_id(state, run)
        def completed(current):
            current['status'] = state['status']
            current['lanes'] = state['lanes']
            if current['outbox'] is None or current['outbox']['id'] != event_id:
                current['outbox'] = {'id': event_id, 'status': 'pending', 'attempts': 0}
        state = update_state(run, completed)
        report(run)
        journal(run, 'tools-finished', status=state['status'], event_id=state['outbox']['id'])
    # Delivery has its own lock; the continued coordinator can use the campaign CLI.
    if scope.get('runtime'):
        from .runtimes import deliver_event
        deliver_event(run, reset_attempts=recover)
    return {'status': state['status'], 'campaign': str(run), 'report': str(run / 'REPORT.md'), 'event_id': state['outbox']['id']}


def launch(run, recover=False):
    run = Path(run).absolute(); state, scope = load_campaign(run)
    if not scope.get('runtime') or not (run / 'runtime-binding.json').is_file():
        raise CampaignError('background campaigns require a bound continuation runtime; run bind-runtime first')
    with lock(run / 'launch.lock'):
        return _launch(run, recover)


def _launch(run, recover):
    for active in (run / 'supervisor.json', run / 'launched-supervisor.json'):
        if active.exists():
            record = read_json(active)
            if identity(record['pid']) == record:
                raise CampaignError('campaign supervisor is already running')
    ident = uuid.uuid4().hex[:8]
    script = Path(__file__).resolve().parents[1] / 'campaign.py'
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with (run / ('background-' + ident + '.log')).open('wb') as out:
        proc = subprocess.Popen([sys.executable, '-B', str(script), 'resume' if recover else 'run', str(run)], cwd=run, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, close_fds=True, creationflags=flags, start_new_session=os.name != 'nt')
    record = identity(proc.pid)
    write_json(run / ('launch-' + ident + '.json'), record)
    write_json(run / 'launched-supervisor.json', record)
    return {'status': 'launched', 'supervisor': record, 'campaign': str(run)}


def cancel(run):
    run = Path(run).absolute()
    load_campaign(run)
    (run / 'cancel').write_text('user requested cancellation\n', encoding='utf-8')
    stopped = cleanup_processes(run)
    journal(run, 'cancel-requested', stopped_pids=stopped)
    return {'status': 'cancel-requested', 'stopped_pids': stopped}
