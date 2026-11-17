# Legacy trace format, version 1 (read-only compatibility)

This reference documents the preserved TRACE object and historical behavior only. Use the explicit `legacy-validate`, `legacy-check`, `legacy-review-check` and `legacy-show` commands described in [format.md](format.md); legacy rendering is not exposed. The current [example.json](example.json) is schema 2. Do not use historical command examples below as current CLI instructions.

JSON is the sole report content source. Use Python 3.11+ `scripts/walkthrough.py` to validate, render, check freshness, retrieve subsets and check a separate review receipt. The helper is offline and never executes commands in data. All objects are closed: every listed field is required and extra fields are errors. Duplicate keys, nonfinite numbers, invalid types, unknown references and invalid step order are errors. Arrays preserve order. IDs start with an ASCII letter followed by ASCII letters, digits, underscores or hyphens; IDs are unique within each referenced collection. Use strings for exact payloads, numbers, addresses and byte values.

Top-level fields:

| Field | Shape |
| --- | --- |
| schema_version | Integer `1` |
| finding | `id`, `title`, `summary` strings |
| context | `repository`, `revision`, `environment` strings; `reproduction_status`: `not-run` or `run` |
| prerequisites | Array of `id`, `description`, `status`, `evidence_ids`, `gap_ids` |
| entities | Array of `id`, `name`, `kind` strings |
| evidence | Array of `id`, `kind` (`source` or `runtime`), `path`, `sha256`, `description` |
| steps | Nonempty ordered array described below |
| outcome | `summary`, `status`, `evidence_ids`, `gap_ids`, `verification` |
| gaps | Array of `id`, `description`, `needed`, `verification`, `impact` strings |
| author | Nonempty identity string |

All text is nonempty except `input.value`, which can represent empty input. No surrogate or unsupported control characters. Unknown revision/environment must be explicitly described. Evidence paths are absolute local POSIX or drive paths, without control characters, URL/script schemes, UNC/device syntax or Windows alternate data streams. On Windows this also rejects colons in leading-slash rooted paths, whose native interpretation otherwise permits alternate streams. Hashes are lowercase 64-character SHA-256 values of raw reviewed bytes. Null is allowed only for explicitly missing evidence; description must explain the absence. Null evidence cannot support a positive claim. Source excerpts bind to matching source evidence ID and identical path; each excerpt carries a positive line range, symbol, language and literal code. Render/validate/show do not open evidence contents. `review-check` reads the explicitly referenced evidence and verifies current hashes and excerpt content against UTF-8 source lines.

Prerequisites, steps and outcome share four statuses. `source-supported` requires referenced hashed source evidence; steps additionally require a matching excerpt. `observed` requires hashed runtime evidence, e.g. a saved log. `hypothetical` and `unknown` require at least one gap. Proposed scenario setup belongs in hypothetical prerequisites with instructions to establish it. `run` requires runtime evidence and an observed claim; `not-run` forbids observed claims. Source support is conditional behavior, not proof that a concrete deployment reached it. Cross-step state consistency, actual causal links, claim scope and completeness need independent semantic review.

Every step has `id`, `title`, `from`, `to`, `kind`, `status`, `input`, `operation`, `checks`, `state_before`, `state_after`, `output`, `next`, `sources`, `evidence_ids`, `gap_ids`. `from`/`to` reference entity IDs. `kind` is `call`, `message`, `return` or `internal`. `input` has `format` and `value` strings. `checks` is an array of objects with `condition`, `values`, `result` strings: record the concrete predicate, local values and why the branch is taken. State/output/operation are strings. `next` must name the next array element; the final element has null. The first step describes the actor trigger. Empty checks/sources/evidence/gaps arrays are permitted when justified by operation/status. Each source object has `path`, `symbol`, `start_line`, `end_line`, `language`, `code`, `evidence_id`; line numbers are positive integers with end >= start. Missing external handlers use unknown steps and gaps, never invented sources.

