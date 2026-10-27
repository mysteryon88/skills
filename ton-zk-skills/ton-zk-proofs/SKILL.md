---
name: ton-zk-proofs
description: "Use when planning or implementing an end-to-end TON zero-knowledge workflow across circuits, Groth16 or experimental PLONK, BLS12-381 artifacts, export-ton-verifier, Tolk/FunC/Tact integration, testing, or deployment."
license: MIT
metadata:
  author: "mysteryon88 / zk-examples"
  ecosystem: "ton"
---

# TON ZK Proofs

## Overview

Route TON ZK work without confusing circuit correctness, verifier validity, application authorization, and release evidence.

## Operating Rules

- Install `$groth16-systems` separately for general theory and review; this archive adds TON requirements. If unavailable, report missing evidence, continue only independent TON inspection, and do not claim general review or end-to-end readiness.
- The bundled read-only helpers require Python 3.10+.
- Inspect the repository and installed tools before changing files.
- Treat the documented TON verifier path as BLS12-381; stop on BN254/bn128 until current platform support is independently proven.
- Scope monorepo artifacts to owners. Map a consumed sibling verifier/circuit with `--artifact-package`; only an independent non-TON package is non-blocking.
- Prefer Tolk for new work; preserve existing FunC/Tact architecture.
- Keep discovery read-only; do not install, regenerate keys, deploy, commit, or mutate remote state without an explicit request.
- Never hand-edit the cryptographic core of a generated verifier.
- End-to-end work requires all five focused skills; report an unavailable phase as missing.
- A full release also requires the independent evidence in [audit-handoff.md](references/audit-handoff.md); development workflow completion is not an audit pass.

## Workflow

1. Run the detector; inspect lockfiles, configs, circuits, artifacts, contracts, wrappers, and tests.
2. Select stack, proof system, curve, format, target, and maturity from [capability-matrix.md](references/capability-matrix.md).
3. Establish general `$groth16-systems` evidence, then identify the TON values and encodings that extend it.
4. Use `$ton-zk-circuit-workflows`; proof, public signals, and VK must verify from one build.
5. Use `$ton-zk-verifier-generation`; run `export-ton-verifier doctor` before rendering.
6. Use `$ton-zk-contract-integration`; separate proof validity, semantics, authorization, domain, replay, and transition.
7. Use `$ton-zk-testing`, then `$ton-zk-integration-review` for the TON boundary.
8. Keep `TON_INTEGRATION_READY` distinct from `FULL_ZK_RELEASE_READY`; any required `NOT_ASSESSED` phase blocks the latter, and owner acceptance cannot replace evidence.
9. For requested deployment, follow [deployment-checklist.md](references/deployment-checklist.md) and require a separate mainnet gate.

## Quick Reference

| Need | Skill |
|---|---|
| Circuit/proof/artifact creation | `$ton-zk-circuit-workflows` |
| `.zkey`, VK, generated verifier/wrapper | `$ton-zk-verifier-generation` |
| Cells, BoCs, messages, nullifiers, policy | `$ton-zk-contract-integration` |
| Negative, replay, gas, code-size tests | `$ton-zk-testing` |
| TON integration verdict | `$ton-zk-integration-review` |
| Full ZK release evidence | [audit handoff](references/audit-handoff.md) |

```bash
python3 <skills-root>/ton-zk-proofs/scripts/detect_project.py --root . --format json
python3 <skills-root>/ton-zk-proofs/scripts/detect_project.py --root . --package packages/ton-app --format json
python3 <skills-root>/ton-zk-proofs/scripts/detect_project.py --root . --package packages/ton-app --artifact-package packages/verifier --format json
npm ls export-ton-verifier snarkjs --depth=0
```

Use [project routing](references/project-routing.md), [sources/versioning](references/source-of-truth.md), or the [deployment checklist](references/deployment-checklist.md) as needed.

## Common Mistakes

- Starting contract work before defining the statement and public-input order.
- Assuming a valid proof authorizes the requested TON action.
- Mixing proof, public inputs, and VK from different builds.
- Treating a getter as a state-changing security boundary.
- Calling experimental PLONK production-ready without current capability and test evidence.
- Deploying after a green getter without checking runtime domain, code hash, replay, fees, and receiver.

## Completion Gate

Report inventory, dependency specs/resolved versions, capability, local verification, `doctor`, generated targets, public-input semantics, replay/domain, tests, gas/code size, setup provenance, and risks. For deployment also report network/global_id, address, hashes, transaction, fees, balance, smoke tests, and approval gate.
