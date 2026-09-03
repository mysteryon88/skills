# TON artifact contract

Start with the general artifact identity from `$groth16-systems`. The TON handoff manifest adds the following fields.

## TON route identity

- BLS12-381 proof-system route and source artifact format;
- `export-ton-verifier` version, command, target language, template, and diagnosis output;
- generated verifier, TypeScript wrapper, compiled code, and fixture hashes;
- proof-message/cell layout and exact BLS component widths;
- target TON network/workchain, expected runtime `global_id`, and contract/domain identity;
- registered address, cell-hash, domain, integer, and public-input encoding profiles.

## TON public-input overlay

For each flattened index, extend the general public-input contract with:

| Field | TON meaning |
|---|---|
| `authenticatedSource` | Message context, sender, current contract state, or runtime TVM configuration |
| `encodingProfile` | Registered TON profile identifier |
| `cellPath` | Wrapper/cell/dictionary location and key width |
| `contractCheck` | Exact equality or policy check in the state-changing receiver |
| `runtimeBinding` | Network, contract, action, root, replay, or expiry value checked at execution |

Arrays, tuples, and dictionaries must flatten deterministically across the circuit, `public.json`, manifest, wrapper, generated verifier, and contract.

## TON consistency checks

- Local verification accepts the exact proof/public/VK tuple.
- `doctor` accepts the exact artifact and selected target.
- The wrapper and an independent decoder agree on the complete cell graph and values.
- Changing one TON semantic input causes policy or proof rejection at the documented layer.
- The generated constants match the recorded VK and the compiled code matches the reviewed generator output.

## Change control

A changed TON encoding profile, wrapper layout, message opcode, runtime domain, generated target, compiled verifier, or contract policy creates a new TON release identity. Regenerate dependent output and fixtures instead of overwriting provenance.
