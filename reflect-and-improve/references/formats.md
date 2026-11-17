# Inputs and audit formats

All helper inputs are bounded UTF-8 JSON. Duplicate keys and nonfinite JSON numbers are
refused. Absolute evidence paths reference ordinary readable files; their SHA-256 is
stored, not their contents. Use existing run journals/artifacts as evidence rather than
copying complete transcripts into a new store. Do not include secrets or hidden reasoning.

## Reflection packet

```json
{
  "run_id": "task-42",
  "actor_id": "root",
  "origin": "task",
  "expected": "Report only counts supported by receipts",
  "actual": "A count had no supporting field",
  "versions": {"skill": "recorded-content-hash", "tool": "recorded-version"},
  "observations": [{
    "source_task_id": "task-42",
    "problem": "Unsupported reported count",
    "scope": {"project": "project-id", "role": "reviewer", "task_type": "report", "tools": "tool-v1"},
    "fact": "The report contains 12; the cited receipt has no count field",
    "hypothesis": "The report may have reused an unbound historical value",
    "action": "Require a source field or explicitly report unknown",
    "evidence": ["/absolute/report.md", "/absolute/receipt.json"]
  }],
  "lessons": []
}
```

Allowed trigger origin is `task`. Outputs are marked `reflection` or `improvement`; those
origins and `evaluation` are refused as reflection inputs. One source-task report is
merged, with one pass, not recursively regenerated. A child uses the same root run ID and
binding context plus its own actor ID. Replaying identical input returns the same report.
One incident reported by several actors remains one independent source. Do not relabel
actor/occurrence IDs as source tasks to inflate evidence.

The saved `reports/<run_id>.json` has expected/actual/versions, observations, decision and
inactive lessons. Each observation separates fact/hypothesis, deduplicates its action and
scope, stores all source/actor IDs and evidence refs, and labels single-case/repeated-source
support. This is recorded support, not authenticated proof of causation or recurrence.
Per-source `claims` retain facts, hypotheses and their citations. Differing facts are marked
`needs_reconciliation` with zero corroborating support rather than silently counted as
agreement; wording differences may need human reconciliation too. Alternative hypotheses
remain in their claims even when the observed fact agrees.

## Scoped lesson proposal

Optional entries in `lessons` require `kind` (`project_fact` or `portable_recommendation`),
`applicability`, `problem`, `action`, complete `scope` (project/role/task_type/tools),
`confidence`, its `basis`, `effect`, `versions` and nonempty evidence paths. Effect is
`helped`, `worsened`, `no-visible-effect` or `confounded`. Include `last_verified`, expiry
conditions, contradictory lesson IDs and obsolescence notes when known.

The helper always stores status `inactive`, even if input requests `active`. It deduplicates
equal applicability/scope/action and retains conflicting versions as `contradiction` data.
It does not automatically resolve conflicts, activate recommendations or write project/global
memory. Rejected alternatives remain in experiment records. No lesson is required.

Before reuse, compare project/role/task/tool scope, evidence versions, confidence basis and
expiry assumptions. Move to active scoped memory only as part of the reviewed whole bundle;
generalizing to all agents needs separate transferable evidence and authority.

## Experiment contract

Create this before any candidates. Existing baseline results are reusable only if their
version, inputs, memory, model and context really match. No placeholders qualify for adoption.

```json
{
  "id": "pilot",
  "problem": "A repeated procedure omits a required evidence check",
  "evidence": ["/absolute/reflection-report.json"],
  "conditions": {
    "model": "offline-fixture",
    "parameters": {},
    "tools": {"validator": "frozen-version"},
    "data": "frozen-dataset-hash",
    "memory": "empty-or-frozen-hash",
    "context": "frozen-request-and-tool-context-hash"
  },
  "metric": {"name": "valid_outputs", "direction": "higher", "min_delta": 1},
  "hard_checks": ["scope_preserved", "dependencies_complete"],
  "budget": {"seconds": 600, "cost": 0},
  "evaluator": "/absolute/fixed-evaluator.py",
  "development_tasks": ["dev-a"],
  "acceptance_tasks": ["heldout-b"]
}
```

`higher`/`lower` determines score direction; `min_delta` must be positive. Budget seconds is
an enforced wall deadline from experiment creation (maximum one day). Cost/time receipts
also cover all named stages and imports. The helper does not meter externally performed
work; it never starts that work. No budget value enables live execution or automatic adoption.

