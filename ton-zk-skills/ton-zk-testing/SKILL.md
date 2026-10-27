---
name: ton-zk-testing
description: "Use when testing TON zero-knowledge verifier contracts or integrations, including tampered proofs, malformed encodings, getters/messages, replay/state, gas, code size, or regression gates."
license: MIT
metadata:
  author: "mysteryon88 / zk-examples"
  ecosystem: "ton"
---

# TON ZK Testing

## Overview

Test proof, verifier, policy, and TON transition separately, then together. A valid proof must work only for its exact VK, inputs, context, message, and state.

## Operating Rules

- Use `$groth16-systems` for the generic proof, public-input, artifact-mismatch, canonical-field, point-validation, and application-binding negative matrix; add the TON cases below.
- Start from one locally verified valid fixture.
- Change one dimension per negative test.
- Test both getter and state-changing internal message; assert transactions, exit codes, storage, replay state, and outgoing actions.
- Include scalar boundaries, exact BLS lengths, trailing-byte/ref cases, and malformed encodings, not only `+1` mutations.
- Record and review gas/code-size snapshots; never auto-accept regressions.
- Never log private witness, entropy, keys, or production proving material.
- Use the repository-pinned test binaries; do not let `npx` install missing tools as an incidental test step.
- Inspect package engines, lockfiles, Acton/Blueprint help, and Sandbox versions before changing Node.js or test dependencies.

## Workflow

1. Record circuit/VK/generator hashes, versions, lockfile, target, and commands.
2. Prove/verify locally; encode through supported helpers; assert getter success and exact state transition.
3. Reuse the generic negative baseline, then exercise TON dictionary/list flattening, wrapper/cell/BoC encoding, and runtime domain mapping.
4. Compare wrapper/cell/BoC encoding with an independent decoder/encoder and assert canonical decode/re-encode parity.
5. For each BLS component, send the same valid 48/96-byte prefix with different tails; reject both before the TVM BLS opcode.
6. Test low value, unknown opcode, malformed cell, bounce, duplicates, large payload, reserves, and failed actions. For external receivers, assert acceptance, payer, repeated-invalid balance delta, and pre-accept auth/replay.
7. Save verify gas and code size in bits/cells; gate unexpected deltas.
8. Run the full repository suite and report exact results.

Use the [test matrix](references/test-matrix.md), [Blueprint/Sandbox](references/blueprint-and-sandbox.md), [negative fixture design](references/negative-fixtures.md), executable [fixture catalog](assets/negative-fixtures.json), [upgrade matrix](references/upgrade-matrix.md), and [gas/code size](references/gas-and-code-size.md).

## Quick Reference

| Layer | Positive | Negative |
|---|---|---|
| Prover | Local verify true | Wrong witness/input/VK false |
| Verifier | Valid getter/message | Tampered/malformed reject |
| Policy | Exact context accepted | Every changed field rejects |
| Replay | First use succeeds | Second use fails with no partial state |
| TON | Expected transaction/state/actions | Exact lengths, low value, acceptance, balance, bounce, duplicate safe |
| Performance | Snapshot recorded | Unreviewed regression fails gate |

```bash
npx --no-install blueprint build --all
npx --no-install blueprint test
npx --no-install jest --runInBand
```

## Common Mistakes

- One happy path is treated as evidence for every layer.
- A negative case changes proof and public inputs together, hiding the intended mismatch.
- Field boundaries, exact BLS slice lengths, public-input reordering, runtime domain, and replay storage are untested.
- Tests assert transaction success but not state delta and outgoing messages.
- Huge `.ptau`, `.zkey`, witness, or secret fixtures are checked in without need/provenance.

## Completion Gate

Report fresh commands, fixture provenance, local/getter/message results, acceptance/balance/state assertions, negative coverage, counts, gas, code size, snapshot deltas, and blockers. No “tests pass” claim without fresh output.
