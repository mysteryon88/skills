# Interpret mutation evidence

Mutation testing asks whether the selected tests detect deliberate code changes. It diagnoses test sensitivity and missing behavioral checks. Fuzzing generates inputs; mutation generates program variants. They complement each other: ordinary, fuzz, invariant and fork tests can all be the oracle for the same variant. A perfect score over one operator population proves neither completeness nor security.

Reach the changed code, activate a semantic difference, propagate it to an observable effect, and assert that effect against intended behavior. Inspect the **actual** compiled bytecode/BOC and executed tests; a passing build with a stale artifact is no oracle. For TON include storage/cell/message layout, exit codes, value/fees, send modes, bounce flow and asynchronous message ordering. For EVM include authority, state transitions, amounts, boundaries, events, external calls, revert paths and fork assumptions.

## One disposition for every native survivor

Preserve the original ID even for duplicates. For each unique substantive group retain:

1. Original/mutated source, exact patch and source/compiler hashes.
2. Reachability and inputs/state: which test/handler/selector executed the site; useful successful transitions versus reverts/no-op calls.
3. Assertions and propagation: the observable value/message/state the changed behavior could affect, and whether a real executed assertion observes it.
4. Expected behavior from specification, protocol design, existing independently justified tests or a reproducible requirement. Ambiguous intent remains a limitation.
5. Environment, fork pin, compiler/tool errors, build cache and replay command; confidence and current evidence hashes.

Possible causes include inadequate inputs, absent/weak assertions, unreachable code under the selected scope, semantic equivalence, duplicate patches, configuration/instrumentation errors, test flakiness, or a defect in the original contract. All-survive calibration first requires checking mutated wiring and test execution. “Add tests because all survived” is not an analysis.

Equivalence is generally undecidable. Same complete bytecode/BOC under pinned compiler/configuration is strong evidence **for that artifact/scope**; it is not proof for arbitrary future compilation or code. A plausible semantic argument with incomplete reachability is `presumed_equivalent`. Do not silently remove such mutants from raw native scores. Distinguish equivalent code from a duplicate mutant: duplicates can still be behavior-changing.

## Counts and scores

Keep `killed`, `survived`, `invalid`/non-compiling, `timed_out`, `skipped`, `equivalent`, `presumed_equivalent`, and `tool_error` separate. A compiler failure, missing executable or runner crash is not an assertion kill. Native inventories/IDs/counts must reconcile; unknown schemas and partial output block a completion claim. Native survivors remain raw survivors even after an analytical equivalence disposition; report disposition counts alongside them.

| Route | Native quantity | Controller interpretation |
|---|---|---|
| Foundry MVP | `mutation_score`, documented K/(K+S); total includes invalid/skipped/timeouts | Keep all raw categories; native JSON exposes all survivor spans but not all killed IDs. Internal span de-duplication can change skipped counts with scheduling. |
| Mewt 4 / MuTON 3.0.1 | Native per-target `100 * TestFail / all outcomes except Skipped`; reconstruct from complete JSON outcome rows because JSON omits the aggregate. Compile errors/timeouts remain in this native denominator. | Keep raw native TestFail distinct from evidence-classified behavioral kills; report this tool score separately from behavior-only K/(K+S). Join IDs with actually applied-source oracle hashes. |
| Slither Mutate | Per-category **uncaught / compiling** candidates (lower is better) | Invert only for the same observed population if useful. Reconcile all evaluated changed-source probes; generator skips are not a complete exposed inventory. |
| Acton | `100 * killed / (killed + survived)`; compile failures and timeouts excluded for verified commit `0ac9ebcd9` | Preserve exact session counts and bind the formula to that inspected source revision; recheck other revisions. [Source](https://github.com/ton-blockchain/acton/blob/0ac9ebcd9/src/commands/test/mutation/session.rs#L304) |
| UM | Legacy analyzer K/processed where any nonzero command may count as K | Campaign uses generation only, independent build/test classification and K/(K+S). Invalid and timed-out outcomes remain separate. |

The controller's optional `behavior_score` is K/(K+S) **within one tool and selected tests only**. Populations/operators, sampling, test sets, compiler rules and equivalent handling differ; never sum incompatible tool percentages. Completion requires calibrated finished selected runs, every survivor accounted and every proposed test improvement checked, not 100%.

The source review records local theory evidence, including the Jia–Harman survey's exclusion of non-equivalent mutants from the ideal denominator and undecidability limitation. Historical notes counting non-compiling variants as kills and claiming 100% proves security are deliberately not adopted.
