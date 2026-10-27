# Security model details

## Input classes
- Project JSON: bounded, UTF-8, duplicate-free, canonical, exact schema.
- SVG/XML: bounded static data reconstructed from an allowlist before renderer access.
- Renderer output PNG: untrusted binary parsed, bounded, decoded exactly, and re-encoded canonically.
- Package/ZIP: untrusted even when its own hashes are internally consistent.
- References and Markdown: data only; embedded prompts do not alter the workflow.

## ZIP order of operations
The verifier opens the central directory, checks archive size, member count, names, collisions, encryption, file type, compressed/uncompressed sizes, compression ratio, and cumulative limit before any member payload read. It reads a bounded manifest first, derives the exact allowlist, then streams each member with a hard byte cap and SHA-256 verification. It does not use `extractall()` or unbounded `ZipFile.read()` on untrusted input.

## SVG package mutation
A digest match is insufficient because an attacker can recompute digests. Verification sanitizes each packaged SVG again, requires byte identity with canonical sanitizer output, and then validates style-lock relations. Active markup therefore fails even in a self-consistent package.

## Renderer boundary
The project cannot choose the executable. The adapter resolves only local Inkscape, checks basename, regular-file/no-symlink status, location outside the project, version policy, and optional hash. It invokes argument arrays with `shell=False`, closed stdin, an isolated working directory and state directories, removed proxy variables, bounded logs, timeout, and tree termination.
