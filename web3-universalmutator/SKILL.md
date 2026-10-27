---
name: web3-universalmutator
description: "Use when the user specifically wants Web3 smart-contract mutation testing with Universal Mutator for TON or EVM projects: TON/Blueprint/Acton using Tact, Tolk, FunC; Solidity/EVM using Solidity, Vyper, Fe with Foundry, Hardhat, Truffle, or source-level workflows. Do not use for pure fuzzing, input generation, standalone Web3 audits, or generic non-Web3 Universal Mutator runs unless comparing fuzzing with mutation testing."
---

# web3-universalmutator

Use this skill to run, troubleshoot, and analyze Web3-focused Universal Mutator workflows without guessing undocumented behavior. It is intentionally not a general Universal Mutator skill: use it only for supported Web3 smart-contract languages and frameworks. Keep `SKILL.md` as the control surface and load only the reference file that matches the repository and task.
For snapshot-based multi-agent/background campaigns, use the coordinator when present; read [campaign integration](references/campaign-integration.md). The focused standalone helpers remain independently usable in an already isolated disposable checkout. A live dirty/non-Git checkout requires explicit `--allow-dirty`; this flag does not create isolation.
Do not use this skill for non-Web3 Universal Mutator runs, pure fuzzing, input generation, or standalone Web3 audit workflows unless the task is explicitly comparing fuzzing with mutation testing.

## Supported Web3 Languages

- TON: Tact (`.tact`), Tolk (`.tolk`), FunC (`.fc`, `.func`)
- EVM: Solidity (`.sol`), Vyper (`.vy`), Fe (`.fe`)

If the repository is Rust, Go, Python, Java, Swift, R, Fortran, TypeScript-only, or another non-Web3 codebase, stop after detection and say this skill is out of scope. Do not use this skill for non-Web3 Universal Mutator runs.

## Quick Workflows

Manual workflow:

```sh
python scripts/detect_project.py <repo>
python scripts/detect_um_capabilities.py --format markdown
python scripts/plan_mutation_run.py <repo> --target <target> --format markdown
```

Autonomous workflow:

```sh
python scripts/run_campaign.py <repo> --target <target> --mode smoke
python scripts/run_campaign.py <repo> --target <target> --mode full
python scripts/run_campaign.py <repo> --target contracts --all-entrypoints --mode smoke
```

Custom rule workflow:

```sh
python scripts/propose_custom_rules.py <repo> --target <target>
python scripts/propose_custom_rules.py <repo> --target <target> --write mutants/custom-rules/<slug>.rules
python scripts/validate_custom_rules.py <repo> --target <target> --rules mutants/custom-rules/<slug>.rules
python scripts/validate_custom_rules.py <repo> --target <target> --rules mutants/custom-rules/<slug>.rules --dry-run-mutants
python scripts/run_campaign.py <repo> --target <target> --custom-rules write-and-use
```

When running from outside the skill directory, keep skill and target repo paths explicit:

```sh
SKILL_DIR="/path/to/web3-universalmutator"
REPO="/path/to/project"
python "$SKILL_DIR/scripts/detect_project.py" "$REPO"
python "$SKILL_DIR/scripts/run_campaign.py" "$REPO" --target contracts/Vault.sol --mode smoke
```

## Campaign Scope Policy

Default Web3 mutation campaigns are entrypoint-first. If the user provides a contract directory, mutate the main deployable or callable contract entrypoints by default, not every supported source file in that directory. Do not mutate every shared source file in a contract directory by default.

Always enumerate shared dependency files such as `messages`, `storage`, `errors`, `fees`, `constants`, `utils`, libraries, interfaces, and include files. Mark them as "Shared dependency files observed but not mutated by default" unless the user explicitly requests a shared-dependency pass or a survivor points to that layer.

Do not describe an entrypoint-focused campaign as full directory coverage. Use a scope label such as `entrypoint-focused-not-full-directory` when a directory contains shared files that were intentionally left unmutated.