Refusal rules are fixed by the controller: any candidate hard-check failure or reported
budget overflow rejects; missing/error/unstable/tied scores retain baseline; malformed,
incomplete or mismatched identities refuse the import; stale evidence blocks adoption.
The evaluator file is hashed and never executed by the helper. Evaluator, frozen contract
and evidence paths must not overlap any editable target file. Criteria/controller/policy
remain outside candidate edits. Heldout content and grading answers must be confined by
an external supported executor before claiming independent evaluation; this release reports
`independent_acceptance: false` and never automatically accepts.

## Paired comparison receipt

Replace the version/contract/evaluator hashes with the values returned by `improve` and
`candidate`. The input receipt and every cited output are hashed again before adoption.

```json
{
  "baseline": "64-lowercase-hex-digits",
  "candidate": "64-lowercase-hex-digits",
  "contract": "contract_hash-from-improve",
  "evaluator": "evaluator.sha256-from-improve",
  "results": [{
    "task_id": "dev-a",
    "baseline": {
      "score": 0,
      "conditions": {"model":"offline-fixture","parameters":{},"tools":{"validator":"frozen-version"},"data":"frozen-dataset-hash","memory":"empty-or-frozen-hash","context":"frozen-request-and-tool-context-hash"},
      "checks": {"scope_preserved":true,"dependencies_complete":true}
    },
    "candidate": {
      "score": 1,
      "conditions": {"model":"offline-fixture","parameters":{},"tools":{"validator":"frozen-version"},"data":"frozen-dataset-hash","memory":"empty-or-frozen-hash","context":"frozen-request-and-tool-context-hash"},
      "checks": {"scope_preserved":true,"dependencies_complete":true}
    }
  }],
  "usage": {
    "baseline":{"cost":0,"seconds":1}, "candidate":{"cost":0,"seconds":1},
    "editor":{"cost":0,"seconds":0}, "judge":{"cost":0,"seconds":0},
    "reflection":{"cost":0,"seconds":1}, "subagents":{"cost":0,"seconds":0},
    "retries":{"cost":0,"seconds":0}
  },
  "evidence": ["/absolute/paired-output.json"],
  "stable": true,
  "evaluator_error": null
}
```

Every frozen phase task must occur exactly once in each receipt. Acceptance uses the
separate declared acceptance IDs only after selection. Both arms must have exactly the
frozen conditions and named Boolean check results. Scores are finite numbers or null;
null/error yields indeterminate. The primary comparison uses the mean paired difference
in the declared direction, with the minimum delta and no candidate hard-check failures.
All imports for that candidate/phase must be eligible; previous uncertainty conservatively
retains baseline. No selection by acceptance results, no automatic combination.

Only the trusted operator imports receipts after reviewing actual outputs. Receipt JSON
does not authenticate who ran a test, whether a reported result is true, or spending.
Synthetic/offline fixtures prove switching/refusal mechanics, never LLM quality improvement.

## On-disk separation

`policy.json` and `state.json` hold control and active/pin history; `versions/<hash>/files/`
holds complete content-addressed bundles plus dependencies. `reports/` holds reflection
audit/inactive scoped lessons; `experiments/` holds contracts, alternatives, evaluations,
rejections and decisions. A pending `transaction.json` references its owned system TEMP
payloads for hash-classified recovery. None is an automatic memory source. Preserve reports
and rejected candidates; clean only owned temporary artifacts after completed recovery.

## Typed scenario laboratory packet

The explicit scenario-lab `reflection-packet --project ID --run RUN --task ORIGINAL_TASK`
command creates `evidence.json`, compatible `packet.json` and a last-published manifest
in a private content-addressed bundle. Optional `--before RUN` adds structural contrasts.
The adapter uses opaque domain-separated aliases for identities and generated directories;
its packet run ID binds the frozen export context, while source_task_id groups the
operator-supplied original task across Runs. This asserted grouping is not authenticated.

Only typed outcomes/counts, hashes, booleans and fixed explanatory text are projected.
Reported versus effective outcomes, missing checks, cleanup, legacy/truncated journals
and receipt-verified known-route counts remain separate. Journal authenticity is
unverified: detectable structural errors refuse export, but valid historical edits
are not attested. Export digests protect subsequent readback only. Incomplete or
different source/program/execution/actor context cannot establish causal comparability.

At most 50 observations and 1 MiB per JSON are allowed; this adapter emits one neutral
observation with no proposed action and no lessons. Its helper import should remain
insufficient_evidence/inactive, not fabricate a portable recommendation. The only
evidence reference is its own sanitized absolute file. The trusted local data-root
prefix can reveal filesystem/user information; this is private pseudonymized evidence,
not an anonymous public export. Inspect it before sharing. Do not alter immutable
bundle files to add interpretation: prepare a separate reviewed input when authorized.
