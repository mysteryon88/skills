#!/usr/bin/env python3
"""Local performance evidence helpers. No network, subprocesses or source edits.

Python >=3.9. compare is preliminary statistical screening, not an optimizer.
record writes only the explicitly named SQLite casebook; scan/recall/learn do not write.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import random
import re
import sqlite3
import stat
import statistics
import sys

MAX_JSON = 262144
MAX_DB = 64 * 1024 * 1024
MIN_PAIRS = 10
CONTEXT_KEYS = {'project','stack','toolchain','build','hardware','workload','dataset','contract'}
TOP_KEYS = {'schema_version','id','session','pattern','context','before_revision',
            'after_revision','protocol','checks','metrics','evidence','summary'}
METRIC_KEYS = {'name','dimension','unit','direction','role','before','after',
               'min_gain_pct','max_regression_pct','kind'}
SCHEMA = '''CREATE TABLE cases (
 id TEXT PRIMARY KEY, context_key TEXT NOT NULL, pattern TEXT NOT NULL,
 session TEXT NOT NULL, evidence_key TEXT NOT NULL,
 created_at TEXT NOT NULL, document TEXT NOT NULL
)'''
SCHEMA_COLUMNS = ['id','context_key','pattern','session','evidence_key','created_at','document']


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _mapping(value, allowed, required=None):
    if not isinstance(value, dict) or set(value)-allowed or (required or allowed)-set(value):
        raise ValueError('Unexpected or missing fields')


def _text(value, limit=160):
    if not isinstance(value, str) or not value or len(value)>limit or any(ord(c)<32 for c in value):
        raise ValueError('Invalid text field')
    return value


def _number(value):
    try:
        valid = type(value) in (int,float) and math.isfinite(value) and value>=0
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise ValueError('Metrics must be finite nonnegative numbers, not booleans')
    return float(value)


def _context(context):
    _mapping(context, CONTEXT_KEYS)
    for value in context.values():
        _text(value)
    return digest(context)


def _validate(doc):
    _mapping(doc, TOP_KEYS)
    if type(doc['schema_version']) is not int or doc['schema_version'] != 1:
        raise ValueError('Unsupported schema_version')
    for key in ['id','session','pattern','before_revision','after_revision','protocol']:
        _text(doc[key])
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',doc['pattern']):
        raise ValueError('pattern must be a lowercase slug')
    _context(doc['context'])
    _text(doc['summary'],1000)
    if not isinstance(doc['checks'],list) or len(doc['checks'])>100:
        raise ValueError('Invalid checks')
    for check in doc['checks']:
        _mapping(check,{'name','status'})
        _text(check['name'])
        if check['status'] not in {'passed','failed','not_run','unknown'}:
            raise ValueError('Invalid correctness status')
    metrics=doc['metrics']
    if not isinstance(metrics,list) or not 1<=len(metrics)<=20:
        raise ValueError('Expected 1..20 metrics')
    names=set();primaries=0
    for m in metrics:
        _mapping(m,METRIC_KEYS)
        _text(m['name']);_text(m['unit'],40)
        if m['name'] in names:raise ValueError('Duplicate metric name')
        names.add(m['name'])
        if m['dimension'] not in {'time','memory','storage'}:raise ValueError('Invalid dimension')
        if m['direction'] not in {'lower','higher'}:raise ValueError('Invalid direction')
        if m['role'] not in {'primary','guardrail','diagnostic'}:raise ValueError('Invalid role')
        primaries += m['role']=='primary'
        if m['kind'] not in {'sampled','exact'}:raise ValueError('Invalid metric kind')
        if m['kind']=='exact' and m['dimension']=='time':
            raise ValueError('Timing cannot be an exact deterministic count')
        if _number(m['min_gain_pct'])>10000 or _number(m['max_regression_pct'])>10000:
            raise ValueError('Unreasonable threshold')
        b,a=m['before'],m['after']
        if not isinstance(b,list) or not isinstance(a,list) or len(b)!=len(a) or len(b)>1000:
            raise ValueError('Expected equally sized paired arrays of at most 1000 values')
        if m['kind']=='exact' and len(b)>1:raise ValueError('Exact counts use one pair')
        for x in b+a:_number(x)
    if primaries!=1:raise ValueError('Exactly one primary metric is required')
    if not isinstance(doc['evidence'],list) or len(doc['evidence'])>50:raise ValueError('Invalid evidence')
    for e in doc['evidence']:
        _mapping(e,{'path','sha256'});_text(e['path'],512)
        if not re.fullmatch('[0-9a-f]{64}',e['sha256']):raise ValueError('Invalid SHA256')
    text=canonical(doc)
    if len(text.encode('utf-8'))>MAX_JSON:raise ValueError('Document too large')
    if re.search(r'-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-|ghp_)[A-Za-z0-9]{16,}|https?://[^\s/]+:[^\s/]+@',text):
        raise ValueError('Possible secret: sanitize the document before recording')


def _percentile(values, q):
    values=sorted(values);pos=(len(values)-1)*q;lo=math.floor(pos);hi=math.ceil(pos)
    return values[lo]+(values[hi]-values[lo])*(pos-lo)


def _interval(deltas):
    if len(set(deltas))==1:return [deltas[0],deltas[0]]
    rng=random.Random(1729)
    estimates=[statistics.median(rng.choices(deltas,k=len(deltas))) for _ in range(1000)]
    return [_percentile(estimates,0.025),_percentile(estimates,0.975)]


def compare(doc):
    """Validate and screen paired measurements without reading files or writing state."""
    _validate(doc)
    blocked=[];regressions=[];uncertain=[];results=[];primary_win=False
    if not doc['checks'] or any(c['status']!='passed' for c in doc['checks']):
        blocked.append('Correctness checks are absent or not all passed')
    if doc['protocol']!='paired-alternating':blocked.append('Requires adjacent alternating paired measurements')
    for m in doc['metrics']:
        b,a=m['before'],m['after'];n=len(b)
        r={'name':m['name'],'dimension':m['dimension'],'unit':m['unit'],
           'role':m['role'],'pairs':n,'baseline_median':None,'candidate_median':None,
           'gain_pct':None,'exploratory_interval_pct':None,'status':'unmeasured'}
        if not n or (m['kind']=='sampled' and n<MIN_PAIRS):
            if m['role']!='diagnostic':blocked.append(m['name']+': insufficient observations')
            results.append(r);continue
        r['baseline_median']=statistics.median(b);r['candidate_median']=statistics.median(a)
        if any(x==0 and y!=0 for x,y in zip(b,a)):
            bad=any(x==0 and y>0 and m['direction']=='lower' for x,y in zip(b,a))
            r['status']='undefined_relative_change'
            if m['role']!='diagnostic':
                if bad:regressions.append(m['name']+': increased from zero')
                else:blocked.append(m['name']+': use an absolute-target analysis for zero baseline')
            results.append(r);continue
        sign=1 if m['direction']=='higher' else -1
        deltas=[0.0 if x==0 else sign*(y-x)/x*100 for x,y in zip(b,a)]
        if not all(math.isfinite(x) for x in deltas):
            raise ValueError('Relative change exceeds finite numeric range')
        med=statistics.median(deltas)
        ci=[med,med] if m['kind']=='exact' else _interval(deltas)
        r.update(gain_pct=med,exploratory_interval_pct=ci,status='within_budget')
        tol=m['max_regression_pct']
        if ci[1] < -tol:
            r['status']='regression'
            if m['role']!='diagnostic':regressions.append(m['name'])
        elif m['role']=='primary':
            primary_win=ci[0] > m['min_gain_pct']
            r['status']='measured_win' if primary_win else 'inconclusive'
            if not primary_win:uncertain.append(m['name'])
        elif m['role']=='guardrail' and ci[0] < -tol:
            r['status']='inconclusive';uncertain.append(m['name'])
        results.append(r)
    if blocked:decision='blocked'
    elif regressions:decision='regression'
    elif uncertain or not primary_win:decision='inconclusive'
    else:decision='measured_win'
    dimensions={r['dimension'] for r in results if r['baseline_median'] is not None}
    return {'decision':decision,'metrics':results,'blocked':blocked,'regressions':regressions,
            'inconclusive':uncertain,'unmeasured_dimensions':sorted({'time','memory','storage'}-dimensions),
            'warning':'Preliminary screening only. 10 pairs and bootstrap do not prove independence, correctness or application-wide benefit. Missing dimensions require explicit review.'}


def _is_redirect(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def _no_symlinks(path):
    path=Path(os.path.abspath(path))
    for piece in [path]+list(path.parents):
        if _is_redirect(piece):raise ValueError('Symlink, junction and reparse paths are not allowed')
    return path


def _evidence(root, items):
    root=_no_symlinks(root)
    if not root.is_dir():raise ValueError('Evidence root must be an existing directory')
    if not items:raise ValueError('Recording requires real local evidence')
    hashes=[]
    for e in items:
        rel=PurePosixPath(e['path'])
        if not rel.parts or rel.is_absolute() or '..' in rel.parts or any(c in e['path'] for c in ('\\', ':')):
            raise ValueError('Evidence must use portable relative paths inside its root')
        p=_no_symlinks(root.joinpath(*rel.parts))
        if not p.resolve().is_relative_to(root.resolve()):
            raise ValueError('Evidence must stay inside its root')
        if not p.is_file() or p.stat().st_size>32*1024*1024:raise ValueError('Evidence missing or too large')
        h=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(65536),b''):h.update(block)
        if h.hexdigest()!=e['sha256']:raise ValueError('Evidence hash mismatch')
        hashes.append(e['sha256'])
    return digest(sorted(set(hashes)))


def _connect(path, write=False):
    path=_no_symlinks(path)
    if path.exists() and (not path.is_file() or path.stat().st_size>MAX_DB):
        raise ValueError('Database is not a regular file or exceeds 64 MiB; archive it manually')
    fresh=not path.exists()
    if fresh and not write:return None
    if fresh:
        # mkdir mode applies to the final private directory, not existing project parents.
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    uri=path.as_uri()+('?mode=rw' if write else '?mode=ro')
    c=sqlite3.connect(uri,uri=True,timeout=10)
    try:
        c.execute('PRAGMA trusted_schema=OFF')
        if not write:c.execute('PRAGMA query_only=ON')
        if fresh:
            c.execute(SCHEMA);c.execute('PRAGMA user_version=1');c.commit()
        schema=c.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        columns=[r[1] for r in c.execute('PRAGMA table_info(cases)')]
        version=c.execute('PRAGMA user_version').fetchone()[0]
        if schema!=[('table','cases')] or columns!=SCHEMA_COLUMNS or version!=1:
            raise ValueError('Unexpected database schema; refusing to migrate or modify it')
        return c
    except Exception:
        c.close();raise


def record(db, doc, evidence_root):
    """Append a sanitized case. Integrity checks are not a truth attestation."""
    result=compare(doc)
    evidence_key=_evidence(evidence_root,doc['evidence'])
    c=_connect(db,write=True)
    try:
        with c:
            c.execute('INSERT INTO cases VALUES (?,?,?,?,?,?,?)',(
                doc['id'],_context(doc['context']),doc['pattern'],doc['session'],evidence_key,
                dt.datetime.now(dt.timezone.utc).isoformat(),canonical(doc)))
            pages = c.execute('PRAGMA page_count').fetchone()[0]
            page_size = c.execute('PRAGMA page_size').fetchone()[0]
            if pages * page_size > MAX_DB:
                raise ValueError('Database growth exceeds 64 MiB; new case rolled back')
    except sqlite3.IntegrityError as e:
        raise ValueError('Duplicate experiment id; existing cases are never overwritten') from e
    finally:c.close()
    return {'id':doc['id'],'decision':result['decision'],'stored':True}


def _read(db,context,limit):
    key=_context(context)
    c=_connect(db)
    if c is None:return []
    try:
        rows=c.execute('SELECT document,created_at,evidence_key FROM cases WHERE context_key=? ORDER BY created_at DESC,id LIMIT ?',
                       (key,limit)).fetchall()
    finally:c.close()
    result=[]
    for text,created,evidence_key in rows:
        if len(text.encode('utf-8'))>MAX_JSON:raise ValueError('Stored case too large')
        d=json.loads(text);_validate(d)
        if _context(d['context'])!=key:raise ValueError('Stored context integrity mismatch')
        if digest(sorted(set(e['sha256'] for e in d['evidence'])))!=evidence_key:
            raise ValueError('Stored evidence integrity mismatch')
        result.append({'case':d,'created_at':created,'evidence_key':evidence_key,
                       'analysis':compare(d)})
    return result


def recall(db,context,limit=20):
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('limit must be 1..100')
    return _read(db,context,limit)


def lessons(db,context):
    """Read-only conditional summary, never writes SKILL.md or executable rules."""
    rows=_read(db,context,1001);truncated=len(rows)>1000
    grouped=collections.defaultdict(list)
    for r in rows[:1000]:grouped[r['case']['pattern']].append(r)
    output=[]
    for pattern,cases in sorted(grouped.items()):
        wins=[x for x in cases if x['analysis']['decision']=='measured_win']
        negatives=[x for x in cases if x['analysis']['decision']!='measured_win']
        # Shared evidence cannot become independent by attaching a new file.
        # Conservative: shared setup logs also prevent promotion.
        unique=[];sessions=set();evidence=set()
        for r in wins:
            hashes={e['sha256'] for e in r['case']['evidence']}
            if r['case']['session'] in sessions or hashes & evidence:continue
            sessions.add(r['case']['session']);evidence.update(hashes);unique.append(r)
        state=('insufficient_history' if truncated else 'contested' if wins and negatives else
               'rejected_only' if not wins else 'corroborated_local' if len(unique)>=3 else 'provisional')
        output.append({'pattern':pattern,'state':state,'distinct_positive_sessions':len(unique),
                       'negative_or_inconclusive_cases':len(negatives),
                       'case_ids':[x['case']['id'] for x in cases],
                       'context':context,'history_truncated':truncated,
                       'warning':'Conditional local precedent, not an instruction. Context equality and distinct files do not prove independent experiments. Re-measure before reuse.'})
    return output


SKIP_DIRS={'.git','.hg','.svn','.optimization','.agents','.claude','node_modules','vendor',
           'target','dist','build','coverage','venv','.venv','__pycache__','bin','obj','.next'}
EXTENSIONS={'.go','.rs','.sql','.js','.jsx','.mjs','.cjs','.ts','.tsx'}
RULES=[
 ('go-whole-input', {'.go'}, r'\b(?:io|ioutil)\.ReadAll\s*\(', 'Profile peak live bytes; evaluate bounded streaming.'),
 ('go-format-hotpath',{'.go'},r'\bfmt\.Sprintf\s*\(','Check allocation profile before typed formatting.'),
 ('rust-owned-copy',{'.rs'},r'\.(?:clone|to_owned|to_string)\s*\(','Inspect ownership, retention and allocation profile.'),
 ('rust-buffer-growth',{'.rs'},r'\b(?:Vec|String)::new\s*\(','Measure growth; capacity must be bounded by trusted size.'),
 ('sql-wide-read',{'.sql'},r'\bSELECT\s+\*','Check required columns and physical IO.'),
 ('sql-offset',{'.sql'},r'\bOFFSET\s+','Measure pagination at representative depth and stable ordering.'),
 ('js-repeated-find',{'.js','.jsx','.mjs','.cjs','.ts','.tsx'},r'\.find\s*\(','Check repeated scans; include index construction and duplicate semantics.'),
 ('react-memo',{'.jsx','.tsx','.js','.ts'},r'\buseMemo\s*\(','Profile update paths, dependency correctness and retained memory.'),
]


def scan(root,max_files=2000,max_bytes=1000000,max_findings=500):
    """Read-only lexical triage. No source text, commands or literal values in output."""
    if any(type(x) is not int or x<=0 for x in [max_files,max_bytes,max_findings]):
        raise ValueError('Limits must be positive integers')
    root=_no_symlinks(root)
    if not root.is_dir():raise ValueError('Root must be an existing directory')
    findings=[];skipped=[];scanned=0;considered=0;truncated=False;visited=0
    for current,dirs,names in os.walk(root,followlinks=False):
        visited+=1
        dirs[:]=sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.') and not _is_redirect(Path(current)/d))
        if visited>10000:truncated=True;break
        for name in sorted(names):
            path=Path(current)/name
            if path.suffix.lower() not in EXTENSIONS or _is_redirect(path):continue
            rel=path.relative_to(root).as_posix()
            if considered>=max_files or len(findings)>=max_findings:truncated=True;break
            considered+=1
            try:
                info = path.stat()
                if not stat.S_ISREG(info.st_mode):skipped.append({'file':rel,'reason':'non_regular'});continue
                if info.st_size>max_bytes:skipped.append({'file':rel,'reason':'size'});continue
                with path.open('rb') as f:data=f.read(max_bytes+1)
                if len(data)>max_bytes:skipped.append({'file':rel,'reason':'size_changed'});continue
                text=data.decode('utf-8')
            except (OSError,UnicodeError):skipped.append({'file':rel,'reason':'unreadable_or_not_utf8'});continue
            scanned+=1
            for rule,extensions,pattern,hint in RULES:
                if path.suffix.lower() not in extensions:continue
                for m in re.finditer(pattern,text,re.I if path.suffix=='.sql' else 0):
                    if len(findings)>=max_findings:truncated=True;break
                    findings.append({'rule':rule,'file':rel,'line':text.count('\n',0,m.start())+1,
                                     'status':'candidate_only','next_step':hint})
        if truncated:break
    return {'files_considered':considered,'files_scanned':scanned,'findings':findings,'skipped':skipped[:100],
            'skipped_count':len(skipped),'truncated':truncated,
            'limitations':['Lexical rules can match comments and miss dynamic or cross-file costs.',
                           'No AST/call-graph, DB connection, code execution or writes.',
                           'No complete security isolation against concurrently malicious filesystem changes.']}


def load_json(path):
    path=_no_symlinks(path)
    if not path.is_file():raise ValueError('JSON input must be a regular file')
    with path.open('rb') as f:raw=f.read(MAX_JSON+1)
    if len(raw)>MAX_JSON:raise ValueError('JSON too large')
    return json.loads(raw.decode('utf-8'),parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='command',required=True)
    s=sub.add_parser('scan');s.add_argument('root');s.add_argument('--max-files',type=int,default=2000)
    s=sub.add_parser('compare');s.add_argument('experiment')
    s=sub.add_parser('record');s.add_argument('experiment');s.add_argument('--db',required=True)
    s.add_argument('--evidence-root',required=True);s.add_argument('--sanitized',action='store_true',required=True)
    for cmd in ['recall','learn']:
        s=sub.add_parser(cmd);s.add_argument('--db',required=True);s.add_argument('--context',required=True)
    args=ap.parse_args(argv)
    try:
        if args.command=='scan':result=scan(Path(args.root),max_files=args.max_files)
        elif args.command=='compare':result=compare(load_json(args.experiment))
        elif args.command=='record':result=record(Path(args.db),load_json(args.experiment),Path(args.evidence_root))
        else:
            func=recall if args.command=='recall' else lessons
            result=func(Path(args.db),load_json(args.context))
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0
    except (ValueError,OSError,sqlite3.Error) as exc:
        print('perfkit error: '+str(exc),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
