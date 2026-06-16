# Mina Protocol Agent Skills

Short description: `mina-protocol` helps agents learn, build, test, debug, deploy, and review Mina Protocol zkApps with o1js.

It is focused on:

- Mina/o1js zkApps: `SmartContract`, state, preconditions, proofs, witnesses, permissions, and `AccountUpdate` trees.
- Circuit and proof design: provable assertions, hashes, signatures, Merkle proofs, `ZkProgram`, recursion, and verifiable compute modules.
- App patterns: off-chain state commitments, reducers, custom tokens, privacy credentials, nullifiers, frontend prover flows, and deployment workflows.
- Security review: authorization, permission matrices, verification keys, replay risks, token accounting, private-data leakage, and transaction structure.
- Agent-ready workflows: learning plans, coding task cards, test recipes, bug patterns, implementation notes, audit reports, and source maps.

Runtime note:

- This bundle does not include Mina tooling, o1js dependencies, deploy keys, secrets, or project infrastructure.
- Mina and o1js APIs change over time. Use the included source map as a starting point, then verify current behavior against official docs and the target repository.
- Mina is not an EVM runtime. o1js code builds proofs and transaction updates; the chain verifies proofs and applies state transitions.
- TypeScript checks are not automatically proof constraints. Security-critical assumptions must become provable assertions, preconditions, signatures, permissions, or transaction-structure checks.
- These skills help an AI agent produce better Mina work, but they do not replace human engineering review or a professional audit for high-value systems.

Main modes:

- Router mode: choose the right Mina specialist skill and shared reference file for the task.
- Learning mode: teach Mina/o1js concepts step by step with exercises and pitfalls.
- zkApp development mode: design and implement `SmartContract` methods, state transitions, and proof-aware flows.
- Circuit design mode: turn witnesses, assertions, hashes, signatures, and Merkle checks into explicit constraints.
- ZkProgram mode: build standalone programs, recursive proof flows, proof aggregation, and SmartContract integrations.
- Testing mode: write LocalBlockchain tests, negative tests, replay tests, wrong-witness tests, permission tests, and invariant coverage.
- Debugging mode: inspect compile, prove, send, permission, witness, `AccountUpdate`, and browser prover failures.
- Security review mode: map architecture, permissions, AccountUpdates, trust boundaries, invariants, and Mina-specific bug patterns.
- Deployment mode: prepare verification keys, permissions, upgrade policy, network config, release notes, and rollback assumptions.
- Research mode: find current Mina/o1js docs, examples, ecosystem repositories, standards, issues, and audit material.

Skill map:

- `mina-protocol-agent`: pack router and shared reference entrypoint.
- `mina-o1js-learning-coach`: guided learning for Mina, o1js, zkApps, proofs, and security basics.
- `mina-o1js-zkapp-dev`: zkApp implementation and refactoring with o1js.
- `mina-o1js-circuit-design-patterns`: circuit constraints, witnesses, assertions, hashing, signatures, and Merkle checks.
- `mina-zkprogram-recursion-dev`: `ZkProgram`, recursive proofs, proof aggregation, and verifiable compute.
- `mina-merkle-offchain-state-dev`: Merkle trees, off-chain state commitments, membership proofs, and root transitions.
- `mina-o1js-testing-fuzzing`: LocalBlockchain, negative, replay, property-style, and invariant tests.
- `mina-accountupdate-transaction-debugger`: transaction trees, authorization, token IDs, balance changes, and permission failures.
- `mina-o1js-debugging-performance`: compile, prove, transaction, worker, memory, and performance debugging.
- `mina-o1js-security-review`: Mina/o1js threat modeling, hardening, audit review, and finding triage.
- `mina-token-standard-security`: custom tokens, token managers, mint/burn rules, token IDs, and accounting.
- `mina-deployment-upgrade-security`: deployment, verification keys, permissions, upgrades, keys, and release procedure.
- `mina-privacy-credentials-security`: private credentials, zkKYC, selective disclosure, nullifiers, and leakage review.
- `mina-frontend-prover-ux`: browser proving, wallet UX, worker performance, transaction submission, and privacy boundaries.
- `mina-ecosystem-research-scout`: current docs, examples, grants, tooling, repositories, standards, and ecosystem research.

Typical outputs are method specs, implementation notes, negative-test plans, permission matrices, `AccountUpdate` maps, invariant lists, audit reports, deployment checklists, source summaries, and targeted code changes.

Important boundaries:

- This skill pack is for Mina Protocol and o1js work, not generic Web3, EVM, or zk tooling.
- The agent should classify public inputs, private witnesses, proven claims, authorization, and off-proof risks before changing security-sensitive code.
- `get()` alone is not enough for state safety when the current on-chain value matters. Prefer explicit preconditions such as `getAndRequireEquals()` or `requireEquals()`.
- AccountUpdates are the transaction language. Always inspect who authorizes each update, which account or token it touches, and what balance or state changes it performs.
- Privacy failures often happen outside the proof through public inputs, events, actions, logs, APIs, analytics, IP metadata, timing, or reused nullifiers.
- Shared dependencies and off-chain services are part of the threat model when they affect witnesses, state roots, nullifiers, transaction assembly, or user privacy.
