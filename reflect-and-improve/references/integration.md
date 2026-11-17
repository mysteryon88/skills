# Shared skill integration

Release2 adds automatic project experience preparation through installed Codex/OpenCode
startup instructions. Read [recall.md](recall.md) for native chat/report discovery and
the bounded read-only helper. The original three controller files and old pins remain
unchanged; a trusted release installation records new state separately, without rewriting
old experiment scores or pretending the feature passed semantic acceptance.

One source definition produces one runtime bundle. All roles use the same installed skill,
not copies in each role prompt. Distribution copies on other machines must be the same
verified release; task pins are immutable content snapshots, not another skill definition.

## Existing runtime

The inspected system uses native Codex root/subagents, registry-backed Hard roles, explicit
dispatch packets, run_state journals and hash-bound artifact review. OpenCode also reads
the user's shared skill root. User-managed global skills belong only in
`C:/Users/ssobolev/.agents/skills`, shared by the Windows Codex/OpenCode installations.
Project-scoped skills stay in their project; do not install into app-managed `.codex/skills`
or OpenCode-specific global directories. Check for an existing name before installation.

The PTNFZ repository has project-local `.agents/skills`, a Rust bounded skill reader and
existing workflow journals/receipts. The current Codex agents can read that repository
over WSL paths while sharing their Windows skill catalog. No Rust provider/model loop,
CLI/MCP tool, global permissions or connectors need changing for this integration.

To distribute, run the repository's packager and install its allowlisted runtime bundle
into the canonical shared root, preserving any existing version until drift is reviewed.
Record the full runtime manifest/hash and backup before replacement. `VERSION` is release
metadata; runtime task versions use the complete content SHA-256, not the one-digit version.
After installation, refresh the skill catalog/new session if needed. Loading a file in an
existing model context cannot retroactively change its earlier context or pin.

Discovery verification uses the installed Codex app-server `skills/list` with absolute
`cwds` and `forceReload: true`, then checks enabled/name/path/error data. OpenCode exposes
`opencode debug skill --pure`. Neither needs a model turn. A custom frontmatter parser is
only structural evidence; keep native loader results. Track PIDs and close any probe server
and its process tree on success, failure and timeout. Do not enable MCP to list skills.

## Root invocation

```text
Use $reflect-and-improve in reflect mode for run task-42.
Expected/actual result and versions: /absolute/task-packet.json.
Evidence: /absolute/run-journal.json and /absolute/report.md.
State: /absolute/project/.reflect-and-improve/example-skill.
Save grounded observations and inactive proposals; active versions stay unchanged.
```

For improve, give the one evidenced proposal/problem, exact editable files, frozen contract,
test criteria and budget. Without a live budget, ask for offline staging/local checks only:

```text
Use $reflect-and-improve in improve mode for proposal OBSERVATION_ID from task-42.
Read /absolute/experiment-contract.json and the original cited evidence.
Stage one small candidate under /absolute/project/tmp/rai-candidate.
Use the existing state /absolute/project/.reflect-and-improve/example-skill.
Run structural checks and prepare a reviewable result. Live runs are disabled.
Do not accept it or alter active memory from this preparation request.
```

## Actual isolated child handoff

For a reflect/improve task tree (not recall-only work), root calls `pin --run-id task-42`. Pass its returned absolute
`skill_path` and `version` in the dispatch packet, rather than making a child discover the
then-current target. For a child call `pin --run-id task-42-child-a --parent-run task-42`.
The child inherits the root's original bundle after any later activation or rollback.
Use a short explicit brief, for example with native `spawn_agent`/`fork_turns: none`:

