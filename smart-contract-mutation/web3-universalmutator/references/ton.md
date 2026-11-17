# TON, Blueprint, And Acton Workflows

## Contents

- [Rule Awareness](#rule-awareness)
- [Cross-Platform Note](#cross-platform-note)
- [Windows / PowerShell Quoting](#windows--powershell-quoting)
- [Helper Scripts](#helper-scripts)
- [Detect TON Quickly](#detect-ton-quickly)
- [Detect Acton](#detect-acton)
- [Detect Blueprint](#detect-blueprint)
- [Verify TON Support Before Using TON Commands](#verify-ton-support-before-using-ton-commands)
- [Bundled TON Language Support](#bundled-ton-language-support)
- [Bundled Compile-Check Controls](#bundled-compile-check-controls)
- [Built-In TON Handler Model](#built-in-ton-handler-model)
- [Minimal TON Workflow](#minimal-ton-workflow)
- [Useful TON Mutation Flags](#useful-ton-mutation-flags)
- [Map Contracts, Wrappers, And Tests](#map-contracts-wrappers-and-tests)
- [Generated Output Visibility](#generated-output-visibility)
- [Choose Commands For TON Projects](#choose-commands-for-ton-projects)
- [Use Environment Variables](#use-environment-variables)
- [Run One Contract Versus Many](#run-one-contract-versus-many)
- [Choose Full Test Command Versus Narrow Command](#choose-full-test-command-versus-narrow-command)
- [When TON Compilation Is Expensive](#when-ton-compilation-is-expensive)
- [Coverage-Guided TON Triage](#coverage-guided-ton-triage)
- [Parallelize Different Contracts](#parallelize-different-contracts)
- [Interpret Surviving TON Mutants](#interpret-surviving-ton-mutants)
- [Runtime Details Worth Knowing](#runtime-details-worth-knowing)

Use the general CLI reference for all projects; use this TON reference when the repository appears to be TON, Acton, Blueprint, FunC, Tolk, Tact, or a TypeScript-based TON wrapper project.

Before writing commands, keep three extra references nearby:

- [command-templates.md](command-templates.md) for smoke, full-run, rerun, and timeout-triage scaffolds
- [troubleshooting.md](troubleshooting.md) when TON support, compile commands, or Blueprint or Acton tests are unstable
- [ton-contract-checklists.md](ton-contract-checklists.md) when a survivor needs contract-type-specific test ideas

When local capability is unknown, phrase commands as templates, not facts: “If your installed `mutate --help` confirms `<flag/language>`, use... Otherwise first verify or install the TON-enabled build.”

## Rule Awareness

Read [mutation-rules.md](mutation-rules.md) when the task is about which TON mutation families exist, which default rule stack is loaded, or whether a survivor came from `ton_common.rules` versus the language-specific layer.

Core model:

- Tact default stack: `ton_common.rules` + `tact.rules`
- FunC default stack: `ton_common.rules` + `func.rules`
- Tolk default stack: `ton_common.rules` + `tolk.rules`
- `--comby` keeps the same stack names but uses the files from `universalmutator/comby/`

For this skill, treat [mutation-rules.md](mutation-rules.md) as the self-contained rule summary. If you need a more exact per-run inventory, use `mutate --showRules` or `--printStat` when those flags are available in the installed environment.

## Cross-Platform Note

Universal Mutator workflows can be run on both Windows and Linux. Use PowerShell syntax on Windows and POSIX shell syntax on Linux or macOS. Treat `--comby` as a Linux or WSL workflow on Windows because the external `comby` binary should not be assumed to be available natively there.

## Windows / PowerShell Quoting

On PowerShell, prefer storing complex analyze commands in variables:

```powershell
$cmd = 'yarn build:base && npx jest --runInBand src/tests/base -t "Base Jetton"'
analyze_mutants "src\contracts\base\jetton-minter.tact" $cmd --mutantDir "mutants" --prefix "base-minter"
```

Avoid single quotes inside commands that will be executed by `cmd.exe`. Prefer double quotes inside the command string only where the nested test runner requires them. For complex commands, keep paths quoted and avoid shell-specific escaping unless verified locally.

`cmd.exe` escaping for nested test-runner quotes is more fragile than the PowerShell variable form. Use this only after local verification:

```cmd
analyze_mutants "src\contracts\base\jetton-minter.tact" "yarn build:base && npx jest --runInBand src/tests/base -t \"Base Jetton\"" --mutantDir "mutants" --prefix "base-minter"
```

## Helper Scripts

Use the bundled helper scripts when you want a faster first pass before manual reasoning:

- `scripts/detect_project.py` to confirm that the layout really looks like `ton`, `acton-ton`, or `blueprint-ton`
- `scripts/collect_mutation_artifacts.py` to group per-contract artifacts after several runs
- `scripts/summarize_results.py` to produce the canonical report shape from [analysis.md](analysis.md)

## Detect TON Quickly

Strong practical signals:

- `contracts/` contains `.tact`, `.tolk`, `.fc`, or `.func`
- `contracts/src/` exists alongside `Acton.toml`
- `wrappers/` contains TypeScript wrapper files for contracts
- `tests/` contains `.spec.ts`, `.test.tolk`, or other contract tests
- `blueprint.config.*` exists
- `Acton.toml` exists
- `package.json` contains Blueprint, Jest, or TON-related scripts
- `jest.config.*` exists
- `tsconfig.json` exists in a wrapper-and-test project

Useful secondary signals:

- contract names repeated across `contracts/`, `wrappers/`, and `tests/`
- scripts invoking `acton build`, `acton test`, `npx blueprint build`, `npx blueprint test`, `jest`, `func-js`, `tact`, or `tolk`

## Detect Acton

Treat these as strong Acton signals:

- `Acton.toml`
- `contracts/src/` with `.tolk` contracts
- `tests/*.test.tolk`
- `wrappers/*.gen.tolk` or `wrappers-ts/*.ts`
- scripts or docs invoking `acton build` or `acton test`

If those exist together, prefer direct `acton build` and `acton test` commands over broader package scripts so mutation runs stay focused on the contract toolchain.

## Detect Blueprint

Treat these as strong Blueprint signals:

- `blueprint.config.*`
- `package.json` scripts calling `blueprint`
- the common layout `contracts/`, `wrappers/`, `tests/`

If those exist together, prefer Blueprint-oriented compile and test commands first.

## Verify TON Support Before Using TON Commands

Do not assume the installed public package supports TON just because this repository source does.

Verify one of:

- `mutate --help` lists `tact`, `tolk`, or `func`
- the installed package contains `static/tact.rules`, `static/tolk.rules`, or `static/func.rules`
- the user explicitly says they are using a TON-enabled fork or build

If support is not verified, keep the discussion at workflow-design level instead of claiming the commands will run as written.

## Bundled TON Language Support

The bundled repository source supports:

- `Tolk` for `.tolk`
- `Tact` for `.tact`
- `FunC` for `.fc` and `.func`

Treat that as repository-level evidence, not automatic proof about the installed CLI in the user's environment.

## Bundled Compile-Check Controls

The bundled TON baseline supports two main ways to provide the compile-check command:

- `--cmd "<command>"` for one `mutate` run
- `UM_TACT_CMD`, `UM_TOLK_CMD`, `UM_FUNC_CMD` as defaults for the current shell session

Treat those environment-variable patterns as repository-level or fork-level guidance, not guaranteed public-PyPI behavior. Do not state that they work unless local verification or a user-confirmed TON-enabled build supports them.

## Built-In TON Handler Model

The current repository source also confirms these built-in TON compile-check defaults:

- Tact handler default: `tact --check MUTANT`
- Tolk handler default: `npx -y @ton/tolk-js --output-json /tmp/tolk-out.json MUTANT`
- FunC handler default: `npx -y @ton-community/func-js MUTANT --fift /tmp/func-out.fif`

Practical implications:

- the handlers run from the source file directory so relative imports and includes keep working
- `VALID` for TON means only that the compile command exited with code `0`
- the TON handlers do not do bytecode-level equivalence or deep artifact deduplication the way a dedicated smart-contract backend might

Treat TON mutation generation as a compile-valid mutation pipeline first, then use `show_mutants`, `prioritize_mutants`, `prune_mutants`, `check_covered`, and `analyze_mutants` to reduce noise and focus on the interesting survivors

## Minimal TON Workflow

Template once local TON support is verified:

```sh
mutate <sourcefile> <tact|tolk|func> --mutantDir mutants

analyze_mutants <sourcefile> "<test command>" --mutantDir mutants --prefix run

show_mutants run.notkilled.txt --mutantDir mutants --sourceDir <source_dir> --concise
```

Otherwise first verify or install the TON-enabled build. Load [analysis.md](analysis.md) after the first `show_mutants` pass.

Optional default-plus-custom TON rules, after the user accepts custom rule generation:

```sh
mutate <sourcefile> <language> <custom.rules> --mutantDir <dir>
mutate <sourcefile> <language> rules/access.rules rules/serialization.rules --mutantDir <dir>
mutate contracts/Wallet.tolk tolk mutants/custom-rules/contracts-Wallet-tolk.rules --mutantDir mutants/contracts-Wallet-tolk
```

Use `--showRules` to check whether default or custom rules fired when local help confirms the flag. Use `--only <custom.rules>` only when the user wants to replace the default stack with the custom file, and only after local `mutate --help` confirms `--only`.

## Useful TON Mutation Flags

Use these when the default one-file mutate pass is too noisy or too broad:

- `--mutantDir <dir>`: always set this explicitly per contract
- `--cmd "<command>"`: override the compile-check for one run
- `--comby`: use structural mutation when regex output is too noisy; treat this as Linux or WSL on Windows
- `--only <rule>`: restrict mutation to one rule file such as `tact.rules` or `ton_common.rules`
- `--showRules`: print which rule produced each mutant
- `--printStat`: write rule and mutant statistics files
- `--ignore <file>`: skip lines matching listed regex patterns
- `--lines <coverfile>`: mutate only the covered or explicitly selected line numbers
- `--noCheck`: generate mutants without compile filtering
- `--noFastCheck`: disable the fast heuristic dead-code filter when you need the broader raw mutant set

Treat `--noCheck` as a last resort. It can create a much larger, noisier mutant set for TON projects.

Less useful for TON:

- `--compile` is described for Solidity-style consumer-file checking; prefer `UM_TACT_CMD`, `UM_TOLK_CMD`, `UM_FUNC_CMD`, or `--cmd` for TON repositories

Verification note:

- `--timeout`, `--fromFile`, and `--noShuffle` belong to `analyze_mutants`, not `mutate`
- confirm them with `analyze_mutants --help` before using them in a real command

## Map Contracts, Wrappers, And Tests

Use this practical mapping order:

1. Start from the contract file in `contracts/`.
2. Look for a same-name or closely related wrapper in `wrappers/`.
3. Look for a same-name or behavior-focused test in `tests/`.
4. Check `package.json` scripts for the actual test entrypoint.
5. If names do not match cleanly, prefer the project script over filename guessing.

Common heuristic:

- `contracts/JettonMinter.tact`
- `wrappers/JettonMinter.ts`
- `tests/JettonMinter.spec.ts`

Treat that as a helpful convention, not a guarantee.

Acton heuristic:

- `contracts/src/Counter.tolk`
- `wrappers/Counter.gen.tolk` or `wrappers-ts/Counter.ts`
- `tests/Counter.test.tolk`

## Generated Output Visibility

For Tact/Blueprint projects, tests often import generated wrappers/output files such as `src/output/...`. If `analyze_mutants` swaps a `.tact` source file but the test command does not rebuild the generated output, tests may run against stale code and mutants can falsely survive.

For Tact targets, the `analyze_mutants` command must usually include:

- the project build command first
- then the narrow Jest command

Example:

```bash
analyze_mutants src/contracts/base/jetton-minter.tact \
  "yarn build:base && npx jest --runInBand src/tests/base -t \"Base Jetton\"" \
  --mutantDir mutants \
  --prefix base-minter
```

Before trusting a TON mutation result, verify:

Does the test command see the mutated source through a rebuild of generated output?

If the answer is no or unclear, do not trust the mutation score.

Prefer expanding package scripts into explicit build + narrow test commands when mutation testing generated-contract projects. Do not stop at `yarn test:base` without checking whether it rebuilds generated contract output and whether Jest runs in-band.

Package scripts can be used only after checking their contents. If a script hides the build/test order, expand it into an explicit command. For Tact/Blueprint mutation analysis, prefer the explicit command shape `<build> && <narrow test>`. Jest should run narrow and preferably with `--runInBand` to avoid parallel swap/analyze workflow problems.

If a smoke run gives `0 killed` on obviously strong mutants, such as authorization checks, supply math, balance accounting, sender validation, opcode routing, or deploy/init logic, first check whether the analyze command rebuilds generated output before running tests.

Do not immediately conclude that tests are weak until generated output visibility has been verified.

## Choose Commands For TON Projects

### Acton, Tolk

Template once local TON support is verified:

```sh
mutate contracts/src/Contract.tolk tolk --cmd "acton build" --mutantDir mutants

analyze_mutants contracts/src/Contract.tolk "acton test" \
  --mutantDir mutants \
  --prefix tolk
```

Otherwise first verify or install the TON-enabled build. Prefer direct `acton build` and `acton test` even when the repository has package scripts that wrap them, because those scripts may also build frontend assets or run unrelated checks.

For Acton projects, still verify whether tests compile the mutated source or run against stale build artifacts. If Acton tests depend on generated or cached artifacts, include the required build step in the analyze command.

### Blueprint, Tolk

Template once local TON support is verified:

```sh
mutate contracts/contract.tolk tolk --mutantDir mutants

analyze_mutants contracts/contract.tolk "npx blueprint test" \
  --mutantDir mutants \
  --prefix tolk
```

### Blueprint, Tact

Template once local TON support is verified:

```sh
mutate contracts/contract.tact tact \
  --cmd "npx blueprint build --all" \
  --mutantDir mutants

analyze_mutants contracts/contract.tact "npx blueprint test" \
  --mutantDir mutants \
  --prefix tact
```

Otherwise first verify or install the TON-enabled build. Use the explicit `--cmd` override when the project build goes through Blueprint rather than a standalone compiler call.

For generated-output Tact projects, expand this into the real project build plus narrow Jest command before trusting results, for example:

```sh
analyze_mutants contracts/contract.tact \
  "npx blueprint build --all && npx jest --runInBand tests/Contract.spec.ts -t \"Contract\"" \
  --mutantDir mutants \
  --prefix tact
```

### FunC

Template once local TON support is verified:

```sh
mutate contracts_FunC/01_jetton/jetton-minter-discoverable.fc func \
  --cmd 'npx func-js -C "contracts_FunC/01_jetton" params.fc op-codes.fc discovery-params.fc jetton-utils.fc jetton-minter-discoverable.fc' \
  --mutantDir mutants
```

Otherwise first verify or install the TON-enabled build. If the mutated `.fc` file is imported rather than being the entrypoint, keep the compile command aligned with the real project target set.

## Use Environment Variables

Use these only when local verification or a user-confirmed TON-enabled build shows the installed environment supports them.

### One-off run

```sh
UM_TOLK_CMD='acton build' \
mutate contracts/src/Contract.tolk tolk --mutantDir mutants
```

```sh
UM_TACT_CMD='npx blueprint build --all' \
mutate contracts/contract.tact tact --mutantDir mutants
```

```sh
UM_FUNC_CMD='npx func-js -C "contracts_FunC/01_jetton" params.fc op-codes.fc discovery-params.fc jetton-utils.fc jetton-minter-discoverable.fc' \
mutate contracts_FunC/01_jetton/jetton-minter-discoverable.fc func --mutantDir mutants
```

### Export for a series of runs

```sh
export UM_TOLK_CMD='acton build'
mutate contracts/src/A.tolk tolk --mutantDir mutants-a
mutate contracts/src/B.tolk tolk --mutantDir mutants-b
```

```sh
export UM_TOLK_CMD='npx blueprint build --all'
mutate contracts/A.tolk tolk --mutantDir mutants-a
mutate contracts/B.tolk tolk --mutantDir mutants-b
```

### Different values per contract

Use inline environment assignments so each process gets its own compile command:

```sh
UM_TACT_CMD='npx blueprint build --all' \
mutate contracts/JettonMinter.tact tact --mutantDir mutants-minter

UM_TACT_CMD='npx blueprint build --all' \
mutate contracts/JettonWallet.tact tact --mutantDir mutants-wallet
```

### Keep temporary artifacts for debugging

The current TON handlers also support:

```sh
export UM_KEEP_TEMP=1
```

Use this when you need to inspect temporary compile artifacts, backup files, or handler output while debugging why a specific TON mutant does not compile cleanly.

## Run One Contract Versus Many

### One contract

Prefer one contract when:

- a single contract is the active area of work
- build and test cost is high
- wrapper and tests map clearly to one entrypoint

### Several contracts

Use several contract runs when:

- contracts have distinct wrappers and test files
- one contract's survivors should not be hidden inside another contract's output
- you want to compare mutation quality per contract

Suggested pattern:

Use this only after local TON capability is verified.

```sh
mutate contracts/JettonMinter.tact tact --cmd "npx blueprint build --all" --mutantDir mutants-minter
analyze_mutants contracts/JettonMinter.tact "npx blueprint test" --mutantDir mutants-minter --prefix minter

mutate contracts/JettonWallet.tact tact --cmd "npx blueprint build --all" --mutantDir mutants-wallet
analyze_mutants contracts/JettonWallet.tact "npx blueprint test" --mutantDir mutants-wallet --prefix wallet
```

## Choose Full Test Command Versus Narrow Command

Prefer the full command when:

- deploy and integration behavior matter
- message flow crosses multiple contracts
- wrappers hide setup that unit-like tests would miss

Bundled full-command example:

```sh
analyze_mutants contracts/contract.tact "npx blueprint test" --mutantDir mutants --prefix tact
```

Prefer a narrower command when:

- one contract has a clearly mapped test file
- the full suite is too expensive for iteration
- you want a quick first pass before a broader re-run

Bundled subset re-test example:

```sh
analyze_mutants contracts_FunC/01_jetton/jetton-minter-discoverable.fc \
  "npx jest --runInBand tests/01_jetton/JettonWallet.spec.ts" \
  --mutantDir mutants \
  --fromFile prioritized.txt \
  --prefix prioritized-run
```

That example is shown after prioritization, but the same idea applies when the repository has a trustworthy contract-to-test mapping.

## When TON Compilation Is Expensive

Use this playbook:

1. Mutate one contract at a time.
2. Override compile-check with `--cmd` or the matching `UM_*_CMD` variable.
3. Prefer the narrowest reliable test command for the first pass.
4. Review survivors with `show_mutants`.
5. Use `prioritize_mutants` to reduce a large surviving set.
6. Re-test a prioritized subset with `--fromFile`.

Bundled prioritized-subset flow:

```sh
prioritize_mutants func-minter.notkilled.txt prioritized.txt 50 \
  --mutantDir mutants \
  --sourceDir contracts_FunC/01_jetton

analyze_mutants contracts_FunC/01_jetton/jetton-minter-discoverable.fc \
  "npx jest --runInBand tests/01_jetton/JettonWallet.spec.ts" \
  --mutantDir mutants \
  --fromFile prioritized.txt \
  --prefix prioritized-run
```

## Coverage-Guided TON Triage

Use `check_covered` only when you already have line coverage from outside Universal Mutator, such as custom instrumentation, sandbox traces, or a repository-specific exporter.

Useful flow:

```sh
check_covered contracts/contract.tolk tmp/covered_lines.txt tmp/covered_mutants.txt --mutantDir mutants
prioritize_mutants tmp/covered_mutants.txt prioritized.txt 100 --mutantDir mutants --sourceDir contracts
analyze_mutants contracts/contract.tolk "npx blueprint test" --mutantDir mutants --fromFile prioritized.txt --prefix prioritized
```

This is especially useful for expensive TON test suites where a full analyze pass over every compile-valid mutant is too slow.

## Parallelize Different Contracts

For the shared Web3 concurrency model, agent template, and shell background-job pattern, read [cli.md](cli.md). This section keeps only the TON-specific adjustments and examples.

### TON-specific safety rules

- Before `analyze_mutants`, require a clean tree or isolated worktree.
- Use one `--mutantDir` per contract.
- Use one `--prefix` per contract.
- Use one log pair per contract.
- Do not reuse one output directory for multiple concurrent contract runs.
- Verify the baseline build or compile command and the baseline test command before starting concurrent runs.
- Keep compile commands explicit per process.
- Give each contract its own test command when that improves isolation and trustworthiness.
- If Blueprint, Tact, FunC, or Tolk tooling writes shared build output, caches, or temporary files, expect possible conflicts and isolate the runs.
- Do not suggest `rm`, `git clean`, or similar destructive cleanup shortcuts as part of TON mutation workflows.
- Start with two concurrent runs, then increase only after the first pair is stable.
- When comparing contracts, remember that all three TON languages inherit the shared `ton_common.rules` layer before the language-specific rules start to diverge.

### Separate terminals

Run one contract per terminal only after local TON support is verified:

```sh
UM_TACT_CMD='npx blueprint build --all' \
mutate contracts/contract_a.tact tact --mutantDir mutants-contract-a

analyze_mutants contracts/contract_a.tact "npm test -- ContractA" \
  --mutantDir mutants-contract-a \
  --prefix contract-a
```

```sh
UM_TACT_CMD='npx blueprint build --all' \
mutate contracts/contract_b.tact tact --mutantDir mutants-contract-b

analyze_mutants contracts/contract_b.tact "npm test -- ContractB" \
  --mutantDir mutants-contract-b \
  --prefix contract-b
```

### Background jobs with `&` and `wait`

This is still just a set of independent processes. It is not a scheduler and it does not resolve shared-cache conflicts for you.

```sh
mkdir -p logs

(
  UM_TACT_CMD='npx blueprint build --all' \
  mutate contracts/contract_a.tact tact --mutantDir mutants-contract-a &&
  analyze_mutants contracts/contract_a.tact "npm test -- ContractA" --mutantDir mutants-contract-a --prefix contract-a
) >logs/contract-a.out 2>logs/contract-a.err &

(
  UM_TACT_CMD='npx blueprint build --all' \
  mutate contracts/contract_b.tact tact --mutantDir mutants-contract-b &&
  analyze_mutants contracts/contract_b.tact "npm test -- ContractB" --mutantDir mutants-contract-b --prefix contract-b
) >logs/contract-b.out 2>logs/contract-b.err &

wait
```

### Agent-owned TON runs

Use separate agents or tasks when each contract can be assigned cleanly. Each agent should own:

- exactly one contract or one explicitly named small bundle
- its own `--mutantDir`
- its own stdout and stderr logs
- its own compile command and test command
- its own summary of killed, survived, timeout, compile-error, and TON-specific findings

Merge the results later with the canonical summary formats from [analysis.md](analysis.md).

### CPU and RAM guidance

- Start with one concurrent worker per heavy contract build.
- Increase concurrency only if compiler memory use and test runtime stay stable.
- Prefer fewer concurrent runs for Tact, FunC, or integrated Blueprint test suites.

## Interpret Surviving TON Mutants

Treat a survivor as a test-design clue, not just a filename.

### Common meanings

- Missing message tests: the suite never sends or asserts a critical inbound message path.
- Weak edge-case coverage: boundaries around zero, limits, underflow-style behavior, or fee math are untested.
- Incomplete storage or state checks: tests execute a flow but do not assert the persisted result strongly enough.
- Missing negative tests: the suite proves happy paths but not rejection paths.
- Incomplete opcode or message coverage: commands exist but are not asserted by type, opcode, payload, or side effect.
- Deploy or init gaps: initialization state, ownership, code or data setup, and redeploy edge cases are under-tested.

### What to recommend after triage

- Add tests for the exact message or opcode that the surviving mutant weakens.
- Assert post-message state, balances, and emitted side effects.
- Add negative tests for rejected senders, invalid payloads, duplicate actions, and insufficient funds.
- Add deploy and init tests that validate owner, storage defaults, and derived addresses.
- Re-run the exact contract after each added test, then use the broader Blueprint test command before closing the issue.
- Use [ton-contract-checklists.md](ton-contract-checklists.md) when the contract class is known and the survivor needs more specific test ideas.
- Use the canonical final output from [analysis.md](analysis.md) so the report stays stable across TON and EVM repositories.

## Runtime Details Worth Knowing

- `analyze_mutants` exports `CURRENT_MUTANT_SOURCE` for the launched test command
- if the test command does not contain `MUTANT`, the tool temporarily swaps the mutant into the original source location and restores the original file afterward
- if the command does contain `MUTANT`, the tool passes the mutant path directly instead of replacing the source file on disk

That second mode can be useful for source-level EVM projects. For TON repositories, the temporary source replacement mode is usually more reliable because project builds tend to depend on entrypoints, config files, and relative imports rather than on compiling one detached file path directly.
