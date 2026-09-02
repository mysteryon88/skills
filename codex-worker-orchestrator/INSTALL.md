# Installation

The package installs the skill and a selected custom-agent profile. It preserves unrelated Codex model, MCP, approval, and sandbox settings. The live parent/session permission mode remains the ceiling.

## Choose a mode

- `lite`: installs `luna_worker` and `luna_test_runner`. The root creates a detailed execution plan, Luna/max implements it, Luna/medium runs the exact planned verification commands, and the root reviews the actual diff. Default thread limit is 2 when no user limit exists.
- `hard`: installs all 11 roles for evidence gathering, runtime diagnosis, architecture, skepticism, connected implementation, background testing, security, documentation, and mandatory Sol/xhigh review. Default thread limit is 4 when no user limit exists.

Interactive installation asks for the mode. Scripts and CI must pass `--mode lite` or `--mode hard` explicitly.

## Global installation

From a trusted package source, validate first:

```bash
python3 scripts/validate_skill.py
python3 scripts/install.py --mode hard
```

Windows PowerShell:

```powershell
py .\scripts\validate_skill.py
py .\scripts\install.py --mode hard
```

Lite example:

```bash
python3 scripts/install.py --mode lite
```

The default skill target is `~/.agents/skills/codex-worker-orchestrator`. The custom-agent target is `~/.codex/agents` or `$CODEX_HOME/agents`. `config.toml` is updated without changing unrelated settings.

## Lite workflow

The root must prepare a detailed, unambiguous plan before spawning `luna_worker`. It includes ordered steps, exact allowed files, protected interfaces, acceptance criteria, exact verification commands, dependencies, and stop conditions. After implementation, the root inspects the diff and dispatches `luna_test_runner` with those exact commands. The runner does not review code or change tracked files. Lite blocks high/extreme-complexity, high-uncertainty, high/critical-risk, and confirmed integration-debugging writes because those require Hard's independent review stages. Lite is also inappropriate when the task needs architecture, security analysis, runtime diagnosis, or independent Sol review.

## Installed role files

| Role | Path in Hard | Lite |
|---|---|---|
| `repo_explorer` | `~/.codex/agents/repo-explorer.toml` | no |
| `docs_researcher` | `~/.codex/agents/docs-researcher.toml` | no |
| `runtime_investigator` | `~/.codex/agents/runtime-investigator.toml` | no |
| `sol_architect` | `~/.codex/agents/sol-architect.toml` | no |
| `skeptic` | `~/.codex/agents/skeptic.toml` | no |
| `luna_worker` | `~/.codex/agents/luna-worker.toml` | yes |
| `terra_worker` | `~/.codex/agents/terra-worker.toml` | no |
| `luna_test_runner` | `~/.codex/agents/luna-test-runner.toml` | yes |
| `sol_reviewer` | `~/.codex/agents/sol-reviewer.toml` | no |
| `security_reviewer` | `~/.codex/agents/security-reviewer.toml` | no |
| `docs_writer` | `~/.codex/agents/docs-writer.toml` | no |

Switching profiles removes only canonical files marked `managed-by: codex-worker-orchestrator` that are not part of the selected profile. Retired managed role files are also removed. If a retired role identity is declared under an alternate, symlinked, or unmanaged file, installation blocks with an explicit move/remove instruction instead of leaving the stale identity active. Unmanaged files, alternate filenames, and an individual role symlink are never deleted automatically.

## Important options

```text
--mode {lite,hard}
--target PATH
--codex-home PATH
--agents-target PATH
--config PATH
--max-threads N
--keep-existing-agents
--replace-existing-agents
--skip-agents
--no-config-change
--no-validate
```

`--keep-existing-agents` accepts a compatible existing role by its TOML `name`, even under an alternate filename. `--replace-existing-agents` replaces only an unmanaged role at the canonical filename after backup. The installer refuses ambiguous duplicate names.

The config file and custom-agent directory symlinks are preserved when they point to valid files/directories. A symlinked skill target is rejected. An individual role symlink requires `--keep-existing-agents` and is not replaced.

An existing skill target is replaceable only when its `SKILL.md` frontmatter name is `codex-worker-orchestrator`. This prevents deletion of an unrelated directory.

## Transaction and verification

Before changing an existing installation, the installer creates one timestamped backup containing the old skill, known role files, config, mode-relevant managed roles, and a manifest. Installation is staged, validated, and rolled back on failure.

After installation run the printed doctor command. Preflight reports `install_mode`, role validity, config state, companion compatibility, and runtime unknowns. Model availability still must be confirmed in the live Codex model picker.
