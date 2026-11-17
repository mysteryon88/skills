# TON Custom Rule Examples

## Contents

- [How To Frame Rules](#how-to-frame-rules)
- [TON Ideas](#ton-ideas)

## How To Frame Rules

Frame TON custom rules as checks for message handling, authorization, serialization, send modes, and state transitions. Keep the default TON rule stack as the baseline and use custom files only for project-specific invariants.

## TON Ideas

Sender or owner checks:

```text
sender\(\) == self.owner ==> sender() != self.owner
myAddress\(\) == sender\(\) ==> myAddress() != sender()
```

Guard direction:

```text
throwIf ==> throwUnless
throw_unless ==> throw_if
```

Opcode dispatch:

```text
op == ==> op !=
opcode == ==> opcode !=
```

Value and fee boundaries:

```text
msg.value >= minValue ==> msg.value > minValue
value <= maxValue ==> value < maxValue
```

Send and reserve mode assumptions:

```text
SendPayGasSeparately ==> SendRemainingValue
raw_reserve ==> raw_reserve_extra
```

Serialization and dictionary assumptions:

```text
load_uint ==> preload_uint
store_uint ==> store_int
dict_get\? ==> dict_get
```
