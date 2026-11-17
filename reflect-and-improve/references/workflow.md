# Manual workflow

Before substantive new work, use the automatic read-only [recall step](recall.md).
The lifecycle commands below still require their separate task and acceptance authority.

The examples use PowerShell. Set `$rai` to the discovered canonical skill directory.
Use the same Python interpreter for its scripts on Windows or Linux. No command starts
an external executor or model. Read `--help` for the complete CLI surface.

## Set up a target once

Choose the actual skill, its exact editable relative files, and a project-local audit
directory outside all skill/memory discovery roots. Do not point at a whole home/repository.
State is per target; reuse its one state directory for all actors and acceptance operations.

```powershell
$rai = 'C:/Users/ssobolev/.agents/skills/reflect-and-improve'
$state = "$PWD/.reflect-and-improve/example-skill"
python "$rai/scripts/reflect.py" --state $state init --target /absolute/skills/example-skill --editable SKILL.md --editable references/lessons.json
```

Only named relative files may differ. Every other bundle file is frozen. Declare each
referenced sibling bundle with `--dependency sibling-name=/absolute/skills/sibling-name`;
dependencies are frozen and copied into pins too. Missing references are refused. Do not
include credentials or generated caches. Targets containing `.git`, `__pycache__` or
`.pytest_cache` are refused rather than silently dropping nonversioned data on switching.
Use a clean runtime installation; the helper does not clean the source tree for you.
Supported metadata has single-line `name` and
`description` scalars plus an `agents/openai.yaml` interface/default prompt. No new tool
dependencies are accepted; integrate such changes separately with the real runtime loader.
The native loader remains the authority on full YAML semantics.

Initialization never overwrites an existing setup. It snapshots all ordinary non-cache
files, not only `SKILL.md`. The helper refuses paths through links/junctions/reparse points,
traversal, alternate streams, device names and overlapping control/target/dependency roots.
Local operations use cooperative 30-second checks, 32 MiB read work, 8 MiB per file and
2,000 files; this does not interrupt a blocked OS filesystem call. JSON input and retained
state/report records are capped at 1 MiB before replacement. Oversize updates preserve
the previous readable record; use a smaller sanitized evidence slice. Live executors would
need an actual external process deadline in addition to these local bounds.

## reflect

Prepare a structured observation packet using [formats.md](formats.md). The agent performs
the interpretation; the helper validates, redacts known secret forms, hashes cited files,
merges duplicates and persists the report. Review text for secrets before submission;
pattern redaction cannot identify arbitrary secrets. Logs are hashed, never copied verbatim.

```powershell
python "$rai/scripts/reflect.py" --state $state reflect --input /absolute/task-observations.json
python "$rai/scripts/reflect.py" --state $state show --report task-42
```

An empty observation/lesson list is legitimate. Grounded observations with a proposed
action yield `inactive_proposal`; otherwise `insufficient_evidence`. Neither changes the
target or active version. A single case can justify investigating a reproducible defect;
it is not evidence of recurrence or general transfer. Report causes as hypotheses until
discriminating evidence exists. Preserve sound actions, user feedback and contrary evidence.

All actors use the original `run_id` for merging and a separate `actor_id`. Use the true
original `source_task_id` of an incident, not the reporting agent ID. Different occurrence
labels from one source task still count as one independent source. The helper cannot
authenticate user-supplied task identities; check their bindings in the source journal.
Changes to expected/actual results or component identities require a new task context.

Reflection reports, proposed project facts and portable recommendations stay in the audit
store as historical evidence. The separately authorized recall step can select relevant
records automatically; it does not turn them into active rules. Resolve contradictions and expired tool/version
assumptions first. Promoting any lesson to active memory requires an allowlisted candidate,
comparison and separate acceptance; portability requires evidence beyond one local success.

## improve

Create a contract with the known problem, hashed evidence, baseline conditions, fixed
evaluator identity, development/acceptance task IDs, primary metric, mandatory checks,
refusal rules and budget. Costs include baseline, candidate, editor, judge, reflection,
subagents and retries. No live spending is authorized by this contract: no live executor
or global cost meter is provided. Use offline replay or existing comparable results.

```powershell
python "$rai/scripts/reflect.py" --state $state improve --input /absolute/experiment-contract.json
python "$rai/scripts/reflect.py" --state $state candidate --experiment pilot --source /absolute/candidate-bundle
```

