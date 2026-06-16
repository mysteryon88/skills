---
name: mina-privacy-credentials-security
description: Use when designing, implementing, testing, or reviewing Mina privacy flows, credentials, zkKYC, selective disclosure, nullifiers, unlinkability, issuer signatures, or private-data leakage.
---

# Mina Privacy and Credentials Security Skill

## Use when

Use this skill when building or auditing private credentials, zkKYC, attestations, proof of membership, proof of age, private voting, private reputation, selective disclosure or nullifier-based applications on Mina.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Core principle

A proof can hide a witness, but the full application can still leak identity through public inputs, events, actions, logs, backend APIs, frontend analytics, timing, IP metadata, wallet behavior or reused nullifiers.

## First output

Produce a data map before design or findings:

```text
Value | Public on-chain | Public proof input | Private witness | Frontend | Backend | Wallet | Logs/analytics | Retention
```

## Privacy claim matrix

For every user-facing claim, verify actual leakage:

```text
Claim:
What chain sees:
What backend sees:
What frontend sees:
What issuer sees:
What relayer sees:
Linkability risk:
Remaining caveat:
```

## Credential model checklist

### Issuer

- issuer public key is constrained;
- issuer signature binds all credential fields;
- issuer key rotation is defined;
- malicious issuer risk is documented;
- issuer does not learn unnecessary verifier/app usage if privacy claim requires that.

### Credential

- credential schema is fixed and versioned;
- expiry is constrained;
- revocation model exists;
- credential commitment has domain separation;
- selective disclosure fields are constrained correctly;
- undisclosed fields cannot be swapped.

### Nullifier

A good nullifier usually binds:

```text
domain/app id
action id or circuit id
user secret or credential secret
contract address or network if needed
round/epoch/poll id if needed
```

Check:

- nullifier cannot be reused for the same action;
- nullifier is not linkable across unrelated apps unless intended;
- nullifier is not derived from low-entropy PII;
- nullifier is stored/checked on-chain or in a verifiable commitment structure.

### Replay and freshness

- proof includes current app domain;
- proof binds recipient/action/amount when relevant;
- proof has expiry or epoch if needed;
- old public input cannot be replayed with new transaction details;
- relayer cannot alter outputs.

### Data leakage

Check that private data is not in:

- public inputs;
- state fields;
- events;
- actions;
- transaction memo;
- frontend console logs;
- backend request body;
- analytics;
- crash reports;
- browser localStorage if not encrypted/justified;
- screenshots or debug UI.

## Common bad patterns

### Nullifier too broad

Bad:

```ts
const nullifier = Poseidon.hash([secret]);
```

This links the user everywhere.

Better:

```ts
const nullifier = Poseidon.hash([
  DOMAIN_NULLIFIER,
  appId,
  actionId,
  epoch,
  secret,
]);
```

### Signature does not bind app/action

Bad:

```ts
issuerSig.verify(issuer, [age]).assertTrue();
```

Better:

```ts
issuerSig.verify(issuer, [
  DOMAIN_CREDENTIAL,
  schemaVersion,
  subjectCommitment,
  ageLowerBound,
  expiry,
]).assertTrue();
```

Then the app-specific proof should bind its own public inputs and nullifier.

### Privacy claim ignores backend

Bad claim:

```text
No one sees your passport data.
```

But backend receives raw passport data to generate proof.

Better design:

```text
Proof is generated locally or with a clearly disclosed trusted prover.
Backend receives only proof and public inputs.
```

## Required tests

- invalid issuer signature fails;
- wrong credential field fails;
- expired credential fails;
- revoked credential fails if revocation is in scope;
- reused nullifier fails;
- same user can create unlinkable proofs for different domains if intended;
- relayer cannot change recipient/action after proof generation;
- logs/events/actions contain no raw PII;
- frontend does not send witness to backend unless explicitly trusted.

## Output format

```text
Data leakage map
Privacy claim matrix
Credential trust model
Nullifier/domain model
Circuit findings
Frontend/backend findings
Regression tests
User-facing caveats
```
