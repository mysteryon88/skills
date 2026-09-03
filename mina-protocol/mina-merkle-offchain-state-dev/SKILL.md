---
name: mina-merkle-offchain-state-dev
description: Use when designing, implementing, testing, or reviewing Mina Merkle trees, off-chain state commitments, membership proofs, update proofs, nullifier sets, or root transition logic.
---

# Mina Merkle and Off-chain State Development Skill

## Use when

Use this skill when building or reviewing Mina apps that store commitments, Merkle roots, indexed maps, off-chain state, membership proofs, allowlists, credentials, nullifier sets or private balances.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Compatibility gate

Before a version-sensitive claim, record the target network, active protocol era, exact `o1js` and signer versions, wallet/CLI versions, endpoints, and the origin of verification keys and proof caches. Load `../mina-protocol-agent/references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js 3 migration rules. If the era is unknown, label the guidance unverified rather than guessing from package or endpoint names.

## Versioned commitments and state synchronization

Version every leaf, node, batch, and public-root schema. Use fixed-length `Poseidon.hash()` only for fixed schemas; use `Poseidon.hashAnyLength()` for genuinely variable-length input with explicit domain and length binding. When events rebuild local state, track cursor/source identity, duplicates, gaps, archive lag, and reorg policy, and compare the reconstructed root with the live account root before producing a witness. Load `../mina-protocol-agent/references/playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md` for live/archive/finality separation.

## Mental model

Mina on-chain state is intentionally small. Real apps often store a root or commitment on-chain and keep the larger data structure off-chain. The proof must show that the off-chain update is valid relative to the old on-chain commitment and produces the new commitment.

## First output

```text
State structure:
On-chain commitment/root:
Off-chain data owner:
Leaf schema:
Index/key schema:
Membership proof type:
Update rule:
Nullifier/replay model:
Data availability assumption:
Recovery plan if off-chain data is lost:
```

## Design checklist

### Leaf schema

Define a fixed schema:

```text
leaf = Poseidon.hash([DOMAIN_LEAF, userKey, value, nonce, ...])
```

Check:

- domain separation;
- stable field order;
- fixed encoding;
- no ambiguous packing;
- values are range-checked before hashing;
- leaf includes owner/index when needed.

### Membership proof

For every update:

- old root is read with `getAndRequireEquals()`;
- witness computes old root from old leaf;
- old root equals on-chain root;
- new leaf is computed from constrained inputs;
- witness computes new root;
- new root is written to state;
- index/key cannot be swapped by attacker.

### Nullifier set

For one-time actions:

- nullifier is domain-separated;
- non-membership or unused-state proof is verified;
- nullifier is inserted/marked used;
- repeated use fails;
- app/domain/poll/epoch binding is explicit.

### Off-chain storage

Document:

```text
Who stores the tree:
How users get witnesses:
How witnesses are verified client-side:
How data is reconstructed from events/actions if possible:
What happens if server lies or goes offline:
```

### Concurrency

Check:

- two users updating same root at the same time;
- stale witness behavior;
- actions/reducers or batching if concurrent updates are required;
- retry flow for users.

## Common bad patterns

### Root update without old root binding

Bad:

```ts
const oldRoot = this.root.get();
const newRoot = witness.calculateRoot(newLeaf);
this.root.set(newRoot);
```

Good:

```ts
const oldRoot = this.root.getAndRequireEquals();
witness.calculateRoot(oldLeaf).assertEquals(oldRoot);
const newRoot = witness.calculateRoot(newLeaf);
this.root.set(newRoot);
```

### Leaf does not bind owner

Bad:

```ts
const leaf = Poseidon.hash([balance]);
```

Good:

```ts
const leaf = Poseidon.hash([DOMAIN_BALANCE_LEAF, ...owner.toFields(), balance.value]);
```

### Index not constrained

Bad:

```ts
// witness proves some leaf exists, but user chooses recipient separately
```

Good:

```ts
// leaf binds owner/index/key, and transfer proof asserts it matches sender/recipient semantics
```

## Required tests

- valid membership proof succeeds;
- wrong leaf fails;
- wrong index/key fails;
- old root replay fails after update;
- new root equals expected local tree update;
- stale witness gives clear failure;
- server-provided wrong witness fails;
- data availability/reconstruction story is documented.

## Output format

```text
State design
Leaf and hash schema
Proof/update flow
Concurrency model
Data availability assumptions
Code
Tests
Security notes
```
