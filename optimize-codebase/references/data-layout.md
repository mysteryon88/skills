# Compact data: choose for the workload, not fashion

## Dense flags

For N independent Boolean values in an array that uses one byte per value, the useful payload is N bytes. With one bit per value, it is ceil(N/8). Storing whole 64-bit words requires 8×ceil(N/64). This is payload arithmetic only. It excludes length, headers, capacity, allocator, validity map, indexes, and wrappers.

For 1 000 000 flags: 1 000 000 bytes versus 125 000 bytes of useful data. This is NOT a promise that “the whole process uses 8 times less.” Textual JSON booleans/strings and SQL storage have different overhead. Measure their size separately.

Bitsets are especially useful for dense IDs, intersections/unions, and popcount. If a single ID with a very large value is set, a conventional dense bitmap may perform worse than sorted IDs, a hash set, or a compressed bitmap. Compare actual density, ID range, random update frequency, and operations. Roaring and other compressed bitmaps require workload validation and approval to add a dependency. They are not universal choices.

## Gate before changing the representation

1. Establish the domain: two states, or true/false/null/unknown? Nullable values need an extra marker/bitmap, not a lost state.
2. Define bit numbering, width, length, and endianness in serialization. Reserve version/unknown bits. Do not change external protocols automatically.
3. Check 0/1/word-1/word/word+1, negative/oversized indexes, overflow in length calculations, trailing bits, malformed input, and the maximum allocation limit.
4. Preserve read/update/clear semantics. Two threads changing different bits in the same word can still conflict. Use appropriate atomics/locks. Do not write custom lock-free code without proof.
5. Measure pack/unpack, count/intersect, random reads/writes, allocation/retention, and the full pipeline. Measure cold construction and steady state separately.
6. Confirm compatibility between old and new readers. A dual-read/write migration needs a separate task and validation. The skill does not re-encode a production store without authorization.

For external formats, do not serialize native struct memory as if the ABI were stable. Go struct alignment and Rust repr(Rust) are not portable wire formats. JavaScript bitwise Number is not arbitrary 64-bit arithmetic.

## Other compact representations

| Conditions | Candidate | When it performs worse |
|---|---|---|
| Small integer range | Validated narrower type | Overflow, data growth, ABI, nullability |
| Many repeated strings | Dictionary IDs/interning with bounded lifetime | High cardinality, global retention |
| Long identical runs | RLE | Frequent alternation and updates |
| Monotonic values | Delta + varint/bit packing | Random access, negative/large deltas |
| Analytical scans over selected fields | Columnar/SoA | Frequent row updates, assembling whole records |
| Repeated large payload | Lossless compression with the right block size | CPU, latency, random reads, incompressible input |
| Frequent lookups/membership checks | Index/map/bitmap | Additional storage and writes |

Packing before compression does not guarantee a better result. Compare compressed bytes, CPU, decompression peak, latency, and reversibility. Do not introduce lossy quantization, Bloom false positives, or truncated hashes in place of exact comparison without a separate requirements change. Base64 increases binary payload size, so a “binary instead of JSON” win must account for the actual transport.

Keep the compact internal representation behind a clear interface. The code should not become a scatter of unexplained masks. A comment should record what the bits mean and the benchmark result, not promise a permanent speedup.

Sources: [ROARING], [ARROW], [PROTOBUF], [PG-BITS], [ECMA-BITS]. The mathematical examples and gates are a synthesis for this package.
