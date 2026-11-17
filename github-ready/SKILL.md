---
name: github-ready
description: Use when reviewing a Git repository before public GitHub publication, especially for secrets in the current tree or history, accidental AI or generated files, ignore hygiene, repository structure, dead-code candidates, dependencies, licensing, or release-readiness evidence.
---

# GitHub Ready

## Overview

Fail closed on unresolved publication risks. Audit every publishable Git surface; report evidence without secret values. A match requires triage before claiming credential exposure. Cleanup grants no destructive authority.

## Audit

1. Establish the Git top level; read repository instructions, inspect `git status`, manifests, workflows, build/test configuration and layout.
2. **Read [audit policy](references/audit-policy.md) first.** Audit read-only: no edits, deletions, dependency installs, project execution, builds/tests/lint, network access or Git-ref mutation.
3. Resolve the installed `github-ready` skill directory from the location of this loaded `SKILL.md`. Never resolve the scanner from the target repository or current working directory. Honor the caller's artifact-location rules. When external temporary storage is permitted, run:

   ```text
   python -B "<absolute-github-ready-skill-root>/scripts/audit_repo.py" "<target-repo>" --gate --fail-on warning --format json --output "<external-temp>/audit.json"
   ```

   Require `schema_version: 1`, `gate_version: 1` and consistent exit/verdict: `1` threshold reached, `2` incomplete coverage, `3` scan failure. Clean up disposable reports.
   `--output` must stay outside the repository. If caller rules require project-local artifacts, capture stdout through the trusted caller into designated scratch storage outside the index.
4. Check index, working tree, untracked/ignored paths, all blobs reachable from local refs, and commit/tag/ref metadata. Disclose unfetched refs; shallow/missing history is `INCOMPLETE`.
5. Portable ignore coverage requires staged tracked `.gitignore` rules; global excludes and `.git/info/exclude` do not protect clones.
6. Indexed/historical AI state, prompts and transcripts block publication; a narrow `.github-ready-allow-ai` can retain intentional instructions only.
7. Independently verify scanner evidence, folder consistency, orphan/duplicate files, generated output, dependencies, documentation, licensing, portability, submodules, symlinks, sizes and GitHub Actions.
8. After inventory, parallelize only when justified and approved. **Read [parallel review](references/parallel-review.md) before dispatch.**
9. Apply [exact-identity triage and publication scoping](references/audit-policy.md#candidate-triage-and-repeat-findings). Separate raw verdicts from confirmed/false-positive/unresolved dispositions; reuse verified unchanged evidence. Never exempt tests by path.

## Report recipe

Produce, in order:

1. **Verdict:** `READY`, `READY WITH WARNINGS`, `NOT READY`, or `INCOMPLETE`.
2. Ranked findings: `GHnnn SEVERITY action: impact, evidence, recommendation. [path:line or commit/blob]`
3. **Unverified:** every skipped, shallow, unavailable, unreadable, timed-out, oversized, or external area.
4. **Clean:** important areas affirmatively checked.
5. **Next:** name concrete remaining actions. Reuse existing authorization for those actions; request selected IDs such as `GH003 GH006`, or `all-safe`, only when remediation authority is missing.

If shallow history or unfetched remote refs blocks coverage, **Next** offers `git fetch --all --tags --prune`; reuse existing approval or request separate consent. Do not execute it during audit.

## Fix gate

Finish the read-only audit before remediation. After selected IDs or `all-safe`, **read [remediation safety](references/remediation-safety.md)** and show the exact plan. Obtain missing approval; reuse explicit authorization already granted for that exact plan and scope without asking again. Separate credential revocation, history rewriting, commit, push, fetch, and other external or destructive actions. Apply only approved scope, re-run the full audit with the strict gate, and report closed, remaining, and new IDs.
