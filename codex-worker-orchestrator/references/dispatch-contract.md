# Dispatch contract

## Runtime path

For a delegated route, the root follows `preflight -> route request -> resolve_roles.py -> validated task packets -> announced spawns -> reports -> reconciliation -> integrated verification`. Resolve preflight, schemas, `resolve_roles.py`, and `run_state.py` only below the directory containing the active installed `SKILL.md`, never from the repository CWD. Pass complete preflight JSON to `--available-agents`. Pass a separate JSON object to `--available-skills`: `{"names": ["<exact active session skill ID>"], "incompatible": []}`. Obtain names from the live session skill catalog, preserving plugin namespaces exactly; never infer them from filenames, short names, or plugin cache contents. Preflight's local inventory contains candidates only. Carry every entry of preflight `skill_inventory.incompatible` into both arrays so an incompatible project companion still blocks the applicable handoff. If the active catalog is unavailable, do not claim capability availability. Every route task instance has a unique task ID, and every report must match that ID and role. A follow-up report reuses the routed task ID with a distinct report ID. A latest per-task `BLOCKED` or `NEEDS_CONTEXT`, a missing report, or any current report decision other than `ACCEPT` forbids completion. A later successful report of the same task can resolve an earlier blocked/context-needed status; retain every immutable report and explicitly accept each historical report after checking its resolution. Another task's success cannot resolve it. Persist each decision with `run_state.py reconcile --task-id ... --report-id ... --decision ...`, then refresh integrated verification. Use `run_state.py` for multi-agent, high-risk, or resumable work; it is a validation ledger, not a scheduler or lock manager. Write isolation comes only from the active Superpowers workflow or `orchestrating-parallel-worktree-changes-v2`.

Every child receives one bounded package. The brief is the task's requirements contract, not a summary of the whole conversation. Prefer one coherent packet over several micro-packets when one role can retain context, ownership, and a meaningful verification boundary. Split only for distinct evidence, capability, sandbox, ownership, or independently useful test work.

Enter `implementing` or `repairing` before new changes, including root-authored work. These transitions invalidate integrated verification. Completion checks ledger event order: selected final/security reviewer reports must follow the latest change report or implementation/repair transition, and verification must follow that change. A fresh `verify` alone cannot renew an older review; obtain a new accepted review report. This validates recorded changes, not unreported edits to external files.

### Model-specific inputs

- Terra visual analysis: accessible application screenshots or rendered technical pages, viewport/page where known, the software question and expected evidence format. `terra_analyst` is read-only and does not capture via mutating tools or operate apps. Root supplies rendered inputs when necessary. A basic one-image question stays Direct; CAD and unrelated visual work are outside this role.
- Terra implementation: assigned files, expected target behavior and regression command; UI work also needs a rendered-result check. For technical `content-writing`, supply project facts, qualifications, audience, tone, length and output file. Root verifies saved results; a draft is not authorization to publish. Keep the brief within the user's software task.
- Evidence batches (Terra/low) and deep-fixed transformations (Luna/max): stable source IDs, exact schema/mapping/classification criteria, unknown-value representation and counts/schema checks. Keep a coherent batch in one packet and use deterministic transformations where appropriate. Do not multiply agents by item count.
- Sol escalation: original scope, inspected evidence, attempted approach and unresolved decision. High complexity alone need not disqualify fixed-interface Luna work; high uncertainty or high/critical risk does. A model change cannot supply missing inputs or tools.

Check actual child model/effort and image/browser/app tools before dispatch, including fallbacks. Caller-discovered skills are guidance, not tool-access proof. Missing required tools or visual inputs means NEEDS_CONTEXT/BLOCKED or safe root work; never claim unseen visual verification. `visual_or_browser` flags UI/browser work; use `visual-analysis` without that flag for supplied images that need no browser. External actions retain the task's existing authorization.

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

The parent must not dispatch until required design approvals or root-cause gates have passed. Optional work needs a structured request, for example `"delegation": {"benefit": "independent-evidence", "expected_output": "Trace the retry callers and report the failure boundary."}`. Other benefits are `specialist-analysis`, `bounded-implementation`, and `parallel-progress`. The expected output must describe real bounded work; a generic complexity label is insufficient. Without it, root does the optional work and still obtains required reviews. Short quiet non-build tests remain in root despite a supplied benefit.

