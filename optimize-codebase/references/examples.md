# Synthetic method checks

Read the source before running these examples. They contain no network clients or user
databases. They check individual methods, not your project's performance.
Run the commands from the skill root, which may differ from the project root.
The examples below use Bash on Linux/WSL. Follow the runtime selected by the project.
on Windows with WSL as the default, explicitly choose the distribution and cwd first, as described in [integration](integration.md).

## Choose a working directory first

In Bash, set the actual project root and verify its physical path first:

```bash
project_root=/absolute/path/to/project
work="$project_root/.tmp/optimize-codebase"
mkdir -p "$work" "$work/go-cache" "$work/go-tmp" "$work/go-modcache" "$work/go-path"
export TEMP="$work" TMP="$work" TMPDIR="$work"
export GOCACHE="$work/go-cache" GOTMPDIR="$work/go-tmp"
export GOMODCACHE="$work/go-modcache" GOPATH="$work/go-path"
```

This example assumes the directory has already been verified and has no redirected ancestors.
In PowerShell, set the same process-scoped variables and explicit output paths.
Do not use /tmp or the current directory as an implicit build/profile output path.

## Go

From `examples/go`, with Go already installed:

```bash
GO111MODULE=off GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off GOTELEMETRY=off go test -v
```

If the project supports the race detector and the compiler is available, run
the same check separately with `-race`. A benchmark is a separately authorized measurement. Alternate
Bytes/Packed across adjacent AB/BA runs and do not run them in parallel.
Count reads the prepared representation. Lifecycle includes copy/pack and 20
counts using the same source input. B/op is not RSS. The bitset helpers are not
parsers for arbitrary unvalidated binary formats.

## JavaScript

`node examples/js/check.mjs` checks lookup semantics and prints 12 pairs.
Finite integer/string IDs are supported. The first object is returned for duplicates.
Map construction is included in candidate timing. This is not a React/browser or RAM test.
the result remains a CPU hypothesis until other material constraints are measured.

## SQLite

`python3 -B examples/sql/check_sqlite.py` creates synthetic SQLite databases inside
the configured temporary directory, checks 24 SELECT workloads, and measures the database-page footprint.
Connections are closed before cleanup. The index speeds up selected reads at a storage cost.
A zero storage budget rejects this option. This example does not check PostgreSQL, RAM, WAL, writes, or
production workloads.

## Rust

From the skill root, with rustc already installed:

```bash
rustc --edition=2021 --test examples/rust/flags.rs -o "$work/flags-tests"
"$work/flags-tests"
```

Choose an unused name that will not overwrite another file. Use .exe on Windows.
The real project's flags and production panic strategy require separate checks,
described in the Rust guide. The package does not install the toolchain automatically.