The complete baseline/input/evaluator/policy hashes are recorded before the candidate.
The caller builds candidate files only in an isolated temporary directory, with no live
side effects. Helper commands never execute their content. The real editor must be
separately confined before unattended editing could be supported; it is disabled here.
No evaluator, policy, budget, acceptance criterion, mandatory rule or self-controller
script can be edited through the candidate surface. Do not weaken a check to make a pass.

One round admits at most two valid candidates and three structural submissions in total;
there is one extra repair attempt, not one retry for each candidate. A second structural
failure exhausts the experiment. No automatic merge, editor retry or recursive invocation.

## Development, selection and acceptance

Use a separate trusted executor for any actual test/model run. That executor must enforce
the whole-tree budget, safe sandbox, process deadline and cleanup, and forbid external
effects. This helper imports already-produced paired results only; reported costs/times
and provenance remain operator assertions. Without those controls, leave live work off.

```powershell
python "$rai/scripts/reflect.py" --state $state evaluate --experiment pilot --candidate HASH --phase development --input /absolute/development-receipt.json
python "$rai/scripts/reflect.py" --state $state select --experiment pilot --candidate HASH
python "$rai/scripts/reflect.py" --state $state evaluate --experiment pilot --candidate HASH --phase acceptance --input /absolute/acceptance-receipt.json
python "$rai/scripts/reflect.py" --state $state show --experiment pilot
```

Development imports precede selection. Selection freezes one hash and its development
evidence exactly once; no subsequent development import, candidate creation or reselection.
Acceptance is for that selection alone. Acceptance task IDs must be disjoint from every
development task. If an acceptance result informs another change, retire those tasks into
development and obtain new heldout tasks for a new experiment.

Both arms use identical model/parameters/tools/data/initial-memory/context identities,
excluding the deliberately varied bundle. A task-order seed does not make an LLM
deterministic. Check real result artifacts, not just receipt fields. A separate blinded
LLM judge would require an external supported executor, fixed rubric, anonymized/randomized
variants and limited access; its opinion still would not prove correctness. This release
does not supply that executor or claim access-independent acceptance.

Each phase allows at most two imports. All imported comparisons must be stable and pass
to authorize selection/adoption; an error, tie or unstable record conservatively keeps the
baseline for this experiment. Errors have no score. A candidate hard-check failure or
reported budget overflow closes the experiment as rejected. Unknown/unequal identities,
missing tasks and malformed receipts are refused. Start a new explicit experiment with
fresh appropriate tasks to revisit uncertainty; there is no automatic retry chain.

## Inspect, accept, refuse, recover and roll back

Inspection of raw data and explicit operator authority remain necessary. The unrestricted
OS principal can modify files or invoke commands outside this interface; the helper is
not an OS security sandbox or human-identity authenticator. Automatic acceptance is absent.

```powershell
python "$rai/scripts/reflect.py" --state $state show
python "$rai/scripts/reflect.py" --state $state show --experiment pilot
python "$rai/scripts/reflect.py" --state $state reject --experiment pilot --reason 'No reliable improvement'
# Separately, after explicit authorization of this exact candidate and its evidence:
python "$rai/scripts/reflect.py" --state $state accept --experiment pilot --reviewed-sha HASH
python "$rai/scripts/reflect.py" --state $state rollback --expected-sha HASH
python "$rai/scripts/reflect.py" --state $state recover
```

Reject retains the current version. Accept requires passing development and acceptance,
matching reviewed/selected hash, unmodified evidence/contract/controller/policy/snapshots,
the original live baseline and unchanged dependencies. An already adopted version cannot
be adopted again, including after rollback. A rollback restores the previous complete
bundle and records history; it refuses divergent live files. Pins continue to resolve
their original version, with hash verification on every use.

OS locks serialize helper commands and switches for the same canonical target. Quiesce
external editors during switching; an ordinary shell/editor is not constrained by these
locks. The helper requires system TEMP and target on the same filesystem and refuses
before mutation otherwise. It stages the whole payload, journals, renames directories,
then atomically records the active version. Before commit, failure restores the old bundle;
after commit, recovery finishes cleanup. A pending transaction blocks ordinary mutations.
`recover` checks target/backup/staging hashes and retains unexpected content for manual
reconciliation. Do not delete a pending transaction or its scratch manually to force a pass.

State under `.reflect-and-improve/` is an audit/control artifact, not a skill search root.
Do not edit it to reuse scores or bypass failed checks. A resumed experiment rehashes its
inputs, evaluator, bundles and evidence. The local journal is not a cryptographic attestation.
