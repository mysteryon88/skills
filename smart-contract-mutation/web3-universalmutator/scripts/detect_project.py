#!/usr/bin/env python
import argparse
import json
from pathlib import Path

from um_skill_lib import detect_project


def main():
    parser = argparse.ArgumentParser(description="Detect Universal Mutator project layout and likely commands.")
    parser.add_argument("root", nargs="?", default=".", help="Repository root to inspect")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()

    result = detect_project(Path(args.root))
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    print(f"Project root: {result['root']}")
    print(f"Project type: {result['project_type']}")
    print(f"Package manager: {result['package_manager']}")
    print("")
    print("Detected markers:")
    for name, value in result["markers"].items():
        print(f"- {name}: {value}")
    print("")
    print("Recommended commands:")
    print(f"- compile: {result['recommended_compile_command'] or 'not detected'}")
    print(f"- test: {result['recommended_test_command'] or 'not detected'}")
    if result["ton_contracts"]:
        print("")
        print("TON contracts:")
        for contract in result["contract_mappings"]:
            print(
                f"- {contract['contract']} ({contract['language']}) | "
                f"wrapper={contract['wrapper'] or 'n/a'} | test={contract['test'] or 'n/a'}"
            )
        print("")
        print("Entrypoint contracts:")
        for contract in result.get("entrypoint_contracts", []):
            print(f"- {contract}")
        print("")
        print("Shared dependency files observed but not mutated by default:")
        for dependency in result.get("shared_dependency_files", []):
            print(f"- {dependency}")
    if result["package_scripts"]:
        print("")
        print("package.json scripts:")
        for name, command in sorted(result["package_scripts"].items()):
            print(f"- {name}: {command}")


if __name__ == "__main__":
    main()
