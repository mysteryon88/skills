# Example: Privacy nullifier pattern

## Bad

```ts
const nullifier = Poseidon.hash([secret]);
```

This can link the user across apps and actions.

## Better

```ts
const nullifier = Poseidon.hash([
  DOMAIN_NULLIFIER,
  appId,
  actionId,
  epoch,
  secret,
]);
```

## Tests

- same nullifier cannot be used twice for same action;
- different domain creates different nullifier if unlinkability is intended;
- relayer cannot change action/recipient after proof generation.
