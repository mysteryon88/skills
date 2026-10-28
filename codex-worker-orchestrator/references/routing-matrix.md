# Routing matrix

## 1. Controller boundary

The root owns task classification, Superpowers lifecycle, approvals, plan quality, dispatch, write isolation, reconciliation, integration, diff inspection, and completion. Every child gets one self-contained packet and never delegates.

Apply the relevant lifecycle only: `superpowers:writing-plans`, `superpowers:executing-plans`, `superpowers:test-driven-development`, `superpowers:requesting-code-review`, `superpowers:using-git-worktrees`, and `superpowers:finishing-a-development-branch`. Existing task authorization and completed gates remain valid.

### Dispatch economy

Use the smallest agent set that creates a real evidence, capability, ownership, or verification advantage. Prefer one broader bounded packet over multiple micro-packets when one role can preserve context and the write surface remains coherent. Do not delegate a task merely to keep an agent busy, and do not split sequential steps that share one root cause or interface owner.

### Ownership split with the parallel skills

`codex-worker-orchestrator` selects roles and reconciles their reports. It does not compile dependency topology for an approved numbered plan and does not execute parallel writer lanes. `parallelizing-subagent-plans` owns the topology and verdict; `orchestrating-parallel-worktree-changes-v2` owns validated worktree execution, integration, and its own bounded fix rounds. A child never becomes a recursive subplanner or second controller.

### Report reconciliation

Record implementation/repair transitions before changing files, including root-owned work. They invalidate verification, and selected final/security reviewers must report after the latest recorded change. Re-verification alone cannot refresh an older review. Ledger event order handles equal timestamps; unreported external edits remain the root's responsibility.

After every report the root persists exactly one current decision: `ACCEPT`, `REPAIR`, `INVESTIGATE`, `REPLAN`, or `BLOCK`. A repair report keeps the routed `task_id` and uses a distinct `report_id`, so earlier reports and decisions remain auditable. Suggested follow-ups are advisory and cannot expand the approved goal automatically. Completion requires `ACCEPT` for every recorded report. For native CWO execution, two failed writer or fix attempts against the same claimed root cause force a `superpowers:systematic-debugging` reset. Lite then switches to Hard only with user authorization or records `BLOCK`; Hard applies skeptic or architecture gates when their triggers match.

## 2. Direct execution and install modes

Direct is a zero-agent execution path, not a third installation profile. For a low/trivial-complexity, low-risk, low-uncertainty task, root works and verifies without preflight or a ledger. Focused documentation/code lookups, including an external page or parameter explanation, stay Direct. A security boundary, runtime investigation, explicitly requested independent review, or useful independent packages prevents the automatic small-task shortcut. A small diff can still be high risk. Do not inflate complexity merely because documentation is external, long, or needs a tool.

Choose delegation once per task from a concrete independent deliverable or a substantial bounded implementation. Optional work requires `delegation.benefit` plus a nonblank `expected_output`; absence means root does the optional work even at moderate complexity. Do not reload the full workflow each turn. `delegated_execution_selected=true` alone, an approved plan, or package labels cannot activate fanout or handoff. With a justified delegation decision, an approved numbered plan can activate execution-compiler handoff; architecture and review routes keep their own stages and never hand off. Explicit independent review and required critic/final/security stages need no optional-work justification.

Use `intent=inline` when a larger coherent task is best done by root; required planning evidence still applies. Nontrivial Hard root writes compile a reviewer-only sequential route with `root_work=true` and root write ownership; root implements and verifies before the reviewer wave. Simple safe Direct edits stay zero-child. A missing mandatory reviewer blocks dispatch. A user prohibition always produces zero children; root discloses unmet review prerequisites and cannot claim independent acceptance or begin work depending on an unmet gate.

### Install modes

| Mode | Roles | Selection rule |
|---|---|---|
| Lite | `luna_worker`, `luna_test_runner` | Choose for a clear bounded change that the root can fully specify and review. |
| Hard | All 14 registered roles | Choose when evidence gathering, architecture, runtime diagnosis, skepticism, security review, or independent Sol review may be needed. |

The installer asks for the mode interactively. Non-interactive installation requires `--mode lite` or `--mode hard`.

## 3. Lite plan and execution gate

The root must finish a detailed, unambiguous execution plan for settled behavior before dispatching `luna_worker`. The plan contains ordered steps, exact allowed files and write surfaces, protected interfaces, forbidden changes, dependencies, binary acceptance criteria, exact verification commands with expected results, and stop conditions. Translating accepted decisions into exact instructions does not create a new substantive design. If new nontrivial decisions remain, use accepted independent artifact review or Hard capability before dependent work; the test runner is not a critic.

The sequence is fixed:

