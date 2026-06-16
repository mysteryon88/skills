# Mina/o1js Quick Reference for Agents

## Always ask or infer

- What is public?
- What is private?
- What is proven?
- What is authorized?
- What is trusted?
- What can be replayed?
- What can leak?

## Use these skills by task

| Task | Skill |
|---|---|
| Learn Mina/o1js | mina-o1js-learning-coach |
| Write zkApp code | mina-o1js-zkapp-dev |
| Review security | mina-o1js-security-review |
| Add tests | mina-o1js-testing-fuzzing |
| Token logic | mina-token-standard-security |
| Deployment | mina-deployment-upgrade-security |
| Credentials/privacy | mina-privacy-credentials-security |
| Research ecosystem | mina-ecosystem-research-scout |
| ZkProgram/recursion | mina-zkprogram-recursion-dev |
| Merkle/off-chain state | mina-merkle-offchain-state-dev |
| Frontend/prover UX | mina-frontend-prover-ux |
| Debug transaction | mina-accountupdate-transaction-debugger |

## High-risk APIs / concepts to inspect

- `Provable.witness`
- `ZkProgram`
- `SmartContract`
- `@state`
- `@method`
- `.get()`
- `.getAndRequireEquals()`
- `.requireEquals()`
- `AccountUpdate`
- `AccountUpdate.create`
- `AccountUpdate.createSigned`
- `AccountUpdate.fundNewAccount`
- `Permissions`
- `setVerificationKey`
- `setPermissions`
- `TokenContract`
- `approveBase`
- `internal.mint/burn/send`
- `Reducer`
- `dispatch`
- `reduce`
- `emitEvent`
- `Poseidon.hash`
- `Signature.verify`
- Merkle witness classes

## Common final note for agents

```text
This code/review is not production-ready until dependencies are pinned, permissions are verified on the target network, proof-enabled smoke tests pass and high-value contracts receive independent security review.
```
