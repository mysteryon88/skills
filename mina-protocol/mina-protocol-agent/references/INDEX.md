# Mina Protocol Shared References

Use this index only when a Mina specialist skill needs reusable material. Load the smallest relevant file, not the whole reference pack.

## Playbooks

- [Quick reference](playbooks/QUICK_REFERENCE.md) - task routing and high-risk APIs.
- [Coding task cards](playbooks/CODING_TASK_CARDS.md) - prompts for common coding, review and debugging tasks.
- [Learning roadmap](playbooks/LEARNING_ROADMAP.md) - step-by-step learning path.
- [o1js code patterns](playbooks/O1JS_CODE_PATTERNS.md) - compact safe patterns to adapt.
- [Security bug patterns](playbooks/SECURITY_BUG_PATTERNS.md) - Mina/o1js issue checklist.
- [Testing recipes](playbooks/TESTING_RECIPES.md) - invariant-to-test mapping.
- [Network era and o1js compatibility](playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md) - Berkeley/Mesa, o1js 3, signer, VK, cache, and migration gates.
- [Transaction lifecycle and wallet preflight](playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md) - Auro, fee payer, nonce, AccountUpdate shape, archive, and finality.
- [Deployment provenance and redeploy](playbooks/DEPLOYMENT_PROVENANCE_AND_REDEPLOY.md) - source/build/cache/VK/address/permissions/state reconciliation and safe migration.
- [Delegated authorization and privacy](playbooks/DELEGATED_AUTHORIZATION_AND_PRIVACY.md) - mission scope, replay, receipts, commitments, and leakage.

## Examples

- [LocalBlockchain test pattern](examples/LOCALBLOCKCHAIN_TEST_PATTERN.md)
- [Method spec example](examples/METHOD_SPEC_EXAMPLE.md)
- [Privacy nullifier pattern](examples/PRIVACY_NULLIFIER_PATTERN.md)
- [Safe counter pattern](examples/SAFE_COUNTER_PATTERN.md)
- [Token test matrix](examples/TOKEN_TEST_MATRIX.md)

## Templates

- [Agent system prompt](templates/MINA_PROTOCOL_AGENT_SYSTEM.md)
- [Audit report template](templates/MINA_AUDIT_REPORT_TEMPLATE.md)
- [Implementation note template](templates/MINA_IMPLEMENTATION_NOTE_TEMPLATE.md)

## Sources

- [Sources and version hygiene](SOURCES.md) - official docs, repos, audits and current-version rules.

## Selection guide

| Need | Load |
|---|---|
| Which skill should handle this? | `playbooks/QUICK_REFERENCE.md` |
| Agent prompt for a common job | `playbooks/CODING_TASK_CARDS.md` |
| Safe o1js snippet | `playbooks/O1JS_CODE_PATTERNS.md` or one `examples/*.md` |
| Security review checklist | `playbooks/SECURITY_BUG_PATTERNS.md` |
| Test planning | `playbooks/TESTING_RECIPES.md` |
| Teaching sequence | `playbooks/LEARNING_ROADMAP.md` |
| Report or implementation artifact | one `templates/*.md` |
| Current docs and source priority | `SOURCES.md` |
| Berkeley/Mesa or o1js major-version change | `playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` |
| Wallet, fee payer, relayer, archive, status, or finality | `playbooks/TRANSACTION_LIFECYCLE_AND_WALLET_PREFLIGHT.md` |
| Deployment, VK change, state-layout migration, key rotation, or redeploy | `playbooks/DEPLOYMENT_PROVENANCE_AND_REDEPLOY.md` |
| Delegated or autonomous-agent authorization | `playbooks/DELEGATED_AUTHORIZATION_AND_PRIVACY.md` |
