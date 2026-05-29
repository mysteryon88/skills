# Safety

## Contents

- [Why Safety Matters Here](#why-safety-matters-here)
- [Clean Git Tree](#clean-git-tree)
- [Isolated Worktree](#isolated-worktree)
- [Sequential Runs In One Checkout](#sequential-runs-in-one-checkout)
- [Temp Dirs And Output Layout](#temp-dirs-and-output-layout)
- [Backups And File Swapping](#backups-and-file-swapping)
- [No Destructive Commands](#no-destructive-commands)
- [No Audit Claims](#no-audit-claims)

## Why Safety Matters Here

`analyze_mutants` often validates mutants by temporarily swapping them into the original source location unless the command explicitly uses `MUTANT`. Treat that as a write-risk to the working tree, not as a read-only analysis.

Before any `analyze_mutants` run, require a clean tree or isolated worktree.

## Clean Git Tree

Prefer a clean baseline before long mutation runs:

```sh
git status --short
```

If the tree is dirty:

- do not revert user work without permission
- keep the run narrow or move it to a worktree
- keep logs and mutant directories separate so artifacts do not hide real edits

## Isolated Worktree

When the repository matters and the run may be noisy, prefer an isolated worktree:

```sh
git worktree add ../repo-muttest -b mutation-testing/<target>
cd ../repo-muttest
```

This reduces the chance of mixing source edits, generated mutants, and log files with the user's active branch.

## Sequential Runs In One Checkout

Do not run `mutate` or `analyze_mutants` in parallel inside the same project checkout. Universal Mutator workflows can swap source files, rebuild generated wrappers, update shared build caches, and run tests against project-local temporary files. Parallel runs in one checkout can break compilation or make test results meaningless.

Run one mutation target at a time in a checkout. If parallel work is necessary, isolate each target with a separate `git worktree` or copy the repository into `.tmp/um-runs/<target-slug>` and run the full mutate plus analyze sequence inside that copy. Keep the copied checkout out of test discovery and build globs.

## Temp Dirs And Output Layout

Use explicit directories from the start:

- `mutants/<safe-target-path>/` for one target
- `mutants/REPORT.md` for the required campaign report
- `logs/<name>.out` and `logs/<name>.err` for one run
- `prioritized.txt` or `timeout-suspects.txt` for one rerun plan

Do not reuse one `--mutantDir` across unrelated runs.

## Backups And File Swapping

Because analysis may swap files in place:

- Run the baseline test command immediately after tooling verification.
- Do not start mutation generation if the baseline tests fail.
- verify the baseline build or test command before mutation
- prefer a clean worktree or copy before large runs
- if a run is interrupted, inspect the target file and `git diff` before assuming restoration succeeded
- preserve logs when debugging suspicious restore behavior

## No Destructive Commands

Do not use destructive cleanup as part of the workflow description.

Avoid:

- commands containing `rm` or `git clean` as workflow shortcuts
- `git reset --hard`
- `git checkout -- <path>`
- recursive delete commands that are broader than the named mutant or log directory

Prefer explicit cleanup of known generated directories only after the user agrees and the path is verified.

## No Audit Claims

Mutation testing is not a security audit.

Do not claim:

- a high mutation score proves contract security
- a surviving mutant is harmless without inspection
- a completed mutation run replaces review, fuzzing, formal methods, or audit work

Use accurate language instead:

- mutation testing measures how sensitively the test suite reacts to injected source changes
- survivors suggest test gaps or possibly equivalent behavior
- security conclusions require separate evidence
