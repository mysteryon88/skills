# EVM Contract Mutation Checklists

## Contents

- [How To Use](#how-to-use)
- [Token Standards](#token-standards)
- [Vaults And Accounting](#vaults-and-accounting)
- [Permissions And Upgrades](#permissions-and-upgrades)
- [Markets And External Data](#markets-and-external-data)
- [Governance And Signatures](#governance-and-signatures)
- [Fees, Rounding, And Decimals](#fees-rounding-and-decimals)

## How To Use

Use these prompts after a Solidity, Vyper, or Fe mutation campaign produces survivors, or when proposing project-specific custom rules. Frame every item as a test-strength question, not an exploit claim:

- Which test should kill this mutant?
- Which boundary, revert path, or state assertion is missing?
- Which invariant should still hold after the mutated branch executes?

## Token Standards

ERC20:

- Balance mutation: would a transfer mutant be killed by sender and recipient balance assertions?
- Allowance mutation: would `approve`, `transferFrom`, and allowance decrement mutants be killed?
- Zero-address mutation: do mint, burn, and transfer tests cover zero-address rejection or allowed burn semantics?
- Event mutation: do tests assert `Transfer` and `Approval` topics and values when the contract promises standard compliance?

ERC721:

- Ownership mutation: would `ownerOf`, `balanceOf`, and transfer ownership updates be killed together?
- Approval mutation: do tests distinguish approved operator, token approval, and unauthorized caller paths?
- Receiver mutation: do safe-transfer tests kill mutants that skip or invert receiver acceptance checks?

ERC1155:

- Batch mutation: do tests assert every id/value pair, not only array length?
- Receiver mutation: do single and batch safe-transfer tests kill acceptance selector changes?
- Supply mutation: if supply is tracked, do mint/burn tests assert per-id totals?

## Vaults And Accounting

ERC4626 vaults:

- Share/asset conversion mutation: do preview and state-changing methods agree under deposit, mint, withdraw, and redeem?
- Rounding mutation: are floor/ceil expectations asserted at small amounts and non-even exchange rates?
- Limit mutation: do maxDeposit, maxMint, maxWithdraw, and maxRedeem tests kill boundary changes?
- Fee mutation: do fee-on-deposit or fee-on-withdraw tests assert both assets and shares?

Staking and rewards:

- Accumulator mutation: do reward-per-token and user index tests cover multiple users and time gaps?
- Claim mutation: does claiming update debt and transfer exactly once?
- Exit mutation: do withdraw/claim combined flows assert balances, rewards, and final storage?

## Permissions And Upgrades

Access control, Ownable, and AccessControl:

- Owner/admin mutation: do unauthorized caller tests kill inverted `msg.sender` or role checks?
- Role constant mutation: do tests use actual role ids and fail for neighboring roles?
- Renounce/transfer mutation: do ownership or admin transfer tests assert old and new permissions?

Upgradeable proxies / upgradeable proxies:

- Initializer mutation: do tests kill missing initializer guard and double-initialization paths?
- Upgrade authorization mutation: do unauthorized upgrade tests assert revert reason or custom error?
- Storage layout mutation: do upgrade tests assert state survives across implementation changes?

Pausable contracts:

- Guard mutation: do paused and unpaused paths both have positive and negative tests?
- Admin mutation: do tests kill unauthorized pause/unpause changes?
- Partial pause mutation: if only some functions pause, do tests prove unaffected functions still work?

## Markets And External Data

Oracles and stale prices / oracles:

- Staleness mutation: do tests kill `<`, `<=`, and missing timestamp checks?
- Decimal mutation: do tests cover oracle decimal scaling and price precision?
- Negative or zero price mutation: do tests reject invalid oracle answers when required?

AMMs, swaps, and slippage:

- Slippage mutation: do tests kill min-out, max-in, and deadline boundary changes?
- Reserve mutation: do tests assert reserve updates after swaps and liquidity changes?
- Fee mutation: do tests cover exact fee basis points and rounding direction?

Bridges:

- Replay mutation: do tests kill nonce, message id, or processed-message guard changes?
- Domain mutation: do tests assert chain id, source domain, and destination domain checks?
- Validator mutation: do tests distinguish threshold, signer set, and duplicate signer behavior?

## Governance And Signatures

Governance:

- Quorum mutation: do tests kill quorum threshold and voting period boundary changes?
- State mutation: do tests assert proposal state transitions before and after each boundary?
- Execution mutation: do tests kill double-execute and execute-before-success changes?

Permit / permit, signatures, and domain separators:

- Nonce mutation: do tests assert nonce increments and replay rejection?
- Deadline mutation: do tests kill `<` versus `<=` and expired deadline changes?
- Domain mutation: do tests include wrong chain id, wrong verifying contract, and wrong name/version cases?
- Signer mutation: do tests reject signatures from non-owners or wrong delegates?

## Fees, Rounding, And Decimals

Fee logic and basis points:

- Basis-point mutation: do tests assert exact fee at 0, 1, max, and typical values?
- Recipient mutation: do tests assert fee recipient balances, not only user net amount?
- Cap mutation: do tests kill fee cap boundary changes?

Rounding and decimals:

- Scaling mutation: do tests cover token decimals other than 18 where supported?
- Dust mutation: do tests assert behavior for tiny amounts and uneven division?
- Overflow boundary mutation: do tests cover checked and intentionally `unchecked` arithmetic assumptions?
