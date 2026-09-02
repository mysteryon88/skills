# R1CS and Circom Review Checklist

Use this reference when designing a relation, debugging a failed proof, or reviewing a circuit and its verifier integration.

## Gather the evidence

Review the smallest complete artifact set available:

- the intended statement or product requirement;
- the circuit source and compiler version;
- the ordered public inputs and outputs;
- witness-generation code;
- compiled R1CS and symbol mapping;
- proving and verification keys;
- verifier code and application-side input mapping.

Missing artifacts are review limitations, not evidence that the missing layer is correct.

Hash or otherwise identify each reviewed source, constraint system, setup artifact, key, proof fixture, converter output, and generated verifier. Confirm they belong to one build rather than a plausible-looking mixture.

## Define the relation

Write the relation as $R(I, W)$ before reading constraints in detail.

- Name the scalar field.
- List public instance values $I$ in verifier order.
- List private and intermediate witness values $W$.
- Define accepted boundary cases, including zero and maximum values.
- Provide one valid and one invalid assignment.

Changing the public/private split changes the claim even when the arithmetic is unchanged.

## Trace intent to constraints

Map every intended predicate to one or more constraints. A value computed by the witness generator is not constrained merely because it received an assignment.

Check these patterns explicitly:

### Boolean

$$
b(1-b)=0
$$

Using `b` as a selector does not make it boolean.

### Inverse and division

For a nonzero inverse witness `inv`, require:

$$
x \cdot inv = 1
$$

If zero is valid, specify a separate gated relation. Do not let `x = 0` silently satisfy an equation intended to prove invertibility.

### Range and bit decomposition

For an $n$-bit decomposition:

$$
x = \sum_{i=0}^{n-1} 2^i b_i
$$

Constrain every $b_i$ as boolean and prove the represented range is canonical in the circuit field. Equality modulo the field prime alone may admit multiple integer encodings.

### Conditional selection

For a boolean selector $b$:

$$
z = bx + (1-b)y
$$

Both branches need valid witness values because the circuit topology is fixed.

### Higher-degree products

Flatten products into intermediate witnesses so each R1CS row multiplies two linear combinations. Then constrain every intermediate value.

## Compare generated artifacts

- Confirm the compiled public/private counts match the intended interface.
- Use the symbol file to map suspicious wires back to source signals.
- Check a valid witness against the compiled R1CS.
- Mutate each security-relevant witness class and confirm the R1CS rejects it.
- Inspect optimization-sensitive output instead of assuming every source assignment survives compilation unchanged.
- Treat witness generation and constraint generation as separate programs that must agree.

For Circom, treat witness-only assignments as unconstrained unless a separate equality binds the result. Verify the exact operators against the installed compiler version.

## Review the Groth16 boundary

- Confirm the proving and verification keys belong to the reviewed R1CS.
- Confirm every public value appears exactly once and in the expected order.
- Validate proof-point encodings, curve membership, subgroup membership, and exceptional points as required by the implementation.
- Confirm field values are canonical before crossing language or serialization boundaries.
- Establish CRS provenance and ceremony assumptions.
- Keep application checks around the verified public statement; proof verification does not replace authorization or business rules.

Use [application-binding.md](application-binding.md) when public values authorize an action or depend on runtime state.

## Adversarial evidence

Start from one verified baseline and change one property at a time. Include:

- each private relation broken independently;
- each public value changed independently, reordered, removed, or duplicated;
- booleans, enums, ranges, zero denominators, and scalar-modulus boundaries;
- a proof or key from another circuit/build;
- malformed, identity, off-curve, or wrong-subgroup points where the harness can construct them safely;
- serialization truncation, extension, alternate encodings, and round trips;
- changed domain, action, version, root, nonce/nullifier, or expiry for application-bound proofs.

Record the layer expected to reject each mutation: input parsing, witness generation, R1CS, proof verification, or application policy. Random bytes alone are weak point-validation evidence because they usually fail before curve or subgroup checks.

## Fast failure smells

| Smell | Likely defect |
|---|---|
| Computed witness never appears in an equality | Underconstraint |
| Selector lacks a boolean constraint | Multiple unintended branches |
| Division has no zero policy | Invalid inverse relation |
| Packed bits span or exceed the field modulus | Non-canonical encoding |
| Loop bound depends on private input | Runtime behavior cannot define fixed topology |
| Public signals are reordered outside the circuit | Verifier binds a different instance |
| Curve check omits subgroup validation | Invalid-group or small-subgroup input |
| Setup transcript or key provenance is unknown | Soundness assumption is ungrounded |
| External integer is reduced before business use | Multiple application values alias one field element |
| Caller controls the verification key | The application may accept an attacker-chosen relation |
| Valid proof is accepted under another action/domain | Missing application binding |
| Proof, key, wrapper, and verifier have different build identities | Stale artifact mix |
| Generated cryptographic code differs from reproducible output | Unreviewed verifier semantics |

## Report shape

Lead with the verdict. For each finding, state:

1. the intended property;
2. the actual constraint or verifier behavior;
3. a concrete valid or invalid assignment demonstrating the gap;
4. impact;
5. the smallest correction and how to verify it.
