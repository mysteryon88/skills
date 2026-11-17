# Integration with the workflow

Follow the project instructions and current task first. This package does not create
AGENTS.md, hooks, agent configuration, MCP configuration, or other skill installations.

## Choosing the task

- Investigation, profile explanation, and audit: AUDIT without edits or recording experience.
- Request to optimize code: IMPLEMENT within the authorized scope, with before/after measurements.
- Continuing work: RESUME after checking the revision, data, context, and others' changes.
- Structure, naming, or decomposition without a performance contract: use refactor-codebase,
  if available, or the project's usual refactoring process.

For a mixed task, do not present structural refactoring as a speedup. Keep
a separate hypothesis and comparable baseline for each performance change.
The current task's general authorizations still apply. The skill adds no new external actions.

## Orchestrator and review

If the project requires codex-worker-orchestrator or another controller, it owns
planning, role selection, isolation, dispatch, and final acceptance. Do not create
a nested controller or duplicate model policy here. Delegate useful
independent research while following available roles and project gates.

Correctness checks may run independently, but comparable benchmarks on one
host run sequentially, without competing builds or measurement processes. The reviewer
receives raw evidence, not only the final perfkit output. If an independent reviewer is required
but unavailable, acceptance is blocked. Label optional self-review explicitly.

## Recall and experience

When project recall is required, follow reflect-and-improve: one scoped lookup
for the parent task, check current applicability, and pass selected context
to children. Do not automatically start reflect/improve, activation, or global memory writes.
If the skill is unavailable, use existing authorized reports without installing it.

The SQLite casebook is separate local experiment data, not a new instruction.
Read-only recall data can help choose hypotheses, but does not replace a fresh baseline,
guardrails, or an independent confirmation series. Do not copy private chats into it.

## Working files and processes

By default, use `<project>/.tmp/optimize-codebase/` for plan.md,
experience.sqlite3, evidence, profiles, test files, downloads, and build outputs.
Before writing, resolve physical paths and check that no symlink/junction/reparse
escapes the project. Do not use redirection to bypass this boundary.

Before using tools, set process-scoped TEMP, TMP, TMPDIR, and the cache/output paths they select
inside this directory. Do not change machine defaults. Bash examples require
equivalent variable configuration in PowerShell/other environments. Available tools
are determined by the project. A missing compiler does not authorize downloading one.

Choose the Python runtime according to the project instructions. If WSL is the
default on Windows, explicitly specify the distribution and Linux cwd, convert Windows/helper paths with
that distribution's `wslpath`, and run `python3` instead of passing a Windows/UNC path to Linux.
Before the first invocation, check `sys.executable`, `sys.platform`, and `os.getcwd()`.
Use Windows Python only for checks requiring the Windows API or by explicit
request. Always specify the interpreter. `.py` file associations, a silent
fallback, and installing a runtime do not replace an unavailable environment.

Record the PID/identity of long-running tests and stop their process trees
after completion/failure. Do not stop other people's processes or requested running services.
Create new worktrees only inside `<repo>/.worktree/` when required by the project.
Do not automatically delete existing files, experience, or worktrees.

SQLite data in .tmp survives sessions only while this directory is retained. For persistent
storage, use a path explicitly provided by the user. Do not promise .tmp is durable.
Package publication, global installation, and discovery checks in a new client are
separate actions. The current optimization does not run them automatically.
