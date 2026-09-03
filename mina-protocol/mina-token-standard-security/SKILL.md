---
name: mina-token-standard-security
description: Use when building or reviewing Mina custom tokens, fungible tokens, stablecoins, wrapped assets, token managers, mint or burn authorization, tokenId handling, or token accounting flows.
---

# Mina Token Standard Security Skill

## Use when

Use this skill when building or reviewing Mina custom tokens, fungible tokens, stablecoins, wrapped assets, token admin contracts, bridge tokens, token-gated apps or accounting flows.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Compatibility gate

Before a version-sensitive claim, record the target network, active protocol era, exact `o1js` and signer versions, wallet/CLI versions, endpoints, and the origin of verification keys and proof caches. Load `../mina-protocol-agent/references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js 3 migration rules. If the era is unknown, label the guidance unverified rather than guessing from package or endpoint names.

## Current token deployment and transaction checks

Do not assume `TokenContract.deploy()` resets all permissions. Verify the pinned o1js behavior, custom permissions set in `init()`, the resulting `access` permission, and on-chain state after deployment. Derive AccountUpdate/segment limits from the target era and test complex child-update trees at the boundary. For wallet, relayer, fee-payer, and finality behavior, load `../mina-protocol-agent/references/playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md`. Load `../mina-protocol-agent/references/playbooks/DEPLOYMENT_PROVENANCE_AND_REDEPLOY.md` when token permissions, verification keys, state layout, manager keys, or deployed configuration change.

## Token mental model

Mina has native support for custom tokens at the account/update level. A token manager smart contract controls the rules for minting, burning and approving transfers of its token. Do not treat Mina tokens as ERC-20 clones.

## First output

Before code or findings, produce:

```text
Token purpose:
Token manager contract:
Token id source:
Admin roles:
Mint rules:
Burn rules:
Transfer approval rules:
Pause/freeze model:
Supply model:
Upgrade model:
Wallet/indexer assumptions:
```

## High-risk areas

- arbitrary mint;
- arbitrary burn;
- broken transfer approval;
- total supply mismatch;
- unintended child AccountUpdate approval;
- wrong tokenId;
- unsafe `mayUseToken` behavior;
- central admin can rug through mint/upgrade/pause;
- events do not match actual balance changes;
- bridge mint/burn not tied to verified source-chain event;
- stablecoin issuer/auditor assumptions undocumented.

## Review checklist

### 1. Supply model

Document:

```text
max supply:
current supply source:
mint source of truth:
burn source of truth:
pending mint/burn queues:
bridge escrow assumptions:
```

Check:

- all mint paths update/emit/document supply;
- burn cannot exceed balance;
- temporary supply increase cannot be externally exploited;
- no flash-mint behavior unless explicitly designed;
- supply invariant has tests.

### 2. Authorization

Check every privileged path:

- mint;
- burn;
- pause/unpause;
- blacklist/freeze if any;
- admin transfer;
- upgrade;
- rescue funds;
- bridge finalization;
- oracle/issuer update.

For each, identify the actual enforcement:

```text
proof constraint / sender / signature / permission / governance / trusted backend
```

### 3. AccountUpdate and tokenId

Inspect:

- `TokenContract` subclass;
- `approveBase()`;
- `approveAccountUpdate()` and `approveAccountUpdates()`;
- `internal.mint`, `internal.burn`, `internal.send`;
- child AccountUpdates;
- `mayUseToken` and token owner assumptions;
- balanceChange signs and overwritten values;
- account creation fees for token accounts.

### 4. Permissions

Build a token-specific permission matrix:

```text
editState:
send:
receive:
setPermissions:
setVerificationKey:
setTokenSymbol:
access:
setDelegate:
incrementNonce:
```

Flag loose permissions that let an admin or attacker bypass token logic.

### 5. Reducers/actions

If token operations use actions:

- accepted action must always be reducible or safely skipped;
- malformed action cannot brick future reductions;
- queue growth and batching are bounded;
- user cannot create free pending claims;
- event/action data is not treated as private.

### 6. User safety and disclosure

Ask:

- Can funds be locked?
- Can admin pause forever?
- Can admin mint unlimited supply?
- Can issuer censor transfers?
- Is upgradeability disclosed?
- Are wallets/indexers able to understand the token correctly?

## Bad vs good examples

### Approving child updates too broadly

Bad:

```ts
@method async approveBase(forest: AccountUpdateForest) {
  // approves without checking balance changes or allowed shape
  this.approve(forest);
}
```

Good pattern:

```ts
@method async approveBase(forest: AccountUpdateForest) {
  // example policy only: no net token balance change for arbitrary children
  this.checkZeroBalanceChange(forest);
}
```

For custom policies, inspect every child update and assert total changes.

### Mint without admin binding

Bad:

```ts
@method async mint(to: PublicKey, amount: UInt64) {
  this.internal.mint({ address: to, amount });
}
```

Good pattern:

```ts
@state(Field) mintNonce = State<Field>();

@method async mint(to: PublicKey, amount: UInt64, adminSig: Signature) {
  const admin = this.admin.getAndRequireEquals();
  const nonce = this.mintNonce.getAndRequireEquals();
  const tokenId = this.deriveTokenId();
  amount.assertGreaterThan(UInt64.from(0));
  adminSig.verify(admin, [
    DOMAIN_MINT,
    ...this.address.toFields(),
    tokenId,
    nonce,
    ...to.toFields(),
    ...amount.toFields(),
  ]).assertTrue();
  this.mintNonce.set(nonce.add(1));
  this.internal.mint({ address: to, amount });
}
```

Initialize `mintNonce` in `init()`. The nonce update and mint are part of the same zkApp transaction, so either both commit or neither does. Add an expiry or a contract-managed nullifier set when the authorization policy needs them.

## Required tests

- random user cannot mint;
- random user cannot burn another user's balance;
- transfer approval rejects unexpected child update;
- wrong tokenId does not affect this token;
- zero amount behavior is intentional;
- max amount does not overflow supply model;
- total supply invariant holds after random sequences;
- admin upgrade/pause behavior matches documentation;
- events reflect actual operation.

## Output format

```text
Token architecture
Supply invariants
Role matrix
Permission matrix
AccountUpdate map
Findings or implementation plan
Required tests
User-facing disclosure notes
```
