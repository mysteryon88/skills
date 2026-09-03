# Noname workflow

Noname can produce an R1CS/witness path compatible with snarkjs. CLI details can change; inspect the installed `noname --help` and repository scripts first.

The upstream repository is archived in the 2026-08-06 reference snapshot and its README still labels the language beta with known limitations. Use this route when the target repository already depends on Noname or compatibility is explicitly required. Pin the exact commit/compiler version and do not introduce Noname as the default for a new production circuit without an owner decision and current executable evidence.

## Baseline flow

1. Run Noname's type/constraint checks.
2. Execute the circuit with the BLS12-381 R1CS backend.
3. Inspect the resulting R1CS and witness with snarkjs.
4. Run a BLS12-381 setup, proof, and local verification.
5. Export `.zkey` or verification-key JSON for the TON generator.

Typical commands used by the TON examples are:

```bash
noname check
noname run --backend r1cs-bls12-381 \
  --private-inputs "$PRIVATE_INPUTS_JSON" \
  --public-inputs "$PUBLIC_INPUTS_JSON"

npx --no-install snarkjs r1cs info Circuit.r1cs
npx --no-install snarkjs wtns check Circuit.r1cs Circuit.wtns
```

Then follow the Groth16 setup/prove/verify sequence from `circom-snarkjs.md`, substituting the generated R1CS and witness paths.

## Review points

Complete the `$groth16-systems` constraint and witness-generation review before applying the TON-specific export checks.

- Confirm Noname's public input object flattening and order. Do not infer order from JSON property display alone.
- Check backend-specific BLS12-381 export behavior.
- Re-run `noname check` and local proof verification after dependency/compiler changes.
- Keep the public/private JSON schemas next to the circuit source and include them in the artifact contract.

## Handoff

Provide the Noname source hash, installed version, backend name, R1CS/witness generation command, constraint counts, public-input mapping, `.zkey`/VK hash, proof/public fixture hash, and local snarkjs verification result.
