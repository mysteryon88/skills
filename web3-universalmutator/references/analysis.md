# Result Analysis

## Contents

- [Start With The Right Artifacts](#start-with-the-right-artifacts)
- [Required `mutants/REPORT.md`](#required-mutantsreportmd)
- [Triage Meanings](#triage-meanings)
- [Group Results Before Recommending Changes](#group-results-before-recommending-changes)
- [Canonical Final Output](#canonical-final-output)
- [How To Fill The Canonical Output](#how-to-fill-the-canonical-output)
- [Decide What Is Good Versus Bad Signal](#decide-what-is-good-versus-bad-signal)
- [Practical TON Interpretation Guide](#practical-ton-interpretation-guide)
- [Multi-Target Summary Template](#multi-target-summary-template)

Use this file after mutation generation or `analyze_mutants`. The goal is to turn raw mutant outcomes into a clear report and concrete next actions. Use `scripts/collect_mutation_artifacts.py` to inventory artifacts and `scripts/summarize_results.py` when you want the canonical report scaffold before deeper reasoning.

## Start With The Right Artifacts

Prefer documented artifacts first:

- `killed.txt` or `<prefix>.killed.txt`
- `not-killed.txt` or `<prefix>.notkilled.txt`
- `show_mutants` output for surviving mutants
- shell logs from stdout and stderr

When available, also review any local runner output that indicates timeouts, compile failures, or reruns. The supplied docs explicitly document killed and not-killed lists; other categories should be reported carefully and not assigned undocumented file-name conventions.

## Required `mutants/REPORT.md`

Every real mutation campaign must maintain `mutants/REPORT.md`.

Create or update it immediately after mutation generation, before analysis, with:

- requested scope, executed scope, and completeness label
- entrypoints mutated or planned
- Shared dependency files observed but not mutated by default
- target file or contract
- exact `mutate` command used
- mutant directory
- total mutants generated
- non-compiling mutants or compile-check failures, even if the count is `unknown`
- any fallback compile command used

Update `mutants/REPORT.md` after analysis with:

- exact `analyze_mutants` command used
- killed, survived, timeout, compile-error, and flaky counts
- mutation score when the known categories support it
- survivor clusters and likely missing assertions
- recommended tests and next commands

Mutation analysis can take a long time because the selected test command may run once per mutant. Tell the user before a long analyze run starts, keep stdout/stderr logs, and update `mutants/REPORT.md` with partial status if the process stalls, times out, or needs a rerun.

When artifacts exist, scaffold or refresh the report with:

```sh
python scripts/summarize_results.py . --prefix <prefix> --output mutants/REPORT.md
```

## Triage Meanings

### Killed mutants

Good signal. The tests or verification command detected the behavioral change.

### Survived mutants

Highest-value review target. Usually means the tests did not observe an important behavioral difference, or that the mutant is equivalent or low-value.

### Timeout mutants

Treat as inconclusive first. Possible meanings:

- tests are too slow or hang under mutation
- the mutant triggered an especially expensive path
- the timeout setting is too aggressive for the chosen command

### Compile-error mutants

Possible meanings:

- the mutation is invalid for the real build context
- the compile-check or test command does not match how the project builds
- the target file should have been mutated through a different entrypoint or `--cmd` override

### Equivalent mutants

Treat as plausible when the mutation changes syntax without changing observable behavior. Do not call a mutant equivalent casually; first inspect it with `show_mutants` and try to define a stronger assertion that would kill it.

### Flaky results

Suspect flakiness when re-runs disagree or when unrelated failures dominate the logs. Re-run the same target or prioritized subset before making broad claims.

### Noisy tests

Treat tests as noisy when they fail for infrastructure reasons more often than because of the mutant. Improve determinism before reading deep coverage meaning into the results.

### Slow mutations

If many mutants are slow but not interesting, narrow the test command, prioritize survivors, or split the work into isolated per-target runs.

## Group Results Before Recommending Changes

Group by:

- contract or source file
- mutation operator or pattern, if visible in mutant names or diffs
- originating rule file or family, when the run used locally verified options such as `--showRules` or `--printStat`
- outcome class: killed, survived, timeout, compile-error, flaky
- feature or behavior area: deploy, transfer, auth, storage, math, parser, wrapper, message flow

This grouping is more actionable than a flat list of mutant IDs.

## Canonical Final Output

Use this exact section order in the final user-facing report so output stays stable across TON and EVM repositories:

```text
Target:
<mutated file, contract, or run prefix>

Scope:
- Requested: <user path, contract, or directory>
- Executed: <single-entrypoint-contract|entrypoint-contracts|single-source-file>
- Completeness: <single-target|entrypoint-focused-not-full-directory|target-file-only>
- Entrypoints mutated/planned: <entrypoint files>
- Shared dependency files observed but not mutated by default: <shared files or none>

Commands:
- <mutate command>
- <analyze_mutants command>
- <show_mutants or prioritize_mutants command, if used>

Results:
- Killed: <count>
- Survived: <count>
- Timeout: <count or unknown>
- Compile-error: <count or unknown>
- Mutation score: <value if available>

Survivors:
- <mutant or survivor cluster>

Likely gaps:
- <why the current tests probably missed the mutation>

Recommended tests:
- <specific assertion, negative test, edge-case, or TON-specific coverage addition>

Next commands:
- <next show_mutants or prioritize_mutants command>
```

The bundled `scripts/summarize_results.py` emits this structure automatically for a collected run.
It checks local Universal Mutator capabilities before printing concrete next commands. If command flags are not confirmed, treat the printed next command as a template or rerun `scripts/detect_um_capabilities.py` first.

## How To Fill The Canonical Output

### Target

Record:

- the mutated file or contract
- the language or contract type
- whether the run used TON/Blueprint/Acton flow or EVM/Foundry/Hardhat/Truffle/source-level flow

### Scope

Record what was requested separately from what was executed. If the user requested a directory but the campaign mutated only entrypoint contracts, say so directly and use `entrypoint-focused-not-full-directory`.

Do not describe an entrypoint-focused campaign as full directory coverage. List shared dependencies such as `messages`, `storage`, `errors`, `fees`, `constants`, `utils`, libraries, interfaces, and include files under "Shared dependency files observed but not mutated by default".

Only call the campaign full directory coverage if every supported source file in the requested directory was intentionally mutated and analyzed.

### Commands

List the exact commands so the user can reproduce the run:

Before copying TON examples below, verify TON language support and every optional flag with `scripts/detect_um_capabilities.py` or local `--help` output.

```sh
mutate contracts/contract.tact tact --cmd "npx blueprint build --all" --mutantDir mutants
analyze_mutants contracts/contract.tact "npx blueprint test" --mutantDir mutants --prefix tact
show_mutants tact.notkilled.txt --mutantDir mutants --sourceDir contracts --concise
```

If several terminals or agents were used, keep the command list grouped by target rather than flattening everything into one block.

### Results

State the overall signal:

- whether the run completed cleanly
- whether survivors are concentrated or widespread
- whether the main blocker is test quality, build configuration, or runtime cost

If the tool or shell artifacts give clean counts, report them. When only killed and surviving counts are clear, compute a simple ratio from those categories and keep timeout or compile-error counts separate instead of hiding them inside the score.

Do not claim that a high mutation score proves contract or application security. It only measures how sensitively the current tests react to injected source changes.

### Survivors

For each surviving cluster, explain:

- what changed
- why the current tests probably missed it
- whether it looks killable with a stronger assertion
- whether it might be equivalent

Always prefer `show_mutants` output over guessing from filenames.

### Likely Gaps

Translate survivors into test gaps:

- missing assertion after a state change
- missing negative test
- missing boundary condition
- missing integration path
- missing wrapper-level or CLI-level assertion

### Recommended Tests

Recommend concrete changes, not generic advice:

- add a negative test for a rejected sender
- assert storage after message processing
- validate emitted side effects after deploy
- add a boundary-value test for fee or balance logic
- split noisy integration tests from deterministic contract checks

When the project is TON, call out:

- missing message or opcode coverage
- weak storage or balance assertions
- missing deploy or init verification
- absent sender, ownership, or permission checks
- untested cross-contract flows

### Next Commands

Use documented commands first:

Treat the next-command examples below as templates until local `show_mutants`, `prioritize_mutants`, and `analyze_mutants` flags are confirmed.

```sh
show_mutants tact.notkilled.txt --mutantDir mutants --sourceDir contracts --concise
prioritize_mutants tact.notkilled.txt prioritized.txt 20 --mutantDir mutants --sourceDir contracts
analyze_mutants contracts/contract.tact "npx blueprint test" --mutantDir mutants --fromFile prioritized.txt --prefix prioritized
```

## Decide What Is Good Versus Bad Signal

Good signal:

- most mutants are killed by fast, deterministic tests
- survivors cluster into a few understandable gaps
- build and test commands match real project behavior

Bad signal:

- many survivors with no clear theme
- frequent compile failures caused by the chosen build command
- repeated timeouts or flaky reruns
- results that cannot be tied back to the actual contract or source behavior

## Practical TON Interpretation Guide

For TON repositories, surviving mutants often indicate one of these gaps:

- the test sends a message but does not assert the full resulting state
- the suite checks the happy path but not a rejected or bounced path
- init or deploy setup is assumed rather than verified
- wrapper calls succeed, but low-level opcode or payload expectations are not asserted
- multi-step flows are tested only at one checkpoint

Frame recommendations around those behaviors instead of around the mutation tool alone.

When the TON contract class is clear, use [ton-contract-checklists.md](ton-contract-checklists.md) to turn survivors into more specific test ideas.

## Multi-Target Summary Template

Use this when several terminals or agents reported back independently:

```markdown
# Mutation Testing Summary

## Targets tested

| Target | Status | Mutant dir | Log files | Main finding |
|---|---|---|---|---|

## Cross-target findings

## Surviving mutants by priority

## TON-specific findings

## Recommended next actions
```
