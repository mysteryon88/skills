# Experimental PLONK on TON

PLONK support in this collection is deliberately marked experimental. The reviewed route uses Circom/snarkjs artifacts over BLS12-381 and generated Tolk or FunC verifiers.

## Entry conditions

Proceed only when all are true:

- the installed `export-ton-verifier` help exposes PLONK for the intended target;
- `doctor` accepts the exact artifact, BLS12-381 curve, public-input count, and template;
- local `snarkjs plonk verify` succeeds;
- the repository includes valid and adversarial on-chain tests;
- gas/code size and TVM tuple/transcript limits are measured;
- the experimental status is explicit in deployment/review documentation.
- the PLONK universal SRS has an exact source and SHA-256, BLS12-381 curve, power/capacity, contribution evidence, successful `snarkjs powersoftau verify` output, and a release record binding it to the VK and generated verifier.

## Public-input and transcript constraints

The generated verifier may use a Keccak transcript and tuple-based helpers with a finite item limit. Use the installed generator's exported constant or `doctor` result rather than copying an old number. Test the exact maximum and one-over-limit case in generator tests.

Reject negative or non-canonical scalar inputs. Do not allow client-side modulo reduction to create multiple application representations of one field element.

## Target matrix

| Target | Collection policy |
|---|---|
| Tolk PLONK | Experimental, supported only after diagnosis/tests |
| FunC PLONK | Experimental, supported only after diagnosis/tests |
| Tact PLONK | Block unless current installed generator and upstream tests prove support |

## Required tests

- valid local and on-chain proof;
- tampered proof and each public input;
- negative, field-order, field-order-plus-one, and oversized inputs;
- public-input count at normal, maximum, and over-limit values;
- transcript serialization mismatch;
- wrapper/message target mismatch;
- getter and internal-message behavior;
- gas and code-size snapshots.

## Production decision

An experimental implementation can be technically correct and still be inappropriate for production. Require explicit owner acceptance of maturity, audit scope, operational rollback, compatibility/version pinning, and monitored limits.

For a `production-candidate` proof-context manifest, require explicit experimental approval with rationale and current executable evidence. Also require `setup.kind=plonk-universal-srs`; verify the exact `.ptau` bytes with `powersoftau verify`, check that the circuit fits its capacity, and bind its SHA-256 and contribution history to the release record. Absence of either gate is a release blocker, not a warning.