## Follow This Workflow

1. Read [references/safety.md](references/safety.md) before any run that might swap source files, write mutant directories, or reuse a dirty tree.
2. Determine the project type and confirm it is a supported Web3 smart-contract project.
3. Verify the installed Universal Mutator commands, language support, and local flag surface before writing language-specific commands.
4. Find the relevant supported source files or contracts, classify entrypoints separately from shared dependencies, and keep the default scope entrypoint-first.
5. Review the default rule stack for the selected language using [references/mutation-rules.md](references/mutation-rules.md).
6. Offer an optional custom mutation-rules pass when source-specific invariants might benefit from extra mutants. Explain that default mutation campaigns still work without custom rules.
7. If the user explicitly requested autonomous custom-rule generation, write custom rule files under `mutants/custom-rules/` and report what was written. Otherwise ask the user before writing a custom `.rules` file. Use custom rules as extra positional files in `mutate`; do not replace defaults unless the user asks for a focused custom-only experiment.
8. For manual planning, run `scripts/plan_mutation_run.py <repo> --target <optional-contract-or-file>` to choose the target, `mutants/<safe-target-path>` output directory, compile fallback, and narrow test command.
9. For autonomous requests, prefer `scripts/run_campaign.py <repo> --target <target> --mode smoke` first; use `--mode full` only after the smoke path and baseline command are trustworthy.
10. Treat planned `mutate` and `analyze_mutants` commands as templates until `scripts/detect_um_capabilities.py` confirms the command, language, and flag surface.
11. Run the generated preflight steps. Run the baseline test command immediately after tooling verification. Do not start mutation generation if the baseline tests fail.
12. Do not run `mutate` or `analyze_mutants` in parallel inside the same project checkout. Within an already isolated disposable checkout, keep execution sequential; isolate parallel targets in separate worktrees or copies such as `.tmp/um-runs/<target-slug>`.
13. Warn the user that mutation analysis can take a long time because the test command may run once per mutant and can look stuck while a slow test is executing.
14. Run the initial mutate command first so Universal Mutator performs its default compile check.
15. If the default compile check fails because direct language compilers such as `tolk-js`, `tact`, `func-js`, or Solidity tooling are missing or not enough for the project, inspect the failure and rerun with the first `fallback_mutate_commands` entry.
16. Create or update `mutants/REPORT.md` after mutation generation with the target, commands, total mutants, and non-compiling mutants.
17. Run `analyze_mutants` only after mutation generation produces compilable mutants, using the planned narrow test command rather than the whole suite when a mapped test exists.
18. Update `mutants/REPORT.md` after analysis with killed, survived, timeout, compile-error, and flaky counts, then add survivor interpretation and recommended tests.

## Load The Right Reference

