# Circom and snarkjs workflow

## Preconditions

Record versions before generating artifacts:

```bash
node --version
circom --version
npx --no-install snarkjs --help
```

Use the repository's pinned dependencies where present. A compiler or snarkjs change can alter artifacts and must be treated as a reproducibility change.

## Compile over BLS12-381

```bash
mkdir -p circuits/Example
cd circuits/Example
circom Example.circom --r1cs --wasm --sym --prime bls12381 --inspect
npx --no-install snarkjs r1cs info Example.r1cs
npx --no-install snarkjs r1cs print Example.r1cs Example.sym > constraints.txt
```

Treat every `--inspect` warning as a review item. Check that the reported public/private input counts and outputs match the intended interface, and compare the constraint count with the reviewed baseline. Use the `.sym` file to map signal names to the flattened public-input order. Review every `<--`/`-->` assignment for a matching `===` constraint, and never substitute `assert(signalExpression)` for a verifier-enforced constraint.

## Development Groth16 setup

Use fresh entropy and keep it out of shell history and logs in sensitive environments:

```bash
PTAU_ENTROPY="$(openssl rand -hex 32)"
ZKEY_ENTROPY="$(openssl rand -hex 32)"

npx --no-install snarkjs powersoftau new bls12-381 12 pot12_0000.ptau -v
npx --no-install snarkjs powersoftau contribute pot12_0000.ptau pot12_0001.ptau \
  --name="development contribution" -v -e="$PTAU_ENTROPY"
npx --no-install snarkjs powersoftau prepare phase2 pot12_0001.ptau pot12_final.ptau -v
npx --no-install snarkjs groth16 setup Example.r1cs pot12_final.ptau Example_0000.zkey
npx --no-install snarkjs zkey contribute Example_0000.zkey Example_final.zkey \
  --name="development phase2 contribution" -v -e="$ZKEY_ENTROPY"
npx --no-install snarkjs zkey export verificationkey Example_final.zkey verification_key.json
```

Choose the powers-of-tau size from the actual constraint count. The value above is illustrative, not a production recommendation. See `trusted-setup.md` before any production use.

## Witness, proof, and local verification

```bash
printf '%s\n' '{"a":"342","b":"1245"}' > input.json
node Example_js/generate_witness.js Example_js/Example.wasm input.json witness.wtns
npx --no-install snarkjs wtns check Example.r1cs witness.wtns
npx --no-install snarkjs groth16 prove Example_final.zkey witness.wtns proof.json public.json
npx --no-install snarkjs groth16 verify verification_key.json public.json proof.json
```

The final command must return a successful verification before TON generation. Keep `input.json` and `witness.wtns` out of the repository when they contain private data.

## Experimental PLONK

For a repository intentionally using the experimental TON PLONK route:

```bash
npx --no-install snarkjs plonk setup Example.r1cs pot12_final.ptau Example_plonk.zkey
npx --no-install snarkjs zkey export verificationkey Example_plonk.zkey verification_key_plonk.json
npx --no-install snarkjs plonk prove Example_plonk.zkey witness.wtns proof_plonk.json public_plonk.json
npx --no-install snarkjs plonk verify verification_key_plonk.json public_plonk.json proof_plonk.json
```

After local verification, run the installed `export-ton-verifier doctor` for Tolk or FunC and enforce its current public-input/transcript limits.

## Circuit checks before handoff

Complete the general `$groth16-systems` circuit and artifact review, then apply the [TON circuit overlay](circuit-security.md). Confirm BLS12-381, registered TON encodings, unchanged public order from `public.json` through the wrapper/contract, recorded constraint/artifact identity, and local verification of the exact final bundle.
