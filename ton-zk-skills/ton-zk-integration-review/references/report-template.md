# TON ZK Security Review Report Template

Use one copy of the finding section per validated issue. Replace bracketed prompts with concrete evidence and remove unused prompts before delivery.

## Review metadata

- Repository and revision:
- Reviewed artifact-manifest path and SHA-256:
- Review date:
- Reviewer/agent:
- Scope paths/contracts:
- Excluded paths/components:
- Target network/workchain:
- Circuit/protocol/curve:
- Generator and compiler versions:
- Artifact/VK/verifier hashes:
- Build command and result:
- Test command and result:
- Blocked validation:

## Intended security invariants

1. [What statement is proven?]
2. [What exact TON action may one valid proof authorize?]
3. [Which authenticated context and current state must match?]
4. [What makes the action one-time?]
5. [What domain/version prevents cross-context reuse?]

## Public-input map

| Index | Signal/name | Encoding/range | Source | Contract/policy check | Freshness/domain role |
|---:|---|---|---|---|---|
| 0 |  |  |  |  |  |

## Executive summary

- **TON integration verdict:** `TON_INTEGRATION_READY` / `TON_INTEGRATION_PARTIALLY_READY` / `TON_INTEGRATION_NOT_READY`
- **Full ZK release verdict:** `FULL_ZK_RELEASE_READY` / `FULL_ZK_RELEASE_NOT_READY`

[State findings, strongest evidence, and blocked areas. `TON_INTEGRATION_READY` requires `PASS` for TON integration and deployment evidence; a `FAIL` in either is `TON_INTEGRATION_NOT_READY`; other incomplete combinations are `TON_INTEGRATION_PARTIALLY_READY`. The full verdict is ready only when every required phase below is `PASS`.]

| Required phase | Status: PASS / FAIL / BLOCKED / NOT_IN_SCOPE / NOT_ASSESSED | Evidence or exact blocker |
|---|---|---|
| Circuit audit |  |  |
| Proof-system audit |  |  |
| Prover/converter audit |  |  |
| Setup/SRS review |  |  |
| TON integration audit |  |  |
| Deployment evidence |  |  |

Owner acceptance cannot convert `NOT_IN_SCOPE`, `NOT_ASSESSED`, or a material `BLOCKED` phase into `PASS` or `FULL_ZK_RELEASE_READY`.

## Finding [ID]: [Specific violated invariant]

- **Severity:** Critical / High / Medium / Low / Informational
- **Confidence:** High / Medium / Low
- **Status:** Confirmed / Likely / Blocked / Fixed / Accepted
- **Affected component:** `[path:line or contract/function]`

### Summary

[One paragraph: attacker, action, violated invariant, and concrete impact.]

### Preconditions

- Attacker capability:
- Required proof/credential/state:
- Required deployment/configuration:
- Timing or message assumptions:

### Technical evidence

[Trace attacker-controlled input through parsing, verification, semantic checks, replay storage, and state transition. Include relevant source locations and artifact hashes.]

### Reproduction

```text
1. Build/setup command and fixture provenance.
2. Exact attacker input or mutation.
3. Exact command/test invocation.
4. Actual output, exit code, transaction, and state delta.
5. Expected secure behavior.
```

### Impact

[Describe affected assets/users, scope, repeatability, recovery requirements, and whether funds/state can be restored.]

### Severity rationale

[Map impact and prerequisites to `severity-model.md`; explain why adjacent ratings are not appropriate.]

### Root cause

[Name the missing or incorrect invariant, not merely the line that manifests it.]

### Remediation

[Give the smallest safe source-level change. Prefer circuit/generator/policy changes over direct edits to generated cryptographic code. Include migration/version/nullifier implications.]

### Regression test

[Specify one valid case and focused negative cases that fail before the fix and pass/reject correctly after it. Include state and transaction assertions.]

### Residual risk

[State assumptions that remain, such as trusted setup, external root authority, upgrade keys, or unaudited circuit code.]

## Non-findings and validated controls

- [Control checked, evidence, and result.]
- [Suspicion disproved and why.]

## Blocked checks

| Check | Missing prerequisite | Security consequence | Exact next action |
|---|---|---|---|
|  |  |  |  |

## Final release gate

Machine-readable companion: copy [`review-verdict.example.json`](../assets/review-verdict.example.json), replace its `reviewTarget` with the immutable repository revision and exact artifact-manifest SHA-256, then run:

```bash
python3 <skills-root>/ton-zk-integration-review/scripts/validate_review_verdict.py \
  ./review-verdict.json --format json
```

The helper derives both verdicts from phase statuses. `PASS` requires non-empty evidence and no blocker; every non-`PASS` requires an exact blocker. Owner-accepted risk is recorded separately and never changes a derived verdict.

### TON integration gate

- [ ] Exact artifacts and versions are reproducible.
- [ ] Proof/VK/curve/protocol/public-input order are consistent.
- [ ] Canonical scalar and point/subgroup boundaries are validated.
- [ ] Every public input has an application-semantic check.
- [ ] Replay and cross-domain tests reject reuse.
- [ ] State transition is atomic and TON message/bounce/value behavior is tested.
- [ ] Setup/SRS provenance and VK/update authority are documented as integration assumptions.
- [ ] All confirmed findings have regression tests and retest evidence.

### Full ZK release gate

- [ ] Circuit audit is `PASS` with frozen constraint identity and retest evidence.
- [ ] Proof-system audit is `PASS`.
- [ ] Prover/converter audit is `PASS`.
- [ ] Setup/SRS review is `PASS`.
- [ ] TON integration audit is `PASS` and supports `TON_INTEGRATION_READY`.
- [ ] Deployment evidence is `PASS`.
- [ ] No required phase is `BLOCKED`, `NOT_IN_SCOPE`, or `NOT_ASSESSED`.

Only then emit `FULL_ZK_RELEASE_READY`; otherwise emit `FULL_ZK_RELEASE_NOT_READY` and preserve accepted risks separately.
