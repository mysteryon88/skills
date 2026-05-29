# Fuzzing Vs Mutation

## Contents

- [Core Difference](#core-difference)
- [What Mutation Testing Changes](#what-mutation-testing-changes)
- [What Fuzzing Changes](#what-fuzzing-changes)
- [What Each Technique Can And Cannot Prove](#what-each-technique-can-and-cannot-prove)
- [Combined Workflow](#combined-workflow)

## Core Difference

Do not confuse the two:

- Universalmutator mutates source code.
- Fuzzers generate inputs or messages.

They answer different questions and should be described separately.

## What Mutation Testing Changes

Mutation testing changes the program and asks whether the existing tests notice.

Use it to evaluate:

- whether assertions are strong enough
- whether negative paths are covered
- whether state changes, message handling, and math are actually observed

It does not generate new external inputs by itself.

## What Fuzzing Changes

Fuzzing keeps the program logic fixed and generates many inputs, messages, or execution sequences.

Use it to explore:

- unexpected input structure
- state-machine edge cases
- crash, revert, or invariant-breaking behavior
- message ordering and malformed payloads

It does not directly measure how strong the existing assertions are against injected source changes.

## What Each Technique Can And Cannot Prove

Mutation testing can suggest that a test suite is insensitive to certain code changes, but it cannot prove security.

Fuzzing can explore broad input space and find crashes or invariant violations, but it cannot prove that the test suite would notice all meaningful source-level logic changes.

Neither one replaces manual review or an audit.

## Combined Workflow

A practical combined workflow is:

1. Stabilize the project build and deterministic test or fuzz harness.
2. Use fuzzing to discover high-value inputs, message sequences, and invariants.
3. Turn those findings into reproducible tests or assertions.
4. Run mutation testing against the contract or source target.
5. Use surviving mutants to identify missing assertions or weak invariants.
6. Feed the strongest survivors back into fuzz targets, seed corpora, or invariant design.

For TON projects, this often means:

- fuzzing message payloads, sequencing, and boundary values
- mutation testing handlers, auth checks, send modes, storage updates, and math
