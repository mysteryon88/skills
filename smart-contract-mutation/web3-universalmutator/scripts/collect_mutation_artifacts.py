#!/usr/bin/env python
import argparse
import json
from pathlib import Path

from um_skill_lib import collect_artifacts


def main():
    parser = argparse.ArgumentParser(description="Collect Universal Mutator result files, logs, and mutant directories.")
    parser.add_argument("root", nargs="?", default=".", help="Directory with mutation artifacts")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()

    report = collect_artifacts(Path(args.root))
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    print(f"Artifact root: {report['root']}")
    print(f"Mutant directories: {', '.join(report['mutant_dirs']) if report['mutant_dirs'] else 'none found'}")
    print("")
    print("Runs:")
    if not report["runs"]:
        print("- No killed/notkilled artifacts were found.")
        return
    for prefix, run in report["runs"].items():
        print(
            f"- {prefix}: killed={run.get('killed_count', 0)}, survived={run.get('survived_count', 0)}, "
            f"mutantDir={run.get('mutant_dir') or 'n/a'}"
        )
        if run.get("stdout_log") or run.get("stderr_log"):
            print(f"  logs: stdout={run.get('stdout_log', 'n/a')}, stderr={run.get('stderr_log', 'n/a')}")
        if run.get("log_hints"):
            for hint in run["log_hints"]:
                print(f"  hint: {hint}")


if __name__ == "__main__":
    main()
