# Plan Parallelization Protocol

## Contents

- Role and preconditions
- Source validity and completed Task evidence
- Inventory and global constraints
- Dependency and contract graph
- File ownership and overlaps
- Task atomicity
- Lanes, waves, and verdict
- Validation and handoff

## 1. Role and preconditions

This skill compiles an approved implementation plan into a new execution overlay. It does not replace the approved specification, source plan, TDD, code review, or final verification.

Start only after:

1. the design/specification is approved;
2. a numbered source plan has been produced and self-reviewed;
3. the user selected delegated execution;
4. no implementation agent has started.

Read repository instructions, status, manifests, test configuration, nearby code, the approved spec, this protocol, and `references/review-and-integration.md` before constructing the graph.

Before selecting delegation, briefly compare useful overlap with briefing, worktree setup, review and integration costs. Small mechanical work or a single useful responsibility normally stays with one executor. Do not add a separate estimation workflow or claim a speedup from lane count alone. Read only the repository evidence needed to establish these boundaries; reuse current accepted plan and review evidence.

Prefer `scripts/compile_overlay.py`: it runs dependency preflight, optional bundle normalization, inventory, constraint-map handling, initialization, and validation in order. A missing parallel executor or an executor outside major version 2 blocks `PARALLEL` handoff. The `companions` section may report `codex-worker-orchestrator`; it is optional and does not affect `ready`. Automatic project discovery checks direct top-level skill folders plus `.codex/skills` and `.agents/skills`, before global roots; it does not trust arbitrary nested project copies. If compatible, use its selected worker role only as task-packet input: this compiler still owns dependency topology and only `orchestrating-parallel-worktree-changes-v2` executes a `PARALLEL` overlay. If absent or incompatible, continue compilation without inventing an orchestrator handoff. No named planning, dispatch, worktree, testing, review, or verification skill bundle is required; use equivalent repository or harness capabilities. No runtime helper searches `PATH` or the project for Git. Pass a trusted absolute `--git-executable` when probing Git, recording canonical repository-relative identity, or verifying commit evidence. Even a successful probe is only a non-mutating environment signal and never proves that the current harness may create a worktree.

The optional `codex-worker-orchestrator` companion supports major versions 2 and 3. Unknown or malformed versions remain incompatible; the required executor stays at major 2.

The source plan remains immutable. SHA-256 is computed from UTF-8 text with LF-normalized line endings, so CRLF/LF checkout changes do not invalidate the same plan. The manifest records its exact canonical repository-relative path and semantic hash, then maps every numbered source Task exactly once to completed evidence, sequential prelude, one ordered lane, sequential epilogue, or sequential fallback.

When the input has an explicit `## Subplans` section, `scripts/normalize_plan_bundle.py` flattens only those listed files. It assigns global numeric Task IDs required by schema 2 plus stable namespaced bindings such as `plans/api.md#Task 3`, rewrites local Task references, preserves exact file/interface metadata, and hash-pins the master and every subplan. Recursive discovery and masters that also define Tasks are rejected. The validator reopens every bound source and rejects a missing source Task, changed semantic hash, or mismatched file set.

## 2. Source validity and completed Task evidence

Repair the source plan before scheduling when it has no numbered Tasks, duplicate Task IDs, invalid repository-relative paths, or references an unknown Task. Raw checkbox fragments are not dispatch units.

Checked text alone is not completion evidence. A completed Task record requires:

- every source checkbox checked;
- one or more full commit SHAs present in the source repository;
- at least one referenced commit touching a declared Task file;
- concrete verification commands without placeholders.

If these facts cannot be verified, the Task remains active. Conversational assertions, summaries, and expected-but-uncommitted output never qualify.

## 3. Inventory and global constraints

Run:

```bash
python <skill-dir>/scripts/plan_inventory.py <source-plan> --format json --output <inventory.json>
```

The inventory is a starting point. Inspect the repository for re-exports, generated code, models, DTOs, events, manifests, lockfiles, schemas, migrations, fixtures, shared databases, ports, caches, devices, accounts, artifact directories, and commands that mutate shared tracked files.

Copy every `## Global Constraints` bullet exactly once into `global_constraints`. Each record names its affected source Tasks, kind, and executable checks. Use `exclusive-resource` plus a stable `resource` name when affected Tasks cannot safely share a wave. Disjoint files do not override a shared mutable resource.

`scripts/generate_constraint_map.py` copies those bullets and common checks into an editable skeleton. Fill only `kind`, `tasks`, and `resource` where exclusive. A valid map does not disable parallelism: the scheduler automatically co-locates only Tasks sharing an `exclusive-resource`; `policy`, `contract`, and `ordering` records remain validated evidence unless explicit Task or interface edges establish order. The overlay reports mapped `ordering` records as `ordering-only` classifications without guessing a direction that the source never states.

