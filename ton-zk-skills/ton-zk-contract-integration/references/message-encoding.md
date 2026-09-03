# Proof and message encoding

## Prefer one implementation

Use the generator's TypeScript wrapper and exported helpers for proof compression, public-input dictionaries/tuples, and internal-message bodies. A hand-written parallel serializer creates a second protocol implementation that must be audited and tested.

## Encoding contract

Record:

- proof component byte lengths and compressed/uncompressed form;
- byte order for field elements and coordinates;
- public-input count and order;
- tuple versus dictionary/map representation;
- dictionary key width and contiguous key requirements;
- cell bit/ref layout and opcode;
- wrapper method/getter names;
- attached-value requirements;
- protocol/language version.


## Exact BLS slice lengths

TVM BLS12-381 operations consume fixed prefixes: G1/FP values use 48 bytes and G2/FP2 values use 96 bytes. An oversized slice is not necessarily rejected; the opcode may use only the first required bytes. A short slice underflows. Therefore the receiver must validate the exact generated layout before invoking any BLS opcode:

- require the exact bit length for every proof component;
- require byte alignment;
- reject trailing bits and bytes;
- reject unexpected cell references;
- reject extra tuple/dictionary items and non-contiguous public-input keys;
- ensure the wrapper and contract hash, parse, and verify the same canonical bytes.

For a compressed Groth16 layout this commonly means G1 `A` = 48 bytes, G2 `B` = 96 bytes, and G1 `C` = 48 bytes, but the generated template is the source of truth. PLONK and other templates may contain a different sequence of fixed-width elements. Never infer widths from a proof filename alone.

A required regression is a valid component followed by one extra byte. It must be rejected before cryptographic verification even when the valid prefix would otherwise verify. Also test a one-byte-short value, non-byte-aligned bits, extra refs, and two messages with the same accepted prefix but different tails.

## Tolk and FunC

Generated wrappers may pass proof components as buffers/cells/slices and public inputs as tuples or dictionaries depending on protocol/language/template. Use the exact emitted wrapper and tests. Do not convert between tuple and dictionary merely because both can hold integers.

## Tact

Tact Groth16 examples commonly represent proof components as `Slice` and public inputs as a map keyed by an integer index. Verify key type/width, every expected key, no extras, and deterministic mapping to the VK `IC` points.

## Getter versus message

- Getter calls are read-only and often emulated off-chain. They are useful for diagnostics and can return a boolean or throw on malformed input.
- An internal message executes in a transaction, consumes gas/value, and may change state or fail with an exit code.

Test both paths, but authorize application state only in a state-changing receiver with replay and semantic checks.

## `proof-to-message`

The generator CLI can encode supported proof/public JSON into a BOC body. Treat the output as serialization evidence, not as an authenticated request. Add application-specific context to the circuit/message schema and validate it in the receiver.

## Attached value and gas

Read the generated receiver and wrapper for its value floor, then benchmark the actual proof/input shape. The value must account for compute, storage, forwarding, actions, and reserve—not only a remembered example such as `0.05` or `0.15 TON`.

## Bounce and duplicates

When verification triggers outgoing messages, define what state is saved before sending, how a bounce restores or compensates state, and how duplicate/reordered messages are identified. The proof/nullifier may prevent repeating the business action, but it does not automatically solve every asynchronous accounting path.
