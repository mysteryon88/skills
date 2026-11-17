# Installation

The package installs the skill and a selected custom-agent profile. It preserves unrelated Codex model, MCP, approval, and sandbox settings. The live parent/session permission mode remains the ceiling.

## Registry consistency and source drift

Preflight checks roles against the installed registry, not against the latest source
release. A locally customized registry/template can therefore pass preflight while
contradicting newer SKILL instructions. Before updating, compare SKILL.md,
config/roles.toml and role templates together with the intended source release.
Preserve explicit user customizations and report conflicts; do not silently replace
models or global settings. A successful preflight alone is not evidence of release parity.

## How to use the skill

Install the skill before invoking it. An explicit invocation looks like `$codex-worker-orchestrator assess the task and choose the smallest useful delegation`. For everyday use, describe the task. With `allow_implicit_invocation: true`, Codex can select the skill based on its description. Selection and subagent dispatch each depend on the task. Simple tasks take the Direct path before preflight or role checks.

Codex discovers the installed skill without a global `~/.codex/AGENTS.md` entry. To authorize delegation for suitable tasks and establish consistent criteria, add the following block to that file once. This is a manual step.

Keep invocation criteria in global `AGENTS.md`, routing rules in the skill, and role models and instructions in `config/roles.toml` and the installed `~/.codex/agents/*.toml` files. Codex registers custom agents through the role files. Use `$codex-worker-orchestrator` for a one-off invocation, or apply the block below for routine work.

```markdown
## Selective delegation

Handle simple questions, focused documentation/code lookups, local mechanical edits, known small fixes, and short quiet non-build checks directly. Reading documentation, loading a skill, or writing a short checklist is not a reason to spawn.
For substantial work, use the installed codex-worker-orchestrator skill when a bounded subtask has a concrete benefit and expected result: independent evidence, specialist analysis, bounded implementation, or useful parallel work. Subagent delegation is authorized under those conditions, subject to the task's permissions and the user's current instructions. Complexity or a documentation lookup alone does not justify a child.
Before dependent work on substantive design, have an independent reviewer/critic check the specification first, then the implementation plan against the corrected specification. Resolve material findings and record accepted artifact reviews through the skill's hash-bound ledger contract; stale or superseded acceptance does not count. Reuse accepted review of unchanged content and resume the same critic where useful; simple checklists and approved execution recipes for settled behavior need no fresh critique.
In Hard, nontrivial file changes require independent Sol review even when root writes them. Inline execution does not waive required planning, final, or security review; simple safe Direct edits stay zero-child. Never automatically weaken Sol-required implementation to Terra or Luna; use the registry's permitted upward escalation.
Dispatch useful ready independent packets together within live slots and task budgets; add roles only for distinct deliverables or required review. Classify once per task and reassess only when scope, risk, evidence, or failures change. Do not invoke the orchestrator on every turn.
Follow the installed role registry for default models and effort. Reserve the Astra advisor for the skill's extreme-complexity gate after Sol analysis remains inconclusive.
When the live spawn tool exposes fork_turns, use "none" for registry-selected roles so the role's model and effort can apply; verify the live role configuration against the route before dispatch. Never silently substitute inherited parent settings for a required role.
If the skill or required roles are unavailable, continue safe independent root work and report any unmet review prerequisite; never claim self-review as independent review. Do not install or change global settings automatically.
When the user asks for no subagents, use none and disclose the independent-review limitation. Root owns integration and proportionate verification.
```

A typo or focused documentation question takes the Direct path. Designing new behavior requires a specification and a plan, each independently reviewed before the next stage starts. In Hard, ordinary quick or bounded implementation uses Sol 6.2/high, including scoped UI fixes. Explicit deep-fixed implementation and focused test authoring use Luna/max within the configured risk and uncertainty limits. An accepted review of an unchanged document still counts when switching workflows. You can resume the same critic for the next stage.

Astra and Sol handle architecture when either is the root model. For a specific question rated `complexity=extreme`, you can dispatch `astra_advisor` on `gpt-6.2-astra` at `xhigh` after Sol analysis and a decisive evidence check leave the question unresolved. Record the reason for escalation.

