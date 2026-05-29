# Helper Scripts

These scripts are bundled with the skill to make recurring Universal Mutator workflows more reproducible. They are skill-local helpers, not upstream Universal Mutator commands.

## Contents

- [When To Use Them](#when-to-use-them)
- [`detect_um_capabilities.py`](#detect_um_capabilitiespy)
- [`detect_project.py`](#detect_projectpy)
- [`plan_mutation_run.py`](#plan_mutation_runpy)
- [`run_campaign.py`](#run_campaignpy)
- [`propose_custom_rules.py` and `validate_custom_rules.py`](#propose_custom_rulespy-and-validate_custom_rulespy)
- [`collect_mutation_artifacts.py`](#collect_mutation_artifactspy)
- [`summarize_results.py`](#summarize_resultspy)
- [`prepare_publish.py`](#prepare_publishpy)
- [Boundaries](#boundaries)

## When To Use Them

- Use `scripts/detect_um_capabilities.py` when you need to probe the installed Universal Mutator environment instead of inferring capabilities from a repository checkout.
- Use `scripts/detect_project.py` when Web3 project layout or the right test command is unclear, or when you need to identify a non-Web3 repository as out of scope.
- Use `scripts/plan_mutation_run.py` when the user asks to run mutation testing on a supported Web3 repository or contract and you need an autopilot route from detection to commands.
- Use `scripts/run_campaign.py` when the user explicitly asks for an autonomous smoke or full campaign with durable artifacts.
- Use `scripts/propose_custom_rules.py` and `scripts/validate_custom_rules.py` when project-specific custom mutation rules would strengthen a campaign.
- Use `scripts/collect_mutation_artifacts.py` after one or more runs to inventory result files, logs, and mutant directories.
- Use `scripts/summarize_results.py` when you want a stable canonical report scaffold before doing deeper mutant interpretation.
- Use `scripts/prepare_publish.py` before publication when you want a cleaned release bundle without cache files or generated local artifacts.

## `detect_um_capabilities.py`

Purpose:

- find `mutate`, `analyze_mutants`, `show_mutants`, `prioritize_mutants`, `prune_mutants`, `intersect_mutants`, and `check_covered`
- run `mutate --help`
- run `analyze_mutants --help`
- run `show_mutants --help`
- run `prioritize_mutants --help`
- probe versions when the installed commands expose them
- check whether `mutate` flags such as `--cmd`, `--mutantDir`, `--noCheck`, `--swap`, `--ignore`, `--lines`, `--noFastCheck`, `--comby`, `--only`, `--showRules`, and `--printStat` appear in help output
- check whether `analyze_mutants` flags such as `--mutantDir`, `--prefix`, `--numMutants`, `--noShuffle`, `--timeout`, `--sourceDir`, and `--fromFile` appear in help output
- check whether `show_mutants` flags such as `--mutantDir`, `--sourceDir`, `--prefix`, and `--concise` appear in help output
- check whether `prioritize_mutants` flags such as `--mutantDir`, `--sourceDir`, `--cutoff`, and `--noSDPriority` appear in help output
- report post-processing command availability only when those commands are actually found
- check whether `tact`, `tolk`, and `func` support appears in help output
- report per-language capability confidence for `tact`, `tolk`, `func`, `solidity`, `vyper`, and `fe`
- report whether TON support came from `mutate --help` or installed package rule files that match the resolved `mutate` command environment
- warn when the current Python package has TON rule files but the resolved `mutate` command appears to come from a different Python environment
- return JSON or markdown so the result can be fed directly into later planning or reporting

Examples:

```sh
python scripts/detect_um_capabilities.py
python scripts/detect_um_capabilities.py --format markdown
```

What it returns:

- platform and Python version
- command presence and resolved paths
- versions when a command exposes them cleanly
- `mutate --help` excerpt
- `analyze_mutants --help` excerpt
- `show_mutants --help` excerpt
- `prioritize_mutants --help` excerpt
- mutate-flag support booleans
- analyze-flag support booleans
- `show_flags` support booleans
- `prioritize_flags` support booleans
- post-processing command support booleans
- TON language support booleans
- TON support source
- language capabilities with `rules_file_found`, `cli_language_advertised`, optional `smoke_probe_passed`, and `confidence`
- notes when commands are missing or help probing times out

## `detect_project.py`

Purpose:

- inspect repository markers
- detect supported Web3 project types: `ton`, `blueprint-ton`, `acton-ton`, `solidity-foundry`, `solidity-hardhat`, `solidity-truffle`, `solidity-generic`, `vyper`, or `fe`
- detect non-Web3 project types such as `generic`, `typescript-jest`, `rust`, `go`, `java-maven`, `java-gradle`, `swift`, `r`, or `fortran` only so `plan_mutation_run.py` can mark them out of scope
- list TON contracts, wrapper matches, test matches, and likely commands
- classify TON entrypoint contracts separately from shared dependency files
- classify mixed TON/EVM repositories while preserving explicit target override behavior

Examples:

```sh
python scripts/detect_project.py .
python scripts/detect_project.py . --format json
```

What it returns:

- project type
- project family, including `mixed` when TON and EVM sources coexist
- detected package manager from lockfiles or `packageManager`, plus ambiguity when only `package.json` exists
- detected markers such as `blueprint.config.*`, `jest.config.*`, `tsconfig.json`
- `package.json` scripts
- TON contract mappings
- entrypoint contracts
- shared dependency files
- recommended compile and test commands

## `plan_mutation_run.py`

Purpose:

- turn "run mutation testing on this Web3 code" into a concrete Universal Mutator route
- choose one source or contract target from TON, Blueprint, Acton, Foundry, Hardhat, Truffle, Solidity, Vyper, or Fe project markers
- let explicit target suffix override repository-family detection
- keep directory targets entrypoint-first and report shared dependency files without mutating them by default
- refuse non-Web3 projects instead of constructing a generic Universal Mutator plan
- derive the output directory as `mutants/<safe-target-path>`
- set the required report path to `mutants/REPORT.md`
- keep execution mode as sequential in one project checkout
- try the default compile check first through `initial_mutate_command`
- provide `fallback_mutate_commands` using the real project compile command when direct language compilers are unavailable or insufficient
- choose a narrow test command when a matching test file exists
- build the final `analyze_mutants` command from the selected compile and test route

Examples:

```sh
python scripts/plan_mutation_run.py .
python scripts/plan_mutation_run.py . --target Wallet
python scripts/plan_mutation_run.py . --target contracts --all-entrypoints --format json
python scripts/plan_mutation_run.py . --target contracts/Wallet.tolk --format json
```

What it returns:

- project type, language, target, wrapper, and mapped test when available
- scope summary with requested scope, executed scope, entrypoint targets, shared dependency files, and completeness label such as `entrypoint-focused-not-full-directory`
- mutant directory, prefix, report path, and execution mode
- `initial_mutate_command`
- structured `commands` entries with `argv` and safe copy-pasteable `shell`
- `fallback_compile_commands`
- `fallback_mutate_commands`
- narrow test command
- final analyze command
- command status, marking planned commands as templates until capability verification
- supported Web3 language families: TON (`tact`, `tolk`, `func`) and EVM (`solidity`, `vyper`, `fe`)
- preflight steps and notes, including baseline test validation, long-running warnings, sequential execution, and `mutants/REPORT.md` updates

## `run_campaign.py`

Purpose:

- detect the project and target language
- verify Universal Mutator command and flag capabilities
- run baseline build/test, `mutate`, and `analyze_mutants` sequentially with `subprocess.run([...], shell=False)`
- write campaign artifacts under `mutants/<campaign-slug>/`
- update aggregate `mutants/REPORT.md`
- retry fallback `mutate --cmd <compile-command>` commands when the default mutation compile check fails
- write/update `mutants/REPORT.md` after planning, mutation generation, analysis, and failure states

Examples:

```sh
python scripts/run_campaign.py . --target contracts/Vault.sol --mode smoke
python scripts/run_campaign.py . --target contracts/Vault.sol --mode full
python scripts/run_campaign.py . --target contracts --all-entrypoints --mode smoke
python scripts/run_campaign.py . --target contracts/Vault.sol --dry-run
python scripts/run_campaign.py . --target contracts/Vault.sol --custom-rules write-and-use
```

Artifacts:

- `plan.json`
- `manifest.json`
- `commands.sh`
- `capabilities.json`
- `artifacts.json`
- `run.log`
- `summary.md`
- aggregate `mutants/REPORT.md`

Smoke mode adds `--numMutants 5` when `detect_um_capabilities.py` verifies `--numMutants`. It adds `--noShuffle` and `--timeout 60` only when those optional flags are verified. If `--numMutants` is unavailable, smoke mode aborts before unbounded analysis and points to `--dry-run`, manual commands, or explicit `--mode full`.

## `propose_custom_rules.py` and `validate_custom_rules.py`

Examples:

```sh
python scripts/propose_custom_rules.py . --target src/Vault.sol
python scripts/propose_custom_rules.py . --target src/Vault.sol --write mutants/custom-rules/src-Vault-sol.rules
python scripts/validate_custom_rules.py . --target src/Vault.sol --rules mutants/custom-rules/src-Vault-sol.rules
python scripts/validate_custom_rules.py . --target src/Vault.sol --rules mutants/custom-rules/src-Vault-sol.rules --dry-run-mutants
```

The proposer emits the `Rule idea:` shape used in reports and can write rules under `mutants/custom-rules/`. The validator checks `.rules` syntax, match counts, touched lines, broad-rule warnings, likely default-rule duplicates, and optional temporary dry-run mutant generation before a campaign uses the file.

## `collect_mutation_artifacts.py`

Purpose:

- find `killed.txt`, `notkilled.txt`, `not-killed.txt`, prefixed variants, manifests, logs, and nested `mutants/<slug>/` directories
- group artifacts by run prefix
- count killed and surviving mutants per run
- surface simple timeout or error hints from stdout and stderr

Examples:

```sh
python scripts/collect_mutation_artifacts.py .
python scripts/collect_mutation_artifacts.py . --format json
```

Expected grouping model:

- `minter.killed.txt` and `minter.notkilled.txt` map to prefix `minter`
- `logs/minter.out` and `logs/minter.err` map to the same prefix
- `mutants-minter` is inferred as that run's mutant directory when the name matches the prefix
- `mutants/src-Vault-sol/src-Vault-sol.not-killed.txt` maps to prefix `src-Vault-sol` and mutantDir `mutants/src-Vault-sol`

## `summarize_results.py`

Purpose:

- emit the skill's canonical final report shape
- summarize one named run or all collected runs
- preserve a stable section order even before deep manual analysis
- write the required campaign report to `mutants/REPORT.md` with `--output`
- make `Next commands` capability-aware; summary next commands are templates until the relevant flags are confirmed by `scripts/detect_um_capabilities.py`

Examples:

```sh
python scripts/summarize_results.py . --prefix minter --project-type blueprint-ton --source-dir contracts
python scripts/summarize_results.py . --prefix minter --command 'mutate contracts/JettonMinter.tact tact --mutantDir mutants-minter'
python scripts/summarize_results.py . --prefix minter --output mutants/REPORT.md
python scripts/summarize_results.py .
```

Single-run output shape:

- `Target:`
- `Scope:`
- `Commands:`
- `Results:`
- `Survivors:`
- `Likely gaps:`
- `Recommended tests:`
- `Next commands:`

## `prepare_publish.py`

Purpose:

- create a cleaned publish tree from the skill folder
- remove Python cache files and local cache directories
- build `_publish/archives/web3-universalmutator.zip` from the cleaned tree

Examples:

```sh
python scripts/prepare_publish.py
python scripts/prepare_publish.py --format json
python scripts/prepare_publish.py --staging-root ../custom-stage --force
```

What it removes from the published bundle:

- `__pycache__/`
- `*.pyc`, `*.pyo`
- `.pytest_cache/`

Safety behavior:

- the default staging directory may be replaced on repeated publish runs
- an existing non-default staging directory requires `--force`
- `zip_path` must be a file path, not a directory

## Boundaries

- These scripts do not replace `show_mutants` or manual mutant interpretation.
- They only summarize what can be inferred safely from files, filenames, and simple log markers.
- For rule-family meaning, read [mutation-rules.md](mutation-rules.md).
- For TON-specific survivor interpretation, read [ton.md](ton.md) and [analysis.md](analysis.md).
