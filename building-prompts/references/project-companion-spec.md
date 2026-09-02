# Project Companion Specification

A project companion is a repository-local reference skill created by `building-prompts`. It reduces repeated discovery cost while keeping current task reasoning in the parent skill.

## Contents

- Write authorization
- Location, layout, and responsibility boundary
- Evidence and bootstrap
- Freshness and refresh policy
- Monorepos

## Write authorization

Reading and validating an existing companion are read-only. Creating, refreshing, hydrating, reconciling, replacing, or manually updating one changes repository files and requires explicit user authorization. Do not infer permission from a request to write a prompt, repository size, repeated work, or the absence of a prohibition.

Without authorization, use standalone mode or return proposed companion content without writing it. Keep the authorization scoped to companion files unless the user separately authorizes other project changes.

## Location and name

Choose one project-local skill root in this order:

1. a location required by repository or user instructions;
2. an existing `.agents/skills` directory;
3. an existing `.claude/skills` directory;
4. `.agents/skills` as the default.

When creation is authorized, create `<project-slug>-project-context`. Do not install it globally and do not duplicate it across roots. Bootstrap operations search the allowed project-local skill roots and match an owned companion by its manifest-resolved project root, which is also its scope. A detected project-name change updates metadata without silently renaming the skill directory. More than one owned match is an ambiguity error that must be resolved explicitly.

## Required layout

```text
<project-slug>-project-context/
  SKILL.md
  manifest.json
  references/
    project-map.md
    commands-and-checks.md
    architecture-and-flows.md
    constraints-and-risks.md
```

## Responsibility boundary

The parent skill owns:

- user intent and task mode;
- task-specific repository inspection;
- prompt structure and acceptance criteria;
- decomposition, parallelism, and verification contract.

The companion owns only durable project facts:

- project identity and repository/workspace boundaries;
- applicable instruction files;
- languages, frameworks, manifests, applications, packages, and services;
- stable module ownership and recurring cross-layer flows;
- repository-derived commands and CI checks;
- generated/vendor areas and public compatibility surfaces;
- durable security, data, deployment, and operational constraints;
- known verification paths and fixtures.

## What must never be stored

- the current task plan, current bug, or one-off review findings;
- guesses, unverified architecture, or copied prompt boilerplate;
- secrets, tokens, credentials, environment values, customer data, or personal data;
- absolute local user paths when a repository-relative path is sufficient;
- transient branch details unless they define a durable release process.

## Evidence format

Every manually added durable fact must be traceable. Add records as ordinary Markdown lines outside fenced examples so the validator can read them:

```text
Fact: API request validation is owned by the gateway package.
Evidence: `apps/gateway/src/validation/...`, symbol `validateRequest`, and its contract tests.
Confidence: confirmed
Last verified: commit `<sha>` or date `<date>`
```

Use `inferred` only as a temporary discovery label. Hydration accepts only `Confidence: confirmed`, an ISO date or commit identifier, and at least one repository-relative evidence path that exists and is readable. It records the evidence content hash for each fact, so a later content change is stale even when the path still exists. It also rejects secret-like content and absolute user paths. A companion with no positive durable fact may be hydrated only with an evidence-backed fact explaining why no cross-task durable fact applies.

## Bootstrap

The bundled scripts require Python 3.11 or newer and use only the standard library. Unsupported runtimes fail explicitly instead of silently skipping TOML project metadata. If script execution is unavailable, create the required layout manually and apply the same evidence, privacy, and freshness rules.

Run bootstrap only after the user explicitly authorizes companion creation or replacement.

Run from the installed parent skill directory:

```bash
python scripts/bootstrap_project_companion.py /path/to/project
```

Useful options:

```bash
python scripts/bootstrap_project_companion.py /path/to/project --json
python scripts/bootstrap_project_companion.py /path/to/project --skills-dir .agents/skills
python scripts/bootstrap_project_companion.py /path/to/project --project-name "Project Name"
```

Bootstrap detects identity, manifests, instructions, top-level structure, explicit package scripts, selected build files, CI files, and high-signal fingerprints. It deliberately does not infer architecture from folder names.

