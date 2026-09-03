# Severity Model for TON ZK Integration Findings

Assign severity from demonstrated impact, attacker prerequisites, reachability, affected value, repeatability, and detectability. Do not rate solely from a vulnerability-class name.

## Required fields

Every finding records:

- **Impact:** exact unauthorized state transition, confidentiality loss, fund loss, setup compromise, denial of service, or integrity failure.
- **Attacker:** unauthenticated user, proof holder, authorized user, relayer, admin, operator, or supply-chain actor.
- **Prerequisites:** valid proof, old root, message timing, admin key, compromised setup, specific upgrade state, or none.
- **Reachability:** production/default, optional configuration, test-only, deprecated, or blocked.
- **Scope:** one user/action, one contract, all deployments sharing a VK/setup, or ecosystem-wide.
- **Repeatability:** one-shot, bounded, replayable, or unlimited.
- **Evidence and confidence:** confirmed test/reproducer, strong code proof, partial evidence, or hypothesis.

## Critical

Use when an external or realistically positioned attacker can cause catastrophic loss of integrity or assets with broad scope, such as:

- forge proofs or bypass verification for production statements;
- execute arbitrary unauthorized mint, withdrawal, transfer, ownership, or governance state transitions;
- exploit a compromised trusted setup to create accepted proofs, with evidence that affected parameters protect production value;
- substitute an attacker-controlled VK/circuit on a production authorization path without equivalent safeguards.

Typical requirements: production reachability, high-value impact, little or no privileged access, and a concrete exploit path. An unproven suspicion about pairing/subgroup handling is not Critical.

## High

Use when exploitation causes major unauthorized effects but is narrower or requires a valid proof/context, such as:

- repeat a one-time withdrawal, mint, claim, vote, or transfer through replay;
- reuse a valid proof across contracts/actions/networks/versions to bypass authorization;
- change recipient, amount, root, owner, or other business semantics not bound by the proof/policy;
- exploit non-canonical field aliases to bypass a high-impact application check;
- trigger substantial, repeatable fund loss through bounce/state inconsistency.

A High finding normally has a reliable reproducer and impacts protected state or funds, even if the attacker must first obtain a legitimate proof.

## Medium

Use for meaningful but constrained security impact, for example:

- repeatable gas or balance griefing that can materially disrupt a contract but does not authorize protected state changes;
- unsafe admin/VK/setup operational controls requiring privileged access but creating credible compromise risk;
- bounded denial of service or permanent lockout affecting a subset of users;
- stale-root or upgrade behavior with narrow prerequisites and limited impact;
- secret exposure limited to non-production/private test data with real privacy consequences.

Do not reduce a finding to Medium merely because it is “only denial of service”; inability to access or recover substantial locked funds can justify High.

## Low

Use for limited defense-in-depth weaknesses with low practical impact, such as:

- malformed input causes a clean transaction failure but no persistent state/fund effect;
- missing provenance metadata makes reproduction harder while current artifacts remain verifiably consistent;
- a bounded inefficiency allows minor caller-funded gas waste;
- a non-default configuration weakens safety but requires unlikely privileged misuse.

Low still requires a concrete violated expectation. Pure style or maintainability issues are informational.

## Informational

Use for hardening, documentation, observability, test-coverage, or maintainability improvements without a demonstrated security impact:

- add artifact hashes or a public-input manifest;
- add negative tests for an invariant already enforced;
- stop hand-editing generated files even though current diffs are benign;
- clarify that a sample trusted setup is development-only;
- document experimental PLONK limitations.

## Confidence

Report confidence separately from severity:

- **High confidence:** reproduced end to end or proven by a complete, reachable code/data-flow argument.
- **Medium confidence:** strong evidence, but an environment/tool/artifact blocks final execution.
- **Low confidence:** plausible hypothesis requiring additional assumptions or missing artifacts.

A low-confidence catastrophic hypothesis should not be presented as a confirmed Critical vulnerability. Mark it blocked and state the exact validation needed.

## Evidence status gate

- **Confirmed:** an executable reproducer demonstrates the violated invariant, or a complete reachable code/data-flow proof establishes the same result with exact source and artifact evidence.
- **Likely:** the attacker path and violated invariant are supported by strong evidence, but one bounded execution or environment fact remains unverified. State that gap and do not claim reproduction.
- **Blocked:** a named missing prerequisite prevents validation. Record what is missing, why it matters, the strongest evidence obtained, and the exact next action.
- **Informational:** no demonstrated security impact; use for hardening, documentation, or test-depth work.

Finding status and release status are separate. Accepted risk records an owner decision; it does not upgrade evidence, confidence, a required audit phase, or readiness.

## Severity decision sequence

1. What exact protected invariant fails?
2. Can an attacker reach it in the deployed/default configuration?
3. What capability or asset does the attacker gain or destroy?
4. How broad and repeatable is the impact?
5. What prerequisites reduce likelihood or scope?
6. Is the evidence complete enough to call it confirmed?
7. Compare the result to the examples above and document the rationale.

## Re-rating after remediation

After a fix, rerun the original reproducer and the full relevant suite. Do not automatically downgrade the original finding; close it when the exploit is no longer reachable, and separately report residual risk or operational migration requirements.
