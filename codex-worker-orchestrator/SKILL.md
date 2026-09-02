---
name: codex-worker-orchestrator
description: Use when a non-trivial coding task may benefit from bounded implementation, specialist investigation, independent tests, skepticism, mandatory Hard-mode review, or isolated parallel work.
---

# Codex Worker Orchestrator

<SUBAGENT-STOP>
If you are already a spawned subagent, do not invoke this skill, orchestrate, review, or spawn. Execute only the dispatch brief.
</SUBAGENT-STOP>

## Core rule

The root owns the workflow. Superpowers owns lifecycle methodology; this skill selects the smallest sufficient custom-agent set. Children never become controllers or delegate.

Prefer one coherent packet over micro-delegation. Split only for a distinct role, independent evidence, isolated write surface, or separately useful long test.

This skill owns role selection, bounded packets, report reconciliation, and completion gates. `parallelizing-subagent-plans` alone compiles an approved plan's topology; `orchestrating-parallel-worktree-changes-v2` alone executes validated parallel writer lanes.

## Start

1. **REQUIRED SUB-SKILL:** Invoke `superpowers:using-superpowers` before repository action or execution advice.
2. Read applicable `AGENTS.md` files and confirm you are the root.
3. Resolve the directory containing this `SKILL.md` as `<skill-dir>` and run `<skill-dir>/scripts/preflight.py`. Never resolve the preflight script from the repository CWD.
4. Inspect actual available custom agents, profile, permissions, slots, spawn schema, and companions. Do not spawn when the user forbids subagents.
5. If preflight does not report `ok: true` with `install_mode` `lite` or `hard`, do not route or spawn. Read [INSTALL.md](INSTALL.md), report the exact missing or conflicting roles, and present one documented install command for explicit user approval. Never run the installer or modify global Codex configuration without that approval. After a successful install, tell the user to start a new Codex session before routing.

The live parent permission mode is the ceiling. Role configuration cannot bypass policy, approvals, unavailable models, or missing tools.

## Choose a mode

- **Lite:** exactly `luna_worker` and `luna_test_runner`. Root writes the detailed plan, worker implements, root inspects the diff, runner executes the planned checks, and root reconciles.
- **Hard:** all registered roles. Use for architecture, uncertainty, runtime diagnosis, security-sensitive or cross-module work. Every Hard write requires `sol_reviewer` on Sol/xhigh without fallback.

Lite requires an approved plan with ordered steps, exact files and write surfaces, protected interfaces, dependencies, binary acceptance criteria, exact checks, and stop conditions. Its sequence is:

```text
root plan -> luna_worker -> root diff -> luna_test_runner -> root reconciliation
```

The worker follows only that plan. The runner never edits tracked files or acts as reviewer. High-rigor or confirmed integration-debugging writes require Hard.

## Route the task

Route through the applicable Superpowers process, including `superpowers:writing-plans`, `superpowers:test-driven-development`, `superpowers:executing-plans`, `superpowers:requesting-code-review`, `superpowers:using-git-worktrees`, and `superpowers:finishing-a-development-branch` when relevant. Read `references/routing-matrix.md` only when delegation, escalation, testing economics, or parallelism is relevant. Read `references/dispatch-contract.md` immediately before the first spawn.

Validate the route request, run `<skill-dir>/scripts/resolve_roles.py` with `--available-agents` and `--available-skills` from preflight, and validate every packet against `task-packet.schema.json`. Use `run_state.py` for multi-agent, high-risk, or resumable work; it is a ledger, never schedules agents, and never supplies write isolation.

For complex planning, keep judgment in root when the active root model is Sol; otherwise use `sol_architect` for plan inputs while Superpowers owns approval.

Before every spawn announce the role, actual agent type, purpose, and selection reason. Give one self-contained packet with ownership, acceptance criteria, exact checks, stop conditions, and output channel.

Keep short blocking tests in root outside Lite. Dispatch long or independent checks only when useful. Shared ports, databases, fixtures, caches, or services force sequential execution.

Never place overlapping writers in one checkout. Parallel writers require independent packages, disjoint surfaces, isolated worktrees, a validated overlay, and explicit user approval. Otherwise serialize.

Discover the parallel companion project-first, then global. Without it, use only the conservative native fallback from the dispatch contract.

## Reconcile and finish

After every report, record one decision with `run_state.py reconcile --task-id ... --report-id ... --decision ...`: `ACCEPT`, `REPAIR`, `INVESTIGATE`, `REPLAN`, or `BLOCK`. Give repair-round reports distinct `report_id` values under the same routed task. Concerns and follow-ups are advisory and never widen scope. Completion requires every report's current decision to be `ACCEPT` followed by fresh integrated verification.

After two failed native-CWO writer attempts against the same claimed cause, run `superpowers:systematic-debugging` before another writer. In Lite, then request authorization to switch to Hard or record `BLOCK`; never call unavailable Hard specialists. In Hard, use `skeptic` or `sol_architect` when their documented triggers apply. This does not replace the V2 executor's fix policy.

Hard completion requires accepted Sol/xhigh review. Lite completion requires root diff inspection and successful runner evidence. Missing reports, non-`ACCEPT` decisions, unresolved findings, or stale verification forbid completion. Invoke `superpowers:verification-before-completion` before success claims.
