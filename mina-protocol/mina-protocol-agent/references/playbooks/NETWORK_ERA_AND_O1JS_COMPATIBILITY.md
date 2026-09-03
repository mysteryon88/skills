# Mina Network Era and o1js Compatibility

Use this playbook before making a version-sensitive coding, signing, proving, deployment, or audit claim.

## Status snapshot

Checked on 2026-08-26:

- o1js 3.0.0 was released on 2026-08-18 and targets Mesa.
- During a protocol transition, the live network era can differ from the newest package defaults.
- o1js 2.x and Berkeley-formatted signing remain relevant wherever the target network still uses Berkeley.
- Upgrade dates, endpoints, and rollout status are mutable operational facts and are intentionally not hard-coded here.

This is a dated compatibility review, not a permanent network-status claim. Before acting, verify the live network era, chain ID, official upgrade tracker, package versions, and current release notes.

## Mandatory compatibility record

Before code changes or operational instructions, record:

```text
Target network:
Network era: Berkeley / Mesa / unknown
Chain ID or network identifier:
o1js version:
mina-signer version and configured era:
zkApp CLI version:
Wallet version:
GraphQL endpoint:
Archive endpoint:
DA endpoint if applicable:
Verification key origin:
Proof/cache origin:
Last official source checked:
```

If the era or package version is unknown, mark the recommendation as unverified and inspect the lockfile, runtime package versions, live network status, and official changelogs. Do not infer the era from an endpoint name alone.

## Berkeley and Mesa are not interchangeable

| Concern | Berkeley / o1js 2.x | Mesa / o1js 3.x |
|---|---|---|
| zkApp state fields | 8 Field elements | 32 Field elements |
| Transaction limit model | legacy cost model | segment/account-update limit model |
| zkApp transaction capacity | legacy weighted-cost formula | `np + n2 + n1 <= 16`; the effective AccountUpdate count depends on authorization segments/tree shape |
| Event/action elements | 100 | 1024 |
| zkApp signature format | Berkeley | Mesa by default in mina-signer v4 |
| Verification keys and caches | Berkeley artifacts | must be regenerated for Mesa |

Treat limits as protocol-era facts, not timeless o1js constants.

## o1js 3.0.0 migration checks

### Verification keys, proofs, and caches

- A Mesa build changes verification keys.
- Recompile contracts and ZkPrograms with the target o1js version.
- Regenerate persistent proving caches and precomputed proofs.
- Redeploy or explicitly migrate contracts whose on-chain verification key must match the Mesa build.
- Record the compiler version, source commit, build flags, verification-key hash, and deployment address together.
- Do not accept "compiled successfully" as proof that the deployed address, permissions, and verification key match.

### Signing era

`mina-signer` v4 signs Mesa zkApp commands by default. A legacy Berkeley target requires an explicit `era: 'berkeley'` configuration. A signer-era mismatch can produce transactions that look structurally valid but fail authorization or verification on the target chain.

Before signing:

1. Determine the live target era.
2. Determine the signer default and explicit era setting.
3. Verify the network and chain context included in the signed payload.
4. Generate a known test vector or dry-run transaction for the target era.
5. Reject ambiguous mixed-era configuration.

### State and transaction limits

- `Transaction.setFeePerSnarkCost()` is removed. Use `Transaction.setFeePerAccountUpdate()` when the pinned version exposes that API.
- Mesa uses `TransactionLimits.MAX_ZKAPP_SEGMENT_PER_TRANSACTION = 16` instead of the removed floating-point cost constants.
- `TransactionLimits.MAX_ACTION_ELEMENTS` and `TransactionLimits.MAX_EVENT_ELEMENTS` are 1024 in o1js 3.0/Mesa; keep stricter application-level DoS limits where appropriate.
- Do not hard-code "8 state fields" without naming the era.
- Do not size events, actions, or AccountUpdate trees from memory. Mesa limits authorization segments with `np + n2 + n1 <= 16`; do not simplify this to a timeless raw AccountUpdate count.
- Inspect the target protocol constants and o1js version.
- Test the boundary and one-over-boundary case.
- Use `TransactionLimits.MAX_ZKAPP_SEGMENT_PER_TRANSACTION` for Mesa-aware limit checks instead of removed floating-point transaction-cost constants.

### VerificationKey serialization

In current o1js, `VerificationKey.toJSON()` returns an object containing both `data` and `hash`. Code that expects a string must be migrated and tests must assert the exact serialized shape used by APIs, deployment scripts, and manifests.

### Token deployment permissions

Current `TokenContract.deploy()` preserves custom permissions set in `init()` and only adjusts `access` when it remains at the default. Never assume deploy silently resets the entire permission set. Query and compare on-chain permissions after deployment.

### External signing commitments

Current mina-signer exposes `Client.getZkappCommandCommitments()` and `Client.getZkappCommandCommitmentsFromJSON()` for explicit commitment/full-commitment checks. Use them where an external wallet or signer must prove it signed exactly the inspected transaction shape.

### Network and browser behavior

- Current GraphQL clients retry some transient transport errors, but application retries still need idempotency and unknown-result handling.
- Mesa Lightnet can provide a local compatibility target.
- Repeated browser proving received a worker-finalization fix in o1js 3.0; capture exact backend/version evidence before adding workarounds.
- Fetched account conversion preserves `permissions.setVerificationKey.txnVersion`; compare it during deployment and upgrade checks.

### Native prover

The native prover is a Node.js runtime path and is not a browser replacement. Browser applications still need the supported web/WASM worker flow. Keep runtime detection explicit and test both paths when the product supports both.

### Hashing variable-length inputs

Use `Poseidon.hashAnyLength()` when the statement truly contains variable-length data. It is intentionally incompatible with fixed-length `Poseidon.hash()` semantics. Version the commitment schema and bind length/domain so producers and verifiers cannot silently disagree.

### Remote slot and finality APIs

For remote networks, prefer current supported APIs such as `fetchCurrentSlot()` and the transaction depth/finality methods exposed by the installed o1js version. Do not equate successful broadcast or endpoint visibility with canonical finality.

## Safe migration workflow

1. Freeze the exact source commit and current deployment metadata.
2. Inventory all o1js, mina-signer, wallet, CLI, GraphQL, archive, and prover dependencies.
3. Classify every environment as Berkeley, Mesa, or unknown.
4. Compile and test in a clean Mesa-specific cache directory.
5. Compare verification-key hashes, transaction JSON, signatures, limits, permissions, and event/action encodings.
6. Run negative tests for mixed-era signatures, stale proofs, stale caches, wrong verification keys, and one-over-limit transactions.
7. Dry-run deployment or redeployment with fresh keys and explicit permissions.
8. Update frontend/backend config atomically and verify derived public keys and verification-key hashes at startup.
9. Keep rollback criteria and old deployment metadata until post-deploy checks pass.
10. Re-check official release notes immediately before mainnet action.

## Fail-closed rules

- Do not claim mainnet is Mesa merely because o1js 3 is installed.
- Do not use a Mesa signer against a Berkeley network without explicit compatibility evidence.
- Do not reuse Berkeley verification keys, proof caches, or precomputed transaction proofs for Mesa.
- Do not silently truncate state, events, actions, or AccountUpdate trees to a remembered limit.
- Do not copy code from a prerelease branch without confirming the package and network versions it targets.
