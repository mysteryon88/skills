# Mina/o1js Security Bug Patterns

Use this as a checklist during reviews.

## 1. State read is not bound to current chain state

Pattern:

```ts
const value = this.value.get();
// security logic
this.value.set(newValue);
```

Risk: stale or unconstrained state assumption.

Fix:

```ts
const value = this.value.getAndRequireEquals();
```

or:

```ts
const value = this.value.get();
this.value.requireEquals(value);
```

## 2. Witness is private but not constrained

Pattern:

```ts
const secret = Provable.witness(Field, () => input);
// no assertion ties secret to public state/input
```

Risk: prover can choose any value.

Fix: assert hash/signature/Merkle relation to public input or state.

## 3. JS conditional used on provable value

Pattern:

```ts
if (x.equals(y).toBoolean()) { ... }
```

Risk: wrong compile/prove-time behavior or unsafe assumptions.

Fix: use assertions or `Provable.if()` without side effects.

## 4. Field used as bounded integer

Pattern:

```ts
const amount = Field(userAmount);
```

Risk: modular arithmetic, overflow/underflow surprises.

Fix: use `UInt64`, `UInt32`, etc., and assert bounds.

## 5. Missing domain separation

Pattern:

```ts
Poseidon.hash([secret, amount])
```

Risk: cross-protocol collisions/reuse.

Fix:

```ts
Poseidon.hash([DOMAIN, appId, actionId, secret, amount.value])
```

## 6. Signature does not bind enough data

Pattern:

```ts
sig.verify(admin, [amount.value]).assertTrue();
```

Risk: replay to another recipient/contract/action.

Fix: bind contract address, action, recipient, amount, nonce, expiry and domain.

## 7. Permissions left loose

Pattern:

```ts
// deployment uses defaults, no explicit permission matrix
```

Risk: verification key or permissions can be changed unexpectedly.

Fix: set and test explicit permissions according to upgrade policy.

## 8. AccountUpdate child abuse

Pattern:

```ts
approveBase(forest) { this.approve(forest); }
```

Risk: unexpected token balance changes or unauthorized child updates.

Fix: inspect/limit child updates and assert zero or expected balance changes.

## 9. Reducer can be bricked

Pattern:

```ts
// reducer assumes every action is well-formed and provable
```

Risk: attacker dispatches bad action, future reductions fail.

Fix: canonicalize action type, make reducer total, skip or handle malformed actions safely.

## 10. Privacy leak through public metadata

Pattern:

```ts
emitEvent('credential', rawCredentialHashOrPII);
```

Risk: linkability or PII leak.

Fix: publish only necessary commitments/nullifiers and document leakage.

## 11. Frontend sends witness to backend without disclosure

Pattern:

```text
Browser sends passport/secret to API, API generates proof, product claims local privacy.
```

Risk: backend sees private data.

Fix: local proving, or explicit trusted prover model and log redaction.

## 12. Tests only cover happy path

Pattern:

```text
All tests use deployer/admin and valid witness.
```

Risk: critical bugs never tested.

Fix: wrong witness, unauthorized caller, replay, stale state, permission and AccountUpdate abuse tests.

## 13. Network era and signer format disagree

Pattern:

```text
o1js/mina-signer defaults to Mesa, but the target network or stored transaction is Berkeley.
```

Risk: signatures, commitments, verification keys, or transaction JSON are valid for a different protocol era.

Fix: record and enforce network era, signer era, package versions, chain context, and test vectors before signing.

## 14. Stale verification key or proof cache after upgrade

Pattern:

```text
Dependency major version changes, but cached compile artifacts and deployed VK are reused.
```

Risk: proofs fail, the frontend points to an incompatible deployment, or a rollback mixes artifacts.

Fix: isolate era/version cache directories, regenerate artifacts, compare VK hashes, and verify the deployed account.

## 15. Variable-length commitment uses fixed-length hashing ambiguously

Pattern:

```text
Different producers concatenate or pad variable input differently before Poseidon.hash().
```

Risk: cross-implementation disagreement, truncation, or ambiguous statements.

Fix: use a versioned canonical schema and `Poseidon.hashAnyLength()` when the installed version and statement require variable length; bind domain, length, field order, and optional presence.

## 16. Wallet hash is treated as final state

Pattern:

```text
UI or backend applies irreversible business effects immediately after sendTransaction returns a hash.
```

Risk: dropped, rejected, reorganized, or unindexed transactions are treated as settled.

Fix: model broadcast, inclusion, live visibility, archive indexing, safe depth, and finality separately.

## 17. Delegated authorization is only a login or generic signature

Pattern:

```text
Agent is authenticated, but approval does not bind mission, tools/data, app/network, budget, expiry, replay control, or receipt.
```

Risk: a valid identity can perform an unintended or replayed action.

Fix: use a canonical mission-bound authorization statement, enforcement checkpoints, revocation/replay policy, and output/payment receipts.
