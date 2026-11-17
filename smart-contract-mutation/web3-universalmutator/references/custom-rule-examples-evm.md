# EVM Custom Rule Examples

## Contents

- [How To Frame Rules](#how-to-frame-rules)
- [Solidity Ideas](#solidity-ideas)

## How To Frame Rules

Frame custom EVM rules as test-strength checks, not exploit instructions. Each rule should answer: which assertion should fail if this contract behavior changes?

## Solidity Ideas

Access control:

```text
owner == msg.sender ==> owner != msg.sender
msg.sender == owner ==> msg.sender != owner
hasRole\(ROLE_ADMIN, msg.sender\) ==> !hasRole(ROLE_ADMIN, msg.sender)
```

Caller and origin assumptions:

```text
tx.origin == msg.sender ==> tx.origin != msg.sender
```

Boundary checks:

```text
amount <= maxAmount ==> amount < maxAmount
amount < maxAmount ==> amount <= maxAmount
```

Zero address:

```text
recipient != address\(0\) ==> recipient == address(0)
```

Deadlines and staleness:

```text
block.timestamp <= deadline ==> block.timestamp < deadline
updatedAt + maxStaleness >= block.timestamp ==> updatedAt + maxStaleness < block.timestamp
```

Slippage and fee constants:

```text
minAmountOut ==> 0
MAX_BPS ==> 100
```

Pause guards:

```text
whenNotPaused ==> whenPaused
```

Token transfer assumptions:

```text
safeTransferFrom ==> transferFrom
safeTransfer ==> transfer
```

Unchecked arithmetic and scaling:

```text
1e18 ==> 1e6
unchecked ==>
```

Domain and chain assumptions:

```text
block.chainid ==> 1
DOMAIN_SEPARATOR ==> bytes32(0)
```
