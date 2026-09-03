# External-message verification

Prefer an internal message for a public, expensive ZK verification path. Internal messages carry value; external messages do not, so after `ACCEPT`/`acceptExternalMessage()` the contract pays the remaining computation from its own balance.

## Safe decision sequence

Before accepting an external message, perform every check that fits safely within gas credit and does not require expensive pairing verification:

1. parse a fixed, bounded envelope;
2. reject unexpected bits, refs, field counts, and versions;
3. check expiry and a stored seqno/nonce;
4. authenticate a signer, relayer, or other cheap pre-authorized identity;
5. bind that envelope to the proof/message hash and intended action;
6. call `ACCEPT` or the language wrapper;
7. update the authenticated external-envelope replay state and execute `COMMIT` before expensive or otherwise fallible work;
8. run ZK verification and semantic policy;
9. consume the application nullifier and apply the business transition atomically on success.

The envelope replay value and application nullifier are separate security layers. A failure after `COMMIT` consumes the signed envelope so validators cannot charge the contract for it again, while leaving the application nullifier and protected business state unchanged. If the post-commit design cannot safely represent that outcome, use a two-transaction internal-message continuation.

Never call `ACCEPT`, `SETGASLIMIT`, or their language wrappers unconditionally.

## When the proof is the only authentication

If proof verification itself is the first meaningful authorization check, an external receiver may have to accept before it can reject an attacker. That creates a balance-drain surface because anyone can submit invalid proofs repeatedly. Use one of these designs instead:

- a value-carrying internal message;
- a signed/seqno-protected external envelope whose signature is checked before accept;
- an authenticated relayer or wallet contract that sends the internal message;
- a deliberately funded verifier service with explicit rate, reserve, and loss limits, documented as such.

Do not describe an unguarded external ZK endpoint as permissionless and economically safe.

## Required tests

- malformed envelope rejected before acceptance;
- wrong signer, seqno, action, domain, or expiry rejected before acceptance;
- same authenticated envelope submitted twice;
- valid envelope with invalid proof after acceptance;
- failure after `COMMIT`: envelope replay state consumed, application nullifier and business state unchanged;
- repeated invalid proofs and exact contract balance/gas delta;
- insufficient reserve or low balance;
- replay-state behavior after compute/action failure;
- proof/message hash mismatch;
- getter success does not bypass receiver authorization.

Record whether each failure occurs before or after acceptance and who pays for it.
