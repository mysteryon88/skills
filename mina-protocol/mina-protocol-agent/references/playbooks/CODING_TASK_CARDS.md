# Mina/o1js Coding Task Cards

Paste one of these into your coding agent.

## Task card: Add a safe state update method

```text
Use mina-o1js-zkapp-dev and mina-o1js-testing-fuzzing.

Goal: add method <methodName> to <ContractName>.

Before coding:
1. Identify public inputs, private witnesses, on-chain state and trusted parties.
2. Identify state preconditions. Use getAndRequireEquals or requireEquals for critical state.
3. Identify authorization model: sender, signature, permission or proof.
4. List AccountUpdates created by the method.

After coding:
1. Add happy-path test.
2. Add wrong witness test.
3. Add unauthorized caller test.
4. Add stale state/replay test if state changes.
5. Write an implementation note.
```

## Task card: Review underconstrained witness risk

```text
Use mina-o1js-security-review.

Search for Provable.witness, privateInputs in ZkProgram and method parameters that are meant to be private.
For each private value:
1. Show where it enters the code.
2. Show which assertions constrain it.
3. Show what public state/input it is bound to.
4. Flag values that are only used in normal TypeScript or auxiliary output.
5. Add regression tests for wrong witness.
```

## Task card: Build Merkle membership/update flow

```text
Use mina-merkle-offchain-state-dev and mina-o1js-testing-fuzzing.

Implement a Merkle root based flow:
1. Define leaf schema with domain separation.
2. Store root on-chain.
3. Prove old leaf membership against old root.
4. Compute new leaf.
5. Compute and set new root.
6. Bind owner/index/key so witness cannot be reused for another user.
7. Add tests for wrong leaf, wrong index, wrong root and stale witness.
```

## Task card: Debug transaction failure

```text
Use mina-accountupdate-transaction-debugger.

Given the failing transaction/test:
1. Reproduce minimal failure.
2. Draw AccountUpdate tree.
3. List accounts, token ids, balance changes, authorizations and permissions.
4. Identify missing proof/signature/precondition/account creation fee.
5. Propose the smallest fix.
6. Add regression test.
```

## Task card: Add token mint authorization

```text
Use mina-token-standard-security and mina-o1js-testing-fuzzing.

Goal: make token minting safe.
1. Define admin key/state.
2. Bind admin authorization to contract address, token id, recipient, amount, nonce/nullifier and expiry where relevant.
3. Ensure amount uses UInt64 and rejects zero if zero mint is not intended.
4. Add random user cannot mint test.
5. Add wrong signature cannot mint test.
6. Add supply invariant test.
```

## Task card: Prepare deployment review

```text
Use mina-deployment-upgrade-security.

For this repo/contract:
1. Identify o1js version, target network and contract addresses.
2. Build permission matrix.
3. Classify upgrade policy: immutable, admin-upgradeable, proof-upgradeable or governance-upgradeable.
4. Check deployment scripts for keys, network config and verification key generation.
5. Add tests that unauthorized VK/permission changes fail.
6. Produce a deployment readiness score and blocking issues.
```

## Task card: Privacy leakage review

```text
Use mina-privacy-credentials-security and mina-frontend-prover-ux.

For this credential/privacy app:
1. Build data leakage map.
2. Classify every value as public on-chain, public input, private witness, frontend data, backend data and logs/analytics.
3. Check issuer signature binding, expiry, revocation and nullifier domain separation.
4. Check frontend/backend do not receive or log raw witness unless trust model says so.
5. Add tests for invalid issuer signature, expired credential, reused nullifier and relayer mutation.
```
