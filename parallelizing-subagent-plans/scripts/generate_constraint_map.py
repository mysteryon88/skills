#!/usr/bin/env python3
"""Generate an editable constraint-map skeleton from exact source-plan bullets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from plan_model import PlanFormatError, parse_plan


def build_skeleton(source: Path, checks: list[str]) -> list[dict[str, object]]:
    plan = parse_plan(source)
    return [
        {
            "constraint": constraint,
            "kind": "",
            "tasks": [],
            "resource": "",
            "checks": checks,
        }
        for constraint in plan.global_constraints
    ]


def _write(path: Path, payload: list[dict[str, object]], force: bool) -> None:
    path = path.expanduser().resolve()
    if path.exists() and not force:
        raise ValueError(f"output already exists: {path}; pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.output.expanduser().resolve() == args.source_plan.expanduser().resolve():
        print("ERROR: output must not replace the source plan", file=sys.stderr)
        return 2
    try:
        payload = build_skeleton(args.source_plan, args.check)
        _write(args.output, payload, args.force)
    except (OSError, UnicodeError, PlanFormatError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {len(payload)} constraint records to {args.output.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
