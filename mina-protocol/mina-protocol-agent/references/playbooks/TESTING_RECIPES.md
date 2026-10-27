# Mina/o1js Testing Recipes

## Invariant matrix template

Include the [3.1.0 regression cases](NETWORK_ERA_AND_O1JS_COMPATIBILITY.md) for
required debits, token substitution, callee authorization and conditional updates.
Run them against the pinned package and deployment artifact identity.

| Invariant | Happy path | Negative test | Edge test | Status |
|---|---|---|---|---|
| Unauthorized user cannot update state | valid user succeeds | attacker fails | old admin fails |  |
| Witness must match commitment | correct secret succeeds | wrong secret fails | zero/max secret |  |
| Nullifier one-time use | first use succeeds | second use fails | different domain succeeds/fails as intended |  |

## Expected failure helper pattern

Adapt to your test runner:

```ts
async function expectTxToFail(fn: () => Promise<unknown>) {
  let failed = false;
  try {
    await fn();
  } catch (_err) {
    failed = true;
  }
  expect(failed).toBe(true);
}
```

## Wrong witness test

```ts
it('rejects wrong witness', async () => {
  await expectTxToFail(async () => {
    const tx = await Mina.transaction(user.toPublicKey(), async () => {
      await zkApp.updateWithSecret(wrongSecret);
    });
    await tx.prove();
    await tx.sign([user]).send();
  });
});
```

## Unauthorized caller test

```ts
it('rejects unauthorized caller', async () => {
  await expectTxToFail(async () => {
    const tx = await Mina.transaction(attacker.toPublicKey(), async () => {
      await zkApp.adminOnlyMethod(value);
    });
    await tx.prove();
    await tx.sign([attacker]).send();
  });
});
```

## Stale state test idea

```text
1. Read old root.
2. Build witness for old root.
3. Submit another valid transaction that changes root.
4. Try old transaction or recreate with old witness.
5. Expect failure or documented retry behavior.
```

## Replay/nullifier test idea

```text
1. Generate valid proof with nullifier N.
2. Submit transaction.
3. Submit same proof or same nullifier again.
4. Expect failure.
```

## Permission test idea

```text
1. Deploy with intended permissions.
2. Try to change verification key as normal user.
3. Try to change permissions as normal user.
4. If upgrade exists, try with wrong governance/admin proof.
5. Expect failures.
```

## Token supply property test idea

```text
For random sequence of valid mint/burn/transfer operations:
  expectedSupply = minted - burned
  on-chain/accounting supply commitment matches expectedSupply
For invalid operations:
  transaction fails and supply stays unchanged
```

## Proof-enabled smoke test

Use fast tests with proofs disabled during development, but keep at least one proof-enabled smoke test for the core circuit before release:

```text
compile contract/program
run one valid proof
run one invalid proof if feasible
verify final state
record proving time roughly
```

## Berkeley/Mesa compatibility matrix

```text
For every supported network era:
  compile with the intended o1js version
  record verification-key hash
  build and serialize one transaction
  sign with the intended signer era
  prove and verify one core path
Reject:
  mixed signer/network era
  stale verification key
  stale proof/cache
  old serialized VK assumptions
  max-limit-plus-one state/event/action/AccountUpdate cases
```

## Wallet and fee-payer preflight tests

```text
wrong wallet network -> rejected before confirmation
wrong fee payer -> rejected
stale nonce or pending collision -> bounded rebuild from fresh state
missing expected AccountUpdate subtree -> fail closed
proof-required update sent before prove() -> rejected
backend attempts to sign wallet-owned fee payer -> rejected
```

## Inclusion, indexing, and finality tests

```text
broadcast returns hash, live endpoint has no inclusion -> submitted only
included transaction, archive lags -> do not overwrite authoritative live state
archive catches up -> indexed state advances idempotently
transaction dropped or reorganized -> explicit recoverable status
safe/final policy reached -> business effect can advance
```

## Delegated authorization tests

```text
wrong agent, mission, network, contract, tool, dataset, recipient, token, or budget -> fail
expired, revoked, not-yet-valid, or replayed authorization -> fail
altered output or payment context -> receipt verification fails
concurrent use of one-time authorization -> at most one success
request-supplied issuer/JWKS/network trust root -> rejected
```