## 4. Dependency and contract graph

Each node is one reviewable source Task. Add `A -> B` when B cannot be implemented, meaningfully tested, or integrated before A.

Classify every relationship before scheduling:

1. **Hard implementation dependency:** the consumer cannot be implemented or tested before the producer; schedule it later in the same lane or in a later wave.
2. **Ordering-only dependency:** no implementation payload is consumed, but integration or policy requires a stable order; preserve that order without inventing same-lane ownership.
3. **Frozen producer/consumer contract:** the complete backticked signature matches exactly and a declared contract test, fixture, or mock plus executable test command fixes behavior; producer and consumer may share a wave.
4. **Shared-file ownership conflict:** Tasks may run in different waves but not concurrently unless the existing soft-overlap contract proves disjoint symbols.
5. **Exclusive resource:** affected Tasks may run in different waves but never concurrently.

### Hard implementation edges

Create a hard edge when Tasks:

- explicitly reference another Task as a prerequisite;
- change and consume an unfrozen public contract;
- form stages of one migration, refactor, state transition, or user flow;
- form a schema or migration chain whose later implementation requires the earlier state;
- require one Task to make another Task's tests or build possible.

Task numbering is not an edge by itself. Preserve source order by default; any reordering needs a declared dependency path. A cross-lane Task edge must appear in the consumer lane's transitive `depends_on` chain when it crosses to a later wave, and the producer lane must precede the consumer in `integration_order`.

Every generated `task_dependencies` record is a derived claim and must match an explicit source Task reference or producer/consumer interface relation. It may classify only `hard-implementation` or `frozen-contract`; ordering and conflicts use their dedicated records. Free-text manifest reasons cannot create new hard edges. Repair and reapprove the source plan when repository inspection discovers a missing dependency.

### Contract edges

A producer and consumer in different lanes may occupy the same wave only when the exact signature or schema, version, required and optional fields, errors, serialization, nullability, compatibility rules, and executable contract tests are frozen before dispatch. Inside one lane, the consumer instead waits for its producer's implementation, tests and review gate.

If either side still needs design judgment, retain a hard dependency: later in the same lane or in a later wave across lanes. Worktrees prevent file collisions; they do not prevent incompatible APIs. A bare `Consumes: ... from Task N` reference establishes order, not mandatory lifetime same-lane ownership; safe adjacent-wave compaction may keep that dependency within one lane. Relax only the exact contract cause: if the same producer/consumer pair also names migration state, generated output, implementation payload, or another unfrozen cause, the pair keeps its hard edge.

## 5. File ownership and overlaps

All paths are canonical repository-relative POSIX paths. `./`, reducible `..`, Windows separators, and case aliases on case-insensitive systems must resolve to one ownership key. Absolute paths and traversal outside the repository are invalid.

`PARALLEL` execution is worktree-only. Each lane has one writer at a time. Same-file writers cannot share a wave. They may occupy later waves because ownership conflicts are wave-local, not permanent lane unions. A soft same-wave overlap is allowed only for a non-hard surface and must name:

- every lane touching the file;
- disjoint functions, types, keys, or regions owned by each lane;
- the shared-scaffolding owner;
- serial merge order;
- the integration owner;
- focused interaction checks.

Never apply this exception to manifests, lockfiles, schemas, migrations, generated files, or an evolving public contract.

## 6. Task atomicity

A source Task may be split only through a revised plan in which each replacement Task has an observable outcome, exact write surfaces, explicit interfaces, its own failing test or deterministic check, a commit boundary, and a mapping to the original Task. The compiler identifies the blocking Task, its files, tests, and blocked successors. The coordinator drafts an evidence-backed partition with ownership, interfaces, checks, and mapping to the original Task. A human explicitly approves the revised plan before execution. List order is not ownership evidence.

If those boundaries duplicate setup, implementation, or review context, keep the Task intact.

## 7. Lanes, waves, and verdict

A lane is a non-empty unit of work in one wave. A `PARALLEL` overlay may contain many lanes across many waves, with at most four active lanes in any one wave.

Prefer one persistent lane owner for each independent chain, not one worktree per source Task. After scheduling safe frontiers, compact an adjacent wave only when each new Task extends exactly one existing lane through hard dependencies, no two new Tasks require that same owner, and the combined lanes have no cross-lane file/resource conflicts. Cross-lane hard dependencies still require later waves. A new independent frontier or join stays a separate wave. Prelude and epilogue never participate; schedules with frozen contracts conservatively keep their original waves. Preserve every Task's order, checks, commit and review boundary within the chain.

