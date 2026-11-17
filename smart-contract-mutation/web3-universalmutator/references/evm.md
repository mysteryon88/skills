# EVM Workflows

## Contents

- [Detection](#detection)
- [Target Selection](#target-selection)
- [Commands](#commands)
- [Mixed Repositories](#mixed-repositories)
- [Contract Checklists](#contract-checklists)

## Detection

Use this reference for Solidity, Vyper, Fe, Foundry, Hardhat, Truffle, and mixed EVM monorepos. Explicit target paths win over repository-family detection:

- `.sol` -> Solidity / EVM
- `.vy` -> Vyper / EVM
- `.fe` -> Fe / EVM

Do not let Blueprint, Acton, or other TON markers override an explicit EVM source target.

## Target Selection

Default EVM selection priority:

1. Explicit user target.
2. Source file with a direct test mapping.
3. Deployable-looking contract source.
4. Skip interfaces, libraries, mocks, tests, scripts, generated files, and vendored libraries unless explicitly targeted.
5. Fallback to sorted supported source files.

For Solidity, prefer files containing `contract Name` over files that only contain `interface Name`, `library Name`, or `abstract contract Name`.

Common source locations:

- `src/`
- `contracts/`
- `packages/*/src/`
- `packages/*/contracts/`
- `apps/*/contracts/`

Common test locations:

- `test/`
- `tests/`
- `contracts/test/`

## Commands

Foundry:

```sh
forge build
forge test
forge test --match-path 'test/Vault.t.sol'
```

Hardhat:

```sh
npm test
npx hardhat test
npx hardhat test 'test/Vault.ts'
npx hardhat test 'test/Vault.js'
```

Truffle:

```sh
npx truffle test
npx truffle test 'test/Vault.test.js'
```

Package-manager scripts are allowed when lockfiles or the `packageManager` field identify the manager: `pnpm`, `yarn`, `npm`, or `bun` only when clearly present. Do not invent a package manager when lockfiles and `packageManager` are absent. If `package.json` exists but the manager is ambiguous, prefer direct framework commands such as `npx hardhat test` or `npx truffle test`.

## Mixed Repositories

For a repository containing both TON and EVM files, route by explicit target extension. Example: `src/Vault.sol` must produce a Solidity/EVM plan even if `contracts/A.tact` and Blueprint files exist.

## Contract Checklists

For EVM survivor triage and custom rule ideation, use [evm-contract-checklists.md](evm-contract-checklists.md). It covers mutation-testing questions for ERC20/ERC721/ERC1155, ERC4626 vaults, access control, upgradeable proxies, pausable contracts, oracles and stale prices, AMMs and slippage, staking rewards, bridges, governance, permit/signatures, fee logic, rounding, and decimals.
