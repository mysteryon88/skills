# React: user-perceived latency, memory, bundle

Identify React/version, framework/bundler, compiler configuration, development/production/production-profiling mode, StrictMode, SSR/RSC, and client boundaries. Do not convert the project to Next.js just to apply a Next.js recipe.

## Measurements

Use React Profiler to attribute renders, not to make end-to-end latency claims. `actualDuration` applies to subtree rendering. `baseDuration` is an estimate. Measure commit/paint, network, and browser work separately. Profiler adds overhead. Production profiling requires a special build with profiling enabled, which is disabled by default in a regular production build. Development profiling does not require this production build. Compare identical instrumentation. Confirm user-perceived improvement using a regular production build on representative devices.

Record the click/type/scroll → visible result scenario, p50/p95 event timings with a sufficient sample, long tasks, request count/size, transferred compressed JS, parsed JS, and retained heap. A conditional Node benchmark for a pure function is not a React rendering/INP test. Development/StrictMode timings do not stand in for shipped production.

## Search order

Start with network waterfalls and unnecessary requests, then bundle/serialization, then rendering and computation volume. Use the existing profiler/browser harness. Do not download tools, create real mailings/payments, or send user data.

| Signal | Candidate | Risk |
|---|---|---|
| Independent awaits run sequentially | Bounded parallel execution | Failure/cancellation/order, upstream load, RAM |
| Large, rarely used code | Dynamic import and a loading boundary | Chunk waterfall, SSR/hydration, export semantics |
| Repeated data lookup | Lookup map/precomputation | Map creation, duplicate semantics, invalidation |
| Expensive rerenders | Localize state, stabilize meaningful props | Stale closure, unnecessary retained cache |
| Huge DOM | Virtualization/visible subtree | Focus, accessibility, search, scroll state |
| Too many client props | Pass only the needed data | SSR/client contracts, auth boundary |

Add manual useMemo only after measuring. The calculation must be pure. Dependencies must contain all reactive values, have constant length, and pass lint. Test changes to each dependency, mount/unmount, suspend/retry, and StrictMode. React may discard the cache, so correctness must not depend on its presence/identity. Evaluate retained memory and hit/miss/dependency-change frequency. Check whether React Compiler already does what is needed. Do not add useMemo/useCallback/memo everywhere based on one static signal.

Do not store cross-user data in a global unbounded Map. For a cache, define its size, eviction, lifetime, invalidation, and tenant/auth key. Do not change TTL/consistency without a separate decision. A migration to Map must preserve the original code's first/last duplicate and equality behavior. Map and === have subtleties, such as NaN.

For large binary sets, consider TypedArray, but Number-bitwise operations have 32-bit semantics. Do not calculate large indexes with `i >> 5` without a range limit. Separately check serialization/JSON and React immutability for BigInt and TypedArray. Do not modify a buffer under the same reference in a way that prevents memo/React from detecting the update.

Sources: [VERCEL], [REACT-PROFILER], [REACT-MEMO], [ECMA-BITS].
