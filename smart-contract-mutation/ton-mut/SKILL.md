---
name: ton-mut
description: Execute and interpret TON mutation testing for Tact, Tolk and FunC using MuTON, Acton and capability-confirmed Universal Mutator, with real compiled-contract execution and survivor evidence.
---

# TON mutation execution

Consume the coordinator's frozen targets/specifications, tool version/help and assigned Git worktree. Return native inventory, real changed source/BOC or native execution receipts, exact tests/assertions, all outcomes and every survivor ID.

- **MuTON:** grammar-backed Tact/Tolk/FunC. Verify `run --help`; use selected targets, `--test.cmd <oracle>`, `--test.timeout`, private `--db`, explicit operators and `--comprehensive`. `muton results --all --format json` is the results command; do not invent `muton print results`. Reconcile the `mutants` table/IDs with outcomes so unfinished records cannot disappear. MuTON 3.0.1 pins Mewt 3.0.1; native per-target score is `100 * TestFail / all outcomes except Skipped`, including compile failures/timeouts. The controller reconstructs it from reconciled JSON rows, while behavior-only K/(K+S) remains separate. Do not equate native TestFail with a useful test kill without checking compile and assertion output.
- **Acton:** for configured Tolk contracts and native `.test.tolk` tests, use `acton test --mutate --mutate-contract <configured-name> --mutation-workers N --mutation-timeout S --no-studio-reporting` after help verification. Tests must construct the contract through its configured wrapper/build route; direct source compilation can bypass instrumentation. Preserve complete `build/mutation-sessions/*.jsonl`, final counts and per-mutant records. Missing `session_finished` is incomplete. Native code/cache instrumentation must be calibrated with an applied source canary and a native mutation.
- **Universal Mutator:** confirm the actual installed `tact.rules`, `tolk.rules`, `func.rules` and selected common layers, not a different Python environment. Use the sibling skill for optional custom rule syntax. The campaign controller compiles every generation-only candidate and executes local TVM tests; it does not count build failures as kills.

Before full execution prove tests rebuild the changed contract, wrappers load that BOC and the asserted getter/message/storage effect differs. If all mutants survive, inspect build dependencies, generated wrappers, executed test count and logs before proposing new assertions. Keep serialization, opcodes, send modes, bounced messages, ownership, arithmetic and storage transitions in scope where relevant; do not import EVM assumptions into TON.

Survivors such as `lazy`/`impure` removal or disjoint flag rewrites can be equivalent, compile noise or meaningful behavior changes depending on context. Inspect each concrete diff and observable semantics. Use `$mutation-survivors`; never infer equivalence from a name. TON forks need full masterchain identity and a TON client, as in [forks](../mutation-campaign/references/forks.md). No public sends or deployment.
