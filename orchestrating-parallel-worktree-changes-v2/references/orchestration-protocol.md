# Parallel Orchestration Protocol

This document is the execution contract for `orchestrating-parallel-worktree-changes-v2`. Implementation requires a source plan and an approved, semantically validated `PARALLEL` overlay from an available equivalent provider. Semantic validation must check source fidelity, dependencies, ownership, conflicts, waves and worktree isolation. The existing ledger checks shape/hash/isolation only; it does not establish semantic validity.

## Contents

1. Controller ownership
2. Preconditions
3. Recovery manifest and replan handoff
4. Worktree isolation
5. Ownership and soft overlap
6. Dispatch waves
7. Per-Task and lane review
8. Serial integration
9. Epilogue and whole-branch review
10. Moving base and delivery
11. Cleanup

## 1. Controller ownership

Exactly one top-level controller owns a Task set.

- A `PARALLEL` overlay selects this skill only when `executor` is exactly `orchestrating-parallel-worktree-changes-v2`.
- A `SEQUENTIAL` overlay selects the repository's sequential implementation workflow instead.
- Never run another implementation controller and this controller over the same Tasks.
- Lane agents, reviewers, fixers, and integrators never invoke another implementation controller.

When an overlay is supplied, it is the approved topology. Before implementation:

1. run the overlay validator against the named source plan;
2. verify the source SHA-256 still matches;
3. read its completed Tasks, prelude, lanes, waves, task dependencies, frozen contracts, allowed overlaps, integration order, review policy, verification commands, and cleanup policy;
4. compare the overlay ownership assumptions with the current repository;
5. stop with `REPLAN_REQUIRED` if repository inspection reveals hidden overlap or changed contracts.

Do not silently collapse, split, reorder, or broaden validated lanes. Return topology changes to the coordinator for equivalent semantic validation and renewed approval.

Without an overlay, use the repository's planning workflow and an available equivalent semantic validation provider. Obtain an explicitly approved, semantically validated overlay before creating the recovery ledger, worktrees, or writer prompts. If that capability is unavailable, leave V2 unstarted and let the root execute sequentially. A `SEQUENTIAL` verdict selects the repository's sequential executor and ends this controller. Never construct or execute an ad-hoc local topology; ledger validation is not a substitute for semantic validation.

## 2. Preconditions

Record:

- named `BASE_BRANCH` and exact `BASE_COMMIT`;
- clean initial status and user-owned changes, if any;
- project setup and focused/full verification commands;
- available worker, CPU, memory, service, and rate-limit capacity;
- availability of isolated Git worktrees for every concurrent lane;
- integration authorization and cleanup ownership.

Run the repository's established baseline checks. A broken baseline blocks the run unless the request explicitly owns those failures. Never stash, reset, overwrite, or hide user changes to make a baseline look clean.

Use two to four concurrent writers by default. Reduce the budget when tests, builds, databases, ports, devices, or services contend.

## 3. Recovery manifest and replan handoff

Keep a coordinator-owned manifest outside tracked source. Use a harness-owned scratch path when one is provided. Otherwise `scripts/run_ledger.py` resolves the common Git directory and owns `<git-common-dir>/parallel-runs/<run-id>/recovery.json`. Do not assume that a worktree's `.git` is a directory. Never hand-author, partially overwrite, or reuse another run's manifest.

Initialize it after overlay validation and before worktree creation:

```bash
python <skill-dir>/scripts/run_ledger.py init \
  --repo . \
  --run-id <stable-run-id> \
  --source-plan <path> \
  --overlay <path> \
  --base-branch "$BASE_BRANCH" \
  --base-commit "$BASE_COMMIT"
```

Use `set-review`, `record-completion`, `set-lane-review`, `register-resource`, `record-integration`, `record-final-review`, and `record-cleanup` with one small JSON record at a time. Each command validates the complete state and atomically replaces the manifest. `status` and `validate` are read-only. The helper snapshots source inputs so recovery evidence survives later drift while reporting that drift explicitly.

The recovery manifest must survive context compaction and contain:

