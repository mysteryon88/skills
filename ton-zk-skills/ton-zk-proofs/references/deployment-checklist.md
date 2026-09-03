# Deployment and release checklist

Deployment is a separate authorized action. Do not deploy merely because local tests pass, and do not ask a wallet to sign until the target network, address derivation, code hash, value, and authority are explicit.

## Release sequence

```text
clean reproducible build
  → local Sandbox/Acton tests
  → testnet deployment
  → deployed code/data verification
  → getter and internal-message smoke tests
  → actual gas, fees, balance, and replay checks
  → independent review and explicit mainnet approval
```

Use the repository's selected toolchain and pinned commands. Current TON projects may use Acton; existing projects may use Blueprint or another maintained framework. Inspect local help, package engines, lockfiles, and network configuration before running commands.

## Before any network action

Record and verify:

- repository commit and clean/intentional working-tree state;
- lockfile hash and package manager;
- Node.js, compiler, Tolk/FunC/Tact, proving stack, and generator versions;
- circuit source hash, R1CS/constraint identity, protocol, curve, and trusted-setup provenance;
- for PLONK, universal SRS source, exact SHA-256, power/capacity, contribution evidence, preserved `snarkjs powersoftau verify` output, and release record binding;
- verification-key source, SHA-256 hash, and generated verifier/wrapper hashes;
- compiled code BoC hash and initial data/config hash;
- derived contract address, workchain, and current contract address binding;
- target endpoint/network and observed runtime `global_id` from network configuration;
- proof-context manifest validation result;
- expected deployment value, reserves, admin/upgrader authority, and rollback/pause policy.

Stop if a build silently regenerates a circuit, VK, verifier, wrapper, address, or code hash that was not reviewed.

## Testnet gate

On testnet:

1. verify the wallet, endpoint, explorer, and `global_id` all identify the intended network;
2. deploy the exact reviewed code/data pair;
3. compare the on-chain account code hash and expected address with the local release record;
4. call the diagnostic getter with a known-valid and known-invalid fixture;
5. execute the real state-changing internal message with sufficient value;
6. replay the exact message and confirm the stored nullifier/nonce/seqno blocks it;
7. try wrong domain, contract address, action version, root, recipient, amount, and expiry;
8. record transaction IDs, exit codes, gas, fees, storage delta, outgoing actions, and contract balance;
9. test bounce/duplicate behavior and an invalid-proof path without leaking private witness material;
10. repeat the smoke test from a clean checkout or CI-produced artifact when practical.

A getter result alone is not deployment evidence because getters do not execute the protected state transition.

## Mainnet gate

Mainnet requires all testnet evidence plus:

- `TON_INTEGRATION_READY` from the TON boundary review;
- `FULL_ZK_RELEASE_READY` only when circuit, proof system, prover/converter, setup/SRS, TON integration, and deployment phases are all `PASS`;
- no required phase in `NOT_ASSESSED`, `NOT_IN_SCOPE`, or material `BLOCKED`; owner acceptance cannot replace the missing technical evidence;

- explicit human approval for the exact network, address, code hash, value, and authority;
- reviewed production trusted setup or documented proof-system assumptions;
- no unresolved Critical/High finding and an accepted disposition for lower findings;
- current gas/code-size measurements with reserve and worst-case failure budget;
- operational monitoring for balance, failed verification, replay rejection, admin/VK changes, and abnormal external-message spend;
- verified source publication and preserved generator/license notices where applicable;
- incident response, pause/migration, and key-management procedures.

Do not reuse a testnet proof-context manifest by only changing its `network` label. Regenerate and verify the domain commitment against the runtime mainnet `global_id`, address, workchain, circuit/VK identity, and action version.

## Deployment record

Preserve at minimum:

```text
commit / lockfile hash
build and test commands
compiler and generator versions
circuit / VK / manifest hashes
protocol / curve / setup identity
generated verifier and wrapper hashes
compiled code and data hashes
network endpoint / global_id / workchain
contract address / deploy transaction
wallet or multisig authority
attached value / reserve policy
smoke-test transactions and results
actual gas / fees / final balance
review approval and unresolved risks
```

Never store wallet secrets, witness values, ceremony entropy, proving keys, or production private inputs in the release record.
