---
name: mina-o1js-circuit-design-patterns
description: Use when designing or reviewing o1js circuit constraints, witnesses, assertions, hashes, signatures, Merkle checks, provable conditionals, fixed-size arrays, or circuit data models.
---

# Mina o1js Circuit Design Patterns Skill

## Use when

Use this skill when designing or reviewing o1js constraint logic: witnesses, assertions, hashes, signatures, Merkle proofs, range checks, conditional logic, fixed arrays and efficient provable data structures.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Core principle

A circuit proves only what is constrained. Private data, helper functions and TypeScript logic do not matter unless they create provable constraints or bind to public input/output/state.

## First output

```text
Circuit goal:
Public inputs:
Private witnesses:
Public outputs:
Assertions:
Hash/signature domains:
Range checks:
Data structure sizes:
Constraint/performance risks:
```

## Pattern checklist

### Witness pattern

For every witness:

- what value does prover choose?
- why is it allowed to be private?
- what constrains it?
- what public value/state does it bind to?
- can wrong witness pass?

### Hash pattern

Use domain separation:

```ts
const h = Poseidon.hash([DOMAIN, appId, actionId, value1, value2]);
```

Check field order, schema version and packing.

### Signature pattern

A signature should bind all values that matter:

```text
domain, contract address, network/app id, action, sender/subject, recipient, amount, nonce/nullifier, expiry
```

### Range pattern

Use bounded integer types for counters and amounts:

```ts
const amount = UInt64.from(rawAmount);
amount.assertGreaterThan(UInt64.from(0));
```

Do not rely on `Field` arithmetic for normal integer semantics unless you explicitly handle modular behavior.

### Conditional logic pattern

Use JS `if` only for compile-time/static structure. Use `Provable.if()` to select between provable values. Avoid side effects inside conditional branches.

### Fixed array pattern

Provable arrays need fixed sizes. Make max sizes explicit and document why they are safe.

### Merkle pattern

A correct Merkle update normally proves:

- old leaf belongs to old root;
- old root equals on-chain state or public input;
- new leaf is computed from constrained values;
- new root is computed with same witness/path;
- owner/index/key is bound.

## Common design mistakes

- witness is only hashed into a new state but never checked against old state;
- public output omits a value the verifier/contract trusts later;
- auxiliary output is treated as verified;
- signature message does not include recipient or contract address;
- hash has no domain separation;
- `Field` used for amount without UInt/range;
- provable array length is assumed dynamic;
- `Provable.if` branches mutate variables.

## Output format

```text
Circuit design summary
Constraint map
Bad patterns found
Recommended pattern
Code sketch
Tests to prove constraints are active
Constraint/performance notes
```
