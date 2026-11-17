# Command Templates

## Contents

- [How To Use These Templates](#how-to-use-these-templates)
- [Package-Manager Variants](#package-manager-variants)
- [Preflight](#preflight)
- [Clean Worktree Or Isolated Run](#clean-worktree-or-isolated-run)
- [Sequential Execution And Reports](#sequential-execution-and-reports)
- [Autopilot Route](#autopilot-route)
- [Entrypoint-First Directory Scope](#entrypoint-first-directory-scope)
- [Target Project Root Templates](#target-project-root-templates)
- [Tact / Blueprint Generated Output Preflight](#tact--blueprint-generated-output-preflight)
- [Acton Tolk Smoke](#acton-tolk-smoke)
- [Acton Tolk Full Run](#acton-tolk-full-run)
- [Blueprint Tact Smoke](#blueprint-tact-smoke)
- [Blueprint Tact Full Run](#blueprint-tact-full-run)
- [FunC Entrypoint Compile Override](#func-entrypoint-compile-override)
- [Show Survivors](#show-survivors)
- [Prioritized Rerun](#prioritized-rerun)
- [Timeout Triage](#timeout-triage)

## How To Use These Templates

These are scaffolds, not proof that every installed CLI exposes every flag. Replace placeholders, verify the real project build and test scripts, and confirm uncertain flags locally before running a long campaign.

When local capability is unknown, phrase commands as templates, not facts: “If your installed `mutate --help` confirms `<flag/language>`, use... Otherwise first verify or install the TON-enabled build.”

Do not turn these templates into destructive cleanup recipes. Avoid `rm`, `git clean`, or similar shortcuts in suggested workflows.

For Acton repositories, prefer direct `acton build` and `acton test` over package scripts that may also build or test unrelated app layers.

For Tact/Blueprint generated-contract projects, prefer expanding package scripts into explicit build + narrow test commands. Do not stop at `yarn test:base` without checking whether it rebuilds generated contract output and whether Jest runs in-band.

Required verification note:

- `--timeout`, `--fromFile`, and `--noShuffle` should be used only after `analyze_mutants --help` confirms they exist in the installed environment.

## Package-Manager Variants

Use repository scripts before hardcoded commands when the project already defines them.

Common script forms:

```sh
npm run <script>
pnpm run <script>
yarn <script>
bun run <script>
```

Helpful placeholder mapping:

- compile script: `<package-manager> run <build-script>`
- test script: `<package-manager> run <test-script>`
- narrow test script: `<package-manager> run <test-script> -- <target>`

Package scripts can be used only after checking their contents. If the script hides build/test order for a generated-contract project, expand it into `<build> && <narrow test>`. For Jest-based Tact/Blueprint mutation analysis, prefer narrow test selection plus `--runInBand`.

## Preflight

Verify command presence and help text before constructing a TON-specific workflow.

```sh
command -v mutate
command -v analyze_mutants
command -v show_mutants
mutate --help
analyze_mutants --help
python scripts/detect_um_capabilities.py --format markdown
```

If `mutate --help` does not list `tact`, `tolk`, or `func`, treat TON language support as unverified until the installed package or the user confirms a TON-enabled fork.

Run the baseline test command immediately after tooling verification. Do not start mutation generation if the baseline tests fail.

## Clean Worktree Or Isolated Run

Prefer a clean tree, or isolate the run in a worktree before commands that may swap files in place. Treat this as mandatory before `analyze_mutants`.

```sh
git status --short
git worktree add ../repo-muttest -b mutation-testing/<target>
cd ../repo-muttest
```

If the repository is already dirty and the user did not ask to reorganize the workspace, keep the run narrow and avoid destructive cleanup.

## Sequential Execution And Reports

Do not run `mutate` or `analyze_mutants` in parallel inside the same project checkout. A mutation run can swap source files, rebuild generated output, and use shared build or test state. Run the target sequentially in the current checkout.

If parallel work is required, use separate `git worktree` checkouts or copy the repository to `.tmp/um-runs/<target-slug>` per target, then run each full sequence inside its isolated checkout.

Before a long `analyze_mutants` run, tell the user that mutation analysis can take a long time and may appear stuck while the test command repeats for many mutants.

Create or update `mutants/REPORT.md` after mutation generation with target, commands, total mutants, and non-compiling mutants. Update `mutants/REPORT.md` after analysis with killed, survived, timeout, compile-error, and flaky counts plus survivor interpretation and next tests.

## Autopilot Route

For user requests such as "run mutation testing on this Web3 contract/code", start with the helper route instead of guessing commands:

```sh
python scripts/plan_mutation_run.py . --target <contract-or-source-name>
python scripts/plan_mutation_run.py . --target <directory> --all-entrypoints --format json
```

The route chooses `mutants/<safe-target-path>`, `mutants/REPORT.md`, an initial default-compiler mutation command, `fallback_mutate_commands`, and a narrow test/analyze command for supported TON and EVM targets. Always run the baseline test command first, then try the default compile check first. If direct compilers such as `tolk-js`, `tact`, `func-js`, or project-local Solidity, Vyper, or Fe tooling are missing or insufficient, inspect the error and rerun with the first fallback mutation command.

Treat the generated commands as templates until `scripts/detect_um_capabilities.py` confirms the local command, language, and flag surface.

Foundry routes should prefer `forge build` and a matching `forge test --match-path <test>` when a test file is mapped. Hardhat routes should prefer package scripts when present, then fall back to `npx hardhat compile` and `npx hardhat test <test>`. Non-Web3 repositories are out of scope for this skill.

For autonomous campaigns:

```sh
python scripts/run_campaign.py . --target <target> --mode smoke
python scripts/run_campaign.py . --target <target> --mode full
python scripts/run_campaign.py . --target <directory> --all-entrypoints --mode smoke
python scripts/run_campaign.py . --target <target> --dry-run
```

Smoke mode limits analysis to five mutants when `analyze_mutants --help` confirms `--numMutants`. It adds `--noShuffle` and `--timeout 60` only when those optional flags are also confirmed. If `--numMutants` is unavailable, smoke mode must abort before unbounded analysis; use `--dry-run`, inspect the manual analyze command, or explicitly choose `--mode full`.

## Entrypoint-First Directory Scope

Default Web3 mutation campaigns are entrypoint-first. When the target is a directory, run separate file-level campaigns for the entrypoint contracts selected by `scripts/plan_mutation_run.py`. Do not mutate every shared source file in a contract directory by default.

Plan output should include a scope block like:

```text
Requested scope: contracts_Tolk/01_jetton
Executed scope: entrypoint-contracts
Completeness: entrypoint-focused-not-full-directory
Entrypoints mutated/planned:
- contracts_Tolk/01_jetton/JettonMinter.tolk
- contracts_Tolk/01_jetton/JettonWallet.tolk
Shared dependency files observed but not mutated by default:
- contracts_Tolk/01_jetton/messages.tolk
- contracts_Tolk/01_jetton/storage.tolk
```

Do not describe an entrypoint-focused campaign as full directory coverage. If shared files must be tested, run a separate explicitly named shared-dependency pass after the entrypoint survivors have been prioritized and triaged.

If the user does not pass `--all-entrypoints`, report: `Directory target detected. Planned the highest-confidence entrypoint only. Use --all-entrypoints to generate commands for every entrypoint.`

## Target Project Root Templates

All source paths, mutant directories, build commands, and test commands must be interpreted relative to the target project root, unless the command explicitly changes directory.

From target project root:

```bash
mutate src/contracts/base/jetton-minter.tact tact --cmd "yarn build:base" --mutantDir tmp/jetton/base-minter

analyze_mutants src/contracts/base/jetton-minter.tact \
  "yarn build:base && npx jest --runInBand src/tests/base -t \"Base Jetton\"" \
  --mutantDir tmp/jetton/base-minter \
  --prefix base-minter
```

From outer/repository root with explicit working directory:

```bash
cd path/to/target-project

mutate src/contracts/base/jetton-minter.tact tact --cmd "yarn build:base" --mutantDir tmp/jetton/base-minter

analyze_mutants src/contracts/base/jetton-minter.tact \
  "yarn build:base && npx jest --runInBand src/tests/base -t \"Base Jetton\"" \
  --mutantDir tmp/jetton/base-minter \
  --prefix base-minter
```

## Tact / Blueprint Generated Output Preflight

Use this before a full Tact/Blueprint analyze run when tests import generated wrappers or output such as `src/output/...`.

Baseline:

```powershell
yarn build:base
npx jest --runInBand src/tests/base -t "Base Jetton"
```

Mutation visibility smoke test:

```powershell
$cmd = 'yarn build:base && npx jest --runInBand src/tests/base -t "Base Jetton"'
analyze_mutants "src/contracts/base/jetton-minter.tact" $cmd --mutantDir "mutants" --numMutants 3 --noShuffle --prefix "smoke"
```

Before trusting the smoke result, answer: Does the test command see the mutated source through a rebuild of generated output? If the answer is no or unclear, do not trust the mutation score.

If a smoke run gives `0 killed` on obviously strong mutants, such as authorization checks, supply math, balance accounting, sender validation, opcode routing, or deploy/init logic, first check whether the analyze command rebuilds generated output before running tests.

## Acton Tolk Smoke

Use this as the first end-to-end probe for an Acton-based Tolk repository.

If your installed `mutate --help` confirms `tolk`, use a template like:

```sh
mkdir -p mutants-smoke logs

mutate contracts/src/<Contract>.tolk tolk \
  --cmd "acton build" \
  --mutantDir mutants-smoke

analyze_mutants contracts/src/<Contract>.tolk \
  "acton test" \
  --mutantDir mutants-smoke \
  --prefix smoke \
  --numMutants 5 \
  --timeout 60 \
  >logs/smoke.out 2>logs/smoke.err
```

Otherwise first verify or install the TON-enabled build. Use this only after `analyze_mutants --help` confirms `--numMutants` and `--timeout`.

## Acton Tolk Full Run

Promote the smoke template into a real run only after the small sample behaves cleanly.

If your installed `mutate --help` confirms `tolk`, use a template like:

```sh
mkdir -p mutants-<name> logs

mutate contracts/src/<Contract>.tolk tolk \
  --cmd "acton build" \
  --mutantDir mutants-<name>

analyze_mutants contracts/src/<Contract>.tolk \
  "acton test" \
  --mutantDir mutants-<name> \
  --prefix <name> \
  >logs/<name>.out 2>logs/<name>.err
```

Otherwise first verify or install the TON-enabled build.

## Blueprint Tact Smoke

Use this as the first end-to-end probe before a large run.

If your installed `mutate --help` confirms `tact`, use a template like:

```sh
mkdir -p mutants-smoke logs

mutate contracts/<Contract>.tact tact \
  --cmd "<package-manager> run <build-script>" \
  --mutantDir mutants-smoke

analyze_mutants contracts/<Contract>.tact \
  "<build command> && npx jest --runInBand <test path> -t \"<test name>\"" \
  --mutantDir mutants-smoke \
  --prefix smoke \
  --numMutants 5 \
  --timeout 60 \
  >logs/smoke.out 2>logs/smoke.err
```

Otherwise first verify or install the TON-enabled build. Use this only after `analyze_mutants --help` confirms `--numMutants` and `--timeout`. Replace `<build command>` with the command that rebuilds generated output.

## Blueprint Tact Full Run

Promote the smoke template into a real run only after the small sample behaves cleanly.

If your installed `mutate --help` confirms `tact`, use a template like:

```sh
mkdir -p mutants-<name> logs

mutate contracts/<Contract>.tact tact \
  --cmd "<package-manager> run <build-script>" \
  --mutantDir mutants-<name>

analyze_mutants contracts/<Contract>.tact \
  "<build command> && npx jest --runInBand <test path> -t \"<test name>\"" \
  --mutantDir mutants-<name> \
  --prefix <name> \
  >logs/<name>.out 2>logs/<name>.err
```

Otherwise first verify or install the TON-enabled build. If the repository has no reliable package script, fall back to an explicit command such as `npx blueprint build --all && npx jest --runInBand <test path> -t "<test name>"`.

## FunC Entrypoint Compile Override

Use this when the mutated file is not a standalone entrypoint and the real compile command must include includes or sibling files.

If your installed `mutate --help` confirms `func`, use a template like:

```sh
mutate contracts/<path>/<entrypoint>.fc func \
  --cmd '<real func compile command including includes and entrypoint>' \
  --mutantDir mutants-<name>
```

Otherwise first verify or install the TON-enabled build. Keep the compile override aligned with the real project entrypoint, not just the mutated file path.

## Show Survivors

Inspect survivor diffs before calling them low-value or equivalent.

```sh
show_mutants <prefix>.notkilled.txt \
  --mutantDir mutants-<name> \
  --sourceDir contracts \
  --concise
```

If the source directory is not `contracts`, replace it with the actual root used by `show_mutants`.

## Prioritized Rerun

Use this after a broad run when survivors need a focused second pass.

```sh
prioritize_mutants <prefix>.notkilled.txt prioritized.txt 20 \
  --mutantDir mutants-<name> \
  --sourceDir contracts

analyze_mutants contracts/<Contract>.tact "<test command>" \
  --mutantDir mutants-<name> \
  --fromFile prioritized.txt \
  --prefix rerun-prioritized
```

Use `--fromFile` only after `analyze_mutants --help` confirms it in the installed CLI.

## Timeout Triage

Use a narrower, deterministic test command before assuming a timeout is meaningful.

```sh
analyze_mutants contracts/<Contract>.tact "<narrow deterministic test command>" \
  --mutantDir mutants-<name> \
  --fromFile timeout-suspects.txt \
  --prefix timeout-rerun \
  --timeout <verified-seconds> \
  --noShuffle
```

Use this only after `analyze_mutants --help` confirms `--fromFile`, `--timeout`, and `--noShuffle`.