```text
Load the shared $reflect-and-improve skill at CANONICAL_SKILL_PATH.
Role: reflection reviewer. No spawning or recursive orchestration.
Root run: task-42; actor: child-a; original incident source task: task-42.
Pinned reviewed target: IMMUTABLE_SKILL_PATH, SHA256 VERSION.
Accessible task/evidence: /absolute/task-packet.json, /absolute/run-journal.json.
Expected/actual/versions binding: /absolute/observation-context.json.
State: /absolute/project/.reflect-and-improve/example-skill.
Use reflect only. Cite accessible observations; missing history stays unknown.
Report into the original task run_id with your actor_id. Never relabel your actor as a
new independent source task. Return report path, inactive proposal IDs and limitations.
No adoption, active-memory write, candidate execution, live send or new campaign.
```

A child preparing improve receives the frozen contract, existing experiment ID/baseline,
explicit writable temporary candidate directory and exact target-file allowlist instead.
It may submit a candidate and development artifacts within that brief, not alter evaluator,
criteria, policy, acceptance, secrets or shared active files. Root owns import/selection and
operator acceptance. There is no new permanent role, worker or orchestration tree.

## Task completion seam

No verified native completion event or authorized tree-wide monetary meter was found in
this installation. There is **no installed automatic hook**. At the existing root
reconciliation/finalization step, an explicit project/user opt-in may call reflect after a
substantial task, repeated error or user correction, using the original task ID. Skip full
cycles for trivial edits. Do not trigger from origins reflection/evaluation/improvement,
from a new reflection report, or from a successful evaluation. Reflect never calls improve.
Native event automation can only be added later through a supported adapter that preserves
these checks; a prose instruction alone is not an event hook or budget control.

## TON adapter

When a `ton-fuzz-reflection` adapter is available in the active catalog, it remains explicit-only and preserves its Markdown
report, isolated diagnostics and finding gates. It is a domain adapter for evidence
inventory/native status boundaries; the common skill owns candidate/version procedure.
Discover the common skill by logical name in the active catalog, not a presumed sibling
path. If unavailable, save the existing report and an inactive handoff packet; do not
download/install a replacement or silently start improve. Common reports cite campaign
evidence without changing its native counts or receipts.

Linux/WSL shells have a different home/catalog. This delivery installs the common skill
into the explicitly authorized Windows canonical root; it does not create a Linux global
duplicate. A separate Linux-native session must use an authorized project installation of
the same runtime release or explicitly supplied mounted path. Report actual discovery,
rather than claiming Windows installation changed every Linux application's catalog.

## Scenario laboratory adapter

After explicit authority to review an immutable scenario Run, export via the lab's
ordinary CLI (the selected data root and original task identity must be known):

```text
npm run lab -- reflection-packet --data DATA --project ID --run RUN --task ORIGINAL_TASK
```

Read the returned sanitized evidence, packet and manifest. The data-root path is a
trusted local prefix, not anonymized. Check effective outcomes, missing checks, cleanup,
legacy/truncated journal history and unknown comparison context. No export starts a
model, evaluator, target application, new Goal cycle or this helper. The repository's
docs/reflection.md documents limits and optional --before structural contrasts.

Only when reflection import is separately authorized, use the existing pinned helper:

```text
python PINNED_SKILL/scripts/reflect.py --state ISOLATED_OR_EXISTING_STATE reflect --input PACKET_PATH
```

Keep the returned original-task alias shared across Runs; do not count agents, people,
scenarios or repeated Runs as independent source tasks. Preserve the current baseline
when useful evidence is absent or contexts differ. One failed preparation can be
investigated without pretending its short duration improved productive agent cost.
Do not recurse from reflection/evaluation/improvement origins, auto-run improve, synthesize
a comparison receipt or call accept. A smallest trajectory-supported proposal still
requires its separate editable scope, frozen comparison and operator authority.

Reviewed prose maintenance of this canonical skill is a trusted release operation,
not behavioural experiment acceptance. Review complete manifests/backups and only
authorized prose differences; preserve controllers, metadata, prior snapshots and pins.
Do not forge scores or rewrite an old state's active/pin history to label a release adopted.
