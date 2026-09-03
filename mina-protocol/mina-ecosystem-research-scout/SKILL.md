---
name: mina-ecosystem-research-scout
description: Use when finding or evaluating current Mina and o1js resources, examples, grants, audit reports, repositories, issues, tooling, standards, or ecosystem projects.
---

# Mina Ecosystem Research Scout Skill

## Use when

Use this skill when the user asks to find or evaluate current Mina/o1js resources, examples, grants, audit reports, repositories, issues, tooling, standards or ecosystem projects.

Always use current web search for this skill unless the user explicitly says not to browse.

## Shared references

If installed from the full package, shared resources live in `../mina-protocol-agent/references/`. Load `../mina-protocol-agent/references/INDEX.md` only when task cards, examples, templates, source links or deeper checklists are needed.

## Compatibility gate

Before a version-sensitive claim, record the target network, active protocol era, exact `o1js` and signer versions, wallet/CLI versions, endpoints, and the origin of verification keys and proof caches. Load `../mina-protocol-agent/references/playbooks/NETWORK_ERA_AND_O1JS_COMPATIBILITY.md` for Berkeley/Mesa and o1js 3 migration rules. If the era is unknown, label the guidance unverified rather than guessing from package or endpoint names.

## Freshness protocol

For current API or network questions, use primary sources in this order: live network status and official Mina upgrade docs, the installed package/lockfile, the official o1js changelog and source, official Zeko docs/skills, then project examples. Report the source date, commit/tag, target era, and whether the example is reusable or application-specific. A newer project demo does not override an official protocol or library contract.

## Research priority

Prefer primary sources:

1. Official Mina docs.
2. Current o1Labs docs.
3. `o1-labs/o1js` repo.
4. `o1-labs/zkapp-cli` repo.
5. Mina Foundation repos and project lists.
6. Published audit reports.
7. Maintained project repos with recent commits.

Then use secondary sources:

- community tutorials;
- blog posts;
- course materials;
- Discord/Telegram content only if user provides it;
- AI agent wrappers and existing skill packs.

## Evaluation criteria

For every resource, assess:

```text
Official or community:
Last updated:
Targets SnarkyJS or current o1js:
Uses current API:
Has tests:
Has security notes:
Has deployment instructions:
Production/audited/demo:
Best use case:
Risk/caveat:
```

## Search queries to use

Use combinations like:

```text
site:docs.minaprotocol.com Mina o1js <topic>
site:docs.o1labs.org/o1js <topic>
site:github.com/o1-labs/o1js <topic>
site:github.com Mina o1js SmartContract <topic>
Mina o1js audit report <project>
Mina zkApp <topic> repository
```

For old examples, search both `SnarkyJS` and `o1js`, then explain whether migration is needed.

## Red flags

- old SnarkyJS examples presented as current o1js;
- no tests;
- no permission discussion;
- no state preconditions;
- no negative tests;
- private keys in frontend examples;
- deprecated APIs;
- token examples without supply invariants;
- privacy claims without leakage map;
- examples that rely on a trusted backend but market themselves as trustless.

## Output format

Return a ranked table:

```text
Rank | Resource | Type | Link | Usefulness | Current? | Risk/Caveat | Best use
```

Then give a practical recommendation:

```text
Start here:
Use this for coding:
Use this for security:
Avoid or treat as legacy:
Missing resource I would create:
```

## Special instruction for learning support

When the user is learning Mina, do not dump 30 links. Give 3 to 7 resources, in order, with one sentence on how to use each.