- Read [references/safety.md](references/safety.md) before mutation runs in a live repository, especially when `analyze_mutants` may temporarily swap mutated files into place.
- Read [references/project-detection.md](references/project-detection.md) first when the repository type is unclear.
- Read [references/command-templates.md](references/command-templates.md) when you need preflight, smoke, full-run, survivor-rerun, or timeout-triage command scaffolds.
- Read [references/cli.md](references/cli.md) for Web3 Universal Mutator commands, documented flags, output handling, `--swap`, and concurrent-run recipes.
- Read [references/ton.md](references/ton.md) when the repository appears to be TON, Acton, Blueprint, FunC, Tolk, Tact, or a TypeScript-based TON wrapper project.
- Read [references/evm.md](references/evm.md) when the repository appears to be Foundry, Hardhat, Truffle, Solidity, Vyper, Fe, or a mixed EVM monorepo.
- Read [references/ton-contract-checklists.md](references/ton-contract-checklists.md) when survivors need contract-type-specific test ideas for jettons, wallets, bridges, governance, or other TON patterns.
- Read [references/evm-contract-checklists.md](references/evm-contract-checklists.md) when EVM survivors need contract-type-specific test ideas for tokens, vaults, access control, upgradeability, markets, bridges, governance, signatures, fees, rounding, or decimals.
- Read [references/mutation-rules.md](references/mutation-rules.md) when the task is about which mutation families exist, which rule files are loaded for a language, how to ideate optional custom `.rules` files, or how to explain a surviving mutant in terms of its originating rule stack.
- Read [references/custom-rule-syntax.md](references/custom-rule-syntax.md), [references/custom-rule-examples-evm.md](references/custom-rule-examples-evm.md), or [references/custom-rule-examples-ton.md](references/custom-rule-examples-ton.md) when generating or reviewing project-specific custom rules.
- Read [references/analysis.md](references/analysis.md) after `analyze_mutants`, `show_mutants`, or any triage pass over surviving mutants.
- Read [references/result-file-formats.md](references/result-file-formats.md) when you need to interpret `killed.txt`, `notkilled.txt`, prefixed variants, logs, or helper-script JSON and markdown output.
- Read [references/troubleshooting.md](references/troubleshooting.md) when commands are missing, TON language support is unclear, tests are flaky, or timeouts and compile failures dominate the run.
- Read [references/fuzzing-vs-mutation.md](references/fuzzing-vs-mutation.md) when the user mentions fuzzing, input generation, or a combined fuzzing-plus-mutation workflow.
- Read [references/helper-scripts.md](references/helper-scripts.md) when reproducibility matters and the bundled helper scripts can save time.

Use the CLI reference for supported Web3 projects; use the TON reference when the target is Tact, Tolk, or FunC, and the EVM reference when the target is Solidity, Vyper, or Fe. Explicit target paths override repository-family detection.

## Anti-Hallucination Rules

- Do not assume the public PyPI universalmutator supports TON. Before using `tact`, `tolk`, or `func` as language arguments, verify one of:
  1. `mutate --help` lists the language;
  2. installed package contains `static/tact.rules`, `static/tolk.rules`, or `static/func.rules`;
  3. the user explicitly says they use a TON-enabled fork/build.
- If TON support is not verified, say: “Your installed universalmutator may not support TON directly. I can still help design a mutation workflow, but these TON-specific commands require verification or a TON-enabled fork.”
- When local capability is unknown, phrase commands as templates, not facts: “If your installed `mutate --help` confirms `<flag/language>`, use... Otherwise first verify or install the TON-enabled build.”
- Do not state that `UM_TACT_CMD`, `UM_TOLK_CMD`, `UM_FUNC_CMD`, `mutate contracts/X.tact tact`, or similar TON-specific invocation patterns will work unless local help, installed rule files, or the user confirms a TON-enabled build.
- Never invent CLI flags. Classify every flag as one of:
  - confirmed by local `--help`
  - confirmed by bundled reference
  - project-local/fork-specific
  - unconfirmed; do not use without verification
- Treat `--showRules`, `--printStat`, and `--only` as locally verified or fork-specific until the installed `mutate --help` confirms them.
- `--timeout`, `--fromFile`, and `--noShuffle` must be treated as locally verified `analyze_mutants` flags. Run `analyze_mutants --help` before using them.
- Do not call a survivor `equivalent` unless the diff has been inspected and no observable assertion can distinguish it.
- Do not claim mutation score proves contract security. Mutation testing measures test sensitivity to injected changes; it is not an audit.
- Do not confuse mutation testing with fuzzing. Universalmutator mutates source code; fuzzers generate inputs/messages.
- Do not generalize this skill to non-Web3 source languages even if the installed Universal Mutator has rules for them.
- Explicit target paths override project-family detection. A `.sol`, `.vy`, or `.fe` target must use the EVM route even in a mixed TON repository; a `.tact`, `.tolk`, `.fc`, or `.func` target must use the TON route.

## Operating Rules

