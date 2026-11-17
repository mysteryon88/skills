# Agent Loop Contract

Use this reference when authoring a prompt for autonomous iteration, long-running coding, multi-agent execution, or an external agent controller. The output is still a prompt contract, not a claim that the current runtime can run it.

## 1. Resolve the execution surface

Identify the target runtime and the mechanism that actually persists work:

- **Codex Goal mode:** render a native Codex goal with `/goal <resolved objective>` as the first non-empty line. Do not imply that ordinary prompt text enables Goal mode.
- **Ralph-style CLI loop:** define how each iteration starts, how state is persisted outside the model context, and how the next iteration reads that state.
- **Bridge/controller-managed loop:** identify the controller, durable run or goal ID, backend adapter, event/state store, and recovery command. Do not assume a CLI worker is itself a durable scheduler.
- **ACP or another agent protocol:** confirm the target client and server support the required session, permission, streaming, cancellation, and resume operations.
- **Ordinary single execution:** if no persistent mechanism exists, write a bounded one-shot task and state the persistence gap. Never simulate durability with wording.

Treat target-runtime capabilities as claims to verify against installed versions and documentation. A prompt cannot create background execution, subagents, memory, quotas, or sandboxing.

## 2. Define the durable goal

State one observable outcome, not a vague instruction to keep working. Include only material details:

- target repository/workspace and starting revision;
- in-scope and excluded work;
- acceptance criteria and required artifacts;
- exact test/evaluation commands and expected evidence;
- dependencies and ownership boundaries;
- maximum iterations, wall-clock deadline, retry budget, and parallelism;
- model/provider constraints, quota source, and fallback authorization;
- checkpoint format/location and resume procedure;
- completion, blocked, cancelled, and budget-exhausted return states.

The goal must survive context reset. Persist a concise progress record containing completed work, evidence, current hypothesis, next action, decisions, blockers, and remaining budget. Do not persist hidden chain-of-thought.

## 3. Specify one iteration

Use a repeatable evidence-producing cycle:

1. Re-read the goal, instructions, current state, and latest checkpoint.
2. Inspect the relevant code, tests, logs, and actual artifacts.
3. Choose the smallest useful next action.
4. Execute within explicit tool and filesystem authority.
5. Run focused verification.
6. Compare the result with the baseline and completion predicate.
7. Save changed artifacts and a checkpoint.
8. Continue, retry, stop, or return a verified partial result.

Do not repeat an action unless new evidence or a changed hypothesis justifies it.

## 4. Multi-agent dispatch

Keep one coordinator responsible for decomposition, integration, and final acceptance. Before dispatch, require a ledger with:

| Field | Contract |
| --- | --- |
| Agent and role | Unique task-derived identity |
| Deliverable | One observable output |
| Inputs | Exact evidence and frozen contracts |
| Owned scope | Exclusive write paths or read-only coverage |
| Exclusions | Shared and out-of-scope surfaces |
| Dependencies | Predecessors and handoff consumers |
| Verification | Focused check and returned evidence |
| Budget | Model/provider, time, iterations, and retries |

Parallelize only independent work. Serialize shared schemas, migrations, lockfiles, generated files, common interfaces, and unresolved root-cause hypotheses. A worker's success message is not acceptance. The coordinator must inspect the actual combined state and rerun integrated checks.

If the target runtime lacks the explicitly required subagent capability, return `BLOCKED` with evidence. Do not pretend that sequential calls were parallel.

## 5. Budget and quota semantics

Separate these limits; never collapse them into a made-up remaining-token number:

- **Tokens:** actual input/output token counts, available only when the provider/runtime exposes usage data.
- **Spend:** USD usage, credits, per-key caps, and organization/workspace budgets.
- **Free request quota:** provider-defined request counters, which may be account-wide and shared across API keys or model variants.
- **Rate limits:** requests per minute, concurrency, provider capacity, and transient 429 responses.
- **Local controller budget:** max iterations, workers, wall time, retries, and locally reserved requests.

For OpenRouter specifically, `GET /api/v1/key` may expose `free_model_daily_requests.used/limit/remaining`, `limit_remaining`, usage totals, and effective budgets. The free-model counter is requests, not tokens, is account-wide, and resets on the UTC day boundary. The endpoint does not expose the remaining per-minute counter. Check current official documentation before hard-coding provider policy.

For each run, define warning and stop thresholds. If quota data is unavailable or stale, mark it `UNKNOWN`; do not treat it as unlimited. Do not switch to a paid model, another provider, another key, or another account without explicit authorization. Failed requests may consume quota; retries need backoff and a bounded retry budget.

When several agents share one provider quota, use one central reservation/dispatch gate. Independent agents must not each assume they own the full remaining allowance. If the controller cannot observe internal model calls, label its estimate advisory and do not claim exact accounting. Exact accounting requires a supported provider gateway or runtime usage events.

## 6. Failure and no-progress controls

Define distinct handling for:

- transient provider/network errors: bounded exponential backoff and `Retry-After` when present;
- quota exhaustion or hard spend limit: stop dispatch and return remaining verified work;
- model/backend incompatibility: stop; do not silently change backend;
- timeout or cancellation: terminate the process/session and preserve checkpoint evidence;
- repeated identical diff or unchanged failing test: no-progress stop;
- conflicting worker changes: pause integration and resolve by inspecting artifacts;
- missing permissions or unsafe requested operation: `BLOCKED`, never bypass.

A retry must change something material: input evidence, action, model/provider if authorized, or execution conditions. Replaying the same failed request indefinitely is not recovery.

## 7. Completion and return gate

Return `COMPLETE` only when the integrated artifact satisfies every required acceptance criterion and verification command. State the exact evidence.

Return `PARTIAL` when the budget ends but useful work is verified; identify the remaining gap and the next safe action.

Return `BLOCKED` when a missing capability, permission, decision, or external dependency prevents safe progress.

Return `FAILED` when the goal cannot be completed and no useful verified partial result remains.

Do not treat elapsed time, a worker's claim, a successful process exit, a green isolated test, or an empty diff as proof of completion. Never apply, publish, deploy, or merge solely because a loop says it is done.
