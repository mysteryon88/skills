# Measurements and the decision to keep a change

## Contract before a round

Record one primary metric, a practical improvement threshold, and guardrails. For speed, RAM, and storage, state what was measured, what was unaffected and why, and what was not checked. An unmeasured material risk is not zero. If the user did not set budgets, explicitly propose working values. A 5% time example is not a universal standard.

Measurements are distinct:
- wall time, CPU time, throughput, and tail latency answer different questions.
- allocated bytes/operation, allocation count, live heap, and peak RSS are not interchangeable.
- logical data, serialized payload, a table with indexes/TOAST, a compressed network response, final binary, and build cache have different boundaries.

Do not call a decrease in alloc/op a RAM saving without measuring the corresponding memory. For a RAM goal, use process and runtime metrics, including peak/steady state, workload duration, and concurrency. In a container, account for cgroup limits and external process memory. Isolate profiler measurements from the control run, or the profiler's cost is included.

## Reproducibility

Record source hashes/commit, toolchain+implementation, flags/profile/features, hardware/OS, limits, workload/dataset/seed, size/density/skew, cache state, concurrency, commands, and timer boundaries. Do not save secret env values. Record only sanitized relevant settings.

Use one host and sequential adjacent A/B pairs, then B/A pairs. Keep warmup, useful work, and setup identical. Builds/external load must not run during measurement. Preserve all raw samples. Exclude a sample only for a recorded objective event, not because its delta is inconvenient.

Do not compare debug with release, a profiled build with a normal build, or an old historical report with a current run. Optimizing compiler flags is a separate hypothesis and requires approval for semantic changes. Also check correctness under the profile for which the improvement is claimed.

## Statistics without false confidence

The perfkit helper requires at least 10 pairs for sampled metrics and calculates the median of paired relative changes with an exploratory bootstrap interval. This is only a screen for gross errors, not full evidence of significance. It does not check stationarity, independence, actual run order, log accuracy, or data representativeness.

Before final acceptance, preserve the predefined threshold, number/budget of attempts, and stopping criterion. Check trends by run order, the AB/BA difference, and dependence between adjacent samples. Repeated operations in one warmed process are not independent runs. For a final improvement claim, run a new confirmation series after choosing the candidate. Do not select only its best values. For multiple hypotheses, account for selection bias. Use a holdout series and domain-specific tools instead of tuning indefinitely until a “significant” result appears.

Go: use benchstat with a sufficient number of runs. Rust: use the existing Criterion/another validated harness. Small effects require stricter conditions. Report effect size, interval/spread, and limitations separately. Request p95/p99 cannot be derived from ten average batch timings. Tail measurements require individual events, a sufficient sample, and realistic load that does not hide queues.

An exact count of serialized bytes can use one measurement when format and data are fixed. The allocation size of a useful array is not the process's physical memory. A zero baseline requires an absolute, not relative, target.

## Full lifecycle

Measure setup and steady state separately, then end to end: lookup map creation, bit packing, unpacking, cache load/invalidation, SQL index creation/maintenance, and write cost. For Q repetitions, estimate setup + Q × operation. Do not move an expensive part outside the timer only for the candidate.

The test set should include small/typical/large inputs, empty values, maximum width, high/low density, skew, cache miss/hit, updates/deletions, and errors. Justify inapplicable scenarios. Preserve ordering/duplicates/precision and byte compatibility when they are contractual.

## Decision

Keep: correctness + material repeatable effect + guardrails + independent confirmation series + diff review. Revert: confirmed regression or increased complexity without a gain. Inconclusive: noise/insufficient data. Blocked: unsafe environment, missing required check, or unknown behavior.

The helper's `measured_win` does not replace the agent's decision. It does not know about omitted metrics and SLAs. If CPU use improves but memory use increases, treat that as a separately agreed trade-off. Do not combine everything into one “optimization score.”

Sources: [GO-DIAG], [GO-GC], [BENCHSTAT], [RUST-PROFILES], [REACT-PROFILER], [PG-EXPLAIN], [FORY], [CODSPEED] in ../SOURCES.json. These are this package's acceptance rules, not a verbatim copy of one source.
