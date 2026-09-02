# Example: Paired Feature Prompt

User request: add CSV import to an existing admin application without changing the public API. An existing project companion is available for read-only use.

A strong result validates the companion, inspects the current import flow, and emits a `STANDARD + CHANGE + AUTONOMOUS` prompt:

```text
Objective and mode
- Outcome: authorized administrators can preview and import valid CSV rows without changing public API contracts.

Scope and deliverables
- In scope: admin upload UI, existing transport seam, import job, persistence, and regression tests.
- Out of scope: unrelated upload cleanup and public API redesign.
- Deliverables: implementation, focused tests, and supported documentation updates.

Constraints
- Preserve public API contracts and the existing file lifecycle.
- Do not add a CSV dependency until existing parsers and security/runtime costs are evaluated.
- Do not modify the project companion; this request authorizes implementation files only.

Confirmed context and starting points
- Companion hints at `apps/admin/...`, `packages/http/...`, and `services/importer/...`; verify every path and owning symbol before relying on it.
- Inspect the closest upload/import flow and search for authorization, MIME/size validation, row errors, transactions, and job retries.
- Unknowns: exact ownership, supported CSV parser, and partial-failure behavior.

Discovery and evidence gate
Read applicable instructions, confirm the working tree, trace UI-to-persistence behavior, and report the files and symbols proving ownership before edits.

Required work and risk controls
1. Reuse current schemas and upload infrastructure for a thin end-to-end slice.
2. Add deterministic row validation, preview, and commit behavior.
3. Cover authorization, malformed files, size/MIME limits, partial failure, and transaction boundaries.

Acceptance and verification
- Authorized users preview and commit valid rows — verify with focused UI/service tests and the repository's supported integration flow.
- Invalid rows produce actionable deterministic errors — verify malformed and mixed-row cases.
- Existing upload and import contracts remain intact — run affected broader checks derived from project files.

Result format
1. Current flow and evidence.
2. Changed files and decisions.
3. Verification commands and outcomes.
4. Remaining risks and out-of-scope findings.
```

Only task-relevant companion facts appear, and each remains subject to fresh inspection.
