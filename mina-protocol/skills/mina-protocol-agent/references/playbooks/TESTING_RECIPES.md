# Mina/o1js Testing Recipes

## Invariant matrix template

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
