# TON circuit security overlay

Apply `$groth16-systems` first for relation design, constraint completeness, witness/constraint separation, ranges, hashes, Merkle paths, setup, artifact identity, and adversarial review. This reference contains only the additional requirements for the supported TON route.

## BLS12-381 route

- Compile and prove over BLS12-381; stop on an unexplained BN254/bn128 artifact.
- Confirm the full witness, public witness, R1CS, proof, and verification key use the same scalar field and build.
- Reconstruct flattened public-input order from generated artifacts and carry it unchanged into the TON wrapper and contract.
- Verify the exact proof/public/VK tuple locally before `export-ton-verifier` runs.

For Circom, keep the curve selection explicit:

```bash
circom circuit.circom --r1cs --wasm --sym --prime bls12381 --inspect
```

## TON encodings entering the circuit

The circuit, client, manifest, and contract must share one registered encoding for:

- `addr_std` identities and workchain handling;
- ordinary-cell representation hashes rather than transport BoC bytes;
- high/low 128-bit big-endian limbs for full 256-bit hashes;
- Merkle leaf, direction, depth, root-version, and empty-node conventions;
- runtime network/application domain values.

Do not reduce an unrestricted 256-bit digest modulo the scalar field and call the result lossless. Any alternate address, cell, hash, or domain preimage requires a new versioned profile and coordinated vectors.

## Runtime TON domain

When a proof authorizes a TON action, its checked context must include or securely derive runtime config-19 `global_id`, workchain, current contract address, circuit/VK identity, protocol, action/opcode, action version, and the relevant replay/state values. A manifest string such as `mainnet` is not runtime binding.

## Stack export checks

- **Circom/snarkjs:** inspect `.sym`, R1CS counts, `public.json`, and the final BLS12-381 `.zkey`/VK.
- **Gnark:** use a BLS12-381 circuit, full/public witnesses from the same field, and a native proof verification before conversion.
- **Arkworks:** use BLS12-381 Groth16, distinguish public and witness allocations, and verify native serialization before export.
- **Noname:** run the selected `r1cs-bls12-381` backend and inspect its R1CS/witness with the pinned tools.

Stack hints and unconstrained computations belong to the general circuit review; this overlay checks that the reviewed relation survives the TON-facing export.

## TON handoff evidence

Record the general `$groth16-systems` review identity plus:

- BLS12-381 evidence;
- TON encoding profile identifiers and golden vectors;
- wrapper and generated-verifier target;
- flattened TON public-input mapping;
- runtime domain fields;
- exported artifact hashes and local verification output.