- optional source request, source plan, overlay, immutable snapshots, and hashes;
- base branch and commit;
- isolation mode;
- every Task and lane, ordered dependencies, owned and forbidden surfaces;
- frozen contracts and soft-overlap records;
- workspace paths, branches, worker identities, reports, commits or path hashes;
- per-Task and per-lane reviews, fix rounds, findings, and rulings;
- integration sequence and evidence;
- final review, reconciliation, delivery, and cleanup state.

Trust the manifest and Git history over conversational memory. Never read or overwrite another run's scratch directory.

Every coordinator-level replan stop uses the ledger before returning:

```bash
python <skill-dir>/scripts/run_ledger.py replan \
  --repo . \
  --run-id <stable-run-id> \
  --reason-code WORKTREE_UNAVAILABLE \
  --reason "Isolated Git worktrees cannot be created." \
  --recommended-verdict sequential
```

The helper derives remaining/completed Tasks, review state, resources, frozen hashes, and manifest hash. It atomically writes `<run-dir>/replan-required.json` with this coordinator-facing shape:

```json
{
  "status": "REPLAN_REQUIRED",
  "reason_code": "WORKTREE_UNAVAILABLE",
  "reason": "Isolated Git worktrees cannot be created in this environment.",
  "source_plan": "docs/plans/feature.md",
  "source_snapshot_path": "<absolute immutable source snapshot path>",
  "source_sha256": "<64-character SHA-256>",
  "overlay_path": "docs/plans/feature-execution.md",
  "overlay_sha256": "<64-character SHA-256>",
  "base_branch": "main",
  "base_commit": "<full commit>",
  "manifest_path": "<absolute recovery.json path>",
  "manifest_sha256": "<64-character SHA-256>",
  "remaining_tasks": [2],
  "completed_task_commits": [
    {
      "task": 1,
      "commits": ["<full commit>"],
      "checks": ["<focused verification command>"],
      "completion_origin": "runtime-replan",
      "spec_review": {"verdict": "PASS", "evidence": ["<report path>"]},
      "quality_review": {"verdict": "APPROVED", "evidence": ["<report path>"]}
    }
  ],
  "review_state": [
    {
      "task": 2,
      "status": "CHANGES_REQUIRED",
      "fix_round": 2,
      "open_findings": [
        {
          "id": "I-1",
          "severity": "Important",
          "summary": "<finding summary>",
          "evidence": ["<review report path>"]
        }
      ],
      "reports": ["<Task report path>"]
    }
  ],
  "resources": [
    {
      "kind": "worktree",
      "path": "<absolute path>",
      "branch": "<branch>",
      "state": "preserve"
    }
  ],
  "recommended_verdict": "sequential"
}
```

Use a stable `reason_code`: `WORKTREE_UNAVAILABLE`, `HIDDEN_OVERLAP`, `CONTRACT_DRIFT`, or `OWNERSHIP_DRIFT`. Return the source plan, old overlay, recovery manifest, and exact replan packet path to the top-level coordinator. Dispatch no more writers or resume/replacement work until an available equivalent provider semantically validates the replacement and the coordinator obtains renewed approval. If that capability is unavailable, preserve the packet and resources and return to the caller.

`completed_task_commits` is a list of the shown evidence objects. `review_state` is a list covering every and only `remaining_tasks`, with a unique `task` ID per record; each record carries `status`, fix round `0..5`, open findings with stable ID/severity/summary/evidence, and report paths. `resources` is a list of owned resource records whose `kind` is `worktree`, `branch`, `report`, `manifest`, or `scratch`; every `path` is absolute, every record has preservation `state`, and worktree/branch records also name `branch`. Verify packet, recovery manifest and prior overlay hashes before equivalent semantic validation and approval of any replacement.

Only Tasks with a recorded commit, focused evidence, and both passed review gates may enter `completed_task_commits`. Runtime completion uses `completion_origin: runtime-replan`; the source plan remains immutable and does not need a synthetic checkbox edit. All unfinished Tasks and every open finding remain in `remaining_tasks` and `review_state`; pass that state to the replacement sequential executor rather than resetting the fix loop. `lane_reviews` remains in the packet as executor recovery evidence while the coordinator obtains validated replacement topology. `Critical` and `Important` are finding severities, not Task priorities, and no priority label bypasses isolation, dependency, or review gates.

## 4. Worktree isolation

