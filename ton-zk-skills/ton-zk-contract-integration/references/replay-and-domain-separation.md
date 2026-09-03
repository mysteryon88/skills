# TON replay and domain overlay

Use `$groth16-systems` to choose the replay primitive, define the general application domain, and require atomic authorization. This reference adds the TON execution context.

## Required TON domain fields

Bind or authenticate:

- runtime config-19 `global_id` and workchain;
- current contract address and application identifier;
- circuit ID, VK hash, protocol, action/opcode, and action version;
- relevant sender/owner, recipient, amount/object, accepted root, replay value, and expiry.

Read the runtime `global_id` from TVM configuration and compare it with the proof-context expectation. Preserve the observed deployment value in the release record. Human-readable `mainnet` or `testnet` labels do not bind execution.

## TON atomic consumption

For an internal message, the state-changing transaction must parse and authenticate the TON context, validate freshness, verify the proof and semantic inputs, persist the replay update, and apply the protected transition atomically.

If a separate verifier contract responds asynchronously, bind its response to one authenticated request/context and handle duplicates, reordering, bounce, timeout, and upgrades.

For a signed external envelope, use replay state separate from the application nullifier. Check signature/seqno/expiry/domain before `ACCEPT`, persist and `COMMIT` the envelope replay state before expensive ZK work, and consume the application nullifier only with the successful protected transition.

## Wrapper `queryId`

A wrapper parameter is not replay protection by itself. Trace `queryId` through serialization, parsing, authentication or proof binding, storage lookup, and state consumption. Any missing link makes it mutable or reusable metadata.

## TON-specific tests

- same internal message twice and two near-concurrent messages with one replay key;
- same proof with changed wrapper `queryId`;
- another `global_id`, workchain, contract, opcode, circuit, or VK;
- root/version update between proving and delivery;
- bounce or failed action followed by retry;
- committed external envelope failure followed by redelivery, confirming the envelope is spent while the application nullifier remains fresh.
