#!/usr/bin/env python
import argparse
import json

from um_skill_lib import detect_um_capabilities


def main():
    parser = argparse.ArgumentParser(
        description="Detect installed Universal Mutator commands, help output, key flags, and TON language support."
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    result = detect_um_capabilities()
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    print(f"Platform: {result['platform']['system']} {result['platform']['release']}")
    print(f"Python: {result['platform']['python']}")
    print("")
    print("Commands:")
    for name, info in result["commands"].items():
        print(
            f"- {name}: found={info['found']}, path={info['path'] or 'n/a'}, "
            f"version={info['version'] or 'n/a'}"
        )
    print("")
    print("Flags in mutate --help:")
    for name, supported in sorted(result["flags"].items()):
        print(f"- {name}: {supported}")
    print("")
    print("Flags in analyze_mutants --help:")
    for name, supported in sorted(result["analyze_flags"].items()):
        print(f"- {name}: {supported}")
    print("")
    print("Flags in show_mutants --help:")
    for name, supported in sorted(result["show_flags"].items()):
        print(f"- {name}: {supported}")
    print("")
    print("Flags in prioritize_mutants --help:")
    for name, supported in sorted(result["prioritize_flags"].items()):
        print(f"- {name}: {supported}")
    print("")
    print("Post-processing commands:")
    for name, supported in sorted(result["post_processing_commands"].items()):
        print(f"- {name}: {supported}")
    print("")
    print("TON language support:")
    for name, supported in sorted(result["ton_languages"].items()):
        print(f"- {name}: {supported}")
    print(f"TON language support source: {result['ton_support_source']}")
    print("")
    print("Language capabilities:")
    for name, info in sorted(result.get("language_capabilities", {}).items()):
        print(
            f"- {name}: confidence={info['confidence']}, "
            f"rules_file_found={info['rules_file_found']}, "
            f"cli_language_advertised={info['cli_language_advertised']}, "
            f"smoke_probe_passed={info['smoke_probe_passed']}"
        )
    if result["notes"]:
        print("")
        print("Notes:")
        for note in result["notes"]:
            print(f"- {note}")


if __name__ == "__main__":
    main()
