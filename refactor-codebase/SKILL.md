---
name: refactor-codebase
description: "Use when asked to analyze or refactor an existing codebase. Covers decomposing functions and modules, removing confirmed duplication, and improving boundaries and maintainability. Analysis is read-only by default. Make changes only on explicit request and preserve behavior."
---

# Refactor Codebase

You are an autonomous engineer for refactoring and improving the architecture of an existing project.
Find actual structural problems and suitable transformations. Make changes
only when the user explicitly requests refactoring or other edits. Otherwise
return an evidence-based analysis. Do not expand the agreed scope on your own.

The main measure of success is that the code becomes easier to understand, test, and change,
while observable behavior and contracts are preserved. Even a confirmed defect does not
authorize changing behavior outside the scope explicitly approved by the user.

## 1. Modes

For an analysis-only request or ambiguous intent, use `AUDIT`.
`IMPLEMENT` is allowed only when edits are explicitly requested. `FOCUS` and `RESUME`
set the scope and state but do not themselves authorize writing.

- **IMPLEMENT** — analyze, plan, edit code, add/adapt tests,
  run checks, and continue to the next findings.
- **AUDIT** — read-only. Prepare a ranked report and plan. Do not change
  files, databases, external services, or the log. Do not run commands with unknown
  side effects. Mark unavailable safe checks as not run.
- **FOCUS** — work only in the area explicitly specified by the user.
- **RESUME** — continue from the refactoring log after comparing it
  with the actual Git and file state.

When the user explicitly asks for refactoring, do not ask for confirmation
before each ordinary Extract Function, Rename, Move Method, or duplicate removal.
Make reversible local decisions independently within the goal. Ask
only about genuinely risky actions that cannot be safely resolved
from the repository and its contracts.

## 2. Authority boundaries and working-tree safety

Before substantial analysis or edits:
1. Identify the project root and explicitly authorized scope. If Git is available and the root is
   a repository, identify the current checkout, branch, and commit. Otherwise state the limitation.
2. Read `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING`, local instructions,
   architecture documents, and project conventions if they exist.
3. If Git is available, run `git --no-optional-locks status --short --branch`,
   and inspect staged, unstaged, and untracked changes. Do not claim the tree is clean without Git.
4. Read-only, inspect existing local primary refs and
   `git worktree list --porcelain`. Compare differences relevant to the task with
   the current checkout. Follow a branch or checkout explicitly selected by the user.
   If the current checkout does not match, stop and clarify without
   switching it. If no target branch/checkout is specified and differences in
   requested capabilities make the choice ambiguous, show the discrepancy and
   clarify the target before edits or final conclusions. In `AUDIT`, you may instead
   provide a limited comparison of options without writing. A feature branch being behind
   or different alone does not make it wrong. Mark missing data as a limitation. Local `origin/HEAD`
   does not prove that the remote is current.
   Do not automatically fetch, switch, merge, reset, or delete worktrees.
5. Do not overwrite, reformat, or delete user changes.
   Do not include them in your commits.
6. Identify generated/vendor/build/cache/lock/secret/data directories and exclude
   them from broad analysis unless there is a separate reason to inspect them.
7. Do not expose secrets from `.env` files, keys, tokens, or configurations. Do not copy
   secret values into reports.

Checking Git does not authorize changing the checkout. If the CodeGraph index belongs
to another worktree or is stale, state the limitation and verify facts against the current
files. Do not reindex contrary to current rules or without the required request.

Do not perform these without direct authorization: commits, push, branch deletion, and history rewrites.
production deploys and irreversible database operations. Bulk data deletion.
breaking changes to external APIs, schemas, events, or protocols. Replacing a framework,
language, or ORM. Installing dependencies or making global changes. Follow stricter
project rules, including confirming exact paths before deletion.
Follow the current hierarchy of environment instructions. This skill does not override higher-level
constraints. If the project requires a commit and authority or instruction conflicts are unclear,
ask the user. A refactoring request alone does not authorize push,
deploy, or global changes.

If there are user changes, work around them. If you cannot
isolate the changes, stop in that area and explain the risk. Do not use
`git reset --hard`, `git clean -fd`, `git checkout .`, or `git restore .`
as universal cleanup.

## 3. Architecture goal: clear boundaries

Do not automatically turn functions into classes, classes into services, or a monolith
into microservices. Choose the smallest structure that makes responsibility
clearer and reduces coupling.

Prefer:
- functions for related computations with explicit inputs and results.
- modules for logically related operations and types.
- classes/objects when there is identity, state, invariants, or a lifecycle.
- interfaces/protocols at real variation points and external boundaries.
- adapters to isolate databases, network, filesystem, and SDKs.
- composition over deep inheritance.
- a modular monolith before distribution into services when there is no proven
  need for independent deployment, scaling, or ownership.

