---
name: mutation-survivors
description: Explain every surviving smart-contract mutant using source diffs, reachability, executed tests, assertions and specification evidence; propose and replay justified test improvements in an isolated campaign worktree.
---

# Survivor analysis

Consume native and normalized inventories, current scope, original/mutated source, compiler artifacts, exact tests/logs and specification evidence. Return a mapping of **every native survivor ID** to an evidence-backed substantive group. Duplicate IDs must not vanish when grouping. Read [analysis.md](../mutation-campaign/references/analysis.md) and the coordinator's triage schema.

For each group establish: the code change; whether the code was reached; whether inputs/state activated a semantic difference; whether the difference propagated to an observable value/message/event/storage effect; which executed assertion could observe it. Inspect setup, cached BOC/bytecode, compiler flags, fork pin, reverts and runner errors. Separate test gaps, unreachable/dead code, equivalence/presumed equivalence, duplicate mutation, environment/instrumentation error and suspected original defect. State evidence paths/hashes and confidence. Unresolved is valid analysis but cannot justify verified completion.

Do not prescribe “add tests” solely because mutants survived. Equivalent means no relevant observable behavior distinguishes the versions; a plausible explanation alone is presumed equivalent. Scores do not establish correctness/security, and percentages across different operator/test populations are not additive.

Only after expected behavior is established from specs/current design evidence, add or improve tests inside the lane. Keep a before/after test diff, specification reference, passing original baseline and exact mutant rerun proving the new assertion kills it. Use `campaign.py retest` where a native source replacement is replayable. Do not change production targets to make tests pass. For a likely original bug prepare a reproducing test, consequences and a **separate proposed patch**, leaving the original checkout untouched for a human decision.

Submit triage JSON via `campaign.py triage <run> --file <json>`; the CLI requires a complete ID mapping and current evidence hashes. Ask the coordinator to obtain an independent verifier over the updated bundle.
