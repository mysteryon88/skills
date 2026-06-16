# Sources and reference map

Use these references as starting points. Always verify current versions before production use.

Last checked: 2026-06-15.

## Official Mina / o1js

- Mina o1js intro: https://docs.minaprotocol.com/zkapps/o1js
- o1Labs current o1js docs: https://docs.o1labs.org/o1js
- o1Labs zkApps intro: https://docs.o1labs.org/o1js/zkapps/intro
- How zkApps work: https://docs.minaprotocol.com/zkapps/writing-a-zkapp/introduction-to-zkapps/how-zkapps-work
- How to write a zkApp: https://docs.minaprotocol.com/zkapps/writing-a-zkapp/introduction-to-zkapps/how-to-write-a-zkapp
- Security and zkApps: https://docs.minaprotocol.com/zkapps/writing-a-zkapp/introduction-to-zkapps/secure-zkapps
- On-chain values and state: https://docs.minaprotocol.com/zkapps/writing-a-zkapp/feature-overview/on-chain-values
- Permissions: https://docs.minaprotocol.com/zkapps/writing-a-zkapp/feature-overview/permissions
- Account Updates tutorial: https://docs.minaprotocol.com/zkapps/tutorials/account-updates
- Account Updates reference: https://docs.o1labs.org/o1js/zkapps/account-updates
- Actions and Reducer: https://docs.minaprotocol.com/zkapps/writing-a-zkapp/feature-overview/actions-and-reducer
- Events: https://docs.minaprotocol.com/zkapps/writing-a-zkapp/feature-overview/events
- Fetch events and actions: https://docs.minaprotocol.com/zkapps/writing-a-zkapp/feature-overview/fetch-events-and-actions
- Custom Tokens: https://docs.minaprotocol.com/zkapps/writing-a-zkapp/feature-overview/custom-tokens
- o1js API reference entry point: https://docs.o1labs.org/o1js
- o1js API reference example, Field: https://docs.o1labs.org/o1js/api-reference/classes/Field
- o1js repo: https://github.com/o1-labs/o1js
- zkApp CLI repo: https://github.com/o1-labs/zkapp-cli

## o1js concepts

- Field: https://docs.o1labs.org/o1js/basic-types/field
- Integers: https://docs.o1labs.org/o1js/basic-types/int
- Keypairs and signatures: https://docs.o1labs.org/o1js/basic-types/keypairs-and-signatures
- Structs: https://docs.o1labs.org/o1js/basic-types/structs
- Arrays: https://docs.o1labs.org/o1js/basic-types/arrays
- Hashing: https://docs.o1labs.org/o1js/basic-types/hashing
- Merkle trees: https://docs.o1labs.org/o1js/basic-types/merkle-trees
- Witnesses: https://docs.o1labs.org/o1js/writing-constraint-systems/witnesses
- Conditional logic: https://docs.o1labs.org/o1js/writing-constraint-systems/conditional-logic
- Analyzing constraints: https://docs.o1labs.org/o1js/writing-constraint-systems/analyzing-constraint-systems
- ZkProgram proof flow: https://docs.o1labs.org/o1js/writing-constraint-systems/zk-program

## Security / audits

- o1Labs: The o1js Audit, Trust but Verify: https://www.o1labs.org/blog/the-o1js-audit
- Veridise: Mastering o1js on Mina, Four key strategies for secure development: https://veridise.com/blog/learn-blockchain/mastering-o1js-on-mina-four-key-strategies-for-secure-development/
- Veridise Mina Fungible Token Standard Audit: https://minaprotocol.com/wp-content/uploads/Veridise-Mina-Fungible-Token-Standard-Audit.pdf
- Awesome Mina Security: https://github.com/ExtropyIO/awesome-mina-security

## Ecosystem

- Mina Foundation list of projects: https://github.com/MinaFoundation/list-of-projects
- Protokit: https://protokit.dev
- Zeko: https://zeko.io

## Version hygiene rules

When a source conflicts with another source:

1. Prefer current official docs over old tutorials.
2. Prefer docs.o1labs.org current version over archived version pages.
3. Prefer code in the current `o1-labs/o1js` repo over blog posts.
4. Treat SnarkyJS examples as legacy unless they were migrated to o1js.
5. In production, pin package versions and record the exact docs/API version used.
