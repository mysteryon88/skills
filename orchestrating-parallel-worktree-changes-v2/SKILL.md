---
name: orchestrating-parallel-worktree-changes-v2
description: Use when a concrete implementation request or validated execution overlay has multiple independent write domains that can be assigned to isolated Git worktrees with per-Task review gates.
---

# Orchestrating Parallel Worktree Changes V2

<SUBAGENT-STOP>
If dispatched for one Task, lane, review, fix, or integration role, do not invoke this skill. Follow the assigned brief.
</SUBAGENT-STOP>

## Overview

Parallel implementation, ownership, validated waves, serial integration.

## Required Process Gates

- Use established dispatch, worktree, testing, debugging, review, and verification workflows.
- These capability gates use equivalent repository or harness facilities.
- Do not run another implementation controller over the same Tasks.
- Use `scripts/run_ledger.py` for recovery state and replan packets; do not hand-author either artifact.

## Workflow

1. **Preflight.** Read repository instructions, require a clean named base, freeze `BASE_COMMIT`, establish a green baseline.
2. **Require validated topology.** Require a source plan and approved, semantically validated overlay before recovery state, worktrees or writer prompts. An equivalent provider checks source fidelity, dependencies, ownership, conflicts, waves and isolation; ledger checks shape/hash/isolation only. Without semantic validation, leave V2 unstarted; work sequentially. `SEQUENTIAL` leaves this controller. Revalidate source hash; never repartition lanes.
3. **Start recovery state.** Initialize `scripts/run_ledger.py` from the source plan, overlay, named base, and frozen commit. Register every owned workspace, branch, report, integration result, review, and cleanup decision as it occurs.
4. **Isolate writers.** Require one worktree per concurrent lane. A soft overlap needs disjoint symbols, a shared-scaffolding owner, merge order, integration owner, and interaction checks. Schemas, migrations, manifests, lockfiles, generated outputs, and evolving contracts remain single-owner.
5. **Fail closed.** Without worktrees, stop concurrent writers. Return the ledger's `REPLAN_REQUIRED` packet to the coordinator; preserve unfinished Tasks, findings and resources. Replacement requires renewed semantic validation and approval.
6. **Dispatch by wave.** Send ready lanes together using `references/prompt-contracts.md`; resume each implementer for its next Task. Each Task keeps its commit, checks, and review boundary. Review while unrelated lanes continue; preserve dependencies and barriers.
7. **Review and fix.** One independent reviewer returns both verdicts unless distinct reviewers are required. Reuse singleton review only for unchanged complete scope. Preserve multi-Task lane review, bounded fix/re-review, and coordinator write restrictions.
8. **Integrate.** Merge approved lanes one at a time in dependency order. A dedicated integrator preserves frozen contracts and runs focused interaction checks after each merge.
9. **Verify the whole branch.** Run the full proportionate suite, independent final review, one complete final fix wave, and scoped re-review.
10. **Deliver and clean.** Reconcile a moved base, verify the target, remove only recorded clean and merged resources. Otherwise preserve the ledger for handoff.

Read `references/orchestration-protocol.md` before execution. Run helpers with `--help` before first use.

## Stop Conditions

Preserve resources when the overlay hash drifts, ownership changes, worktree isolation is unavailable, a contract is not frozen, hidden overlap appears, a Task or final review has a load-bearing finding, integration checks fail, the base cannot be reconciled, or cleanup proof fails. Never push, force-delete, or manually erase worktree directories without explicit authorization.
