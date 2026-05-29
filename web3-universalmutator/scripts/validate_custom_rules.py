#!/usr/bin/env python
import argparse
import json
import sys
from pathlib import Path

from um_skill_lib import validate_custom_rules_file


def main():
    parser = argparse.ArgumentParser(description="Validate a project-specific Universal Mutator custom rules file.")
    parser.add_argument("repo", help="Repository root")
    parser.add_argument("--target", required=True, help="Target source file")
    parser.add_argument("--rules", required=True, help="Rules file to validate")
    parser.add_argument("--dry-run-mutants", action="store_true", help="Best-effort probe in a temporary mutant directory")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    result = validate_custom_rules_file(Path(args.repo), args.target, args.rules, dry_run_mutants=args.dry_run_mutants)
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Target: {result.get('target')}")
        print(f"Language: {result.get('language') or 'unknown'}")
        print(f"Rules: {result.get('rules')}")
        print(f"Valid: {result['valid']}")
        for error in result.get("errors", []):
            print(f"- error: {error}")
        for warning in result.get("warnings", []):
            print(f"- warning: {warning}")
        for check in result.get("rule_checks", []):
            print(f"- line {check['line']}: matches={check['match_count']} broad={check['broad']}")
        if result.get("dry_run_mutants", {}).get("attempted"):
            print(f"Dry-run mutants returncode: {result['dry_run_mutants'].get('returncode')}")
    if not result["valid"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
