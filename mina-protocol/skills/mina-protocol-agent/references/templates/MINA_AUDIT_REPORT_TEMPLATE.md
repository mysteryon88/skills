# Mina / o1js zkApp Audit Report Template v2

## 1. Scope

- Project:
- Repository:
- Commit hash:
- o1js version:
- zkApp CLI version:
- Target network:
- Deployed addresses:
- In-scope files:
- Out-of-scope files:
- Review type: architecture / manual code review / tests / deployment / frontend / backend

## 2. Executive summary

Briefly describe the project, assets at risk, review limitations and strongest risks found.

## 3. Architecture map

- SmartContract classes:
- ZkPrograms:
- State fields:
- Methods:
- Events:
- Actions/reducers:
- AccountUpdate flows:
- Tokens:
- Frontend/backend/prover flow:
- External dependencies:

## 4. Public/private/proven/trusted classification

| Value | Public on-chain | Public proof input | Private witness | Trusted party | Notes |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 5. Role model

- Deployer:
- Admin:
- User:
- Prover:
- Relayer:
- Issuer/oracle/auditor:
- Frontend host:
- Backend operator:

## 6. Permission matrix

| Permission | Current value | Intended value | Who can use/change it | Risk | Recommendation |
|---|---|---|---|---|---|
| editState |  |  |  |  |  |
| send |  |  |  |  |  |
| receive |  |  |  |  |  |
| setPermissions |  |  |  |  |  |
| setVerificationKey |  |  |  |  |  |
| setZkappUri |  |  |  |  |  |
| editActionsState |  |  |  |  |  |
| setTokenSymbol |  |  |  |  |  |
| access |  |  |  |  |  |
| incrementNonce |  |  |  |  |  |
| setTiming |  |  |  |  |  |

## 7. AccountUpdate map

| Flow | Account | Token id | Auth | Balance change | State change | Preconditions | Children | Risk |
|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |

## 8. Invariants

- INV-001:
- INV-002:
- INV-003:

## 9. Findings

### F-001: Finding title

- Severity:
- Confidence:
- Category:
- Affected files:
- Description:
- Impact:
- Why this happens in Mina/o1js:
- Proof-of-concept or exploit sketch:
- Recommended fix:
- Regression test:
- Status:

## 10. Test coverage and gaps

| Invariant | Existing positive test | Existing negative test | Missing tests |
|---|---|---|---|
|  |  |  |  |

Common gaps:

- unauthorized caller;
- wrong witness;
- stale state;
- replay;
- reducer/action DoS;
- permission/upgrade;
- token supply;
- privacy leakage;
- frontend/backend trust.

## 11. Deployment risks

- Key management:
- Verification key policy:
- Upgrade process:
- Dependency pinning:
- Frontend integrity:
- Network/address config:
- Incident response:

## 12. Recommendations

### Immediate

-

### Before testnet/mainnet

-

### Long-term hardening

-

## 13. Open questions

- Q1:
- Q2:
