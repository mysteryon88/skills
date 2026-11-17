# Go evidence checklist

Collect toolchain/build tags, entrypoint, exact arguments/request bytes and caller identity. Follow parsing, checks, error returns, deferred operations, state mutation and downstream calls. For concurrent findings, identify goroutines and shared values, synchronization operations and the required happens-before relationships. Distinguish a possible interleaving from an observed one; capture race/test logs only when execution is authorized and tie them to exact source bytes. Inspect cancellation, cleanup and error paths. No runtime evidence means a source-supported or hypothetical claim, never an observed race.

Primary orientation: [The Go memory model](https://go.dev/ref/mem). Apply its questions to actual synchronization and the project's toolchain; do not infer scheduling from diagram order alone.
