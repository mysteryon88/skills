#!/usr/bin/env python3
"""Deterministic structural validation for codex-worker-orchestrator."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from orchestrator_lib import (
    InstallProfile, RoleSpec, included_files, load_install_profiles, load_role_registry,
    package_tree_files,
)

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
VERSION_FILE = ROOT / "VERSION"
ROLE_DIR = ROOT / "assets" / "agent-configs"
MANAGED_MARKER = "# managed-by: codex-worker-orchestrator"
VERSION_PATTERN = re.compile(r"^[0-9]$")
FRONTMATTER_KEYS = {"name", "description"}
FORBIDDEN_ROLE_NAMES = {
    "orchestrator",
    "task_manager",
    "synthesizer",
    "adjudicator",
    "state_manager",
    "lock_manager",
    "test_runner",
    "root",
}
ROLE_SAFETY_POLICY = """<ROLE-SAFETY-POLICY>
Do not invoke codex-worker-orchestrator. Do not spawn agents. Do not delegate to agents, helpers, or reviewers.
The parent workflow owns task sequencing, approval gates, workflow state, write isolation, fix and review loops, and the output contract.
The root agent is the workflow owner.
Do not orchestrate, adjudicate findings, manage state or write isolation, or create a competing process.
Separate evidence from inference.
Return NEEDS_CONTEXT or BLOCKED instead of inventing facts, requirements, access, results, or conclusions.
</ROLE-SAFETY-POLICY>"""
READ_ONLY_OUTPUT_POLICY = """<ROLE-OUTPUT-POLICY>
Do not edit files. Do not write a report file.
If the brief supplies an output or report contract, obey it exactly.
Return the full structured report in your final response; do not write a report file.
</ROLE-OUTPUT-POLICY>"""
WRITE_OUTPUT_POLICY = """<ROLE-OUTPUT-POLICY>
Write only within the assigned packet and its declared write surface.
If the brief supplies an output or report contract, obey it exactly.
</ROLE-OUTPUT-POLICY>"""
DIAGNOSTIC_OUTPUT_POLICY = """<ROLE-OUTPUT-POLICY>
Write only assigned diagnostic artifacts on the declared write surface.
Do not implement fixes or change production behavior.
If the brief supplies an output or report contract, obey it exactly.
</ROLE-OUTPUT-POLICY>"""
TEST_ONLY_OUTPUT_POLICY = """<ROLE-OUTPUT-POLICY>
Do not edit tracked files. Write only explicitly assigned untracked test logs or diagnostic artifacts on the declared write surface.
Do not change production code, tests, configuration, dependencies, snapshots, or generated source.
If the brief supplies an output or report contract, obey it exactly.
</ROLE-OUTPUT-POLICY>"""
DOCUMENTATION_OUTPUT_POLICY = """<ROLE-OUTPUT-POLICY>
Write only documentation on the declared write surface.
Do not change source code.
If the brief supplies an output or report contract, obey it exactly.
</ROLE-OUTPUT-POLICY>"""
RELAX_POLICY_PATTERN = re.compile(
    r"\b(?:ignore|override|disregard)\b.{0,80}\b(?:polic(?:y|ies)|instructions?)\b",
    re.IGNORECASE,
)
ROLE_PERMISSION_PATTERN = (
    r"(?:spawn(?:\s+agents?)?|delegate(?:\s+to)?|invoke|edit(?:\s+files?)?|"
    r"write(?:\s+(?:files?|reports?))?|orchestrat(?:e|ion)|state|locks?)"
)
RELAX_PERMISSION_PATTERN = re.compile(
    rf"(?:\b(?:except|unless|when necessary|if necessary)\b.{{0,80}}\b{ROLE_PERMISSION_PATTERN}\b|"
    rf"\b{ROLE_PERMISSION_PATTERN}\b.{{0,80}}\b(?:except|unless|when necessary|if necessary)\b)",
    re.IGNORECASE,
)
POSITIVE_PERMISSION_PREFIX = (
    r"\b(?:you|agents?|helpers?|reviewers?|(?:(?:the|this)\s+)?(?:roles?|workers?))\s+(?:may|can|"
    r"(?:are|is)\s+(?:allowed|permitted)\s+to)\s+"
)
POSITIVE_GLOBAL_PERMISSION_PATTERN = re.compile(
    POSITIVE_PERMISSION_PREFIX
    + r"(?:spawn(?:\s+agents?)?|delegate(?:\s+to)?|invoke|orchestrate|"
    r"adjudicate|manage\s+(?:state|locks?))\b",
    re.IGNORECASE,
)
POSITIVE_READ_ONLY_PERMISSION_PATTERN = re.compile(
    POSITIVE_PERMISSION_PREFIX
    + r"(?:edit(?:\s+files?)?|write(?:\s+(?:a\s+)?(?:report\s+)?files?)?)\b",
    re.IGNORECASE,
)

REQUIRED_FILES = (
    VERSION_FILE,
    SKILL,
    ROOT / "INSTALL.md",
    ROOT / "agents" / "openai.yaml",
    ROOT / "config" / "roles.toml",
    ROOT / "config" / "install-profiles.toml",
    ROOT / "references" / "routing-matrix.md",
    ROOT / "references" / "dispatch-contract.md",
    ROOT / "scripts" / "install.py",
    ROOT / "scripts" / "preflight.py",
)

REQUIRED_SUPERPOWERS = {
    "superpowers:using-superpowers",
    "superpowers:brainstorming",
    "superpowers:systematic-debugging",
    "superpowers:writing-plans",
    "superpowers:subagent-driven-development",
    "superpowers:executing-plans",
    "superpowers:dispatching-parallel-agents",
    "superpowers:test-driven-development",
    "superpowers:requesting-code-review",
    "superpowers:using-git-worktrees",
    "superpowers:verification-before-completion",
    "superpowers:finishing-a-development-branch",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def reject_package_symlinks(root: Path) -> None:
    try:
        package_tree_files(root)
    except ValueError as exc:
        fail(str(exc))


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not match:
        fail("SKILL.md has no valid YAML frontmatter block")
    fields: dict[str, str] = {}
    for line_number, raw_line in enumerate(match.group(1).splitlines(), start=2):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[:1].isspace():
            fail(
                f"Unsupported nested frontmatter at SKILL.md:{line_number}: "
                f"{raw_line!r}"
            )
        if ":" not in raw_line:
            fail(f"Malformed frontmatter line at SKILL.md:{line_number}: {raw_line!r}")
        key, value = raw_line.split(":", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            fail(f"Invalid frontmatter key at SKILL.md:{line_number}: {key!r}")
        if key in fields:
            fail(f"Duplicate frontmatter key `{key}` at SKILL.md:{line_number}")
        if key not in FRONTMATTER_KEYS:
            fail(f"Unsupported frontmatter key `{key}` at SKILL.md:{line_number}")
        value = value.strip()
        if not value:
            fail(f"Frontmatter value `{key}` is empty at SKILL.md:{line_number}")
        if value[0] in "\"'":
            try:
                parsed = ast.literal_eval(value)
            except (SyntaxError, ValueError) as exc:
                fail(
                    f"Invalid quoted frontmatter value `{key}` at "
                    f"SKILL.md:{line_number}: {exc}"
                )
            if not isinstance(parsed, str):
                fail(f"Frontmatter value `{key}` must be a string")
            value = parsed
        fields[key] = value
    missing = sorted(FRONTMATTER_KEYS - set(fields))
    if missing:
        fail(f"Missing frontmatter field(s): {', '.join(missing)}")
    return fields


def load_package_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not VERSION_PATTERN.fullmatch(version):
        fail(f"VERSION must contain one digit, found {version!r}")
    return version


def parse_metadata_scalar(value: str, line_number: int) -> object:
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        items: list[str] = []
        for raw_item in inner.split(","):
            item = raw_item.strip()
            if not item:
                fail(f"agents/openai.yaml:{line_number}: empty list item")
            if item[:1] in "\"'":
                try:
                    parsed = ast.literal_eval(item)
                except (SyntaxError, ValueError) as exc:
                    fail(f"agents/openai.yaml:{line_number}: invalid list item: {exc}")
                if not isinstance(parsed, str):
                    fail(f"agents/openai.yaml:{line_number}: list items must be strings")
                item = parsed
            elif not re.fullmatch(r"[A-Za-z0-9_-]+", item):
                fail(f"agents/openai.yaml:{line_number}: invalid bare list item {item!r}")
            items.append(item)
        return items
    if value[:1] in "\"'":
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            fail(f"agents/openai.yaml:{line_number}: invalid quoted value: {exc}")
        if not isinstance(parsed, str):
            fail(f"agents/openai.yaml:{line_number}: scalar must be a string")
        return parsed
    fail(
        f"agents/openai.yaml:{line_number}: quote string values or use a supported "
        "boolean/list scalar"
    )


def parse_openai_metadata(text: str) -> dict[str, dict[str, object]]:
    if "\t" in text:
        fail("agents/openai.yaml: tabs are not allowed")
    sections: dict[str, dict[str, object]] = {}
    current: dict[str, object] | None = None
    current_name: str | None = None
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0:
            match = re.fullmatch(r"([a-z_][a-z0-9_]*):\s*", raw_line)
            if not match:
                fail(f"agents/openai.yaml:{line_number}: invalid top-level mapping line")
            current_name = match.group(1)
            if current_name in sections:
                fail(
                    f"agents/openai.yaml:{line_number}: duplicate section "
                    f"`{current_name}`"
                )
            if current_name not in {"interface", "policy"}:
                fail(
                    f"agents/openai.yaml:{line_number}: unsupported section "
                    f"`{current_name}`"
                )
            current = {}
            sections[current_name] = current
            continue
        if indent != 2 or current is None or current_name is None:
            fail(
                f"agents/openai.yaml:{line_number}: expected exactly two spaces "
                "inside interface or policy"
            )
        match = re.fullmatch(r"  ([a-z_][a-z0-9_]*):\s*(.+)", raw_line)
        if not match:
            fail(f"agents/openai.yaml:{line_number}: invalid nested mapping line")
        key, raw_value = match.groups()
        if key in current:
            fail(
                f"agents/openai.yaml:{line_number}: duplicate key "
                f"`{current_name}.{key}`"
            )
        current[key] = parse_metadata_scalar(raw_value.strip(), line_number)
    return sections


def load_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        fail(f"{path.relative_to(ROOT)}: invalid TOML: {exc}")


def load_canonical_role_registry() -> dict[str, RoleSpec]:
    try:
        return load_role_registry(ROOT)
    except ValueError as exc:
        fail(f"Role registry error: {exc}")


def expected_role_output_policy(spec: RoleSpec) -> str:
    if spec.sandbox_mode == "read-only":
        return READ_ONLY_OUTPUT_POLICY
    if spec.mutation_class == "write":
        return WRITE_OUTPUT_POLICY
    if spec.mutation_class == "diagnostic":
        return DIAGNOSTIC_OUTPUT_POLICY
    if spec.mutation_class == "test-only":
        return TEST_ONLY_OUTPUT_POLICY
    if spec.mutation_class == "documentation-only":
        return DOCUMENTATION_OUTPUT_POLICY
    fail(f"{spec.filename}: unsupported registry mutation_class {spec.mutation_class!r}")


def extract_policy_block(instructions: str, tag: str, filename: str) -> str:
    matches = re.findall(
        rf"<{re.escape(tag)}>\n.*?\n</{re.escape(tag)}>",
        instructions,
        re.DOTALL,
    )
    if len(matches) != 1:
        fail(f"{filename}: expected exactly one <{tag}> block, found {len(matches)}")
    return matches[0]


def reject_relaxed_role_policy(instructions: str, filename: str) -> None:
    if RELAX_POLICY_PATTERN.search(instructions):
        fail(f"{filename}: role instructions contain a policy relaxation")
    if RELAX_PERMISSION_PATTERN.search(instructions):
        fail(f"{filename}: role instructions contain a permission relaxation")


def reject_direct_positive_permissions(
    instructions: str,
    safety_policy: str,
    output_policy: str,
    spec: RoleSpec,
) -> None:
    remaining = instructions.replace(safety_policy, "", 1).replace(output_policy, "", 1)
    if POSITIVE_GLOBAL_PERMISSION_PATTERN.search(remaining):
        fail(f"{spec.filename}: role instructions contain a forbidden direct permission")
    if (
        spec.sandbox_mode == "read-only"
        and POSITIVE_READ_ONLY_PERMISSION_PATTERN.search(remaining)
    ):
        fail(f"{spec.filename}: read-only instructions contain a forbidden direct permission")


def validate_role_files(role_registry: dict[str, RoleSpec]) -> None:
    actual = {path.name for path in ROLE_DIR.glob("*.toml")}
    expected = {spec.filename for spec in role_registry.values()}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected: {', '.join(extra)}")
        fail("Agent template set mismatch (" + "; ".join(details) + ")")

    role_data: dict[str, tuple[RoleSpec, dict[str, object]]] = {}
    seen_names: set[str] = set()
    for spec in role_registry.values():
        path = ROLE_DIR / spec.filename
        text = path.read_text(encoding="utf-8")
        if not text.startswith(MANAGED_MARKER + "\n"):
            fail(f"{spec.filename}: package-managed marker is missing")
        data = load_toml(path)
        for key in ("name", "description", "developer_instructions"):
            if not isinstance(data.get(key), str) or not str(data[key]).strip():
                fail(f"{spec.filename}: required string field `{key}` is missing")
        name = str(data["name"])
        if name in seen_names:
            fail(f"Duplicate custom-agent name: {name}")
        if name in FORBIDDEN_ROLE_NAMES:
            fail(f"{spec.filename}: forbidden custom-agent name: {name}")
        seen_names.add(name)
        role_data[spec.filename] = (spec, data)

    for filename, (spec, data) in role_data.items():
        expected_values = {
            "name": spec.name,
            "description": spec.description,
            "model": spec.model,
            "model_reasoning_effort": spec.model_reasoning_effort,
            "model_reasoning_summary": spec.model_reasoning_summary,
            "model_verbosity": spec.model_verbosity,
            "sandbox_mode": spec.sandbox_mode,
        }
        for key, expected_value in expected_values.items():
            if data.get(key) != expected_value:
                fail(
                    f"{filename}: `{key}` is {data.get(key)!r}, expected {expected_value!r}"
                )
        instructions = str(data["developer_instructions"])
        safety_policy = extract_policy_block(instructions, "ROLE-SAFETY-POLICY", filename)
        reject_relaxed_role_policy(instructions, filename)
        if safety_policy != ROLE_SAFETY_POLICY:
            fail(f"{filename}: ROLE-SAFETY-POLICY must exactly match the canonical policy")
        output_policy = extract_policy_block(instructions, "ROLE-OUTPUT-POLICY", filename)
        if output_policy != expected_role_output_policy(spec):
            fail(f"{filename}: ROLE-OUTPUT-POLICY must exactly match the canonical policy")
        reject_direct_positive_permissions(instructions, safety_policy, output_policy, spec)
        if spec.name == "docs_researcher":
            required = (
                "Check locally installed or vendored source first",
                "Record the exact investigated version",
                "Cross-check implementation with tests or exported types",
                "INVESTIGATED_VERSION:",
                "API_SIGNATURES:",
                "BREAKING_CHANGES_AND_CAVEATS:",
            )
            missing = [marker for marker in required if marker not in instructions]
            if missing:
                fail(
                    f"{filename}: source-research contract is incomplete: "
                    + ", ".join(missing)
                )
        if "status" not in instructions.lower() and "verdict" not in instructions.lower():
            fail(f"{filename}: no explicit status or verdict output contract")
        if data.get("approval_policy") is not None:
            fail(f"{filename}: must not override approval_policy")
        if data.get("sandbox_mode") == "danger-full-access":
            fail(f"{filename}: danger-full-access is forbidden")


def validate_install_profiles(
    role_registry: dict[str, RoleSpec],
    profiles: dict[str, InstallProfile],
) -> None:
    if list(profiles) != ["lite", "hard"]:
        fail("install profiles must be ordered exactly as lite, hard")
    if list(profiles["lite"].roles) != ["luna_worker", "luna_test_runner"]:
        fail("Lite profile must contain only luna_worker and luna_test_runner")
    if list(profiles["hard"].roles) != list(role_registry):
        fail("Hard profile must contain the complete role registry in registry order")
    if profiles["lite"].default_max_threads != 2:
        fail("Lite default_max_threads must be 2")
    if profiles["hard"].default_max_threads != 4:
        fail("Hard default_max_threads must be 4")

    required = {
        "luna_worker": ("gpt-5.6-luna", "max", "workspace-write"),
        "luna_test_runner": ("gpt-5.6-luna", "medium", "workspace-write"),
        "skeptic": ("gpt-5.6-terra", "high", "read-only"),
        "sol_reviewer": ("gpt-5.6-sol", "xhigh", "read-only"),
    }
    for name, (model, effort, sandbox) in required.items():
        spec = role_registry.get(name)
        if spec is None:
            fail(f"required role is missing: {name}")
        if (spec.model, spec.model_reasoning_effort, spec.sandbox_mode) != (
            model, effort, sandbox
        ):
            fail(f"{name}: model, effort, or sandbox does not match the profile contract")
    if role_registry["sol_reviewer"].fallbacks:
        fail("sol_reviewer must not have a weaker fallback")
    if role_registry["luna_test_runner"].intents != ("test-execution",):
        fail("luna_test_runner must be execution-only")


def validate_openai_yaml() -> None:
    path = ROOT / "agents" / "openai.yaml"
    data = parse_openai_metadata(path.read_text(encoding="utf-8"))
    expected_sections = {"interface", "policy"}
    if set(data) != expected_sections:
        fail(
            "agents/openai.yaml: expected sections "
            + ", ".join(sorted(expected_sections))
        )
    interface = data["interface"]
    policy = data["policy"]
    expected_interface = {"display_name", "short_description", "default_prompt"}
    expected_policy = {"products", "allow_implicit_invocation"}
    unexpected_interface = sorted(set(interface) - expected_interface)
    unexpected_policy = sorted(set(policy) - expected_policy)
    if unexpected_interface:
        fail(
            "agents/openai.yaml: unsupported interface key(s): "
            + ", ".join(unexpected_interface)
        )
    if unexpected_policy:
        fail(
            "agents/openai.yaml: unsupported policy key(s): "
            + ", ".join(unexpected_policy)
        )
    missing_interface = sorted(expected_interface - set(interface))
    missing_policy = sorted(expected_policy - set(policy))
    if missing_interface:
        fail(
            "agents/openai.yaml: missing interface key(s): "
            + ", ".join(missing_interface)
        )
    if missing_policy:
        fail(
            "agents/openai.yaml: missing policy key(s): " + ", ".join(missing_policy)
        )
    for key in expected_interface:
        if not isinstance(interface[key], str) or not str(interface[key]).strip():
            fail(f"agents/openai.yaml: interface.{key} must be a non-empty string")
    if policy["products"] != ["CODEX"]:
        fail("agents/openai.yaml: policy.products must be exactly [CODEX]")
    if policy["allow_implicit_invocation"] is not False:
        fail("agents/openai.yaml: allow_implicit_invocation must be false")
    default_prompt = str(interface["default_prompt"])
    if "$codex-worker-orchestrator" not in default_prompt:
        fail(
            "agents/openai.yaml: default_prompt must explicitly invoke "
            "$codex-worker-orchestrator"
        )


def validate_python_scripts() -> None:
    for path in sorted((ROOT / "scripts").glob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            fail(f"{path.relative_to(ROOT)}: syntax error: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the orchestrator package and optionally run its test suite."
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run the source unittest suite after structural validation.",
    )
    args = parser.parse_args(argv)

    reject_package_symlinks(ROOT)

    missing = [
        path.relative_to(ROOT).as_posix()
        for path in REQUIRED_FILES
        if not path.is_file()
    ]
    if missing:
        fail(f"Missing required files: {', '.join(missing)}")

    role_registry = load_canonical_role_registry()
    try:
        install_profiles = load_install_profiles(ROOT, role_registry)
    except ValueError as exc:
        fail(f"Install profile registry error: {exc}")
    validate_install_profiles(role_registry, install_profiles)
    package_version = load_package_version()
    skill_text = SKILL.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(skill_text)
    if frontmatter.get("name") != "codex-worker-orchestrator":
        fail("frontmatter name must be codex-worker-orchestrator")
    if not re.fullmatch(r"[a-z0-9-]+", frontmatter["name"]):
        fail("skill name must contain only lowercase letters, numbers, and hyphens")
    if len(frontmatter["name"]) > 64:
        fail("skill name must remain at most 64 characters")
    if (
        frontmatter["name"].startswith("-")
        or frontmatter["name"].endswith("-")
        or "--" in frontmatter["name"]
    ):
        fail("skill name must not start/end with a hyphen or contain consecutive hyphens")
    description = frontmatter.get("description", "")
    if not description.startswith("Use when "):
        fail("frontmatter description must start with `Use when `")
    if len(description) > 500:
        fail("frontmatter description must remain under 500 characters")
    if "<" in description or ">" in description:
        fail("frontmatter description must not contain angle brackets")
    body_match = re.match(r"\A---\r?\n.*?\r?\n---\r?\n(.*)\Z", skill_text, re.DOTALL)
    if body_match is None or not body_match.group(1).strip():
        fail("SKILL.md body must not be empty")

    if "<SUBAGENT-STOP>" not in skill_text or "</SUBAGENT-STOP>" not in skill_text:
        fail("recursive orchestration guard is missing")
    if "## Route the task" not in skill_text:
        fail("SKILL.md must have a clear routing section")
    start_index = skill_text.find("superpowers:using-superpowers")
    route_index = skill_text.find("## Route the task")
    if start_index < 0 or start_index > route_index:
        fail("using-superpowers must be required before task routing")
    if "scripts/preflight.py" not in skill_text:
        fail("SKILL.md must require the runtime preflight")
    if "directory containing this `SKILL.md`" not in skill_text:
        fail("SKILL.md must resolve preflight relative to its own skill directory")
    if "Never resolve the preflight script from the repository CWD" not in skill_text:
        fail("SKILL.md must forbid resolving preflight from the repository CWD")
    if "actual available custom agents" not in skill_text.lower():
        fail("SKILL.md must tell the controller to inspect actual available custom agents")

    scenarios_path = ROOT / "tests" / "behavioral-scenarios.md"
    scenario_count = None
    if scenarios_path.is_file():
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (*REQUIRED_FILES, scenarios_path)
        )
        missing_skills = sorted(
            name for name in REQUIRED_SUPERPOWERS if name not in combined
        )
        if missing_skills:
            fail(f"Missing Superpowers references: {', '.join(missing_skills)}")
        scenarios = scenarios_path.read_text(encoding="utf-8")
        scenario_count = len(re.findall(r"^## \d+\.", scenarios, re.MULTILINE))
        if scenario_count < 21:
            fail(f"Expected at least 21 behavioral scenarios, found {scenario_count}")

    dispatch_text = (ROOT / "references" / "dispatch-contract.md").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "full structured report in the final response",
        "Do not write a report file",
        "Mode: `<report-file | final-response>`",
    ):
        if phrase not in dispatch_text:
            fail(f"Dispatch contract is missing read-only output rule: {phrase}")

    validate_role_files(role_registry)
    validate_openai_yaml()
    validate_python_scripts()

    local_refs = re.findall(
        r"`((?:references|tests|scripts|assets)/[^`\n]+(?:\.md|\.py|\.toml))`",
        skill_text,
    )
    missing_refs = sorted({rel for rel in local_refs if not (ROOT / rel).is_file()})
    if missing_refs:
        fail(f"Broken local references: {', '.join(missing_refs)}")

    # Check the explicit publish/install manifest only after semantic role
    # diagnostics, so a malformed role set reports its specific contract error.
    included_files(ROOT)

    print("PASS: skill package structure and routing invariants are valid")
    print(f"Root: {ROOT}")
    print(f"Version: {package_version}")
    print(f"Custom-agent templates: {len(role_registry)}")
    print(f"Install profiles: {', '.join(install_profiles)}")
    if scenario_count is not None:
        print(f"Behavioral scenarios: {scenario_count}")

    if args.run_tests:
        if not (ROOT / "tests").is_dir():
            fail("Source tests are not included in the published package")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(ROOT / "tests"),
                "-p",
                "test_*.py",
                "-v",
            ],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode
        print("PASS: bundled unittest suite")

    print("NOTE: runtime role discovery and behavioral compliance require a real Codex session")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
