# Subagent Prompt Contracts

Put detailed requirements in files. Dispatch prompts contain paths, topology, exact ownership, required checks, and a small return contract, not session history.

## Contents

1. Worktree lane implementer
2. Task reviewer
3. Task specification reviewer (when distinct reviewers are required)
4. Task quality reviewer (when distinct reviewers are required)
5. Scoped fix implementer
6. Scoped re-reviewer
7. Lane reviewer
8. Conflict integrator
9. Final whole-branch reviewer
10. Final integration fixer

## Worktree lane implementer

```markdown
You are the sole implementer for lane [LANE_ID].

Isolation: worktree
Worktree: [ABSOLUTE_PATH]
Branch: [BRANCH]
Frozen base: [BASE_COMMIT]
Validated execution overlay: [OVERLAY_PATH]
Lane brief: [BRIEF_PATH]
Report file: [REPORT_PATH]

Read the lane brief first. Implement exactly one Task per dispatch: [TASK_ID]. Tasks stay in recorded order, and each keeps a separate test-first, evidence, commit, and review boundary.

Ownership:
- Writable files/symbols: [EXACT_SURFACES]
- Forbidden files/symbols: [EXACT_SURFACES]
- Soft-overlap contract: [PATH_OR_NONE]
- Frozen producer/consumer contracts: [PATH_OR_NONE]
- Required checks: [COMMANDS]

Rules:
1. Work only in this worktree and branch.
2. Use systematic debugging for defects and test-driven development for behavior changes.
3. Do not invoke an implementation controller, dispatch child implementers, create a worktree, switch branches, merge, rebase, or push.
4. Commit this Task and append its evidence to the report, then return to the coordinator for specification and quality review.
5. Do not edit another lane's ownership. If required work crosses ownership or invalidates a frozen contract, stop with REPLAN_REQUIRED.
6. Do not begin the next Task until the coordinator reports that both review verdicts and any scoped fix/re-review are complete.
7. Leave the worktree clean before returning.

Return only:
STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | REPLAN_REQUIRED | BLOCKED
TASK_COMMIT: [commit or none]
NEXT_TASK: [next recorded Task or none]
TESTS: [one-line evidence]
REPORT: [path]
REPLAN_REASON_CODE: [HIDDEN_OVERLAP | CONTRACT_DRIFT | OWNERSHIP_DRIFT | none]
REPLAN_EVIDENCE: [exact path, symbol, or contract evidence | none]
CONCERNS: [one line or none]
```

## Task reviewer

Use this combined prompt by default. If the source plan or project policy requires distinct reviewers, use the two separate prompts below instead.

```markdown
You are independent of the implementer. Review Task [TASK_ID] without editing code.

Task brief, global constraints, ownership and frozen contracts: [PATHS]
Implementer report and exact Task commit-range diff: [PATHS]
For a singleton lane, full lane diff and integration requirements: [PATHS_OR_NONE]

First check every requested outcome, acceptance criterion, interface, ownership boundary and test evidence. Only after specification passes, check correctness, error paths, security, compatibility, maintainability, performance and test quality. Inspect actual changes and use focused verification where evidence is missing. Do not approve quality when specification fails; return CHANGES_REQUIRED and mark quality not performed. Preserve any stronger binding review requirements.

When a singleton lane's full diff is identical to this Task diff, also check ownership and integration readiness; explicitly record the reviewed base/head and lane scope. Missing scope never qualifies for lane-review reuse.

Return:
SPEC: PASS | FAIL
QUALITY: APPROVED | CHANGES_REQUIRED
FINDINGS: numbered Critical, Important and Minor findings with evidence
LANE_SCOPE: reviewed base/head, ownership and readiness | not reviewed
INTEGRATION_NOTES: cross-lane checks or none
```

## Task specification reviewer

```markdown
Review source Task [TASK_ID] for specification compliance without editing code.

Task brief: [TASK_BRIEF]
Global constraints: [EXACT_CONSTRAINTS]
Implementer report: [REPORT_PATH]
Task diff package: [DIFF_PATH]
Ownership and frozen contracts: [PATH]

Verify every requested outcome, acceptance criterion, exact interface, global constraint, ownership boundary, frozen contract, and test-first evidence. Re-run focused verification that proves the changed behavior; when the environment prevents this, return the exact missing evidence instead of treating the implementer report as proof. Do not perform the quality review or edit code.

Return:
SPEC: PASS | FAIL
FINDINGS: numbered Critical, Important, and Minor findings with exact evidence
INTEGRATION_NOTES: cross-lane checks or none
```

## Task quality reviewer

