# Delegated Authorization and Privacy

Use this playbook when a human, organization, service, or autonomous agent delegates authority to another component and the action is enforced by a Mina/o1js proof, signature, contract, relayer, or receipt.

## Identity is not authorization

Authentication answers who the subject is. Delegated authorization must also answer:

- who granted authority;
- which agent or delegate receives it;
- the exact mission or action;
- which contract, application, network, and token context it applies to;
- permitted tools, datasets, recipients, and side effects;
- amount, budget, rate, or payment rail limits;
- start, expiry, slot, and revocation conditions;
- nonce, nullifier, sequence, or one-time-use policy;
- required checkpoints and approvals;
- output or receipt commitments;
- what remains trusted outside the proof.

A login token or generic signature is not enough when downstream services must enforce mission scope.

## Canonical authorization statement

Define a versioned canonical statement before hashing or signing:

```text
schemaVersion
domain
issuer / owner
agent / delegate
organization or tenant
network and era
contract / app id
action or mission id
tool and dataset scopes
recipient and token id
amount / budget / rate limits
payment rail and context digest
not-before and expiry
nonce / nullifier / sequence
policy hash
input commitment
expected output or receipt commitment
revocation registry or root
```

Use an unambiguous serialization, explicit field order, and domain separation. Bind optional-field presence and collection lengths so two implementations cannot hash different meanings to the same apparent statement.

## Enforcement checkpoints

Verify authorization immediately before each sensitive boundary:

- payment or balance movement;
- external API call with side effects;
- private-compute request;
- data export;
- deployment or verification-key update;
- contract admin action;
- final receipt or settlement.

Do not verify once at login and assume all later actions remain in scope.

## Replay and revocation

- choose whether authorization is single-use, bounded-use, or reusable;
- bind a nonce, nullifier, sequence, or usage counter;
- scope replay protection to the intended domain and contract;
- define expiration in slots/time using an on-chain or otherwise trusted source;
- make revocation checkable by the verifier at enforcement time;
- test concurrent attempts and retries;
- make receipts idempotent and link them to the consumed authorization.

## Receipt model

A durable receipt should bind enough context to audit the action without revealing private inputs:

```text
authorization commitment
policy hash
input or dataset commitment
output hash
payment context digest
checkpoint result
network/contract context
timestamp or slot
verifier identity/version
```

A receipt is evidence only for fields it cryptographically binds and for trust assumptions it explicitly discloses.

## Privacy map

For each field, classify:

```text
on-chain public
proof public input/output
private witness
wallet-visible
frontend-visible
backend-visible
relayer-visible
archive/event-visible
log/analytics-visible
retained or deleted
```

Commitment-first design does not automatically hide timing, traffic shape, fee payer, contract address, amounts encoded elsewhere, event metadata, or repeated identifiers.

## Data availability and encrypted payloads

When publishing data outside the chain:

- anchor a canonical commitment on-chain when the protocol needs integrity;
- encrypt private payloads before DA or storage publication;
- bind ciphertext metadata, schema version, commitment, and retrieval reference;
- document key custody, rotation, deletion, and recovery;
- state clearly what is still public, including timing and traffic metadata;
- do not call application-layer encryption full balance or transaction privacy unless the state-transition design actually provides it.

## Trust-root safety

- never accept issuer, audience, JWKS URL, contract address, network, or verifier key from an untrusted request as its own trust root;
- pin or configure trust roots out of band;
- normalize provider-specific claims before commitments;
- include provider/issuer context in subject mapping;
- reject unmapped or ambiguous subjects in production;
- keep secrets and private keys out of repositories, logs, generated demo bundles, and frontend builds.

## Required negative tests

- correct identity but wrong mission fails;
- correct mission but wrong agent fails;
- wrong network, contract, token, recipient, tool, or dataset scope fails;
- amount or budget above limit fails;
- expired, not-yet-valid, revoked, or already-consumed authorization fails;
- altered output or payment context fails receipt verification;
- optional-field or serialization ambiguity cannot change meaning;
- concurrent replay attempts cannot both succeed;
- private inputs remain absent from events, payloads, logs, and analytics;
- a verifier cannot substitute request-supplied trust roots.
