# Report format, version 2

Python 3.11+ standard library only. JSON is the sole content source for two full reports. All objects are closed: every field below is required, extra fields are errors. Duplicate JSON keys, nonfinite values, missing sections, incomplete localization, known scaffold markers, wrong references and wrong order fail validation. No commands in report data are executed. Plain text is escaped as Markdown; only generated markup and literal code fences are structural.

## Envelope and evidence

The exact envelope is `{schema_version: 2, template_version: "2", trace: TRACE, content: CONTENT}`. `TRACE` is the complete closed [schema-1 trace](legacy-format.md), retaining stable IDs, inputs, classified transitions, prerequisites, entities, evidence, outcome, gaps and author. This is an evidence backbone, not a second main narrative. Legacy prose is not substituted for localization. Current schema-2 validate/render/check/show/review-check verify every evidence hash and every literal source excerpt, even excerpts not selected for display. Missing evidence declared with null must remain missing. Source excerpt comparison preserves inclusive line ranges and blank lines, normalizes CRLF to LF and allows one optional final newline.

A localized pair is exactly `{ru: "...", en: "..."}` with nonempty plain text in both languages. Digit tokens must match in order; accurate translation, negation, units and causal meaning still need independent human or agent review. No language fallback exists. A claim is exactly `{text: PAIR, status: STATUS, evidence_ids: [ID], gap_ids: [ID]}`. Every individual claim, including `checks[].result`, is independently validated:

- `source-supported` requires referenced hashed source evidence. It describes conditional source behavior, not proof of deployment reachability.
- `observed` requires referenced hashed runtime evidence and trace context `reproduction_status: "run"`. Saved historical observations must be identified as historical; they do not imply a new run by the author.
- `hypothetical` and `unknown` require explicit gap references. Step status never promotes nested claims.

`trace.context.reproduction_status: "not-run"` forbids every observed trace/content claim, including check results, even when unused runtime evidence exists. The helper verifies structure and artifacts; it cannot prove prose truth, completeness, claim scope, independence or translation equivalence.

## Exact content shape

Every list below is nonempty except a step's `sources`/`checks`. ID-keyed maps may be empty only when the corresponding trace collection is empty. Shared values and code are strings, keeping exact integers/units/bytes out of floating-point conversions.

| Field | Exact shape |
| --- | --- |
| title | PAIR |
| opening | `{story: CLAIM, severity: {level: LEVEL, reason: PAIR}, conditions: CLAIM, scope: CLAIM}` |
| comparison | `[{stage: PAIR, normal: CLAIM, finding: CLAIM}]` |
| initial | `{setup: [CLAIM], input: {language: STRING, value: STRING}, values: [{name: STRING, value: STRING, unit: STRING, meaning: PAIR}]}` |
| steps | `[{id: TRACE_STEP_ID, title: PAIR, diagram: PAIR, explanation: CLAIM, sources: [INTEGER], checks: [{condition: STRING, values: STRING, result: CLAIM}], state: CLAIM, next: CLAIM}]` |
| impact | `[CLAIM]` |
| reproduction | `{environment: [CLAIM], setup: [CLAIM], history: [CLAIM], expected: [CLAIM], saved: [CLAIM], control: [CLAIM], commands: [STRING]}` |
| remediation | `{cause: [CLAIM], required: [CLAIM], proposal: [CLAIM], validation: [CLAIM], checks: [CLAIM]}` |
| gaps | `{TRACE_GAP_ID: {description: PAIR, needed: PAIR, verification: PAIR, impact: PAIR}}` |
| appendix | `{context: {repository: PAIR, revision: PAIR, environment: PAIR, reproduction_status: PAIR}, prerequisites: {TRACE_PREREQUISITE_ID: PAIR}, entities: {TRACE_ENTITY_ID: PAIR}, evidence: {TRACE_EVIDENCE_ID: PAIR}, outcome: PAIR, review: PAIR}` |

LEVEL is exactly `Critical`, `High`, `Medium`, `Low` or `undetermined`; every value requires a reason. Do not fabricate a ranking when practical impact is unresolved. `sources` contains zero-based indexes into that same trace step's source array, with no duplicates. Content steps exactly match trace IDs/order. All ID-keyed maps match the complete corresponding trace collection. `checks.condition` and `checks.values` are shared exact predicates/expressions and local values, such as `amount > limit` and `amount=1; limit=0`; explanatory prose belongs in the localized result claim. `initial.input.language` and source `language` are safe fence tokens using letters/digits/underscore/plus/dot/hyphen. Empty exact input value is allowed. Sources retain literal code, not synthesized pseudocode.