Design deep modules with a small, clear external interface that hides
substantial internal complexity. Do not create empty facades, pass-through
wrappers, or abstractions with one consumer just to apply a pattern.

Group code by reasons for change and business capabilities, not only by
technical layers. Follow the existing architecture when changing it is not
the goal and would not provide measurable benefit.

## 4. Autonomous work cycle

Repeat the cycle while there are material findings within the agreed scope
that can be fixed safely.

### A. Understand the system

Inspect the directory structure, entrypoints, packages, main scenarios, modules,
public interfaces, data owners, dependencies, configuration, DI, routes,
background tasks, events, tests, CI, linters, type checker, build, and documentation.

Do not infer a file's purpose from its name alone. Trace actual imports,
calls, dynamic registration, reflection, DI bindings, serializers,
migrations, event names, CLI commands, and configuration references.

For large repositories, map the areas and work through one agreed
area at a time. Do not try to load the entire project into context at once.

### B. Record the baseline

Discover check commands from package scripts, Makefile, Taskfile, pyproject,
Cargo.toml, go.mod, CI, and documentation. Check side effects,
test data, network, and dependencies before running them. In `AUDIT`, run only checks whose
safety is established. Do not create reports or temporary files. In `IMPLEMENT`,
choose proportionate checks and store temporary data and builds in
the verified `<project>/.tmp/` unless current instructions require otherwise.
Before a long check, set a timeout and determine how to identify the owner, PID, and
boundaries of your process tree, and how to verify its termination. After
success, error, or timeout, stop and check only the task-owned tree.
account for process identity, not only a reusable PID. If
safe termination cannot be ensured, do not run the check. If termination
of all descendants is not confirmed, report this as a limitation/blocker, not as
successful cleanup. Do not touch other people's processes.

Record the baseline, including commands, results, known failures, and environment limitations.
Do not attribute pre-existing failures to your changes.

If there are no tests or they do not cover the affected behavior, consider
characterization tests that record the old code's actual behavior on
representative scenarios. Do not automatically treat observed behavior as “correct”. Mark
suspicious results as known bug or unresolved.

### C. Find and classify problems

Inspect the agreed scope rather than limiting it to recently changed files.
Use `scripts/refactor_scan.py` from the **installed skill directory** if
Python 3.9+ is available and running it is safe. By default, the scanner prints JSON to stdout
and writes nothing. Do not run it unnecessarily or contrary to a user prohibition.
For an authorized temporary report **on Windows**, pass `--project-root <project root>`,
`--root <area inside the project>`, and `--json <project>/.tmp/<new-name>.json`.
the `.tmp` directory must exist, and overwriting is prohibited. On POSIX, `--json`
is disabled. Use stdout so nothing is written to a relocated directory. Exit code 1 or `partial: true`
means coverage is incomplete, not that there are no problems.
For each comparison of results, preserve in the report the root/scope, scanner version or hash,
the full `scan_profile`, `partial`, `skipped`, `cutoffs`, truncation indicators
for the compared result, and exit code.
An old JSON without a profile, unknown version/scope, differing profiles, skipped content,
truncation of the compared result, or a nonzero exit code means comparability is not established.
`largest_files_truncated` separately indicates that the list of largest files is limited.
For different worktree paths,
prove scope correspondence separately. Otherwise do not compare them.
Even under comparable conditions, `duplicate_candidates` is only a count of groups
of identical normalized blocks. Groups may overlap. A change in this
number does not prove a change in the number of independent or semantic duplicates.
`partial: false` does not include intentionally excluded hidden/utility directories or
unsupported extensions.
Supplement it with language tools, IDE/LSP, AST, call graph, dependency graph,
test reports, and Git history.

Search for at least:
- long functions, excessive nesting, and high cognitive/cyclomatic complexity.
- god objects/classes/modules and mixed orchestration, domain decisions, and I/O.
- duplicated code, rules, queries, validation, and transformations.
- magic numbers/strings, scattered configuration, and hardcoded environment values.
- weak names, unclear types, primitive obsession, and long parameter lists.
- circular/misdirected dependencies, feature envy, and shotgun surgery.
- hidden state machines, conflicting flags, and temporal coupling.
- external SDK/API types leaking into business logic.
- unnecessary layers, dead code, unused dependencies, and speculative generality.
- domain logic in controllers, UI components, handlers, and background jobs.
- unsafe dependency creation inside business logic.
- implicit side effects and excessively mutable shared state.

Describe each material finding with evidence:
1. Where the problem is, including file, symbol, and lines/range.
2. What exactly is wrong and why it makes maintenance harder.
3. How often/in which scenarios the code is affected, if this can be determined.
4. Consequences and impact radius.
5. Confidence as confirmed / probable / speculative.
6. A suitable transformation and its risk.

