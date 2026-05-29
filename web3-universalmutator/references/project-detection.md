# Project Detection

## Contents

- [Detection Algorithm](#detection-algorithm)
- [Root-Level Scan](#root-level-scan)
- [Campaign Scope Policy](#campaign-scope-policy)
- [Classify The Project](#classify-the-project)
- [Inspect `package.json`](#inspect-packagejson)
- [Find Compile And Test Commands](#find-compile-and-test-commands)
- [Blueprint Mapping Strategy](#blueprint-mapping-strategy)
- [Handle Ambiguity Safely](#handle-ambiguity-safely)

Use this file before choosing commands. The goal is to identify whether the repository is a supported Web3 smart-contract project, find the real compile or test command, and avoid a mutation run against the wrong target. When you want a deterministic first pass, run `scripts/detect_project.py` before doing the same reasoning manually.

This skill supports only these Web3 language families:

- TON: Tact (`.tact`), Tolk (`.tolk`), FunC (`.fc`, `.func`)
- EVM: Solidity (`.sol`), Vyper (`.vy`), Fe (`.fe`)

## Campaign Scope Policy

Default Web3 mutation campaigns are entrypoint-first. If the user gives a directory, treat it as a contract-family scope and choose the main deployable or callable entrypoint contracts under it. Do not mutate every shared source file in a contract directory by default.

For TON folders, classify files with wrappers/tests or contract-like names as entrypoints. Classify files named like `errors`, `messages`, `storage`, `fees-management`, `constants`, `utils`, or include/library folders as shared dependencies unless the user explicitly targets them.

For EVM folders, prefer source contracts that have a direct test mapping or deployable/callable contract role. Treat libraries, interfaces, generated files, test helpers, and shared constants as dependencies unless the user asks for a deeper shared-dependency pass.

Explicit target paths override project-family detection. A `.sol`, `.vy`, or `.fe` target uses the EVM route even in a mixed TON repository; a `.tact`, `.tolk`, `.fc`, or `.func` target uses the TON route.

Every plan for a directory must record:

- requested scope
- executed scope
- entrypoint targets selected
- Shared dependency files observed but not mutated by default
- completeness label, using `entrypoint-focused-not-full-directory` when appropriate

Do not describe an entrypoint-focused campaign as full directory coverage. A shared-dependency pass is a separate follow-up mode, not the default.

## Detection Algorithm

1. Inspect the repository root.
2. Find `package.json`, lock files, build files, and config files.
3. Check for TON, Acton, and Blueprint markers.
4. Check whether contract or source directories exist.
5. Split entrypoint contracts from shared dependency files.
6. Inspect scripts in `package.json` or equivalent build files.
7. Choose the compile command and the test command from explicit project artifacts.
8. If still ambiguous, choose the safest narrow default and ask the user only if the risk of a wrong command is high.

## Root-Level Scan

Look for:

- `package.json`
- `pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`
- `bun.lockb`, `bun.lock`
- `blueprint.config.*`
- `Acton.toml`
- `foundry.toml`
- `hardhat.config.*`
- `truffle-config.*`
- `jest.config.*`
- `tsconfig.json`
- `Cargo.toml`
- `go.mod`
- `pom.xml`
- `build.gradle`, `build.gradle.kts`
- `Package.swift`
- `DESCRIPTION`
- `fpm.toml`
- `Makefile`, `justfile`
- language markers such as `.tact`, `.tolk`, `.fc`, `.func`, `.py`, `.rs`, `.go`, `.sol`, `.vy`, `.fe`
- directories such as `contracts/`, `wrappers/`, `tests/`, `src/`, `lib/`

## Classify The Project

### Non-Web3 project

Signals:

- regular source directories such as `src/` or `lib/`
- language-specific files without TON or EVM smart-contract markers
- README or build files describing compile and test commands

Approach:

- treat it as out of scope for this skill
- do not construct a generic Universal Mutator plan
- tell the user that this skill is limited to TON and EVM smart-contract mutation testing

### TON project

Signals:

- `.tact`, `.tolk`, `.fc`, or `.func` files
- `contracts/` directory
- `contracts/src/` in Acton-style Tolk projects
- TypeScript wrappers or tests related to contract names

Approach:

- switch to [ton.md](ton.md)
- switch to [mutation-rules.md](mutation-rules.md) if the user asks what TON mutation families exist
- use `mutate <sourcefile> <tact|tolk|func> --mutantDir ...`
- choose compile overrides through `--cmd` or the documented `UM_*_CMD` variables when needed

### Acton TON project

Strong signals:

- `Acton.toml`
- `contracts/src/` containing `.tolk`
- `tests/` containing `.test.tolk`
- scripts or docs invoking `acton build` or `acton test`

Preferred commands:

- compile: `acton build`
- test: `acton test`
- prefer direct `acton` commands even if `package.json` wraps them, because Universal Mutator compile-check and analyze loops should stay narrow and avoid unrelated frontend builds
- ruleset expectation: `ton_common.rules` plus `tolk.rules`

Contract selection:

- start from a concrete contract under `contracts/src/`
- map it to `wrappers/<Contract>.gen.tolk` or `wrappers-ts/<Contract>.ts` when available
- map it to `tests/<Contract>.test.tolk` before falling back to the full `acton test` suite

### Blueprint TON project

Strong signals:

- `blueprint.config.*`
- `package.json` scripts containing `blueprint`
- the layout `contracts/`, `wrappers/`, `tests/`

Preferred commands:

- compile: prefer a repository script first, such as `pnpm run build:contracts`, `yarn build`, `bun run build`, or `npm run build`
- test: prefer a repository script first, such as `pnpm run test:contracts`, `yarn test`, `bun run test`, or `npm run test`
- fallback: use `npx blueprint build --all` and `npx blueprint test` only when suitable scripts are missing
- ruleset expectation: `ton_common.rules` plus the language-specific TON file, not the generic `universal.rules + c_like.rules` stack

Contract selection:

- start from a concrete contract under `contracts/`
- map it to a wrapper and test file by name or behavior
- use the full Blueprint test command first if the mapping is uncertain

### TypeScript and Jest project

Signals:

- `package.json`
- `jest.config.*`
- `tsconfig.json`
- tests in `tests/` or `*.spec.ts`

Approach:

- look for a project script such as `test`, `test:unit`, or `test:contracts`
- if a single test file clearly maps to the target, a narrower command can be useful for subset re-runs

### Solidity and EVM project

Common detections:

- Foundry: `foundry.toml`
- Hardhat: `hardhat.config.*`
- Truffle: `truffle-config.*`
- source-level Solidity, Vyper, or Fe repo: source files such as `.sol`, `.vy`, `.fe` without a stronger framework marker

Preferred commands:

- Foundry: `forge build`, `forge test`
- Hardhat: prefer package scripts first, otherwise `npx hardhat compile`, `npx hardhat test`
- Truffle: prefer package scripts first, otherwise `npx truffle compile`, `npx truffle test`
- source-level Solidity, Vyper, or Fe: prefer repository scripts or the documented project command instead of guessing a framework

Notes:

- A Hardhat or Truffle repo may still use `pnpm`, `yarn`, `bun`, or `npm` for the surrounding project scripts.
- For Foundry targeted tests, prefer `forge test --match-path '<test-file>'` when a direct mapping exists.
- For Hardhat targeted tests, prefer `npx hardhat test '<test-file>'`, or the repository test script with a test-file argument when that is the detected route.
- For Truffle targeted tests, prefer `npx truffle test '<test-file>'`.
- Skip `interfaces/`, `mocks/`, `test/`, `tests/`, `script/`, `scripts/`, `generated/`, `lib/`, and `libraries/` by default unless the user explicitly targets a file there.
- If source files are `.vy` or `.fe` but no framework marker exists, keep the project type narrow and ask only if the test command cannot be recovered from repo files.

### Unsupported Rust project

Signals:

- `Cargo.toml`

Action: mark out of scope unless the Rust code is only a wrapper around supported TON or EVM contracts.

### Unsupported Go project

Signals:

- `go.mod`

Action: mark out of scope unless the Go code is only a wrapper around supported TON or EVM contracts.

### Unsupported Java project

Signals:

- Maven: `pom.xml`
- Gradle: `build.gradle`, `build.gradle.kts`, or related settings files

Action: mark out of scope.

### Unsupported Swift project

Signals:

- `Package.swift`

Action: mark out of scope.

### Unsupported R project

Signals:

- `DESCRIPTION`

Action: mark out of scope.

### Unsupported Fortran project

Signals:

- `fpm.toml`

Action: mark out of scope.

### Other obvious non-Web3 project types

Examples:

- Python: out of scope
- Rust: out of scope unless it is only a helper around supported Web3 contracts
- Go: out of scope unless it is only a helper around supported Web3 contracts
- Swift, Java, R, Fortran: out of scope
- Solidity framework repos: supported when they use `forge test`, `npx hardhat test`, or `npx truffle test`

For supported Web3 repositories, prefer the command already used by the repository to prove correctness.

## Inspect `package.json`

When `package.json` exists, check:

- `scripts.test`
- build scripts
- Blueprint-specific scripts
- Jest-specific scripts
- wrapper or contract-specific test scripts

Use scripts as the first source of truth. If `package.json` and the README disagree, prefer the script that the repository actually runs successfully.

When lockfiles or the `packageManager` field are present, infer the package manager before constructing the command string:

- `pnpm-lock.yaml` -> `pnpm`
- `yarn.lock` -> `yarn`
- `bun.lockb` or `bun.lock` -> `bun`
- `package-lock.json` -> `npm`
- `packageManager: "pnpm@..."`, `"yarn@..."`, `"npm@..."`, or `"bun@..."` -> that manager

If no lockfile or `packageManager` field exists, do not assume npm purely because `package.json` exists. Mark `package_manager_ambiguous: true`; prefer direct framework commands such as `npx hardhat test` or ask for the intended package manager when a package script is necessary.

Script invocation style:

- `pnpm run <script>`
- `yarn <script>`
- `bun run <script>`
- `npm run <script>`

Helpful automation:

```sh
python scripts/detect_project.py .
python scripts/detect_project.py . --format json
```

## Find Compile And Test Commands

Use this order:

1. `package.json` scripts or dedicated build files
2. Web3 framework config markers such as `foundry.toml`, `hardhat.config.*`, `truffle-config.*`, `blueprint.config.*`, or `Acton.toml`
3. repository README for the project under test
4. obvious tool defaults already used by the codebase
5. a narrow fallback command that only targets the current file or contract

Examples of safe Web3 defaults:

- Acton contract: `acton test`
- Blueprint contract: `npx blueprint test`
- Foundry repo: `forge test`
- Hardhat repo: `npx hardhat test`
- Truffle repo: `npx truffle test`

Do not invent undocumented Universal Mutator flags to compensate for unclear project commands.

## Blueprint Mapping Strategy

### Strong signals

Treat these as strongest Blueprint indicators:

- `blueprint.config.*`
- `npx blueprint build` in scripts or docs
- `npx blueprint test` in scripts or docs

### How to pick the contract

1. Prefer the contract actively being changed.
2. Otherwise pick the contract with the clearest wrapper and test mapping.
3. If several contracts share infrastructure, split them into separate runs rather than one mixed directory plan.
4. When several contracts need mutation testing, prefer separate terminals or separate agents with isolated `--mutantDir` values and logs.

### How to map contract, wrapper, and test

Use this order:

1. same or similar basename
2. wrapper imports or comments referencing the contract
3. tests importing the wrapper or referencing the contract behavior
4. package scripts targeting a named test file

If that mapping is weak, use the broader Blueprint test command instead of pretending the one-file test is authoritative.

## Handle Ambiguity Safely

When detection is ambiguous:

- choose a narrow target file
- choose the least destructive compile or test command that still reflects real project behavior
- run one mutation slice first
- scale to separate terminals or agents only after one target completes cleanly
- ask the user only if the repository artifacts do not reveal a trustworthy compile or test command

Good escalation case:

- several competing test scripts exist and it is unclear which one is the contract-quality gate

Bad escalation case:

- the repository already has an obvious `npx blueprint test`, `acton test`, `forge test`, or `npx hardhat test` command and you simply have not inspected it yet
