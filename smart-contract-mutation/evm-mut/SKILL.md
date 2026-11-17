---
name: evm-mut
description: Execute and interpret Solidity mutation testing with native Foundry, Slither Mutate, Mewt and capability-confirmed Universal Mutator. Use for EVM test-quality campaigns and survivor analysis; additional EVM tools are cataloged with their verification limits.
---

# EVM mutation execution

Use the coordinator's frozen scope and assigned worktree. Consume exact test/specification/tool evidence and return native artifacts, changed-source receipts, reconciled outcomes and all survivor IDs. Do not choose models or depend on another orchestration product.

- **Foundry first:** probe `forge test --help` for `--mutate`, `--mutation-jobs`, `--mutation-timeout`; inspect MVP configuration restrictions. Run baseline and changed-source canary, then a small native generation. Prefer `forge test --mutate <selected.sol> --json` with explicit worker/timeout caps. Native exit zero can contain survivors. Keep killed/survived/invalid/skipped/timed_out separate; score is K/(K+S). Skipped spans are not tested kills.
- **Slither Mutate:** `slither-mutate <source> --test-cmd <oracle> --output-dir <private-output>`. Freeze selected mutators and compiler path. The runner supplies a compile/test/source-capture oracle. Slither may delete its output directory and rewrite source line endings; byte-exact restoration and oracle/native-count reconciliation are mandatory. Human-only inventories limit completeness claims.
- **Mewt:** `mewt run <targets> --test.cmd <oracle> --test.timeout <seconds> --db <private.sqlite> --comprehensive`; collect `results --all --format json` and reconcile every DB mutant ID, including pending ones. The native per-target score is `100 * TestFail / all outcomes except Skipped` and includes compile failures/timeouts; JSON omits it, so the controller reconstructs it from reconciled rows. Preserve native `TestFail` separately when evidence reclassifies a runner error; only assertion-backed failures count as behavioral kills. Current v4 Linux-only release uses existing WSL on Windows.
- **Universal Mutator:** verify language/rule support in the actual installed environment. The controller uses generation-only `--noCheck`, then independently compiles/tests every generated source; a compilation error never becomes a behavioral kill. This differs from the native analyzer's exit-code-based score. Use the sibling skill for rules and source-specific operator guidance.

Run ordinary tests, fuzz, invariants and fork tests selected by scope. Preserve deterministic seeds, failure/corpus directories and traces. Coverage proves reachability, not assertion quality. Check successful state transitions and reverts before crediting invariants; save reproducible shrunk sequences. See [Foundry verification](../mutation-campaign/references/foundry.md) and [catalog](../mutation-campaign/references/tool-catalog.md).

Add Gambit/Vertigo-rs/SuMo only for evidenced incremental value and verified project compatibility; they are not automatic executable routes here. Do not silently replace an explicit fork block or send public transactions. Analyze survivors with `$mutation-survivors`; a suspected production defect is a separate proposal.
