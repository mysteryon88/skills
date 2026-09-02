# Public Inputs and Application Binding

Use this reference when a valid Groth16 proof authorizes an application action. Cryptographic verification establishes one relation under one verification key; the application must bind that result to authenticated context, current state, freshness, and one intended transition.

## Public-input contract

For every flattened public-input index, record:

- stable name and circuit signal;
- canonical field encoding;
- logical type and accepted application range;
- authenticated source in the request, execution context, or state;
- equality or policy check performed by the application;
- privacy rationale and version policy.

Arrays and structures need deterministic flattening. Test the exact order rather than trusting object or map iteration.

## Field values versus application values

Let $r$ be the circuit scalar-field order. Accept one canonical external representation, normally $0\le x<r$. Reject negative, oversized, or alternative encodings before business interpretation. Never reduce an unrestricted external integer modulo $r$, verify the reduced value, and then use the original integer as an amount, identifier, timestamp, nonce, or address component.

Application types need their own rules:

- booleans are exactly `0` or `1`; enums belong to an explicit set;
- amounts, counters, timestamps, and indices have documented unsigned ranges;
- multi-limb encodings are injective over the accepted domain and fix limb/byte order;
- hashes and commitments fix their preimage format, domain tag, length framing, and field mapping;
- roots bind tree depth, hash, leaf encoding, version, and accepted lifecycle;
- every public value is intentionally public; hashing low-entropy data does not make it secret.

## Domain separation

Bind enough context to make proof portability intentional. Depending on the application, include:

- environment or network and verifier/application identity;
- circuit and verification-key fingerprint;
- protocol, action, opcode, and schema version;
- authenticated sender/owner and intended recipient;
- amount, asset, object, commitment, or accepted state root;
- nullifier, nonce, sequence number, or one-shot object;
- expiry, epoch, or validity window.

Runtime-derived fields must be recomputed or authenticated by the application. A manifest label is documentation, not execution-time binding.

## Replay protection

Choose a replay primitive that matches the identity model:

- a deterministic nullifier set for anonymous one-time actions;
- an authenticated per-user nonce or sequence number;
- a consumed note, claim, commitment, or object identifier;
- expiry combined with persisted replay state.

Expiry limits a replay window but does not prevent repeated use inside it. Wrapper-only request IDs provide no protection unless they are authenticated or proven and consumed by state.

## Verification-key policy

- A fixed key gives the simplest binding to one relation.
- An upgradeable key needs authenticated governance, explicit circuit/domain versioning, and old/new proof policy.
- A caller-supplied key is unsuitable for application authorization unless an independent allowlist authenticates the accepted relation.

A proof valid under an attacker-selected key proves only the attacker's chosen statement.

## Atomic authorization

Keep the reasoning layers explicit:

```text
parse and canonicalize → cryptographic verification → semantic policy → replay guard → state transition
```

The protected transition and replay consumption should be atomic. If verification and execution are separated asynchronously, bind the result to one authenticated request/context and handle duplicate, stale, failed, and reordered responses.

## Required negative cases

- same proof twice;
- same proof with one public value or its order changed;
- another application, environment, action, circuit, key, or version;
- stale/future root, nonce, sequence, or expiry;
- non-canonical scalar and application-range boundaries;
- failed verification or policy followed by a valid retry.

For every rejection, assert that protected state and outgoing effects remain unchanged and that replay state follows the documented failure policy.
