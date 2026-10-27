---
name: ton-zk-verifier-generation
description: "Use when inspecting a .zkey, verification_key.json, Gnark JSON/binary, or Arkworks bundle and generating TON Groth16 or experimental PLONK verifiers and TypeScript wrappers with export-ton-verifier for Tolk, FunC, or Tact."
license: MIT
metadata:
  author: "mysteryon88 / zk-examples"
  ecosystem: "ton"
---

# TON ZK Verifier Generation

## Overview

Turn a locally verified artifact into reproducible TON contract output. Diagnosis precedes rendering: format, protocol, BLS12-381 curve, public-input count, target template, and TVM limits must be known.

## Operating Rules

- Inspect the installed package and lockfile; do not silently change generator versions.
- Use the locally installed or explicitly approved `export-ton-verifier` and its supported Node.js LTS; inspect project engines and installed help.
- Run `export-ton-verifier doctor` for the exact artifact and language.
- Fail closed on unsupported curve, format, protocol, template, point/subgroup validation, or limits.
- Prefer Tolk; use `--func` or `--tact` only for an explicitly supported target.
- Treat the generated verifier and wrapper as reproducible output. Preserve SPDX/license headers; see [licensing.md](references/licensing.md).
- Command snippets assume a repository-pinned local package; do not let `npx` fetch or replace `export-ton-verifier` without explicit approval.

## Workflow

1. Identify `.zkey`, snarkjs VK JSON, native Gnark JSON/binary, or Arkworks bundle/VK JSON.
2. Record local CLI version/help and run `doctor`.
3. Confirm protocol, BLS12-381, source format, public-input count, template, and all checks.
4. Render to an intentional path with a stable contract name.
5. Generate/copy the matching TypeScript wrapper.
6. Use library helpers or `proof-to-message` for a fixture; do not invent parallel serialization.
7. Compile immediately and test valid, malformed/tampered, one-byte-short, valid-prefix-plus-tail, and extra-ref cases at the integration parser boundary.
8. Record input/output hashes, command, generator version, target, and VK fingerprint.

Read [CLI](references/cli.md), [formats](references/formats.md), [language targets](references/language-targets.md), and [experimental PLONK](references/plonk.md).

## Quick Reference

```bash
npm ls export-ton-verifier --depth=0
npx --no-install export-ton-verifier --help
npx --no-install export-ton-verifier doctor ./circuits/verification_key.json --tolk
npx --no-install export-ton-verifier ./circuits/verification_key.json ./contracts/verifier.tolk --contract-name ApplicationVerifier
npx --no-install export-ton-verifier import-wrapper ./wrappers/Verifier_tolk.ts --groth16 --force
npx --no-install export-ton-verifier proof-to-message ./circuits/proof.json ./circuits/public.json --groth16 --tolk
```

| Target | Policy |
|---|---|
| Tolk Groth16 | Preferred |
| FunC Groth16 | Supported for existing/compatibility projects |
| Tact Groth16 | Use only when installed template supports it |
| Tolk/FunC PLONK | Experimental |
| Tact PLONK | Block without current upstream proof of support |

## Common Mistakes

- Rendering before `doctor` or feeding BN254/bn128 to BLS12-381 templates.
- Mixing wrapper, protocol, language, VK, or circuit versions.
- Hand-editing pairing, transcript, scalar, point, or VK code.
- Assuming a named Tolk contract keeps an old getter name.
- Treating `proof-to-message` as authorization or replay protection.
- Assuming the generated BLS opcode rejects oversized slices instead of enforcing exact 48/96-byte component lengths in the receiver.

## Completion Gate

Provide diagnosis, generator version, input format/hash, protocol, BLS12-381 evidence, public-input count, target, commands, output hashes, license status, build result, and valid/invalid plus exact-length parser results. A generated verifier is incomplete until reproducible and tested.
