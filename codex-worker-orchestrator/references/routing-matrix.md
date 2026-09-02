# Routing matrix

## 1. Controller boundary

The root owns task classification, Superpowers lifecycle, approvals, plan quality, dispatch, write isolation, reconciliation, integration, diff inspection, and completion. Every child gets one self-contained packet and never delegates.

### Dispatch economy

Use the smallest agent set that creates a real evidence, capability, ownership, or verification advantage. Prefer one broader bounded packet over multiple micro-packets when one role can preserve context and the write surface remains coherent. Do not delegate a task merely to keep an agent busy, and do not split sequential steps that share one root cause or interface owner.

### Ownership split with the parallel skills

`codex-worker-orchestrator` selects roles and reconciles their reports. It does not compile dependency topology for an approved numbered plan and does not execute parallel writer lanes. `parallelizing-subagent-plans` owns the topology and verdict; `orchestrating-parallel-worktree-changes-v2` owns validated worktree execution, integration, and its own bounded fix rounds. A child never becomes a recursive subplanner or second controller.

### Report reconciliation

After every report the root persists exactly one current decision: `ACCEPT`, `REPAIR`, `INVESTIGATE`, `REPLAN`, or `BLOCK`. A repair report keeps the routed `task_id` and uses a distinct `report_id`, so earlier reports and decisions remain auditable. Suggested follow-ups are advisory and cannot expand the approved goal automatically. Completion requires `ACCEPT` for every recorded report. For native CWO execution, two failed writer or fix attempts against the same claimed root cause force a `superpowers:systematic-debugging` reset. Lite then switches to Hard only with user authorization or records `BLOCK`; Hard applies skeptic or architecture gates when their triggers match.

## 2. Install modes

| Mode | Roles | Selection rule |
|---|---|---|
| Lite | `luna_worker`, `luna_test_runner` | Choose for a clear bounded change that the root can fully specify and review. |
| Hard | All 11 registered roles | Choose when evidence gathering, architecture, runtime diagnosis, skepticism, security review, or independent Sol review may be needed. |

The installer asks for the mode interactively. Non-interactive installation requires `--mode lite` or `--mode hard`.

## 3. Lite plan and execution gate

The root must finish a detailed, unambiguous plan before dispatching `luna_worker`. The plan contains ordered steps, exact allowed files and write surfaces, protected interfaces, forbidden changes, dependencies, binary acceptance criteria, exact verification commands with expected results, and stop conditions.

The sequence is fixed:

1. root writes and checks the plan;
2. `luna_worker` executes only the plan;
3. root inspects the actual diff and scope;
4. `luna_test_runner` runs the exact planned commands without tracked-file edits;
5. root reconciles evidence and owns completion.

A missing worker, runner, plan element, diff inspection, or runner report blocks completion. The runner is not a reviewer. High/extreme-complexity, high-uncertainty, high/critical-risk, and confirmed integration-debugging writes are blocked in Lite. Architecture, security-sensitive work, unresolved runtime failures, and tasks needing independent review require Hard mode.

## 4. Hard role matrix

| Observable need | Primary role | Escalation or gate |
|---|---|---|
| Locate symbols, callers, config, and data flow | `repo_explorer` | Root integrates evidence. |
| Verify external library, API, or documentation behavior | `docs_researcher` | Check installed or vendored source first; report exact versions and cross-check implementation with tests or exported types. |
| Reproduce an unexplained failure | `runtime_investigator` | Do not dispatch a fixer until root cause is confirmed. |
| Resolve architecture and boundary trade-offs | `sol_architect` | Returns plan inputs, never a final implementation plan; Superpowers owns design approval. |
| Attack assumptions and claimed readiness | `skeptic` | Returns gates or replan advice, never final acceptance. |
| Implement a clear packet | `luna_worker` | Mandatory `sol_reviewer` after the Hard write. |
| Implement a confirmed connected multi-file fix | `terra_worker` | Mandatory `sol_reviewer` after the Hard write. |
| Run long/noisy/parallelizable tests | `luna_test_runner` | Root collects before dependent work. |
| Review any Hard file-changing result | `sol_reviewer` | Sol/xhigh, mandatory, no Terra fallback. |
| Review auth, secrets, CI/CD, parsers, process execution, or trust boundaries | `security_reviewer` | Additional to `sol_reviewer`, not a replacement. |
| Change only established documentation | `docs_writer` | Mandatory `sol_reviewer` after the Hard write. |

