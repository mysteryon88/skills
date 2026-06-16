# Example: Safe counter pattern

This is a teaching example, not production code.

## Goal

A counter can only increment by 1 and must bind to the current on-chain state.

## Important pattern

Use `getAndRequireEquals()` for the state value used in the transition.

```ts
@method async increment() {
  const current = this.counter.getAndRequireEquals();
  const next = current.add(UInt64.from(1));
  this.counter.set(next);
}
```

## Tests to add

- deploy initializes counter;
- increment changes counter by exactly 1;
- stale-state transaction fails or retry behavior is documented;
- unauthorized caller test if increment is restricted.
