# Full ZK audit handoff

`$ton-zk-integration-review` owns only the circuit-to-TON integration boundary. A full release decision requires independent evidence for every phase below; secure development work performed with the other skills is not automatically an independent audit.

| Required phase | Minimum handoff |
|---|---|
| Circuit audit | Frozen circuit/constraint identity, intended-versus-implemented statement, underconstraint and malicious-witness analysis, findings, fixes, and retest evidence |
| Proof-system audit | Protocol/version/curve assumptions, verifier equation/transcript review, soundness-relevant deviations, and validated findings |
| Prover/converter audit | Exact prover and conversion versions, artifact transformations, public-input preservation, negative tests, and review outcome |
| Setup/SRS review | Parameters, source, capacity, exact hashes, transcript/contribution verification, ceremony scope, and release binding |
| TON integration audit | `TON_INTEGRATION_READY` evidence from `$ton-zk-integration-review` |
| Deployment evidence | Exact reviewed artifacts, network/domain/address/code identity, testnet transactions, gas/balance results, and approval |

Each phase status is `PASS`, `FAIL`, `BLOCKED`, `NOT_IN_SCOPE`, or `NOT_ASSESSED`. `FULL_ZK_RELEASE_READY` requires `PASS` for all six phases. `NOT_IN_SCOPE`, `NOT_ASSESSED`, or a material `BLOCKED` result keeps `FULL_ZK_RELEASE_NOT_READY`; owner acceptance cannot promote missing evidence to a technical pass.
