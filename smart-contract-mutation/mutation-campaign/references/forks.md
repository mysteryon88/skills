# Local fork execution with pinned upstream reads

First find network/RPC/block in tests, project configuration, environment references, scripts and existing records. Honor the project's explicit values. For EVM, public endpoint discovery may use [Chainlist](https://chainlist.org/) / its [chain data](https://github.com/ethereum-lists/chains); check chain ID and archive capability, not just endpoint availability. For TON use TON-specific clients/block identities and [Toncenter's API](https://toncenter.com/api/v2/). Never translate an EVM block model into TON implicitly.

Set RPC URLs only in inherited environment variables, outside source-controlled files. Lane example:

```json
{"fork":{"kind":"evm","chain_id":1,"block":19000000,"rpc_envs":["PROJECT_RPC_URL","PROJECT_ARCHIVE_FALLBACK"],"test_mode":"forge"}}
```

`block` can be a number or `{number,hash}`. With no block, the first request resolves `finalized` and saves number/hash before any test. Each later phase validates that same number/hash and chain ID. Fallback endpoints preserve the exact historical block; none is silently replaced with latest. Endpoint failures block only the affected lane. Pin receipts save host and environment **name**, never URL/key. The controller's RPC helper exposes only an explicit read-method allowlist; it cannot submit transactions.

With `test_mode="forge"`, baseline/canary tests receive pinned `--fork-block-number`, `ETH_RPC_URL` and `FOUNDRY_FORK_BLOCK_NUMBER`; native Forge receives the same pin. The test argv must be a real `forge test` command. Tests creating their own forks must explicitly consume/validate these inputs. For wrappers/custom runners choose `test_mode="env"` and provide `binding_evidence` explaining the actual test harness's use of `MUTATION_RPC_URL`, `MUTATION_FORK_BLOCK` and `MUTATION_FORK_HASH`; a pin alone is not proof a custom harness used it. Scope review must reject hard-coded conflicting forks.

TON example uses `kind="ton"`, `test_mode="env"`, `rpc_envs`, verified binding evidence and optionally a full masterchain block `{workchain,shard,seqno,root_hash,file_hash}` or explicit seqno. Read-only `getMasterchainInfo`/`lookupBlock` pins and revalidates all five identity fields. The harness receives `MUTATION_TON_BLOCK` JSON and must use a compatible TON remote-storage/client at that pin. Masterchain pinning alone does not establish arbitrary shard-state availability or a complete TON fork. If the project's client cannot bind the state identity, keep execution blocked/unverified; do independent local contract lanes.

Fork tests execute locally. Cached state can be incomplete: read-only network requests are allowed for missing pinned data. Do not promise a complete offline chain snapshot. Save network, block number/identity, hash, host/source and test/cache provenance; never RPC secrets. No public transactions, deployments, wallet signing or broadcast commands are authorized.
