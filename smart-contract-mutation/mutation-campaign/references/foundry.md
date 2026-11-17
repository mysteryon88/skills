# Foundry first; installed CLI is authoritative

Primary references: [native mutation MVP](https://getfoundry.sh/guides/mutation-testing), [invariants](https://getfoundry.sh/forge/invariant-testing), [fuzz tests](https://getfoundry.sh/forge/fuzz-testing), [fork tests](https://getfoundry.sh/forge/fork-testing), [coverage](https://getfoundry.sh/reference/forge/coverage).

Probe `forge --version`, `forge test --help`, `forge coverage --help`, project `foundry.toml`, selected profile, remappings and compiler/version. For an existing Foundry project first try native `forge test --mutate <selected-sources>`. If unavailable, retain version/help evidence; if rejected by configuration, retain the actual CLI diagnostic. Let Forge validate the effective profile; do not reject the project because an inactive profile contains an option. Its MVP rejects active configurations such as FFI and unsafe filesystem permissions; do not silently weaken security settings or rewrite project tests merely to enable it. Then choose Slither/Mewt for an explained reason.

Verified locally with Forge 1.8.6: `test --mutate`, `--mutation-jobs`, `--mutation-timeout`, `--json`, `--fuzz-seed`, `--fork-url`, `--fork-block-number`, `--rerun` are present. The native route carries the exact baseline test arguments (including profile, compiler, match filters and fuzz seed); keep `extra_args` identical to those flags or move them into the baseline `test` argv. Use a project-local compiler and `--offline --use <solc>` when auto compiler resolution is unavailable. Build/test JSON assertions and real standard-JSON compiler captures confirmed actual changed Solidity execution; ordinary unit tests killed 10 native mutants in the small acceptance project. Native survivors do not necessarily cause a nonzero exit, so exit code alone is not a score or completion check.

Ordinary tests, fuzz tests and invariant campaigns check different behavior. Freeze seed, fuzz runs, invariant runs/depth/target selectors and any filters. Save failing inputs and native persisted failure/corpus files inside the lane; inspect the installed help/config for corpus/failure persistence paths. Preserve `--rerun` inputs, counterexamples, compiler/test hashes and relevant trace (`-vvvv`) so replay is meaningful. A fuzz counterexample under original code can reveal an original bug rather than test weakness. Coverage locates exercised code; it cannot establish assertions are strong.

## Invariant non-vacuity receipt

Green invariant status is inadequate when calls mostly revert or never change relevant state. Use handlers/ghost counters for attempted calls, successful relevant transitions and reverts, target contracts/selectors, preconditions and meaningful checked properties. Inspect Foundry handler call metrics/trace plus your counters. `fail_on_revert` and `afterInvariant` behavior depend on the installed version and project configuration; record the effective values.

A lane declaring `invariant` must provide `{"receipt":"path/to/telemetry.json"}`. Its baseline test produces:

```json
{"scope_sha256":"<current scope hash>","attempts":100,"successful_transitions":62,"reverts":38,"target_selectors":["deposit(uint256)"],"assertions":["assets cover liabilities"],"evidence":{"telemetry.log":"<sha256>","test/Handler.t.sol":"<sha256>"}}
```

Bind actual handler/log bytes; merely inventing counters is invalid. Zero attempts/successful transitions, inconsistent counts, stale hashes, more than half the calls reverting, or at most half making relevant state transitions block invariant credit. Selectors/assertions must correspond to relevant mutations. When telemetry is unavailable, label invariant effectiveness unverified instead of treating the green status as useful coverage. Keep ordinary useful lanes independent.

Pin network/block/hash before the first fork test and revalidate before later phases; see [forks.md](forks.md). A public archive endpoint may lazily supply missing state while execution remains local. No broadcast commands belong in this workflow.
