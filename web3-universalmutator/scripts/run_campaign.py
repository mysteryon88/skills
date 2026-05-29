#!/usr/bin/env python
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from um_skill_lib import (
    collect_artifacts,
    detect_project,
    detect_um_capabilities,
    format_single_run_summary,
    plan_mutation_run,
    propose_custom_rules,
    shell_join,
    validate_custom_rules_file,
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _campaign_dir(root, plan):
    return Path(root) / plan["mutant_dir"]


def _manifest_for_plan(root, plan, mode, custom_rules=None):
    commands = plan.get("commands", {})
    return {
        "schema_version": 1,
        "repo": str(Path(root).resolve()),
        "project_family": plan.get("project_family") or plan.get("project_type"),
        "project_type": plan.get("project_type"),
        "target": plan.get("target"),
        "language": plan.get("language"),
        "prefix": plan.get("prefix"),
        "mutant_dir": plan.get("mutant_dir"),
        "rules": custom_rules or [],
        "mode": mode,
        "baseline": {
            "build": commands.get("build", {}).get("argv", []),
            "test": commands.get("test", {}).get("argv", []),
        },
        "mutation": {
            "mutate_argv": commands.get("mutate", {}).get("argv", []),
            "analyze_argv": commands.get("analyze", {}).get("argv", []),
        },
        "artifacts": {
            "killed": "",
            "notkilled": "",
            "equivalent": "",
            "logs": [f"{plan.get('mutant_dir')}/run.log"],
        },
        "status": "planned",
        "mutate_attempts": [],
        "selected_mutate_argv": [],
        "custom_rule_validation": None,
        "started_at": "",
        "finished_at": "",
    }


def _write_campaign_files(root, plan, manifest, capabilities=None, artifacts=None, summary=None):
    out_dir = _campaign_dir(root, plan)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command_lines = ["#!/usr/bin/env sh", "set -eu", ""]
    for key in ("build", "test", "mutate"):
        command = plan.get("commands", {}).get(key)
        if command:
            command_lines.append(command["shell"])
    for command in plan.get("commands", {}).get("fallback_mutate", []):
        command_lines.append(command["shell"])
    command = plan.get("commands", {}).get("analyze")
    if command:
        command_lines.append(command["shell"])
    (out_dir / "commands.sh").write_text("\n".join(command_lines).rstrip() + "\n", encoding="utf-8")
    if capabilities is not None:
        (out_dir / "capabilities.json").write_text(json.dumps(capabilities, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if artifacts is not None:
        (out_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if summary is not None:
        (out_dir / "summary.md").write_text(summary.rstrip() + "\n", encoding="utf-8")
    log_path = out_dir / "run.log"
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")


def _append_log(root, plan, text):
    log_path = _campaign_dir(root, plan) / "run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")


def _run_argv(root, plan, argv, label):
    _append_log(root, plan, f"$ {shell_join(argv)}\n")
    completed = subprocess.run(
        argv,
        cwd=Path(root),
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    _append_log(root, plan, completed.stdout)
    _append_log(root, plan, completed.stderr)
    _append_log(root, plan, f"[{label}] exit={completed.returncode}\n")
    return completed.returncode


def _smoke_analyze_argv(plan, capabilities):
    argv = list(plan.get("commands", {}).get("analyze", {}).get("argv", []))
    if not argv:
        return argv, "no analyze command was planned"
    if not capabilities.get("commands", {}).get("analyze_mutants", {}).get("found", True):
        return None, "analyze_mutants was not found; run --dry-run or install Universal Mutator before analysis"
    flags = capabilities.get("analyze_flags", {})
    if not flags.get("--numMutants"):
        return None, "smoke mode cannot run safely without verified --numMutants; use --dry-run for commands or explicit --mode full for unbounded analysis"
    argv.extend(["--numMutants", "5"])
    if flags.get("--noShuffle"):
        argv.append("--noShuffle")
    if flags.get("--timeout"):
        argv.extend(["--timeout", "60"])
    return argv, None


def _append_report(root, summary):
    report_path = Path(root) / "mutants" / "REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    existing = report_path.read_text(encoding="utf-8") if report_path.exists() else "# Mutation Campaign Report\n"
    report_path.write_text(existing.rstrip() + "\n\n" + summary.rstrip() + "\n", encoding="utf-8")


def _update_report_section(root, plan, content):
    report_path = Path(root) / "mutants" / "REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    existing = report_path.read_text(encoding="utf-8") if report_path.exists() else "# Mutation Campaign Report\n"
    slug = plan["prefix"]
    start = f"<!-- campaign:{slug}:start -->"
    end = f"<!-- campaign:{slug}:end -->"
    section = f"{start}\n{content.rstrip()}\n{end}"
    if start in existing and end in existing:
        before = existing.split(start, 1)[0].rstrip()
        after = existing.split(end, 1)[1].lstrip()
        text = before + "\n\n" + section + ("\n\n" + after.rstrip() if after.strip() else "") + "\n"
    else:
        text = existing.rstrip() + "\n\n" + section + "\n"
    report_path.write_text(text, encoding="utf-8")


def _status_summary(plan, manifest, reason=None):
    lines = [
        "## Campaign `" + plan["prefix"] + "`",
        "",
        f"- Target: {plan.get('target')}",
        f"- Language: {plan.get('language')}",
        f"- Status: {manifest.get('status')}",
        f"- Mutant dir: {plan.get('mutant_dir')}",
    ]
    if reason:
        lines.append(f"- Reason: {reason}")
    if manifest.get("selected_mutate_argv"):
        lines.append(f"- Selected mutate: {shell_join(manifest['selected_mutate_argv'])}")
    if manifest.get("mutate_attempts"):
        lines.append(f"- Mutate attempts: {len(manifest['mutate_attempts'])}")
    if manifest.get("status") == "aborted":
        lines.append("- Next: inspect `commands.sh`, run `--dry-run`, or rerun with explicit `--mode full` if unbounded analysis is acceptable.")
    return "\n".join(lines)


def _planned_command_shells(plan):
    shells = []
    for key in ("build", "test", "mutate", "analyze"):
        command = plan.get("commands", {}).get(key)
        if isinstance(command, dict) and command.get("shell"):
            shells.append(command["shell"])
    for command in plan.get("commands", {}).get("fallback_mutate", []):
        if isinstance(command, dict) and command.get("shell"):
            shells.append(command["shell"])
    return shells


def _insert_custom_rules(argv, custom_rules):
    return argv[:3] + custom_rules + argv[3:]


def _run_one_campaign(root, plan, mode, dry_run, custom_rules_mode):
    custom_rules = []
    custom_rule_validation = None
    if custom_rules_mode in {"propose", "write-and-use"}:
        custom_path = Path("mutants") / "custom-rules" / f"{plan['prefix']}.rules"
        proposal = propose_custom_rules(root, plan["target"], write_path=custom_path if custom_rules_mode == "write-and-use" else None)
        if custom_rules_mode == "write-and-use" and proposal.get("written_path"):
            custom_rule_validation = validate_custom_rules_file(root, plan["target"], proposal["written_path"])
            if custom_rule_validation.get("valid") and custom_rule_validation.get("auto_usable"):
                custom_rules.append(proposal["written_path"])
                mutate = plan["commands"]["mutate"]
                argv = _insert_custom_rules(mutate["argv"], custom_rules)
                plan = dict(plan)
                plan["commands"] = dict(plan["commands"])
                plan["commands"]["mutate"] = {"argv": argv, "shell": shell_join(argv)}
                plan["commands"]["fallback_mutate"] = [
                    {"argv": _insert_custom_rules(command["argv"], custom_rules), "shell": shell_join(_insert_custom_rules(command["argv"], custom_rules))}
                    for command in plan.get("commands", {}).get("fallback_mutate", [])
                ]

    capabilities = detect_um_capabilities()
    manifest = _manifest_for_plan(root, plan, mode, custom_rules=custom_rules)
    manifest["custom_rule_validation"] = custom_rule_validation
    manifest["status"] = "dry-run" if dry_run else "running"
    manifest["started_at"] = _now()
    _write_campaign_files(root, plan, manifest, capabilities=capabilities, artifacts={"runs": {}}, summary="# Planned Mutation Campaign\n")
    _update_report_section(root, plan, _status_summary(plan, manifest))
    if dry_run:
        manifest["finished_at"] = _now()
        _write_campaign_files(root, plan, manifest, capabilities=capabilities, artifacts={"runs": {}}, summary="# Planned Mutation Campaign\n")
        _update_report_section(root, plan, _status_summary(plan, manifest))
        return {"status": "dry-run", "plan": plan, "manifest": manifest}

    build = plan.get("commands", {}).get("build", {}).get("argv")
    test = plan.get("commands", {}).get("test", {}).get("argv")
    mutate = plan.get("commands", {}).get("mutate", {}).get("argv")
    analyze = plan.get("commands", {}).get("analyze", {}).get("argv")
    if mode == "smoke":
        analyze, reason = _smoke_analyze_argv(plan, capabilities)
        if reason:
            manifest["status"] = "aborted"
            manifest["finished_at"] = _now()
            _append_log(root, plan, reason)
            _write_campaign_files(root, plan, manifest, capabilities=capabilities)
            _update_report_section(root, plan, _status_summary(plan, manifest, reason=reason))
            return {"status": "aborted", "reason": reason, "plan": plan, "manifest": manifest}

    for label, argv in (("build", build), ("test", test)):
        if not argv:
            continue
        code = _run_argv(root, plan, argv, label)
        if code != 0:
            manifest["status"] = f"failed-{label}"
            manifest["finished_at"] = _now()
            _write_campaign_files(root, plan, manifest, capabilities=capabilities)
            _update_report_section(root, plan, _status_summary(plan, manifest))
            return {"status": manifest["status"], "plan": plan, "manifest": manifest}

    mutate_attempts = []
    selected_mutate = None
    for command in [plan.get("commands", {}).get("mutate")] + list(plan.get("commands", {}).get("fallback_mutate", [])):
        if not command or not command.get("argv"):
            continue
        code = _run_argv(root, plan, command["argv"], "mutate")
        attempt = {"argv": command["argv"], "shell": command["shell"], "exit_code": code}
        mutate_attempts.append(attempt)
        manifest["mutate_attempts"] = mutate_attempts
        _write_campaign_files(root, plan, manifest, capabilities=capabilities)
        if code == 0:
            selected_mutate = command["argv"]
            break
    if mutate and selected_mutate is None:
        manifest["status"] = "failed-mutate"
        manifest["finished_at"] = _now()
        manifest["selected_mutate_argv"] = []
        _write_campaign_files(root, plan, manifest, capabilities=capabilities)
        _update_report_section(root, plan, _status_summary(plan, manifest))
        return {"status": manifest["status"], "plan": plan, "manifest": manifest}
    if selected_mutate:
        manifest["status"] = "mutants-generated"
        manifest["selected_mutate_argv"] = selected_mutate
        _write_campaign_files(root, plan, manifest, capabilities=capabilities)
        _update_report_section(root, plan, _status_summary(plan, manifest))

    if analyze:
        code = _run_argv(root, plan, analyze, "analyze")
        if code != 0:
            manifest["status"] = "failed-analyze"
            manifest["finished_at"] = _now()
            _write_campaign_files(root, plan, manifest, capabilities=capabilities)
            _update_report_section(root, plan, _status_summary(plan, manifest))
            return {"status": manifest["status"], "plan": plan, "manifest": manifest}

    artifacts = collect_artifacts(root)
    run = artifacts.get("runs", {}).get(plan["prefix"], {"prefix": plan["prefix"], "mutant_dir": plan["mutant_dir"]})
    summary = format_single_run_summary(
        run,
        target=plan["target"],
        project_type=plan["command_project_type"],
        commands=_planned_command_shells(plan),
        capabilities=capabilities,
    )
    manifest["status"] = "completed"
    manifest["finished_at"] = _now()
    _write_campaign_files(root, plan, manifest, capabilities=capabilities, artifacts=artifacts, summary=summary)
    _update_report_section(root, plan, summary)
    return {"status": "completed", "plan": plan, "manifest": manifest, "artifacts": artifacts}


def run_campaign(root, target, mode="smoke", dry_run=False, all_entrypoints=False, custom_rules="none"):
    root = Path(root).resolve()
    plan = plan_mutation_run(root, target=target, all_entrypoints=all_entrypoints)
    if "runs" in plan:
        results = [
            _run_one_campaign(root, run, mode=mode, dry_run=dry_run, custom_rules_mode=custom_rules)
            for run in plan["runs"]
        ]
        return {"status": "dry-run" if dry_run else "completed", "runs": results, "plan": plan}
    return _run_one_campaign(root, plan, mode=mode, dry_run=dry_run, custom_rules_mode=custom_rules)


def main():
    parser = argparse.ArgumentParser(description="Run or dry-run an autonomous Web3 Universal Mutator campaign.")
    parser.add_argument("repo", help="Repository root to mutate")
    parser.add_argument("--target", required=True, help="Target source file, contract name, or directory")
    parser.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all-entrypoints", action="store_true")
    parser.add_argument("--custom-rules", choices=("none", "propose", "write-and-use"), default="none")
    args = parser.parse_args()

    result = run_campaign(
        args.repo,
        target=args.target,
        mode=args.mode,
        dry_run=args.dry_run,
        all_entrypoints=args.all_entrypoints,
        custom_rules=args.custom_rules,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
