# TON setup overlay

Use `$groth16-systems` for Groth16 trapdoors, development-versus-production setup, ceremony assumptions, contribution verification, secret handling, and incident policy. This reference binds the selected setup to the TON release artifacts.

## Groth16 BLS12-381 release binding

For the supported TON route, record separate SHA-256 hashes for:

- final Powers of Tau material;
- exact R1CS;
- final circuit-specific `.zkey`;
- exported verification key;
- generated TON verifier and wrapper;
- compiled TON code and the proof/public fixtures used by its tests.

Preserve successful output from the pinned checks against those exact files:

```bash
npx --no-install snarkjs powersoftau verify pot_final.ptau
npx --no-install snarkjs zkey verify circuit.r1cs pot_final.ptau circuit_final.zkey
npx --no-install snarkjs zkey export verificationkey circuit_final.zkey verification_key.json
```

A matching VK hash alone is not complete setup-artifact identity. Any R1CS or public-layout change that produces new setup/key material also requires regenerated TON verifier, wrapper, fixtures, and release record.

## PLONK universal SRS gate

The experimental TON PLONK route still requires a reviewed universal SRS. Record curve, capacity, contribution attestations, SHA-256, verification command output, and the release record binding the SRS to R1CS, final `.zkey`, transcript inputs, generated verifier, and fixtures.

Fail the release if `powersoftau verify` fails, capacity is insufficient, the contribution chain cannot be reviewed, a recorded hash differs, or the build silently downloads or replaces the SRS.

## TON release boundary

- Never place witness files, private inputs, ceremony entropy, or temporary contributor state in the TON package, wrapper fixtures, build logs, or deployment record.
- Keep development and production verifier addresses/configuration unmistakably separate.
- Record the response if the setup, coordinator state, or deployed VK is suspected compromised.
