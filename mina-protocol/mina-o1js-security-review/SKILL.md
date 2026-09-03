---
name: mina-o1js-security-review
description: Use when auditing, threat modeling, hardening, or reviewing Mina o1js zkApps, circuits, AccountUpdates, permissions, custom tokens, frontend prover flows, privacy, or deployment security.
---

# Mina o1js Security Review Skill

## Use when

Use this skill when the user asks for an audit, security review, vulnerability assessment, threat model, hardening plan or code review for a Mina/o1js zkApp.

This skill is defensive. Review only user-owned or authorized code.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Compatibility gate

Before a version-sensitive claim, record the target network, active protocol era, exact `o1js` and signer versions, wallet/CLI versions, endpoints, and the origin of verification keys and proof caches. Load `../mina-protocol-agent/references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js 3 migration rules. If the era is unknown, label the guidance unverified rather than guessing from package or endpoint names.

## Current high-risk review additions

Add these checks to every applicable audit:

- network era, signer era, transaction JSON, verification key, proof, and cache are mutually compatible;
- state/event/action/AccountUpdate limits are derived from the target era and boundary-tested;
- variable-length commitments use unambiguous length/domain binding;
- `TokenContract.deploy()` permission behavior is verified from the pinned version and on-chain state;
- wallet submission is inspected after proving and before signing;
- submitted, included, archive-indexed, safe, and final are not conflated;
- delegated authority binds mission, agent, app/network, tools/data, budget, expiry, replay control, and receipts.

Load `../mina-protocol-agent/references/playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md` and `../mina-protocol-agent/references/playbooks/DELEGATED_AUTHORIZATION_AND_PRIVACY.md` when those surfaces exist. Load `../mina-protocol-agent/references/playbooks/DEPLOYMENT_PROVENANCE_AND_REDEPLOY.md` whenever verification keys, permissions, state layout, deployments, upgrades, key rotation, or runtime configuration are in scope.

## Safety boundary

- Do not provide destructive exploitation against third-party systems.
- Do not exfiltrate secrets.
- If secrets appear in files, report minimal evidence and recommend immediate rotation.
- Do not ask the user to paste private keys, seed phrases or production secrets.

## Review principle

Mina/o1js security bugs often happen when a developer believes a normal TypeScript check is part of the proof, or when an AccountUpdate/permission path allows something the proof logic did not intend.

Always separate:

```text
Ordinary TS runtime check
Provable assertion
State precondition
Signature authorization
Permission authorization
Transaction/AccountUpdate structure
Frontend/backend trust assumption
```

## Audit workflow

### 1. Scope capture

Collect or infer:

- repository and commit hash;
- o1js version and zkApp CLI version;
- deployed addresses if any;
- target network;
- in-scope files;
- roles: deployer, admin, user, prover, frontend, backend, relayer, oracle, issuer, auditor;
- assets at risk: MINA, custom tokens, credentials, votes, reputation, private data, verification keys;
- high-risk features: tokens, reducers/actions, custom AccountUpdates, recursion, Merkle state, credentials, external data.

### 2. Architecture map

Produce this before findings:

```text
Contracts:
ZkPrograms:
State fields:
Methods and call graph:
Events/actions:
AccountUpdate tree per user flow:
Permissions and upgrade policy:
Frontend/prover/backend flow:
External dependencies:
```

### 3. Invariant list

Write project-specific invariants. Examples:

- only authorized users can update state;
- state transitions bind to the current on-chain state;
- every private witness is constrained to public input or on-chain commitment;
- nullifier can be used only once;
- token supply equals documented mint minus burn plus/minus pending operations;
- all token movements are approved by the intended token owner logic;
- every accepted action can be reduced without permanently bricking the contract;
- admin cannot silently replace verification key unless explicitly documented;
- private data does not appear in public inputs, events, actions, logs or analytics;
- frontend/backend cannot forge a proof or swap public inputs without detection.

### 4. Code review checklist

#### Provable constraints

- Security checks use `assertEquals`, `assertTrue`, `assertFalse`, range assertions or equivalent provable constraints.
- No witness is accepted without being tied to a public root, hash, signature, commitment or state value.
- Conditional logic uses `Provable.if()` correctly and avoids side effects inside branches.
- Fixed-size provable arrays are used where required.
- `Field` modular arithmetic is not used where bounded integer behavior is required.
- Hashes include domain separation.
- Signatures bind all required fields: app id, chain/network id if needed, contract address, action id, nonce/nullifier, amount, recipient, expiry.

#### State and preconditions

- Security-critical state reads use `getAndRequireEquals()` or `requireEquals()`.
- Account and network preconditions are explicit for balances, nonce, timestamp, slot, delegate or token state where relevant.
- Stale state and concurrent user flows are handled.

#### AccountUpdates

- Every AccountUpdate has the intended account, tokenId, authorization and balance change.
- Child AccountUpdates cannot inherit unintended token powers.
- `mayUseToken` and token ownership are understood and tested.
- `fundNewAccount`, `AccountUpdate.create`, `createSigned`, `approve`, custom send/mint/burn flows are reviewed.
- Transaction shape is stable enough for security assumptions.

#### Permissions and upgrades

- Permission matrix is documented.
- `setVerificationKey` and `setPermissions` are not left too loose.
- Least authority is applied.
- Upgrade path is either locked, proof-governed, multisig/timelock-governed or clearly documented as admin-trusted.

#### Actions/reducers

- Actions are public and not used for secret data.
- Reducer can process malformed or adversarial actions safely.
- Action type has canonical representation if needed.
- Queue growth, batching and griefing are considered.
- Reduction state cannot be permanently stuck by one bad action.

#### Privacy

- Public inputs, events, actions and state do not reveal private values accidentally.
- Backend and frontend do not log private witnesses.
- Nullifiers are domain-separated.
- Timing/IP/wallet metadata risks are documented when privacy claims are made.

#### Dependencies and devops

- o1js version is pinned.
- Deprecated APIs are flagged.
- Deployment scripts do not expose keys.
- CI does not print secrets or proofs containing sensitive auxiliary data.
- Frontend integrity and supply chain risks are considered.

## Finding format

```text
### [Severity] Title

Affected files:
Confidence: High / Medium / Low
Category:
Description:
Impact:
Why this happens in Mina/o1js:
Proof-of-concept or exploit sketch:
Recommended fix:
Regression test:
References:
```

## Severity guide

- Critical: direct theft, arbitrary mint/burn, arbitrary state update, verification key replacement, permanent fund lock for high-value assets.
- High: unauthorized privileged action, replay of important operation, broken nullifier, severe privacy leak, reducer bricking.
- Medium: missing precondition with realistic race risk, incomplete supply invariant, centralization risk not documented, unsafe upgrade process.
- Low: weak docs, test gaps, non-critical leakage, maintainability issues.
- Informational: hardening suggestion or architectural note.

## Required output

For every review, return:

1. Scope and assumptions.
2. Architecture map.
3. Role model.
4. Permission matrix.
5. AccountUpdate map.
6. Invariants.
7. Findings.
8. Test gaps.
9. Deployment risks.
10. Recommended next steps.

## Red flags

- `get()` without `requireEquals()` on state used in security logic.
- `Provable.witness()` without assertions tying it to public data.
- `Field` used as token amount without range/UInt wrapper.
- JS `if` depending on provable values.
- Admin can set verification key by signature without disclosure.
- Token manager approves arbitrary child updates.
- Reducer assumes all actions are honest.
- Events/actions contain PII or secrets.
- Tests only cover happy path.
- README claims privacy but frontend sends raw credential to backend.
