# TON ZK capability matrix

Use this matrix to choose a route before writing code. “Supported” means the repository/toolchain documents and examples cover the path; it does not mean the application is audited or safe for production.

## On-chain verifier routes

| Circuit/prover source | Proof system | Curve | Generator input | Tolk | FunC | Tact | Status |
|---|---|---|---|---:|---:|---:|---|
| Circom + snarkjs | Groth16 | BLS12-381 | `.zkey` or snarkjs VK JSON | Yes | Yes | Yes | Primary route |
| Noname + snarkjs | Groth16 | BLS12-381 | `.zkey` or snarkjs VK JSON | Yes | Yes | Yes | Supported through R1CS/snarkjs |
| Gnark | Groth16 | BLS12-381 | native JSON, native `.bin`, or converted snarkjs JSON | Yes | Yes | Yes | Supported in the 1 reference snapshot |
| Arkworks | Groth16 | BLS12-381 | native bundle/VK JSON or converted snarkjs JSON | Yes | Yes | Yes | Supported in the 1 reference snapshot |
| Circom + snarkjs | PLONK | BLS12-381 | `.zkey` or compatible VK JSON | Yes | Yes | No documented template | Experimental |

## Hard constraints

- The verifier templates in this collection target TON/TVM BLS12-381 operations. A BN254, bn128, or alt_bn128 artifact is a blocking mismatch, not an encoding inconvenience.
- Proof, public signals, and VK must be generated from the same circuit build and setup.
- Tolk was the default target in the 1 `export-ton-verifier` reference snapshot. Select FunC with `--func`; select supported Tact/Groth16 with `--tact`.
- PLONK has transcript and public-input limits that must be checked by the installed `doctor` command. Do not copy a numeric limit from old documentation into application code.
- Tact support is treated as Groth16-only unless the installed generator and tests prove otherwise.
- Fift output is a compiler/build artifact, not a verifier source target in this workflow.
- TVM BLS operations do not replace an exact application parser. Reject short values, accepted prefixes with trailing data, non-byte-aligned slices, unexpected refs, and extra public-input items before verification.
- A production-candidate experimental PLONK route requires explicit approval, current capability evidence, and the stricter test/review gates documented by this collection.

## Input-format decision

1. Prefer the original `.zkey` when a Circom/snarkjs pipeline is reproducible.
2. Prefer native Gnark/Arkworks artifacts when the installed generator supports the exact format and local native verification is part of CI.
3. Use conversion to snarkjs JSON only with tests that compare public-input order, point coordinates/encoding, protocol, curve, and local verification on both sides.
4. Reject a JSON file whose provenance, curve, protocol, or input count cannot be established.

## Target-language decision

- **Tolk:** default for a new TON verifier or application that can use modern typed TON tooling.
- **FunC:** select when an existing codebase, audit baseline, or compatibility requirement is FunC.
- **Tact:** select for supported Groth16 integrations when the application is already Tact and generated verifier composition is understood.

Generated verifier language does not decide application architecture. A project may isolate the verifier and call it through a message, embed it in an application contract, or compose it as a trait/module. Review atomicity, replay, and asynchronous behavior for the chosen pattern.

## Unsupported or separately scoped routes

- BN254/alt_bn128 on the documented TON BLS verifier path.
- UltraHonk, Halo2, STARK, zkVM receipts, or arbitrary proof systems without a separately implemented and validated TON verifier.
- A generic off-chain attestation service presented as trustless on-chain proof verification.
- Production deployment based only on tutorial trusted setup or educational contracts.

## Evidence to record

For the selected row, record source stack/version, proof system, curve, generator version, input format/hash, public-input count/order, target language, generated output hash, local verify result, TON test result, gas/code size, setup provenance, and integration review status.
