# Mina/o1js Implementation Note Template

## Goal

## Compatibility preflight

- Target network and active era:
- o1js / mina-signer / wallet / CLI versions:
- GraphQL / archive / DA endpoints:
- Verification-key / proof / cache origin:

## Files changed

## Public/private/proven/trusted classification

| Item | Public | Private witness | Proven | Trusted | Notes |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## State model

- On-chain state:
- Off-chain state:
- Commitments/roots:
- Preconditions:

## Method design

| Method | Inputs | State read/write | Authorization | AccountUpdates | Failure cases |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## Constraints added

-

## Tests added

- Happy path:
- Wrong witness:
- Unauthorized caller:
- Replay/stale state:
- Boundary values:

## Security notes

- What is proven:
- What is not proven:
- Trusted parties:
- Remaining risks:

## Transaction and deployment notes

- Transaction shape and fee payer:
- Prove / serialize / sign order:
- Inclusion / indexing / finality policy:
- Permissions:
- Verification key:
- Network config:
- Rollback and redeploy consistency:
