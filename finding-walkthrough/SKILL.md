---
name: finding-walkthrough
description: Use when explaining or reviewing one finding or bug as a concrete source-to-outcome trace, or preparing a manual reproduction with exact inputs, branch checks, state changes and evidence gaps.
---

# Finding Walkthrough

Explain one finding along one selected path. Produce schema-2 `REPORT.json` as the sole content source and deterministic full `REPORT.ru.md` and `REPORT.en.md`, each with a Mermaid sequence diagram and numbered steps sharing stable IDs. Both mandatory version-2 templates drive generation. Split unrelated findings into separate reports.

Default to source analysis and a concrete manual reproduction recipe. Run a reproduction only when requested or otherwise authorized in an appropriate environment. The helper validates/renders data; it never executes report commands or accesses the network. Do not expose real credentials.

1. Read [workflow.md](references/workflow.md). Identify the actor trigger, relevant prerequisites, exact input format and values, identity/rights, callsites and callees, predicates and local values, state changes, downstream handoffs and outcome. Read actual source; include only meaningful intermediate calls.
2. Read [format.md](references/format.md) and start from [example.json](references/example.json). Rebind the illustrative source path to the included example source for a tool demonstration; use reviewed project files and hashes for a real report. Preserve evidence classifications in the trace and every localized claim, including check results. Record revision, environment, exact values and explicit gaps. A historical saved observation is distinct from a new run; describe both honestly. Sending does not prove receipt or success. Write both translations explicitly; numeric parity checks cannot prove equivalent meaning.
3. Write JSON, validate it, and render Markdown using Python 3.11+:

```text
python scripts/walkthrough.py validate REPORT.json
python scripts/walkthrough.py render REPORT.json --output-dir OUTPUT_DIRECTORY
python scripts/walkthrough.py check REPORT.json OUTPUT_DIRECTORY
python scripts/walkthrough.py show REPORT.json --index
python scripts/walkthrough.py show REPORT.json --step STEP_ID
```

Run from this skill directory or use its absolute script path. Every default command validates schema 2, current evidence hashes, literal excerpts and mandatory templates. The output directory must exist. Both paths are checked before writes; identical Markdown is a no-op and replacing different content requires `--replace`. Do not hand-edit generated Markdown. Pair replacement is not a transactional filesystem commit; run `check` after interruption. Subset retrieval validates complete JSON but prints an index or one step with context. To preserve a schema-1 report, use the explicit read-only `legacy-*` commands; `migrate OLD.json --output NEW.json` creates an exclusive incomplete draft, retaining the whole trace and requiring manual bilingual authoring. No translation, evidence promotion or receipt inheritance occurs.

4. Use [roles.md](references/roles.md) for independent author/reviewer handoff. The reviewer retrieves raw source and evidence, checks the selected branch, prerequisites, each transition and outcome scope, then supplies a hash-bound receipt. Repair blocking issues and request review again, up to three repair rounds. If independent review is unavailable, deliver explicitly **unreviewed**; do not invent acceptance.

```text
python scripts/walkthrough.py review-check REPORT.json OUTPUT_DIRECTORY RECEIPT.json
```

Acceptance means the report is ready within its stated evidence limits; it does not mean an exploit was confirmed. The receipt binds exact JSON, both Markdown files, both template files, template version and every evidence fingerprint. Template changes require regeneration and fresh independent review even when output bytes stay identical. The receipt cannot authenticate identities or prove independence.

Load only the relevant platform checklist: [TON](references/ton.md), [EVM](references/evm.md), [Sui](references/sui.md), [Aptos](references/aptos.md), [Solana](references/solana.md), [web](references/web.md), or [Go](references/go.md). Verify project versions and behavior instead of importing platform assumptions.
