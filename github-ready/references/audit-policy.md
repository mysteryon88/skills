# Audit Policy

## Boundary and evidence

Resolve the Git top level before inspection. Read repository instructions and infer conventions from the README, manifests, workflows, build/test configuration, language norms, and dominant layout. The scanner's schema and gate versions are evidence, not a verdict; corroborate semantic findings and cite a path/line, index blob, commit, tag, ref, or object ID.

Publication surfaces are the Git index, working tree, untracked and ignored files, every object reachable from all local refs, and reachable commit/tag/ref metadata. The index is first-class evidence because staged content may differ from both `HEAD` and the working tree. Record all such differences without printing candidate values.

History coverage means every object reachable from all local refs. Unfetched remote refs are outside local coverage: disclose this, list local refs, offer `git fetch --all --tags --prune`, and never fetch without approval. Shallow history, missing objects, unreadable or oversized content, budget exhaustion, scanner errors, or incomplete filesystem inventory makes the verdict `INCOMPLETE` and the affected area `Unverified`.

The audit must not execute repository code, hooks, filters, credential helpers, lazy fetches, global Git configuration, or project tools. Any temporary files and generated reports must be outside the target repository and removed after the audit. The strict CLI must reject an output path inside the audited repository so a successful scan cannot create or overwrite publication content after inventory.

## Classification

Verdict precedence is exact: critical coverage gap -> `INCOMPLETE`; otherwise any `BLOCKER` -> `NOT READY`; otherwise any `WARNING` -> `READY WITH WARNINGS`; otherwise `READY`. Under `INCOMPLETE`, still list every known blocker and its evidence; the critical coverage gap controls the verdict.

Verdicts:

- `READY`: no blocker, warning, or critical gap.
- `READY WITH WARNINGS`: warnings but no blocker or critical gap.
- `NOT READY`: at least one blocker and no critical gap.
- `INCOMPLETE`: critical coverage was not verified.

Severities are `BLOCKER`, `WARNING`, and `INFO`. Actions are `revoke:`, `purge:`, `delete:`, `ignore:`, `move:`, `fix:`, `document:`, `review:`, and `keep:`.

Each finding contains a stable ID, impact, evidence, recommendation, and location. Deduplicate the same issue across the index, working tree, and history while preserving every relevant surface.

## Secret gate

Never print, quote, return, or write a secret candidate value. Evidence is limited to detector, type, path and line or commit/blob/ref, source surface, and masked fingerprint. This rule also applies to filenames, branch names, tag names, commit messages, errors, and generated reports.

A plausible candidate is `BLOCKER review:` until triaged. A confirmed credential is `BLOCKER revoke:`. When a confirmed credential is reachable in history, the same finding must also require `purge:` and retain only its masked fingerprint. Removing text does not revoke access, and adding `.gitignore` does not remove an indexed or historical object.

Scan at minimum provider-shaped credentials, private-key headers, credential assignments, credentials embedded in URLs, and sensitive Git metadata. Detector coverage is deliberately conservative and cannot prove that every possible secret is absent; semantic review remains mandatory.

### Explicit reviewed generic findings

The default audit retains all original secret blockers. An optional staged `.github-ready-reviewed-findings.json` can record individually reviewed false positives of `quoted-credential-assignment` only. Applying it requires the caller to supply the exact raw staged policy SHA256 with `--gate --reviewed-findings-sha256 <independently-approved-literal-sha256>` (API: `enhance_pre_push_audit(..., reviewed_findings_sha256=...)`). The caller must pin that literal digest after actual human/root review outside repository-controlled configuration. Never construct an audit command that hashes the repository policy and automatically passes that result as approval.

The UTF-8 JSON object has exactly these keys and structure:

```json
{
  "schema_version": 1,
  "findings": [
    {
      "path": "src/render.py",
      "blob_sha256": "<64 lowercase hex characters of the raw Git blob SHA256>",
      "detector": "quoted-credential-assignment",
      "fingerprint": "sha256:<12 lowercase hex characters from the finding>",
      "line": 42,
      "reason": "Reviewed use as a render-directory label."
    }
  ]
}
```

