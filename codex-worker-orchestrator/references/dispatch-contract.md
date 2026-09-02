# Dispatch contract

## Runtime path

For a delegated route, the root follows `preflight -> route request -> resolve_roles.py -> validated task packets -> announced spawns -> reports -> reconciliation -> integrated verification`. Resolve preflight, schemas, `resolve_roles.py`, and `run_state.py` only below the directory containing the active installed `SKILL.md`, never from the repository CWD. Pass the complete preflight JSON to both resolver inventory inputs so missing roles or installed capability skills cannot be assumed or omitted. Every route task instance has a unique task ID, and every report must match that ID and role. A follow-up report reuses the routed task ID with a distinct report ID. `BLOCKED`, `NEEDS_CONTEXT`, a missing report, or any current decision other than `ACCEPT` forbids completion. Persist each decision with `run_state.py reconcile --task-id ... --report-id ... --decision ...`, then refresh integrated verification. Use `run_state.py` for multi-agent, high-risk, or resumable work; it is a validation ledger, not a scheduler or lock manager. Write isolation comes only from the active Superpowers workflow or `orchestrating-parallel-worktree-changes-v2`.

Every child receives one bounded package. The brief is the task's requirements contract, not a summary of the whole conversation. Prefer one coherent packet over several micro-packets when one role can retain context, ownership, and a meaningful verification boundary. Split only for distinct evidence, capability, sandbox, ownership, or independently useful test work.

## 1. Parent responsibilities before spawn

The root controller records:

- process owner;
- selected actual role name;
- task identifier;
- repository/worktree and baseline commit when applicable;
- prerequisites and dependency order;
- allowed read scope and exclusive write surface, if any;
- exact acceptance criteria;
- exact validation commands;
- output channel: a report file for `workspace-write` roles or the final child response for `read-only` roles;
- fallback used, if any.

The parent must not dispatch until required design approvals or root-cause gates have passed.

### Lite execution-plan gate

Before a Lite implementation spawn, the root must write and approve a detailed, unambiguous execution plan. It includes ordered steps, exact allowed files and write surfaces, protected interfaces, forbidden changes, dependencies, binary acceptance criteria, exact verification commands with expected results, and stop conditions. `luna_worker` receives the complete plan. After implementation, the root inspects the actual diff and scope, then sends the exact planned commands to `luna_test_runner`. The runner is not a reviewer, and the root owns the completion decision.

Before every spawn, write the following announcement in the main chat before invoking the spawn tool:

```text
Spawning <role> (<agent type>) — <purpose>. Selected because <selection reason>.
```

Announce every new child, including explorers, background test workers, implementers, reviewers, fallbacks, and behavioral-pressure agents. Resuming an existing child does not require a new-role announcement, but the root should state why it is being resumed.

## 2. Spawn rules

- Use isolated child context when the actual tool schema supports it. For schemas exposing `fork_turns`, prefer `"none"`.
- Use the actual custom role identifier when the schema supports an agent type or role field.
- Do not override a loaded role's model, reasoning, or sandbox with stale values.
- If explicit overrides are required, set both model and reasoning effort and verify them against the current allowlist.
- Only the root controller spawns.
- Children do not invoke `codex-worker-orchestrator`, spawn helpers, create reviewers, or act as recursive subplanners.
- Prefer brief files and workspace-write implementer report files over pasting large requirements into the controller context. Read-only results stay in the child final response.
- One writer owns one write surface. Parallel writers require non-overlapping ownership and isolated mutable resources. Ask the user before creating separate worktrees; without explicit approval, keep writer packets sequential.
- For an applicable approved-plan handoff, `parallelizing-subagent-plans` owns dependency topology and only `orchestrating-parallel-worktree-changes-v2` executes its `PARALLEL` overlay. Do not copy either protocol into a child brief.
- When that companion is absent, a conservative native fallback may fan out only independent read-only or `test-execution` packets. Give each instance a unique task identifier and collect every result.

### Background test runner

In Lite, `luna_test_runner` is required after each write and runs the exact verification commands from the approved root plan. In Hard or standalone test execution, use it when the command exceeds the configured threshold, produces noisy output, can run independently while the root can continue independent root work, or belongs to an independent suite; keep short blocking tests in the root. The runner uses Luna/medium, never edits tracked files, records duration and exit status, and stops only the process tree it started. Collect every result before dependent work or a completion claim. Shared ports, databases, fixtures, caches, or services force sequential execution. The root remains responsible for diff inspection and fresh integrated verification.

