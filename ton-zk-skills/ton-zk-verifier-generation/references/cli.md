# export-ton-verifier CLI workflow

Always inspect the locally selected package before relying on this reference.

## Preflight

```bash
node --version
npm ls export-ton-verifier snarkjs --depth=0
npx --no-install export-ton-verifier --help
```

If the package is absent, stop and ask before installing it. If the repository has a lockfile, do not replace its version with `latest` as part of an unrelated task.

## Diagnose first

```bash
npx --no-install export-ton-verifier doctor ./circuits/verification_key.json --tolk
npx --no-install export-ton-verifier doctor ./circuits/verification_key.json --func
npx --no-install export-ton-verifier doctor ./circuits/verification_key.json --tact
npx --no-install export-ton-verifier doctor ./circuits/verification_key.json --json
```

Use only language flags exposed by the installed help. The report should establish source format, protocol, curve, number of public inputs, target language, template path, and pass/fail checks.

A blocked report is a stop condition. Do not edit the artifact to make the report cosmetically pass.

## Generate contracts

```bash
# Tolk default
npx --no-install export-ton-verifier ./circuits/verification_key.json ./contracts/verifier.tolk

# Named Tolk receiver/getter shape
npx --no-install export-ton-verifier ./circuits/verification_key.json ./contracts/verifier.tolk \
  --contract-name ApplicationVerifier

# Explicit FunC
npx --no-install export-ton-verifier ./circuits/verification_key.json ./contracts/verifier.fc --func

# Supported Tact/Groth16
npx --no-install export-ton-verifier ./circuits/verification_key.json ./contracts/verifier.tact --tact
```

Generate to a temporary or new path first when replacing reviewed output. Compare the result, then update intentionally.

## Generate wrappers

```bash
# Generate contract and place the matching wrapper
npx --no-install export-ton-verifier ./circuits/verification_key.json ./contracts/verifier.tolk \
  --wrapper-dest ./wrappers/ --force

# Copy a wrapper independently
npx --no-install export-ton-verifier import-wrapper ./wrappers/Verifier_tolk.ts --groth16 --force
npx --no-install export-ton-verifier import-wrapper ./wrappers/Verifier_func.ts --groth16 --func --force
npx --no-install export-ton-verifier import-wrapper ./wrappers/Verifier_tolk_plonk.ts --plonk --tolk --force
npx --no-install export-ton-verifier import-wrapper ./wrappers/Verifier_func_plonk.ts --plonk --func --force
```

Keep protocol/language in the filename when multiple wrappers coexist.

## Encode proof messages

```bash
npx --no-install export-ton-verifier proof-to-message \
  ./circuits/proof.json ./circuits/public.json --groth16 --tolk

npx --no-install export-ton-verifier proof-to-message \
  ./circuits/proof.json ./circuits/public.json --plonk --tolk \
  --format hex --output ./fixtures/verify-body.hex
```

`proof-to-message` constructs a supported message body; it does not add application authorization, domain separation, or replay protection.

## Required follow-through

After generation:

1. Hash the input and generated outputs.
2. Compile with the repository's existing build command.
3. Generate/verify a proof locally.
4. Run getter and internal-message tests with valid and invalid fixtures.
5. Verify the consuming parser enforces the exact generated proof-element sizes and rejects trailing bits, bytes, refs, keys, or tuple items before TVM BLS operations.
6. Validate the proof-context manifest and run state-changing replay/domain tests, not only the getter.
7. Update reviewed gas/code-size snapshots and any external-message balance-loss evidence.
8. Record the command and generator version in repository documentation or a reproducibility manifest.
