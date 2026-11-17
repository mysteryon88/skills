# Rust: data, ownership, builds

Record `rustc -Vv`, Cargo.lock, target triple/CPU features, Cargo profile, RUSTFLAGS, config overrides, allocator, and feature set. Compare identical modes. `dev` versus `release` does not prove an algorithmic improvement. Also run boundary/error tests with the production profile.

After checking scripts/build.rs and the local environment, choose existing checks such as `cargo test --locked --offline`, `cargo test --release --locked --offline`, and `cargo clippy --locked --offline`. First configure CARGO_TARGET_DIR and temporary/output paths inside the project .tmp as described in [integration](integration.md). Offline mode requires dependencies to be already available. Do not silently download them if they are missing. `cargo test --release` checks release optimizations, but the test harness ignores profile `panic=abort` and uses unwind. Check production panic behavior separately if needed. Run `cargo bench` only with a known project harness/profile. `std::hint::black_box` prevents some benchmark optimizations but does not prove measurement correctness.

| Bottleneck | Candidate | Check the trade-offs |
|---|---|---|
| Unnecessary clone/owned strings | Borrow, &str/&[T], Cow where ownership is conditional | Borrow may retain the entire large source buffer. Concurrency/lifetime |
| Vec/String growth | Bounded with_capacity, reuse, clone_from | Capacity/retention. Input must not dictate unbounded allocation |
| Pointer chasing | Vec/arena/indexes, SoA for needed fields | Deletion, address stability, locality under other access patterns |
| Large enum/object | Extract large rare payload, reduce representation | New allocation or indirection. Check `size_of` on the target platform |
| Repeated passes | Remove unnecessary collect, use entry instead of double lookup | Ordering, iterator side effects, lazy evaluation |
| Binary | Analyze monomorphization/dependencies. Treat LTO/profile as separate experiments | Build time, runtime, CPU compatibility, diagnostics |

Do not automatically enable `panic=abort`, change overflow-checks or debug-assertions, disable bounds checks, add unsafe/repr(packed), or use `target-cpu=native`. These can change contracts, safety, or portability. Compare even authorized flags separately with the same features/inputs and tests. “More opt-level” does not guarantee less time or a smaller binary.

Do not assume Vec<bool> is a packed bit vector like C++. Do not use memory layout as a serialization format by default. An explicit byte format and versioning matter more than `size_of`. Vec<u64> may suit dense Boolean sets, but check tail bits, bounds, endianness, update/race semantics, and the full conversion cost.

SmallVec, compact strings, compressed bitmaps, and arenas are candidates only after profiling and approval for new dependencies. Inline payload reduces heap allocations but increases the containing object's size. Do not choose the inline array size by guesswork.

If the task concerns build storage, separately measure the final executable, target/incremental/dependency artifacts, clean build, and incremental rebuild. A smaller binary does not mean a smaller build cache. Do not delete the user's caches for a metric.

Sources: [RUST-SKILL], [RUST-PROFILES], [RUST-BLACKBOX], [RUST-ALLOC], [RUST-SIZE]. The example in examples/rust is for local checks. See VALIDATION.md for whether it was run.
