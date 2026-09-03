---
name: mina-frontend-prover-ux
description: Use when designing, implementing, reviewing, or debugging Mina frontend prover flows, wallet UX, local proving, worker performance, privacy boundaries, or transaction submission UX.
---

# Mina Frontend Prover and UX Skill

## Use when

Use this skill when building or reviewing a Mina zkApp frontend, browser prover flow, wallet integration, backend prover, API flow, static hosting setup or privacy-sensitive UI.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Compatibility gate

Before a version-sensitive claim, record the target network, active protocol era, exact `o1js` and signer versions, wallet/CLI versions, endpoints, and the origin of verification keys and proof caches. Load `../mina-protocol-agent/references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js 3 migration rules. If the era is unknown, label the guidance unverified rather than guessing from package or endpoint names.

## Wallet and status preflight

Load `../mina-protocol-agent/references/playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md`. Before opening a wallet confirmation, verify network/era, fee payer, fresh nonce and pending traffic, integer nanomina fee, proved authorization kinds, deployed permissions, and the final serialized AccountUpdate tree. The wallet signs wallet-owned keys only. Display submitted, included, indexed, safe, final, failed, replaced, and unknown as distinct states; a transaction hash is not a finality signal.

The native prover is a Node.js path, not a browser substitute. Keep browser/WASM worker and server/native-prover trust boundaries explicit.

## Core principle

The proof can be cryptographically sound while the app still fails users through bad UX, private data leakage, wrong network config, malicious frontend updates or trusted backend assumptions.

## First output

```text
Where proof is generated:
What data user enters:
What data leaves browser:
What wallet signs:
What backend sees:
What public inputs are submitted:
What network/address is configured:
What logs/analytics exist:
```

## Frontend/prover checklist

### Network and address safety

- correct Mina network endpoint;
- correct archive endpoint if events/actions are fetched;
- correct contract address and token id;
- clear testnet/mainnet display;
- frontend build tied to deployed verification key/source version;
- protection against stale config.

### Private data handling

- private witness stays local unless trusted backend is explicit;
- no witness in console logs;
- no witness in analytics or crash reports;
- no raw credential in localStorage unless encrypted/justified;
- no private key/seed phrase requests;
- file uploads and screenshots do not leak secrets.

### Proof generation UX

- compile/prove progress shown;
- cancellation/retry path;
- stale witness/root error explained;
- proof generation time measured;
- mobile/browser limitations documented;
- fallback backend prover trust model documented if used.

### Wallet/signature binding

- user sees what they sign;
- signature message binds app domain, contract address, action, recipient, amount, nonce/nullifier and expiry when relevant;
- relayer cannot change public inputs after user approval;
- transaction sender assumptions are tested.

### Backend prover/API

If backend proves:

- backend trust model is explicit;
- API does not store private witness longer than needed;
- request logs redacted;
- rate limits exist;
- prover output is verified client-side or on-chain;
- backend cannot swap public inputs without detection.

### Frontend integrity

- static hosting/CDN risk documented;
- release hashes or reproducible builds considered;
- dependencies pinned;
- wallet package and GraphQL endpoint dependencies reviewed;
- user can verify contract address and app version.

## Common bad patterns

### Hidden backend trust

Bad:

```text
User uploads passport to backend, backend generates proof, website says “fully private”.
```

Better:

```text
Generate proof locally, or clearly disclose backend prover trust and data retention.
```

### Signature does not bind transaction

Bad:

```ts
Signature.create(userKey, [Field(1)]);
```

Better:

```ts
Signature.create(userKey, [
  DOMAIN_ACTION,
  ...contractAddress.toFields(),
  actionId,
  ...recipient.toFields(),
  amount.value,
  nonce,
  expiry,
]);
```

### Wrong network accident

Bad:

```ts
const zkAppAddress = '...'; // no network check
```

Better:

```text
Display network, contract address, token id and app version in UI.
Reject transaction if wallet network does not match config.
```

## Required tests / checks

- frontend submits to correct network/address;
- wrong network is rejected or clearly warned;
- witness does not appear in logs;
- relayer cannot change recipient/amount;
- stale root gives user-friendly retry;
- proof generation works in supported browsers;
- backend prover redacts logs if used.

## Output format

```text
Frontend/prover architecture
Data leakage map
Wallet/signature binding
UX risks
Backend trust assumptions
Code changes
Tests/checks
Release checklist
```
