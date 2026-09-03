# Gas and code-size regression gates

Pairing checks and large verification keys are expensive. Measure the exact generated verifier and public-input shape rather than extrapolating from a small multiplier example.

## Record per verifier

- generator/compiler versions;
- circuit/VK hash and public-input count;
- contract language/template/contract name;
- deployment gas;
- getter/emulated gas if available;
- internal-message verification gas;
- application policy/state-transition gas;
- code size in bits and cells;
- message body size and refs;
- attached value used and resulting balance/reserve;
- date and test environment.

## Snapshot policy

Store structured snapshots next to tests. A change is accepted only when the reviewer can identify why it changed: VK size, input count, generator template, compiler, policy logic, or measurement method.

Use one of these gates:

- exact snapshot for stable deterministic measurements;
- percentage/absolute threshold with a documented baseline;
- explicit review annotation for intentional large changes.

Do not automatically rewrite snapshots on every test run.

## Worst-case paths

Measure:

- valid proof;
- cryptographically invalid but well-formed proof;
- maximum supported public-input count;
- duplicate/replay path after cheap checks;
- malformed shape path;
- application success with outgoing messages;
- bounce/recovery path where relevant.

A cheap precheck can reduce abuse, but it must not create semantic discrepancies or attacker-controlled acceptance.

## Attached value

The minimum value in a generated example is not a universal fee. Simulate realistic storage, forwarding, action, and reserve costs. Test below-minimum rejection, the selected operating value, and price/config sensitivity where tooling permits.

## Reporting

Include baseline and current values, absolute/percentage delta, cause, threshold, and whether the deployment remains within TVM/code/message limits. Treat unexplained regression as a blocker.
