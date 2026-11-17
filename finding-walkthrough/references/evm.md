# EVM evidence checklist

Collect chain/revision/compiler, deployed code identity, caller/origin/value/calldata and decoded ABI arguments. Follow access checks, storage reads/writes, return/revert behavior and relevant external calls. Distinguish implementation code from proxy callsite, storage context and effective sender/value; inspect the actual forwarding code. At a delegated call, record whose code executes against whose storage and the observed failure propagation. Treat emitted logs and attempted calls separately from final committed effects. Use an authorized local fixture/fork only when requested; pin state and save traces before calling a result observed.

Primary orientation: [Solidity smart-contract introduction](https://docs.soliditylang.org/en/latest/introduction-to-smart-contracts.html), [EIP-7 DELEGATECALL](https://eips.ethereum.org/EIPS/eip-7). These guide questions; verify actual project/runtime behavior.
