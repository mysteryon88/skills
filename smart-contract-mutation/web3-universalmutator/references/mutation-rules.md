# Mutation Rule Summary

## Contents

- [Core Loading Model](#core-loading-model)
- [Shared Rule Layers](#shared-rule-layers)
- [TON Rule Model](#ton-rule-model)
- [Other Language-Specific Rule Summaries](#other-language-specific-rule-summaries)
- [Custom Rule Ideation](#custom-rule-ideation)
- [How To Use This In Practice](#how-to-use-this-in-practice)

Use this file when the task is about what mutation families exist for supported Web3 languages, which rule files are loaded for a language, or how to explain a surviving mutant in terms of the active ruleset.

Supported languages for this skill are:

- TON: `tact`, `tolk`, `func`
- EVM: `solidity`, `vyper`, `fe`

Other Universal Mutator language rows are context only. Do not use this skill to plan non-Web3 mutation runs.

## Core Loading Model

The current tool code loads rule files by language, then swaps to the `comby/` directory when `--comby` is enabled.

Default stacks verified from local `genmutants.py`:

| Language or family | Default stack | Notes |
|---|---|---|
| `tact` | `ton_common.rules` + `tact.rules` | TON default, not `universal.rules` |
| `func` | `ton_common.rules` + `func.rules` | TON default, not `universal.rules` |
| `tolk` | `ton_common.rules` + `tolk.rules` | TON default, not `universal.rules` |
| `c`, `cpp`, `java`, `javascript`, `swift`, `rust`, `go`, `solidity` | `universal.rules` + `<language>.rules` + `c_like.rules` | c-like surface gets the extra `c_like` layer |
| `python`, `lisp`, `fortran`, `r`, `none` | `universal.rules` + `<language>.rules` | `r.rules` and `none.rules` are currently empty |
| `vyper`, `fe` | `universal.rules` + `<language>.rules` + `python.rules` + `solidity.rules` | the dedicated `vyper.rules` and `fe.rules` files are currently empty, so behavior comes from shared layers |

For TON file extensions `.tact`, `.fc`, `.func`, and `.tolk`, the Comby path uses the generic matcher while still loading the same rule-file names.

## Shared Rule Layers

### `universal.rules`

This is the broad non-TON baseline. It currently contributes:

- arithmetic operator swaps among `+`, `-`, `*`, `/`, `%`
- comparison rewrites among `==`, `!=`, `<`, `>`, `<=`, `>=`
- compound assignment rewrites like `+= -> =+`
- increment and decrement flips
- numeric literal rewrites to `0`, `1`, `-1`, `n+1`, `n-1`
- boolean logic rewrites `&& <-> ||` and removal of unary `!`
- bitwise `& <-> |`
- control-flow injections that append `break;` or `continue;`
- string emptying
- `while -> if`
- argument or element order swaps
- `min <-> max` and `begin <-> end`

This is why even languages with empty dedicated rule files such as `c.rules`, `r.rules`, `none.rules`, `vyper.rules`, and `fe.rules` can still produce many mutants.

### `c_like.rules`

This layer adds C-like control-flow shaping:

- `#include` exclusion
- line comment-out replacement
- `if` and `while` forcing
- `else` removal
- boolean short-circuit forcing around `||` and `&&`
- line-tail `//` skip-rest behavior

It is automatically added for `c`, `cpp`, `java`, `javascript`, `swift`, `rust`, `solidity`, and `go`.

### `python.rules`

This layer adds Python-shaped families such as:

- import exclusion
- `if` and `while` negation
- `break <-> continue`
- `and/or/not` rewrites
- `return ... -> return None`
- `pass` replacement
- integer division swap `/ <-> //`
- list and dict emptying or truncation
- element reordering
- decorator removal

It is loaded directly for Python and indirectly for Vyper and Fe.

### `solidity.rules`

This layer adds Ethereum-specific and Solidity surface mutations:

- `true <-> false`
- `int <-> uint`, `fixed <-> ufixed`, width downgrades
- `memory <-> storage`
- `view <-> pure`, `constant -> pure`, `payable` removal, `private` removal
- `msg.sender <-> tx.origin`
- unit and time rewrites like `ether`, `wei`, `minutes`, `days`, `years`
- `now` and `block.timestamp` zeroing
- `msg.value -> 0/1`
- `addmod <-> mulmod`
- statement replacement with `selfdestruct(msg.sender);` or `revert();`
- `call`, `delegatecall`, `callcode` swaps
- name removal in declaration-like contexts
- `if` forcing to `false` or `true`

It is loaded directly for Solidity and indirectly for Vyper and Fe.

## TON Rule Model

TON repositories are special because they do not use the broad `universal.rules + c_like.rules` default stack. They start from `ton_common.rules`, then add a language-specific layer.

### `ton_common.rules`

Current parsed rule lines:

- regex: `36`
- comby: `36`

Shared families:

- `true <-> false`
- safe `==`, `!=`, `<=`, `>=` rewrites
- guarded `&& <-> ||` with Tolk narrowing protection
- `while (cond) -> while (false)`
- `break <-> continue`
- arithmetic compound assignment shuffle
- bitwise compound assignment shuffle
- `<<= <-> >>=`, `<< <-> >>`

This is the common base for Tact, Tolk, and FunC, so many simple boolean, comparison, and control-flow survivors are shared across all three languages.

### `tact.rules`

Current parsed rule lines:

- regex total: `175`
- regex mutation lines: `170`
- comby total: `161`
- comby mutation lines: `157`

Main families:

- import, comment, and doc-line exclusions
- standalone statement comment-out mutation
- `if` forcing
- `throwIf <-> throwUnless`
- `require` weakening, removal, and throw-code zeroing
- ordered comparisons, arithmetic, and bitwise rewrites
- `until`, `repeat`, ternary forcing
- math helper families such as `abs/sign`, `min/max`, `mulShiftRight*`, `log`, `pow`
- bounce and send-mode mutations
- reserve-mode and `nativeReserve` mutations
- attached value and time/context helper rewrites
- randomness and seed API rewrites
- width and signedness casts
- ACL/auth patterns involving `sender`, `myAddress`, and `self.field`
- `acceptMessage` removal
- function-kind, receiver-kind, message opcode, empty-cell/body, and map update mutations

Interpretation tip:

- Tact survivors often point to missing access-control tests, send-mode assertions, attached-value checks, and context-sensitive logic around time, balance, or inbound message handling.

### `tolk.rules`

Current parsed rule lines:

- regex total: `175`
- regex mutation lines: `172`
- comby total: `248`
- comby mutation lines: `246`

Main families:

- import or comment guards and block-comment skipping
- standalone statement comment-out and assert or throw removal
- `if` forcing with explicit `is / !is` protection
- unary `!`, `~`, `-` removal in selected expression contexts
- `lazy`, `get fun`, function attributes, and `mutate` parameter stripping
- default parameter and default struct-field removal
- `uintN <-> intN`, `varuint <-> varint`, and `as uintN <-> as intN`
- `throwIfOpcodeDoesNotMatch`, `assertEndAfterReading`, and non-null assertion relaxation
- blockchain time, size, fee, and random helper swaps
- load, preload, store, slice, and message parsing helper swaps
- large families for dictionary signedness and navigation
- string checksum and hash helper swaps
- send or reserve named constants, raw numeric modes, `createMessage({ value: ... })`, `BounceMode.*`, and `struct (prefix)` mutations

Interpretation tip:

- Tolk survivors often reveal weak serialization, message parsing, dictionary navigation, send-mode, and opcode-prefix assertions.

### `func.rules`

Current parsed rule lines:

- regex total: `141`
- regex mutation lines: `139`
- comby total: `161`
- comby mutation lines: `161`

Main families:

- `#include` exclusion and `;;` skip-rest handling
- standalone statement comment-out
- `throw_if <-> throw_unless`, `throw_arg_if <-> throw_arg_unless`, and uppercase helper swaps
- `if`, `ifnot`, `until`, `repeat`
- XOR, AND, OR shuffles
- `/`, `~/`, `^/` and `%`, `~%`, `^%` operator or assignment families
- function specifier rewrites like `inline`, `inline_ref`, `impure`
- gas or state helpers `accept_message`, `commit`, `set_code`
- time and randomness helpers `now`, `cur_lt`, `block_lt`, `random`, `get_seed`
- preload versus load families, store signedness swaps, store zeroing, and mutating versus non-mutating notation
- slice and builder inspection helpers
- dictionary signedness swaps
- numeric builtins like `divmod`, `moddiv`, `muldiv`, `muldivr`, `muldivc`, `muldivmod`
- `send_raw_message`, `raw_reserve`, and `raw_reserve_extra` numeric mode mutations

Interpretation tip:

- FunC survivors often point to missing tests for rounding mode, preload versus consuming read behavior, send or reserve mode semantics, and low-level serialization assumptions.

## Additional Rule Context

Current parsed stacks in this repository. Solidity, Vyper, and Fe are supported EVM targets. The other rows are included only to explain inherited rule layers and should not be used as run targets for this Web3 skill:

| Language | Default regex stack | Parsed rule lines | Practical summary |
|---|---|---:|---|
| `c` | `universal + c_like` | `93` | no dedicated `c.rules`; mutations come entirely from the shared non-TON layers |
| `cpp` | `universal + cpp + c_like` | `107` | adds STL or algorithm families like `any_of/all_of/none_of`, `at(0)`, inserter direction, `min_element/max_element`, `accumulate/inner_product` |
| `java` | `universal + java + c_like` | `103` | adds import, annotation, and comment exclusions plus `synchronized` removal |
| `javascript` | `universal + javascript + c_like` | `98` | adds `=== <-> !==` and short-circuit shaping |
| `go` | `universal + go + c_like` | `98` | adds `defer` removal plus short-circuit shaping |
| `swift` | `universal + swift + c_like` | `104` | adds `var <-> let`, boolean literal flips, array truncation or emptying, and comma-order rewrites |
| `rust` | `universal + rust + c_like` | `95` | the dedicated layer only adds `true <-> false`; most behavior comes from shared layers |
| `python` | `universal + python` | `102` | adds branch negation, `break/continue`, list or dict truncation, decorator removal, `return None`, `pass`, and `/ <-> //` |
| `lisp` | `universal + lisp` | `81` | adds `and/or/not` and `T/nil` rewrites |
| `fortran` | `universal + fortran` | `165` | adds exponentiation rewrites plus large families for `.lt./.le./.gt./.ge./.eq./.ne.` and `.and./.or./.eqv./.neqv.` in upper and lower case |
| `solidity` | `universal + solidity + c_like` | `143` | adds Solidity and EVM semantics around signedness, storage location, sender or origin, units, timestamps, value, addmod or mulmod, revert or selfdestruct, and call variants |
| `vyper` | `universal + python + solidity` | `152` | no dedicated `vyper.rules`; relies on Python-style and Solidity-style layers |
| `fe` | `universal + python + solidity` | `152` | no dedicated `fe.rules`; relies on Python-style and Solidity-style layers |
| `r` | `universal + r` | `74` | `r.rules` is currently empty, so the universal layer dominates |

## Custom Rule Ideation

Custom rules are optional. Offer them after selecting a target and reviewing the default rule stack. If the user explicitly requested autonomous custom-rule generation, write custom rule files under `mutants/custom-rules/` and report what was written; otherwise ask before writing. Default language rules remain the baseline; custom files should add source-specific pressure, not replace the normal campaign unless the user explicitly wants that.

Derive candidates from the source and nearby shared dependencies. Look for security invariants, access control, message/opcode parsing, storage transitions, fees/value flow, send/reserve modes, rounding, time/randomness, serialization, and dictionary/key behavior. A useful candidate usually answers: "If this behavior changed, which test should fail?"

Use these quality criteria before writing a rule:

- small, compilable, targeted, non-duplicative with default rule families
- likely to expose a missing assertion, not merely produce many compile errors
- narrow enough to explain in the final report as a domain-specific hypothesis
- written in the same rule-file style as the installed `universalmutator/static/` or `universalmutator/comby/` rules

Suggested workflow:

1. Inspect the selected source file plus relevant shared files such as messages, storage, errors, constants, libraries, and wrappers.
2. List two to five custom mutation ideas and map each idea to the invariant or missing test it probes.
3. Ask the user whether to generate the custom rules file unless the user explicitly requested autonomous custom-rule generation.
4. If accepted or autonomous mode was requested, write it under a clear project-local path such as `mutants/custom-rules/<target-slug>.rules`.
5. Run default-plus-custom mutation by passing the custom file as an extra positional rules file after the language argument, then use `--showRules` when available to confirm which default or custom rules fired.

Use `--only <custom.rules>` only when the user wants to replace the default stack with the custom file for a focused experiment, and only after local help confirms `--only`.

For syntax and examples, read [custom-rule-syntax.md](custom-rule-syntax.md), [custom-rule-examples-evm.md](custom-rule-examples-evm.md), or [custom-rule-examples-ton.md](custom-rule-examples-ton.md).

## How To Use This In Practice

When the user asks what mutants exist:

1. State the active rule stack for the target language.
2. Name the most important mutation families from that stack.
3. Offer optional custom rule ideation when the source has project-specific invariants that default rules may not probe well.
4. If the user needs a more exact inventory than this summary, use `mutate --showRules` or `--printStat` when those flags are available in the installed environment.
5. Tie surviving mutants back to the relevant family instead of listing filenames only.

When the user asks why a TON survivor matters:

- decide whether it came from `ton_common.rules` or the language-specific layer
- map it to a family such as send mode, opcode, storage or serialization, dictionary navigation, ACL, or randomness
- recommend tests that directly observe that family
