---
name: mina-o1js-debugging-performance
description: Use when debugging or optimizing Mina o1js compile, prove, transaction, AccountUpdate, permission, witness, constraint count, browser proving, worker, memory, or performance issues.
---

# Mina o1js Debugging and Performance Skill

## Use when

Use this skill when the user has failing proofs, slow proving, compile errors, transaction failures, state mismatch, frontend prover issues or confusing o1js behavior.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Debugging rule

Separate three failure classes:

```text
TypeScript/runtime error
Proof/constraint error
Mina transaction/AccountUpdate/permission error
```

Do not debug all three at once. Reduce to the smallest failing case.

## First output

```text
Failure type:
Where it fails: compile / prove / sign / send / fetch / frontend
Minimal reproduction:
o1js version:
Proofs enabled:
Contract/program involved:
Inputs:
State before:
Expected state after:
```

## Debug workflow

### 1. Compile-time/circuit issues

Check:

- dynamic arrays in provable code;
- JS values used where provable types are expected;
- unsupported branching on provable values;
- witness shape changes between compile and prove;
- methods not async when expected by current style;
- imported API from wrong o1js version.

### 2. Proof failures

Check:

- assertion actually fails;
- witness callback returns unexpected value;
- hash field order/domain mismatch;
- signature message mismatch;
- Merkle witness generated for different root/index;
- range check fails;
- public input differs from frontend/backend expectation.

### 3. Transaction failures

Use `mina-accountupdate-transaction-debugger`.

Check:

- missing proof;
- missing signature;
- missing `fundNewAccount`;
- wrong network/address;
- stale state precondition;
- wrong token id;
- permission mismatch;
- verification key mismatch.

### 4. Performance issues

Check:

- proof generated in browser vs Node/backend;
- repeated compile in hot path;
- large fixed arrays;
- expensive hash or signature loops;
- unnecessary recursion depth;
- too many AccountUpdates;
- no caching of compiled artifacts;
- frontend bundle too heavy.

Use constraint analysis for heavy pure provable functions when possible.

## Common fixes

- replace `get()` with `getAndRequireEquals()` for state mismatch bugs;
- use `UInt64`/`UInt32` instead of `Field` for bounded values;
- include domain/action/recipient/nonce in signature message;
- use fixed `Provable.Array` size;
- precompute off-circuit data, but prove the relation in-circuit;
- move heavy proof generation out of blocking UI path;
- compile once, prove many times where architecture allows;
- add a minimal failing test before changing logic.

## Output format

```text
Likely failure class
Minimal reproduction
Root cause hypothesis
Fix
Regression test
Performance notes
```
