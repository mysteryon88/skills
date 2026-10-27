# Derived Execution Overlay Template

## Contents

- Human-readable plan
- Schema 2 manifest
- Completed Task evidence
- Global constraint mapping
- Soft same-file overlap record
- Sequential manifest differences
- Runtime replan extension

Copy the original Task text or reference exact Task briefs so the executor never infers omitted requirements. Use the source plan's canonical repository-relative path, replace every angle-bracket value, and run the validator with `--format json` before handoff.

For a plan bundle, first run `scripts/normalize_plan_bundle.py` or the unified compiler. The normalized file remains the schema-2 `source_plan`; its embedded bundle manifest binds every global Task to the exact master/subplan hash, namespaced source Task, and file set. Do not hand-edit those bindings.

## Human-readable plan

```markdown
# <Feature> Execution Overlay

**Source plan:** `<repository-relative path>` at SHA-256 `<digest>`
**Approved spec:** `<repository-relative path>`
**Verdict:** `PARALLEL` or `SEQUENTIAL`
**Reason:** <one concrete graph, ownership, contract, or resource explanation>

## Dependency graph

| Before | After | Kind | Evidence |
|---:|---:|---|---|
| 1 | 3 | interface/order/resource | <source text or repository evidence> |

## Execution topology

- Prelude: <ordered source Tasks or none>
- Wave 1:
  - Lane `<id>`: Tasks <ordered IDs>, owns <surfaces>
  - Lane `<id>`: Tasks <ordered IDs>, owns <surfaces>
- Wave 2: <later lanes and dependencies>
- Epilogue: <integration and broad verification Tasks>

## Frozen contracts and global constraints

State exact signatures, source constraints, affected Tasks, exclusive resources, and executable checks. Write `None` only when the corresponding source section is empty.

## Controlled overlaps

State the file, lane-specific symbols, shared-scaffolding owner, merge order, integration owner, and interaction checks. Write `None` when lanes are file-disjoint.

## Review, integration, verification, and cleanup

Copy the concrete commands and policies from the manifest. Explain the dependency-safe serial merge order and final whole-branch review.

## Approval

For `PARALLEL`, implementation starts only after explicit approval of this saved overlay. For `SEQUENTIAL`, continue immediately with the repository's sequential implementation workflow.
```

## Schema 2 manifest

```markdown
<!-- parallel-execution-manifest
{
  "schema_version": 2,
  "source_plan": "docs/plans/2026-08-14-feature.md",
  "source_sha256": "<64-character SHA-256>",
  "verdict": "parallel",
  "executor": "orchestrating-parallel-worktree-changes-v2",
  "approval_required": true,
  "continue_without_confirmation": false,
  "isolation": "worktree",
  "completed_tasks": [],
  "global_constraints": [
    {
      "constraint": "- Preserve `ApiResponse.version == 1`.",
      "kind": "contract",
      "tasks": [1, 2, 5],
      "checks": [
        "pytest tests/test_api_contract.py",
        "npm test -- frontend-contract.test.ts"
      ]
    },
    {
      "constraint": "- Tasks 2 and 4 require exclusive access to `test-db`.",
      "kind": "exclusive-resource",
      "resource": "test-db",
      "tasks": [2, 4],
      "checks": ["pytest tests/test_database_isolation.py"]
    },
    {
      "constraint": "- Preserve the documented release order.",
      "kind": "ordering",
      "tasks": [2, 4],
      "checks": ["pytest tests/test_release_order.py"]
    }
  ],
  "task_dependencies": [
    {
      "before": 1,
      "after": 4,
      "classification": "hard-implementation",
      "reason": "Task 4 consumes the public contract produced by Task 1"
    }
  ],
  "ordering_constraints": [
    {
      "constraint": "- Preserve the documented release order.",
      "tasks": [2, 4],
      "checks": ["pytest tests/test_release_order.py"],
      "classification": "ordering-only"
    }
  ],
  "prelude_tasks": [],
  "prelude_evidence": [],
  "lanes": [
    {
      "id": "backend",
      "wave": 1,
      "tasks": [1, 2],
      "depends_on": [],
      "owned_files": []
    },
    {
      "id": "docs",
      "wave": 1,
      "tasks": [3],
      "depends_on": [],
      "owned_files": []
    },
    {
      "id": "integration-followup",
      "wave": 2,
      "tasks": [4],
      "depends_on": ["backend", "docs"],
      "owned_files": []
    }
  ],
  "epilogue_tasks": [5],
  "allowed_overlaps": [],
  "contracts": [
    {
      "name": "ApiResponse",
      "producer_lane": "backend",
      "consumer_lanes": ["integration-followup"],
      "frozen_before_parallel": true,
      "signature": "ApiResponse = { version: 1, value: string }",
      "evidence_files": ["tests/fixtures/api-response-v1.json"],
      "contract_tests": [
        "pytest tests/test_api_contract.py",
        "npm test -- frontend-contract.test.ts"
      ]
    }
  ],
  "integration_order": ["backend", "docs", "integration-followup"],
  "topology_metrics": {
    "scheduler": "critical-path-v1",
    "task_count": 5,
    "prelude_size": 0,
    "wave_count": 2,
    "max_active_lanes": 2,
    "source_dag_critical_path": 3,
    "scheduled_critical_path": 3,
    "relationship_counts": {
      "hard-implementation": 1,
      "ordering-only": 1,
      "frozen-contract": 0,
      "shared-file-conflict": 0,
      "exclusive-resource": 1
    }
  },
  "concurrency_conflicts": [],
  "repair_suggestions": [],
  "review_policy": {
    "per_task": true,
    "per_lane": true,
    "spec_and_quality": true,
    "max_fix_rounds": 5,
    "scoped_rereview_each_round": true,
    "final_whole_branch": true,
    "final_fix_waves": 1
  },
  "integrated_verification": {
    "required": true,
    "commands": [
      "pytest tests/test_api_contract.py",
      "python -m unittest discover -s tests",
      "npm run build"
    ]
  },
  "cleanup": {
    "after_merged_verification": true,
    "owned_resources_only": true
  }
}
parallel-execution-manifest -->
```

