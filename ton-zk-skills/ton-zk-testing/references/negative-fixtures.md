# TON negative fixtures

Start with the generic mutations from `$groth16-systems`, then add the TON parser, cell, message, and economic cases below. Change one property at a time and record the expected rejection layer.

## Exact TVM BLS inputs

- truncate each fixed-width G1/G2 component by one byte;
- append one byte, non-byte-aligned bits, or an unexpected ref to a valid component;
- create messages with the same valid 48/96-byte cryptographic prefix and different tails;
- alter tuple/dictionary cardinality, key width, or cell placement;
- compare wrapper output with an independently encoded fixture.

The receiver must reject non-canonical layout before the TVM BLS opcode. The fact that an opcode consumes the same valid prefix is not evidence that an oversized message is safe.

## BLS12-381 scalar boundary in TON encodings

For the supported route, cover `0`, `1`, the documented application maximum and next value, `r-1`, `r`, `r+1`, oversized widths, and alternate external encodings accepted by the client parser. Distinguish canonical scalar rejection from the TON application's narrower range rejection.

## TON public-input containers

- remove, append, swap, or duplicate a flattened input;
- leave a dictionary hole or change its key width;
- reverse registered hash limbs or byte order;
- substitute an unregistered address/cell/domain profile;
- keep values correct but use another wrapper flattening convention.

## TON semantic and state mutations

- another runtime `global_id`, workchain, contract, action/opcode, circuit, or VK;
- body-supplied sender different from authenticated sender;
- another recipient, amount/token/object, root/version, replay key, or expiry;
- identical message, bounced action, retry, and concurrent replay.

Assert protected storage, balances, replay state, and outgoing actions follow the documented failure policy.

## External-message economics

Classify each fixture as rejected before or after `ACCEPT`. Repeatedly submit an invalid proof under a valid envelope and measure the contract balance/gas effect. After a committed envelope failure, confirm redelivery is rejected cheaply while the application nullifier remains available for a new authenticated attempt.
