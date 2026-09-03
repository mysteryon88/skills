---
name: mina-o1js-testing-fuzzing
description: Use when writing or reviewing Mina o1js tests, negative tests, LocalBlockchain tests, proof-enabled smoke tests, fuzz or property-style tests, replay tests, or invariant coverage.
---

# Mina o1js Testing and Fuzzing Skill

## Use when

Use this skill when the user asks to write, improve or review tests for Mina/o1js code.

The goal is to make tests catch real zkApp bugs, not only confirm the happy path.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Compatibility gate

Before a version-sensitive claim, record the target network, active protocol era, exact `o1js` and signer versions, wallet/CLI versions, endpoints, and the origin of verification keys and proof caches. Load `../mina-protocol-agent/references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js 3 migration rules. If the era is unknown, label the guidance unverified rather than guessing from package or endpoint names.

## Cross-era and lifecycle test matrix

When a project may cross Berkeley/Mesa or library major versions, add tests for mixed signer era, stale verification key, stale cache/proof, old/new serialized VK shape, state and event/action boundaries, and maximum-plus-one AccountUpdate trees. For remote flows, test submitted-but-not-included, archive lag, dropped/reorganized transactions, nonce contention, and bounded rebuild/retry behavior using `../mina-protocol-agent/references/playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md`.

## Testing mindset

For every invariant, write at least one test that must fail if the invariant is removed.

A good Mina/o1js test suite checks:

- proof constraints;
- state preconditions;
- authorization;
- AccountUpdate shape;
- permission matrix;
- replay resistance;
- reducer/action safety;
- token accounting;
- privacy leakage in emitted public data;
- deployment scripts.

## Test workflow

1. Inventory the code.

```text
Contracts:
Methods:
State fields:
ZkPrograms:
Tokens:
Actions/reducers:
Events:
External AccountUpdates:
Deployment scripts:
```

2. Build invariants.

Examples:

```text
INV-001: Unauthorized sender cannot update state.
INV-002: Wrong Merkle witness cannot update root.
INV-003: Old root cannot be reused after state changes.
INV-004: Nullifier cannot be reused.
INV-005: Mint requires admin proof/signature.
INV-006: Verification key cannot be changed by normal user.
```

3. Map each invariant to tests.

```text
Invariant | Positive test | Negative test | Edge test
```

4. Add tests in layers.

- unit tests for pure/provable helpers;
- ZkProgram proof tests;
- SmartContract LocalBlockchain tests;
- AccountUpdate/transaction-shape tests;
- deployment permission tests;
- frontend/backend leakage tests where relevant.

## Standard negative tests

Use these categories by default:

### Wrong witness

- wrong secret for commitment;
- wrong Merkle path;
- wrong signature message;
- wrong issuer key;
- expired credential;
- malformed action data.

### Unauthorized caller

- random user calls admin method;
- old admin calls after role transfer;
- relayer changes recipient/amount/public input;
- user signs one message but transaction submits another value.

### Replay

- same proof submitted twice;
- same nullifier used twice;
- same action reduced twice;
- old state root reused;
- old signature reused with different contract/app id.

### Boundary values

- zero amount;
- max UInt64;
- overflow/underflow attempt;
- empty Merkle tree;
- first/last index;
- expired timestamp exactly at boundary;
- array length mismatch.

### AccountUpdate abuse

- child update tries to modify token balance;
- unexpected tokenId;
- unauthorized balance change;
- extra AccountUpdate added by attacker;
- missing proof or signature.

### Deployment permissions

- normal user cannot change verification key;
- admin cannot change locked permission;
- intended upgrade method works only under governance rule;
- token symbol cannot change if immutable.

## Property-style test ideas

Even without a full fuzzing library, simulate adversarial inputs:

```text
For N random users:
  random valid deposits preserve supply invariant.
  random invalid witnesses fail.
  random repeated nullifiers fail after first use.
  random token transfers preserve total supply.
```

Use deterministic seeds when possible so failures are reproducible.

## LocalBlockchain testing skeleton

Adapt to the project style:

```ts
import { Mina, PrivateKey, AccountUpdate } from 'o1js';

let Local = await Mina.LocalBlockchain({ proofsEnabled: false });
Mina.setActiveInstance(Local);

const deployer = Local.testAccounts[0].key;
const user = Local.testAccounts[1].key;
const attacker = Local.testAccounts[2].key;

// compile if needed
// await MyContract.compile();

const zkAppKey = PrivateKey.random();
const zkAppAddress = zkAppKey.toPublicKey();
const zkApp = new MyContract(zkAppAddress);

const deployTx = await Mina.transaction(deployer.toPublicKey(), async () => {
  AccountUpdate.fundNewAccount(deployer.toPublicKey());
  await zkApp.deploy();
});
await deployTx.prove();
await deployTx.sign([deployer, zkAppKey]).send();
```

## Test output format

```text
Test plan
Invariant matrix
Files changed
New tests
Expected pass/fail behavior
Remaining untested risks
```

## Review existing tests

Flag these gaps:

- all tests use the deployer/admin account;
- no test expects `.prove()` or `.send()` to fail;
- tests do not inspect final on-chain state;
- no stale-state test;
- no replay test;
- no permission test;
- no token supply invariant;
- frontend and backend are ignored while privacy claims are made;
- proofs disabled locally and no proof-enabled smoke test exists.

## Proofs enabled strategy

- Use `proofsEnabled: false` for fast logic tests.
- Add at least one proof-enabled smoke test for core circuits before release.
- For heavy projects, compile once in setup and reuse artifacts where the test framework allows it.

## Do not finish until

- every critical invariant has a negative test;
- expected failures are explicit;
- test names explain the attack being prevented;
- edge cases are listed even if not all are implemented.
