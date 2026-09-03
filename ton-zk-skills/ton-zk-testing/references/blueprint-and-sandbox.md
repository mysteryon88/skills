# Blueprint, Acton, and TON Sandbox testing

Use the framework already present in the repository. Do not replace the test stack or Node.js version as part of a verifier change without a separate migration decision. Inspect package engines, lockfiles, and installed help first.

## Blueprint/Sandbox structure

A typical test needs:

- `Blockchain.create()` and a treasury sender;
- compiled/opened verifier or application contract;
- known-valid proof/public fixture;
- generated wrapper or exact ABI/message helper;
- local snarkjs/native verification;
- getter assertion;
- internal-message transaction assertion;
- storage and outgoing-message assertions;
- gas/code-size logger or snapshot.

Use `@ton/test-utils` matchers to assert sender, destination, deploy flag, success/failure, exit code, bounced status, value, and message body where relevant.

## Test order

1. Compile and deploy.
2. Verify the fixture locally.
3. Call the getter and assert `true`.
4. Send the state-changing message with a tested value.
5. Assert transaction success and exact state/outgoing changes.
6. Re-send and assert replay rejection.
7. Run isolated negative cases from fresh blockchain state unless the test intentionally exercises sequencing.
8. Assert fees and contract balance deltas, not only logical success or exit codes.

## Malformed input behavior

Decide whether malformed shape should throw during wrapper serialization, getter execution, or contract parsing. Tests must distinguish malformed input from a well-formed but cryptographically invalid proof. Assert stable developer exit codes for application failures where the contract controls them.

## Tact integrations

Use the generated Tact wrapper and message types. When proof bytes are carried as slices/cells and public inputs as a map, construct them through the same helper used in production. Assert map keys and input count.

## Acton projects

Inspect the installed CLI before choosing flags:

```bash
acton --version
acton doctor
acton help build
acton help test
```

Run the project's configured `acton build`/`acton test` flow. Use available gas/fuzz/mutation options only after reading installed help and ensuring the verifier fixtures remain deterministic.

## Clean-state verification

Run the full test command after removing only safe generated build caches—not proof/VK source artifacts. A reproducible build must not depend on an untracked locally generated wrapper or verifier file.

## External receivers

When the application accepts external messages, record whether each case fails before or after acceptance. Test malformed envelopes, wrong signatures/seqno/expiry, valid envelopes with invalid proofs, repeated anonymous submissions, replay after compute/action failures, and insufficient reserves. Assert the exact contract balance loss. A logical rejection after acceptance can still be an economic failure.

Prefer an internal-message test route for a public expensive verifier unless the external endpoint is an explicit product requirement.
