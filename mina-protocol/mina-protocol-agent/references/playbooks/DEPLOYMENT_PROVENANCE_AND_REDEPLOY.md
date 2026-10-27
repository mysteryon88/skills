# Deployment provenance, upgrades and redeploy consistency

Use this reference for deployment, verification-key changes, state-layout changes, permission changes, key rotation and hard-fork migration.

## Release identity

Minor security releases can change verification keys: apply the
[3.1.0 refresh](NETWORK_ERA_AND_O1JS_COMPATIBILITY.md) before reusing caches or a
deployment manifest. An npm update alone does not patch an already deployed contract.

Record one immutable release identity:

```text
Repository and source commit:
Dirty-tree status:
Build command and environment:
Node/package-manager versions:
o1js / mina-signer / zkapp-cli versions:
Target network and protocol era:
Contract and ZkProgram class names:
Compiled verification-key data hash:
Compiled verification-key protocol/hash field:
Cache directory and cache manifest hash:
Deployer and zkApp public keys:
Deployment transaction hash:
On-chain VK hash and setVerificationKey txnVersion:
On-chain permission matrix:
State-layout/schema version:
Frontend/backend configuration revision:
```

Do not call a deploy reproducible when one of these values is inferred from an unpinned workstation state.

## Verification-key and cache rules

- Recompile and regenerate caches whenever o1js, proof-system, protocol era, circuit code, method signature, provable type, state layout or compile option changes.
- Compare both VK data and hash where the API provides them.
- Never mix Berkeley and Mesa caches, signer formats or VKs.
- Verify the on-chain VK hash and `setVerificationKey.txnVersion` after deploy/upgrade.
- Keep stale artifacts outside the active cache path, labelled with source/version provenance.

## Permissions and state-layout changes

- Diff intended permissions against deployed permissions before and after the transaction.
- Treat `setPermissions`, `setVerificationKey`, `access`, `editState`, `send`, `editActionState` and token permissions as release-critical controls.
- A state-field expansion or reorder is a storage migration, even if the target protocol allows more fields.
- Document initialization defaults, old-state interpretation, migration authorization, rollback and partial-failure behavior.
- For `TokenContract`, inspect final on-chain permissions instead of assuming deploy defaults.

## Key and configuration consistency

After key rotation or redeploy, synchronize and verify all sources of truth:

- deploy configuration;
- environment variables and secret manager;
- local key aliases/keychain references;
- frontend and backend public configuration;
- indexer/archive configuration;
- monitoring and incident runbooks.

At startup, log non-secret provenance such as target network, zkApp public key, source revision and expected VK hash. Derive public keys from private material only inside the trusted secret boundary and never log the private material.

## Safe redeploy workflow

1. Build from a clean, pinned source revision.
2. Compile and record current VK/caches.
3. Generate or select the approved zkApp key through the project key-management policy.
4. Fund/create the account only on the intended network.
5. Deploy with the reviewed permission matrix.
6. Record transaction hash and wait for the required finality.
7. Query the live account and compare address, VK, txnVersion, permissions, state and tokenId.
8. Update configuration atomically and restart affected services.
9. Run an end-to-end transaction plus negative permission/VK tests.
10. Keep the previous release identity and rollback decision documented.

## Hard-fork and upgrade fail-closed behavior

Never hardcode a mutable upgrade schedule as the source of truth. Before a write:

- query live protocol/upgrade status;
- confirm transactions are open;
- confirm the daemon is synced to the expected genesis/era;
- stop on unknown status, unreachable schedule or missing live slot;
- after a new genesis, refetch constants and all deployed account data.

## Required tests

- stale VK/cache rejected;
- wrong era/signer format rejected;
- changed state layout requires an explicit migration path;
- permission diff catches unexpected defaults;
- wrong zkApp public key/config source is detected at startup;
- deploy succeeds but runtime uses old key/VK, and the health check fails closed;
- rollback path preserves keys/state and does not accept both releases silently;
- hard-fork status unknown blocks writes.

## Completion gate

A deploy is complete only after source/build/cache/VK/address/permissions/state/runtime configuration all reconcile against live on-chain evidence.