`scheduled_critical_path` is unit-Task depth: prelude plus the longest lane in each wave plus epilogue. It excludes actual task duration, startup, reviews and integration; it is not a wall-clock speedup estimate. Consolidation reduces worktrees and repeated setup without claiming that arbitrary tasks take equal time.

- **Prelude:** only Tasks whose concrete dependency, shared hard surface, unfrozen contract, or exclusive resource evidence proves they must complete before two safe lanes can open.
- **Wave N:** two or more ready, non-empty lanes may run concurrently.
- **Later waves:** consumers released by earlier barriers; a sole ready join is a one-lane wave and scheduling may fork again afterward.
- **Epilogue:** only Tasks identified by the unchanged exact-title or explicit `**Execution:** Epilogue` detector and their descendants.

Rank the hard DAG by downstream critical-path length and select up to four compatible ready Tasks per wave. Do not maximize lane count at the cost of delaying a more critical branch. Same-wave file/resource conflicts remain serial; `Consumes Task N` dependencies may cross ordinary wave boundaries. Barrier descendants are computed from the complete source ordering graph before any frozen contract edge is relaxed.

Use `PARALLEL` only when at least two non-empty lanes are ready in one wave and the integration path is explicit. Never create an empty lane or unrelated `owned_files` entry to manufacture this condition.

Use `SEQUENTIAL` when all useful work forms a chain, every ready frontier is serialized by unfrozen contracts or conflicts, or safe isolation is unavailable. State the exact reason and continue directly with the repository's sequential implementation workflow without asking the user to approve a non-choice.

Before writing `PARALLEL`, confirm worktree availability from the harness capability signal or repository preflight. The static validator checks the declared isolation value and graph consistency; it cannot prove that the current environment can create a worktree. Never write `"isolation": "worktree"` merely to satisfy validation when the capability is known unavailable.

## 8. Validation and handoff

Compile the usual workflow with:

```bash
python <skill-dir>/scripts/compile_overlay.py <source-or-master-plan> --project <repo> --output <overlay-plan> --isolation <worktree|unavailable|unknown> --check <command> --git-executable <absolute-git> --format json
```

If constraints exist and no map was supplied, the compiler writes a skeleton and exits with `constraint-map-required`; fill it and rerun with `--constraint-map`. The scheduler keeps hard edges in a DAG, treats repeated files and exclusive resources as wave-local conflicts, peels only an evidence-backed prelude, and emits repeated bounded waves with short joins. Exact-title or explicit execution barriers alone create epilogue. It reports critical-path metrics, classified conflicts, and conservative repaired-plan suggestions for oversized singleton blockers without changing the approved source. It refuses to guess constraint judgments or checked-Task completion evidence.

Replace every placeholder and validate:

```bash
python <skill-dir>/scripts/validate_parallel_plan.py <source-plan> <overlay-plan> --git-executable <absolute-git> --format json
```

Validator success proves the overlay is structurally consistent with the source plan, recorded Git evidence, ownership graph, constraints, and scheduling contract. For critical-path overlays it replays every prelude frontier against source-backed hard edges, all file/resource conflicts, and frozen-contract gates; then it recomputes ordering records, conflict records, every relationship count, and all topology metrics. Removing or changing the scheduler label cannot select a weaker validation path. It does not prove that future implementation or verification commands have run.

A valid `PARALLEL` overlay waits for one explicit approval, then selects `orchestrating-parallel-worktree-changes-v2` as its only top-level controller. A valid `SEQUENTIAL` overlay selects the repository's sequential implementation workflow. Never run both controllers over the same Tasks.

If implementation returns `REPLAN_REQUIRED`, read its `replan-required.json`; verify `source_sha256`, `overlay_sha256`, `manifest_sha256`, and the referenced paths; and preserve the review state. Only Tasks carrying a commit plus focused and both review-gate evidence remain completed. Mid-run completion uses `completion_origin: runtime-replan` instead of modifying the immutable source plan. Put every unfinished Task and open finding into the replacement schedule, copy the hash-pinned `replan_handoff` and `review_state`, and rerun the validator. `WORKTREE_UNAVAILABLE` always produces `SEQUENTIAL` and continues directly with the repository's sequential implementation workflow; a materially changed parallel topology requires a new explicit approval.

An existing overlay that names a retired executor is invalid input, not an executable compatibility alias. Do not dispatch it and do not silently accept it. Rewrite `executor` to exactly `orchestrating-parallel-worktree-changes-v2`, rerun the validator, and obtain the normal explicit approval for the resulting valid `PARALLEL` overlay. If worktrees are also unavailable, emit `SEQUENTIAL` instead.

If implementation discovers hidden overlap, a new exclusive resource, an unfrozen contract, or false independence without a complete packet, stop the affected lanes, construct the same replan handoff from the recovery ledger, update and revalidate the overlay, and request approval again when the parallel topology materially changes.
