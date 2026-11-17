# Executable campaign protocol

Requirements: Python 3.11+, Git, a project with an existing commit, its real compiler/test runner, and one locally probed mutation engine. No Python package is required by the controller. Install the eight sibling skill folders together. Keep this script path absolute in commands.

## Start a small campaign

Prepare `scope.json` **inside the target project**. Inspect every command: project commands are trusted local code, not sandboxed by this controller. Never include broadcasting, deployment, push, global installers, or credentials. Example for an installed Foundry project (replace the canary with one justified by that project's specification):

```json
{
  "schema": 1,
  "coordinator": "actual-campaign-owner",
  "seed": 42,
  "exclusions": ["test/**", "lib/**: third-party dependencies"],
  "include_ignored": [],
  "runtime": {"adapter": "codex", "timeout": 600},
  "lanes": [{
    "id": "forge-counter", "language": "solidity", "tool": "forge",
    "targets": ["src/Counter.sol"],
    "rationale": "Foundry project: calibrate its installed native MVP first",
    "build": ["forge", "build", "--force"],
    "test": ["forge", "test", "--json", "--fuzz-seed", "42"],
    "pass_regex": "\"status\":\"Success\"",
    "failure_regex": "counter must increment",
    "calibration": {"path": "src/Counter.sol", "before": "number += 1", "after": "number += 2", "specification": "test/Counter.t.sol asserts increment by one"},
    "internal_workers": 1, "memory_mb": 1024,
    "timeout": 900, "idle_timeout": 900, "mutant_timeout": 60,
    "extra_args": []
  }]
}
```

Use only flags confirmed by the **installed** `forge test --help`; this release has no `--mutations` operator filter. Keep the calibration source small, or use a confirmed test filter. `pass_regex` must establish nonempty executed passing tests, and `failure_regex` must identify the intended assertion. A generic `error` pattern is inadequate. Include test contracts/shared helpers needed by the selected targets in the snapshot; `targets` selects mutations, not the files copied.

```powershell
python <mutation-campaign>/scripts/campaign.py init --project <project> --scope <project>/scope.json
python <mutation-campaign>/scripts/campaign.py bind-runtime <project>/.mutation/<id>
python <mutation-campaign>/scripts/campaign.py run <project>/.mutation/<id> --background
```

Record the returned PID and end the active agent turn. The CLI can also run synchronously for a short calibration without `runtime`. `--background` requires a successfully bound continuation runtime. Use `runtime.adapter="opencode"` for the compatible OpenCode adapter. Optional `runtime.prefix` is an inspected argv prefix for an existing CLI, not a shell command. No model is prescribed; the user's existing configured model is used.

## Scope fields and engines

Each lane has a unique lowercase ID, language (`solidity`, `tact`, `tolk`, `func`), engine, selected paths, rationale, `build`/`test` argv, pass/failure regexes, a concrete canary and resource/time estimates. `setup` is a list of project-local installation argv arrays. `needs` lists lane IDs that must finish first. `env` holds nonsecret string values; `inherit_env` maps a required child environment name to an existing environment name, for example `{"RPC_KEY":"PROJECT_RPC_KEY"}`. Never store secret literals in scope.

Tokens `{worktree}`, `{output}`, `{campaign}`, `{python}` expand in argv and nonsecret env values. Fork binding also supplies `{fork_block}` and `{fork_hash}`. No shell expansion occurs except the native engine's required test-command string; that wrapper uses quoted absolute paths. WSL engines require the **whole controller** under Linux with Linux Python/Git/tools; `wsl.exe` as an engine prefix is rejected.

| Engine | Additional fields / execution |
|---|---|
| `forge` | `executable` optional argv prefix; native `test --mutate <targets> --mutation-jobs N --mutation-timeout S --json`; help and MVP restrictions checked first. |
| `slither` | One Solidity target; `extra_args` for confirmed operators/compiler flags, e.g. `--mutators AOR`; `--test-cmd` wraps separate build and test receipts. |
| `mewt`, `muton` | Native `run <targets> --test.cmd <oracle> --test.timeout S --db <private-db> --comprehensive`; `results --all --format json`. For example `extra_args=["--mutations","AOS"]`. |
| `acton` | `contract` is the configured Acton contract name; native `test --mutate --mutate-contract NAME --mutation-workers N --mutation-timeout S --no-studio-reporting`; exactly one new session JSONL required. |
| `universal` | One target, `language_evidence` describes the installed rule/version probe; native `mutate <target> <language> --noCheck --mutantDir <private-output>`. Each generated file is separately compiled/tested. `analyze_mutants` exit-code scoring is not used. |
| `replay` | Explicit `mutants` list of `{id,path,before,after}` for diagnostic fixtures or known native patches. This is **not** evidence of native generator support. |

`calibration_targets` and `calibration_args` can restrict a short native probe; they cannot expand beyond frozen targets. Extra flags must not override output, source, test command, process count or frozen fork settings. Record tool installation/source/version/checksum receipts alongside the scope. `compiled_artifacts` lists expected project-relative bytecode/BOC files whose hashes are captured. Invariant lanes additionally require the telemetry contract in [foundry.md](foundry.md).

## State, restoration and recovery

`.mutation/<id>/` holds the frozen scope/hash, current-byte snapshot manifest and owned bare Git repository; per-lane receipts, native DB/reports, applied sources, environments, review and outbox. `.worktree/mutation-<id>/<lane>` holds each detached snapshot worktree. Both reserved roots get private `*` ignore sentinels. The source checkout/index/refs are not mutated. Ignored dependencies are omitted unless named in `include_ignored`; reinstall them locally using lockfiles or explicitly materialize required inputs. Symlinks, junctions, submodules, unmerged indexes and redirected state are rejected. Current executable modes are preserved on POSIX. Every materialized file is byte/mode checked; checkout filters cannot silently replace current content.

Stages are baseline → changed-source assertion-killed canary → native calibration → full native run → analysis → independent review. The first failure and every attempt remain on disk, including attempt-local baseline summaries and exact failed setup/build/test command logs. Completion event IDs bind lane attempt counters, unique attempt paths and failure evidence, so a recovered attempt creates a new callback while duplicate delivery of one acknowledged attempt stays idempotent. Setup, baseline, canary and native calibration use finite `timeout`; a selected full native campaign has no overall elapsed-time limit. Its engine enforces `mutant_timeout`, while `idle_timeout` stops a run only after there is no output or observed private-artifact progress. Forge JSON runs watch the lane-private temporary directory because the MVP is quiet until its final summary. Cancel explicitly with the campaign's `cancel` command. Resource slots use available CPU/RAM divided by each tool's internal worker demand; unknown RAM means one lane. Independent lanes continue after another is blocked.

Forge native mutation uses the same executable and exact flags from baseline `test` argv, including profile, compiler, filters, fuzz seed and test selection. Any `extra_args` must exactly match options already in that argv; move test/configuration flags into `test`. This prevents the native campaign from using a different test population. The controller supplies a frozen fork URL and block itself.

On Windows, the controller permits Forge help/version probes but unconditionally blocks direct side-effecting Forge commands. The installed Windows Forge 1.8.6 wrote under the user profile's `.foundry` cache despite project-local HOME variables, so setting `FOUNDRY_CACHE_PATH` alone is not confinement evidence. Use an already-installed WSL2 and run the controller inside Linux, where the campaign sets HOME and TMP under its own project directory. Direct Forge commands used by another engine's build/test oracle receive the same guard. Arbitrary wrappers bypass that direct-command check; the Windows runner does not inspect their effective cache path, so no wrapper-based Windows Forge route is supported. Linux/WSL wrappers may be selected only after the environment scout independently verifies and records their effective cache path. Do not install WSL or change global user settings.

The tested Forge MVP exposes no mutant-count or line-sampling limit. `calibration_targets` can narrow the probe to a file, but every eligible mutant in that file may run; for a large contract, record this limitation and choose a genuinely small source target before calibration rather than assuming the probe is short.

```powershell
python <skill>/scripts/campaign.py status <run>
python <skill>/scripts/campaign.py cancel <run>
python <skill>/scripts/campaign.py resume <run> --background
python <skill>/scripts/campaign.py deliver <run>
```

Cancel/recovery uses only the controller's explicit process registry with OS PID birth identities. It never scans tool artifacts for kill authority. Windows Job Objects and Linux process groups contain descendants. Repeated `resume` is an explicit new attempt; failed attempts are retained, never overwritten. Delivery has three attempts per explicit batch; `deliver` retries delivery without rerunning completed tools. State, snapshot or scope edits are rejected; changed requirements need a **new campaign**, with `parent_campaign` and reason in its scope. Development states missing current bindings must also be reinitialized.

If the original baseline fails because of a demonstrated test or configuration defect, preserve that failed run and create a successor inside the parent campaign's already ignored `successors/` directory. Only named test/configuration files may change; production contract sources and selected mutation targets are rejected. The successor freezes the parent failure, command request/receipt/stdout/stderr/exit records, each repair's before/after contents, and hash-bound specification references. Its snapshot keeps executable modes and explicitly tracks those evidence files even when inherited ignore rules match `*.log`. The source checkout remains untouched. Example:

```powershell
python <skill>/scripts/campaign.py successor <parent-campaign> --lane <lane-id> --destination <parent-campaign>/successors/<repair-name> --scope <updated-scope.json> --repair test/Counter.t.sol --specification INTENT.md --reason "Correct the fixture to match the documented one-step increment."
```

Run the returned child campaign through baseline, canary and calibration again. The failure is preserved as evidence, not converted into a passing result.

## Survivor/test/review artifacts

`triage --file <json>` requires `scope_sha256` and `groups`. Each group has original `lane:native_id` IDs, classification (`test_gap`, `unreachable`, `environment`, `equivalent`, `presumed_equivalent`, `duplicate`, `tool_error`, `contract_defect`), explanation, diff, reachability, tests, assertions, environment, specification, reproduction, confidence (`high|medium|low`), and `evidence` mapping project-local references to SHA256. Multiple IDs require `grouping_evidence`. Every survivor appears exactly once. References are campaign-relative, or `worktree/<lane>/<path>`. Unknown/unresolved causes do not grant verified completion. The detached runtime continuation stores an evidence-hash-bound proposal for every original survivor under `continuations/<event>/analysis.json`; it cannot write `triage.json`. If the capsule exceeds its byte bound, the event records `needs-bounded-analysis` instead of acknowledging a generic summary. Binary artifacts stay local and are represented only by hashes.

After justified test edits in a lane, `retest --file <request>` accepts `scope_sha256`, `lane`, `native_ids`, `tests` (exact changed test file paths), `specification`, and current `evidence` hashes. It proves the new tests pass on original, repeats the selected native campaign and maps unique patch signatures; Forge survivors also support exact applied-span replay because its MVP omits killed IDs. Results stay in `retests/`; original results are never replaced. A triage group's optional `test_improvement` references that `retest.json`; final validation checks current test hashes and each claimed kill. For a production defect, keep a reproducer and proposed contract patch separately; do not apply it to original checkout.

When a passing-output pattern contains the old test count, a retest may provide `pass_regex` plus `pass_regex_reason` describing the newly executed count. The new nonempty positive-evidence pattern is recorded in its request; the contract source, test command, assertion-failure classifier and original campaign scope/results remain fixed. This is not permission to weaken assertions.

```powershell
python <skill>/scripts/campaign.py triage <run> --file <triage.json>
python <skill>/scripts/campaign.py verify <run>
python <skill>/scripts/campaign.py finish <run>
```

Even zero survivors requires `triage` with an empty `groups` list. `verify` dispatches a fresh read-only actual runtime session; arbitrary imported verdict JSON is insufficient. `finish` binds current scope, results, triage, test/evidence bytes, supplied capsule and recorded invocation chain. A rejected/stale review, unreconciled inventory, tool error or unfinished lane blocks verified completion. See [runtimes.md](runtimes.md) for credential handling and local provenance limits.

For synchronous campaigns without `runtime`, final verification discovers the existing Codex CLI by default. Set `runtime` initially to select OpenCode, a custom inspected executable prefix, or a larger explicit evidence packet bound. Native tool execution alone does not claim independent acceptance. Fork pins are revalidated after native phases and again before first verified completion.

For a runtime without a native subagent API, `agent-job <run> --file <request.json>` launches a bounded fresh read-only CLI agent. Request fields: `capability` (`project-research`, `environment-plan`, `tool-plan`, `survivor-analysis`), `scope_sha256`, `objective`, `inputs` (evidence references), `expected_output`, `stop_conditions`. The actual session/invocation and returned report are saved in `jobs/`. Findings/proposed commands are data for the coordinator to verify; the controller never executes model-returned code. Environment writes/tool execution use inspected scope setup/lanes, and test edits use the assigned worktree plus the retest gate. Final review always uses the distinct `verify` command.
