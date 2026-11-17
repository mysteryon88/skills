#!/usr/bin/env python
import argparse
import json
import sys
from pathlib import Path

from um_skill_lib import collect_artifacts, detect_um_capabilities, format_multi_run_summary, format_single_run_summary


def main():
    parser = argparse.ArgumentParser(description="Summarize Universal Mutator results in a canonical report format.")
    parser.add_argument("root", nargs="?", default=".", help="Directory with mutation artifacts")
    parser.add_argument("--prefix", help="Only summarize one named run prefix")
    parser.add_argument("--target", help="Optional explicit target label")
    parser.add_argument("--project-type", default="web3", help="web3, ton, blueprint-ton, acton-ton, foundry, hardhat, truffle, vyper, fe, or another Web3 project label")
    parser.add_argument("--source-dir", help="Source directory to use in suggested show_mutants commands")
    parser.add_argument("--command", action="append", default=[], help="Command to include in the summary; repeat as needed")
    parser.add_argument("--output", help="Optional path to write the markdown report, e.g. mutants/REPORT.md")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    def emit(text):
        if args.output and args.format == "markdown":
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text.rstrip() + "\n", encoding="utf-8")
        print(text)

    report = collect_artifacts(Path(args.root))
    capabilities = detect_um_capabilities()
    if args.prefix:
        run = report["runs"].get(args.prefix)
        if run is None:
            print(f"Unknown prefix: {args.prefix}", file=sys.stderr)
            sys.exit(1)
        if args.format == "json":
            print(json.dumps(run, indent=2, sort_keys=True))
            return
        emit(
            format_single_run_summary(
                run,
                target=args.target,
                project_type=args.project_type,
                commands=args.command,
                source_dir=args.source_dir,
                capabilities=capabilities,
            )
        )
        return

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    if len(report["runs"]) == 1:
        run = next(iter(report["runs"].values()))
        emit(
            format_single_run_summary(
                run,
                target=args.target,
                project_type=args.project_type,
                commands=args.command,
                source_dir=args.source_dir,
                capabilities=capabilities,
            )
        )
        return

    emit(format_multi_run_summary(report))


if __name__ == "__main__":
    main()
