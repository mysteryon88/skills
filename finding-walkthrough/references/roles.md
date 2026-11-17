# Author and independent reviewer

Use distinct independently dispatched identities. JSON carries content; a separate receipt records review of exact bytes. Handoff file paths and stable IDs with `show --index`/`show --step ID`, plus both full reports. A subset is navigation, not a substitute for reading the whole report and raw artifacts.

## Author

Read actual caller/handler sources and saved logs. Establish actor authority, exact inputs, preconditions, each predicate and local value, causal order, state and failure boundaries. Classify every claim independently, including each check result; preserve the difference between conditional source behavior, historical runtime observation, proposed setup and unresolved effects. Author every Russian/English prose pair and all gap explanations. Separate historical execution from a new run, and proposed remediation from verified fixes. Follow [workflow.md](workflow.md) and the exact [format.md](format.md). Validate, render the mandatory template pair and check it. Return paths, fingerprints and known limitations. Never accept your own report or synthesize another reviewer's verdict.

## Read-only reviewer

Retrieve raw sources and evidence independently. Check every path/hash/range/snippet, actor binding, setup, exact input, check condition and value, branch, callsite/callee, state change, order, async boundary, failure and outcome scope. Read both complete reports. Verify language equivalence including numbers, units, negation and qualification. Check that observed check results have runtime support and a run context, that historical execution does not become a fresh run, and source expectations do not become measurements. Inspect the diagram and all numbered steps against the same JSON; run check. Review templates and renderer for current-byte consistency. Honest gaps can be acceptable without confirming an exploit.

Return explicit blocking findings by stable step ID with raw evidence, or an explicit accepted verdict and exact fingerprints after all blockers are resolved. No independent review means unreviewed. The coordinator may serialize a witnessed verdict/fingerprints; silence does not grant acceptance. Repair at most three rounds, regenerating both outputs and obtaining fresh review after the last change; otherwise deliver unresolved findings as unaccepted.

## Schema-2 receipt

Exact fields (no extras):

```text
schema_version: 2
author: exact trace.author
reviewer: distinct independently dispatched reviewer identity
verdict: accepted
json_sha256: SHA256 of exact REPORT.json bytes
markdown_sha256: {ru: SHA256 of REPORT.ru.md, en: SHA256 of REPORT.en.md}
template_version: "2"
template_sha256: {ru: SHA256 of actual RU template, en: SHA256 of actual EN template}
evidence_sha256: {every evidence ID: its reviewed hash, or null only for missing evidence}
findings: []
```

Use real lowercase 64-character SHA-256 fingerprints, not scaffold values. The helper requires matching author, distinct reviewer, accepted verdict, no unresolved findings, fresh JSON/output/template bytes, full evidence map, current files and matching excerpts. Legacy receipts fail schema-2 review-check. Template drift requires new review even if rendered output bytes happen to be unchanged. A changed evidence hash requires reinspection, not merely rehashing to silence the guard.

A receipt cannot authenticate identities, prove independent dispatch or prove prose truth. The human or coordinator must witness independence. Accepted report readiness means consistency within the stated evidence limits; it does not mean the scenario was reproduced or an exploit confirmed.
