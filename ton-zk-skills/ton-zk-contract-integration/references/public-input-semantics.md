# TON public-input semantics overlay

Use `$groth16-systems` for canonical scalar handling, logical types, application ranges, privacy, deterministic flattening, and the general public-input contract. This reference defines the additional TON mappings and registry.

## Proof-context validator

Use the bundled proof-context schema and run:

```bash
python3 <skills-root>/ton-zk-contract-integration/scripts/validate_proof_context.py \
  ./proof-context.json --project-root .
```

The validator rejects duplicate JSON keys, checks the schema and registered profile combinations, resolves artifact sources inside the declared project root, and recomputes SHA-256 over exact bytes. It separates manifest consistency from implementation verification and does not verify the circuit or generated contract.

Define `verifyingKey.hash` over the exact bytes of `verifyingKey.source`. Record generated verifier, wrapper, and compiled-code hashes separately.

## TON address and identity inputs

The bundled address profile accepts canonical `addr_std` without anycast. It hashes the ordinary level-0 address cell representation—not a friendly string or transport BoC—and exposes the complete 256-bit digest as paired high/low 128-bit big-endian limbs. Another address form or preimage requires a new registered profile.

Authenticate sender identity from TON execution context when policy depends on the caller; a body-supplied address is data, not authentication.

## TON cell and message hashes

Name the application-selected root and TL-B layout. The bundled cell profile uses the root representation hash, including referenced-cell depths and hashes; BoC indexes, CRC, ordering, and transport flags are outside that hash target. Exotic cells require a separately reviewed profile.

## TON roots, replay, and time

- Bind Merkle/state root version, source, depth, and accepted history policy.
- Give a public nonce/seqno an explicit bit width and inclusive range with `maximum < 2^bits`.
- Persist and consume the selected nullifier/nonce/object exactly once in the state-changing path.
- Define timestamp units and compare expiry with `blockchain.now()` under a bounded validity policy.

## Runtime domain input

The TON domain extends the general application domain with runtime config-19 `global_id`, workchain, current contract address, TON opcode, and the registered TON encoding profile. Recompute runtime-derived parts in the contract; a manifest network label is not sufficient.

The bundled `sha256-length-delimited-msb248-v1` profile fixes field order, byte encoding, length framing, SHA-256, 31-byte selection, and big-endian interpretation. An alternate hash-to-field route requires a new registry entry and coordinated schema, validator, circuit, wrapper, contract, and vectors.

## Normative encoding registry

[`proof-context-profiles.json`](../assets/proof-context-profiles.json) is the machine-readable registry. [`ton-encoding-vectors.json`](../assets/ton-encoding-vectors.json) fixes canonical address/cell cases, 128-bit limb splits, and serialized BoCs.

| Identifier family | TON purpose |
|---|---|
| `domain-hash-msb248-v1` | Runtime TON domain commitment |
| `ton-address-cell-hash-*-v1` | Lossless paired limbs of canonical address-cell hash |
| `ton-cell-hash-*-v1` | Lossless paired limbs of canonical cell representation hash |
| `field-canonical-v1` | Canonical scalar at the TON boundary |
| `uint-be-v1` / `boolean-01-v1` | TON-facing bounded values |

Changing a profile's byte order, limb order, preimage, padding, or range requires a new identifier.

All public inputs, TON messages, storage, and transaction effects are public or inferable. Apply the general privacy review before registering a value.
