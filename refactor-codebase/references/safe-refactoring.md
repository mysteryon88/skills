# Safe refactoring: behavior, tests, and verification

## Characterization tests

For legacy code without tests, record actual behavior before changing it:
ordinary inputs. Empty/null/zero/false values. Boundaries. Errors. Repeated calls.
side-effect order. State before/after. Observed behavior is not necessarily
correct. Mark suspicious behavior `known-bug` or `unresolved`.

Stabilize time, RNG, network, filesystem, and database. Do not replace expected values
with assumptions. Obtain them through an actual run or from an approved contract.

## Contract checklist

Before moving/renaming, check callers, imports, exports, re-exports,
DI bindings, reflection, decorators, plugin registries, routes, schemas, serializers,
API clients, events, queues, job names, CLI, environment keys, migrations, DB columns,
error types/codes/messages, authorization, transaction/concurrency semantics, and docs.

Searching for an identifier does not always find consumers of enum/state/role values. Also search
switch/match, lookup tables, validators, serializers, fixtures, translations, and fallbacks.

## Expand-Contract

1. Add the new interface/path and keep the old one.
2. Migrate consumers gradually.
3. Check that there are no old callers.
4. Keep the old path if external or dynamic consumers have not been checked.
   Remove it only with the required explicit authorization and in accordance with project rules.

## Checks

Determine commands from the repository. A typical set includes unit/integration/e2e tests,
typecheck/compiler, lint/static analysis, build, migration/schema validation,
smoke tests, and performance checks for hot paths. Inspect scripts/CI/docs first.
Assess side effects before running commands. Do not run write commands during AUDIT.
Place temporary files and builds in `<project>/.tmp/`. After authorized
auto-fixers, rerun available typechecks and tests. For long checks,
set a timeout in advance and determine how to identify the owner/PID, boundaries, and termination
of your process tree. Check it after success, error, and timeout. If termination of all descendants is not
confirmed, state the limitation explicitly. Do not stop other processes
or processes with reused PIDs.

Do not game checks: do not delete failing tests, change expected results to get
a green status, weaken lint/type/security rules, or claim that a check was run
when it was not. Tests should check behavior through the
public interface where appropriate.

## Rollback

Keep each major stage bounded and reversible. If it fails, isolate
your changes, safely roll back only those changes, preserve user changes,
record the reason, and do not continue dependent stages on a broken state.

## Git and publication

Do not commit, push, open a PR, or merge branches without user authorization.
Follow the hierarchy of current instructions and stricter constraints. If a
project rule requires a commit but authority or instruction conflicts are unclear, ask first.
If authorized, follow branch protection and required checks.
Verify the target checkout and task-related local refs/worktrees without
automatic fetch or switching. Do not replace the user's specified branch with an assumption
about the “main” branch.

## Handoff for independent review

If requested/required and authorized, pass the base commit, diff, new
untracked files in the change under review, exact check results, and available paths.
Do not pass unrelated user files, secrets, or private configurations.
Check encoding and material accessibility. Required evidence that
is unavailable or cannot be safely passed limits the review. This checklist does not
authorize delegation by itself.

## Final diff checklist

- [ ] No unrelated changes.
- [ ] All callers are updated.
- [ ] Old code is preserved or removed after consumer migration and required authorization.
- [ ] No new circular dependencies.
- [ ] Duplication is reduced without false abstraction.
- [ ] New modules have a clear responsibility and small interface.
- [ ] Configuration has not become a global dumping ground.
- [ ] Behavior and contracts are preserved or changes are listed.
- [ ] Tests/typecheck/lint/build are checked with exact results.
- [ ] Documentation and paths are updated when needed.
- [ ] User's uncommitted changes are preserved.
