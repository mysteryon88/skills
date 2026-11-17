# Sui evidence checklist

Record package/version, sender, object IDs/versions/digests, ownership and input access mode. Inspect Move entrypoints, capabilities and object authorization. Trace the concrete programmable transaction commands and argument/result references in order; distinguish a value moved between commands from a final persisted effect. Capture abort handling and effects of the complete transaction. Identify shared/owned/immutable object assumptions from the actual source and execution context. Missing object state, package code or transaction effects remain gaps, not inferred successful transfers.

Primary orientation: [Programmable transaction blocks](https://docs.sui.io/develop/transactions/ptbs/), [Sui objects](https://www.docs.sui.io/develop/objects). Verify versions and concrete object behavior in the examined project.
