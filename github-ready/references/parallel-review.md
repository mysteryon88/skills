# Parallel Review

Parallel review is optional. Offer it only after inventory shows that a large repository has independent audit domains. Parallel workers require explicit user consent; never dispatch them automatically. Use at most four read-only workers and continue with one reviewer if consent is absent or coordination costs exceed the benefit.

## Worker handoff

Give each worker the resolved repository root, applicable repository instructions, immutable scanner evidence for its scope, prohibitions on edits/project execution/network/Git mutation, and exactly one scope:

1. secrets and Git history;
2. Git hygiene, AI files, ignore coverage, build/temp/generated files;
3. structure, dependencies, dead-code and unused-file candidates;
4. documentation/licensing or adversarial verification of a disputed finding.

Require this output for each candidate:

```text
candidate-id | proposed severity/action | evidence location | impact | recommendation | uncertainty
```

Workers also return `Unverified` and `Clean` items for their scope. They must not assign final `GHnnn` IDs, broaden scope, expose candidate values, or recommend deletion from text-search absence alone.

## Coordination

The coordinator must independently verify every cited evidence location, resolve conflicts, merge duplicates, and assign stable IDs. Coordinator evidence verification—not worker confidence—controls the report. Voting is not evidence. Any missing or conflicting critical evidence remains `Unverified` and forces `INCOMPLETE`.
