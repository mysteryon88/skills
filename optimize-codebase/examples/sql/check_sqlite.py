"""Disposable SQLite demonstration: a faster index consumes more disk pages.
Uses no project databases or network. Temporary data are destroyed on exit.
"""
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

QUERY='SELECT id, payload FROM events WHERE tenant = ? AND state = ? ORDER BY id LIMIT 100'

def run():
    with tempfile.TemporaryDirectory(prefix='perf-sql-demo-') as folder:
        root=Path(folder);base=root/'base.db';candidate=root/'candidate.db'
        with closing(sqlite3.connect(base)) as c:
            with c:
                c.execute('PRAGMA journal_mode=DELETE')
                c.execute('CREATE TABLE events(id INTEGER PRIMARY KEY,tenant INTEGER,state INTEGER,payload TEXT)')
                c.executemany('INSERT INTO events VALUES(?,?,?,?)',
                              ((i,i%100,(i//100)%3,'synthetic'+str(i)) for i in range(50000)))
                c.execute('ANALYZE')
        shutil.copyfile(base,candidate)
        with closing(sqlite3.connect(candidate)) as c:
            with c:
                c.execute('CREATE INDEX event_lookup ON events(tenant,state,id)')
                c.execute('ANALYZE')
        a=sqlite3.connect(base);b=sqlite3.connect(candidate)
        try:
            checks=0
            for tenant in [0,1,49,99,100,-1]:
                for state in [0,1,2,3]:
                    assert a.execute(QUERY,(tenant,state)).fetchall()==b.execute(QUERY,(tenant,state)).fetchall()
                    checks+=1
            params=[(i*7%100,i%3) for i in range(40)]
            def measure(c):
                start=time.perf_counter_ns();count=0
                for q in params:count+=len(c.execute(QUERY,q).fetchall())
                return (time.perf_counter_ns()-start)/1e6,count
            measure(a);measure(b)
            before=[];after=[];order=[]
            for i in range(12):
                if i%2==0:x=measure(a);y=measure(b);order.append('AB')
                else:y=measure(b);x=measure(a);order.append('BA')
                assert x[1]==y[1];before.append(x[0]);after.append(y[0])
            def size(c):return c.execute('PRAGMA page_count').fetchone()[0]*c.execute('PRAGMA page_size').fetchone()[0]
            return {'sqlite':sqlite3.sqlite_version,'correctness_checks':checks,'unit':'ms/40 selects',
                    'before':before,'after':after,'order':order,'disk_before':size(a),'disk_after':size(b),
                    'plan_before':a.execute('EXPLAIN QUERY PLAN '+QUERY,(7,1)).fetchall(),
                    'plan_after':b.execute('EXPLAIN QUERY PLAN '+QUERY,(7,1)).fetchall(),
                    'limitations':['SQLite only; not a PostgreSQL test','Hot connections/OS cache','RAM, WAL and write overhead not measured'],
                    'decision':'REJECT under zero storage growth budget even when read time improves'}
        finally:a.close();b.close()

if __name__=='__main__':print(json.dumps(run(),indent=2))
