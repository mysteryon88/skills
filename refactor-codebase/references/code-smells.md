# Catalog of code smells and remedies

Use these signals to guide inspection, not as automatic thresholds.
No single metric proves that code should be changed.

| Signal | What to check | Possible techniques |
|---|---|---|
| Long Method | Are abstraction levels, responsibilities, I/O, and computation mixed? | Extract Function, Split Phase |
| Deep Nesting | Can guard clauses be used without changing side-effect order? | Replace Nested Conditional |
| Long Parameter List | Do the parameters form a conceptual group? | Introduce Parameter Object |
| Flag Argument | Does a boolean select different scenarios/contracts? | Split Function, Enum/Strategy |
| Repeated Switch | Are branches repeated by type? | Strategy, Polymorphism |
| Feature Envy | Does the function mostly use data owned elsewhere? | Move Method |
| Side-effect soup | Are decisions and I/O mixed together? | Functional Core / Imperative Shell |
| God Object/Class | Are there several independent reasons for change? | Extract Class/Module |
| Divergent Change | Does one module change for unrelated reasons? | Extract Module |
| Shotgun Surgery | Does one rule change in several places? | Move/Extract Module |
| Inappropriate Intimacy | Do modules read/change each other's internals? | Encapsulate, ownership, seam |
| Pass-through Module | Does the layer only forward a call? | Inline/Collapse Module |
| Speculative Generality | Does the abstraction exist for a hypothetical future? | Remove abstraction |
| Cyclic Dependency | Do modules form a cycle? | Invert dependency, stable contract |
| Duplicate Code | Is the business meaning the same or only the text? | Extract Function/Module |
| Data Clumps | Are fields often passed together? | Parameter Object / Value Object |
| Primitive Obsession | Does a primitive encode a domain concept with rules? | Value Object / Newtype |
| Magic Literal | Does the value have a meaningful name? | Extract Constant / Enum |
| Scattered Configuration | Is a setting changed in multiple places? | Configuration object |
| Mutable Shared State | Do multiple owners change the same object? | Encapsulation, ownership |
| Hidden State Machine | Do flags allow impossible combinations? | Tagged union / state machine |
| Temporal Coupling | Is one method valid only after another? | Explicit lifecycle / type-state |
| Hardcoded Dependency | Does business logic create its own DB/client/clock/SDK? | DI, adapter |
| External Type Leakage | Does an SDK type pass through business layers? | Anti-corruption layer |
| Error Leakage | Do low-level errors leak outward? | Translate at module boundary |
| Unused Code | Were dynamic callers/reflection/entrypoints and deletion rules checked? | Keep or remove after obtaining required authorization |

## Safe Abstraction Gate for duplication

Before merging, answer:
1. Is this one business policy or just a similar implementation?
2. Do both fragments change for the same reason?
3. Is there a shared concept/name that is honest for all callers?
4. Are differences in errors, permissions, rounding, defaults, and side effects preserved?
5. Will caller-specific flags and modes appear?
6. If the implementations diverge, will that be a bug or legitimate evolution?

If they may legitimately diverge, keep them separate (`keep-duplicated`). If a shared
abstraction has grown conditional branches, consider `de-abstract`. Similar text
is not sufficient reason to merge.

The rule of three is a heuristic, not a law. A shared rule may be worth extracting with two
consumers, while three similar blocks may represent different domain policies.

## Priority

Assess impact, likelihood, confidence, and cost/risk separately. Do not invent frequency.
A rare scenario involving data loss or authorization bypass may still have critical priority.