## Completed Task evidence

Use an empty list when no Task is already complete. A Task completed before compilation must be fully checked in the source plan and backed by commits that exist in the source repository and touch a declared Task file:

```json
{
  "completed_tasks": [
    {
      "task": 1,
      "commits": ["0123456789abcdef0123456789abcdef01234567"],
      "checks": ["pytest tests/test_task_1.py"]
    }
  ]
}
```

## Global constraint mapping

Copy every `## Global Constraints` bullet exactly once. Use `kind` values `policy`, `contract`, `ordering`, or `exclusive-resource`. Every record requires affected source Tasks and executable checks. An exclusive-resource record also requires `resource`; its Tasks cannot occupy concurrent lanes.

## Soft same-file overlap record

Use only with worktree isolation and independent symbols in a non-hard surface:

```json
{
  "file": "src/large-module.ts",
  "lanes": ["header", "footer"],
  "classification": "soft",
  "owned_symbols": {
    "header": ["renderHeader"],
    "footer": ["renderFooter"]
  },
  "shared_scaffolding_owner": "integration",
  "integration_owner": "integration",
  "merge_order": ["header", "footer"],
  "checks": ["npm test -- header.test.ts footer.test.ts interaction.test.ts"]
}
```

## Sequential manifest differences

Use schema 2, keep `completed_tasks`, `global_constraints`, `task_dependencies`, and the full `review_policy`, then replace the parallel fields with:

```json
{
  "verdict": "sequential",
  "executor": "repository-sequential-workflow",
  "approval_required": false,
  "continue_without_confirmation": true,
  "reason": "Every remaining Task changes or consumes the same load-bearing contract.",
  "sequential_tasks": [1, 2, 3, 4]
}
```

Remove `isolation`, lanes, overlaps, contracts, integration, verification, and cleanup fields unless the derived sequential plan retains them only as explanatory prose.

## Runtime replan extension

When V2 returns `replan-required.json`, do not edit source-plan checkboxes to manufacture mid-run completion. Add a hash-pinned handoff and copy the packet's `review_state` into the replacement `SEQUENTIAL` manifest:

```json
{
  "replan_handoff": {
    "packet": "<absolute or overlay-relative replan-required.json path>",
    "packet_sha256": "<64-character SHA-256>"
  },
  "completed_tasks": [
    {
      "task": 1,
      "commits": ["0123456789abcdef0123456789abcdef01234567"],
      "checks": ["pytest tests/test_task_1.py"],
      "completion_origin": "runtime-replan",
      "spec_review": {"verdict": "PASS", "evidence": ["reports/task-1-spec.md"]},
      "quality_review": {"verdict": "APPROVED", "evidence": ["reports/task-1-quality.md"]}
    }
  ],
  "review_state": [
    {
      "task": 2,
      "status": "CHANGES_REQUIRED",
      "fix_round": 2,
      "open_findings": [
        {
          "id": "I-1",
          "severity": "Important",
          "summary": "Preserve the error contract.",
          "evidence": ["reports/task-2-review.md"]
        }
      ],
      "reports": ["reports/task-2.md"]
    }
  ]
}
```

The packet itself must cover every source Task through disjoint `completed_task_commits` and `remaining_tasks`, and `review_state` must cover exactly those remaining Tasks. It hash-pins the old overlay and recovery manifest and uses the nested completion, review, and resource structures defined by the V2 protocol; resource kinds are allowlisted and their paths are absolute. The validator reads the packet, checks those hashes and structures, requires the replacement fields to match it exactly, and permits an unchecked source Task as completed only through this runtime-replan evidence path.
