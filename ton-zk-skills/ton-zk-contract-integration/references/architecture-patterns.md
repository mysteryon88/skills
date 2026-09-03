# Integration architecture patterns

Use `$groth16-systems` for the general verifier/policy/application boundary and verification-key policy. The patterns below describe TON deployment and message consequences.

## Pattern A: verifier embedded in the application

The application contract contains generated verification logic and executes policy/state changes in the same receiver.

**Advantages:** atomicity is straightforward; no asynchronous verifier callback; fewer contracts/messages.

**Risks:** larger audit surface and code size; regeneration can collide with application edits; upgrades couple cryptographic and business logic.

Use a strict generated-code boundary and application helpers. Regenerate to a separate file/module when the toolchain permits.

## Pattern B: dedicated verifier as a pure service

A dedicated contract exposes proof verification, while another contract uses it.

A getter call is off-chain/emulated and cannot authorize an on-chain state transition. An internal-message verifier introduces asynchronous state and message-order questions. The application must authenticate the verifier response, bind it to one request/context, prevent replay, handle bounce/timeouts, and avoid executing based on a stale result.

Use this pattern only when the cross-contract boundary provides a concrete benefit and its state machine is fully tested.

## Pattern C: verifier, policy, and application separation inside one deployment unit

Keep conceptual modules even when compiled into one contract:

```text
parse/normalize → cryptographic verifier → semantic policy → replay guard → state transition
```

This is the preferred reasoning model. It makes audits and tests distinguish proof rejection from policy rejection.

## Verification-key policy

Apply the general key policy, then bind the accepted VK/circuit identity into TON storage, runtime domain, generated-code identity, wrapper version, and upgrade/migration behavior. A caller-supplied key must not become TON application authorization without an authenticated allowlist.

## State layout

Consider separate typed storage for:

- application version/domain identifier;
- accepted circuit/VK fingerprint;
- current or allowed Merkle/state roots;
- used nullifiers or per-user nonce/seqno;
- pending asynchronous requests if any;
- admin/governance identity;
- reserve/fee parameters;
- pause/migration state.

Storage keys and serialized widths are part of the security interface. Test collisions, missing entries, and migration behavior.

## Order of effects

For internal messages, run cheap parsing, value, length, canonical, and authorization checks before expensive proof verification, then consume the application nullifier with the business transition after all checks pass. For a signed external envelope, check authentication and envelope replay before `ACCEPT`, persist and `COMMIT` the envelope replay state before expensive or fallible work, then keep the application nullifier atomic with the successful transition. Do not send irreversible outgoing actions before the contract has committed the state needed to handle failure or duplication safely.


## External receiver boundary

External messages do not bring value for execution. If the contract accepts before authenticating the envelope, repeated invalid proofs can spend its balance. Prefer internal messages for public expensive verification, or require a cheap signed/seqno-protected envelope before acceptance. See [external-messages.md](external-messages.md).
