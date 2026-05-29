# Web3 UniversalMutator

Short description: `web3-universalmutator` helps agents plan, run, troubleshoot, and summarize Web3 smart-contract mutation testing with Universal Mutator.

Version: see `VERSION`.

It is focused on:

- TON contracts: Tact, Tolk, FunC, Blueprint, and Acton-style projects.
- EVM contracts: Solidity, Vyper, Fe, Foundry, Hardhat, Truffle, and source-level workflows.
- Safe campaign planning with explicit targets, isolated mutant directories, verified command capabilities, and durable reports.

Runtime note:

- This bundle does not include Universal Mutator itself. Users need a local Universal Mutator installation that exposes the commands and flags used by the selected workflow.
- EVM/Solidity workflows are the most mature path: standard Foundry, Hardhat, Truffle, and source-level Solidity projects usually work when local Universal Mutator capabilities are verified.
- TON workflows are available but environment-dependent. Direct Tact, Tolk, and FunC mutation requires a Universal Mutator build or fork whose `mutate --help` output or installed rule files confirm TON language support.
- Mutation testing measures whether tests notice injected source changes. It is not fuzzing and does not replace a smart-contract security audit.

Main modes:

- Manual planning: detect the project and produce a mutation campaign plan.
- Smoke campaign: run a bounded first pass before a longer analysis.
- Full campaign: run the selected target through mutation generation and analysis.
- All-entrypoints campaign: handle directory targets by mutating entrypoint contracts one by one.
- Custom-rules pass: propose, validate, and use project-specific `.rules` files when useful.
- Artifact/report mode: collect result files and refresh `mutants/REPORT.md`.

Typical outputs are mutant directories under `mutants/`, killed and surviving mutant lists, campaign metadata, logs, summaries, and the aggregate `mutants/REPORT.md`.

Important boundaries:

- This skill is for Web3 mutation testing, not generic source mutation.
- Mutation testing is not fuzzing and does not replace a security audit.
- Campaigns are entrypoint-first by default; shared dependency files are recorded but not mutated unless explicitly requested.
- Live analysis can temporarily swap source files, so clean trees or isolated worktrees are preferred.

Start with `SKILL.md`; load only the reference file that matches the target repository and task.
