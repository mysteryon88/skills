# Licensing and generated output

The TON ZK skill collection uses the MIT license and contains no copied verifier templates. `export-ton-verifier` is a separate project licensed under GPL-3.0-or-later, and its package/templates may place GPL SPDX notices in generated contracts or wrappers.

## Agent rules

- Preserve all SPDX and copyright headers emitted by the generator.
- Do not change a generated file's license marker to MIT because the surrounding skill collection uses MIT.
- Before distributing a product containing generated output, inspect the exact generated files and upstream license/version used.
- Keep generator provenance in the repository: package version, source URL, input hash, command, and output hash.
- Do not copy upstream source/templates into this skill package merely for convenience.

## Repository layout recommendation

Keep original application code and generated verifier output in clearly identified paths. A generated-file banner can state the command and input hash, but it must not overwrite upstream license notices.

## Legal boundary

This reference describes provenance and preservation practices, not a legal conclusion about a particular distribution or linking arrangement. Obtain qualified advice for a production licensing decision.
