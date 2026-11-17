#!/usr/bin/env python
import argparse
import json
from pathlib import Path

from um_skill_lib import propose_custom_rules


def main():
    parser = argparse.ArgumentParser(description="Propose project-specific Universal Mutator custom rules.")
    parser.add_argument("repo", help="Repository root to inspect")
    parser.add_argument("--target", required=True, help="Target source file")
    parser.add_argument("--write", help="Optional rules file path to write, e.g. mutants/custom-rules/<slug>.rules")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    result = propose_custom_rules(Path(args.repo), args.target, write_path=args.write)
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(result["markdown"])
    if result.get("written_path"):
        print("")
        print(f"Wrote rules: {result['written_path']}")


if __name__ == "__main__":
    main()