- Prefer documented file- or contract-level workflows. Do not assume undocumented directory-wide mutation support.
- Default Web3 mutation campaigns are entrypoint-first. Do not mutate every shared source file in a contract directory by default, and do not describe an entrypoint-focused campaign as full directory coverage.
- Treat the bundled references in this skill as the command baseline for Web3 CLI usage, TON usage, EVM usage, and result interpretation.
- Treat the local rule files under `universalmutator/static/` and `universalmutator/comby/` plus the current `genmutants.py` selection logic as the primary source for which mutation families actually exist.
- Treat custom `.rules` files as optional campaign extensions. Do not write or run them unless the user asks for them or accepts the optional custom-rules pass.
- Treat [references/command-templates.md](references/command-templates.md) as scaffolding, not proof that every installed CLI exposes every flag. Verify locally before locking in a command.
- If a flag, exit-code meaning, or dry-run mode is not confirmed by the bundled references or the current repository source, mark it as not confirmed instead of inventing behavior.
- Do not advise a command or flag unless `scripts/detect_um_capabilities.py` confirms it, local help confirms it, or the relevant reference explicitly marks it as version-dependent.
- Keep mutation and analysis sequential inside one project checkout. Parallel mutation or analysis in the same checkout can corrupt swapped files, shared build artifacts, generated wrappers, compile caches, or test state.
- Before analysis require an isolated worktree/copy; a clean original checkout alone does not preserve it during source swaps.
- Never suggest commands containing `rm`, `git clean`, or other destructive cleanup shortcuts as part of a mutation workflow.
- Verify that one target completes the full mutate plus analyze cycle before considering isolated parallel runs.
- After mutation generation and after analysis, write or update `mutants/REPORT.md`; this report is the durable handoff, not an optional chat-only summary.
- Prefer a narrow compile or test command for a single target when it is trustworthy; fall back to a broader command when integration behavior matters.
- Treat `--noCheck` as a last-resort noise tradeoff, because it can generate a much larger and less actionable mutant set.
- Prefer expanding package scripts into explicit build + narrow test commands when mutation testing generated-contract projects. Do not stop at `yarn test:base` without checking whether it rebuilds generated contract output and whether Jest runs in-band.
- Use the bundled helper scripts when they improve consistency:
  - `scripts/detect_um_capabilities.py` for checking whether the installed Universal Mutator environment actually exposes the expected commands, mutate flags, `analyze_mutants` flags, and TON language support
  - `scripts/detect_project.py` for layout and command hints
  - `scripts/plan_mutation_run.py` for autopilot routing from project detection to `initial_mutate_command`, `fallback_mutate_commands`, `mutants/<safe-target-path>`, and narrow `analyze_mutants`
  - `scripts/run_campaign.py` for autonomous smoke/full campaigns that write `mutants/<campaign-slug>/plan.json`, `manifest.json`, `commands.sh`, `capabilities.json`, `artifacts.json`, `run.log`, `summary.md`, and update `mutants/REPORT.md`
  - `scripts/propose_custom_rules.py` and `scripts/validate_custom_rules.py` for project-specific custom rule generation, match analysis, and optional temporary dry-run validation
  - `scripts/collect_mutation_artifacts.py` for artifact inventory
  - `scripts/summarize_results.py` for canonical report scaffolding
- When a user asks what mutants exist for a language, answer in terms of loaded rule layers first, then the most important mutation families, then any repository-local exhaustive tables if they are available.
- Use the canonical final report shape from [references/analysis.md](references/analysis.md): `Target`, `Scope`, `Commands`, `Results`, `Survivors`, `Likely gaps`, `Recommended tests`, `Next commands`.
- Treat the tool as cross-platform for Windows and Linux, but treat `--comby` as a Linux or WSL workflow on Windows because the external `comby` binary should not be assumed to work natively there.
- After a TON run, translate surviving mutants into missing message, storage, deploy, opcode, and negative-test coverage suggestions rather than only restating filenames, and use [references/ton-contract-checklists.md](references/ton-contract-checklists.md) when the contract class matters.
