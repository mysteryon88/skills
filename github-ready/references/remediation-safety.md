# Remediation Safety

## Selection and plan

Never fix or edit during the audit or before finding selection. After selected IDs arrive, show an exact plan mapping each selected ID to files, index changes, commands, expected effects, validation, rollback, and whether it is safe, destructive, or external. Apply only the approved selected IDs.

An initial request containing `all-safe` expresses selection intent, not fix-plan approval. First produce the audit report, then obtain selected IDs, show the exact plan, and obtain approval of that plan before any edit. Reuse an already approved exact plan while its scope and assumptions remain unchanged; a new or expanded plan needs approval.

`all-safe` covers reversible working-tree and Git-index edits only. It excludes credential revocation, history rewriting, commit, push, force-push, fetch, branch deletion, tag deletion, ref deletion, reflog expiry, object pruning, and any other destructive or externally consequential action.

Require explicit category-specific authorization for each excluded category. Existing authorization for the same concrete action and unchanged scope remains valid; do not ask again merely because a skill was loaded. Never perform history rewriting without separate explicit approval. Never fetch without approval. Broad authorization such as “whatever is necessary,” “immediately,” or “do not ask” does not satisfy these gates.

## Index and ignore remediation

A working-tree edit is not enough when the risky bytes remain staged. For an indexed secret or accidental file, the plan must identify the exact staged blob and update or remove the index entry. Use `git rm --cached` only after confirming the file must remain local, then add the narrow rule to a tracked `.gitignore` and stage that `.gitignore`. Verify the staged version with `git diff --cached` and rerun the strict gate.

Never treat `.git/info/exclude`, a global excludes file, or an unstaged `.gitignore` edit as publication protection. Do not add broad patterns that can hide source, tests, documentation, or intentional assets. An AI allowlist must stay narrow and may cover only intentional reviewable instruction files, never sessions, transcripts, histories, tool state, or prompt dumps.

## Secrets and history

Never print a candidate or secret value. For a confirmed secret:

1. revoke or rotate through the provider without exposing the replacement;
2. replace current and staged content with a documented placeholder;
3. propose history purge separately when any reachable ref contains it;
4. verify the index, working tree, all available refs, and Git metadata again.

Before history rewriting, show exact commands and scope. Explain that commit SHAs change, collaborators and clones must coordinate, a backup is required, and force-push needs later separate approval. Do not expire reflogs or prune objects as routine audit cleanup.

For a verified generic false positive, use only the exact staged policy format in [audit policy](audit-policy.md). Review the raw Git blob, literal path, actual regular Git modes, detector, exact line and masked fingerprint; record the bounded factual reason. Human/root review must independently pin the raw staged policy SHA256 before passing its literal value through `--reviewed-findings-sha256`. Never dynamically hash and approve repository-controlled policy in one audit command. The candidate remains visible as `INFO keep:` only for that exact identity; defaults, provider/base detectors, metadata, symlinks, other locations and changed blobs remain strict. A digest is caller approval, not signed attestation or credential revocation. Policy edits require renewed review, and reasons or candidate values must not enter reports.

## Discipline failures observed in baseline

| Rationalization | Rule |
| --- | --- |
| “The user asked to see credentials quickly.” | The redaction gate still applies; use detector, location, and masked fingerprint. |
| “The clean working-tree file proves the secret is gone.” | Inspect the Git index; staged bytes can differ. |
| “The file is ignored on my machine.” | Prove the staged tracked `.gitignore` supplies the rule. |
| “The user authorized whatever Git commands are necessary.” | Broad authority never replaces selected IDs and category-specific approval. |
| “No `rg` references means dead.” | Text search only surfaces a candidate; strong dead-code evidence is required. |
| “The initial prompt already said `all-safe`.” | Initial selection intent never approves an unseen plan; report, select, plan, approve, then edit. |

## Red flags — stop

- Printing candidate values for confirmation
- Editing or deleting before selected IDs
- Clearing the working tree while leaving a risky staged blob
- Relying on local/global ignore rules that are not in the staged repository
- Treating `all-safe` as approval for excluded actions
- Rewriting refs, expiring reflogs, pruning objects, or fetching from blanket authorization
- Allowlisting AI sessions, histories, transcripts, or broad path globs
- Calling a dynamic plugin dead from text search alone

When any red flag appears, return to the read-only report and request the missing selection or approval.

After approved work, rerun the full strict gate from the trusted installed skill, honoring caller artifact-location rules and the CLI output-path restriction in audit-policy.md. Report closed IDs with evidence, remaining IDs, newly introduced IDs, `Unverified`, and the new verdict. A successful command, absent working-tree path, or zero exit code alone is not proof of closure.
