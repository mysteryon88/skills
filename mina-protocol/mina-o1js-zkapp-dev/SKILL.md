---
name: mina-o1js-zkapp-dev
description: Use when learning, designing, implementing, refactoring, or debugging Mina zkApps with o1js, SmartContract methods, state preconditions, proofs, witnesses, permissions, or AccountUpdates.
---

# Mina o1js zkApp Development Skill

## Use when

Use this skill when the user wants to learn, design, write, refactor or debug Mina zkApps with o1js.

This skill is for practical programming. It should help the user move from idea to working code, tests and security notes.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Compatibility gate

Before a version-sensitive claim, record the target network, active protocol era, exact `o1js` and signer versions, wallet/CLI versions, endpoints, and the origin of verification keys and proof caches. Load `../mina-protocol-agent/references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js 3 migration rules. If the era is unknown, label the guidance unverified rather than guessing from package or endpoint names.

## Current implementation preflight

Before editing code, determine whether the target is Berkeley/o1js 2, Mesa/o1js 3, local, or Zeko. Do not mix verification keys, caches, proofs, signer formats, transaction limits, or serialized APIs across those environments. Derive state, event/action, and AccountUpdate limits from the pinned version and test boundaries.

For transaction code, use `../mina-protocol-agent/references/playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md`: build with explicit sender/fee/network, inspect the AccountUpdate tree, prove before wallet serialization/signing, sign only locally owned keys, persist non-secret recovery metadata, and distinguish inclusion/indexing/finality.

## Default posture

Act like a careful Mina/o1js pair programmer.

Do not copy EVM assumptions into Mina. Always reason in terms of:

- off-chain prover execution;
- proof constraints;
- AccountUpdates;
- state preconditions;
- signatures and permissions;
- public inputs vs private witnesses;
- frontend/backend/prover trust boundaries.

## Required first step

Before coding, produce a compact design note:

```text
Goal:
Contract classes:
State fields:
Methods:
Public inputs:
Private witnesses:
AccountUpdates:
Permissions involved:
Trusted parties:
Failure cases:
```

If the user only asks a learning question, answer directly and include one tiny o1js example.

## Core Mina/o1js model

- o1js zkApps are written in TypeScript, but security comes from provable constraints, not normal TypeScript checks.
- A `SmartContract` method creates a proof and/or AccountUpdates.
- Mina verifies proofs and applies account updates. It does not run your whole app logic like an EVM.
- State is limited, so store commitments, counters or roots on-chain, not large data structures.
- `get()` reads a value inside the transaction context. If current-state correctness matters, use `getAndRequireEquals()` or `requireEquals()`.
- `Field` arithmetic is modular. For normal bounded integers, prefer `UInt32`, `UInt64`, `UInt8`, etc.
- `Provable.witness()` introduces a private value. A witness is unconstrained until you assert something about it.
- Use `Provable.if()` for runtime selection on provable values. Avoid side effects inside branches.
- Arrays in provable code must have fixed sizes.
- Events are public signals for UIs/indexers. Actions can be reduced inside provable code, but still need careful DoS and canonicalization handling.

## Coding workflow

1. Define the state model.
   - What fits in 8 fields?
   - What must be a Merkle root or commitment?
   - What state must be protected with a precondition?

2. Define the proof model.
   - What is public to the verifier?
   - What is private witness?
   - What must be asserted?
   - What is only auxiliary/debug data and not verified?

3. Define authorization.
   - Who can call each method?
   - Is caller identity checked by `this.sender`, signature, account permission, token owner logic or custom proof?
   - What AccountUpdates are created and who authorizes them?

4. Implement minimal safe code.
   - Use explicit assertions.
   - Prefer o1js types and helpers.
   - Keep provable functions pure and deterministic.
   - Avoid hidden mutation of JS objects when it affects proof logic.

5. Add tests before claiming it is done.
   - Happy path.
   - Wrong witness.
   - Unauthorized caller.
   - Stale state.
   - Replay.
   - Boundary values.
   - Malformed AccountUpdate or unexpected child update when relevant.

6. Output implementation notes.
   - What is proven.
   - What is not proven.
   - What is trusted.
   - Remaining risks.

## Bad vs good patterns

### State read without precondition

Bad:

```ts
const root = this.root.get();
// use root for a security-critical update
this.root.set(newRoot);
```

Good:

```ts
const root = this.root.getAndRequireEquals();
// or:
// const root = this.root.get();
// this.root.requireEquals(root);
this.root.set(newRoot);
```

Why it matters: without a precondition, the proof may not bind to the current on-chain state the way the developer expects.

### Witness without constraints

Bad:

```ts
const secret = Provable.witness(Field, () => userSecret);
this.commitment.set(Poseidon.hash([secret]));
```

Good:

```ts
const secret = Provable.witness(Field, () => userSecret);
const expectedCommitment = this.commitment.getAndRequireEquals();
Poseidon.hash([DOMAIN, secret]).assertEquals(expectedCommitment);
```

Why it matters: a witness is private, but not magically valid. It must be connected to public state or public input through assertions.

### JS condition on provable value

Bad:

```ts
if (amount.greaterThan(UInt64.from(100)).toBoolean()) {
  // unsafe in provable code
}
```

Good:

```ts
amount.assertLessThanOrEqual(UInt64.from(100));
```

Or for value selection:

```ts
const capped = Provable.if(
  amount.greaterThan(UInt64.from(100)),
  UInt64.from(100),
  amount
);
```

### Missing domain separation

Bad:

```ts
const nullifier = Poseidon.hash([secret]);
```

Good:

```ts
const DOMAIN_NULLIFIER = Field(1001);
const nullifier = Poseidon.hash([DOMAIN_NULLIFIER, appId, actionId, secret]);
```

### Field used for money amount

Bad:

```ts
const amount = Field(userAmount);
amount.assertGreaterThan(Field(0));
```

Good:

```ts
const amount = UInt64.from(userAmount);
amount.assertGreaterThan(UInt64.from(0));
```

Why it matters: `Field` is modular. Money and counters usually need bounded integer semantics.

## Standard method skeleton

Use this skeleton when adding a state-changing method:

```ts
@method async updateSomething(
  publicValue: Field,
  privateWitness: Field
) {
  // 1. Bind to current on-chain state.
  const oldRoot = this.root.getAndRequireEquals();

  // 2. Validate witness against public state/input.
  const computed = Poseidon.hash([DOMAIN, privateWitness]);
  computed.assertEquals(publicValue);

  // 3. Enforce business rule with provable assertions.
  publicValue.assertNotEquals(Field(0));

  // 4. Compute new state deterministically.
  const newRoot = Poseidon.hash([oldRoot, publicValue]);

  // 5. Write state.
  this.root.set(newRoot);

  // 6. Emit only non-sensitive public data.
  this.emitEvent('updated', newRoot);
}
```

Adapt the skeleton. Do not blindly copy it into production.

## What to inspect in a repo

When the user gives a repository, find and summarize:

```text
package.json o1js version:
SmartContract classes:
ZkProgram definitions:
State variables:
Methods:
Events:
Actions/reducers:
TokenContract usage:
AccountUpdate.create / createSigned / fundNewAccount usage:
Permissions.default / setPermissions usage:
Tests:
Deployment scripts:
Frontend prover code:
Backend/API code:
```

## Expected output for coding tasks

```text
Implementation summary
Files changed
Mina/o1js design notes
Code
Tests
Security notes
Open questions or assumptions
```

## Do not claim completion until

- state preconditions are handled;
- every witness has a meaningful constraint;
- authorization is explicit;
- public/private values are classified;
- negative tests are proposed or added;
- deployment permissions are at least mentioned if the code is deployable.
