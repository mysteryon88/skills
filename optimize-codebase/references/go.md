# Go: CPU, memory, I/O

## Discovery and measurements

First check `go version`, go.mod/toolchain, GOARCH/GOOS, build tags, CGO, CPU limits, and GOMAXPROCS. Do not use a newer API until the project's version supports it. The package example uses `b.N`. `b.Loop` requires a compatible version.

Choose commands based on the project. Before running them, configure `$work`, TEMP/TMP/TMPDIR, and Go cache/output paths as shown in the [example](examples.md#choose-a-working-directory-first). A typical set for a local environment without external effects is:

```bash
go test ./path/to/package
go test -race ./path/to/package
go test -run '^$' -bench '^BenchmarkTarget$' -benchmem -count 10 ./path/to/package
go test -run '^$' -bench '^BenchmarkTarget$' -o "$work/profile.test" -outputdir "$work" -cpuprofile "$work/cpu.out" -memprofile "$work/mem.out" ./path/to/package
go tool pprof -top "$work/cpu.out"
go tool pprof -alloc_space -top "$work/mem.out"
go tool pprof -inuse_space -top "$work/mem.out"
```

Profile separately from ordinary timing. Mark unavailable race/pprof checks. Do not expose net/http/pprof to the internet. Do not install benchstat or another tool without authorization. Do not invent its results if it is unavailable.

## Candidates based on the profile

| Signal | What to try | What may get worse |
|---|---|---|
| Signal | What to try | What may get worse |
|---|---|---|
| Allocations/copies on the hot path | Preallocate using a reliable bounded length, reuse buffers, use typed formatting, use streaming I/O | Excess capacity, retaining large backing arrays, aliasing |
| Repeated lookup/parsing | Index by key, remove duplicated work, prepare an immutable object in advance | Memory/preparation, invalidation rules, stale data |
| GC pressure | Fewer short-lived objects and pointer-rich structures | Lifetime changes, retained heap growth |
| CPU/cache misses | Contiguous arrays, dense bitsets, data-oriented layout | Update complexity, false sharing, packing cost |
| I/O wait | Batching/streaming, correct connection reuse, bounded concurrency | Peak memory, ordering/transactions, downstream load |
| Locks/goroutines | Mutex/block/trace and shorter critical sections/queues | Races, starvation, loss of cancellation/backpressure |

`sync.Pool` is not a permanent cache and does not guarantee that objects are available. Bound retained capacity. Reset must not leave private data or references behind. Converting between string/bytes through unsafe without copying is outside the standalone safe mode.

## RAM: a separate check

To make a RAM claim, measure peak RSS and suitable runtime/live-heap metrics under a long-running representative workload. Record GOGC/GOMEMLIMIT, GC activity, phase, and concurrency. Treat `B/op` and `allocs/op` as allocation diagnostics. Reducing GC through a longer-lived cache may increase RAM use.

GOMEMLIMIT is a soft limit on memory accounted for by the runtime, not a hard limit on total RSS. Do not substitute a universal percentage of container memory. GC tuning changes the CPU/memory balance and requires load testing. Advice about escape analysis/inlining applies to a specific implementation+toolchain. Recheck prior gains after upgrading Go.

Reordering struct fields requires checking layout, atomic alignment, unsafe/FFI/serialization/reflection, and source compatibility. Do not do it based only on a linter suggestion.

Sources: [GO-SKILL], [GO-DIAG], [GO-GC], [GO-PPROF], [BENCHSTAT].
