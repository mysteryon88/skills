# Sources of truth and version discipline

TON ZK capabilities, CLI flags, compiler syntax, network configuration, and package behavior change. Use a layered source policy instead of relying on model memory.

## Priority order

1. **Installed binaries and project lockfiles** for exact local behavior:
   - `npx --no-install export-ton-verifier --help`
   - `npx --no-install export-ton-verifier doctor <artifact> --json`
   - the selected package manager's dependency tree
   - package `engines`, lockfiles, `Acton.toml`, Blueprint/Tact config, and compiler help
2. **Runtime and deployed evidence** for the target network:
   - network configuration and TVM `global_id` source
   - deployed address, code/data hash, getter result, receiver transaction, gas/fee, and balance changes
3. **Current official TON documentation**:
   - https://docs.ton.org/contracts/techniques/zero-knowledge
   - https://docs.ton.org/contracts/techniques/groth16-examples
   - https://docs.ton.org/v3/guidelines/smart-contracts/security/things-to-focus
   - https://docs.ton.org/v3/documentation/tvm/changelog/tvm-upgrade-2023-07 (current official BLS12-381 sizes and oversized-slice behavior)
   - https://docs.ton.org/v3/documentation/tvm/specification/runvm (current TVM instruction index)
   - https://docs.ton.org/llms.txt
4. **Current upstream source and tests**:
   - https://github.com/mysteryon88/export-ton-verifier
   - https://github.com/zk-examples/zk-ton-examples
   - https://github.com/zk-examples/zk-ton-plonk
   - https://github.com/zk-examples/zkJetton
5. **Primary prover/compiler documentation** for Circom/snarkjs, Noname, Gnark, and Arkworks.

If sources disagree, state the installed version, target environment, exact discrepancy, and which source controls the current task. Runtime and executable evidence outweigh an unsupported documentation assumption, but unexplained divergence remains a release blocker.

## Scoped metadata refresh — 2026-10-26

The upstream [package metadata](https://github.com/mysteryon88/export-ton-verifier/blob/main/package.json)
now identifies `export-ton-verifier` 3.1.0 with Node.js 24.22.1. This is a source
metadata observation, not proof of a published package or a new compatibility test.
The broader capability snapshot below remains dated 2026-08-06. Preserve existing
project pins; inspect the installed generator and rerun its doctor/tests before
using newer behavior. No dependencies or verification keys are upgraded by this note.

## Reference snapshot

The collection was reviewed on 2026-08-06. At that snapshot:

- `export-ton-verifier` repository/package metadata identified version 3.0.2;
- Groth16 generation covered Tolk, FunC, and Tact;
- experimental PLONK generation covered Tolk and FunC;
- inputs included Circom/snarkjs artifacts plus native BLS12-381 Gnark and Arkworks formats;
- Tolk was the default generation target documented by the generator;
- TON verifier templates relied on TVM BLS12-381 operations and rejected unsupported curves before rendering;
- TVM BLS input handling required application-level exact-length checks because oversized slices may leave trailing data outside the consumed prefix;
- external-message acceptance moved later execution cost to the contract balance, so expensive verification required pre-accept policy and balance-loss tests;
- runtime network binding could use TVM configuration parameter 19 `global_id` rather than trusting a manifest label alone;
- the current official Blueprint documentation required a newer Node.js release than some older ZK examples. The project package engines and selected toolchain remain controlling.
- the upstream Noname repository was archived and still described the language as beta, so it remained a pinned compatibility route rather than the default for new production circuits.

These are reference facts, not permanent assumptions. Re-run local diagnosis and current documentation checks before implementation, review, or deployment.

## Toolchain compatibility

Do not collapse all TON ZK workflows into one Node.js requirement. Older examples, the verifier generator, and the current project framework may have different supported ranges. Inspect package engines, lockfiles, and installed help before changing the environment.

For existing repositories, preserve the selected framework and version unless migration is requested. For new work, inspect current TON guidance and choose the supported toolchain deliberately rather than treating this snapshot as a permanent recommendation.

## Safe update behavior

- Do not run dependency upgrades merely to answer a question or inspect a repository.
- If an update is requested, read release notes/diffs, update one boundary at a time, regenerate outputs, and rerun circuit, local proof, on-chain, state, and security tests.
- Never silently regenerate a production VK or replace trusted-setup artifacts during a package update.
- Record tool versions, package engines, commands, network configuration, and hashes in review and deployment artifacts.
- Treat a generator version change, proof-system change, VK change, public-input order change, message layout change, or network-domain change as a compatibility event.

## Citation discipline for skill maintenance

When changing this collection, prefer official documentation, upstream source, upstream tests, and cryptographic papers. Separate verified facts from inferred recommendations. Do not copy large upstream code blocks into a skill; link to the source and encode the reusable decision or test instead.
