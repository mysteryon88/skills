---
name: mina-protocol-agent
description: Use when installing, choosing, coordinating, or operating the Mina Protocol/o1js skill pack, especially when shared playbooks, examples, templates, source references, or multiple Mina specialist skills may be needed.
---

# Mina Protocol Agent Skill Pack

## Use when

Use this skill as the router and shared reference hub for the Mina Protocol/o1js skill pack.

It is especially useful when the user asks which Mina skill to use, wants a complete Mina coding or review agent, or needs task cards, examples, templates, source links or version hygiene notes.

## Install model

This package is self-contained when the full `skills/*` directory is copied into an agent skills directory.

Shared materials live here:

```text
mina-protocol-agent/
  references/
    INDEX.md
    SOURCES.md
    playbooks/
    examples/
    templates/
```

Specialist skills can refer to this sibling path:

```text
../mina-protocol-agent/references/INDEX.md
```

Load only the specific reference file needed for the task.

## Package compatibility gate

Before routing a version-sensitive task, identify target network, active protocol era, exact `o1js`/signer/wallet versions, endpoints, and proof/VK/cache origin. If unknown, route first to `mina-ecosystem-research-scout` and load `references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md`.

For transaction, wallet, relayer, archive, or finality work, load `references/playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md`. For deployment, verification-key changes, state-layout migration, key rotation, or redeploy, load `references/playbooks/DEPLOYMENT_PROVENANCE_AND_REDEPLOY.md`. For delegated-agent or scoped authorization, load `references/playbooks/DELEGATED_AUTHORIZATION_AND_PRIVACY.md`.

## Skill routing

| Task | Use skill |
|---|---|
| Learn Mina/o1js | `mina-o1js-learning-coach` |
| Write zkApp code | `mina-o1js-zkapp-dev` |
| Review security | `mina-o1js-security-review` |
| Add tests | `mina-o1js-testing-fuzzing` |
| Token logic | `mina-token-standard-security` |
| Deployment and upgrades | `mina-deployment-upgrade-security` |
| Credentials and privacy | `mina-privacy-credentials-security` |
| Current ecosystem research | `mina-ecosystem-research-scout` |
| ZkPrograms and recursion | `mina-zkprogram-recursion-dev` |
| Merkle/off-chain state | `mina-merkle-offchain-state-dev` |
| Frontend prover UX | `mina-frontend-prover-ux` |
| Transaction or AccountUpdate debugging | `mina-accountupdate-transaction-debugger` |
| Circuit design patterns | `mina-o1js-circuit-design-patterns` |
| Debugging and performance | `mina-o1js-debugging-performance` |

Use multiple specialist skills when the task crosses boundaries, for example privacy plus frontend, token plus testing, or deployment plus security review.

## Shared references

Start with `references/INDEX.md` when you need reusable material.

Common choices:

- `references/playbooks/QUICK_REFERENCE.md` for task-to-skill routing.
- `references/playbooks/CODING_TASK_CARDS.md` for prompts to paste into coding agents.
- `references/playbooks/O1JS_CODE_PATTERNS.md` for compact code patterns.
- `references/playbooks/SECURITY_BUG_PATTERNS.md` for audit checklists.
- `references/playbooks/TESTING_RECIPES.md` for invariant-to-test mapping.
- `references/playbooks/LEARNING_ROADMAP.md` for a teaching path.
- `references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js compatibility.
- `references/playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md` for wallet, fee payer, archive and finality flows.
- `references/playbooks/DEPLOYMENT_PROVENANCE_AND_REDEPLOY.md` for release identity, VK provenance and safe redeploy.
- `references/playbooks/DELEGATED_AUTHORIZATION_AND_PRIVACY.md` for mission-scoped authority, receipts and leakage.
- `references/templates/` for audit reports, implementation notes and system prompt setup.
- `references/examples/` for small examples.
- `references/SOURCES.md` for official source links and version hygiene.

## Working rule

For every Mina/o1js task, force this classification:

```text
What is public?
What is private?
What is proven?
What is authorized?
What is trusted?
What can replay?
What can leak?
```

Do not treat normal TypeScript checks as proof constraints. Do not load every shared reference file by default.
