# Parallel Subagent Mode

Use this reference whenever execution is `PARALLEL_SUBAGENTS`. The prompt must instruct the main executor to remain the orchestrator and integration owner. Subagents perform bounded units; they do not replace final judgment or combined-state verification.

Capability gates apply to the target executor described by the prompt, not the current prompt-authoring runtime. Do not block prompt creation merely because the current runtime lacks subagent tools. Encode the target executor's preflight and required fallback or `BLOCKED` behavior inside the produced prompt.

## Capability and decomposition gate

Before dispatch, require the executor to inspect applicable instructions, available subagent tools, task boundaries, shared contracts, and dependencies. Parallel work requires at least two worthwhile units that can proceed concurrently.

- If the user explicitly requires subagents or parallel execution, absence of the capability or viable independent units is `BLOCKED`. Return evidence, completed safe work, the strongest verified partial result, and one operator action. Do not simulate parallel execution or silently downgrade it.
- If `PARALLEL_SUBAGENTS` was inferred only as an optimization, record the reason and use `SEQUENTIAL` when the gate fails.

## Dispatch contract

Require a dispatch ledger before workers start:

| Field | Requirement |
| --- | --- |
| Agent ID and role | Task-derived identity; no generic role-only dispatch |
| Goal and deliverable | One observable result |
| Inputs | Exact evidence, contracts, and starting state |
| Owned scope | Primary components or exclusive write ownership |
| Exclusions | Shared or out-of-scope surfaces the worker must not change |
| Dependencies | Predecessors, frozen assumptions, and handoff consumers |
| Verification | Focused check the worker must run or evidence it must return |

Derive roles from the discovered architecture and risk map. Do not create a fixed team or arbitrary worker count. For read-only work, give each worker exclusive primary coverage; overlap only for deliberate independent verification. For changes, require exclusive write ownership. Serialize shared interfaces, schemas, migrations, lockfiles, generated output, unresolved root-cause hypotheses, and any unit whose safe boundary is uncertain.

## Execution waves

1. **Discover and freeze:** establish shared instructions, current state, ownership boundaries, contracts, and dependency graph.
2. **Parallel workers:** run only ready independent units concurrently; the orchestrator owns undispatched cross-cutting work.
3. **Integrate:** collect structured handoffs, inspect the actual combined state, resolve conflicts by evidence, and run dependent work.
4. **Verify:** run combined-state verification and an independent adversarial check when risk justifies it.

Each handoff reports inspected or changed scope, evidence, decisions, commands and outcomes, remaining risks, blockers, and exact downstream dependencies. Status-only worker messages do not count as deliverables.

## Integration integrity

The integration owner must verify material worker claims against current artifacts, reject unsupported findings or changes, resolve duplicates and contradictions, and run checks on the integrated result. A successful worker result never proves the whole task complete. Return one coherent final artifact plus a compact orchestration summary when the user requested role or coverage accountability.