1. root writes and checks the plan;
2. `luna_worker` executes only the plan;
3. root inspects the actual diff and scope;
4. root runs short quiet checks; `luna_test_runner` runs builds, noisy checks, and worthwhile long or independently useful planned commands without tracked-file edits;
5. root reconciles evidence and owns completion.

A missing worker, plan element, diff inspection, or required verification evidence blocks completion. A runner report is required only when a runner was dispatched. The runner is not a reviewer. High/extreme-complexity, high-uncertainty, high/critical-risk, and confirmed integration-debugging writes are blocked in Lite. Architecture, security-sensitive work, unresolved runtime failures, and tasks needing independent review require Hard mode.

Declared file-changing diagnostics count toward the same Lite high-rigor prohibition and Hard review requirements. Keeping a short test in root suppresses only the optional runner; it cannot remove final/security review. Ordinary verification without declared changed files retains the root shortcut.

## 4. Hard role matrix

| Observable need | Primary role | Escalation or gate |
|---|---|---|
| Locate symbols, callers, config, and data flow | `repo_explorer` | Terra 6.1/low; root integrates evidence. |
| Verify external library, API, or documentation behavior | `docs_researcher` | Terra 6.1/low; check installed or vendored source first; report exact versions and cross-check implementation with tests or exported types. |
| Reproduce an unexplained failure | `runtime_investigator` | Do not dispatch a fixer until root cause is confirmed. |
| Resolve architecture and boundary trade-offs | Root Sol/Astra; otherwise `sol_architect` | Supply actual `root_model`; set `independent_analysis_required=true` for distinct plan inputs. Independent `skeptic` checks substantive artifacts; Superpowers owns design approval. |
| Review a substantive specification/design, then its implementation plan | `skeptic` | `spec-review` before planning, `plan-review` before implementation; root resolves material findings. Reuse accepted unchanged review, never the author's own review. |
| Attack assumptions and claimed readiness | `skeptic` | Returns gates or replan advice, never user approval or final code acceptance. |
| Implement deep/fixed work against fixed interfaces or author focused tests | `luna_worker` | Luna 6/max; high complexity alone can stay Luna for deep-fixed work, high uncertainty or high/critical risk selects Sol. High-rigor test-authoring selects Sol. Mandatory `sol_reviewer` after the Hard write. |
| Implement high-rigor quick/bounded work, uncertain/risky fixed work, or a confirmed connected multi-file fix | `sol_worker` | Sol 6.1/high; no downward fallback. Mandatory `sol_reviewer` after the Hard write. |
| Ordinary quick/bounded implementation, including scoped UI/code fixes | `terra_worker` | Terra 6.1/xhigh below high rigor; visual inputs are optional. |
| Source-grounded technical draft/revision in assigned files | `terra_worker` | content-writing for the requested software task; high rigor selects sol_worker. Established technical documentation stays docs_writer. |
| Inspect application screenshots, UI states or rendered technical pages | `terra_analyst` | visual-analysis, read-only Terra/high; high rigor selects sol_architect on the same evidence question. |
| Run builds or long/noisy/parallelizable checks | `luna_test_runner` | Root collects before dependent work; failures return to powerful root or Sol diagnosis. |
| Review nontrivial Hard file-changing results from root or children | `sol_reviewer` | Sol/xhigh, mandatory, no weaker fallback. Simple safe Direct edits need no child. |
| Review auth, secrets, CI/CD, parsers, process execution, or trust boundaries | `security_reviewer` | Additional to `sol_reviewer`, not a replacement. |
| Change only established documentation | `docs_writer` | Mandatory `sol_reviewer` after the delegated Hard write; simple edits stay Direct. |
| Resolve an extreme-complexity question still unresolved after Sol analysis | `astra_advisor` | Last-resort Astra/xhigh, read-only, gated by the escalation conditions below. |

### Terra and Luna examples (v3)

These are local routing defaults, not measured quality or subscription-cost guarantees.

| Example packet | Route and observable result |
|---|---|
| Explain one screenshot or find a docs parameter | Direct; loading a model or skill is not a delegation reason. |
| Compare application screenshots before/after a UI change | `visual-analysis` -> `terra_analyst`; cite file/page/region and unreadable areas. |
| Fix a scoped responsive-layout defect | quick/bounded with `visual_or_browser=true` -> Terra, unless high rigor requires Sol. Check rendered result and relevant regression. |
| Draft technical documentation or a project report from supplied facts | `content-writing` -> Terra; verify facts, qualifications, audience and saved artifact. Simple rewrites stay Direct. |
| Update known API names in existing docs | `documentation` -> Luna `docs_writer` when delegation is useful. |
| Triage a coherent log batch or extract facts into a schema | Terra/low evidence role; return IDs, locations, unknown values and processed counts. No child per record. |
| Implement a fixed mapper/adapter or fixtures as ordinary bounded work | Terra worker/xhigh; explicit deep-fixed implementation and focused test authoring keep Luna/max. High-rigor test-authoring selects Sol. |
| Run builds or noisy regression suites | Luna runner/medium; return errors/full-log path, no fixes or retries. |