Hard includes 14 roles. Terra 6.1/low handles exploration and documentation research, Terra/xhigh writes technical material, and Terra/high analyzes visuals. Sol 6.2 handles implementation, diagnosis, architecture, critique, and review. Luna/max handles agreed deep-fixed implementation, focused test authoring, and edits to existing documentation. The `luna_test_runner` role uses Luna/medium to execute exact commands. After two failed attempts to fix the same cause, the worker reports both attempts and their evidence to root for diagnosis.

Check local overrides before updating. The installer and preflight check models and reasoning effort against the registry. Start a fresh session after installation and verify model and tool availability. The `--keep-existing-agents` option rejects incompatible templates. Use `--replace-existing-agents` to replace unmanaged canonical role files and save a backup.

The resolver emits `model`, `reasoning_effort`, and `fork_turns="none"` for the selected role, including fallbacks. Before dispatch, root checks those settings against the actual custom role and live tool schema. First-party defaults and session rules can differ. The current schema accepts `none` and `all`. Using `all` or omitting the field inherits the parent's model and effort. Use `none` when available. For a different schema, use a supported mechanism that preserves the required settings, or stop dispatch. Use only values supported by the schema and verify runtime identity separately from metadata or preflight. TOML settings can apply as defined by the live tool. The parent's effective permission ceiling limits each role's read-only instructions and sandbox.

For manual invocation, set `allow_implicit_invocation: false` in the installed `agents/openai.yaml` and omit the automatic routing block from `AGENTS.md`. You can still use `$codex-worker-orchestrator` explicitly. Reinstallation restores the source package settings.

