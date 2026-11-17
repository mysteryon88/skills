# Aptos evidence checklist

Collect package/module version, entry function, signer identities, type arguments and exact serialized inputs. Follow signer/address binding, resource reads/writes, capabilities, table/object accesses and abort conditions in actual source. Record concrete primitive types and conversions at each relevant predicate; establish numeric ranges and arithmetic behavior from the project's language/runtime version rather than assuming another Move platform's behavior. Separate proposed input values from observed transaction state/effects. Missing module dependencies or state need explicit verification gaps.

Primary orientation: [Aptos Move primitive types](https://aptos-labs.github.io/move-book/primitive-types.html). Use this as an evidence checklist alongside the actual deployed package and runtime.
