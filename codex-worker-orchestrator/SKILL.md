---
name: codex-worker-orchestrator
description: Use when bounded delegation helps or substantive specifications/plans need independent critique. Handle simple questions, focused lookups, routine edits, and short quiet non-build checks directly.
---

# Codex Worker Orchestrator

<SUBAGENT-STOP>
If already a spawned subagent, execute only the dispatch brief. Do not invoke this skill, orchestrate, or spawn.
</SUBAGENT-STOP>

## First decide whether to delegate

Loading alone never requires spawning. Do not spawn when the user forbids subagents.

- **Direct:** simple questions, focused lookups, mechanical edits, known small fixes, short quiet non-build checks. No preflight, ledger, or install prompts. Material risk, uncertainty, or security impact prevents Direct.
- **Delegate:** require bounded benefit exceeding overhead. Start with one child; add only distinct deliverables or required reviews.
- **Escalate:** Sol handles material uncertainty/risk. Astra requires `extreme` complexity, unresolved prior Sol analysis, a decisive evidence check and recorded escalation reason.

Reclassify on scope/evidence/risk/failure changes. File length and approved plans alone never require children.

## Delegation preflight

1. Read `AGENTS.md`; use `superpowers:using-superpowers` and relevant lifecycle without repeating approvals.
2. Resolve the directory containing this `SKILL.md` and run `<skill-dir>/scripts/preflight.py`. Never resolve the preflight script from the repository CWD.
3. Inspect actual available custom agents, models, profile, slots, permissions, spawn schema and companions. The live parent permission mode is the ceiling.
4. Require `ok: true` and `install_mode` `lite` or `hard` before spawning. Otherwise do not spawn. Continue safe Direct work if sufficient; otherwise report missing/conflicting roles and [INSTALL.md](INSTALL.md). Global installation/configuration needs user authorization and a new session afterward.

## Route the task

- **Lite:** `luna_worker` implements a detailed settled recipe; root inspects the diff and runs short quiet checks. `luna_test_runner` handles builds, noisy checks, and worthwhile long/independent checks. Include steps, files, interfaces, dependencies, acceptance, checks, and stops. High-rigor/integration writes require Hard.
- **Hard:** registry roles are available on demand. Every nontrivial file-changing route, including root-written work, requires independent `sol_reviewer` on Sol/xhigh without weaker fallback; security-sensitive work also requires `security_reviewer`. Simple safe Direct edits remain zero-child.

Terra 6.1/low handles exploration/research; Terra/xhigh ordinary Hard quick/bounded and UI/code/content implementation; Terra/high read-only visual evidence. Luna/max retains fixed/deep implementation, focused tests and established documentation. Sol 6.1 owns high-rigor implementation, architecture, diagnosis and review. Volume alone never requires Sol; high uncertainty/risk does.

Execution-only builds/tests use Luna/medium; build/noise overrides short duration. Return failures to Sol/Astra root or Sol specialists with compact evidence. No autonomous fixes/retries; reuse the runner after fixes.

Luna/Terra workers may escalate to Sol; downward fallback is forbidden. Missing required Sol blocks dispatch. Diagnose input/tool/environment failures before model escalation; pass evidence and failed approaches onward.

For substantive planning, Sol/Astra root authors decisions; `sol_architect` supplies distinct inputs when justified. Independently review the spec/design with `skeptic` before drafting its plan, then review the plan before implementation. Root resolves material findings and reuses accepted unchanged review. Simple checklists/settled recipes need no fresh critique. Inline cannot bypass this gate.

Read `references/routing-matrix.md` only for routing details. Read `references/dispatch-contract.md` immediately before spawning.

Use `visual-analysis` for application screenshots, `content-writing` for technical drafts. Direct applies. Verify child tools/inputs: model capabilities grant no tools. Root owns unavailable interactive steps.

Run `resolve_roles.py`: complete preflight JSON as `--available-agents`, exact active-session IDs as `--available-skills`; preserve companion incompatibility. Compare emitted registry `model`, `reasoning_effort`, `fork_turns="none"` with live role/schema before dispatch. Use supported isolated context; never silently inherit incorrect settings or invent numeric forks. Resolver never spawns or proves runtime identity. Optional delegation requires `delegation.benefit`/`expected_output`; otherwise root works with required reviews. Supply actual `root_model`; `deep-analysis` needs `escalation_reason`. Required reproduction blocks writes until cause confirmation. Validate packets; announce role, agent type, purpose and reason before spawning.

Pass `--project-root` and `planning` review references. Resolver checks current hashes, independence, latest ACCEPT and spec-to-plan order. Planning requires accepted spec evidence. Nontrivial writes default substantive; approved settled recipes exempt only low-rigor, non-security work without independent-analysis requirements. See dispatch-contract fields/examples.

Discover companions project-first, then global. `parallelizing-subagent-plans` alone compiles topology; `orchestrating-parallel-worktree-changes-v2` alone executes parallel writer lanes. Require disjoint surfaces, separate worktrees, validated overlay and user authorization; otherwise serialize. Shared-resource tests serialize with separate IDs/reports.

## Reconcile and finish

Use `run_state.py` for multi-agent, high-risk, or resumable work; reconcile reports as `ACCEPT`, `REPAIR`, `INVESTIGATE`, `REPLAN`, or `BLOCK`. Follow-ups preserve scope. Two failed writer attempts against one cause require systematic debugging; Terra stops and returns its attempts and evidence to root for that reset. Lite needs authorized Hard escalation or `BLOCK`.

Record implementation/repair transitions before changes, invalidating verification. Completion requires diff inspection, verification and selected final/security reviews after the latest recorded change, resolved findings and accepted reports. Use `superpowers:verification-before-completion`.

Opt-in `reflect-and-improve`: inherit evidence; accept separately.
