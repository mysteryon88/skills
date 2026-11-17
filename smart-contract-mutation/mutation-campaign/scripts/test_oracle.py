"""Engine test-command wrapper. The engine owns swapping; this wrapper records actual sources."""
import json
from pathlib import Path
import sys
import uuid

from mutationlib.engines import context, test_once
from mutationlib.storage import child, digest, file_hash, read_json, write_json


def main():
    data = read_json(sys.argv[1]); run = Path(data['run']); worktree = Path(data['worktree'])
    output = Path(data['output']) / uuid.uuid4().hex[:12]
    ctx = context(run, data['lane'], worktree, output)
    baseline = read_json(run / 'snapshot.json')['files']
    hashes = {p: file_hash(child(worktree, p)) for p in data['lane']['targets']}
    changed = any(h != baseline[p]['sha256'] for p, h in hashes.items())
    sources = {}
    for p in data['lane']['targets']:
        dest = child(output / 'sources', p); dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(child(worktree, p).read_bytes()); sources[p] = dest.relative_to(run).as_posix()
    record = {'native_id': digest(hashes), 'path': ','.join(data['lane']['targets']), 'changed': changed, 'source_hashes': hashes, 'mutated_sources': sources, 'status': 'running'}
    write_json(output / 'record.json', record)
    outcome = test_once(ctx, 'oracle')
    record.update(status=outcome['status'], outcome=outcome)
    write_json(output / 'record.json', record)
    print(outcome.get('build', {}).get('output', ''))
    print(outcome.get('test', {}).get('output', ''))
    print('MUTATION_ORACLE_RESULT=' + json.dumps({'status': outcome['status'], 'changed': changed}))
    return 0 if outcome['status'] == 'survived' else 1


if __name__ == '__main__':
    raise SystemExit(main())
