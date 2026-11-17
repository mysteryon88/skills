# SQL: queries, storage, and write cost

Identify the engine and exact version. PostgreSQL, MySQL, SQLite, and other engines have different plans, types, and DDL. Do not apply the PostgreSQL commands below blindly.

## Safe entry point

By default, inspect SQL and existing planning-only EXPLAIN output. Executing a query, even with EXPLAIN, requires a verified isolated environment. `EXPLAIN ANALYZE` really executes the statement. Allow it only in a disposable environment with synthetic/anonymized data after checking the statement and called functions. SELECT/EXECUTE may have external effects. A read-only transaction/ROLLBACK is not a complete sandbox. Do not automatically run unknown functions, CREATE TABLE AS, EXECUTE, or materialized-view operations.

Example for a **verified safe SELECT in disposable PostgreSQL**:

```sql
EXPLAIN (FORMAT JSON, SETTINGS) SELECT ...;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SETTINGS, FORMAT JSON) SELECT ...;
```

Check which options the project's version supports. EXPLAIN cost is not time. Plan instrumentation has overhead, and TIMING OFF does not make it an ordinary application request. For the primary result, separately measure the normal client path, fetch/serialization/round trips, and concurrency. Compare plans with identical options/parameters/cache state.

## Plan context

Record data/parameter distribution, statistics freshness/ANALYZE policy, statistics snapshot, planner settings, version, and generic/custom prepared plan. Regenerating statistics only for the candidate invalidates the comparison. Do not attribute a plan change to a SQL rewrite without controlled state. Test common and rare parameters, not just one favorable tenant.

## Optimization directions

| Signal | Candidate | Required check |
|---|---|---|
| N+1 and many round trips | Join/batch/preload what is needed | Duplicates, NULL, permissions, cardinality, peak memory |
| Large table scan | Suitable composite/partial/expression/covering index | Plan, selectivity, index size, write/WAL cost |
| SELECT * / huge JSON | Needed columns, move filtering closer to the data | API schema, TOAST/IO, serializer cost |
| Large OFFSET | Keyset with a stable unique order | Ordering/NULL, concurrent changes, existing pagination contract |
| Spill/temp I/O | Reduce rows/sorting/aggregation, use the right index | work_mem per node × workers × sessions |
| Bloated storage | Diagnose tables/indexes/TOAST and lifecycle | Locks, vacuum/rewrite, replica/backup/migration safety |

An index is not free. Measure table+index size, insert/update/delete time/volume, WAL, and temporary migration space in PostgreSQL. Faster reads alone do not mean a system-wide gain. Add/remove indexes through a migration for review. Do not run it automatically on a working database. Even CONCURRENTLY has limitations and impact, and does not authorize production DDL.

For PG, compare `pg_table_size`, `pg_indexes_size`, and `pg_total_relation_size` for the exact version. The size of logical JSON or `pg_column_size` for one row does not replace the full footprint. SQLite page_count×page_size measures SQLite file pages, not PostgreSQL or WAL/backup size.

Do not narrow TEXT to small numeric/bit types without proven ranges, a NULL model, compatibility with old readers, a migration, and reversibility. A bitmask may worsen predicates/indexing. Saving space in the application does not prove that the SQL table uses less space because of overhead and compression.

Never disable RLS, constraints, fsync, synchronous_commit, validation, or isolation for speed. Do not change LIMIT/order/distinct/join semantics so that a “speedup” comes from skipping work.

Sources: [SUPABASE], [PG-EXPLAIN], [PG-SIZES], [PG-INDEX], [PG-TOAST], [PG-MEM], [PG-BITS].