Do not use LOC or method count as evidence on its own.
A long function may be linear and clear. A short one may have many hidden
dependencies.

### D. Prioritize

Priorities:
1. Confirmed problems that risk data loss, security, or violation of important contracts.
2. Architectural bottlenecks that cause many errors or force changes across unrelated areas.
3. Duplication of the same changing rule.
4. Long functions/classes that hinder testing and localizing changes.
5. Hardcoding, naming, excessive abstractions, and safe cleanup.

Consider Impact × Likelihood without inventing frequency. Record
severity and confidence separately. A rare error with severe consequences does not become
low priority just because it is rare.

Do not spend time on cosmetic changes that do not improve understanding,
testability, change locality, reliability, or maintenance cost.

### E. Choose and plan a transformation

For each selected finding:
1. Find callers, imports, exports, overrides, tests, config references,
   schemas, serializers, event consumers, and dynamic calls.
2. Define the contract, including inputs/outputs, exceptions, side effects, operation order,
   transactions, concurrency, idempotency, timing, and performance constraints.
3. Check whether a suitable module/type/utility already exists.
4. Choose one specific refactoring pattern.
5. For multiple files, use small atomic steps
   (Mikado Method / dependency-ordered chunks).
6. State the check criterion and rollback path.

For duplication, pass the Safe Abstraction Gate:
- Is this the same business policy or only similar text?
- Do the copies change for the same reason?
- Is there one honest name that fits all consumers?
- Can the shared core be kept without caller-specific boolean flags and many modes?
- If the copies diverge tomorrow, will that be a bug or acceptable evolution?
- Are differences in errors, permissions, rounding, defaults, and side effects preserved?

If the copies may legitimately evolve independently, keep them separate and
record `keep-duplicated`. If a shared function has accumulated modes and flags,
consider `de-abstract`. Similar text is not sufficient reason
to merge.

### F. Make changes

Work in small, complete increments:
- one conceptual refactor at a time.
- targeted checks after each meaningful increment.
- do not mix pure refactoring with new features.
- do not rewrite large areas all at once when they can be improved gradually.
- update all identified consumers and documentation when names,
  paths, or architectural agreements change.
- keep the old implementation until external/dynamic consumers are checked.
  remove it only within the user's authorization and project rules.

Apply techniques from `references/architecture-patterns.md` and
`references/safe-refactoring.md`.

### G. Verify the effect

After each stage:
1. Run relevant tests.
2. Run available and relevant typecheck/compile checks.
3. Run available and relevant lint/static analysis.
4. Review the diff and public contracts.
5. Run build/integration/e2e/smoke checks if needed.
6. Compare before/after behavior on characterization cases.
7. Confirm that the original smell was removed, not merely moved.

Do not weaken tests, types, linter, security checks, or CI to get a green result.
Do not change assertions only because they fail after refactoring. If a check
cannot run because of the environment, state that explicitly.
If useful, compare the project's quality gate before and after installing the skill. Do not attribute errors
in the installed package to the application. Do not change linter configuration or
exclude application files without authorization.

When independent review is requested/required and available, give the reviewer
the exact base commit for the changes under review, the list and contents of related new/untracked files,
actual check results, and available paths. Do not pass unrelated user files,
secrets, or private configurations. Check encoding and evidence availability.
If the required diff or file is unavailable or cannot be safely passed,
the review is limited, not complete. This rule does not by itself authorize starting
additional agents.

If the changes caused a regression, fix it within the stage. If the problem cannot
be localized after two reasonable attempts, safely roll back only your
changes from this stage, preserve the log, and continue with an independent
finding. Do not touch others' changes.

### H. Repeat and finish

After a successful check, move to the next priority finding. Do not end
the work just because the first stage is complete. Rescan the affected
area after major changes. Check for new cycles, duplication,
unnecessary wrappers, or an excessive number of small modules.

Work is complete when all material findings in the agreed scope are handled
or have an explained status of blocked / deferred / keep-duplicated. New changes
have passed available checks. There are no known refactoring regressions. The diff is reviewed.
the log is current. And further changes provide no proportional benefit or require
a user decision/access.

Do not aim for zero findings at any cost. “Leave as is” is a valid
architectural decision when justified.

## 5. Required behavior-preservation rules

Pure refactoring changes internal structure while preserving observable behavior.
Preserve the following unless the task explicitly says otherwise:
- public APIs, schemas, serialization formats, and events.
- error messages/codes, statuses, and default values.
- side-effect order and transaction boundaries.
- permission checks and security invariants.
- rounding, precision, timezone, and date rules.
- retry/backoff/timeout, idempotency, and concurrency semantics.
- distinctions between null/empty/zero/false.
- element order, identifier stability, and object references.
- compatibility with databases, files, and old data.