### Substantive specification and plan review gate

A substantive artifact introduces or resolves nontrivial choices about behavior, requirements, interfaces, ownership/dependencies, or acceptance criteria. A focused documentation lookup, short checklist, or detailed execution recipe for already settled behavior stays in root; its length and the presence of this skill do not justify a reviewer. Do not classify substantive planning as `inline` to evade independent critique.

Use `architecture` with `phase=requirements` or `design` to produce a substantive specification, `spec-review` to check it, and `plan-review` to check the implementation plan. Every substantive `phase=planning` request, including architecture/inline plan inputs, needs accepted specification evidence; `spec-review` remains available to obtain that first critique. Sol/Astra root keeps architectural authorship; a separate architect requires a justified distinct deliverable. A read-only `skeptic` checks the artifact. Each packet names the current stage; an architect cannot draft both artifacts ahead of the review boundary and cannot independently review its own work.

Architecture and review routes retain their own independent stages, even when a numbered plan is approved and delegation selected.

The ordered gate is:

1. Review the substantive specification/design, when supplied or produced, before drafting its implementation plan. Do not create a separate spec document merely to satisfy this gate.
2. Root resolves every material finding by correcting the artifact or recording an evidence-backed rejection. Optional improvements do not force another round or expand scope.
3. Draft the plan against the corrected specification or binding requirements; independently check fidelity, ordered steps, ownership, dependencies, failure paths, and meaningful acceptance checks before implementation.
4. Root resolves material plan findings before dependent work. Critique neither grants user approval nor replaces final Hard code review.

Keep the repository root distinct from the ledger/artifact root. Create and validate a task directory `<repository>/.tmp/<task>` physically inside the repository, rejecting symlinks/junctions; put briefs, plans, request/report JSON, logs, backups and test/build outputs there. A new permanent specification is unnecessary. Pass that task directory explicitly as `resolve_roles.py --project-root <repository>/.tmp/<task>` and `run_state.py --project-root <repository>/.tmp/<task>` (API: `project_root=`), so the ledger and its atomic staging remain inside project `.tmp`. Packet cwd/repository remains the actual repository. For nontrivial writes, missing planning context defaults to substantive. Artifact references are relative to the task root:

```json
{
  "planning": {
    "kind": "substantive",
    "specification": {"path": "spec.md", "author_id": "root", "review_run_id": "spec-review", "review_report_id": "spec-1"},
    "plan": {"path": "plan.md", "author_id": "root", "review_run_id": "plan-review", "review_report_id": "plan-1"}
  }
}
```

Record each actual independent report with existing `run_state.py record-report`, then the root ruling using `reconcile ... --decision ACCEPT`. Use a separate run per artifact stage when routes differ. The report's optional `artifact_review` is required for evidence reuse: `kind` (`specification` or `plan`), project-relative `path`, lowercase `sha256` of the exact bytes, `author_id`, and actual `reviewer_id`; a plan also supplies `specification_sha256`. The author and critic must be distinct even when root merely persists an architect's draft. Root checks actual tool dispatch identity; self-reported identity is insufficient. Equivalent accepted review from another workflow can be recorded through this same contract without creating another child.

Resolver validates the referenced ledger and dispatched read-only `skeptic` or `sol_reviewer`, `DONE`, no unresolved `findings` or authoring changes, current root `ACCEPT`, metadata/current bytes, and the latest same-path/stage report within that run. Put optional improvements in `concerns`; resolve material findings before recording an accepting report. A later unaccepted/rejected/blocking report supersedes an older ACCEPT. Plan review must bind the current specification digest and be recorded after its acceptance. Missing/stale/self-review, absolute/traversal/stream paths, redirected path members, and nonregular files block dependent work and handoff. This is a local root-owned audit record, not signed identity attestation or discovery of superseding reviews in unrelated runs. Revalidate before dependent work if artifacts change.

All declared file-changing routes enter this barrier, including `mutation=diagnostic` with nonempty `write_surfaces`; both accepted specification and plan are required. Diagnostics without declared changes retain ordinary verification routing. Planning acceptance never permits a diagnostic/test-only role to edit production or tracked/generated source; retain the role's output restrictions and return NEEDS_CONTEXT when required.

