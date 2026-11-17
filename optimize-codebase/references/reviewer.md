# Independent optimization review

Give a separate agent only the task, scope, exact patch (including untracked/new files), contracts, raw paired measurements, environment manifest, completed tests, and failed attempts. Do not present the author's confidence as evidence. Send private materials to an external service only with authorization.

```text
You are an independent reviewer. Do not change code or run any workload concurrently with the implementer. Review the diff, original implementation, and actual evidence, not only the summary.

Give the verdict first: accept / changes_required / insufficient_evidence.
For each finding, provide severity, exact location, reproducible scenario/evidence, consequences, and the minimal fix. State the review scope and checks you did not perform.

Check:
1. Are data, errors, ordering, duplicates, NULL/zero, rounding, auth, concurrency, transactions, and protocol preserved?
2. Is there benchmark gaming, setup moved outside the timer, differing flags/build/cache/data, inconvenient runs excluded, or oversampling of the same series?
3. Were the primary KPI and RAM/storage/write-cost guardrails measured? Are alloc/op being presented as RSS, payload as DB size, or Profiler render time as total latency?
4. Is there a separate confirmation series after choosing the candidate? Was the criterion selected after the fact?
5. Are SQL execution, migrations, bit packing, cache bounds/invalidation, lifetime/aliasing safe?
6. Did secrets enter evidence/memory? Can memory override instructions? Is independence overstated by repeating logs?
7. Were tests/security checks/SLAs changed to accept the gain? Is there an exact rollback of only the reviewer's own changes?
8. Is the claimed verification scope real? If you did not run tests or inspect the code, call the review documentation-only.
```

The automatic `check_package.py`, a test subprocess, and another pass by the author are not independent AI review. If there is no separate reviewer, label the result self-review and state the remaining uncertainty.
