# Architecture patterns and decomposition

## Functional Core / Imperative Shell

Separate deterministic decisions from I/O. The core receives data and returns
a decision/result. The shell reads databases, network, filesystem, and time, and performs
side effects. Do not make a function artificially pure when its purpose is to
manage a transaction or resource lifecycle.

## Extract Function / Move Function

Extract a complete conceptual step. The name should explain the intent
(`validatePayment`, not `stepTwo`). Check inputs/results, captured local
variables, side-effect ordering, exceptions, early returns, async/await, and cancellation.

## Extract Class / Module

Extract a class when there is state, identity, invariants, or a lifecycle.
Extract a module when there is a related group of functions and types that does not need
object identity. For a new module, document its responsibility,
public interface, data ownership, dependencies, invariants, error model, and lifecycle.
Do not create a class for every function or turn a module into a `utils` dumping ground.

## Deep modules and interfaces

A good module hides substantial internal complexity behind a small interface.
The interface includes signatures, invariants, valid call order, errors,
configuration, and performance/consistency guarantees. Do not export
internal helpers without need. Check the deletion test: if the module is removed,
does the complexity disappear or spread across callers?

## Package by feature / common closure

Group by product features and reasons for change, not only by
`controllers/`, `services/`, `utils/`. Git co-change is additional evidence,
but change correlation does not prove an architectural relationship.

## Dependency Direction / Composition Root

- Domain policy should not depend on unstable SDK/DB/UI details.
- Create dependencies in the composition root and pass them to their owners.
- Invert a dependency at a real boundary where this reduces coupling.
- Do not introduce a DI container, interface, or factory when a parameter is enough.

## Value objects and types

Use Value Object / Newtype / branded type for domain values with
invariants or different units (Money, Email, DurationMs, UserId) when
this reduces errors and fits the language. Do not wrap primitives without purpose.

## Adapter / Anti-corruption Layer

Isolate external APIs, SDKs, ORMs, and data formats at the boundary. Internal logic
should use its own concepts, not vendor types. Do not create
an abstraction for every external function. Provide a stable replacement/testing point.

## State Machines

For a complex process, create a table with current state | event | guard | next state |
side effects. Check impossible combinations, repeated events, out-of-order
callbacks, retries, cancellation, timeout, and recovery. For two simple states,
a regular condition may be clearer.

## Monolith: start with a modular monolith

1. Identify bounded contexts by business meaning.
2. Find incoming calls and shared symbols.
3. Build a dependency and cycle graph.
4. Check co-change in Git.
5. Identify owners of tables/aggregates and invariants.
6. Check transaction boundaries.
7. Create an in-process interface and route callers through it.
8. Check that there are no bypass calls.

A service boundary is justified when there is a real need for independent deploy,
scaling, or ownership and there are models for data, failures, consistency,
idempotency, observability, migration, and rollback. Do not extract a service that
continues to write the same data together with the monolith in one transaction.
