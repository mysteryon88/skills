# Solana evidence checklist

Record program/deployment identity, instruction bytes and ordered accounts with ownership, signer and writable status. Trace deserialization, account identity/owner checks, PDA seeds/bump and authorization. At each CPI, inspect the actual invoked program, passed account metadata and signer derivation. Distinguish caller-side checks from callee requirements; capture error propagation and transaction effects before asserting a committed balance/data change. Retrieve missing invoked program code or pin transaction logs/state as appropriate. Do not infer authority merely because an account appears in the account list.

Primary orientation: [Solana cross-program invocation](https://solana.com/docs/core/cpi). Collect concrete project/runtime evidence; no universal deployment or compute-limit assumptions.
