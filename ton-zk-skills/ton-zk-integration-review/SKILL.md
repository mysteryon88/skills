---
name: ton-zk-integration-review
description: "Use when reviewing the TON integration boundary after proof-system artifacts exist, including canonical scalars, VK handling, public-input semantics, replay, messages, state, gas, or generated verifier edits. Do not use as the sole audit for circuit constraints, prover correctness, proof-system soundness, or ceremony execution."
license: MIT
metadata:
  author: "mysteryon88 / zk-examples"
  ecosystem: "ton"
---

# TON ZK Integration Review

## Overview

Review where a valid proof becomes an authorized TON transition. Findings need a reachable path, violated invariant, evidence, impact, reproducibility, and proportionate severity.

## Scope Boundary

Covers the TON overlay: BLS12-381 artifact compatibility, wrappers/cells/BoCs, runtime-domain binding, TON messaging/state, gas, upgrades, and setup deployment binding. Repository-backed review may require the project's proving stack, generator, compiler, Acton/Blueprint tests, and local artifacts. Use `$groth16-systems` for the general circuit, field, point, setup, artifact, public-input, replay, and application-binding review. Neither skill replaces a proof-system or prover audit.

## Workflow

1. Reproduce versions, artifacts, generated outputs, application paths, builds, and tests.
2. State the proof statement, authorized action, required context/state, and one-time invariant.
3. Check BLS12-381, exact lengths/refs, canonical scalars, point decoding/subgroups/identity, input order, fixed VK, and fail-closed errors.
4. Regenerate/compare verifier and wrapper; identify stale hashes, unsupported templates, hand edits, or changed headers.
5. Trace every public input from circuit signal through client encoding to contract semantics and current state.
6. Attempt same-contract and cross-`global_id`/workchain/contract/action/circuit/VK/protocol/version reuse; verify runtime binding and atomic replay consumption.
7. Review authentication, getter misuse, pre-accept checks, value/balance griefing, bounce/duplicates, effects, reserves, upgrades, and in-flight messages.
8. Review trusted setup, artifact provenance, and VK/update authority.
9. Validate candidates with focused reproducers; classify confirmed, likely, blocked, or informational.
10. Bind the report to immutable revision/artifact identity and run `scripts/validate_review_verdict.py`. Emit `TON_INTEGRATION_READY` and `FULL_ZK_RELEASE_READY` only when their derived phase gates pass; see the [template](references/report-template.md) and [schema](assets/review-verdict.schema.json).

Use the full [checklist](references/review-checklist.md) and [failure catalog](references/known-failure-modes.md).

## Quick Reference

| Invariant | Core question |
|---|---|
| Artifact | Do proof, inputs, VK, protocol, curve, and generator agree? |
| Canonical | Can `x`/`x+r` or one BLS prefix with different tails gain different business meaning? |
| Points | Are malformed, identity, off-curve, and wrong-subgroup values rejected correctly? |
| Statement | Do inputs bind the exact action and current state? |
| Replay/domain | Does runtime domain plus replay state prevent reuse? |
| TON state | Are acceptance, payer/balance, value, gas, bounce, duplicates, effects, and upgrades safe? |
| Verdict | Is the conclusion integration-only, or backed by every full-ZK audit handoff? |

## Common Mistakes

- Reporting underconstraint or subgroup risk without a reachable witness/input and boundary trace.
- Calling a deliberately stateless verifier replay-vulnerable while ignoring its consumer.
- Treating getter replay as state mutation.
- Assuming `queryId`, a network label, sender, or message hash is bound without runtime evidence.
- Testing only short malformed points while missing valid-prefix-plus-tail aliases.
- Ignoring where an external receiver accepts and who pays for invalid proofs.
- Assigning Critical severity from a class name or test-only path.
- Patching generated cryptographic code directly.

## Completion Gate

State scope, revision/artifact identity, versions, and invariants; trace security boundaries; validate BLS/canonical/VK/domain/replay/message/state/deployment/setup integration. Findings need evidence, impact, severity, remediation, and regressions. Run the verdict validator. Owner acceptance cannot turn `BLOCKED`, `NOT_IN_SCOPE`, or `NOT_ASSESSED` work into a technical pass.
