# Circom and snarkjs Tooling

Use this reference when compiled artifacts or CLI evidence are available. Commands and formats are version-sensitive: run `circom --help`, `snarkjs --help`, and the relevant subcommand help before relying on flags in a live project.

## Compile and inspect

```bash
circom circuit.circom --r1cs --wasm --sym --inspect
snarkjs r1cs info circuit.r1cs
snarkjs r1cs print circuit.r1cs circuit.sym
```

`--r1cs` emits the constraint system, `--wasm` emits witness-generation code, and `--sym` emits the symbol mapping used for annotated inspection. `--inspect` asks Circom for additional constraint checks.

## Calculate and check a witness

```bash
snarkjs wtns calculate circuit_js/circuit.wasm input.json witness.wtns
snarkjs wtns check circuit.r1cs witness.wtns
```

A successful witness calculation proves only that the generator produced values. `wtns check` tests those values against the compiled R1CS; neither command proves that the R1CS matches the intended relation.

## Check keys and proofs

```bash
snarkjs zkey verify circuit.r1cs powers_of_tau.ptau circuit_final.zkey
snarkjs groth16 prove circuit_final.zkey witness.wtns proof.json public.json
snarkjs groth16 verify verification_key.json public.json proof.json
```

Do not treat an initial Groth16 `zkey` without valid phase-2 contributions as production-ready. Verify the ceremony transcript and confirm the key matches the reviewed circuit.

## Artifact roles

| Artifact | What it establishes |
|---|---|
| `.circom` source | Intended circuit structure |
| `.r1cs` | Constraints actually proved |
| `.sym` | Signal-to-wire mapping for inspection |
| witness generator | How assignments are computed |
| `.wtns` | One concrete assignment |
| `.ptau` / `.zkey` | Setup material and circuit-specific proving data |
| `public.json` | Ordered public values supplied to verification |
| `proof.json` | Serialized Groth16 proof points |

Pin tool versions in reproducible projects. When commands, public-signal conventions, or serialized formats affect a conclusion, prefer observed artifacts and current official documentation over this summary.

## Artifact identity

Treat a usable proof bundle as one versioned contract. Record:

- source revision and compiler/backend versions;
- proof system, curve, constraint-system hash, and counts;
- setup/transcript and final proving-key identity where applicable;
- verification-key hash;
- ordered public-input names, types, ranges, and encodings;
- proof/public fixtures and exact generation commands;
- converter, generated verifier, and wrapper hashes when those layers exist.

Verify that the local verifier accepts the exact proof, public list, and key, rejects a changed public value, and reports the expected public-input count. Native and converted representations need an explicit mapping test.

Any change to constraints, public order or encoding, setup, key, compiler output, generator interpretation, or proof system creates a new artifact identity. Regenerate dependent fixtures and verifier code instead of silently overwriting provenance.

## Official references

- [Circom: compiling circuits](https://docs.circom.io/getting-started/compiling-circuits/)
- [snarkjs README and CLI workflow](https://github.com/iden3/snarkjs/blob/master/README.md)