An explicit `"planning": {"kind": "settled"}` recipe skips new critique only with `approved_design=true`, below high rigor, and without security or independent-analysis requirements. Do not relabel new substantive choices as settled. Simple safe Direct work and ordinary verification need no ledger. The same critic may be resumed sequentially for spec and plan. Accepted unchanged plan critique replaces a redundant pre-write skeptic; final Hard code review remains separate. Stop after at most three review/correction rounds per artifact and escalate unresolved material decisions before dependent work.

Latest-review matching recognizes validated paths addressing the same filesystem artifact, including case aliases and hardlinks. The recorder adds optional `artifact_review.filesystem_identity` from the trusted filesystem, replacing any worker-supplied value; schema version 1 remains readable. Recorded identity and path continuity preserve rulings after alias deletion/replacement or atomic file replacement. Removed distinct files remain unrelated even with identical bytes. A later missing legacy path without identity is ambiguous and requires a fresh review; earlier unknown history does not invalidate that fresh review.

Lite execution recipes for settled decisions remain root-checked. A Lite task introducing substantive planning choices needs accepted independent review of unchanged artifacts or Hard capability; the runner and root self-review cannot substitute, and a profile switch needs user authority. When a required reviewer is missing, continue only independent safe work and expose the unmet prerequisite. A user prohibition on subagents wins: use zero children and explicitly disclose the self-review limitation without claiming independent acceptance.

### Lite execution-plan gate

Before a Lite implementation spawn, the root must write and approve a detailed, unambiguous execution plan for settled behavior. It includes ordered steps, exact allowed files and write surfaces, protected interfaces, forbidden changes, dependencies, binary acceptance criteria, exact verification commands with expected results, and stop conditions. Apply the substantive artifact gate above when new design choices remain. `luna_worker` receives the complete plan. After implementation, the root inspects the actual diff and scope, then runs short quiet checks itself or sends builds, noisy checks, and worthwhile long/independent checks to `luna_test_runner`. The runner is not a reviewer, and the root owns the completion decision.

Before every spawn, write the following announcement in the main chat before invoking the spawn tool:

```text
Spawning <role> (<agent type>) — <purpose>. Selected because <selection reason>.
```

Announce every new child, including explorers, background test workers, implementers, reviewers, fallbacks, and behavioral-pressure agents. Resuming an existing child does not require a new-role announcement, but the root should state why it is being resumed.

## 2. Spawn rules

- Read each selected role's registry-derived `model`, `reasoning_effort` and `fork_turns="none"` from the route; fallback metadata names the actual selected role. These optional fields preserve legacy route compatibility. For a legacy route, load the current registry before dispatch. Resolver metadata is dispatch intent, not proof of runtime identity.
- Compare the actual available custom role and live spawn schema with that intent. Use the custom role identifier and isolated child context where supported. When `fork_turns` exposes `"none"`, use it for registry-selected roles. In the current schema, omitted/`"all"` context inherits the parent model and effort and cannot be used to claim a heterogeneous role dispatch. Never invent numeric fork values.
- First-party generic defaults and a concrete session's context-inheritance rules can differ; adapt to the actual schema rather than claiming that role TOML is universally ignored. If `fork_turns` is unavailable, use only a supported role/override mechanism whose documented behavior preserves the required model and effort; otherwise stop that dispatch and report the limitation.
- Do not override a loaded role's model, reasoning, or sandbox with stale values. If the live schema requires explicit model/effort overrides, pass both from the selected role and confirm they are supported. A mismatch or unsupported required setting blocks dispatch; never silently substitute inherited parent settings. Role read-only instructions and configured sandbox remain subject to the live parent permission ceiling.
- Only the root controller spawns.
- Children do not invoke `codex-worker-orchestrator`, spawn helpers, create reviewers, or act as recursive subplanners.
- Prefer brief files and workspace-write implementer report files over pasting large requirements into the controller context. Read-only results stay in the child final response.
- One writer owns one write surface. Parallel writers require non-overlapping ownership and isolated mutable resources. Ask the user before creating separate worktrees; without explicit approval, keep writer packets sequential.
- The separate `orchestrating-parallel-worktree-changes-v2` executes only an approved, semantically validated `PARALLEL` overlay. Its ledger checks shape/hash/isolation, not source fidelity, dependencies, ownership, conflicts or waves. Without equivalent semantic validation, leave V2 unstarted and work sequentially; do not copy its protocol into a child brief.
- Conservative native parallel dispatch may fan out only independent read-only or `test-execution` packets. Writer packets stay sequential. Give each instance a unique task identifier and collect every result.

