# Troubleshooting

## Contents

- [Start With A Small Reproduction](#start-with-a-small-reproduction)
- [Timeouts](#timeouts)
- [Compile Errors](#compile-errors)
- [Missing CLI Commands](#missing-cli-commands)
- [Unsupported TON Language](#unsupported-ton-language)
- [Flaky Jest Or Blueprint Tests](#flaky-jest-or-blueprint-tests)
- [Comby Missing](#comby-missing)

## Start With A Small Reproduction

Before changing many knobs at once:

1. Run the preflight commands from [command-templates.md](command-templates.md).
2. Confirm the baseline build or test command passes without mutation.
3. Run one small smoke pass against one target.
4. Only then widen scope or add rerun flags.

## Timeouts

Possible causes:

- the full suite is too broad for mutation analysis
- the timeout is lower than the real test runtime
- one mutant triggers an unusually expensive path
- the test runner is flaky or waiting on external state

What to do:

- rerun with a narrow deterministic test command
- confirm `--timeout` support with `analyze_mutants --help` before using it
- isolate timeout suspects with `--fromFile` only after local help confirms it
- keep separate logs and compare repeated runs before calling a timeout meaningful

## Compile Errors

Possible causes:

- the mutated file is not the true compile entrypoint
- the compile command does not include required includes or wrappers
- the build script differs from the one developers actually use
- the run is hitting an environment or dependency problem rather than a mutant

What to do:

- verify the baseline compile command outside mutation testing first
- use `--cmd` for Tact or FunC when the default handler is not the real project build
- for FunC, compile through the real entrypoint and include set, not only the mutated file
- if the project uses package scripts, prefer those over guessed `npx` commands

## Missing CLI Commands

If `mutate`, `analyze_mutants`, or `show_mutants` are missing:

- do not invent substitute commands and pretend they are upstream
- run the preflight checks from [command-templates.md](command-templates.md)
- use `python scripts/detect_um_capabilities.py --format markdown` to record what actually exists
- if the user only has repository source and not installed console scripts, explain that the workflow needs installation or a confirmed wrapper command

## Unsupported TON Language

Do not assume the installed public package supports TON just because the repository source does.

Verification options:

- `mutate --help` lists `tact`, `tolk`, or `func`
- installed package contains `static/tact.rules`, `static/tolk.rules`, or `static/func.rules`
- the user confirms they are on a TON-enabled fork or build

If support is still unclear, say:

“Your installed universalmutator may not support TON directly. I can still help design a mutation workflow, but these TON-specific commands require verification or a TON-enabled fork.”

## Flaky Jest Or Blueprint Tests

Warning signs:

- the same mutant survives on one run and fails on another
- logs are dominated by unrelated test failures
- Blueprint or Jest hangs without a stable failing assertion

What to do:

- use the narrowest deterministic test command that still exercises the target
- avoid parallel mutation runs until one serial run is stable
- separate infrastructure failures from mutation-caused failures in the logs
- rerun prioritized survivors instead of trusting one noisy full-suite pass

## Comby Missing

If `--comby` is desired but the environment does not have the `comby` binary:

- do not claim structural mutation is available
- treat `--comby` as a Linux or WSL workflow on Windows unless the user has already confirmed native support
- fall back to the default regex-based mutation flow and explain the limitation
- keep the command honest: “regex mutation only” is better than pretending a structural pass ran
