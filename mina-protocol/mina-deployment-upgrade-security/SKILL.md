---
name: mina-deployment-upgrade-security
description: Use when preparing, reviewing, or hardening Mina zkApp deployments, upgrade policies, verification keys, permission matrices, key management, network configuration, or release procedures.
---

# Mina Deployment and Upgrade Security Skill

## Use when

Use this skill when deploying a Mina zkApp, preparing testnet/mainnet, reviewing permissions, managing verification keys, planning upgrades, rotating keys or writing deployment scripts.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Compatibility gate

Before a version-sensitive claim, record the target network, active protocol era, exact `o1js` and signer versions, wallet/CLI versions, endpoints, and the origin of verification keys and proof caches. Load `../mina-protocol-agent/references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js 3 migration rules. Load `../mina-protocol-agent/references/playbooks/DEPLOYMENT_PROVENANCE_AND_REDEPLOY.md` for release identity, verification-key provenance, state-layout migration, key/config reconciliation, rollback, and hard-fork fail-closed checks. If the era is unknown, label the guidance unverified rather than guessing from package or endpoint names.

## Era migration and redeploy gate

Treat a protocol-era or major o1js change as a deployment migration, not a dependency-only upgrade. Recompile with a clean era-specific cache, regenerate verification keys and precomputed proofs, compare deployed address/key/VK/permissions, and synchronize frontend, backend, environment, and keychain configuration atomically. Query the deployed account after rollout. Keep Berkeley and Mesa artifacts in separate directories and reject mixed-era signing or rollback plans that reuse incompatible artifacts.

For wallet and transaction rollout checks, load `../mina-protocol-agent/references/playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md`.

## Deployment principle

A correct Mina/o1js contract can still be unsafe if deployed with wrong permissions, wrong verification key policy or sloppy key handling.

## Required first output

```text
Network:
o1js version:
zkApp CLI version:
Contract addresses:
Verification key source:
Deployer/admin keys:
Upgrade policy:
Permission matrix:
Incident plan:
```

Never ask the user to paste private keys.

## Deployment checklist

### 1. Environment

- Confirm network: local, devnet, testnet, mainnet.
- Pin `o1js`, zkApp CLI and wallet dependencies.
- Record exact commit hash.
- Rebuild from a clean checkout.
- Confirm GraphQL endpoint and archive endpoint if actions/events are needed.
- Confirm proof generation works in the intended environment.

### 2. Keys

- Separate deployer, admin, prover, backend and testing keys.
- Do not commit keys to repo.
- Do not put production keys in frontend.
- Do not print private keys in CI logs.
- Use hardware wallet/multisig/governance where available for high-value admin actions.
- Prepare rotation procedure.

### 3. Verification key

Document:

```text
How VK was generated:
Which code commit generated it:
Where VK is stored:
Who can update VK:
Whether update requires proof/signature/governance:
How users can verify deployed VK matches source:
```

### 4. Permissions

Build a permission matrix:

```text
editState:
send:
receive:
setDelegate:
setPermissions:
setVerificationKey:
setZkappUri:
editActionState:
setTokenSymbol:
setVotingFor:
access:
incrementNonce:
setTiming:
```

Apply least authority:

- permissions not used by the app should usually be impossible or tightly controlled;
- `setVerificationKey` must match upgrade policy;
- `setPermissions` should not remain loose by accident;
- token-specific permissions require extra review.

### 5. Upgrade policy

Classify the app:

```text
Immutable:
Admin-upgradeable:
Proof-upgradeable:
Governance-upgradeable:
Emergency-upgradeable:
```

For upgradeable apps, document:

- who can upgrade;
- delay/timelock if any;
- user notice process;
- rollback path;
- how to prevent malicious VK replacement;
- how to recover if a future protocol/proof-system change requires redeployment.

### 6. Pre-mainnet dry run

- Fresh deploy on local network.
- Fresh deploy on target testnet.
- Run every method.
- Run negative tests.
- Verify final account state and permissions from chain data.
- Verify explorer/indexer sees expected events/actions.
- Verify frontend points to correct address/network.
- Verify no private data appears in logs.

### 7. Incident plan

Prepare playbooks for:

- admin key compromised;
- deployer key compromised;
- wrong VK deployed;
- permission misconfiguration;
- frontend supply-chain attack;
- backend/prover outage;
- reducer/action queue griefing;
- privacy data leak;
- dependency compromise.

## Deployment script review

Flag:

- private key loaded from hard-coded string;
- faucet/devnet code left in mainnet path;
- deploy script uses wrong network id;
- permissions omitted and default values assumed;
- VK generated from unclean working tree;
- frontend config not updated after deployment;
- no post-deploy verification.

## Required tests

- unauthorized VK change fails;
- unauthorized permission change fails;
- intended upgrade path succeeds under correct authorization;
- normal user cannot call admin-only deployment method;
- deployed permissions match the intended matrix;
- all state-changing methods still work after deployment.

## Output format

```text
Deployment readiness score
Permission matrix
VK and upgrade risk assessment
Key management plan
Dry-run checklist
Incident plan
Blocking issues
```
