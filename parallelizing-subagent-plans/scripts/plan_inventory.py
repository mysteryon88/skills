#!/usr/bin/env python3
"""Print a JSON or Markdown inventory for a numbered implementation plan."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from plan_model import PlanFormatError, parse_plan


def render_markdown(plan) -> str:
    lines = [
        f"# Plan Inventory: {plan.title}",
        "",
        f"- Source: `{plan.source_plan}`",
        f"- Semantic SHA-256: `{plan.sha256}`",
        f"- Tasks: {len(plan.tasks)}",
        f"- Repeated file surfaces: {len(plan.overlaps)}",
        "",
        "## Tasks",
        "",
        "| Task | Lines | Files | Produces | Consumes | Depends on | Barrier | Complete |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]
    for task in plan.tasks:
        lines.append(
            f"| {task.task_id}. {task.title} | {task.line_start}-{task.line_end} | "
            f"{len(task.files)} | {len(task.produces)} | {len(task.consumes)} | "
            f"{', '.join(map(str, task.depends_on_tasks)) or '-'} | "
            f"{'yes' if task.barrier_candidate else 'no'} | {'yes' if task.completed else 'no'} |"
        )
    lines.extend(["", "## File Overlaps", ""])
    if plan.overlaps:
        for file_path, task_ids in plan.overlaps.items():
            lines.append(f"- `{file_path}`: Tasks {', '.join(map(str, task_ids))}")
    else:
        lines.append("- None detected from the plan metadata.")
    lines.extend(["", "## Warnings", ""])
    if plan.warnings:
        lines.extend(f"- {warning}" for warning in plan.warnings)
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        plan = parse_plan(args.plan)
    except (OSError, UnicodeError, PlanFormatError) as exc:
        print(f"ERROR: cannot read plan: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        rendered = json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n"
    else:
        rendered = render_markdown(plan)

    if args.output:
        output = args.output.expanduser().resolve()
        if output == args.plan.expanduser().resolve():
            print("ERROR: output must not replace the source plan", file=sys.stderr)
            return 2
        if output.exists() and not args.force:
            print("ERROR: output already exists; pass --force to replace it", file=sys.stderr)
            return 2
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
            os.replace(temp_name, output)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