Parallel writers require isolated Git worktrees. Prefer the harness's native worktree mechanism. If none exists, use `scripts/worktree_pool.py` after confirming `.worktrees/` is ignored:

```bash
python <skill-dir>/scripts/worktree_pool.py create \
  --repo . \
  --run-id <stable-run-id> \
  --base-ref "$BASE_COMMIT" \
  --lane <lane-a> \
  --lane <lane-b>
```

The fallback creates one integration branch and one branch/worktree per lane from the same frozen base. The coordinator owns topology. Lane agents do not create worktrees, switch branches, merge, rebase, or push.

Run checkout-specific setup in each workspace. Confirm focused tests can start from the frozen base before blaming lane code for an environment failure.

If isolated worktrees cannot be created, do not dispatch concurrent writers in one checkout. Preserve recovery state, have the ledger write the section 3 packet with `reason_code: WORKTREE_UNAVAILABLE`, and return it to the coordinator. A sequential replacement still requires equivalent semantic validation and renewed approval, preserving unfinished Tasks, open findings and resources.

## 5. Ownership and soft overlap

One writer owns each file by default.

A validated worktree `soft-overlap` is the only exception. It must name:

- the shared non-hard file;
- disjoint symbols, types, translation keys, or regions per lane;
- one owner for imports and other shared scaffolding;
- serial merge order;
- an integration owner;
- interaction checks covering both changes.

The exception never applies to dependency manifests, lockfiles, schemas, migrations, generated outputs, root build configuration, or an evolving public contract. If either worker needs a symbol or region owned by the other, stop both affected lanes and return `REPLAN_REQUIRED`.

Worktrees prevent simultaneous filesystem writes. They do not prove API compatibility. Frozen producer/consumer contracts remain binding.

## 6. Dispatch waves

A lane is a sequential chain. All lanes ready in one wave are dispatched in the same controller turn. Later waves wait for their declared dependencies and integration barriers.

Keep one implementer context and worktree for the lane; resume it after each Task's review instead of spawning a new implementer. Dispatch every ready lane before waiting for any one result. Review and resume a ready lane while unrelated lanes continue; do not wait for the entire wave merely to review a Task or resume its same-lane successor. Respect the harness's available slots for both writers and reviewers.

Before each lane starts, write a lane brief that includes:

- source Task text or exact task-brief files;
- ordered Task list;
- observable outcomes and global constraints;
- owned and forbidden paths/symbols;
- frozen contracts and dependency outputs already available;
- focused tests and shared-resource rules;
- report path and return contract.

Each lane implementer executes Tasks in order, one controller dispatch at a time. Every source Task remains a distinct TDD and review boundary:

1. write or identify the failing test/reproduction;
2. verify the failure reason;
3. implement the smallest coherent change;
4. run focused checks;
5. inspect ownership and diff;
6. create a Task commit;
7. append the Task report and return to the coordinator;
8. wait until specification and quality review, any scoped fix rounds, and scoped re-review pass before the coordinator resumes the lane on its next Task.

The next Task is never implemented speculatively while the current Task is under review. A dependent Task stays blocked even when the same worker owns both Tasks.

A worker returns one status:

- `DONE`;
- `DONE_WITH_CONCERNS`;
- `NEEDS_CONTEXT`;
- `REPLAN_REQUIRED`;
- `BLOCKED`.

Do not force a blocked worker to repeat the same attempt without new context, an independent capability-matched worker, a smaller Task, or a corrected plan.

## 7. Per-Task and lane review

Review may run while unrelated lanes continue. By default, the same reviewer, independent of the implementer, checks both dimensions in order in one dispatch:

- specification compliance returns `SPEC: PASS`;
- after specification passes, engineering quality returns `QUALITY: APPROVED`.

Use distinct reviewers when the source plan or project policy requires them, retaining specification-before-quality order. Otherwise use the combined Task reviewer prompt. Use a diff package scoped to that Task's commit range; reviewers never edit code. Reviewer self-reports and test summaries are claims, not proof. Record open findings with `set-review`; only `record-completion` can remove a Task from remaining state, and it requires commit/check evidence plus both passed review records. Both records may cite the same combined report. Specification failure blocks completion; do not run or approve quality yet. In lane ledger records quality remains `NOT_STARTED` until specification passes.

