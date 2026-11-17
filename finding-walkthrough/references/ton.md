# TON evidence checklist

Inspect the actual message entrypoint and serialization: source/destination identities, internal message flags, value/currencies, bounce behavior and body layout. Record op/query identifiers, cell/slice fields and concrete decoded values from this project. Follow sender/owner checks, storage before/after, actions and outbound messages separately. Trace bounce handlers and failure evidence when relevant. A send action does not establish recipient execution or committed state; retrieve the receiver and its transaction evidence, otherwise record a gap. Capture actual network/revision/configuration and authorized transaction/log artifacts rather than assuming fees or execution phases from another version.

Primary orientation: [TON internal messages](https://docs.ton.org/foundations/messages/internal). Use it to identify evidence to collect; project source and actual runtime settle the finding.
