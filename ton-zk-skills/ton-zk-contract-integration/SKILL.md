---
name: ton-zk-contract-integration
description: "Use when integrating a TON ZK verifier, proof/public-input cells or BoCs, wrappers, internal/external messages, global_id/state binding, authorization, or nonce/nullifier replay protection."
license: Apache-2.0
metadata:
  author: "mysteryon88 / zk-examples"
  ecosystem: "ton"
---

# TON ZK Contract Integration

## Overview

A verifier proves one relation under one VK; the application binds it to authenticated TON context, current state, and one authorized transition.

## Operating Rules

- Use `$groth16-systems` for general application binding; this skill adds TON execution and encodings.
- The bundled validator requires Python 3.10+; builds and tests use the target repository's pinned TON toolchain.
- Separate verifier validity, authorization, and state transition.
- Validate the [example](assets/proof-context.example.json) and [schema](assets/proof-context.schema.json). The helper separates consistency and artifact identity; it does not verify the circuit or implementation.
- Bind security values through public inputs or authenticated message/state sources; body-supplied addresses are not authentication.
- Bind runtime `global_id`, workchain, current address, action, circuit/VK, protocol, and version.
- Persist and atomically consume a nullifier, nonce, seqno, or one-shot marker.
- Reject wrong proof widths, trailing bits/bytes, and refs before TVM BLS operations.
- A getter is read-only; reverify and enforce policy in the state-changing transaction.
- Prefer value-carrying internal messages; never accept an external message unconditionally.

## Workflow

1. Record proof fields, exact layout, public-input representation, message kind/opcode, wrapper, and value rule.
2. Add TON profiles and authenticated sources. Define nonce/seqno bits and range.
3. Bind runtime `global_id`, workchain, current address, opcode, and TON state.
4. Design storage for replay state, roots, VK/version authority, pending operations, and reserves.
5. For internal messages: parse, authenticate, range-check, verify, check semantics/state, then atomically consume the application nullifier and transition.
6. For signed external messages, authenticate and check envelope replay before `ACCEPT`; persist and `COMMIT` it before expensive ZK work. Consume the application nullifier only with success.
7. Define acceptance, payer/value, bounce, duplicates, callbacks, reserves, and in-flight behavior.
8. Decode golden wrapper BoCs and compare the complete graph and representation hash with the contract layout.
9. Run:

```bash
python3 <skills-root>/ton-zk-contract-integration/scripts/validate_proof_context.py \
  ./proof-context.json --project-root .
```

Then use `$ton-zk-testing` for getter, message, state, replay, acceptance, balance, and bounce assertions.

References: [architecture](references/architecture-patterns.md), [public inputs](references/public-input-semantics.md), executable [TON encoding vectors](assets/ton-encoding-vectors.json), [encoding](references/message-encoding.md), [replay/domain](references/replay-and-domain-separation.md), and [external messages](references/external-messages.md).

## Quick Reference

| Layer | Required invariant |
|---|---|
| Circuit | Intended relation and context are exposed |
| Verifier | Fixed VK, canonical inputs, valid proof |
| Policy | Inputs match authenticated request/current state |
| Replay | Fresh marker becomes consumed |
| Application | Exactly one atomic state change |
| Messaging | Lengths/refs, acceptance, value, bounce, duplicates, and reserves are safe |

## Common Mistakes

- Checking proof validity but not application semantics.
- Relying on wrapper-only `queryId` for replay protection.
- Reducing an external value modulo the field before business interpretation.
- Trusting an address supplied only in the body.
- Splitting verification and execution without robust correlation state.
- Letting BLS parsing ignore a tail used elsewhere.
- Accepting an external message before cheap authentication/replay checks.
- Treating get-method output as consensus authorization.

## Completion Gate

Report manifest, input map, authenticated sources, runtime domain, replay key, message layout, external acceptance/payer, getter role, atomic transition, bounce/value policy, wrapper/BoC fixture, and end-to-end tests. Every application input needs one unambiguous check.
