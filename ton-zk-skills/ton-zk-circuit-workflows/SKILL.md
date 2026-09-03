---
name: ton-zk-circuit-workflows
description: "Use when creating, compiling, proving, or converting TON-compatible circuits and artifacts with Circom, Noname, Gnark, Arkworks, snarkjs, gnark-to-snarkjs, or ark-snarkjs, especially when curve selection, public-input order, witness generation, or trusted setup matters."
license: Apache-2.0
metadata:
  author: "mysteryon88 / zk-examples"
  ecosystem: "ton"
---

# TON ZK Circuit Workflows

## Overview

Adapt an already defined and reviewed proof relation into mutually consistent BLS12-381 artifacts accepted by the TON toolchain.

## Operating Rules

- Use `$groth16-systems` for relation design, constraint completeness, Groth16 setup assumptions, artifact identity, and general adversarial review.
- Use BLS12-381 for this TON route; Circom commands must include `--prime bls12381`.
- Use the proving stack, Node.js, and TON toolchain selected by the target project; inspect engines, lockfiles, and installed help.
- Verify constraints and the exact proof locally before verifier generation.
- Apply the [TON circuit overlay](references/circuit-security.md) to curve choice, field/byte encodings, TON hashes, runtime domain values, and exported public-input order.
- Apply the [TON setup overlay](references/trusted-setup.md) to release binding and TON artifact provenance.
- Command snippets assume the named tools are already pinned and installed; do not let `npx` fetch a missing package without explicit approval.

## Workflow

1. Consume the reviewed relation, public-input contract, constraint evidence, setup mode, and artifact identity from `$groth16-systems`.
2. Compile the TON route under BLS12-381 and confirm the exported public/private/constraint counts still match that evidence.
3. Apply TON address, cell, hash-limb, domain, and public-order encodings.
4. Generate and locally verify the exact proof, public list, and VK.
5. Export a supported snarkjs or native Gnark/Arkworks artifact for `export-ton-verifier`.
6. Freeze the TON-specific hashes, profiles, commands, target, and setup binding in [artifact-contract.md](references/artifact-contract.md).

After the general review, use the TON overlays: [circuit security](references/circuit-security.md), [Circom/snarkjs](references/circom-snarkjs.md), [Noname](references/noname.md), [Gnark](references/gnark.md), [Arkworks](references/arkworks.md), and [trusted setup](references/trusted-setup.md).

## Quick Reference

| Stack | TON-facing artifact | Local evidence |
|---|---|---|
| Circom/snarkjs | BLS12-381 `.zkey` or VK JSON | `snarkjs ... verify` |
| Noname | BLS12-381 R1CS/witness + snarkjs artifacts | Noname checks + snarkjs verify |
| Gnark | Native or converted BLS12-381 Groth16 artifacts | `go test` + Gnark verify |
| Arkworks | Native or converted BLS12-381 Groth16 artifacts | `cargo test` + Arkworks verify |

```bash
circom circuit.circom --r1cs --wasm --sym --prime bls12381 --inspect
npx --no-install snarkjs r1cs info circuit.r1cs
npx --no-install snarkjs groth16 verify verification_key.json public.json proof.json
```

## Common Mistakes

- General `$groth16-systems` review evidence is missing or belongs to another circuit build.
- Conversion changes public-input order, G2 component order, sign, or endianness.
- Proof/public/VK files come from different source, compiler, setup, or build versions.
- A local single-contributor setup is described as production ceremony security.
- A TON address, cell hash, domain, or limb encoding lacks a registered profile and golden vector.

## Completion Gate

Report source/hash, tool versions, protocol, BLS12-381 evidence, statement/signal inventory, constraint counts, public-input contract, hint and range review, domain binding, setup mode, local/adversarial verification, exported formats/hashes, and remaining circuit-security risks. Do not hand an ambiguous or unverified artifact to generation.
