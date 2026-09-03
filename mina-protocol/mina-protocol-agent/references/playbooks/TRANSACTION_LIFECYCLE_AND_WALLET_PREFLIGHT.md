# Mina Transaction Lifecycle and Wallet Preflight

Use this playbook for transaction construction, Auro or other wallet integration, relayers, explicit fee-payer flows, Zeko operations, archive/event synchronization, and status UX.

## Do not collapse the lifecycle into "sent"

Track these states separately:

```text
constructed
proved
serialized
signed
broadcast
accepted by endpoint or sequencer
included on the live chain
visible through a live query
indexed by an archive or event service
safe at the chosen depth
canonically final for the product's policy
```

The exact transitions differ between Mina L1 and Zeko. A transaction hash proves only that an identifier was produced, not that every later state has happened.

## Construction gate

Before proving or signing, inspect the transaction shape:

- fee-payer public key, fee, nonce, memo, and network/era;
- all root and child AccountUpdates;
- `callDepth` and parent/child relationships;
- touched accounts and token IDs;
- balance changes;
- state updates and preconditions;
- authorization kind for each update;
- permission required for each update;
- expected final state and emitted events/actions.

Fail closed when an expected AccountUpdate subtree is missing, duplicated, reordered in a security-relevant way, or authorized differently than the method specification.

## Build, prove, sign, send

Preferred order:

1. Fetch current account, nonce, network state, and required witnesses.
2. Build with the real compiled contract class and explicit network configuration.
3. Inspect transaction shape before proof generation.
4. Call `prove()` when a proof authorization is required.
5. Serialize only after proof generation if the wallet/API consumes the proved JSON.
6. Sign only keys controlled by the current component.
7. Let the wallet sign the wallet-owned fee payer; never move a user private key to the backend to simplify integration.
8. Re-inspect the final JSON and commitments before broadcast.
9. Broadcast once and persist a recoverable journal entry.
10. Poll the appropriate live and historical surfaces with bounded retries.

## Auro and browser-wallet preflight

Before `window.mina.sendTransaction(...)` or an equivalent wallet call:

- wallet network matches the app's target network;
- displayed network, chain/era, contract address, token ID, and app version match runtime config;
- fee payer is the intended wallet account;
- fee is an integer in nanomina and follows product policy;
- current fee-payer nonce is known;
- pending fee-payer traffic or nonce races are surfaced;
- transaction JSON contains the expected proved updates and authorization kinds;
- on-chain permissions permit the intended path;
- no private witness or secret is present in JSON, logs, analytics, or error reports.

A wallet confirmation timeout is not automatically a proving bug. Classify network mismatch, stale nonce, unsupported transaction format, wallet ownership, authorization-kind mismatch, and pending-transaction contention separately.

## Fee payer and nonce safety

- Fetch a fresh nonce immediately before construction when the flow is latency-sensitive.
- Serialize concurrent sends per fee payer or use an explicit nonce reservation strategy.
- Distinguish the fee-payer nonce from zkApp account nonce preconditions.
- On a nonce race, rebuild from fresh chain state; do not mutate signed JSON in place.
- Bound retries and make each retry idempotent from the user's point of view.
- Never remove a nonce precondition merely because a project-specific demo did so. Any deviation from o1js defaults needs protocol-specific justification, a threat analysis, and a regression test.
- `useFullCommitment` and other fee-payer settings change what a signature binds. Verify the exact installed API and signer era before use.

## Error classification

Use separate buckets:

```text
shape error
state/precondition error
proving error
authorization-kind error
signing or signer-era error
wallet ownership error
nonce/mempool race
broadcast/endpoint error
inclusion timeout
archive/indexing lag
finality/reorg issue
```

Do not fix one bucket by weakening a different security boundary.

## Mina L1 status policy

For products that need more than inclusion:

- query transaction depth using the supported o1js API for the installed version;
- define the product's safe depth and canonical-finality policy explicitly;
- handle dropped or reorganized transactions;
- keep UI states honest: submitted, included, safe, final, failed, replaced, or unknown;
- avoid final business effects from a wallet hash alone.

## Zeko live, archive, and DA split

Use the endpoint that matches the question:

- live Zeko/sequencer endpoint for current config, current state, and request lifecycle;
- archive endpoint for historical events, actions, and backfills;
- DA surfaces for availability status and publication receipts;
- Mina L1 surfaces when the product requires L1 anchoring or finality.

Do not assume live and archive endpoints are synchronized. For witness generation, compare event-derived state with current on-chain roots. Keep expensive backfills and full event rebuilds out of request-time transaction construction.

## Event-derived state

When local state is reconstructed from events:

1. Persist an event cursor and source identity.
2. Verify ordering, duplicates, gaps, and reorg behavior.
3. Compare reconstructed roots with live account roots.
4. Keep wallet activity separate from authoritative event-confirmed state.
5. Treat archive lag as an indexing condition, not automatic proof failure.
6. Refuse witness generation when local state and live root disagree unless a documented recovery path reconciles them.

## Recoverable transaction journal

Persist enough non-secret metadata to resume safely:

```text
client request id
network and era
source commit/app version
fee payer public key
nonce and fee
contract addresses/token ids
transaction hash if available
transaction-shape digest
proof/VK identifiers
current lifecycle state
last endpoint response class
retry count and timestamps
```

Never store private keys or raw witnesses in the journal.

## Required tests

- wrong wallet network is rejected before signing;
- wrong fee payer is rejected;
- pending nonce collision triggers bounded rebuild, not JSON mutation;
- missing or unexpected AccountUpdate subtree fails closed;
- proof-required update cannot be sent unproved;
- wallet-owned fee payer is not signed by the backend;
- signer-era mismatch is detected;
- submitted but not included remains a non-final UI state;
- archive lag does not overwrite authoritative live state;
- reorg or dropped transaction moves to an explicit recoverable state;
- private witness data does not appear in payloads or logs.
