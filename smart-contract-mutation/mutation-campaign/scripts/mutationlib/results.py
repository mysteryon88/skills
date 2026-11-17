from collections import Counter
from pathlib import Path
import re

from .storage import CampaignError, binary_file, child, credential_path, digest, file_hash, load_campaign, lock, read_json, replace_bytes, update_state, write_json


STATUSES = ('killed', 'survived', 'invalid', 'timed_out', 'skipped', 'equivalent', 'presumed_equivalent', 'tool_error')


def result(records, raw_score=None, counts=None):
    ids = [str(r['native_id']) for r in records]
    if len(set(ids)) != len(ids):
        raise CampaignError('duplicate native mutant IDs')
    if any(r.get('status') not in STATUSES for r in records):
        raise CampaignError('unknown native outcome')
    observed = Counter(r['status'] for r in records)
    counts = counts if counts is not None else observed
    if any(type(n) is not int or n < 0 for n in counts.values()):
        raise CampaignError('invalid native counts')
    values = {k: counts.get(k, 0) for k in STATUSES}
    denominator = values['killed'] + values['survived']
    return {'schema': 1, 'reconciled': True, 'counts': values, 'records': records, 'raw_score': raw_score or {'formula': 'not established; see native report', 'value': None}, 'behavior_score': {'formula': 'killed / (killed + survived)', 'value': values['killed'] / denominator if denominator else None, 'scope': 'this tool and selected tests only'}}


def normalize_forge(raw):
    summary = raw['summary']
    keys = ('killed', 'survived', 'invalid', 'skipped', 'timed_out')
    if summary['total'] != sum(summary[k] for k in keys):
        raise CampaignError('Forge count reconciliation failed')
    records = []
    for path, mutants in raw['survived_mutants'].items():
        for m in mutants:
            record = {'path': path, 'line': m['line'], 'column': m['column'], 'original': m['original'], 'replacement': m['mutant'], 'status': 'survived'}
            record['native_id'] = digest(record)[:24]
            records.append(record)
    if len(records) != summary['survived']:
        raise CampaignError('Forge survivor reconciliation failed')
    return result(records, {'formula': 'killed / (killed + survived)', 'value': summary.get('mutation_score'), 'unit': 'percent'}, {k: summary[k] for k in keys})


def normalize_mewt(raw, native_ids, failure_regex, pass_regex=None):
    records = []
    native_scores = {}
    for r in raw['results']:
        m, t, o = r['mutant'], r['target'], r['outcome']
        if str(m['id']) != str(o['mutant_id']):
            raise CampaignError('native ID/outcome mismatch')
        status = {'Uncaught': 'survived', 'TestFail': 'killed', 'Timeout': 'timed_out', 'Skipped': 'skipped', 'CompileError': 'invalid', 'BuildFail': 'invalid'}.get(o['status'])
        if status is None:
            raise CampaignError('unknown Mewt/MuTON outcome: ' + str(o['status']))
        output = o.get('output') or ''
        if status == 'killed' and not re.search(failure_regex, output):
            status = 'tool_error'
        if status == 'survived' and pass_regex and not re.search(pass_regex, output):
            status = 'tool_error'
        records.append({'native_id': str(m['id']), 'path': t['path'], 'original': m['old_text'], 'replacement': m['new_text'], 'byte_offset': m.get('byte_offset'), 'line_offset': m.get('line_offset'), 'operator': m.get('mutation_slug'), 'status': status, 'native_status': o['status']})
        target_score = native_scores.setdefault(t['path'], {'test_fail': 0, 'eligible': 0})
        if o['status'] != 'Skipped':
            target_score['eligible'] += 1
            target_score['test_fail'] += o['status'] == 'TestFail'
    if {r['native_id'] for r in records} != {str(x) for x in native_ids}:
        raise CampaignError('native inventory/outcome reconciliation failed: pending, missing or extra IDs')
    for score in native_scores.values():
        eligible = score['eligible']
        score['percent'] = 100.0 * score['test_fail'] / eligible if eligible else 0.0
    return result(records, {'formula': '100 * TestFail / all statuses except Skipped; reconstructed per target from the native outcome inventory', 'targets': native_scores, 'unit': 'percent'})