Critical and Important findings enter a bounded scoped fix loop:

- rounds 1-3 resume the original implementer;
- rounds 4-5 prefer a fresh independent implementer with the required capability; when capacity is unavailable, use a fresh isolated context with the complete finding packet;
- every round reruns focused tests and receives a scoped re-review;
- the coordinator never edits production code;
- Minor findings go to the ledger for final triage;
- after round 5, every residual finding gets an explicit ruling;
- a real load-bearing residual blocks the lane.

After all Tasks in a lane pass, dispatch a lane-level review for ownership, cross-Task consistency, duplicated foundations, missing acceptance criteria, and integration notes. Record its specification and quality verdicts with `set-lane-review`. The ledger rejects integration until every Task in that lane is complete and both lane verdicts pass.

For a single-Task lane, reuse its accepted Task review without another dispatch only when it explicitly covered the unchanged full lane diff, ownership and integration readiness, with no intervening changes or unresolved findings. Record both lane verdicts and reference that exact evidence. A changed diff, missing lane scope, multi-Task lane, or binding requirement for a separate lane reviewer requires the lane review. Whole-branch review after integration is always retained.

## 8. Serial integration

Integration is deliberately single-threaded.

1. enter the integration worktree;
2. merge one approved lane branch in recorded order;
3. run that lane's focused checks plus contracts and interactions with already integrated lanes;
4. record the merge commit and results with `record-integration`;
5. continue to the next lane.

For a textual conflict, dispatch one dedicated integrator with the source plan, overlay, both lane briefs and reports, frozen contracts, conflicted files, already integrated constraints, and required checks. The integrator preserves both approved behaviors and adds a regression test when the conflict reveals an untested interaction.

A clean merge is not semantic proof. Check producer/consumer boundaries, errors, versions, optional fields, serialization, UI/backend assumptions, schemas, artifacts, and lifecycle behavior.

## 9. Epilogue and whole-branch review

Execute overlay epilogue Tasks after all required lanes are integrated. They normally own broad tests, build, packaging, migrations, documentation synchronization, artifact verification, and process cleanup.

Then:

1. inspect the whole diff from `BASE_COMMIT`;
2. run the full proportionate suite and every named integrated check;
3. dispatch an independent reviewer whose capabilities match the repository and risk surface, with the spec, source plan, overlay, manifest, reports, findings, and fresh evidence;
4. send the complete final finding set to one integration fixer in one wave;
5. run focused and broad checks;
6. perform one scoped re-review of the fix diff.

Record the resulting verdict with `record-final-review`. The ledger rejects an approval before every Task and lane integration gate has completed in the frozen order.

There is no second final fix wave. Contestable or non-load-bearing residuals receive explicit ledger rulings. A real load-bearing residual blocks delivery.

## 10. Moving base and delivery

Compare the current base head with `BASE_COMMIT`. If it moved, merge the current base into integration, resolve conflicts through the integrator, rerun affected/full checks, and review reconciliation behavior when needed. Never reset or force-update the base.

Local auto-merge is allowed only when the direct request or project policy authorizes it. Otherwise use the repository's normal finishing or handoff workflow once for the integration result, never for each lane.

Do not push or create a pull request unless separately requested.

## 11. Cleanup

Cleanup happens only after the final target branch contains every approved lane and passes fresh verification.

Fallback worktree cleanup:

```bash
python <skill-dir>/scripts/worktree_pool.py cleanup \
  --repo . \
  --run-id <stable-run-id> \
  --merged-into "$BASE_BRANCH"
```

The script refuses dirty, unmerged, locked, foreign, or unsafe resources. It removes only resources recorded for this run, deletes branches without force, and prunes stale Git registrations. After successful preflight it journals every worktree and branch operation; an interrupted cleanup resumes from the last atomic checkpoint, while unexplained missing or recreated resources still fail closed.

After each cleanup attempt, write its `pending`, `in_progress`, `blocked`, or `complete` status and evidence through `run_ledger.py record-cleanup`. The ledger accepts `complete` only after an approved final review marked cleanup safe.

Native worktrees use their native cleanup primitive for exactly recorded resources.

On any implementation, review, integration, reconciliation, verification, or cleanup failure, preserve recovery state and report exact paths, branches, commits, and blockers.
