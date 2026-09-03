---
name: mina-zkprogram-recursion-dev
description: Use when building or reviewing Mina o1js ZkPrograms, recursive proofs, proof aggregation, verifiable compute modules, public input/output design, or SmartContract proof integration.
---

# Mina ZkProgram and Recursion Development Skill

## Use when

Use this skill when building or reviewing standalone `ZkProgram`s, recursive proofs, proof aggregation, verifiable compute modules or circuits that later feed into a Mina `SmartContract`.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Compatibility gate

Before a version-sensitive claim, record the target network, active protocol era, exact `o1js` and signer versions, wallet/CLI versions, endpoints, and the origin of verification keys and proof caches. Load `../mina-protocol-agent/references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js 3 migration rules. If the era is unknown, label the guidance unverified rather than guessing from package or endpoint names.

## Proof artifact compatibility

Treat compile output, verification keys, recursive proof types, dummy-proof helpers, and persistent caches as pinned-version artifacts. Across o1js or protocol-era changes, regenerate them and re-run base, recursive-step, serialization, and SmartContract integration tests. Never accept a previous proof merely because its TypeScript type still compiles. Record the o1js version and verification-key hash in proof manifests.

## Mental model

A `ZkProgram` defines a proof system with public input/output types, private inputs and methods that generate proofs. It can be used independently or as a component of a zkApp.

Important distinction:

```text
publicInput/publicOutput = verifier can see and check
privateInputs = prover knows, verifier does not see
auxiliary output = developer convenience, not verified by verifier unless committed to public output
```

## First output

Before coding, write:

```text
Program name:
Public input:
Public output:
Private inputs:
Proof methods:
Recursive methods:
Base case:
Step case:
What the verifier learns:
What remains private:
How SmartContract will consume the proof:
```

## Design checklist

### Public I/O

- Public input/output types are minimal but sufficient.
- Public output includes all values the verifier or contract must rely on.
- Private inputs are not accidentally returned as auxiliary output and logged.
- Domain separation is included in hashes/commitments.

### Constraints

- Every private input is constrained.
- Range checks are explicit.
- Signatures bind all required fields.
- Merkle witnesses bind leaf, index/key and root.
- Public output is asserted to match the intended transformation.

### Recursion

For recursive flows, define:

```text
Base proof:
Step proof:
Previous proof public output:
New public output:
Invariant preserved across steps:
Maximum depth or batching model:
```

Check:

- base case cannot fake initial state;
- step verifies previous proof;
- step cannot skip invalid transition;
- public output carries the accumulated state needed by the verifier;
- proof type and verification key assumptions are documented.

### Performance

- Analyze constraint count for heavy helpers.
- Prefer Poseidon for native Mina-friendly hashing unless compatibility requires another hash.
- Keep fixed array sizes intentional.
- Avoid expensive dynamic-looking logic that blows up constraints.

## Common bad patterns

### Private input not bound to public output

Bad:

```ts
method: async (publicInput: Field, secret: Field) => {
  const x = secret.add(1);
  return { publicOutput: publicInput };
}
```

Good:

```ts
method: async (commitment: Field, secret: Field) => {
  Poseidon.hash([DOMAIN, secret]).assertEquals(commitment);
  return { publicOutput: commitment };
}
```

### Auxiliary output mistaken for verified data

Bad:

```ts
return {
  publicOutput: root,
  auxiliaryOutput: privateBalance,
};
```

Then backend trusts `privateBalance` as if verified.

Good:

```ts
// Put commitments or verified summaries in publicOutput.
// Treat auxiliaryOutput as local prover metadata only.
```

## Testing requirements

- proof verifies for valid input;
- proof fails for wrong witness;
- public output changes when input changes;
- recursive step rejects wrong previous proof;
- base case rejects fake initial state;
- constraint count is recorded for critical methods;
- SmartContract integration verifies the proof and binds public output to state update.

## Output format

```text
ZkProgram design
Code
Constraint notes
Integration with SmartContract
Tests
Security notes
```
