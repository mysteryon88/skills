# o1js Code Patterns

These are patterns for an agent to adapt, not production-ready copy-paste code.

## Commitment check

```ts
const DOMAIN_COMMITMENT = Field(1000);

function commitment(secret: Field): Field {
  return Poseidon.hash([DOMAIN_COMMITMENT, secret]);
}

// inside method
const expected = this.commitment.getAndRequireEquals();
const secret = Provable.witness(Field, () => userSecret);
commitment(secret).assertEquals(expected);
```

## Signature binding pattern

```ts
const DOMAIN_ADMIN_ACTION = Field(2000);

const message = [
  DOMAIN_ADMIN_ACTION,
  ...this.address.toFields(),
  actionId,
  ...recipient.toFields(),
  amount.value,
  nonce,
  expiry,
];

adminSignature.verify(adminPublicKey, message).assertTrue();
```

## Merkle update pattern

```ts
const oldRoot = this.root.getAndRequireEquals();

const oldLeaf = Poseidon.hash([DOMAIN_LEAF, ...owner.toFields(), oldValue]);
witness.calculateRoot(oldLeaf).assertEquals(oldRoot);

const newLeaf = Poseidon.hash([DOMAIN_LEAF, ...owner.toFields(), newValue]);
const newRoot = witness.calculateRoot(newLeaf);

this.root.set(newRoot);
```

## Nullifier pattern

```ts
const nullifier = Poseidon.hash([
  DOMAIN_NULLIFIER,
  appId,
  actionId,
  epoch,
  userSecret,
]);

// Then prove nullifier unused and mark it used via state/root update.
```

## Safe conditional selection

```ts
const selected = Provable.if(condition, valueIfTrue, valueIfFalse);
```

Avoid mutating variables inside `Provable.if()` branches.

## State precondition pattern

```ts
const current = this.someState.getAndRequireEquals();
// use current
this.someState.set(next);
```

## UInt amount pattern

```ts
const amount = UInt64.from(rawAmount);
amount.assertGreaterThan(UInt64.from(0));
amount.assertLessThanOrEqual(maxAmount);
```

## Event privacy pattern

Good events contain public facts only:

```ts
this.emitEvent('updated-root', newRoot);
```

Avoid raw private data:

```ts
// bad
this.emitEvent('credential', credentialField);
```
