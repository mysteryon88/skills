# TON Contract Checklists

## Contents

- [How To Use These Checklists](#how-to-use-these-checklists)
- [Jetton](#jetton)
- [NFT](#nft)
- [Wallet](#wallet)
- [Multisig](#multisig)
- [Vesting](#vesting)
- [DEX](#dex)
- [Escrow](#escrow)
- [Staking](#staking)
- [Bridge](#bridge)
- [Governance](#governance)
- [Oracle](#oracle)

## How To Use These Checklists

Use these lists after `show_mutants` or other survivor triage. A survivor is most useful when translated into a missing test about authorization, message flow, state persistence, math, replay protection, or negative behavior.

## Jetton

- Verify mint, burn, and transfer paths with explicit total-supply and wallet-balance assertions.
- Check sender and owner authorization for minting, admin changes, and privileged maintenance paths.
- Assert wallet deployment, address derivation, and bounce behavior for missing or malformed wallets.
- Test forward amount, excess handling, and message payload semantics on transfer-like flows.
- Add negative tests for insufficient balance, duplicate actions, and invalid sender paths.

## NFT

- Verify collection-owner and token-owner authorization on mint, transfer, and metadata update paths.
- Assert ownership, content, royalty, and collection linkage after transfer or mint.
- Check approval or delegated-control behavior if the contract supports it.
- Test deploy and init state, including index, content defaults, and derived addresses.
- Add negative tests for invalid sender, duplicate mint, or malformed metadata/message payloads.

## Wallet

- Verify signature, sender, plugin, and owner authorization paths explicitly.
- Test replay protection, sequence number handling, and expiration or timeout fields.
- Assert send mode, bounce behavior, and outbound message construction.
- Check balance changes and reserved value after successful and rejected sends.
- Add negative tests for stale seqno, wrong signature, and unauthorized plugin actions.

## Multisig

- Verify threshold counting, signer uniqueness, and proposal state transitions.
- Assert execute-once semantics and replay prevention for approved proposals.
- Test expiration, cancellation, and signer-set update flows.
- Check outbound call data, value, and mode after execution.
- Add negative tests for duplicate approvals, insufficient threshold, and unauthorized execution.

## Vesting

- Verify cliff, interval, and unlock math at exact boundaries and just around them.
- Assert beneficiary, owner, and revoker permissions separately.
- Test partial withdrawal, full withdrawal, and remaining-balance bookkeeping.
- Check pause, revoke, or emergency flows if they exist.
- Add negative tests for early claim, over-withdrawal, and stale-schedule assumptions.

## DEX

- Verify reserve accounting, fee math, and slippage checks with explicit post-swap assertions.
- Test liquidity add and remove flows for both token sides and LP accounting.
- Assert routing, pool selection, and cross-contract message ordering where relevant.
- Check refund, bounce, and partial-fill behavior for failed or constrained swaps.
- Add negative tests for zero liquidity, stale quote, bad sender, and invalid path payloads.

## Escrow

- Verify depositor, beneficiary, arbiter, and admin permissions independently.
- Test release, refund, cancel, and dispute transitions with exact state assertions.
- Assert deadline handling, partial release rules, and single-use payout semantics.
- Check bounced messages and double-spend or double-release protection.
- Add negative tests for unauthorized release, late cancellation, and malformed dispute messages.

## Staking

- Verify stake, unstake, claim, and reward accrual math over time and across multiple actors.
- Assert validator, operator, or admin permissions separately from user flows.
- Test lock periods, cooldowns, and slash or penalty behavior at boundaries.
- Check total-shares versus underlying-balance consistency after every major action.
- Add negative tests for premature unstake, invalid reward claim, and stale-epoch assumptions.

## Bridge

- Verify source authorization, replay protection, nonce tracking, and message uniqueness.
- Test mint, burn, lock, unlock, or release parity across the bridged asset lifecycle.
- Assert pause, guardian, relayer, or emergency control paths explicitly.
- Check proof validation, chain-id handling, and malformed payload rejection.
- Add negative tests for replayed messages, wrong source domain, and partial-completion edge cases.

## Governance

- Verify proposal creation, voting, queue, timelock, and execution transitions.
- Test quorum, threshold, and voting-power snapshot math at boundaries.
- Assert proposer, voter, executor, and admin permissions independently.
- Check cancel, veto, expiration, and duplicate-execution protection.
- Add negative tests for stale snapshot, unauthorized execution, and malformed proposal payloads.

## Oracle

- Verify signer or feed authorization, quorum, and replay or round-id protection.
- Test freshness windows, timestamp bounds, and stale-data rejection explicitly.
- Assert decimal handling, scaling, and rounding behavior at boundaries.
- Check deviation thresholds, fallback behavior, and pause or emergency controls.
- Add negative tests for stale rounds, insufficient signatures, and malformed observation payloads.
