---
name: github-ready
description: Use when reviewing a Git repository before public GitHub publication, especially for secrets in the current tree or history, accidental AI or generated files, ignore hygiene, repository structure, dead-code candidates, dependencies, licensing, or release-readiness evidence.
---

# GitHub Ready

## Overview

Fail closed. Audit every publishable Git surface, report reproducible evidence, and never expose a secret value. A cleanup request does not authorize destructive Git operations.

## Audit

1. Confirm the target is a Git repository. Establish the top level, read repository instructions, inspect `git status`, manifests, workflows, build/test configuration, and documented layout.
2. **Read [audit policy](references/audit-policy.md) before auditing.** The audit is read-only: do not edit, delete, install dependencies, run project code, build, test, lint, access the network, or mutate Git refs.
3. Resolve the installed `github-ready` skill directory from the location of this loaded `SKILL.md`. Never resolve the scanner from the target repository or current working directory. Create a temporary directory outside the repository and run:

   ```text
   python -B "<absolute-github-ready-skill-root>/scripts/audit_repo.py" "<target-repo>" --gate --fail-on warning --format json --output "<external-temp>/audit.json"
   ```

   Require `schema_version: 1`, `gate_version: 1`, and a matching verdict/exit code. Exit `1` means findings reached the selected gate threshold, `2` means critical coverage is incomplete, and `3` means the scan failed. Clean up the external temporary directory after synthesis.
4. Verify the Git index, working tree, untracked and ignored paths, every blob reachable from all local refs, and commit/tag/ref metadata. State that unfetched remote refs were not checked. Shallow or missing history is `INCOMPLETE`. Offer `git fetch --all --tags --prune` separately; never fetch without approval.
5. Treat ignore coverage as portable only when the staged version of a tracked `.gitignore` supplies it. Global excludes and `.git/info/exclude` do not protect a published clone.
6. AI state, prompts, transcripts, and tool files are blockers in the index or history. Only intentional instruction files may use a narrow tracked `.github-ready-allow-ai` rule.
7. Semantically verify folder consistency, orphan/duplicate files, generated output, dependencies, public documentation, licensing, path portability, submodules, symlinks, large files, and GitHub Actions. Independently verify scanner evidence.
8. After inventory, parallelize only when justified and approved. **Read [parallel review](references/parallel-review.md) before dispatch.**

## Report recipe

Produce, in order:

1. **Verdict:** `READY`, `READY WITH WARNINGS`, `NOT READY`, or `INCOMPLETE`.
2. Ranked findings: `GHnnn SEVERITY action: impact, evidence, recommendation. [path:line or commit/blob]`
3. **Unverified:** every skipped, shallow, unavailable, unreadable, timed-out, oversized, or external area.
4. **Clean:** important areas affirmatively checked.
5. **Next:** request selected IDs such as `GH003 GH006`, or `all-safe`.

If shallow history or unfetched remote refs blocks coverage, **Next** must separately offer `git fetch --all --tags --prune` with separate consent; do not execute it during the audit.

Never print a candidate value. Show only type, detector, location, and masked fingerprint. Missing critical verification cannot produce a successful verdict.

## Fix gate

Finish the read-only audit before remediation. After selected IDs or `all-safe`, **read [remediation safety](references/remediation-safety.md)** and show the exact plan. Obtain missing approval; reuse explicit authorization already granted for that exact plan and scope without asking again. Separate credential revocation, history rewriting, commit, push, fetch, and other external or destructive actions. Apply only approved scope, re-run the full audit with the strict gate, and report closed, remaining, and new IDs.
