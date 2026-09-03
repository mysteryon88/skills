# TON ZK integration review overlay

Complete the general `$groth16-systems` review first. Mark each TON item `pass`, `fail`, `blocked`, or `not applicable` and attach source, command, test, or artifact identity.

## 1. TON route and reproducibility

- Record repository revision, TON toolchain and generator versions, target network/workchain, and contract addresses.
- Identify BLS12-381 source artifacts, generated verifier, wrapper, compiled code, proof-message fixtures, and proof-context manifest.
- Regenerate into a clean path and compare cryptographic constants, wrapper layout, and compiled output.
- Confirm `export-ton-verifier doctor` accepts the exact artifact and target.

## 2. TON artifact and parser boundary

- Confirm the supported route is BLS12-381 and public-input order survives every conversion.
- Require exact G1/G2 slice widths, byte alignment, tuple/dictionary shape, and zero unexpected refs before TVM BLS operations.
- Test one-byte-short, valid-prefix-plus-tail, extra bits, extra refs, malformed flags, and wrong input counts.
- Distinguish generator-time fixed-VK validation from runtime attacker-controlled proof parsing.

## 3. TON public-input mapping

For each index, record the registered encoding profile, wrapper/cell location, authenticated TON source, and exact receiver check. Cover runtime `global_id`, workchain, current address, action/opcode, circuit/VK/protocol/version, identities, amount/object, root, replay value, and expiry as applicable.

Reject a release whose network separation is only a human-readable manifest label.

## 4. TON authorization and state

- Derive authorization from message context or an authenticated signature/proof, not a body-supplied address.
- Keep proof verification, semantic policy, replay consumption, and protected transition atomic.
- Treat getters as read-only observations, not authorization for a later transaction.
- Review internal versus external receiver behavior, `ACCEPT` timing, payer/value, reserves, bounce, duplicates, callbacks, failed actions, and messages in flight.
- For asynchronous verifier contracts, authenticate and correlate one response to one pending request and handle timeout/reorder/upgrade cases.

## 5. TON replay and upgrades

- Attempt same-message, changed-`queryId`, cross-network/workchain/contract/action/circuit/VK/version, and concurrent replay.
- Confirm runtime config-19 `global_id` and current contract address are checked.
- Review root history, replay-store pruning, VK/circuit upgrades, rollback, and old or in-flight proofs.
- For signed external envelopes, confirm pre-accept authentication and committed envelope replay state do not prematurely consume the application nullifier.

## 6. Generated code and release evidence

- Flag hand edits to pairing, transcript, scalar, point, VK, input, or parser logic.
- Preserve SPDX/license headers and record generator/lockfile provenance.
- Bind proof artifacts, generated output, compiled code, deployment address, and smoke tests in one release record.
- Record gas and code-size snapshots for representative and worst supported paths.

## 7. Findings

A TON finding needs a reachable message/state path, violated invariant, reproducible fixture, actual versus expected transaction/state effect, impact, confidence, smallest safe remediation, and regression test. Unsupported general proof-system concerns belong in the separate audit handoff rather than the TON integration verdict.