The full [example.json](example.json) shows a hypothetical non-owner setup, source-supported trigger and publish call, and unknown downstream handling. Its path/hash are illustrative and must be replaced. The complete minimal example below is valid data describing an unavailable entrypoint; it claims no source support or observation:

```json
{
  "schema_version": 1,
  "finding": {"id": "candidate", "title": "Unresolved candidate", "summary": "Entrypoint is unavailable."},
  "context": {"repository": "unknown: repository not supplied", "revision": "unknown: source unavailable", "environment": "not run; source requested", "reproduction_status": "not-run"},
  "prerequisites": [{"id": "setup", "description": "Proposed actor invokes the unavailable handler.", "status": "hypothetical", "evidence_ids": [], "gap_ids": ["missing"]}],
  "entities": [{"id": "actor", "name": "Proposed actor", "kind": "actor"}, {"id": "handler", "name": "Unavailable handler", "kind": "external"}],
  "evidence": [],
  "steps": [{"id": "trigger", "title": "Proposed actor trigger", "from": "actor", "to": "handler", "kind": "call", "status": "unknown", "input": {"format": "unknown: exact transport unavailable", "value": "Exact input must be obtained from caller source."}, "operation": "Stop: retrieve the actual caller and handler before asserting behavior.", "checks": [], "state_before": "Unknown initial state.", "state_after": "Unknown; no execution.", "output": "No supported result.", "next": null, "sources": [], "evidence_ids": [], "gap_ids": ["missing"]}],
  "outcome": {"summary": "The claim is unresolved.", "status": "unknown", "evidence_ids": [], "gap_ids": ["missing"], "verification": "Obtain caller/handler source, bind exact inputs and follow checks manually; reproduce only when authorized."},
  "gaps": [{"id": "missing", "description": "Source and concrete setup unavailable.", "needed": "Repository revision, caller, handler, identity binding and exact input.", "verification": "Request source artifacts and inspect actual entrypoint before extending the trace.", "impact": "Cannot establish reachability, behavior or effect."}],
  "author": "author-identity"
}
```

Source excerpt comparison normalizes CRLF to LF and accepts one optional final line terminator. Preserve every blank line inside the inclusive selected range; do not trim trailing blank lines.

Rendering includes every field, full paths/fingerprints and explicit unknowns. Source links use normalized absolute paths with `:start_line`; range/symbol/path remain visible independently for portable manual navigation. The Mermaid diagram uses generated internal participant IDs, one transition per step, matching IDs/ordinals and escaped labels. Generated trusted `<br/>` breaks wrap labels at 36 characters. Participant labels show only stable entity IDs; full names remain in Entities. Step titles are diagram summaries (at most 72 characters), while IDs and statuses remain visible. Each note is only the compact pointer `Checks and state: see numbered detail`; the corresponding numbered step retains the full title, every check/value and all state text. This keeps the diagram an overview of entities and transitions without duplicating long detail text. User-supplied markup is escaped before generated breaks are joined. It describes the selected path only; a message arrow never implies delivery. See [Mermaid sequence syntax](https://mermaid.js.org/syntax/sequenceDiagram). Literal input/code uses fences longer than embedded backtick runs; general prose is escaped. Newlines in labels are flattened, while details preserve their meaning. CR characters in literal blocks are shown as `&#13;`; the output always uses UTF-8 LF.

`render REPORT.json --output REPORT.md` refuses different existing bytes unless `--replace`; identical bytes are a no-op. Output must have `.md` extension, an existing parent directory and no link/junction/reparse components or JSON/source/evidence aliases (including hardlinks). New output uses exclusive creation. Replacement stages complete bytes in system TEMP then uses atomic `os.replace`; a cross-filesystem error preserves the old output and asks you to choose a compatible destination/TEMP setup. No unsafe copy fallback. `check REPORT.json REPORT.md` compares exact generated bytes. `show ... --index` and `--step ID` retrieve compact subsets; review prerequisites/outcome separately. [roles.md](roles.md) defines the exact independent-review receipt and its limitations.