## 3. Required brief

```markdown
# Task <ID>: <short title>

## Role and process
Role: <actual custom role or disclosed fallback>
Process owner: <active Superpowers skill>
Required sub-skills:
- REQUIRED SUB-SKILL: Use <exact skill name>
- REQUIRED DOMAIN SKILL: Use <exact domain skill>, when applicable

## Position in the work
<One or two sentences explaining how this package fits the larger change.>

## Goal
<One observable outcome.>

## Confirmed current behavior or evidence
<Only facts. Include exact errors, symbols, reproduction steps, commits, or evidence paths.>

## Required behavior
<Exact behavior after completion.>

## Repository state
Worktree/repository: `<path>`
Baseline commit: `<sha or not applicable>`
Prerequisites:
- <completed task, artifact, interface, or none>

## Scope and ownership
Allowed read scope:
- `path/to/file-or-directory`

Allowed writes:
- `path/to/file` | none for a read-only role

Exclusive interfaces/generated outputs/resources:
- <schema, lockfile, snapshot, fixture, service, port, database, or none>

Forbidden changes:
- <public API, dependencies, unrelated modules, generated files, architecture, etc.>

## Interfaces
Consumes:
- <exact signature or prior-task artifact>

Produces:
- <exact signature or artifact later work relies on>

## Acceptance criteria
- <binary observable criterion>
- <binary observable criterion>

## Validation
Run:
- `<exact focused command>`
- `<broader command when proportionate>`

Expected:
- <observable result and exit status>

## Stop conditions
Return `NEEDS_CONTEXT` or `BLOCKED` instead of guessing when:
- product behavior or architecture must be chosen;
- root cause is not established for an implementation fix;
- files/resources outside ownership must change;
- requirements or interfaces conflict;
- a prerequisite is missing;
- sandbox, approval, tool, model, or dependency access blocks required work;
- validation cannot distinguish success from a false positive.

## Output channel
Mode: `<report-file | final-response>`

For a `workspace-write` implementation role:
- Report path: `<path/to/task-report.md>`
- Write the full structured report there.
- Return to the parent only status, changed files, one-line validation, and concerns/blockers.

For a `read-only` investigator or reviewer:
- Return the full structured report in the final response.
- Do not write a report file or any other artifact.
- The parent persists the result when the owner workflow needs a file-backed record.
```

### Machine-readable packet fields

`task-packet.schema.json` keeps schema version 1 backward-compatible and accepts these optional structured fields when the root emits JSON packets:

- `consumes`: exact prior artifacts, interfaces, or evidence required by the task;
- `produces`: exact interfaces, files, or reports downstream work may rely on;
- `stop_conditions`: one or more explicit reasons to return `NEEDS_CONTEXT` or `BLOCKED` instead of guessing;
- `output_channel`: exactly `report-file` or `final-response`.

The Markdown brief remains authoritative when both forms are present. Optional JSON fields clarify the handoff but never create permission beyond the brief.

## 4. Writer preamble

Place this before the brief path:

```text
You are a spawned implementation worker, not the root controller.
Do not invoke codex-worker-orchestrator. Do not spawn agents, helpers, or reviewers.
Read the task brief first and treat it as the complete requirements contract.
Use only the process/domain skills named in the brief.
Stay inside its write ownership. Do not redesign architecture or widen requirements.
Return NEEDS_CONTEXT instead of guessing.
Write the full report to the required report path and keep the parent reply concise.
```

## 5. Read-only preamble

```text
You are a spawned read-only investigator or reviewer, not the root controller.
Do not invoke codex-worker-orchestrator. Do not spawn agents, helpers, or reviewers.
Read the task brief first. Do not edit source, tests, configuration, lockfiles, generated artifacts, or report files.
Separate direct evidence from inference. Return NEEDS_CONTEXT when the requested conclusion cannot be established.
Return the full structured report in the final response. Do not write a report file.
The parent owns persistence of read-only findings when the workflow needs a file-backed record.
```

## 6. Report contract

```markdown
STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED

ROLE_USED:
<actual role name or disclosed fallback>

SUMMARY:
<What was established or changed.>

EVIDENCE_OR_CHANGES:
- <file/symbol/evidence path>

VALIDATION:
- Command: `<exact command>`
  Exit: <integer or not run>
  Result: <concise material result>

SCOPE_CHECK:
- Allowed files changed: <list or none>
- Out-of-scope changes: none | <details>
- Shared resources touched: none | <details>

CONCERNS:
- none | <specific uncertainty, risk, environmental limitation, or unsupported assumption>

RECOMMENDED_NEXT_STEP:
<One concrete parent action.>

SUGGESTED_FOLLOW_UPS:
- none | <advisory candidate task; never automatic scope expansion>
```

