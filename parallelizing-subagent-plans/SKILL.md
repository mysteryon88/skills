---
name: parallelizing-subagent-plans
description: Use when an approved numbered implementation plan is ready for delegated execution and dependencies, ownership, contracts, or exclusive resources may affect concurrency safety.
---

# Parallelizing Subagent Plans

<SUBAGENT-STOP>
If dispatched as an implementer, reviewer, fixer, or integrator, do not invoke this skill. Follow the assigned brief.
</SUBAGENT-STOP>

<HARD-GATE>
With an approved numbered plan and delegated execution selected, do not start implementation, create worktrees, or dispatch writers until this skill validates an execution overlay.
</HARD-GATE>

## Purpose

Compile an approved plan into a dependency-safe schedule. Keep coherent chains with one owner; minimize setup and review overhead without weakening verification.

Use repository or harness planning, dispatch, worktree, testing, debugging, review, and verification capabilities; no named workflow bundle is required.

## Workflow

1. Before analysis, read `references/plan-parallelization-protocol.md` and `references/review-and-integration.md` completely.
2. Read the plan, approved spec, repository instructions, status, Git history, and prior execution ledger. Completion needs checked steps plus manifest commit/check evidence.
3. Run `python <skill-dir>/scripts/compile_overlay.py <source-or-master-plan> --project <repo> --output <overlay-plan> --isolation <worktree|unavailable|unknown> --check <command> --git-executable <absolute-git> --format json`. It runs every compilation stage. A missing or non-V2 parallel executor blocks `PARALLEL` handoff; `codex-worker-orchestrator` remains optional.
4. A master plan is expanded only from `## Subplans`; recursive discovery is forbidden. The normalized plan carries namespaced source bindings and an LF-canonical semantic hash. If the compiler returns `constraint-map-required`, fill the generated skeleton's `kind`, affected Tasks, and `resource` where exclusive, then rerun with `--constraint-map`.
5. Inspect hidden ownership, contracts, generated outputs, schemas, migrations, manifests, fixtures, and mutable resources. Classify relations as hard implementation, ordering-only, frozen contract, shared-file conflict, or exclusive resource. If the source lacks an edge, resource, or useful split, draft an evidence-backed repair and obtain explicit approval. Use `references/parallel-plan-template.md` and rerun `scripts/validate_parallel_plan.py`.
6. Optimize the safe critical path. Compact adjacent waves into persistent lanes when dependencies and whole-lane ownership/resources permit. Hard dependencies stay ordered within a lane or cross to later waves. Prelude needs evidence that it unlocks parallelism; joins may fork again; only explicit barriers create epilogue. Compare expected overlap with orchestration overhead; topology depth is not elapsed time.
7. Use `SEQUENTIAL` when worktrees are unavailable/unverified or no wave can open two lanes. `PARALLEL` allows at most four active worktree lanes per wave. Across different lanes, a producer and consumer may share a wave only when their complete backticked signature matches exactly, a declared test, fixture, or mock plus executable test command freezes it, and no unfrozen dependency cause exists. For an oversized singleton blocker, the coordinator drafts an evidence-backed partition with ownership, interfaces, checks, and mapping to the original Task. A human explicitly approves the revised plan before execution. No runtime helper searches `PATH` or the project for Git.

Optional `codex-worker-orchestrator` may inform packets, but never owns topology or execution. Project discovery precedes global roots; report incompatible project copies.

## Verdict and handoff

| Verdict | Required handoff |
|---|---|
| `PARALLEL` | Show lanes, waves, contracts, constraints, overlaps, integration order, checks, and risks; wait for one explicit approval; invoke `orchestrating-parallel-worktree-changes-v2` as the only top-level executor. |
| `SEQUENTIAL` | State the concrete dependency, ownership, or resource reason; continue with the repository's sequential implementation workflow without another confirmation. |

For `REPLAN_REQUIRED`, follow the protocol's packet workflow: verify hashes and evidence, replace the overlay, use `SEQUENTIAL` when isolation failed, and reapprove changed parallel topology.