### Background test runner

Serialization preserves one task instance and report per declared test package, with one instance per wave. Reuse the runner between waves; do not collapse the packages into an anonymous task. All package instances count toward the route budget and completion coverage.

In every profile, keep short quiet non-build checks in root; unknown duration alone does not justify delegation. Use `luna_test_runner` for builds and noisy checks even when short/blocking, or when duration exceeds the configured threshold or the root can continue independent root work. Use `intent=test-execution` and optional `test_context.is_build=true` for builds. In Lite, preserve exact commands from the approved root plan. The runner uses Luna/medium, never edits tracked files, records duration and exit status, and stops only the process tree it started. Collect every result before dependent work or a completion claim. Shared ports, databases, fixtures, caches, or services force sequential execution. The root remains responsible for diff inspection and fresh integrated verification.

Supply only the bounded execution context: cwd, exact commands/environment, dependencies, timeout and progress checks, log path, allowed untracked build outputs/caches, and tracked-file baseline. A build requiring tracked/generated source edits returns NEEDS_CONTEXT before execution. Save full logs to the assigned path and return a compact result with command, exit code, duration, error excerpt, and log path. On failure, stop dependent commands and return DONE_WITH_CONCERNS; independent commands continue only if the brief permits. Do not diagnose, fix, or retry autonomously. Sol/Astra root diagnoses the failure or routes it to an actual Sol specialist under the existing gates; a role name alone does not prove its model. After the fix, resume the same runner with affected commands. Silence alone is not a hang; honor the assigned timeout. Avoid passing full conversation history or creating a fresh agent for every rerun.

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

`run_state.py` is a ledger: it never schedules agents or supplies write isolation. Use it for multi-agent, high-risk, or resumable work.

After every report, the root records exactly one current decision with `run_state.py reconcile --task-id ... --report-id ... --decision ... --reason ...`:

| Decision | Use when | Required next action |
|---|---|---|
| `ACCEPT` | Scope, evidence, and acceptance criteria are satisfied. | Continue to the next dependency or integrated verification. |
| `REPAIR` | A bounded finding remains inside unchanged ownership and root cause is established. | Resume the same implementer with the exact finding and checks. |
| `INVESTIGATE` | Failure cause, evidence, or environment is unclear. | Return to `superpowers:systematic-debugging` or a read-only investigator before another writer. |
| `REPLAN` | Ownership, contract, architecture, or dependency assumptions changed. | Re-enter the owning planning workflow; do not patch around the change. |
| `BLOCK` | Access, policy, prerequisite, or unresolved load-bearing finding prevents safe continuation. | Preserve evidence and report the blocker. |

Concerns and suggested follow-ups never become tasks automatically. The root accepts, rejects, consolidates, or defers each one against the user's approved goal, dependency graph, and remaining budget.

For a native CWO route, after two failed implementation or fix attempts against the same claimed root cause, do not spawn a third writer. Terra stops and returns the attempts, evidence and unresolved issue to root. Re-establish the cause through `superpowers:systematic-debugging`. In Lite, request authorization to switch to Hard or record `BLOCK`; do not invoke unavailable specialists. In Hard, invoke `skeptic` when its triggers apply and use `sol_architect` when the boundary or design changed. This gate does not override the separate five-round policy owned by `orchestrating-parallel-worktree-changes-v2`.

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
6. Nontrivial Hard file changes, including root-written ones, have accepted mandatory `sol_reviewer` review on Sol/xhigh with no weaker fallback; Lite has root inspection of the actual diff plus successful root-run or `luna_test_runner` evidence for the exact planned commands. A root-written route has `root_work=true`, root write ownership, and reviewer waves after root implementation/verification, with no spawnable root role.
7. `superpowers:verification-before-completion` has fresh evidence for every completion claim.
8. Every recorded report has a current `ACCEPT` decision in the durable run ledger.

The final delivery summary separates:

- accepted and verified work;
- implemented work that remains unaccepted because evidence, review, or integration is incomplete;
- blocked or partial work with the exact reason.

Only the first category may be reported as complete.