The filled [example.json](example.json) uses a deliberately illustrative absolute source path. It is not a report of an executed incident. Before running validate/render, rebind **both** `trace.evidence[].path` and `trace.steps[].sources[].path` to the absolute path of [example-source.txt](example-source.txt), then recompute the SHA-256 over its actual bytes. Its snippet must still match the inclusive range. Example author/review prose declares no independent acceptance. For a real finding replace the entire example scenario, claims and references using raw project evidence; do not merely rename actors.

## Templates, outputs and public API

`templates/VERSION` must be `2`. Both actual `REPORT.ru.template.md` and `REPORT.en.template.md` are mandatory. Each has exactly one of these slots, in this order: `opening`, `comparison`, `diagram`, `initial`, `steps`, `impact`, `reproduction`, `remediation`, `unknowns`, `appendix`. Missing/misordered/duplicate/unknown slots or version mismatch fail. Their localized headings determine report structure. Renderer uses the actual files; do not copy their structure into an alternate generator.

```text
python scripts/walkthrough.py validate REPORT.json
python scripts/walkthrough.py render REPORT.json --output-dir OUTPUT_DIRECTORY [--replace]
python scripts/walkthrough.py check REPORT.json OUTPUT_DIRECTORY
python scripts/walkthrough.py show REPORT.json --index
python scripts/walkthrough.py show REPORT.json --step STEP_ID
python scripts/walkthrough.py review-check REPORT.json OUTPUT_DIRECTORY RECEIPT.json
```

The existing directory receives exactly named `REPORT.ru.md` and `REPORT.en.md`. Existing identical bytes are no-ops; different bytes require explicit `--replace`. Both output paths and protected JSON/evidence/source/template aliases are preflighted before either write. Outputs must be distinct regular files without links, junctions, reparse points or hardlink aliases. Receipt aliases supplied to check/review-check are protected too; an existing output containing a recognizable receipt is never replaced. Both complete replacement files stage in the destination directory. Pair updates are not a transactional filesystem commit; an interruption can leave a stale pair, detected by check. Output permissions or concurrent filesystem mutations can still fail at operating-system boundaries.

Main body contains the explanatory narrative and compact basename/line-range source labels linked to absolute paths. Each step presents explanation, literal source, checks, state and next transition in that order. Exact input appears once in the initial section from the shared v2 input; old trace input and stable step IDs stay in the technical appendix/JSON. Individual classifications appear inline; concise human gap descriptions link to full needed/verification/impact details in the unknowns section. Keep each affected claim's practical limit explicit in its own prose. Human localized gap descriptions head the unknowns section. The appendix carries localized context/maps plus stable IDs, trace input, file paths and fingerprints for inspection, without duplicating English explanatory context in Russian. Mermaid has generated participant IDs and readable Unicode labels; only grammar controls are escaped, and labels are not truncated. Arrows do not establish delivery or success. Code fences exceed embedded backtick runs. Source language labels are validated before use.

Public Python seams from `scripts/walkthrough.py`:

```python
validate_report(data)  # schema 2, templates and current evidence; returns data
load_report(path)      # strict JSON read + validate
render_report(data, language)  # language is "ru" or "en"; returns UTF-8/LF text
write_pair(data, report_path, output_dir, replace=False)
check_pair(data, report_path, output_dir, receipt_path=None)
review_check_pair(data, report_path, output_dir, receipt_path)
sha256(path)
```

Pair functions require `data` to equal the current JSON object's content. They raise ValueError/OSError on failure; CLI prints an error and exits nonzero. Review receipt schema and semantic review are in [roles.md](roles.md).

## Honest migration and legacy inspection

```text
python scripts/walkthrough.py legacy-validate OLD.json
python scripts/walkthrough.py legacy-check OLD.json OLD.md
python scripts/walkthrough.py legacy-review-check OLD.json OLD.md OLD-RECEIPT.json
python scripts/walkthrough.py legacy-show OLD.json --index
python scripts/walkthrough.py legacy-show OLD.json --step STEP_ID
python scripts/walkthrough.py migrate OLD.json --output NEW.json
```

Legacy commands are read-only and retain historical schema-1 behavior; only legacy-review-check verifies current evidence. No legacy render command is exposed. Migration writes exclusively to a new path and preserves the entire validated trace byte-for-value, with `content: {}`. The draft intentionally fails schema-2 validation until every required bilingual field is authored. Migration neither translates nor promotes evidence nor inherits old acceptance; originals remain untouched. Generate and independently review a new pair after completion.