The hash/fingerprint placeholders illustrate the format and must be replaced by exact reviewed evidence. `findings` contains at most 128 entries. Each entry has exactly the six keys shown: a literal canonical repository-relative POSIX path (no empty/dot/traversal components, absolute path, backslash, glob, colon, or control characters), full lowercase blob SHA256, the one eligible detector, exact masked fingerprint, integer line from 1 through 2147483647, and a nonempty reason of at most 1024 characters without control characters. Booleans are not integers. Duplicate JSON keys, duplicate finding identities, extra keys, unsupported versions/detectors, and invalid types fail closed. Reasons are review input and are never echoed in findings or errors.

Read only regular stage-0 index policy bytes (`100644` or `100755`), including when the working file differs. Missing policy with no approval preserves existing behavior; a present malformed policy or supplied approval with missing/unreadable/nonregular/mismatched policy adds a constant-text blocker. No approval means no classification change. A supplied digest without `--gate` is rejected.

Match only concrete index/history candidates with proven regular Git mode (`100644` or `100755`), exact path, full raw blob SHA256, detector, line and fingerprint. History modes come from their actual tree entries; current index mode cannot approve a historical symlink. Unknown modes, symlinks, pathless metadata/ref findings, provider/private-key/URL/base-detector candidates, and every unmatched path/blob/line remain blocking. A matching generic candidate stays visible with `severity: INFO`, `action: keep`, `reviewed_false_positive: true`, and `reviewed_policy_sha256`; the report also records the approved policy digest under `pre_push`. Secret scanning, redaction, full local-ref scope and all budgets remain active; exhausted or missing coverage still produces `INCOMPLETE`.

The digest binds caller approval to policy bytes. It is not a signature, identity attestation, proof of independent review, or revocation mechanism. Knowingly approving a false classification is a caller decision. Any policy update requires fresh review and a newly pinned digest; modifying both target file and policy cannot reuse an earlier approval. Default audits without explicit approval remain strict.

## Checks and thresholds

### Index and ignore policy

Scan every stage-0 index blob and report unresolved non-zero index stages. Compare indexed content with the working tree. A file is portably ignored only when the version of a tracked `.gitignore` staged for publication supplies the final effective rule. Working-tree-only edits, `.git/info/exclude`, and global excludes do not count. A risky ignored file without staged portable coverage is a blocker.

Infer a minimal ignore baseline from detected ecosystems and check common environment, credential, AI-state, cache, build, coverage, IDE, OS, and temporary artifacts. Do not demand one universal `.gitignore`; report only relevant missing categories and actual risky files.

### AI files

AI tool state, sessions, transcripts, prompt dumps, local rules, and generated assistant files are blockers when indexed or reachable in history. Detect them at any repository depth. A narrow tracked `.github-ready-allow-ai` may justify intentional reviewable instruction files such as `AGENTS.md`, `CLAUDE.md`, Copilot instructions, prompts, or `agents/openai.yaml`; it must not allow tool state, histories, transcripts, or broad wildcards.

### Repository integrity

Inventory tracked, staged, untracked, ignored, generated, cache, archive, backup, dump, database, state, credential, binary, large, symlink, submodule, and nested-repository paths. Unknown untracked files and unstaged tracked changes require review because they are outside the exact commit that would be pushed. Report dangling or escaping symlinks, case-insensitive and Unicode-normalization collisions, Windows-name hazards, and excessive path length. Files at or above 100 MiB are blockers for ordinary Git; files at or above 50 MiB require review. Content exceeding the scan limit creates a critical coverage gap even when a size finding already exists.

Require each staged gitlink to have one matching staged `.gitmodules` section. Block missing paths or URLs, duplicate declarations, local or command-capable transports, and gitlinks absent from `.gitmodules`; review stale declarations, relative URLs, and submodule ownership.

Review README, license, publication rights, manifest/lock consistency, local dependency paths, package boundaries, duplicate or orphan candidates, and GitHub Actions. Warn when workflow permissions are implicit, action or container refs are mutable, checkout credentials remain available, or workflows use `pull_request_target`, `workflow_run`, inherited secrets, or direct download-to-shell patterns. `permissions: write-all` and privileged `pull_request_target` execution of pull-request head code are blockers.

Strong dead-code evidence requires an authoritative analyzer, unreachable configured entrypoint, known generated duplicate, or complete reference/configuration analysis. Text search alone with dynamic loaders cannot prove dead code; dynamic plugins, reflection, fixtures, package exports, and build configuration remain `INFO review:` unless stronger evidence exists.

Record affirmative coverage under `Clean`; never infer clean from a zero exit code alone. In strict mode, exit `1` means the selected finding threshold was reached, exit `2` means incomplete coverage, and exit `3` means execution failure.