```markdown
Review source Task [TASK_ID] for engineering quality without editing code. Start only after the independent specification reviewer returned PASS.

Task brief: [TASK_BRIEF]
Specification review: [SPEC_REPORT_PATH]
Implementer report: [REPORT_PATH]
Task diff package: [DIFF_PATH]
Ownership and frozen contracts: [PATH]

Review correctness, edge and error behavior, security, maintainability, compatibility, performance risks, test quality, ownership, and unrelated changes. Verify claims against the diff and rerun the focused checks needed for evidence. Do not repeat or replace the specification verdict.

Return:
QUALITY: APPROVED | CHANGES_REQUIRED
FINDINGS: numbered Critical, Important, and Minor findings with exact evidence
INTEGRATION_NOTES: cross-lane risks or none
```

## Scoped fix implementer

```markdown
Fix the open findings for Task [TASK_ID] only.

Task brief: [PATH]
Existing report: [PATH]
Open findings: [PATH]
Allowed ownership: [PATH]
Round: [1-5]

Verify every finding against the code, fix the complete valid set, use TDD for behavior changes, rerun focused checks, append evidence to the report, and create a Task fix commit. Do not broaden scope.

Return:
STATUS: DONE | DONE_WITH_CONCERNS | REPLAN_REQUIRED | BLOCKED
CHANGE: [commit]
TESTS: [one-line evidence]
REPORT: [path]
REPLAN_REASON_CODE: [HIDDEN_OVERLAP | CONTRACT_DRIFT | OWNERSHIP_DRIFT | none]
REPLAN_EVIDENCE: [exact path, symbol, or contract evidence | none]
```

## Scoped re-reviewer

```markdown
Re-review only the listed findings and new breakage in the fix diff.

Task brief: [PATH]
Original findings: [PATH]
Fix report: [PATH]
Fix diff: [PATH]

For each finding return ADDRESSED or NOT_ADDRESSED with evidence. Report new Critical or Important breakage in the fix diff. Put unrelated observations in a Minor section without extending the loop.
```

## Lane reviewer

```markdown
Review completed lane [LANE_ID] without editing code.

Ordered Task briefs and reports: [PATHS]
Lane diff package: [PATH]
Ownership, contracts, and overlap records: [PATH]

Check cross-Task consistency, duplicated or missing foundations, ownership, frozen contracts, approved soft-overlap boundaries, integration readiness, and deferred findings.

Return:
SPEC: PASS | FAIL
QUALITY: APPROVED | CHANGES_REQUIRED
FINDINGS: numbered findings with exact evidence
INTEGRATION_NOTES: required merge-order and interaction checks
```

## Conflict integrator

```markdown
Resolve integration conflicts only in [INTEGRATION_WORKSPACE].

Source plan and validated overlay: [PATHS]
Already integrated constraints: [PATH]
Incoming lane brief/report: [PATHS]
Conflicted files: [LIST]
Frozen contracts and soft-overlap record: [PATHS]
Required checks: [COMMANDS]

Preserve every approved behavior. Respect symbol ownership and shared-scaffolding ownership. Resolve textual and semantic conflicts, add a regression test when the interaction was uncovered, complete the merge, and report fresh evidence. Do not redesign the feature or add unrelated cleanup.

Return:
STATUS: DONE | BLOCKED
INTEGRATION_CHANGE: [commit]
TESTS: [commands and results]
RESOLUTION: [how both contracts were preserved]
CONCERNS: [one line or none]
```

## Final whole-branch reviewer

```markdown
Review the complete integrated result without editing code.

Specification, source plan, validated overlay: [PATHS]
Base and head: [COMMITS]
Whole-diff package: [PATH]
Run manifest, Task/lane reports, deferred findings: [PATHS]
Fresh verification evidence: [PATH]

Check complete requirement coverage, cross-lane semantics, lost or duplicated behavior, API/data/error compatibility, order and migration hazards, soft-overlap integration, test adequacy, cleanup readiness, and unrelated changes. Worker summaries are claims, not proof.

Return:
VERDICT: APPROVED | CHANGES_REQUIRED | BLOCKED
FINDINGS: numbered findings with severity and exact evidence
MISSING_VERIFICATION: exact missing commands or behaviors
CLEANUP_SAFE: YES | NO with reason
```

## Final integration fixer

```markdown
You are the sole fixer for the final review.

Integration workspace: [PATH]
Specification, plans, and manifest: [PATHS]
Complete approved finding set: [PATH]
Whole diff and evidence: [PATHS]
Report file: [PATH]

Fix the entire valid finding set in one coherent wave. Preserve all approved lane behavior and frozen contracts. Use systematic debugging and TDD, run focused and integrated checks, commit the wave, and write full evidence. Do not reopen lane architecture or make unrelated improvements.

Return:
STATUS: DONE | DONE_WITH_CONCERNS | BLOCKED
CHANGE: [commit]
TESTS: [one-line evidence]
REPORT: [path]
RESIDUAL_CONCERNS: [one line or none]
```
