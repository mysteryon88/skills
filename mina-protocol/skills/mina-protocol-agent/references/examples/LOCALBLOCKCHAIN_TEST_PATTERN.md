# Example: LocalBlockchain test pattern

```ts
import { Mina, PrivateKey, AccountUpdate } from 'o1js';

const Local = await Mina.LocalBlockchain({ proofsEnabled: false });
Mina.setActiveInstance(Local);

const deployer = Local.testAccounts[0].key;
const user = Local.testAccounts[1].key;
const attacker = Local.testAccounts[2].key;

const zkAppKey = PrivateKey.random();
const zkAppAddress = zkAppKey.toPublicKey();
const zkApp = new MyContract(zkAppAddress);

const deployTx = await Mina.transaction(deployer.toPublicKey(), async () => {
  AccountUpdate.fundNewAccount(deployer.toPublicKey());
  await zkApp.deploy();
});
await deployTx.prove();
await deployTx.sign([deployer, zkAppKey]).send();
```

Use proofs disabled for fast iteration, but add at least one proof-enabled smoke test before release.
