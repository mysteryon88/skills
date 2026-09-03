# Gnark workflow

## Curve and proof-system selection

Use Gnark's BLS12-381 curve explicitly for the documented TON path. The circuit and witness must compile under the same field, and local verification must succeed before export.

A project commonly performs these stages in Go:

1. Compile the circuit over `ecc.BLS12_381.ScalarField()`.
2. Build full and public witnesses in the same field.
3. Run Groth16 setup/prove/verify.
4. Export the VK/proof as a supported native artifact or through `gnark-to-snarkjs`.

Use the repository's actual Gnark API version; do not paste API calls from another major version without compiling tests.

## Repository verification

```bash
go version
go mod verify
go test -count=1 ./...
go run .
```

The executable should fail on setup/prove/verify/export errors rather than ignore return values.

## Export routes

The 2026-08-06 TON examples and generator reference snapshot documented these routes:

- snarkjs-compatible `verification_key.json` and `proof.json` produced with `gnark-to-snarkjs`;
- native Gnark verification-key JSON;
- native Gnark verification-key binary.

Run `export-ton-verifier doctor` on the exact file rather than choosing by extension alone.

## Conversion invariants

- Curve is BLS12-381 on both sides.
- Protocol is Groth16.
- Public witness order exactly matches the exported `IC` mapping.
- G1/G2 coordinate order, extension-field component order, signs, compression, and endianness are correct.
- The exported proof verifies with the exported VK and public list in the target verifier library.
- Native and converted artifacts identify the same VK; record hashes for each representation.

## Constraint-security review

Use `$groth16-systems` for hints, custom solvers, optional branches, ranges, and constraint completeness. The TON overlay confirms BLS12-381 full/public witnesses, exported public order, registered TON encodings, and native-to-TON fixture parity before export.

## Tests

Add Go tests for valid proof, invalid witness, changed public value, wrong public-witness length, serialization round-trip, and conversion output. Add a cross-language fixture test in the TON repository that verifies locally and on-chain.

## Handoff

Report Go/Gnark/module versions, compile field, protocol, circuit/VK hashes, native and converted artifact paths, public-input order, local Gnark verification, conversion test, and `doctor` output.