See the official documentation for details. [Skill selection and invocation policy](https://learn.chatgpt.com/docs/build-skills) · [Custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents) · [Current models](https://learn.chatgpt.com/docs/models)

## Opt-in root and native memory settings

These are user-selected examples, not installer defaults. The installer preserves root model and memory settings. Merge only the desired keys into existing `~/.codex/config.toml` tables; preserve other settings, including memory quotas and platform defaults, and avoid duplicate TOML tables.

```toml
model = "gpt-6.2-sol"
model_reasoning_effort = "high"

[features]
memories = true

[memories]
generate_memories = true
use_memories = true
extract_model = "gpt-6-luna"
consolidation_model = "gpt-6.1-terra"
```

Native [Codex memories](https://learn.chatgpt.com/docs/customization/memories) are background-generated context, not binding rules. Local clients using the same Codex home share these local memories. Generation needs eligible idle chats and may take time; enabling the settings does not promise immediate memories or measured quality/cost gains. Do not edit generated memories to configure the feature. This is separate from the opt-in `reflect-and-improve` skill and does not change its settings or acceptance gates. Start a new session to load changed root/role configuration; existing chats do not thereby switch models.

## Choose a mode

- `lite`: installs `luna_worker` and `luna_test_runner`. The root creates a detailed execution plan, Luna/max implements it, root runs short quiet checks and Luna/medium runs builds, noisy checks, and worthwhile long or independent planned checks, and the root reviews the actual diff. Default thread limit is 2 when no user limit exists.
- `hard`: installs all 14 roles for evidence gathering, runtime diagnosis, architecture, skepticism, connected implementation, background testing, security, documentation, and mandatory Sol/xhigh review. Default thread limit is 4 when no user limit exists.

Interactive installation asks for the mode. Scripts and CI must pass `--mode lite` or `--mode hard` explicitly.

## Global installation

From a trusted package source, validate first:

```bash
python3 scripts/validate_skill.py
python3 scripts/install.py --mode hard
```

Windows PowerShell:

```powershell
py .\scripts\validate_skill.py
py .\scripts\install.py --mode hard
```

Lite example:

```bash
python3 scripts/install.py --mode lite
```

The default skill target is `~/.agents/skills/codex-worker-orchestrator`. The custom-agent target is `~/.codex/agents` or `$CODEX_HOME/agents`. `config.toml` is updated without changing unrelated settings.

## Lite workflow

The root must prepare a detailed, unambiguous execution recipe for settled behavior before spawning `luna_worker`. It includes ordered steps, exact allowed files, protected interfaces, acceptance criteria, exact verification commands, dependencies, and stop conditions. Translating accepted decisions into exact steps does not require a new design critique. A task introducing substantive design choices needs accepted independent review of unchanged artifacts or Hard capability before dependent work; root inspection and the test runner cannot substitute. After implementation, the root inspects the diff and runs short quiet non-build checks itself. Dispatch `luna_test_runner` for builds, noisy checks, and worthwhile long or independent checks using the exact planned commands. Build/noise takes precedence over short/blocking; set optional `test_context.is_build=true` on a `test-execution` request. Failures return as compact evidence and a full-log path to Sol/Astra root or a Sol diagnostic specialist under existing gates. The runner never fixes or retries autonomously; resume it after an authorized fix. The runner does not review code or change tracked files. Lite blocks high/extreme-complexity, high-uncertainty, high/critical-risk, and confirmed integration-debugging writes because those require Hard's independent review stages. Lite is also inappropriate when the task needs architecture, security analysis, runtime diagnosis, or independent Sol review.

## Installed role files

| Role | Path in Hard | Lite |
|---|---|---|
| `repo_explorer` | `~/.codex/agents/repo-explorer.toml` | no |
| `docs_researcher` | `~/.codex/agents/docs-researcher.toml` | no |
| `runtime_investigator` | `~/.codex/agents/runtime-investigator.toml` | no |
| `sol_architect` | `~/.codex/agents/sol-architect.toml` | no |
| `skeptic` | `~/.codex/agents/skeptic.toml` | no |
| `luna_worker` | `~/.codex/agents/luna-worker.toml` | yes |
| `terra_worker` | `~/.codex/agents/terra-worker.toml` | no |
| `sol_worker` | `~/.codex/agents/sol-worker.toml` | no |
| `terra_analyst` | `~/.codex/agents/terra-analyst.toml` | no |
| `luna_test_runner` | `~/.codex/agents/luna-test-runner.toml` | yes |
| `sol_reviewer` | `~/.codex/agents/sol-reviewer.toml` | no |
| `security_reviewer` | `~/.codex/agents/security-reviewer.toml` | no |
| `docs_writer` | `~/.codex/agents/docs-writer.toml` | no |
| `astra_advisor` | `~/.codex/agents/astra-advisor.toml` | no |

Switching profiles removes only canonical files marked `managed-by: codex-worker-orchestrator` that are not part of the selected profile. Retired managed role files are also removed. If a retired role identity is declared under an alternate, symlinked, or unmanaged file, installation blocks with an explicit move/remove instruction instead of leaving the stale identity active. Unmanaged files, alternate filenames, and an individual role symlink are never deleted automatically.

## Important options

```text
--mode {lite,hard}
--target PATH
--codex-home PATH
--agents-target PATH
--config PATH
--max-threads N
--keep-existing-agents
--replace-existing-agents
--skip-agents
--no-config-change
--no-validate
```

`--keep-existing-agents` accepts a compatible existing role by its TOML `name`, even under an alternate filename. `--replace-existing-agents` replaces only an unmanaged role at the canonical filename after backup. The installer refuses ambiguous duplicate names.

The config file and custom-agent directory symlinks are preserved when they point to valid files/directories. Protected-path containment uses physical paths, including symlink/junction ancestors, so an alias cannot hide agent or config data inside the replaceable skill target. A symlinked skill target is rejected. An individual role symlink requires `--keep-existing-agents` and is not replaced.

An existing skill target is replaceable only when its `SKILL.md` frontmatter name is `codex-worker-orchestrator`. This prevents deletion of an unrelated directory.

## Transaction and verification

Before changing an existing installation, the installer creates one timestamped backup containing the old skill, known role files, config, mode-relevant managed roles, and a manifest. Installation is staged, validated, and rolled back on failure.

After installation run the printed doctor command. Preflight reports `install_mode`, role validity, config state, companion compatibility, and runtime unknowns. Model or reasoning-effort drift from a registered role is an error, including for user-managed roles. Model availability still must be confirmed in the live Codex model picker. Local skill discovery does not scan plugin caches or infer plugin namespaces; use the active session's exact skill IDs for resolver capability input as described in `references/dispatch-contract.md`.