Creation always produces `context_state: bootstrap`; `--state hydrated` is rejected. Discovery traverses nested project instructions, recognized manifests, and CI workflows without a silent depth or file-count cap. An unreadable discovered input makes the inventory indeterminate and prevents creation or refresh from claiming success. The schema-3 manifest records discovery completeness, generator version, full inventory hash, immutable generator fingerprints, accepted generated-content fingerprints, and per-fact evidence fingerprints.

After bootstrap:

1. inspect the real project boundaries and recurring flows;
2. replace bootstrap-only uncertainty with evidence-backed durable facts;
3. remove facts that are task-specific or speculative;
4. validate and mark the context hydrated:

```bash
python scripts/hydrate_project_companion.py /path/to/project/.agents/skills/<project-slug>-project-context
```

Hydration is a separate semantic transition. It verifies fact structure, evidence content, confidence, last-verification value, privacy signals, current inventory, and generated-content freshness before atomically updating only the accepted-content and evidence baselines. It never overwrites the original generator baseline.

## Freshness validation

Before relying on a companion, run:

```bash
python scripts/validate_project_companion.py /path/to/project/.agents/skills/<project-slug>-project-context
```

The report separates `structure_status`, `inventory_status`, `generated_content_status`, and `durable_facts_status`. Exit codes:

- `0`: valid structure, current recomputed inventory, reconciled generated content, and valid hydrated facts when applicable;
- `2`: invalid structure or metadata;
- `3`: stale or indeterminate because the full inventory changed, a high-signal input was added, removed, changed, or unreadable, accepted generated content was modified, generated content no longer matches inventory, or durable evidence disappeared or changed content.

Validation reruns the same complete inventory builder as bootstrap rather than trusting the recorded high-signal list. It compares the full inventory hash, current high-signal details, accepted generated-file fingerprints, and hydrated evidence fingerprints. Any discovery or read error or recorded truncation prevents a false `valid`. A valid result still does not replace task-specific inspection; current code and user decisions always win.

## Refresh policy

Refresh only after the user explicitly authorizes companion changes. Validation may still run read-only without that authorization.

Refresh when:

- high-signal manifests, workspace config, repository instructions, CI files, or documented commands change;
- referenced paths disappear or ownership moves;
- a task reveals a durable contradiction;
- a major migration changes module boundaries, deployment, or verification.

`--refresh-metadata` atomically updates fingerprints and Git metadata while preserving content. If inventory changed, generated references remain explicitly stale until reconciled; metadata refresh cannot declare them current.

Reconciliation is an explicit reviewed transition. First run it without write acceptance to see stale generated files and the exact operator action:

```bash
python scripts/reconcile_project_companion.py /path/to/project/.agents/skills/<project-slug>-project-context
```

After inspecting and updating the generated references against the refreshed inventory while preserving durable facts, accept the current files:

```bash
python scripts/reconcile_project_companion.py /path/to/project/.agents/skills/<project-slug>-project-context --accept-current-generated
```

The command refuses indeterminate inventory, unreadable generated files, invalid or stale durable evidence, and invalid structure. It updates accepted generated-content and evidence baselines only after post-write validation succeeds; otherwise it restores the previous manifest.

Full regeneration uses `--reinitialize`, only for a companion whose manifest proves ownership by this tool and the same project. A hydrated companion, modified generated files, or untracked companion files are refused unless the operator also supplies `--discard-curated`. Regeneration renders and validates a sibling staging directory, atomically swaps it into place, and restores the original directory if installation fails. Unknown, malformed, symlinked, or user-authored directories are always refused.

Schema-1 and schema-2 companions have a safe migration path through `--refresh-metadata`. Migration upgrades metadata but marks generated content `stale` because an old manifest cannot prove which content was regenerated or curated.

## Monorepos

Use one root companion when shared instructions, tooling, and architecture are meaningful across the repository. Add component sections or supporting files for major applications and services. Create separate companions only when components have genuinely independent roots, instructions, and release lifecycles.