def normalize_acton(events):
    finished = [e for e in events if e.get('event') == 'session_finished']
    if len(finished) != 1:
        raise CampaignError('Acton report is incomplete or contains multiple sessions')
    summary = finished[0]
    records = []
    for e in events:
        if e.get('event') != 'mutation_completed':
            continue
        m = e['record']
        status = {'killed': 'killed', 'survived': 'survived', 'compile_error': 'invalid', 'compile-error': 'invalid', 'timed_out': 'timed_out', 'timeout': 'timed_out', 'skipped': 'skipped'}.get(m['status'])
        if status is None:
            raise CampaignError('unknown Acton status')
        records.append({'native_id': str(m['id']), 'path': m['source_path'], 'line': m['line'], 'column': m.get('column'), 'operator': m['rule_name'], 'context': m.get('code_context'), 'status': status, 'session_id': summary['session_id']})
    observed = Counter(r['status'] for r in records)
    expected = {'killed': summary['killed'], 'survived': summary['survived'], 'invalid': summary['compile_errors'], 'timed_out': summary['timed_out']}
    if summary['total_mutants'] != len(records) or any(observed[k] != v for k, v in expected.items()):
        raise CampaignError('Acton inventory/count reconciliation failed')
    return result(records, {'formula': '100 * killed / (killed + survived); compile errors and timeouts excluded', 'value': summary['mutation_score'], 'unit': 'percent'})


def require_nonempty_campaign(data):
    if not data.get('reconciled') or not sum(data.get('counts', {}).values()):
        raise CampaignError('full native run reported no reconciled mutants; it cannot be marked completed')


def validate_invariant(data, root, scope_hash):
    if data.get('scope_sha256') != scope_hash or data.get('attempts', 0) <= 0 or data.get('successful_transitions', 0) <= 0 or data.get('reverts', -1) < 0 or not data.get('target_selectors') or not data.get('assertions') or not data.get('evidence'):
        raise CampaignError('invariant execution is vacuous, unsupported or not bound to current scope')
    if data['successful_transitions'] + data['reverts'] > data['attempts']:
        raise CampaignError('inconsistent invariant telemetry')
    if data['successful_transitions'] * 2 <= data['attempts'] or data['reverts'] * 2 > data['attempts']:
        raise CampaignError('invariant calls mostly revert or fail to make relevant state transitions')
    for relative, expected in data['evidence'].items():
        if file_hash(child(root, relative)) != expected:
            raise CampaignError('stale invariant telemetry')


def capture_invariant(run, lane, worktree, attempt_output):
    receipt_source = child(worktree, lane['invariant']['receipt'])
    if credential_path(receipt_source):
        raise CampaignError('credential file cannot be captured as invariant evidence')
    data = read_json(receipt_source)
    output = Path(attempt_output).relative_to(run).as_posix() + '/invariant'
    receipt_ref = output + '/receipt.json'
    replace_bytes(run, receipt_ref, receipt_source.read_bytes())
    evidence = {}
    for relative, expected in data.get('evidence', {}).items():
        source = child(worktree, relative)
        if credential_path(source):
            raise CampaignError('credential file cannot be captured as invariant evidence')
        actual = file_hash(source)
        reference = output + '/evidence/' + relative
        replace_bytes(run, reference, source.read_bytes())
        evidence[relative] = {'path': reference, 'sha256': actual, 'expected_sha256': expected}
    return {'receipt': receipt_ref, 'receipt_sha256': file_hash(run / receipt_ref), 'evidence': evidence}


def evidence_path(run, relative):
    if relative.startswith('worktree/'):
        _, ident, path = relative.split('/', 2)
        state, _ = load_campaign(run)
        return child(Path(state['lanes'][ident]['worktree']), path)
    return child(run, relative)


def survivors(run):
    state, _ = load_campaign(run)
    found = {}
    for ident, lane in state['lanes'].items():
        path = Path(run) / 'lanes' / ident / 'results.json'
        if path.exists():
            data = read_json(path)
            if not data.get('reconciled'):
                raise CampaignError('unreconciled native inventory')
            for record in data['records']:
                if record['status'] == 'survived':
                    found[ident + ':' + str(record['native_id'])] = record
            if sum(r['status'] == 'survived' for r in data['records']) != data['counts']['survived']:
                raise CampaignError('survivor count no longer reconciles')
    return found


