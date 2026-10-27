#!/usr/bin/env python3
"""Install or remove the mandatory delegated-plan parallelization gate."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

START = "<!-- parallelizing-subagent-plans:start -->"
END = "<!-- parallelizing-subagent-plans:end -->"
BLOCK = f"""{START}
## Mandatory delegated-execution parallelization gate

After a numbered implementation plan is approved and the user selects delegated execution, invoke `parallelizing-subagent-plans` before the repository's sequential implementation workflow, before creating implementation worktrees, and before dispatching any implementation agent.

- A validated `PARALLEL` verdict is worktree-only, creates a derived execution overlay, waits for one explicit approval, then uses `orchestrating-parallel-worktree-changes-v2` as the only top-level executor for that task set.
- A validated `SEQUENTIAL` verdict states why safe parallelism is unavailable and continues immediately with the repository's sequential implementation workflow without another confirmation.
- Never run both execution controllers over the same tasks. Preserve TDD, spec-and-quality review, scoped fix/re-review loops, whole-branch review, integrated verification, and owned-resource cleanup.
{END}"""


def _marker_state(text: str) -> tuple[int, int]:
    return text.count(START), text.count(END)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def install(path: Path) -> str:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    starts, ends = _marker_state(text)
    if starts != ends or starts > 1:
        raise ValueError("Malformed parallelizing-subagent-plans marker block in AGENTS.md")
    if starts == 1:
        before, remainder = text.split(START, 1)
        _, after = remainder.split(END, 1)
        updated = before.rstrip() + "\n\n" + BLOCK + after
    else:
        updated = text.rstrip()
        if updated:
            updated += "\n\n"
        updated += BLOCK + "\n"
    _atomic_write(path, updated)
    return f"Installed mandatory gate in {path}"


def remove(path: Path) -> str:
    if not path.exists():
        return f"No AGENTS.md at {path}; nothing to remove"
    text = path.read_text(encoding="utf-8")
    starts, ends = _marker_state(text)
    if starts != ends or starts > 1:
        raise ValueError("Malformed parallelizing-subagent-plans marker block in AGENTS.md")
    if starts == 0:
        return f"Gate not present in {path}"
    before, remainder = text.split(START, 1)
    _, after = remainder.split(END, 1)
    updated = (before.rstrip() + "\n\n" + after.lstrip()).strip()
    if updated:
        updated += "\n"
    _atomic_write(path, updated)
    return f"Removed mandatory gate from {path}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "remove"))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()

    project = args.project.expanduser().resolve()
    target = project / "AGENTS.md"
    if target.exists() and target.is_symlink():
        print("ERROR: refusing to rewrite a symlinked AGENTS.md", file=sys.stderr)
        return 2
    try:
        message = install(target) if args.action == "install" else remove(target)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
