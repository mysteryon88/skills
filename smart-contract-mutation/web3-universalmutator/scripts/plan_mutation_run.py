#!/usr/bin/env python
import argparse
import json
from pathlib import Path

from um_skill_lib import plan_mutation_run


def main():
    parser = argparse.ArgumentParser(description="Plan an autopilot Universal Mutator run for one source target.")
    parser.add_argument("root", nargs="?", default=".", help="Repository root to inspect")
    parser.add_argument("--target", help="Optional source path or contract name to mutate")
    parser.add_argument("--all-entrypoints", action="store_true", help="For a directory target, plan every detected entrypoint")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()

    result = plan_mutation_run(Path(args.root), target=args.target, all_entrypoints=args.all_entrypoints)
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    if "runs" in result:
        print(f"Project root: {result['root']}")
        print(f"Project type: {result['project_type']}")
        print(f"Campaign scope: {result['campaign_scope']}")
        print("")
        print("Runs:")
        for run in result["runs"]:
            print(f"- {run['target']} ({run['language']}) -> {run['mutant_dir']}")
            if run.get("analyze_command"):
                print(f"  analyze: {run['analyze_command']}")
        if result.get("notes"):
            print("")
            print("Notes:")
            for note in result["notes"]:
                print(f"- {note}")
        return

    print(f"Project root: {result['root']}")
    print(f"Project type: {result['project_type']}")
    print(f"Target: {result['target'] or 'not detected'}")
    print(f"Language: {result['language'] or 'not detected'}")
    print(f"Mutant directory: {result['mutant_dir'] or 'not detected'}")
    print(f"Report path: {result['report_path']}")
    print(f"Execution mode: {result['execution_mode']}")
    print(f"Command status: {result.get('command_status', 'unknown')}")
    scope = result.get("scope") or {}
    if scope:
        print("")
        print("Scope:")
        print(f"- requested: {scope.get('requested_scope') or 'unknown'}")
        print(f"- executed: {scope.get('execution_scope') or 'unknown'}")
        print(f"- completeness: {scope.get('completeness') or 'unknown'}")
        if scope.get("entrypoint_targets"):
            print("- entrypoints:")
            for target in scope["entrypoint_targets"]:
                print(f"  - {target}")
        if scope.get("unmutated_shared_dependency_files"):
            print("- Shared dependency files observed but not mutated by default:")
            for dependency in scope["unmutated_shared_dependency_files"]:
                print(f"  - {dependency}")
    print("")
    print("Preflight steps:")
    for step in result["preflight_steps"]:
        print(f"- {step}")
    print("")
    print("Commands:")
    print(f"- initial mutate: {result['initial_mutate_command'] or 'not available'}")
    for command in result["fallback_mutate_commands"]:
        print(f"- fallback mutate: {command}")
    print(f"- narrow test: {result['narrow_test_command'] or 'not detected'}")
    print(f"- analyze: {result['analyze_command'] or 'not detected'}")
    if result["notes"]:
        print("")
        print("Notes:")
        for note in result["notes"]:
            print(f"- {note}")


if __name__ == "__main__":
    main()