def save_triage(run, data):
    state, _ = load_campaign(run)
    if data.get('scope_sha256') != state['scope_sha256']:
        raise CampaignError('triage must bind the frozen scope')
    covered = []
    for group in data.get('groups', []):
        for key in ('ids', 'classification', 'explanation', 'diff', 'reachability', 'tests', 'assertions', 'environment', 'specification', 'reproduction', 'confidence', 'evidence'):
            if not group.get(key):
                raise CampaignError('survivor group lacks ' + key)
        if group['confidence'] not in ('high', 'medium', 'low'):
            raise CampaignError('confidence must be high, medium or low')
        if group['classification'] not in ('test_gap', 'unreachable', 'environment', 'equivalent', 'presumed_equivalent', 'duplicate', 'tool_error', 'contract_defect'):
            raise CampaignError('survivor cause is unresolved or unsupported')
        if len(group['ids']) > 1 and not group.get('grouping_evidence'):
            raise CampaignError('grouping requires evidence of identical substantive cases')
        for relative, expected in group['evidence'].items():
            if file_hash(evidence_path(run, relative)) != expected:
                raise CampaignError('stale survivor evidence')
        if group.get('test_improvement'):
            from .retest import validate_retest
            lanes = {i.split(':', 1)[0] for i in group['ids']}
            if len(lanes) != 1:
                raise CampaignError('test-improvement group must belong to one lane')
            validate_retest(run, group['test_improvement'], next(iter(lanes)), [i.split(':', 1)[1] for i in group['ids']])
        covered.extend(group['ids'])
    if len(set(covered)) != len(covered) or set(covered) != set(survivors(run)):
        raise CampaignError('every native survivor must map to exactly one evidence-backed group')
    write_json(Path(run) / 'triage.json', data)
    return {'accounted_survivors': len(covered), 'groups': len(data['groups'])}


def review_bundle(run):
    from .isolation import inventory
    run = Path(run).absolute()
    state, scope = load_campaign(run)
    paths = ['scope.json', 'snapshot.json', 'triage.json']
    for ident, lane in state['lanes'].items():
        paths.extend(['lanes/' + ident + '/' + x for x in ('baseline.json', 'calibration.json', 'results.json')])
        if (Path(run) / 'lanes' / ident / 'progress.json').is_file():
            paths.append('lanes/' + ident + '/progress.json')
        if (Path(run) / 'lanes' / ident / 'fork.json').is_file():
            paths.append('lanes/' + ident + '/fork.json')
    hashes = {p: file_hash(child(run, p)) for p in paths}
    binary = set()
    visited = set()
    def include(reference, expected=None, binary_ok=False):
        path = evidence_path(run, reference); sha = file_hash(path)
        if expected is not None and expected != sha:
            raise CampaignError('referenced execution evidence changed: ' + reference)
        hashes[reference] = sha
        if binary_ok and binary_file(path):
            binary.add(reference)
        return path
    def closure(value):
        if isinstance(value, list):
            for item in value:
                closure(item)
        elif isinstance(value, dict):
            if value.get('invariant'):
                item = value['invariant']
                include(item['receipt'], item['receipt_sha256'])
                for captured in item['evidence'].values():
                    include(captured['path'], captured['sha256'], binary_ok=True)
            if value.get('logs'):
                directory = value['logs']
                for name in ('request.json', 'receipt.json', 'stdout.log', 'stderr.log', 'workload-exit.json'):
                    include(directory + '/' + name)
            if value.get('mutated_source'):
                include(value['mutated_source'], value.get('mutated_sha256'))
            for source_path, ref in value.get('mutated_sources', {}).items():
                include(ref, value.get('source_hashes', {}).get(source_path))
            for key in ('compiled_captures', 'native_artifacts'):
                for ref, sha in value.get(key, {}).items():
                    include(ref, sha, binary_ok=True)
            if value.get('oracle_record'):
                ref = value['oracle_record']; path = include(ref, value['oracle_sha256'])
                if ref not in visited:
                    visited.add(ref); closure(read_json(path))
            for key, item in value.items():
                if key not in ('logs', 'compiled_artifacts', 'compiled_captures', 'native_artifacts', 'mutated_sources'):
                    closure(item)
    for ref in list(paths):
        closure(read_json(child(run, ref)))
    if scope.get('parent_campaign'):
        reference = scope.get('parent_lineage')
        if not reference:
            raise CampaignError('successor campaign is missing its parent lineage receipt')
        lineage_path = include(reference)
        lineage = read_json(lineage_path)
        if lineage.get('parent_campaign') != scope['parent_campaign'] or lineage.get('repair_reason') != scope.get('parent_reason') or lineage.get('successor_scope_sha256') != state['scope_sha256']:
            raise CampaignError('parent repair lineage does not bind this successor scope')
        for evidence_ref, expected in lineage.get('evidence', {}).items():
            include(evidence_ref, expected)
    triage = read_json(Path(run) / 'triage.json')
    save_triage(run, triage)
    for group in triage['groups']:
        for ref in group['evidence']:
            hashes[ref] = file_hash(evidence_path(run, ref))
        if group.get('test_improvement'):
            reference = group['test_improvement']; path = child(run, reference)
            for name in ('retest.json', 'baseline.json', 'results.json'):
                ref = (path.parent / name).relative_to(run).as_posix(); hashes[ref] = file_hash(child(run, ref)); closure(read_json(child(run, ref)))
    source = {ident: inventory(Path(lane['worktree']), scope.get('include_ignored', [])) for ident, lane in state['lanes'].items()}
    snapshot_files = read_json(Path(run) / 'snapshot.json')['files']
    allowed = {ident: set() for ident in state['lanes']}
    from .retest import validate_retest
    for group in triage['groups']:
        if group.get('test_improvement'):
            ident = group['ids'][0].split(':', 1)[0]
            receipt = validate_retest(run, group['test_improvement'], ident, [p.split(':', 1)[1] for p in group['ids']])
            allowed[ident].update(receipt['tests'])
    for ident, current in source.items():
        changed = {p for p in current.keys() | snapshot_files.keys() if current.get(p) != snapshot_files.get(p)}
        if not changed <= allowed[ident]:
            raise CampaignError('execution inputs changed without a verified test rerun: ' + ','.join(sorted(changed - allowed[ident])))
    return {'campaign': state['id'], 'scope_sha256': state['scope_sha256'], 'scope_hash_derivation': 'SHA256 of UTF-8 JSON with sorted keys, ensure_ascii=false, separators=(comma,colon); distinct from pretty-printed scope.json byte hash', 'coordinator': read_json(Path(run) / 'scope.json')['coordinator'], 'artifacts': hashes, 'binary_artifacts': sorted(binary), 'binary_review_limit': 'Only public compiled artifact/database byte digests are supplied; binary contents stay local. Review source, native output and execution receipts; no binary disassembly claim.', 'worktree_files': source}


