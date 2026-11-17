# Harness² source practices and local additions

Inspected source commit: `1cfe254e8d25b15f37048c3730134686abe60335`,
[fixed source tree](https://github.com/google-research/harness2/tree/1cfe254e8d25b15f37048c3730134686abe60335).
The nine requested source files were read at that commit; the additional source is
[paper v1](https://arxiv.org/html/2610.14224v1), especially §2, E.6 and F. No upstream code
was copied and no Harness² package/runner was installed. These are adapted ideas.

| Verified practice | Local reuse |
| --- | --- |
| `prompts.propose` relates edits to observed trajectory moments and allows keeping the base | Ground proposals in observations; permit no-change outcomes |
| `tree.is_allowed` and `tree.validate` constrain paths, metadata and bundled references; `_accept_tree` adds adapter checks | Exact editable-file scope, complete dependency snapshots and structural validation |
| `context.build` supplies task, runs, diffs and outputs; selection gets anonymized deliverables, reflection richer contrasts | Explicit task/evidence/version packets and paired conditions; no presumed parent context |
| `prompts.experience`/`Library.add` permit no entry and retain cue/action/evidence with helped/hurt/no-effect/confounded outcomes | Inactive scoped lessons, no forced universal rule from one success |
| Recursion has finite `4k` rollouts/`3k` improvement stages and bounded proposal repairs; workflow tests cover resume and NO_ENTRY | One round, two candidates, one structural repair; stale-evidence and no-lesson tests |

Primary implementation links:
[prompts.py](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/prompts.py),
[tree.py](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/tree.py),
[context.py](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/context.py),
[library.py](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/library.py),
[recursion.py](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/recursion.py),
[selection.py](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/selection.py),
[judge.py](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/judge.py),
[EXPERIMENTS.md](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/docs/EXPERIMENTS.md),
[test_workflow.py](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/tests/test_workflow.py).

Upstream `selection_pool` excludes baseline runs from its final pool. `judge.py` is
post-selection evaluation; an error records no score. The paper reports selection failures
and warns that behavioral contrasts/model judgment do not verify correctness or transfer.
The experiment guide does not impose network restriction and describes Codex with its
sandbox disabled. None of those settings is imported here.

Our additions are separate operator acceptance, retaining the baseline on uncertainty,
frozen development selection before disjoint acceptance, scoped inactive-memory proposals,
whole-bundle hashes/pins, stale-input refusal, transaction recovery/rollback and explicit
limits on live execution. They are requirements of this integration, not upstream deployment
guarantees. Content hashes/receipts do not create OS access separation or authenticate a
judge. This installation has no such independent heldout boundary or shared live-spend
meter; live runs and automatic acceptance are disabled. Local fixtures establish lifecycle
mechanics, not a measured agent-quality improvement.

## Scenario laboratory evidence seam

The lab already has immutable Runs, typed journals, independent role sessions, bounded
Goal cycles and known-route receipts. Its explicit typed reflection-packet export is
a local adapter to Propose/Probe/Compose-style evidence preparation, not another upstream
executor or an autonomous learning loop. Proposed trajectory lessons remain inactive;
structural contrasts and safe packaging tests cannot establish agent-quality transfer.
Original-task aliases bind shared source cases without inflating support from multiple
actors or Runs. Unknown context, unverified historical journal authenticity, unsuccessful
cleanup or missing actions preserve uncertainty and the baseline. No sandbox-disabled
upstream defaults, raw trajectories, recursive reflection or automatic adoption are imported.
