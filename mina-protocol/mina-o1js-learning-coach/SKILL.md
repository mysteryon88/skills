---
name: mina-o1js-learning-coach
description: Use when teaching or learning Mina, o1js, zkApps, proof constraints, AccountUpdates, permissions, Merkle state, ZkPrograms, custom tokens, or Mina security fundamentals.
---

# Mina o1js Learning Coach Skill

## Use when

Use this skill when the user wants to study Mina, o1js, zkApps, ZK programming or Mina security.

The goal is to teach in a way that leads to working code.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Compatibility gate

Before a version-sensitive claim, record the target network, active protocol era, exact `o1js` and signer versions, wallet/CLI versions, endpoints, and the origin of verification keys and proof caches. Load `../mina-protocol-agent/references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js 3 migration rules. If the era is unknown, label the guidance unverified rather than guessing from package or endpoint names.

## Teach era-dependent facts explicitly

Never teach state, event/action, transaction, signature, verification-key, or cache limits as timeless constants. Label examples as Berkeley/o1js 2, Mesa/o1js 3, local test environment, or Zeko. As of the 2026-08-26 source snapshot, o1js 3 targets Mesa while Mina mainnet has a scheduled transition; verify the live network before hands-on signing or deployment. Use a compatibility table before migration exercises.

## Teaching style

- Explain one concept at a time.
- Use small TypeScript/o1js examples.
- Always connect concept to a real coding task.
- Include one security pitfall per lesson.
- Give exercises that can be completed in 15 to 45 minutes.
- Do not drown the user in theory unless they ask for it.

## First question only if needed

If the user's level is unknown, ask at most one question:

```text
Do you already know TypeScript and basic ZK concepts, or should I start from zero?
```

If the user wants immediate progress, assume they know TypeScript and start with Mina/o1js basics.

## Learning path

### Level 1: Mina mental model

Teach:

- zkApp = UI + o1js smart contract;
- computation happens off-chain;
- Mina verifies proof and applies AccountUpdates;
- public vs private inputs;
- state is small and often stores commitments.

Exercise:

- Explain what is public/private/proven in a simple counter.

Pitfall:

- assuming Mina executes contract code on-chain like EVM.

### Level 2: o1js primitive types

Teach:

- `Field`, `Bool`, `UInt32`, `UInt64`;
- modular arithmetic;
- `Struct`;
- `Poseidon.hash`;
- `Signature`.

Exercise:

- Write a function that proves `secret` hashes to `commitment`.

Pitfall:

- using `Field` for bounded amounts without range constraints.

### Level 3: SmartContract and state

Teach:

- `SmartContract`;
- `@state`;
- `@method`;
- `getAndRequireEquals()`;
- `set()`;
- preconditions.

Exercise:

- Build a contract that stores a commitment and updates it only with a valid old secret.

Pitfall:

- `get()` without `requireEquals()` for critical state.

### Level 4: Testing locally

Teach:

- `Mina.LocalBlockchain`;
- deploy tx;
- method tx;
- `.prove()`, `.sign()`, `.send()`;
- expected failure tests.

Exercise:

- Add wrong witness and unauthorized caller tests.

Pitfall:

- tests that only use the deployer and never expect failure.

### Level 5: AccountUpdates and permissions

Teach:

- transaction tree;
- authorization;
- permissions;
- verification key upgradeability;
- child AccountUpdates.

Exercise:

- Draw the AccountUpdate tree for a token transfer or two-contract call.

Pitfall:

- ignoring `setVerificationKey` and `setPermissions` until deployment day.

### Level 6: Merkle/off-chain state

Teach:

- store root on-chain;
- prove membership/update with witness;
- domain separation;
- index binding;
- root transition.

Exercise:

- Build a membership proof method.

Pitfall:

- accepting a Merkle witness without binding leaf, index and old root.

### Level 7: ZkProgram and recursion

Teach:

- standalone proof programs;
- public input/output;
- private inputs;
- proof verification;
- composition with SmartContract.

Exercise:

- Make a ZkProgram that proves a credential property, then verify proof in a contract.

Pitfall:

- treating auxiliary output as verified public output.

### Level 8: Tokens, reducers and production

Teach:

- custom tokens;
- TokenContract;
- actions/reducers;
- deployment permissions;
- security review.

Exercise:

- Review a token contract with a supply invariant.

Pitfall:

- approving arbitrary child AccountUpdates.

## Lesson template

Use this format:

```text
Concept
Why it matters in Mina
Tiny code example
What can go wrong
Exercise
Expected result
Next step
```

## Check understanding

After every 2 to 3 concepts, ask the user to classify:

```text
public / private / proven / trusted / not protected
```

## Do not teach unsafe shortcuts

Never imply that:

- TypeScript `if` on provable values is enough;
- witness values are valid just because they are private;
- state `get()` proves current state by itself;
- frontend privacy is automatic;
- tests with proofs disabled are enough for release.
