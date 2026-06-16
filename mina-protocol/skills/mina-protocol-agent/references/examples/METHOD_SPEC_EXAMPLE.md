# Example method spec

Use this before coding a Mina/o1js method.

```text
Method name: claimCredentialReward
Goal: user claims once if they prove a valid credential.
Public inputs: credential commitment, nullifier, reward amount
Private witnesses: credential fields, issuer signature, user secret, Merkle witness
On-chain state: credential root, nullifier root, reward pool balance
Preconditions: current roots must match on-chain state
Authorization: proof validates credential; sender/recipient bound in proof or signature
AccountUpdates: reward transfer to recipient, nullifier root update
Events: nullifier and new root only, no PII
Tests: valid claim, wrong signature, expired credential, reused nullifier, relayer recipient swap
```
