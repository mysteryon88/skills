---
name: groth16-systems
description: "Use when designing, explaining, debugging, testing, or reviewing Groth16 circuits and integrations, especially for R1CS/QAP derivations, underconstrained witnesses, setup provenance, artifact mismatches, public-input semantics, verifier boundaries, or replay/domain binding."
---

# Groth16 Systems

## Core principle

Make the exact relation explicit, then trace the same claim through witness generation, constraints, compiled artifacts, and verification. A successful proof establishes only the constrained relation, not the developer's unstated intent.

## Scope

Use this skill to:

- design the relation, public inputs, private witness, and boundary cases before writing a circuit;
- explain or derive the R1CS → QAP → Groth16 chain;
- debug failed proofs, unexpected witnesses, or public-signal mismatches;
- review circuit constraints, generated R1CS, verifier integration, and CRS assumptions;
- bind verified public inputs to application policy, domain, freshness, and state transitions.

Do not apply its R1CS/QAP model directly to PLONKish arithmetizations, Halo2, AIR, or STARK systems. Use their native model unless the request is explicitly comparative.

## Route the request

| Request | Read |
|---|---|
| Design, debug, or review a relation/circuit | [review-checklist.md](references/review-checklist.md) |
| Recall fields, polynomials, groups, or pairings | [algebra-foundations.md](references/algebra-foundations.md) |
| Explain or derive relation → R1CS → QAP | [relation-r1cs-qap.md](references/relation-r1cs-qap.md) |
| Reason about circuit compilation or witness generation | [circuit-compilers.md](references/circuit-compilers.md) |
| Explain Groth16 setup, proving, verification, or zero knowledge | [groth16-protocol.md](references/groth16-protocol.md) |
| Bind public inputs to application semantics, domain, or replay state | [application-binding.md](references/application-binding.md) |
| Inspect Circom/snarkjs artifacts or commands | [tooling.md](references/tooling.md) plus the review checklist |

Read only the references needed for the request.

## Working method

1. State the scalar field and relation `R(public, witness)`.
2. List public values in verifier order; list private and intermediate witness values separately.
3. Define valid boundaries and at least one invalid assignment.
4. Map every intended predicate to an actual constraint.
5. Treat witness generation and constraint generation as separate programs.
6. When artifacts exist, compare source, R1CS, symbols, witness, public signals, keys, and verifier behavior.
7. Give every artifact set and flattened public-input layout one reproducible identity.
8. Separate cryptographic verification from application authorization, replay protection, and state transition.
9. Follow the QAP and pairing layers only as far as the question requires.
10. Create examples independently, label pedagogical parameters, and verify version-sensitive claims against current official documentation.

## Output contract

For design work, return the relation, ordered interface, required constraints, application bindings, edge cases, and a minimal verification plan.

For explanations, keep one notation from relation through verification. If an example helps, derive a fresh one and show at least one valid or invalid substitution.

For debugging or review, lead with the verdict. Support each finding with the intended property, actual constraint or artifact behavior, a concrete counterexample when possible, impact, and the smallest verifiable correction.
