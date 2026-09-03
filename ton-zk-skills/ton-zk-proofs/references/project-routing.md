# Project routing

## First pass

Run the detector from the collection without modifying the repository:

```bash
python3 <skills-root>/ton-zk-proofs/scripts/detect_project.py --root . --format json
```

For a known monorepo boundary, select it explicitly:

```bash
python3 <skills-root>/ton-zk-proofs/scripts/detect_project.py \
  --root . --package packages/ton-app --format json
```

If the selected TON package imports verifier artifacts from a sibling workspace/module, name every such package explicitly:

```bash
python3 <skills-root>/ton-zk-proofs/scripts/detect_project.py \
  --root . --package packages/ton-app \
  --artifact-package packages/verifier --format json
```

The detector associates artifacts with the nearest package manifest and emits package-scoped blockers. Explicit artifact packages are treated as part of the selected TON boundary, so their actual normalized curve is included in warnings. A BN254 artifact in an independent non-TON package remains advisory. The detector does not build an implicit workspace dependency graph; an unmapped cross-package consumer is incomplete inventory and requires manual tracing.

Then inspect, in this order:

1. Every relevant nested `package.json`, `go.mod`, `Cargo.toml`, and `Acton.toml`, plus lockfiles and package engines. Use the detector's `manifests` and `dependencyLocations` fields to avoid assuming the root manifest owns the ZK package.
2. `blueprint.config.*`, `tact.config.*`, compile descriptors, contract entry points, and wrapper-generation configuration.
3. Circuit sources (`.circom`, `.no`, Go/Gnark, Rust/Arkworks), statement documentation, and public/private signal declarations.
4. Setup, proof, public-signal, and VK artifacts (`.ptau`, `.zkey`, JSON, native `.bin`, or bundles), together with the command that produced them.
5. Generated contracts (`.tolk`, `.fc`, `.tact`) and TypeScript wrappers.
6. Receivers, public-input mapping, replay/domain policy, storage layout, and state transitions consuming verification results.
7. Tests, gas snapshots, deployment scripts, addresses, code/data hashes, and network configuration.

The detector does not classify a generic `vk.json` by filename alone; it requires a recognized key structure. Canonical `verification_key*.json` names remain artifact hints whose curve/protocol must still be confirmed. Output is an inventory and routing hint, not a security conclusion; confirm critical conclusions against source, lockfiles, installed tool help, and executable behavior.

For release work, the full [audit handoff](audit-handoff.md) is required; secure-development workflow completion is not equivalent to independent audit evidence.

## Routing rules

| Evidence found | Primary skill | Follow-up |
|---|---|---|
| Circuit source but no reviewed constraint contract | `$ton-zk-circuit-workflows` | Build signal inventory and adversarial constraint checks |
| Circuit source but no proof/VK | `$ton-zk-circuit-workflows` | Produce a locally verified artifact set |
| Proof/VK but no TON contract | `$ton-zk-verifier-generation` | Diagnose format/curve/protocol and generate reproducibly |
| Generated verifier but no application policy | `$ton-zk-contract-integration` | Define parser, semantic, network, and replay boundary |
| Integration with weak or missing tests | `$ton-zk-testing` | Build adversarial and resource matrix |
| Release, deployment, or security question | `$ton-zk-integration-review` | Require the full [audit handoff](audit-handoff.md); TON integration review alone is insufficient |
| Multiple generations or stale wrappers | `$ton-zk-verifier-generation` | Match hashes and regenerate from the selected source artifact |
| External receiver performs expensive verification | `$ton-zk-contract-integration` | Review pre-accept checks and balance-loss tests |

## New project

Start with the smallest end-to-end Groth16/BLS12-381 circuit that exercises the intended public-input types. Review the constraints, prove and verify locally, generate a Tolk verifier, validate a proof-context manifest, test in Sandbox, and only then add application state and deployment automation. Do not begin with a privacy-token architecture, large Merkle tree, custom serialization, or mainnet deployment before the minimal path is reproducible.

## Existing project

Preserve the project's package manager, framework, contract language, message/storage layouts, and test runner. Do not introduce Acton into Blueprint or replace FunC/Tact with Tolk merely because another route is preferred for new work. A migration is a separate task with compatibility tests and a deployment plan.

In a monorepo, treat each package or module as a possible toolchain boundary. Use `packageBoundaries`, select the target with `--package`, add consumed sibling artifact roots with repeatable `--artifact-package`, and report conflicting dependency versions instead of silently choosing the first manifest found.

## Ambiguous artifacts

When a file named `verification_key.json` lacks a clear curve or protocol:

- inspect it without rewriting it;
- run the installed `doctor` command;
- trace the command or source that generated it;
- compare it with proof/public fixtures and local verification;
- block generation if provenance remains ambiguous.

When multiple `.zkey` or VK files exist, do not choose the newest modification time. Match cryptographic hashes, generation scripts, test imports, public-input count/order, wrapper constants, and contract constants.

When a JSON file only contains generic words such as `curve` or `protocol`, do not classify it as a proof artifact unless its file name or structure supports that conclusion.

## Deployment route

Before any live write, use [deployment-checklist.md](deployment-checklist.md). Keep the sequence explicit:

```text
clean reproducible build
  -> Sandbox
  -> testnet
  -> deployed code/data identity
  -> getter and receiver smoke tests
  -> fee, gas, value, reserve and balance review
  -> mainnet approval
```

A request to deploy does not authorize dependency upgrades, key generation, contract funding, mainnet use, or administrative changes unless those targets and effects are explicitly approved.

## Repository hygiene

Generated verifier output, wrappers, and public fixtures may be checked in when reproducible review requires them, but record the source artifact and exact generation command. Do not commit witnesses, private inputs, entropy, production proving secrets, unreviewed ceremony material, wallet secrets, or generated proof/key artifacts to this skill collection.
