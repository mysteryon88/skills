---
name: codex-worker-orchestrator
description: Use when bounded delegation helps or substantive specifications/plans need independent critique. Handle simple questions, focused lookups, routine edits, and short quiet non-build checks directly.
---

# Codex Worker Orchestrator

<SUBAGENT-STOP>
If already a spawned subagent, execute only the dispatch brief. Do not invoke this skill, orchestrate, or spawn.
</SUBAGENT-STOP>

## Delegation

Loading never requires spawning. Do not spawn when the user forbids subagents.

- **Direct:** simple questions, focused lookups, mechanical edits, known small fixes, short quiet non-build checks. No preflight, ledger, or install prompts. Material risk, uncertainty, or security impact prevents Direct.
- **Delegate:** require bounded benefit exceeding overhead. Dispatch useful ready independent packets together within live slots and task budgets; add only distinct deliverables or required reviews.
- **Escalate:** Sol handles material uncertainty/risk. Astra requires `extreme` complexity, unresolved prior Sol analysis, a decisive evidence check and recorded escalation reason.

Reclassify on scope/evidence/risk/failure changes; length or approval alone never requires children.

## Delegation preflight

1. Read `AGENTS.md`; use `superpowers:using-superpowers` and relevant lifecycle; reuse approvals.
2. Resolve the directory containing this `SKILL.md`; run `<skill-dir>/scripts/preflight.py`. Never resolve the preflight script from the repository CWD.
3. Inspect actual available custom agents, models, profile, slots, permissions, spawn schema and companions. The live parent permission mode is the ceiling.
4. Require `ok: true` and `install_mode` `lite` or `hard`; otherwise do not spawn. Continue safe Direct work if sufficient or report missing/conflicting roles and [INSTALL.md](INSTALL.md). Global installation/configuration requires user authorization and a new session.

## Route the task

- **Lite:** `luna_worker` implements a detailed settled recipe; root inspects the diff and runs short quiet checks. `luna_test_runner` handles builds, noisy checks, and worthwhile long/independent checks. Include steps, files, interfaces, dependencies, acceptance, checks, and stops. High-rigor/integration writes require Hard.
- **Hard:** every nontrivial file-changing route, including root-written work, requires independent `sol_reviewer` on Sol/xhigh without weaker fallback; security-sensitive work also requires `security_reviewer`. Safe Direct edits remain zero-child.

In Hard, `sol_worker` (GPT-6.2 Sol/high) handles coding and UI fixes. Sol covers architecture, diagnosis, review and risky or uncertain deep-fixed work. Terra 6.1 handles research/exploration (low), technical drafts (xhigh) and visuals (high). Luna/max handles fixed implementation, focused tests and established documentation.

Execution-only builds/tests use Luna/medium; build/noise overrides short duration. Return failures to Sol/Astra root or Sol specialists with compact evidence. No autonomous fixes/retries; reuse the runner after fixes.

Luna/Terra may escalate to Sol; never downward. Missing required Sol blocks dispatch. Diagnose input/tool/environment failures before model escalation; pass evidence and failed approaches.

For substantive planning, Sol/Astra root authors decisions; `sol_architect` supplies justified distinct inputs. Independently review spec/design with `skeptic` before drafting its plan, then review the plan before implementation. Resolve material findings; reuse accepted unchanged review. Simple checklists/settled recipes need no fresh critique. Inline cannot bypass this gate.

Read `references/routing-matrix.md` only for routing details. Read `references/dispatch-contract.md` immediately before spawning.

Use `visual-analysis` for screenshots, `content-writing` for technical drafts. Direct applies. Verify child tools/inputs; models grant no tools. Root owns unavailable interactive steps.

Run `resolve_roles.py`: preflight JSON as `--available-agents`, exact active-session IDs as `--available-skills`; preserve incompatibility. Compare registry `model`, `reasoning_effort`, `fork_turns="none"` with live role/schema; require supported isolated context, never incorrect inheritance or numeric forks. Resolver cannot spawn/prove runtime identity. Optional delegation requires `delegation.benefit`/`expected_output`; otherwise root works with required reviews. Supply actual `root_model`; `deep-analysis` requires `escalation_reason`. Required reproduction blocks writes until cause confirmation. Validate packets; announce role, agent type, purpose and reason before spawning.

Pass `--project-root` and `planning` references. Resolver checks current hashes, independence, latest ACCEPT and spec-to-plan order. Planning requires accepted spec evidence. Nontrivial writes default substantive; approved settled recipes exempt only low-rigor, non-security work without independent-analysis requirements.

Native parallel dispatch covers only independent read/test packets; writer packets stay sequential. The separate `orchestrating-parallel-worktree-changes-v2` executor requires an approved, semantically validated overlay, disjoint surfaces, separate worktrees and user authorization. Without equivalent semantic validation, leave V2 unstarted and execute sequentially. Shared-resource tests serialize with separate IDs/reports.

## Reconcile and finish

Use `run_state.py` for multi-agent, high-risk, or resumable work; reconcile reports as `ACCEPT`, `REPAIR`, `INVESTIGATE`, `REPLAN`, or `BLOCK`. Preserve follow-up scope. After two failed fixes against the same cause, the worker returns both attempts and evidence to root for diagnosis. Lite needs authorized Hard escalation or `BLOCK`.

Record implementation/repair transitions before changes, invalidating verification. Completion requires diff inspection, verification and selected final/security reviews after the latest recorded change, resolved findings and accepted reports. Use `superpowers:verification-before-completion`.

Meet original requested acceptance; optional suggestions stay in `concerns` without expanding scope. Stop once proportionate current verification and required reviews pass. Repeat checks/reviews only for new changes, failures, or material uncertainty.

Opt-in `reflect-and-improve`: inherit evidence; accept separately.
