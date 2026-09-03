# TON-supported artifact formats

Use `$groth16-systems` for general artifact identity, scalar/base-field distinctions, canonical encodings, point validation, and rejection of malformed data. The installed `export-ton-verifier doctor` is authoritative for TON format support.

## Circom/snarkjs `.zkey`

Require the supported Groth16 or explicitly selected experimental PLONK route, BLS12-381, the manifest public-input count, verified R1CS/setup provenance, and proof/public fixtures produced from the same final `.zkey`.

## snarkjs verification-key JSON

Confirm `protocol`, `curve`, public-input count (`IC.length - 1` for Groth16), point component order, and a successful local proof verification with the exact file. A curve alias must not hide BN254/bn128.

## Native Gnark and Arkworks

- Gnark input must be identified as the supported native format, BLS12-381, and Groth16, with a native Go verification test.
- Arkworks input must declare or encode BLS12-381 Groth16, decode under the pinned library, expose the expected public count, and pass a native Rust verification test.

Do not infer a native format from the filename alone. Compare native and generated TON representations through recorded VK/artifact identity and cross-language fixtures.

## TON validation boundary

Before embedding fixed VK points, the generation path must establish the general point invariants. At runtime, the generated verifier and receiver must reject malformed attacker-controlled proof points and enforce exact TON message layout before TVM BLS operations.

Do not repair an input by reducing scalars, swapping G2 components, changing the curve label, padding/truncating coordinates, deleting fields, or altering public-input counts. Regenerate from the source stack or fix the converter and retest both native and TON paths.
