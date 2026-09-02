# Change and Debug Modes

| Mode | Required discovery | Required verification | Forbidden shortcut |
| --- | --- | --- | --- |
| Proposal | Current constraints, reusable patterns, options, migration cost | Compare scope, risk, compatibility, and verification | Recommending before understanding the existing seam |
| Bug fix | Reproduction, failing path, data/control flow, related changes, nearest regression test | Focused check fails for the intended reason, then passes; broader affected checks | Treating symptoms before finding the owner |
| Feature | Public seam, similar feature, owning modules, coupled layers, compatibility | Thin vertical slice, affected tests, build/type/lint, meaningful manual flow | Parallel architecture, duplicate components, speculative abstractions |
| Refactor | Characterized behavior, callers, invariants, coverage gaps | Behavior-preservation checks before and after each slice | Mixing new behavior into cleanup |
| Migration or schema change | Producers, consumers, compatibility window, rollout, existing data, rollback | Migration, compatibility, data validation, and rollback checks | One-step break or irreversible change without recovery |
| Security | Assets, trust boundaries, attacker inputs, auth/authz, secret and data flows | Threat-specific and negative authorization checks | Generic checklist disconnected from the boundary |
| Performance or reliability | Baseline, workload, bottleneck evidence, failure/retry/time behavior, limits | Repeatable benchmark or load check and regression threshold | Optimizing from intuition |
| CI, deployment, or infrastructure | Workflows, environments, permissions, artifacts, secret interfaces, rollback | Safe dry run, config validation, deployment/recovery evidence | Unauthorized live, credential, or destructive change |
| Testing or quality | Test pyramid, stable seams, uncovered behavior, flaky sources, CI commands | New test fails for the intended gap and passes after change | Mocking implementation instead of observable behavior |
| Documentation | Source of truth, audience, version, supported commands/API | Validate links, commands, and examples | Documenting assumed behavior as current |

## Cross-layer trace patterns

Use a trace as a search guide, never as proof:

- Web: route/page -> component -> state/query -> API -> handler -> service -> persistence -> tests.
- Event: producer -> schema -> broker -> consumer -> side effect -> retry/dead-letter -> observability -> tests.
- CLI: entry point -> parser -> command -> domain -> filesystem/network -> exit/output -> tests.
- Library: public API -> validation -> implementation -> external boundary -> compatibility -> examples/tests.
- Data pipeline: source -> ingestion -> transformation -> storage -> quality -> consumer -> recovery.
- Mobile/desktop: view -> state -> domain -> storage/network/platform -> lifecycle -> tests.
- Infrastructure: desired config -> plan/render -> platform -> state -> rollout -> health -> rollback.

Replace the guide with exact project files and symbols after inspection.