## 5. Skeptic triggers

Invoke `skeptic` when at least one condition is present:

- the plan depends on an unverified assumption;
- API, schema, migration, persistence, cache, concurrency, authorization, or background execution changes;
- two evidence sources or agents disagree;
- in Hard, two implementation attempts failed;
- tests are green but the proof is weak or overly mocked;
- rollback, compatibility, or failure behavior is unclear;
- a high-risk change is about to enter implementation or final review.

Do not invoke it for formatting, renaming, a mechanical local edit, an ordinary test command, or simply because the role exists.

Expected output: assumptions, contradictions, failure scenarios, missing evidence, alternatives, required gates, and `PROCEED`, `PROCEED_WITH_GATES`, `REPLAN`, or `BLOCK`.

## 6. Test routing

In Lite, `luna_test_runner` is mandatory after each write and receives commands from the approved plan. For standalone or Hard testing, the configured spawn threshold is 120 seconds.

| Test situation | Route |
|---|---|
| Lite post-write verification | `luna_test_runner`, exact planned commands. |
| One standalone focused command below threshold and blocks the next step | Run in root. |
| Duration unknown but likely short | Run in root once, then reassess from evidence. |
| Long, noisy, or root has useful independent work | `luna_test_runner`. |
| Multiple independent suites | Up to configured `max_parallel_runners`, one packet per suite. |
| Shared database, port, fixture, cache, service, or mutable environment | Sequential, even with multiple runners. |
| Failure needs diagnosis | Return to `superpowers:systematic-debugging`; do not keep spawning runners. |

The runner receives exact commands, timeout/progress expectations, shared-resource constraints, and a tracked-file cleanliness check. It never authors tests, fixes code, or reviews the diff.

## 7. Parallelism and worktrees

Read-only packets may run in parallel when they are independent. Test packets may run in parallel only without shared mutable resources.

A second writer requires all of the following:

1. independently useful packages;
2. disjoint canonical write surfaces with no parent/child overlap;
3. isolated Git worktrees and branches;
4. a validated dependency overlay;
5. explicit user approval before worktrees are created.

If any item is missing, use sequential writers. Never treat a role declaration as a filesystem lock. `parallelizing-subagent-plans` owns topology and only its `PARALLEL` output may target `orchestrating-parallel-worktree-changes-v2`.

## 8. SDD role mapping

In Hard `superpowers:subagent-driven-development`, the implementer is `luna_worker`, `terra_worker`, or `docs_writer` according to the packet. Mandatory review applies to every task-scoped write and the final integrated state through `sol_reviewer` on Sol/xhigh. The same reviewer role is used for ordinary and final review so the quality floor cannot silently drop.

Lite uses the root-authored plan, one `luna_worker` implementation stage, one `luna_test_runner` verification stage, and root-owned diff inspection instead of a child reviewer. A fix round resumes `luna_worker` with the exact finding and repeats the runner commands.

## 9. Fallback and escalation

Fallbacks are explicit registry edges only. A fallback must preserve the requested mutation and safety class.

- `luna_worker` may fall back to `terra_worker` only in Hard for connected implementation.
- `terra_worker` may fall back to `luna_worker` only when the packet remains bounded.
- `runtime_investigator` may fall back to read-only exploration, which stops at evidence.
- `sol_architect`, `skeptic`, `luna_test_runner`, `sol_reviewer`, and `security_reviewer` have no weaker fallback.

Missing `luna_worker` or `luna_test_runner` blocks Lite. Missing `sol_reviewer` blocks every Hard write route. Missing `sol_architect` blocks architecture work rather than pretending a cheaper role made the same judgment.

## 10. End-to-end workflows

```text
Lite:
root detailed plan -> luna_worker -> root diff inspection -> luna_test_runner -> root reconciliation -> root verification

Hard:
classify with Superpowers
  -> gather repository/docs/runtime evidence as needed
  -> sol_architect for ambiguous design
  -> skeptic when trigger conditions are present
  -> bounded worker packet
  -> root or luna_test_runner according to test economics
  -> mandatory sol_reviewer xhigh
  -> security_reviewer when security-sensitive
  -> root reconciliation: ACCEPT | REPAIR | INVESTIGATE | REPLAN | BLOCK
  -> fix round and repeated review if required
  -> fresh integrated verification by root
```
