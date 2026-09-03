# Known TON ZK integration failure modes

Use the general `$groth16-systems` failure patterns first. This catalog contains TON-specific manifestations that require TVM, cell/message, or TON state evidence.

## Oversized BLS slice accepted by prefix

The receiver passes a valid 48/96-byte prefix plus trailing bits, bytes, or refs to a TVM BLS operation while another layer treats the full payload as distinct. Require exact slice shape before the opcode and test different tails over the same prefix.

## TON encoding profile drift

Circuit, wrapper, and receiver disagree on address-cell preimage, ordinary-cell representation hash, 128-bit limb order, BoC versus cell hash, or registered domain profile. Compare the complete encoded graph and golden vectors; do not normalize until verification succeeds.

## Manifest-only network separation

Metadata names a network but the checked domain omits runtime config-19 `global_id`, workchain, or current contract address. Demonstrate reuse under another runtime domain and bind the observed values through the registered domain profile.

## Getter used as authorization

An off-chain getter returns `true`, then a separate state-changing path acts without atomic re-verification and policy checks. Change state or sender between calls, replay the proof, and invoke the state-changing receiver directly.

## Non-atomic verifier contract

A dedicated verifier sends an asynchronous result without authenticated request correlation, one-time completion, bounce/timeout handling, or upgrade policy. Duplicate, reorder, replay, bounce, or stale-success messages can authorize the wrong transition.

## TON replay marker not consumed

A wrapper `queryId`, body nonce, or nullifier exists but is not authenticated/proven, checked in storage, and consumed with the protected transition. Submit the same message twice, change wrapper-only metadata, and exercise bounce/retry paths.

## External-message balance drain

An external receiver calls `ACCEPT` before cheap signer/seqno/expiry/domain checks, then the contract funds attacker-controlled proof attempts. Repeated invalid proofs must include balance/gas evidence, not only exit codes.

## Bounce and duplicate inconsistency

The protected state update and outgoing action are not reconciled on bounce, or a retry repeats the effect. Inspect balances, replay state, pending records, outgoing actions, and duplicate/reordered callbacks.

## Stale TON generated bundle

The proof/VK, generated verifier, wrapper, compiled code, or deployed contract comes from a different build. Regenerate from recorded artifacts, compare hashes, and run mismatched-bundle negative tests.

## Unsafe TON root or upgrade lifecycle

Stale roots remain accepted indefinitely, or old proofs/messages cross circuit, VK, code, or state migrations without explicit version policy. Test proof generation before an update and delivery after it, including in-flight messages and rollback.
