"""Evidence-bound test improvements; original campaign results remain immutable."""
from pathlib import Path
import re
import uuid

from .engines import apply_and_test, context, ensure_fork, run_engine, test_once
from .isolation import inventory
from .storage import CampaignError, child, digest, file_hash, load_campaign, lock, now, read_json, test_path, write_json


def signature(record):
    keys = ('path', 'line', 'column', 'operator', 'original', 'replacement', 'byte_offset', 'mutated_sha256')
    return digest({k: record[k] for k in keys if k in record})


def run_retest(run, request):
    run = Path(run).absolute()
    with lock(run / 'controller.lock'):
        state, scope = load_campaign(run)
        if request.get('scope_sha256') != state['scope_sha256'] or not request.get('specification') or not request.get('evidence'):
            raise CampaignError('retest requires current scope and expected-behavior evidence')
        from .results import evidence_path
        for ref, sha in request['evidence'].items():
            if file_hash(evidence_path(run, ref)) != sha:
                raise CampaignError('retest behavior evidence changed')
        ident = request['lane']; saved = state['lanes'][ident]
        lane = dict(next(x for x in scope['lanes'] if x['id'] == ident))
        if request.get('pass_regex'):
            if not request.get('pass_regex_reason') or re.compile(request['pass_regex']).match(''):
                raise CampaignError('updated passing-test evidence requires a reason and a nonempty match')
            lane['pass_regex'] = request['pass_regex']
        if saved['status'] != 'completed':
            raise CampaignError('only a calibrated completed lane can be retested')
        worktree = Path(saved['worktree']); manifest = read_json(run / 'snapshot.json')['files']
        current = inventory(worktree, scope.get('include_ignored', []))
        changes = {p for p in current.keys() | manifest.keys() if current.get(p) != manifest.get(p)}
        tests = set(request.get('tests', []))
        if not tests or changes != tests or tests.intersection(lane['targets']):
            raise CampaignError('retest changes must be exactly the declared test files; contract changes need a separate human decision')
        for p in tests:
            child(worktree, p)
            if p not in current or not test_path(p):
                raise CampaignError('declared improvement is not a current test file')
        parent_path = child(run, 'lanes/' + ident + '/results.json'); parent = read_json(parent_path)
        old = {r['native_id']: r for r in parent['records'] if r['status'] == 'survived'}
        ids = request.get('native_ids', [])
        if not ids or len(ids) != len(set(ids)) or not set(ids) <= old.keys():
            raise CampaignError('retest must identify original surviving mutant IDs')
        output = child(run, 'retests/' + ident + '-' + uuid.uuid4().hex[:12])
        ctx = context(run, lane, worktree, output); ensure_fork(ctx)
        baseline = test_once(ctx, 'improved-baseline')
        write_json(output / 'baseline.json', baseline)
        if baseline['status'] != 'survived':
            raise CampaignError('improved tests fail on original; no mutant-kill claim is allowed')
        ensure_fork(ctx)
        data = run_engine(ctx); ensure_fork(ctx); write_json(output / 'results.json', data)
        if data['counts']['tool_error']:
            raise CampaignError('retest has unresolved tool outcomes')
        by_signature = {}
        for record in data['records']:
            by_signature.setdefault(signature(record), []).append(record)
        mapping = {}
        for native_id in ids:
            matches = by_signature.get(signature(old[native_id]), [])
            if not matches and lane['tool'] == 'forge':
                record = old[native_id]; source = child(worktree, record['path']).read_bytes()
                lines = source.splitlines(keepends=True)
                offset = sum(len(line) for line in lines[:record['line'] - 1]) + record['column'] - 1
                before, after = record['original'].encode(), record['replacement'].encode()
                if source[offset:offset + len(before)] != before or before == after:
                    raise CampaignError('Forge survivor span cannot be faithfully replayed')
                copy = output / ('forge-' + digest(native_id)[:12] + '.source')
                copy.write_bytes(source[:offset] + after + source[offset + len(before):])
                replay = apply_and_test(ctx, {'id': native_id, 'path': record['path'], 'content_path': copy.name}, 'survivor-replay-' + digest(native_id)[:12])
                matches = [replay]
            if len(matches) != 1:
                raise CampaignError('retest mutant correspondence is missing or ambiguous')
            mapping[native_id] = {'native_id': matches[0]['native_id'], 'status': matches[0]['status'], 'signature': signature(old[native_id]), 'method': 'applied-source replay plus full native rerun' if lane['tool'] == 'forge' else 'unique native patch signature in full rerun'}
        receipt = {'schema': 1, 'at': now(), 'scope_sha256': state['scope_sha256'], 'lane': ident, 'parent_results_sha256': file_hash(parent_path), 'request': request, 'tests': {p: file_hash(child(worktree, p)) for p in tests}, 'baseline_sha256': file_hash(output / 'baseline.json'), 'results_sha256': file_hash(output / 'results.json'), 'mapping': mapping}
        write_json(output / 'retest.json', receipt)
        return {'retest': str(output / 'retest.json'), 'mapping': mapping}


def validate_retest(run, reference, lane_id, native_ids):
    state, _ = load_campaign(run); path = child(run, reference); receipt = read_json(path)
    if not reference.startswith('retests/' + lane_id + '-') or path.name != 'retest.json' or receipt['lane'] != lane_id or receipt['scope_sha256'] != state['scope_sha256'] or receipt['parent_results_sha256'] != file_hash(child(run, 'lanes/' + lane_id + '/results.json')):
        raise CampaignError('test improvement is not bound to original lane results')
    if file_hash(path.parent / 'baseline.json') != receipt['baseline_sha256'] or read_json(path.parent / 'baseline.json')['status'] != 'survived' or file_hash(path.parent / 'results.json') != receipt['results_sha256']:
        raise CampaignError('test improvement baseline/results changed')
    for relative, sha in receipt['tests'].items():
        if file_hash(child(Path(state['lanes'][lane_id]['worktree']), relative)) != sha:
            raise CampaignError('improved test changed after its rerun')
    for native_id in native_ids:
        if receipt['mapping'].get(native_id, {}).get('status') != 'killed':
            raise CampaignError('proposed improved test did not kill its original survivor')
    return receipt
