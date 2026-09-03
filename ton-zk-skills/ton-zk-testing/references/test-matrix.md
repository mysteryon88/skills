# TON ZK test overlay

Run the generic `$groth16-systems` circuit, artifact, point/scalar, application-binding, and replay matrix first. Every TON row below needs a named test, expected rejection layer, and assertions on transactions, storage, replay state, balances, and outgoing actions.

## Layer 1: TON artifact conversion

| Case | Expected evidence |
|---|---|
| `doctor` on reviewed BLS12-381 artifact | Selected target and all required checks pass |
| Wrong curve/protocol/format/template | Generation is blocked |
| Native versus converted VK/proof | Cross-language fixture agrees |
| Wrapper versus independent encoder | Public values and complete cell graph match |
| Generated output from another build | Hash/version mismatch is detected |

## Layer 2: TON parser and verifier

| Case | Expected evidence |
|---|---|
| Valid getter and state-changing message | Expected result and exact state delta |
| One-byte-short G1/G2 | Deterministic malformed rejection |
| Valid BLS prefix plus trailing byte/bits/ref | Rejected before TVM BLS verification |
| Same prefix with different tails | Both non-canonical messages reject |
| Wrong tuple/dictionary count or key width | Deterministic parser rejection |
| Wrong TON public-input flattening | Verification or policy rejects at documented layer |
| BoC decode/re-encode | Canonical representation has no semantic alias |

## Layer 3: TON semantic context

Change one TON value at a time:

- runtime `global_id`, workchain, current contract address, or application domain;
- circuit/VK/protocol/action/opcode/version;
- sender/owner, recipient, amount/token/object;
- accepted root/version, nullifier/nonce/seqno, or expiry;
- registered address/cell/domain encoding profile.

Assert protected state and outgoing actions remain unchanged.

## Layer 4: TON replay and messaging

- identical internal message twice and near-concurrent duplicate replay keys;
- changed wrapper `queryId` with the same proof;
- stale/future nonce, root, version, or expiry;
- insufficient/exact attached value, malformed body, unknown opcode, and extra refs;
- bounce, duplicate/reordered callback, failed action phase, and reserve boundary;
- signed external envelope rejected before acceptance for wrong signer/seqno/expiry/domain;
- failure after `ACCEPT` and `COMMIT`: envelope replay is consumed, application nullifier remains fresh, and protected state/actions remain unchanged;
- redelivery rejects before another paid proof verification.

## Layer 5: TON performance and reproducibility

- clean build and regeneration from recorded hashes;
- verify gas for representative and worst supported shapes;
- code-size bits/cells and maximum supported public-input count;
- reviewed snapshot deltas and practical CI runtime.

## Exit evidence

Report commands, TON tool versions, target, test names and counts, blocked cases, gas/code-size deltas, and hashes for artifacts, fixtures, wrapper, generated verifier, and compiled code.