The output channel is part of the brief contract:

- `workspace-write` implementers normally write the report file and return a compact handoff;
- `read-only` investigators and reviewers return the full report in their final response and never write a report file;
- the parent, not the read-only child, persists reviewer or investigator output when needed.

For JSON reports, `agent-report.schema.json` accepts optional `recommended_next_step` and `suggested_follow_ups`. They are advisory. The root must independently decide whether either belongs inside the approved goal.

The parent verifies `ROLE_USED` against dispatch metadata. A child's self-reported model or effort is not sufficient proof.

## 7. Root reconciliation loop

After every report, the root records exactly one current decision with `run_state.py reconcile --task-id ... --report-id ... --decision ... --reason ...`:

| Decision | Use when | Required next action |
|---|---|---|
| `ACCEPT` | Scope, evidence, and acceptance criteria are satisfied. | Continue to the next dependency or integrated verification. |
| `REPAIR` | A bounded finding remains inside unchanged ownership and root cause is established. | Resume the same implementer with the exact finding and checks. |
| `INVESTIGATE` | Failure cause, evidence, or environment is unclear. | Return to `superpowers:systematic-debugging` or a read-only investigator before another writer. |
| `REPLAN` | Ownership, contract, architecture, or dependency assumptions changed. | Re-enter the owning planning workflow; do not patch around the change. |
| `BLOCK` | Access, policy, prerequisite, or unresolved load-bearing finding prevents safe continuation. | Preserve evidence and report the blocker. |

Concerns and suggested follow-ups never become tasks automatically. The root accepts, rejects, consolidates, or defers each one against the user's approved goal, dependency graph, and remaining budget.

For a native CWO route, after two failed implementation or fix attempts against the same claimed root cause, do not spawn a third writer. Re-establish the cause through `superpowers:systematic-debugging`. In Lite, request authorization to switch to Hard or record `BLOCK`; do not invoke unavailable specialists. In Hard, invoke `skeptic` when its triggers apply and use `sol_architect` when the boundary or design changed. This gate does not override the separate five-round policy owned by `orchestrating-parallel-worktree-changes-v2`.

## 8. Review package

A reviewer receives files or paths for:

- original task brief;
- implementer report;
- actual diff/evidence package from the recorded baseline;
- binding global constraints;
- applicable review rubric;
- any parent rulings made after the brief.

The reviewer must not be given another reviewer's conclusion as the expected answer. Do not ask it to trust the implementer summary or suppress likely findings.

## 9. Fix rounds

For ordinary findings, resume the same implementer with:

- exact finding and severity;
- evidence and affected location;
- violated acceptance criterion or invariant;
- unchanged write ownership;
- exact re-validation command;
- updated report path or fix-round section.

Record each returned fix round under the original routed `task_id` and a new stable `report_id`; never overwrite or discard the earlier report or its decision.

Use a fresh or stronger worker only when:

- the original role lacks a proven required capability;
- a recorded parent ruling changes the boundary;
- the original agent cannot be resumed after a supported attempt;
- the owner workflow's escalation rule requires a fresh agent.

Do not restart the whole task to obtain a different answer. Apply the two-attempt diagnostic reset from the reconciliation loop before a third native-CWO writer attempt.

## 10. Parent integration gate

Before accepting a package, the root controller checks:

1. The actual diff/evidence matches the brief.
2. Only the assigned write surface changed.
3. Dependencies and produced interfaces match neighboring tasks.
4. Validation ran on the final integrated state.
5. Worker concerns are resolved or explicitly carried forward.
6. Hard has accepted mandatory `sol_reviewer` review on Sol/xhigh with no Terra fallback; Lite has root inspection of the actual diff plus a successful `luna_test_runner` report for the exact planned commands.
7. `superpowers:verification-before-completion` has fresh evidence for every completion claim.
8. Every recorded report has a current `ACCEPT` decision in the durable run ledger.

The final delivery summary separates:

- accepted and verified work;
- implemented work that remains unaccepted because evidence, review, or integration is incomplete;
- blocked or partial work with the exact reason.

Only the first category may be reported as complete.
