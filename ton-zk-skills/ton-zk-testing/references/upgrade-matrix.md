# Verifier and proof-context upgrade matrix

Run this matrix against the real state-changing receiver, not only a getter. Freeze the old/new code hash, VK hash, circuit ID, action version, domain profile, public-input order, and storage layout before testing. Every rejection must leave protected state, replay markers, outgoing actions, reserve, and balance consistent with policy.

| Scenario | Required result and assertions |
|---|---|
| old code + old VK | Baseline remains valid before activation; record proof, domain, gas, state delta, and replay behavior. |
| new code + old VK | Reject unless an explicitly versioned compatibility window was designed and audited; never select a VK from untrusted message data. |
| old code + new VK | Reject or prove unreachable; an uploaded VK must not silently change the verifier/circuit binding. |
| new code + new VK | Accept only the reviewed circuit/VK/setup/context tuple and its new action/domain version. |
| old proof after upgrade | Reject when statement, VK, circuit, address/domain, or action version changed; if intentionally supported, test a bounded, explicit old-version route. |
| pending request during upgrade | Define activation ordering and prove that a request authorized under the old state cannot execute under unintended new semantics. |
| rollback | Restore a known code/data pair atomically; verify address/code/data hashes, replay continuity, and whether proofs issued during the failed release remain usable. |
| partial migration | Fail closed when code, VK registry, proof-context state, wrapper, or client version advances without the others. |

## State and replay cases

- Submit the same nullifier/nonce immediately before and after activation; exactly one authorized transition may succeed.
- Exercise pending asynchronous/bounced messages across the activation boundary.
- Verify old and new domain commitments use runtime `global_id`, workchain, current contract address, circuit/VK identity, action, and version.
- Test storage migration with empty, typical, maximum-size, and malformed legacy state.
- Interrupt migration at every persisted phase and prove restart is idempotent or safely rejected.
- Check admin/upgrader authorization, timelock/multisig policy, pause state, and unauthorized VK/code replacement.

## Release evidence

Preserve the exact commands, old/new artifact hashes, activation transaction, transaction traces, exit codes, state snapshots, gas/fees, rollback rehearsal, and the disposition of every intentionally supported compatibility route. A checklist statement without executable evidence does not pass the upgrade phase.
