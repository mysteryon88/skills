# Result File Formats

## Contents

- [Core Universal Mutator Text Files](#core-universal-mutator-text-files)
- [Prefixed Variants](#prefixed-variants)
- [Logs](#logs)
- [Mutant Directories](#mutant-directories)
- [Required Report](#required-report)
- [Helper Script Outputs](#helper-script-outputs)
- [Practical Reading Order](#practical-reading-order)

## Core Universal Mutator Text Files

The most important result files are plain text lists of mutant paths or identifiers.

Common names:

- `killed.txt`
- `notkilled.txt`
- `not-killed.txt`

Treat these on-disk files as the source of truth. Helper scripts normalize `not-killed` to the logical `notkilled` result kind.

## Prefixed Variants

When the run uses `--prefix`, expect prefixed files such as:

- `<prefix>.killed.txt`
- `<prefix>.notkilled.txt`
- `<prefix>.not-killed.txt`

Use the prefixed file with matching logs and `--mutantDir` when running `show_mutants` or `prioritize_mutants`.

## Logs

Keep shell output separate from result lists:

- `logs/<prefix>.out`
- `logs/<prefix>.err`

Use logs for:

- compile failures
- timeout markers
- flaky test clues
- stack traces and infrastructure errors

Do not infer survivor meaning from logs alone when `show_mutants` can show the diff directly.

## Mutant Directories

Keep a unique mutant directory per target or rerun:

- `mutants/<safe-target-path>`
- `mutants/smoke`
- `mutants/minter`
- `mutants/wallet`

Do not reuse the same mutant directory for unrelated runs.

Autonomous campaign runs write nested artifacts:

```text
mutants/<campaign-slug>/plan.json
mutants/<campaign-slug>/manifest.json
mutants/<campaign-slug>/commands.sh
mutants/<campaign-slug>/capabilities.json
mutants/<campaign-slug>/artifacts.json
mutants/<campaign-slug>/run.log
mutants/<campaign-slug>/summary.md
```

`plan.json` is the static `plan_mutation_run` output. `manifest.json` is the live campaign state: schema version, status, timestamps, selected commands, mutate attempts, custom rules, and artifact pointers. Helper scripts prefer `manifest.json`; for backward compatibility they still understand older `plan.json` files that contained manifest-like fields.

When a manifest exists, helper scripts use it before guessing from filenames. `show_mutants` commands must use the run's actual mutant directory, for example:

```sh
show_mutants mutants/src-Vault-sol/src-Vault-sol.notkilled.txt --mutantDir mutants/src-Vault-sol
```

## Required Report

Keep the campaign report at `mutants/REPORT.md`.

After mutation generation, record the target, commands, total mutants, non-compiling mutants, fallback compile command, and logs. After analysis, update the same file with killed, survived, timeout, compile-error, and flaky counts plus survivor interpretation, likely test gaps, recommended tests, and next commands.

## Helper Script Outputs

The bundled helper scripts add structured outputs around the plain text files.

`scripts/detect_um_capabilities.py`:

- `--format json`
- `--format markdown`

`scripts/collect_mutation_artifacts.py`:

- `--format json`
- `--format markdown`

`scripts/summarize_results.py`:

- `--format json`
- `--format markdown`

`scripts/run_campaign.py`:

- writes static plan, campaign manifest, commands, capabilities, artifacts, logs, summaries, and report sections under `mutants/<campaign-slug>/`

These formats are helper outputs from the skill bundle, not native Universal Mutator result files.

## Practical Reading Order

Use this order for triage:

1. baseline logs if the run failed early
2. `<prefix>.notkilled.txt` or `notkilled.txt`
3. `show_mutants` on the survivors
4. `killed.txt` or `<prefix>.killed.txt` only when counts or comparisons matter
5. helper-script JSON or markdown when you need inventory or report scaffolding
