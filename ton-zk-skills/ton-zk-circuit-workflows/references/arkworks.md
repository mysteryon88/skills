# Arkworks workflow

## Curve and proof-system selection

Use `ark-bls12-381` and Groth16 for the documented TON path. Circuit synthesis, setup, proof, public inputs, and verification must use the same concrete curve and library versions.

A repository commonly performs:

1. Implement `ConstraintSynthesizer` for the statement.
2. Generate or load parameters for BLS12-381 Groth16.
3. Create a proof from a witness.
4. Prepare and verify the VK locally.
5. Export a supported native bundle/VK JSON or convert through `ark-snarkjs`.

Follow the installed Arkworks APIs and crate versions; API names and serialization behavior can differ across releases.

## Repository verification

```bash
rustc --version
cargo metadata --format-version 1 --no-deps
cargo test
cargo run
```

Do not discard `Result` values from setup, proof, verification, serialization, or file writes.

## Export routes

The 2026-08-06 TON examples and generator reference snapshot documented these routes:

- snarkjs-compatible proof and VK JSON produced through `ark-snarkjs`;
- a native Arkworks compressed artifact bundle;
- a VK-only JSON carrying curve and verifying-key data in the generator's accepted shape.

Use `doctor` to identify the exact source format and target template.

## Serialization invariants

- BLS12-381 and Groth16 are explicit.
- Compressed/uncompressed point encodings decode to the same points.
- G2 extension-field components and byte order are not swapped.
- Public-input vector order is stable and its length agrees with the VK.
- The identity point is not accepted where the VK format forbids it.
- Native subgroup/on-curve validation and generator-side validation both succeed.

## Constraint-security review

Use `$groth16-systems` for allocation choices, constraint completeness, errors, counts, ranges, and artifact identity. The TON overlay confirms BLS12-381, exported public order, registered TON encodings, and native-to-TON fixture parity before export.

## Tests

Add Rust tests for constraint satisfaction, valid proof, invalid witness/public input, serialization round-trip, deterministic public-input ordering, native export, converted export, and a cross-language fixture consumed by the TON tests.

## Handoff

Report Rust/Arkworks crate versions, curve/protocol, circuit and VK hashes, serialization mode, native/converted paths, public-input contract, local verification, and generator diagnosis.
