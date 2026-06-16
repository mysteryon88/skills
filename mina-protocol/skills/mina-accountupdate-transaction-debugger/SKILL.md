---
name: mina-accountupdate-transaction-debugger
description: Use when debugging Mina transactions, AccountUpdates, proof or signature authorization, token transfers, cross-contract calls, permissions, balance changes, or confusing transaction failures.
---

# Mina AccountUpdate and Transaction Debugger Skill

## Use when

Use this skill when debugging Mina transactions, AccountUpdates, proof/signature authorization, token transfers, cross-contract calls, permissions, balance changes or confusing transaction failures.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Core idea

AccountUpdates are the real language of Mina transactions. Most confusing Mina bugs become clearer when you draw the transaction tree.

## First output

For any flow, produce:

```text
Transaction sender:
Fee payer:
Root AccountUpdates:
Child AccountUpdates:
Touched accounts:
Token ids:
Balance changes:
State updates:
Preconditions:
Authorization per update:
Permissions required:
Expected final state:
```

## Debug workflow

### 1. Reproduce minimally

- Use LocalBlockchain first.
- Reduce to one transaction and one method.
- Turn proofs off for shape/debug, then add proof-enabled smoke test.
- Log transaction JSON only if it does not contain secrets.

### 2. Draw AccountUpdate tree

For every update:

```text
Account:
TokenId:
Authorization: proof/signature/none
BalanceChange:
State updates:
Preconditions:
MayUseToken:
Children:
```

### 3. Check permissions

For each touched account, ask:

- Is this update allowed by account permissions?
- Does it need a proof, signature or impossible permission?
- Is `setVerificationKey`/`setPermissions` unexpectedly involved?
- Is token owner approval required?

### 4. Check state preconditions

- Is current state required?
- Is `getAndRequireEquals()` used?
- Are network/account preconditions too strict or too loose?
- Could stale local state cause failure?

### 5. Check token semantics

- Does AccountUpdate use the expected token id?
- Is token owner approving child updates?
- Are balance changes signed correctly?
- Are account creation fees handled?

### 6. Check proof/signature separation

- Which update is authorized by proof?
- Which update is authorized by signature?
- Does transaction sender equal assumed caller?
- Can relayer submit on behalf of user safely?

## Common failure patterns

- transaction has extra AccountUpdate requiring a signature not provided;
- zkApp account permission requires proof but method was not proved;
- state changed before transaction was submitted;
- wrong token id;
- missing `fundNewAccount` for new account;
- child AccountUpdate not approved by token owner;
- verification key mismatch after rebuild;
- frontend uses wrong network or contract address;
- permission matrix differs from local assumptions.

## Useful debug outputs

Ask coding agents to produce:

```text
- transaction.toJSON() with secrets redacted
- permission matrix from chain account data
- final account state before/after
- touched account list
- AccountUpdate tree diagram
- minimal failing test
```

## Transaction tree template

```text
Tx
├─ Fee payer: <public key>
├─ AU-1: <account>, token=<id>, auth=<proof/signature/none>
│  ├─ state: <changes>
│  ├─ balanceChange: <amount>
│  └─ children:
│     └─ AU-1.1: <account>, token=<id>, auth=<...>
└─ AU-2: ...
```

## Output format

```text
Likely cause
AccountUpdate tree
Permission/precondition mismatch
Minimal fix
Regression test
Remaining unknowns
```