def finish(run):
    with lock(Path(run) / 'controller.lock'):
        return _finish(Path(run))


def _finish(run):
    from .runtimes import validate_review
    state, scope = load_campaign(run)
    if state['status'] == 'running':
        raise CampaignError('cannot finalize while tools are running')
    if any(l['status'] != 'completed' for l in state['lanes'].values()):
        raise CampaignError('selected runs are not all calibrated and complete')
    for ident in state['lanes']:
        data = read_json(Path(run) / 'lanes' / ident / 'results.json')
        require_nonempty_campaign(data)
        if data['counts']['tool_error']:
            raise CampaignError('unresolved tool outcomes prevent verified completion')
    bundle = review_bundle(run)
    validate_review(run, bundle)
    if state['status'] != 'verified-complete':
        from .rpc import pin_from_scope
        for lane in scope['lanes']:
            if lane.get('fork'):
                pin = read_json(child(run, 'lanes/' + lane['id'] + '/fork.json'))
                pin_from_scope(lane['fork'], pin)
    state = update_state(run, lambda current: current.update(status='verified-complete'))
    report(run)
    return {'status': state['status'], 'report': str(Path(run) / 'REPORT.md')}


def report(run):
    state, scope = load_campaign(run)
    lines = ['# Mutation campaign ' + state['id'], '', 'Status: ' + state['status'], '', 'Frozen scope SHA256: ' + state['scope_sha256'], '', '| Lane / engine | ' + ' | '.join(STATUSES) + ' |', '|---|' + '---:|' * len(STATUSES)]
    rows = []
    for lane in scope['lanes']:
        ident = lane['id']; path = Path(run) / 'lanes' / ident / 'results.json'
        lines.extend(['', 'Tool choice ' + ident + ': ' + lane['rationale']])
        if path.exists():
            data = read_json(path)
            rows.append('| ' + ident + ' / ' + lane['tool'] + ' | ' + ' | '.join(str(data['counts'][k]) for k in STATUSES) + ' |')
            lines += ['Native formula: ' + str(data['raw_score']), 'Behavior-only comparison for this scope: ' + str(data['behavior_score'])]
        else:
            lines += ['Run state: ' + state['lanes'][ident]['status'], 'Reason: ' + state['lanes'][ident].get('reason', 'pending')]
    lines[8:8] = rows
    pending = survivors(run)
    triage_path = Path(run) / 'triage.json'
    lines += ['', '## Survivors', '']
    if triage_path.exists():
        groups = read_json(triage_path)['groups']
        dispositions = Counter()
        for group in groups:
            dispositions[group['classification']] += len(group['ids'])
            lines += ['- ' + ', '.join(group['ids']) + ': ' + group['classification'] + ' (' + group['confidence'] + ') — ' + group['explanation']]
            if group.get('test_improvement'):
                receipt = read_json(child(run, group['test_improvement']))
                lines += ['  Test improvement: ' + group['test_improvement'] + '; original survivor outcomes: ' + str(receipt['mapping'])]
        lines += ['', 'Analyst dispositions (native survivor counts retained): ' + str(dict(dispositions))]
    else:
        lines += ['- ' + ident + ': pending analysis' for ident in pending] or ['No survivors in the selected scope.']
    lines += ['', 'Raw reports, per-command receipts and scope stay in this project. Scores from different tools are not added. Fork caches are lazy reads, not complete offline chain snapshots.', '']
    (Path(run) / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
