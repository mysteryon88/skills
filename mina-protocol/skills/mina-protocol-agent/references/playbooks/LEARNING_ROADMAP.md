# Mina/o1js Learning Roadmap

Use this roadmap with `mina-o1js-learning-coach`.

## Stage 0: Setup

Goal: run a generated zkApp locally.

Tasks:

- install Node.js and package manager used by the project;
- create or open a zkApp project;
- run tests;
- identify contract file, tests and deployment script.

Checkpoint:

```text
I can point to the SmartContract class, state fields and tests.
```

## Stage 1: Mina mental model

Learn:

- zkApp = UI + o1js contract;
- prover runs off-chain;
- Mina verifies proof and applies AccountUpdates;
- state is small;
- public inputs are visible, private witnesses are not.

Exercise:

```text
For a simple counter, classify what is public, private, proven and trusted.
```

## Stage 2: o1js types

Learn:

- `Field`, `Bool`, `UInt32`, `UInt64`;
- `Struct`;
- `Poseidon.hash`;
- `Signature`;
- fixed-size arrays.

Exercise:

```text
Write a function that proves knowledge of a secret whose Poseidon hash equals a public commitment.
```

Security checkpoint:

```text
Every witness must be constrained.
```

## Stage 3: SmartContract basics

Learn:

- `SmartContract`;
- `@state`;
- `@method`;
- `getAndRequireEquals()`;
- state updates.

Exercise:

```text
Build a commitment contract with init, update and read tests.
```

Security checkpoint:

```text
State reads that matter must have preconditions.
```

## Stage 4: Local testing

Learn:

- LocalBlockchain;
- deploy transaction;
- method transaction;
- proof disabled vs proof enabled;
- expected failure tests.

Exercise:

```text
Add wrong witness, unauthorized caller and stale state tests.
```

## Stage 5: AccountUpdates and permissions

Learn:

- transaction tree;
- authorizations;
- account permissions;
- verification keys;
- cross-contract calls.

Exercise:

```text
Draw the AccountUpdate tree for your latest transaction.
```

Security checkpoint:

```text
A deployment permission mistake can undo good code.
```

## Stage 6: Merkle/off-chain state

Learn:

- Merkle root on-chain;
- off-chain tree;
- membership and update witnesses;
- stale root issues;
- nullifier sets.

Exercise:

```text
Implement an allowlist membership proof with a Merkle root stored on-chain.
```

## Stage 7: ZkProgram

Learn:

- public input/output;
- private inputs;
- standalone proof generation;
- verification;
- recursion basics.

Exercise:

```text
Build a ZkProgram that proves a user has a valid signed credential without revealing the raw credential.
```

## Stage 8: Actions/reducers

Learn:

- actions are public;
- reducers process action history;
- concurrent update pattern;
- archive node assumptions.

Exercise:

```text
Model a voting or queue system with actions and write a bad-action test.
```

## Stage 9: Custom tokens

Learn:

- TokenContract;
- token manager;
- mint/burn/send;
- approveBase;
- supply invariants.

Exercise:

```text
Review or build a token where unauthorized mint fails and total supply invariant is tested.
```

## Stage 10: Production readiness

Learn:

- verification key policy;
- permission matrix;
- key management;
- frontend prover UX;
- privacy leakage map;
- audit report.

Exercise:

```text
Write a deployment readiness checklist for your app.
```
