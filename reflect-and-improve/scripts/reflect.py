"""Manual shared reflection controller. Never runs models, hooks or candidate code."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True

from cycle import Controller
from store import Refusal, locked, safe_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--target", required=True, type=Path)
    init.add_argument("--editable", required=True, action="append")
    init.add_argument("--dependency", default=[], action="append", help="sibling-name=absolute-directory")
    show = commands.add_parser("show")
    view = show.add_mutually_exclusive_group()
    view.add_argument("--report")
    view.add_argument("--experiment")
    pin = commands.add_parser("pin")
    pin.add_argument("--run-id", required=True)
    pin.add_argument("--parent-run")
    reflection = commands.add_parser("reflect")
    reflection.add_argument("--input", required=True, type=Path)
    improve = commands.add_parser("improve")
    improve.add_argument("--input", required=True, type=Path)
    for name in ("candidate", "evaluate", "select", "accept", "reject"):
        command = commands.add_parser(name)
        command.add_argument("--experiment", required=True)
        if name == "candidate":
            command.add_argument("--source", required=True, type=Path)
        if name in ("evaluate", "select"):
            command.add_argument("--candidate", required=True)
        if name == "evaluate":
            command.add_argument("--phase", required=True, choices=("development", "acceptance"))
            command.add_argument("--input", required=True, type=Path)
        if name == "accept":
            command.add_argument("--reviewed-sha", required=True, help="explicit trusted operator approval of this exact version")
        if name == "reject":
            command.add_argument("--reason", required=True)
    rollback = commands.add_parser("rollback")
    rollback.add_argument("--expected-sha", required=True)
    commands.add_parser("recover")
    args = parser.parse_args(argv)
    try:
        controller = Controller(args.state)
        # A sibling lock leaves an existing state unchanged when initialization is refused.
        root = controller.store.root
        with locked(safe_path(root.parent / (root.name + ".lock"))):
            if args.command == "init":
                result = controller.init(args.target, args.editable, args.dependency)
            elif args.command == "show":
                from store import identifier
                result = controller.show()
                if args.report:
                    result = controller.store.read(f"reports/{identifier(args.report)}.json")
                elif args.experiment:
                    result = controller.store.read(f"experiments/{identifier(args.experiment)}.json")
            elif args.command == "pin":
                result = controller.pin(args.run_id, args.parent_run)
            elif args.command == "reflect":
                result = controller.reflect(args.input)
            elif args.command == "improve":
                result = controller.improve(args.input)
            elif args.command == "candidate":
                result = controller.candidate(args.experiment, args.source)
            elif args.command == "evaluate":
                result = controller.evaluate(args.experiment, args.candidate, args.phase, args.input)
            elif args.command == "select":
                result = controller.select(args.experiment, args.candidate)
            elif args.command == "reject":
                result = controller.reject(args.experiment, args.reason)
            else:
                policy, _ = controller.load(pending=args.command == "recover")
                key = hashlib.sha256(os.path.normcase(policy["target"]).encode()).hexdigest()
                with locked(Path(tempfile.gettempdir()) / ("reflect-target-" + key + ".lock")):
                    if args.command == "accept":
                        result = controller.accept(args.experiment, args.reviewed_sha)
                    elif args.command == "rollback":
                        result = controller.rollback(args.expected_sha)
                    else:
                        result = controller.recover()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (Refusal, OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