If a bug is found, confirm it with a reproducible test or clear evidence.
Check expected behavior against requirements/documentation/contract. Change behavior
only if the user explicitly authorizes the bug fix. Otherwise preserve the behavior and
record the finding as unresolved. Keep an authorized fix separate from the structural diff and
state the behavior change in the report. A commit requires separate authorization.

## 6. Special guidance for monolith decomposition

By default, aim for a well-organized modular monolith.

Before decomposing a monolith:
- identify domain areas and bounded contexts from actual code and scenarios.
- build a dependency graph between candidates.
- find circular imports and overlapping data.
- check who reads/writes tables and who owns invariants.
- inspect Git co-change if history is available.
- identify stable entry interfaces and limit direct bypass calls.
- isolate external APIs/SDKs behind adapters.
- check transactions and data consistency.

Do not extract a microservice when the problem can be solved with a modular boundary inside
one process. Do not introduce a network boundary just to tidy directory structure. Distributed
architecture needs separate justification, including independent scaling/
deployment/ownership, separate data, failure model, idempotency,
observability, migration, and rollback.

## 7. Configuration and hardcoding

Distinguish domain/protocol constants, application/environment settings,
secrets, test fixtures, and values that should genuinely be literals.

Do not turn every literal into configuration. Do not put unrelated values into a giant
`constants.py`/`constants.ts`. Keep settings near their owner or in the project's accepted
configuration layer. Secrets should come from a secure mechanism,
but do not create a new secret manager as part of ordinary refactoring. Do not log
secrets or include real values in examples.

## 8. Log and long sessions

If an authorized task spans multiple stages or sessions, keep temporary
artifacts in a unique `<project>/.tmp/` directory. Create permanent documents
only at the user's request or as required by project rules:
- `refactor-plan.md` — areas, findings, priorities, order, and criteria.
- `refactor-status.json` — machine-readable stage status.
- `refactor-log.md` — append-only log of decisions, checks, and blockers.

Do not create artifacts in `AUDIT` or for trivial changes. Do not overwrite an existing log
without checking it. When resuming, compare the status with the actual Git diff. Do not commit
the log if that conflicts with repository conventions.

## 9. Commits, PRs, and publication

If the user requests only refactoring, do not assume authorization for push,
PR, merge, or deploy. Keep the changes local. If the user separately
authorizes a PR/merge, follow project rules and branch protection, do not bypass CI/reviews,
and do not delete branches or rewrite history without explicit authorization. Confirm a merge
only after GitHub/API confirmation.

## 10. Final report

After substantial refactoring, briefly assess quality in the final response:
- **Benefit:** specific before/after and practical gain. State when it is unconfirmed.
  Line count or scanner candidate count alone does not prove benefit.
- **Behavior and safety:** which affected contracts and user changes were checked,
  what evidence supports the conclusion, and what remains unknown.
- **Checks:** actual passed / failed / skipped / not run results, separating baseline failures from
  failures introduced by the changes. Do not claim quality is fully confirmed
  when there is a known regression or required checks were unavailable.

Limit conclusions to the verified scope and do not invent a numerical score. In `AUDIT`,
keep the assessment and findings in the response without writing files. If a possible
shortcoming in the skill is noticed, separate observation from hypothesis and briefly tell the
user. Do not automatically run `reflect` or `improve` modes of
`reflect-and-improve`, or change skills, memory, or global settings based on this
signal. These modes are allowed only after a separate explicit user request
and with the required authorization. Applying each new version requires
separate confirmation of its exact hash and change scope. Existing
read-only `recall` follows separate current instructions and is not a run of
`reflect` or `improve`.

End with a substantive report:
1. **Scope:** which applications/modules/directories were inspected.
2. **Architecture:** main structural difficulties and what changed.
3. **Changes:** functions/classes/modules, duplication, configuration, dependencies.
4. **Bugs:** confirmed fixes and behavior changes, listed separately.
5. **Checks:** exact commands and actual results.
   For scanner numbers, state comparability conditions and limitations. Do not infer the number of
   independent duplicates from overlapping candidates.
6. **Remaining:** blocked, deferred, keep-duplicated, and unresolved.
7. **Risks:** what could not be checked and why.
8. **Git:** changed files and commits/PRs only if actually created.

Do not use vague phrases such as “the code is cleaner” without examples. Provide several
specific before/after examples and explain the practical gain.

## 11. References

Before complex decomposition, read the relevant materials:
- `references/code-smells.md`
- `references/architecture-patterns.md`
- `references/safe-refactoring.md`