Ordinary Hard quick/bounded work defaults to Terra/xhigh. High rigor takes priority over modality and selects Sol. Deep-fixed work stays Luna for high complexity alone, but not high uncertainty or high/critical risk. Lite keeps ordinary bounded Luna routing; new specialist intents require Hard, with safe root work available when appropriate. After two unsuccessful Terra implementation/fix attempts against one cause, return the attempts and evidence to root for the existing diagnostic reset.

Terra routes serve the user's software tasks: code, UI, technical text and relevant screenshots. Do not expand them into CAD/AutoCAD, engineering drawings, unrelated office/design automation or generic creative writing based on model capabilities.

Require actual accessible screenshots and child image tools, never infer details from filenames. `visual-analysis` itself does not require browser access. UI verification requires actual tools and authorized target actions before dispatch; model/skill names do not establish access. Inspect the rendered result to verify UI changes.

Official sources checked 2026-10-28: [Terra model](https://developers.openai.com/api/docs/models/gpt-6.1-terra), [model selection](https://developers.openai.com/api/docs/guides/model-selection). Terra supports text/image input, visual interpretation, scoped fixes, writing and computer use where tools are available. This skill chooses low for exploration/research, xhigh for scoped execution and high for visual evidence. API tool calling requires Responses; this skill uses native Codex dispatch and configures no API endpoints. API support does not establish child tool access or account quotas. Luna/max and Sol review efforts remain local policy. Do not infer pricing, CLI version floors or Ultra delegation semantics from third-party summaries.

## 5. Skeptic triggers

Invoke `skeptic` when at least one condition is present:

- a substantive specification/design or implementation plan is authored or materially revised, including moderate-complexity planning by a Sol/Astra root;
- the plan depends on an unverified assumption;
- API, schema, migration, persistence, cache, concurrency, authorization, or background execution changes;
- two evidence sources or agents disagree;
- in Hard, two implementation attempts failed;
- tests are green but the proof is weak or overly mocked;
- rollback, compatibility, or failure behavior is unclear;
- a high-risk change is about to enter implementation or final review.

Do not invoke it for formatting, renaming, a mechanical local edit, a focused documentation lookup, an ordinary test command, a short checklist or settled execution recipe, or simply because the role exists. Explicit independent-review requests still use the requested review route.

Review the specification first, resolve material findings, then draft and review the plan against the corrected spec before implementation. Use an existing brief or binding requirements as the materialized artifact; no new permanent spec document is required. Resolver validates `planning` references against current file bytes and the existing run ledger, including independent identities, the latest applicable report and root ACCEPT, and the plan's current specification digest/order. An older accepted report cannot override a later unresolved review in that run. Reuse equivalent unchanged evidence from another workflow by recording it through the same report contract; resume the same critic across stages where useful. An accepted plan critique replaces a redundant pre-write skeptic on that artifact. Re-review load-bearing changes, not every turn. At most three review/correction rounds per artifact; unresolved material decisions stop dependent work. See `dispatch-contract.md` for fields, phase semantics, and Lite/missing-reviewer handling.

Expected output: assumptions, contradictions, failure scenarios, missing evidence, alternatives, required gates, and `PROCEED`, `PROCEED_WITH_GATES`, `REPLAN`, or `BLOCK`.

## 6. Test routing

All profiles use the same build/test routing. Root runs short quiet blocking checks and quiet checks of unknown duration without a demonstrated benefit from delegation. Builds and noisy checks go to Luna/medium even below the configured 120-second threshold; long duration or useful independent work can also justify a runner. Use `intent=test-execution` for both, with optional `test_context.is_build=true` for builds (omission means false). Record the concrete delegation benefit and output; user prohibitions and capability gates still apply. Lite requires the approved plan's exact commands.

| Test situation | Route |
|---|---|
| Lite post-write verification | Root or `luna_test_runner` according to the same economics; exact planned commands. |
| One quiet non-build command below threshold and blocks the next step | Run in root. |
| Quiet non-build command of unknown but likely short duration | Run in root once, then reassess from evidence. |
| Build, noisy check, long check, or root has useful independent work | `luna_test_runner`; build/noise takes precedence over short/blocking. |
| Multiple independent suites | Up to configured `max_parallel_runners`, one packet per suite. |
| Shared database, port, fixture, cache, service, or mutable environment | Sequential, even with multiple runners. |
| Serialized declared test packages | Preserve each package/task ID and require every report; reuse the runner across one-instance waves. |
| Command fails | Runner stops dependent commands and returns evidence to Sol/Astra root or a Sol diagnostic specialist; no autonomous fixes or retries. |

The runner receives cwd, exact commands, environment, timeout/progress expectations, log paths, allowed untracked outputs, shared-resource constraints, and a check that tracked files remain unchanged from the dispatch baseline. It never authors tests, diagnoses failures, fixes code, or reviews the diff. Silence alone is not a timeout. Full logs stay in files; return command, exit status, duration, relevant error excerpt, and log path. After powerful-model diagnosis and an authorized fix, resume the same runner for the affected commands. Send a bounded brief rather than the whole conversation. This limits context overhead; it does not guarantee fewer tokens or lower cost. A failing command never justifies automatic Astra escalation or bypassing Lite's capability gates.

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

In Hard `superpowers:subagent-driven-development`, the implementer is `luna_worker`, `terra_worker`, `sol_worker`, or `docs_writer` according to the packet. Mandatory review applies to every task-scoped write and the final integrated state through `sol_reviewer` on Sol/xhigh. The same reviewer role is used for ordinary and final review so the quality floor cannot silently drop.

Lite uses the root-authored plan, one `luna_worker` implementation stage, root-owned diff inspection, and root-run checks or a `luna_test_runner` according to test economics. A fix round resumes `luna_worker` with the exact finding and reruns the affected planned checks; it does not automatically create a runner.

## 9. Fallback and escalation

Fallbacks are explicit registry edges only. A fallback must preserve the requested mutation and safety class.

- `luna_worker` and `terra_worker` may fall back to `sol_worker` in Hard for the same supported intent and mutation.
- `terra_analyst` may fall back to read-only `sol_architect` for the same visual question, with actual image tools.
- `sol_worker` has no downward fallback. A missing required Sol model cannot be substituted by Terra or Luna.
- `runtime_investigator` may fall back to read-only exploration, which stops at evidence.
- `sol_architect`, `skeptic`, `luna_test_runner`, `sol_reviewer`, and `security_reviewer` have no weaker fallback.

A Lite installation includes both roles; only a selected role is required by its compiled route. Missing `sol_reviewer` blocks nontrivial Hard write routes, including root-written work. Missing `sol_architect` blocks a route that requires it; a Sol/Astra root need not duplicate its own analysis. Missing `astra_advisor` blocks an Astra escalation without silent fallback.

## Astra escalation

Normal work uses GPT-6 Luna, GPT-6.1 Terra and GPT-6.1 Sol. Astra is reserved for the hardest questions after Sol analysis and a decisive evidence check have not resolved them. Use `intent=deep-analysis`, read mutation, `complexity=extreme`, and one recorded `escalation_reason`:

- `conflicting-evidence`: a material conflict remains after root compared raw evidence and sought a decisive check;
- `failed-specialist-analysis`: a completed specialist investigation did not resolve the question; include what failed and the new hypothesis to test;
- `extreme-complexity`: the task is classified extreme and a bounded cross-system question benefits from an independent deep analysis.

An evidence conflict or failed specialist alone does not permit Astra: the resolver blocks every non-extreme request. Ordinary disagreement first goes to Sol root or `skeptic`; a routine failing test goes to diagnosis. Do not classify work as extreme simply because it is large. `astra_advisor` is one advisory pass, including when root itself is Astra. Supply previous Sol analysis, the decisive evidence check, raw evidence, competing hypotheses, and one acceptance question without prescribing the answer. It neither replaces `sol_reviewer`/`security_reviewer` nor authorizes a writer. A repeat needs new evidence or a new hypothesis; no automatic advisor loop.

These are policy choices, not benchmark-derived cost or quality guarantees. Verify actual model/effort availability before dispatch; `cost_rank` is a routing preference, not token pricing. See [Astra guidance](https://developers.openai.com/api/docs/guides/latest-model).

## 10. End-to-end workflows

```text
Lite:
root detailed plan -> luna_worker -> root diff inspection -> root checks OR luna_test_runner -> root reconciliation

Hard:
classify with Superpowers
  -> gather repository/docs/runtime evidence as needed
  -> root Sol/Astra or sol_architect for substantive specification/design
  -> independent skeptic critique and root corrections
  -> implementation plan against the corrected specification
  -> independent skeptic critique and root corrections (accepted unchanged review counts)
  -> bounded worker packet
  -> root or luna_test_runner according to test economics
  -> mandatory sol_reviewer xhigh
  -> security_reviewer when security-sensitive
  -> root reconciliation: ACCEPT | REPAIR | INVESTIGATE | REPLAN | BLOCK
  -> fix round and repeated review if required
  -> fresh integrated verification by root
```
