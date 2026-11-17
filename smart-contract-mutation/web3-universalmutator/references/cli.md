# Universal Mutator CLI Reference

## Contents

- [Scope](#scope)
- [Documented Core Commands](#documented-core-commands)
- [Choose The Target](#choose-the-target)
- [Choose The Compile Or Test Command](#choose-the-compile-or-test-command)
- [Documented Flags And Inputs](#documented-flags-and-inputs)
- [Locally Verified Rule-Introspection Flags](#locally-verified-rule-introspection-flags)
- [Locally Verified `analyze_mutants` Flags](#locally-verified-analyze_mutants-flags)
- [Environment Variables](#environment-variables)
- [Read Stdout, Stderr, And Output Files](#read-stdout-stderr-and-output-files)
- [Concurrent Execution](#concurrent-execution)
- [Compare And Merge Results](#compare-and-merge-results)
- [POSIX Focus And Windows Note](#posix-focus-and-windows-note)

## Scope

Use this file for Universal Mutator command selection and shell workflow in supported Web3 smart-contract repositories. It bundles the safe command baseline that this skill was authored against, plus a small set of locally verified flags called out explicitly. If something is not described here or in the current repository source, treat it as not confirmed.

Before assuming that a user environment matches this baseline, use `scripts/detect_um_capabilities.py` when command availability or flag support is uncertain.

If the capability detector reports that current Python package rule files do not match the resolved `mutate` command environment, do not rely on package-local TON rule files as proof that the command supports TON.

Do not advise a command or flag unless `scripts/detect_um_capabilities.py` confirms it, local help confirms it, or this reference explicitly marks it as version-dependent.

When local capability is unknown, phrase commands as templates, not facts. This matters especially for TON-language examples and locally verified flags.

Before a live run that may swap files into place, read [safety.md](safety.md). When you want ready-made command scaffolds, read [command-templates.md](command-templates.md). When a run fails or becomes noisy, read [troubleshooting.md](troubleshooting.md).

## Documented Core Commands

### `mutate`

Generate mutants for one source file.

Documented Web3 examples:

```sh
mutate <sourcefile> <tact|tolk|func> --mutantDir mutants
mutate contracts/Vault.sol solidity --mutantDir mutants
mutate contracts/Oracle.vy vyper --mutantDir mutants
mutate contracts/Asset.fe fe --mutantDir mutants
```

Use `mutate --help` before inventing syntax. Treat TON and EVM language forms as templates until local help or installed rule files confirm support.

Optional default-plus-custom rules templates:

```sh
mutate <sourcefile> <language> <custom.rules> --mutantDir <dir>
mutate <sourcefile> <language> rules/access.rules rules/serialization.rules --mutantDir <dir>
mutate contracts/Vault.sol solidity mutants/custom-rules/vault.rules --mutantDir mutants/contracts-Vault-sol
```

Use custom `.rules` files after the user asks for them, accepts an optional custom-rules pass, or explicitly requests autonomous custom-rule generation. Positional custom rule files are intended to add project-specific rules to the language defaults. Use `--showRules` to check whether default or custom rules fired when local help confirms the flag. Use `--only <custom.rules>` only when the user wants to replace the default stack with the custom file, and only after local `mutate --help` confirms `--only`.

### `analyze_mutants`

Run a build, compile, or test command against generated mutants.

Documented examples:

```sh
analyze_mutants <sourcefile> "<test command>" --mutantDir mutants --prefix run
analyze_mutants contracts/Vault.sol "forge test --match-path test/Vault.t.sol" --mutantDir mutants --prefix vault
```

Before any `analyze_mutants` run, require a clean tree or isolated worktree.

### Post-processing commands

Bundled command baseline:

```sh
show_mutants run.notkilled.txt --mutantDir mutants --sourceDir <source_dir> --concise
prioritize_mutants func-minter.notkilled.txt prioritized.txt 50 --mutantDir mutants --sourceDir contracts_FunC/01_jetton
prune_mutants
intersect_mutants
check_covered <sourcefile> <coverfile> <outfile> --mutantDir mutants
```

The current repository also includes `findmissing.py` for comparing mutant directories, but it is an internal helper rather than a primary workflow command.

Treat post-processing commands and their flags as usable only when the capability detector or local `--help` confirms them in the current environment.
When `scripts/summarize_results.py` has not confirmed `show_flags` or `prioritize_flags`, treat its `Next commands` as templates and verify them before use.

## Choose The Target

### Prefer explicit files or contract entrypoints

The supplied docs consistently show `mutate` and `analyze_mutants` against a single file:

- `contracts/contract.tact`
- `contracts/contract.tolk`
- `contracts/src/Counter.tolk`
- `jetton-minter-discoverable.fc`
- `contracts/Vault.sol`
- `contracts/Oracle.vy`
- `contracts/Asset.fe`

This is the safest documented workflow. Use project detection to choose the right file, then mutate that file directly.

### Directory-wide mutation

Direct directory-wide mutation syntax is not confirmed by the bundled command baseline. If a user wants a whole project pass, translate that into a per-file or per-contract plan unless you have locally confirmed broader support.

## Choose The Compile Or Test Command

### Simple projects

If the Web3 source file compiles directly and the default compiler integration is enough, start with:

```sh
mutate contracts/Vault.sol solidity --mutantDir mutants
```

### Complex builds

For multi-step builds or real tests, use `analyze_mutants` with the exact shell command that proves correctness:

```sh
analyze_mutants contracts/Vault.sol "forge test --match-path test/Vault.t.sol" --mutantDir mutants --prefix vault
```

Acton-backed Tolk example:

```sh
mutate contracts/src/Contract.tolk tolk --cmd "acton build" --mutantDir mutants
analyze_mutants contracts/src/Contract.tolk "acton test" --mutantDir mutants --prefix tolk
```

### TCE versus full project builds

The bundled CLI baseline confirms that many languages try to compile the mutated file by default and use Trivial Compiler Equivalence. If Web3 build dependencies make this unworkable, the documented fallback is:

```sh
mutate contracts/Vault.sol solidity --mutantDir mutants --noCheck
```

Then run a real build or test command with `analyze_mutants`.

Treat `--noCheck` as a last resort. It can generate a much larger, noisier mutant set and should not be the default suggestion when a narrower compile-aware flow is available.

### `--compile`

The bundled CLI baseline confirms `--compile` specifically for cases such as Solidity libraries with only `internal` functions. The value is another file used to check whether mutants are redundant.

Use it when:

- the mutated file is not a standalone compilation unit
- the real build emits code only when a consumer file is compiled

Do not generalize `--compile` beyond this documented purpose without local confirmation.

## Documented Flags And Inputs

### Bundled shared baseline

- `--help`
- `--comby`
- `--noCheck`
- `--mutantDir`
- `--compile`
- `--swap`

### Bundled TON baseline

- `--cmd`
- `--prefix`
- `--sourceDir`
- `--concise`

If you need more flags, inspect local help first and call out that they were verified locally rather than from the bundled command baseline.

## Locally Verified Rule-Introspection Flags

The current repository source and CLI help in `genmutants.py` also expose flags that are useful when the user asks which rules fired. These are locally verified from the current tool code, not from the bundled command baseline.

- `--showRules`: print the rule source used to generate each mutant
- `--only <rule>`: restrict mutation to one rule file
- `--printStat`: write rule and mutant statistics files such as `rules_count.txt`

Use these only with a clear note that they are verified from the local codebase rather than the supplied top-level docs.

Treat `--showRules`, `--only`, and `--printStat` as locally verified or fork-specific until the installed `mutate --help` confirms them.

## Locally Verified `analyze_mutants` Flags

The current repository help text in `analyze.py` also confirms these extra flags for `analyze_mutants`. They are useful, but they are not described in the supplied top-level docs.

- `--timeout`
- `--show`
- `--verbose`
- `--seed`
- `--noShuffle`
- `--resume`
- `--numMutants`
- `--fromFile`
- `--compileCommand`

When you use them, say that they were verified locally from the current repository source or help output. For `--timeout`, `--fromFile`, and `--noShuffle`, prefer an explicit `analyze_mutants --help` check in the installed environment before writing the command into a plan.

## `--swap`

### What it does

The bundled CLI baseline confirms `--swap` as adding mutations that swap adjacent lines of code.

### When to use it

Use it when line ordering matters semantically, especially for smart contracts and stateful code. The README calls out Solidity and re-entrancy-style ordering bugs as the clearest documented example.

### Risks

- It increases the mutant set, which can raise runtime and review cost.
- It can create mutants that are syntactically valid but operationally noisy.
- It is easy to overuse on code where adjacent-line order is not meaningful.

### Example commands

```sh
mutate contracts/contract.tact tact --swap --mutantDir mutants
mutate contracts/MyLibrary.sol --compile contracts/MyConsumer.sol --swap --mutantDir mutants
```

### How to verify that swap mutants applied sensibly

1. Generate into a fresh `--mutantDir`.
2. Run `analyze_mutants` and then `show_mutants` on surviving mutants.
3. Confirm that the displayed mutant actually swapped neighboring operations and did not merely introduce unrelated compile failures.

Example:

```sh
show_mutants run.notkilled.txt --mutantDir mutants --sourceDir contracts --concise
```

### When `--swap` is not needed

- When you only need default operator-level mutation coverage.
- When build or test cost is already too high.
- When ordering changes are unlikely to matter for the target code.

## Environment Variables

### Confirmed documentation

The supplied docs only confirm compile-command environment variables for TON languages, and those are covered in [ton.md](ton.md).

### Conditional pattern for other projects

If the tool supports compile or test overrides via environment variables in a specific environment, that behavior is not confirmed by the bundled baseline. Treat it as a project-local pattern rather than a documented Universal Mutator feature.

## Dry-Run Support

Dry-run support is not confirmed by the bundled command baseline. Do not promise a dry-run flag unless you verify it locally.

## Read Stdout, Stderr, And Output Files

The supplied docs describe result files more clearly than console output.

Documented output files:

- `killed.txt` and `not-killed.txt`
- `<prefix>.killed.txt` and `<prefix>.notkilled.txt`

Recommended shell pattern:

```sh
mkdir -p logs
analyze_mutants contracts/contract.tolk "npx blueprint test" --mutantDir mutants --prefix tolk >logs/tolk.out 2>logs/tolk.err
```

Acton variant:

```sh
mkdir -p logs
analyze_mutants contracts/src/Contract.tolk "acton test" --mutantDir mutants --prefix tolk >logs/tolk.out 2>logs/tolk.err
```

Use:

- stdout/stderr for build errors, test failures, and runtime clues
- the result text files as the stable handoff into `show_mutants`, `prioritize_mutants`, and subset re-runs
- `scripts/collect_mutation_artifacts.py` when you want a quick inventory of which prefixes, logs, and result files exist
- `scripts/summarize_results.py` when you want the canonical report shape before deeper manual analysis; its next commands are capability-aware and omit unsupported flags such as `--sourceDir`

For file-name conventions and helper-script JSON or markdown output, read [result-file-formats.md](result-file-formats.md).

## Exit Codes

Tool-specific exit-code semantics are not documented in the supplied files. Treat shell success versus non-zero failure as useful operational feedback, but do not assign finer meaning unless you verified it locally.

## Environment Behavior During Analysis

The current repository code also confirms one useful runtime detail:

- `analyze_mutants` sets `CURRENT_MUTANT_SOURCE` for the command it launches

Use that variable only when a wrapper script or test runner truly needs to know which mutant is currently under test.

## Concurrent Execution

### Safety rules

- Do not run `mutate` or `analyze_mutants` in parallel inside the same project checkout.
- Run mutation generation and analysis sequentially for one checkout, because parallel runs can corrupt swapped source files, generated wrappers, build caches, or test state.
- Before `analyze_mutants`, start from a clean tree or an isolated worktree.
- Use a separate `--mutantDir` per target.
- Use a separate `--prefix` per target.
- Write logs to separate files.
- Do not reuse the same output directory for separate runs.
- Do not suggest `rm`, `git clean`, or similar destructive cleanup shortcuts as part of the workflow.
- Verify that one target completes the full mutate plus analyze cycle before considering isolated parallel runs.
- Use separate worktrees or clones for parallel runs. A `.tmp/um-runs/<target-slug>` copy is acceptable when it is kept out of test discovery and build globs.
- If the compile or test command uses a shared build cache or temporary files, expect conflicts unless the environment is isolated.

### Isolated terminals

Run one target per isolated checkout and keep ownership explicit. Do not run these examples from the same project checkout.

```sh
cd .tmp/um-runs/contract-a
mutate path/to/contract-a.ext --mutantDir mutants-contract-a
analyze_mutants path/to/contract-a.ext "test command for contract a" --mutantDir mutants-contract-a --prefix contract-a
```

```sh
cd .tmp/um-runs/contract-b
mutate path/to/contract-b.ext --mutantDir mutants-contract-b
analyze_mutants path/to/contract-b.ext "test command for contract b" --mutantDir mutants-contract-b --prefix contract-b
```

```sh
cd .tmp/um-runs/contract-c
mutate path/to/contract-c.ext --mutantDir mutants-contract-c
analyze_mutants path/to/contract-c.ext "test command for contract c" --mutantDir mutants-contract-c --prefix contract-c
```

### Background jobs with `&` and `wait`

Use background jobs only when every subshell changes into a separate isolated checkout. This is not a scheduler. It is just several independent processes started from one shell.

```sh
mkdir -p logs

(
  cd .tmp/um-runs/contract-a &&
  mutate path/to/contract-a.ext --mutantDir mutants-contract-a &&
  analyze_mutants path/to/contract-a.ext "test command for contract a" --mutantDir mutants-contract-a --prefix contract-a
) >logs/contract-a.out 2>logs/contract-a.err &

(
  cd .tmp/um-runs/contract-b &&
  mutate path/to/contract-b.ext --mutantDir mutants-contract-b &&
  analyze_mutants path/to/contract-b.ext "test command for contract b" --mutantDir mutants-contract-b --prefix contract-b
) >logs/contract-b.out 2>logs/contract-b.err &

wait
```

### Agent-Based Parallelization

Use this when separate agents or tasks can own separate targets cleanly. One agent should handle exactly one file, one contract, or one explicitly assigned small bundle.

Each agent should receive:

- the target path
- the project type
- the compile command
- the test command
- a unique `--mutantDir`
- a unique log prefix
- the canonical report shape from [analysis.md](analysis.md)

Agent task template:

```text
You are responsible for running Universal Mutator for exactly one target.

Target:
<path>

Project type:
<TON | Blueprint | Acton | Tact | FunC | Tolk | Solidity | Foundry | Hardhat | Truffle | Vyper | Fe>

Compile/test command:
<command>

Mutant directory:
<unique-mutant-dir>

Log files:
<stdout-log>
<stderr-log>

Tasks:
1. Verify the baseline compile/test command passes before mutation testing.
2. Run Universal Mutator only for the assigned target.
3. Do not modify or reuse another target's mutant directory.
4. Save stdout/stderr separately.
5. Summarize killed, survived, timeout, compile-error, and suspicious mutants.
6. For TON projects, call out missing message, opcode, storage/state, deploy/init, and negative test coverage.
7. Return recommended next tests.
```

## Compare And Merge Results

After concurrent runs, compare per-target artifacts instead of mixing everything into one directory:

- `<prefix>.killed.txt`
- `<prefix>.notkilled.txt`
- `logs/<target>.out`
- `logs/<target>.err`

Use `show_mutants` per target first. Merge lists only after confirming the source directories and naming conventions align. Use the canonical single-target and multi-target report formats from [analysis.md](analysis.md), or scaffold them with `scripts/summarize_results.py`.

## POSIX Focus And Windows Note

Universal Mutator itself can be used on both Windows and Linux. Examples here use POSIX shell syntax because it is the most compact cross-project style. On PowerShell, replace `VAR=value cmd` with `$env:VAR='value'; cmd`, and replace `2>file` redirection patterns with the PowerShell equivalents if needed.

Treat `--comby` as a Linux or WSL workflow on Windows. The external `comby` binary should not be assumed to be available natively in the same way as on Linux.
