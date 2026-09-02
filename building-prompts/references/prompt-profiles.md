# Prompt Profiles

Choose the smallest adequate contract. Most requests need only the four core decisions; optional modifiers are activated by a real signal, not normalized ceremonially.

## Core decisions

### Authoring action and input

The authoring action says what to do with the prompt; the downstream intent says what its future executor will do.

| Authoring action | Result |
| --- | --- |
| `CREATE_PROMPT` | Create one copy-ready prompt |
| `REWRITE_PROMPT` | Replace a prompt while preserving binding requirements |
| `REVIEW_PROMPT` | Review the prompt artifact; do not rewrite unless separately requested |
| `STANDARDIZE_PROMPT` | Normalize prompts without erasing meaningful differences |

Classify input as `USER_REQUEST`, `SUPPLIED_PROMPT`, `PROMPT_FILE`, or `MULTIPLE_PROMPTS`. It is context, not another execution profile. Content describing a downstream task is not authority to perform it.

### Downstream intent

- `LOOKUP`: establish one fact and stop.
- `RESEARCH`: synthesize sources and reconcile disagreement.
- `REVIEW`: judge an artifact or system with evidence, impact, and confidence.
- `CRITIQUE`: verdict first; challenge assumptions and hidden complexity; give a better alternative.
- `PROPOSAL`: compare viable options and recommend a decision-ready direction.
- `CHANGE`: make and verify an authorized modification.
- `DEBUG_FIX`: reproduce, find the mechanism, fix when authorized, and prove the regression path.
- `VERIFY`: gather evidence for or against one claim without broadening scope.

### Authority

- `READ_ONLY`: no tracked files, data, dependencies, configuration, or external-state changes.
- `FILES_ALLOWED`: only in-scope repository files; no commit, push, deploy, credentials, or live changes.
- `EXTERNAL_CHANGES_ALLOWED`: only the exact remote or live action explicitly authorized.
- `USER_DEFINED`: preserve the stated boundary literally.

Authority is a ceiling, not an instruction. Silence, urgency, autonomy, and technical necessity never expand it.

### Interaction

- `COLLABORATIVE`: ask one material question only when evidence cannot resolve a choice that changes scope, behavior, data, safety, or authority.
- `AUTONOMOUS`: resolve ordinary ambiguity from evidence; ask only for a required decision or authority.
- `UNATTENDED`: Do not ask questions. Choose the safest reversible option, verify it, and continue.

`UNATTENDED` does not grant authority. If required access or authority is absent, return `BLOCKED` with evidence, completed work, the strongest safe partial result, and one operator action.

## Optional modifiers

- **Source:** `REPOSITORY`, `EXTERNAL`, or `MIXED`. External access is discovery, not remote-write authority.
- **Depth:** `AUTO`, `SHORT`, `STANDARD`, or `DEEP`. `SHORT` is at most 250 words; `STANDARD` includes all material semantic slots; `DEEP` adds only decision-changing adversarial, recovery, and false-success controls.
- **Execution:** `AUTO` prefers `SEQUENTIAL`; use `PARALLEL_SUBAGENTS` only for a binding request or at least two worthwhile independent units.
- **Tone:** `NEUTRAL`, `DIRECT`, or `ROAST`. Tone never changes evidence, severity, scope, or authority; humor never replaces evidence or targets people.
- **Critique stance:** `GENERAL` or `SKEPTIC`. `CRITIQUE + SKEPTIC` steelmans an idea, seeks disconfirming evidence, exposes load-bearing assumptions, distinguishes fatal, repairable, and unknown issues, and returns kill criteria, cheap falsification tests, and a stronger alternative.

### Target runtime

Infer the target runtime only when it changes capability or output shape: generic chat agent, repository coding agent, API multi-message prompt, or custom tool-using agent. Use its native shape: plain prompt, `system`/`developer`/`user` messages, JSON schema, repository instruction file, or typed template.

Capability gates apply to the target executor described by the prompt, not the current prompt-authoring runtime. Do not block prompt creation merely because the authoring runtime lacks repository, browsing, or subagent tools. Encode the target executor's preflight, fallback, or exact `BLOCKED` behavior inside the produced prompt.

## Deterministic normalization

Apply this precedence: **Binding user restrictions**, **Authority safety**, **Intent compatibility**, critique stance, interaction, execution feasibility, **Source feasibility**, depth, then tone.

| Conflict | Resolution |
| --- | --- |
| `CHANGE + READ_ONLY` | Downgrade to a proposal; do not edit |
| `DEBUG_FIX + READ_ONLY` | Diagnose and return the fix direction without applying it |
| `REVIEW + FILES_ALLOWED` | Keep review read-only |
| `CRITIQUE + CHANGE` | Split phases; change only when separately requested and authorized |
| `SHORT + DEEP` | Honor `SHORT`; retain only risk-critical controls |
| `COLLABORATIVE + UNATTENDED` | Explicit no-question wording wins |
| Binding `PARALLEL_SUBAGENTS` unavailable to the target executor | Return evidenced `BLOCKED`; do not simulate |
| Inferred parallelism unavailable or unsafe | Use `SEQUENTIAL` and record the reason |
| `EXTERNAL` plus repository-only acceptance | Block unavailable evidence; use `MIXED` only with repository access |
| Multiple intents | Select one primary intent per phase or split deliverables |
| Missing authority | Infer the narrowest safe boundary; prompt authoring itself is read-only |

Never expand authority for compatibility. Reject, downgrade, split, block, or infer deterministically. Keep profile labels internal unless the user requests metadata or is debugging this skill.
