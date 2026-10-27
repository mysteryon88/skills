import json
import importlib.metadata
import platform
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
}

SKILL_LOCAL_DETECTION_SKIP_PREFIXES = {
    ("scripts", "tests", "fixtures"),
    ("scripts", "tests", "testdata"),
}

TON_SUFFIXES = {
    ".tact": "tact",
    ".tolk": "tolk",
    ".fc": "func",
    ".func": "func",
}

EVM_SUFFIXES = {
    ".sol": "solidity",
    ".vy": "vyper",
    ".fe": "fe",
}

WEB3_PROJECT_TYPES = {
    "ton",
    "blueprint-ton",
    "acton-ton",
    "mixed",
    "mixed-evm-target",
    "mixed-ton-target",
    "solidity-foundry",
    "solidity-hardhat",
    "solidity-truffle",
    "solidity-generic",
    "vyper",
    "fe",
}

WEB3_SUPPORTED_LANGUAGES = {
    "ton": ["tact", "tolk", "func"],
    "evm": ["solidity", "vyper", "fe"],
}

TON_SHARED_DEPENDENCY_STEMS = {
    "common",
    "constant",
    "constants",
    "error",
    "errors",
    "helper",
    "helpers",
    "imports",
    "message",
    "messages",
    "opcode",
    "opcodes",
    "serialization",
    "storage",
    "type",
    "types",
    "util",
    "utils",
}

EVM_DEFAULT_SKIP_PARTS = {
    "interfaces",
    "interface",
    "mocks",
    "mock",
    "test",
    "tests",
    "script",
    "scripts",
    "generated",
    "cache",
    "artifacts",
    "lib",
    "libs",
    "libraries",
}

LANGUAGE_HINTS = {
    ".py": "python",
    ".rs": "rust",
    ".go": "go",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".sol": "solidity",
    ".vy": "vyper",
    ".fe": "fe",
}

RESULT_RE = re.compile(r"^(?:(?P<prefix>.+)\.)?(?P<kind>killed|not[-]?killed|timeout|compile[-_]error|invalid|flaky|skipped|equivalent|presumed[-_]equivalent)\.txt$")


@dataclass(frozen=True)
class CommandSpec:
    argv: list
    cwd: str | None = None

    @property
    def shell(self):
        return " ".join(shell_quote(part) for part in self.argv)

    def to_dict(self):
        data = {
            "argv": [str(part) for part in self.argv],
            "shell": self.shell,
        }
        if self.cwd:
            data["cwd"] = self.cwd
        return data


def shell_quote(value: str) -> str:
    return shlex.quote(str(value))


def command_spec(argv, cwd=None):
    return CommandSpec([str(part) for part in argv], cwd=str(cwd) if cwd else None)


def shell_join(argv):
    return command_spec(argv).shell


def _relative(path, root):
    return path.relative_to(root).as_posix()


def supported_web3_languages():
    return {family: list(languages) for family, languages in WEB3_SUPPORTED_LANGUAGES.items()}


def _is_in_skipped_dir(path, root):
    relative_parts = path.relative_to(root).parts
    return any(part in SKIP_DIRS for part in relative_parts)


def _iter_files(root):
    for path in root.rglob("*"):
        if _is_in_skipped_dir(path, root):
            continue
        if path.is_file():
            yield path


def _looks_like_skill_root(root):
    return (root / "SKILL.md").exists() and (root / "references").is_dir() and (root / "scripts").is_dir()


def _is_skill_local_detection_path(relative_path, root):
    if not _looks_like_skill_root(root):
        return False
    parts = Path(relative_path).parts
    return any(parts[: len(prefix)] == prefix for prefix in SKILL_LOCAL_DETECTION_SKIP_PREFIXES)


def _safe_read_text(path):
    return path.read_text(encoding="utf-8", errors="replace")


def _is_generated_mutant_path(path):
    if ".mutant." in path.name:
        return True
    return any(part.startswith("mutants") for part in path.parts)


def _load_package_scripts(root):
    package_json = root / "package.json"
    if not package_json.exists():
        return {}
    try:
        data = json.loads(_safe_read_text(package_json))
    except json.JSONDecodeError:
        return {}
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {str(key): str(value) for key, value in scripts.items()}


def _load_package_json(root):
    package_json = Path(root) / "package.json"
    if not package_json.exists():
        return {}
    try:
        data = json.loads(_safe_read_text(package_json))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _detect_package_manager(root):
    root = Path(root)
    lockfile_map = [
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("bun.lockb", "bun"),
        ("bun.lock", "bun"),
        ("package-lock.json", "npm"),
    ]
    for filename, manager in lockfile_map:
        if (root / filename).exists():
            return manager
    package_manager = _load_package_json(root).get("packageManager")
    if isinstance(package_manager, str):
        name = package_manager.split("@", 1)[0].strip().lower()
        if name in {"pnpm", "yarn", "npm", "bun"}:
            return name
    return None


def _has_any(root, patterns):
    for pattern in patterns:
        if any(root.glob(pattern)):
            return True
    return False


def _normalize_contract_name(path):
    name = Path(path).name.lower()
    for suffix in (
        ".spec.ts",
        ".test.ts",
        ".spec.js",
        ".test.js",
        ".spec.tolk",
        ".test.tolk",
        ".wrapper.ts",
        ".wrapper.js",
        ".wrapper.tolk",
        ".gen.ts",
        ".gen.js",
        ".gen.tolk",
    ):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(path).stem.lower()


def _choose_best_match(contract_name, candidates):
    exact = [candidate for candidate in candidates if _normalize_contract_name(candidate) == contract_name]
    if exact:
        return sorted(exact)[0]
    partial = [candidate for candidate in candidates if contract_name in _normalize_contract_name(candidate)]
    if partial:
        return sorted(partial)[0]
    return None


def _choose_best_target_match(target_hint, candidates):
    if not candidates:
        return None
    if not target_hint:
        return list(candidates)[0]
    normalized_hint = str(target_hint).replace("\\", "/").lower()
    exact_path = [candidate for candidate in candidates if candidate.lower() == normalized_hint]
    if exact_path:
        return exact_path[0]
    normalized_name = _normalize_contract_name(normalized_hint)
    exact_name = [candidate for candidate in candidates if _normalize_contract_name(candidate) == normalized_name]
    if exact_name:
        return sorted(exact_name)[0]
    partial = [candidate for candidate in candidates if normalized_hint in candidate.lower() or normalized_name in _normalize_contract_name(candidate)]
    if partial:
        return sorted(partial)[0]
    return None


def _is_primary_contract_path(relative_path):
    first_part = Path(relative_path).parts[0]
    return first_part not in {"examples", "tmp", "fixtures"}


def _looks_like_shared_ton_dependency(relative_path, wrapper=None, test=None):
    if wrapper or test:
        return False
    path = Path(relative_path)
    stem = path.stem.lower()
    parts = {part.lower() for part in path.parts[:-1]}
    if parts.intersection({"common", "include", "includes", "lib", "libs", "shared", "stdlib", "types", "utils"}):
        return True
    if stem in TON_SHARED_DEPENDENCY_STEMS:
        return True
    if stem.endswith("-utils") or stem.endswith("_utils"):
        return True
    if stem.endswith("-helpers") or stem.endswith("_helpers"):
        return True
    if stem in {"fees-management", "fee-management"}:
        return True
    return False


def _target_hint_relative_path(root, target_hint):
    if not target_hint:
        return None
    raw_hint = str(target_hint).replace("\\", "/")
    path = Path(raw_hint)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            return None
    return raw_hint.strip("/")


def _filter_paths_under_directory(paths, directory):
    if not directory:
        return list(paths)
    prefix = directory.rstrip("/") + "/"
    return [path for path in paths if path == directory or path.startswith(prefix)]


def _target_hint_is_existing_directory(root, target_hint):
    relative_hint = _target_hint_relative_path(root, target_hint)
    if not relative_hint:
        return None
    candidate = root / Path(relative_hint)
    if candidate.is_dir():
        return relative_hint
    return None


def _target_hint_is_existing_file(root, target_hint):
    relative_hint = _target_hint_relative_path(root, target_hint)
    if not relative_hint:
        return None
    candidate = root / Path(relative_hint)
    if candidate.is_file():
        return relative_hint
    return None


def _safe_target_slug(relative_path):
    path = str(relative_path).replace("\\", "/")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-")
    return slug or "target"


def _quote_shell_value(value):
    return shell_quote(value)


def _append_unique(values, value):
    if value and value not in values:
        values.append(value)


def _is_solidity_source_path(relative_path):
    parts = Path(relative_path).parts
    if any(part in EVM_DEFAULT_SKIP_PARTS for part in parts):
        return False
    if Path(relative_path).name.endswith(".t.sol"):
        return False
    return Path(relative_path).suffix.lower() == ".sol"


def _is_evm_source_path(relative_path):
    parts = Path(relative_path).parts
    if any(part in EVM_DEFAULT_SKIP_PARTS for part in parts):
        return False
    if Path(relative_path).name.endswith(".t.sol"):
        return False
    return Path(relative_path).suffix.lower() in EVM_SUFFIXES


def _is_test_path(relative_path):
    path = Path(relative_path)
    parts = path.parts
    return any(part in {"test", "tests"} for part in parts) or ".spec." in path.name or ".test." in path.name or path.name.endswith(".t.sol")


def _solidity_sources(root):
    root = Path(root).resolve()
    sources = []
    tests = _test_files(root)
    for path in _iter_files(root):
        relative_path = _relative(path, root)
        if _is_generated_mutant_path(Path(relative_path)) or _is_skill_local_detection_path(Path(relative_path), root):
            continue
        if _is_solidity_source_path(relative_path):
            sources.append(relative_path)
    return _rank_evm_sources(root, sources, tests)


def _evm_sources(root):
    root = Path(root).resolve()
    sources = []
    tests = _test_files(root)
    for path in _iter_files(root):
        relative_path = _relative(path, root)
        if _is_generated_mutant_path(Path(relative_path)) or _is_skill_local_detection_path(Path(relative_path), root):
            continue
        if _is_evm_source_path(relative_path):
            sources.append(relative_path)
    return _rank_evm_sources(root, sources, tests)


def _test_files(root):
    root = Path(root).resolve()
    tests = []
    for path in _iter_files(root):
        relative_path = _relative(path, root)
        if _is_generated_mutant_path(Path(relative_path)) or _is_skill_local_detection_path(Path(relative_path), root):
            continue
        if _is_test_path(relative_path):
            tests.append(relative_path)
    return sorted(tests)


def _read_source_excerpt(root, relative_path):
    path = Path(root) / Path(relative_path)
    if not path.exists() or not path.is_file():
        return ""
    return _safe_read_text(path)[:20000]


def _solidity_declaration_kind(text):
    if re.search(r"\bcontract\s+\w+", text):
        if re.search(r"\babstract\s+contract\s+\w+", text):
            return "abstract-contract"
        return "contract"
    if re.search(r"\blibrary\s+\w+", text):
        return "library"
    if re.search(r"\binterface\s+\w+", text):
        return "interface"
    return "unknown"


def _evm_target_score(root, relative_path, test_files, explicit=False):
    path = Path(relative_path)
    score = 0
    if explicit:
        score += 1000
    match = _choose_best_match(_normalize_contract_name(relative_path), test_files)
    if match:
        score += 400
    parts = {part.lower() for part in path.parts[:-1]}
    if parts.intersection(EVM_DEFAULT_SKIP_PARTS):
        score -= 200
    if path.name.endswith(".t.sol"):
        score -= 500
    if path.suffix.lower() == ".sol":
        kind = _solidity_declaration_kind(_read_source_excerpt(root, relative_path))
        if kind == "contract":
            score += 250
        elif kind == "abstract-contract":
            score -= 40
        elif kind in {"interface", "library"}:
            score -= 100
    if relative_path.startswith("src/"):
        score += 80
    elif relative_path.startswith("contracts/"):
        score += 70
    elif relative_path.startswith("packages/") or relative_path.startswith("apps/"):
        score += 50
    return score


def _rank_evm_sources(root, sources, test_files, explicit=False):
    return sorted(
        sources,
        key=lambda item: (-_evm_target_score(root, item, test_files, explicit=explicit), item),
    )


def _package_script_command(scripts, preferred_names, package_manager="npm"):
    if not package_manager:
        return None
    for name in preferred_names:
        if name in scripts:
            if package_manager == "yarn":
                return f"yarn {name}"
            if package_manager == "bun":
                return f"bun run {name}"
            if package_manager == "pnpm":
                return f"pnpm run {name}"
            return f"npm run {name}"
    return None


def _recommended_script_commands(scripts, package_manager, compile_names, test_names):
    return (
        _package_script_command(scripts, compile_names, package_manager=package_manager),
        _package_script_command(scripts, test_names, package_manager=package_manager),
    )


def _run_command_probe(command, timeout=3):
    executable = shutil.which(command[0])
    if executable is None:
        return {
            "found": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "invoked_as": command[0],
            "path": None,
            "timed_out": False,
        }
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "found": True,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "invoked_as": command[0],
            "path": executable,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "found": True,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "invoked_as": command[0],
            "path": executable,
            "timed_out": True,
        }


def _extract_version_line(text):
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "usage" in stripped.lower():
            continue
        if stripped.lower().startswith("error:"):
            continue
        if stripped.startswith("***"):
            continue
        if not re.search(r"\d", stripped) and "version" not in stripped.lower():
            continue
        return stripped
    return None


def _probe_version(command_name, command_runner):
    for candidate in ("--version", "-V"):
        result = command_runner([command_name, candidate])
        if not result.get("found"):
            return None
        if result.get("timed_out"):
            continue
        if result.get("returncode") != 0:
            continue
        version_line = _extract_version_line((result.get("stdout") or "") + "\n" + (result.get("stderr") or ""))
        if version_line is not None:
            return version_line
    return None


def _probe_installed_um_package():
    package_root = None
    package_version = None
    ton_languages = {"tact": False, "tolk": False, "func": False}
    rule_files = {language: False for language in WEB3_SUPPORTED_LANGUAGES["ton"] + WEB3_SUPPORTED_LANGUAGES["evm"]}
    script_dirs = []

    try:
        import universalmutator  # pylint: disable=import-outside-toplevel

        package_root = Path(universalmutator.__file__).resolve().parent
    except Exception:
        package_root = None

    try:
        package_version = importlib.metadata.version("universalmutator")
    except importlib.metadata.PackageNotFoundError:
        package_version = None

    if package_root is not None:
        static_dir = package_root / "static"
        ton_language_files = {
            "tact": static_dir / "tact.rules",
            "tolk": static_dir / "tolk.rules",
            "func": static_dir / "func.rules",
        }
        for name, rule_path in ton_language_files.items():
            ton_languages[name] = rule_path.exists()
        for name in rule_files:
            rule_files[name] = (static_dir / f"{name}.rules").exists()

    for candidate in (
        sysconfig.get_path("scripts"),
        str(Path.home() / "AppData" / "Roaming" / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}" / "Scripts") if platform.system() == "Windows" else None,
        str(Path.home() / ".local" / "bin") if platform.system() != "Windows" else None,
    ):
        if candidate and candidate not in script_dirs:
            script_dirs.append(candidate)

    return {
        "version": package_version,
        "root": str(package_root) if package_root is not None else None,
        "python_executable": sys.executable,
        "sys_prefix": sys.prefix,
        "script_dirs": script_dirs,
        "ton_languages": ton_languages,
        "rule_files": rule_files,
    }


def _path_is_under(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except (OSError, ValueError):
        return False


def _package_rules_match_command_environment(command_path, package_info):
    if not command_path:
        return False
    script_dirs = package_info.get("script_dirs") or []
    return any(_path_is_under(command_path, script_dir) for script_dir in script_dirs)


def _language_capability(language, help_text, package_info, package_rules_match_command, smoke_probe_passed=None):
    advertised = re.search(rf"\b{re.escape(language)}\b", help_text, re.IGNORECASE) is not None
    rule_files = package_info.get("rule_files") or {}
    rules_file_found = bool(rule_files.get(language))
    if language in (package_info.get("ton_languages") or {}):
        rules_file_found = rules_file_found or bool(package_info.get("ton_languages", {}).get(language))

    if smoke_probe_passed is True:
        confidence = "high"
    elif advertised:
        confidence = "high"
    elif rules_file_found and package_rules_match_command:
        confidence = "medium"
    elif rules_file_found:
        confidence = "low"
    elif help_text:
        confidence = "unsupported"
    else:
        confidence = "unknown"
    return {
        "language": language,
        "rules_file_found": rules_file_found,
        "cli_language_advertised": advertised,
        "smoke_probe_passed": smoke_probe_passed,
        "confidence": confidence,
    }


def _derive_evm_project_type(markers):
    if markers.get("foundry_exists") or markers.get("has_foundry_script"):
        return "solidity-foundry"
    if markers.get("hardhat_configs") or markers.get("has_hardhat_script"):
        return "solidity-hardhat"
    if markers.get("truffle_configs") or markers.get("has_truffle_script"):
        return "solidity-truffle"
    if markers.get("has_solidity"):
        return "solidity-generic"
    if markers.get("has_vyper"):
        return "vyper"
    if markers.get("has_fe"):
        return "fe"
    return None


def _recommended_commands_for_project_type(project_type, scripts, package_manager):
    if project_type == "acton-ton":
        return "acton build", "acton test"
    if project_type == "blueprint-ton":
        return (
            _package_script_command(
                scripts,
                ["build:contracts", "build", "compile", "blueprint:build"],
                package_manager=package_manager,
            ) or "npx blueprint build --all",
            _package_script_command(
                scripts,
                ["test:contracts", "test", "test:unit", "blueprint:test"],
                package_manager=package_manager,
            ) or "npx blueprint test",
        )
    if project_type == "ton":
        return (
            _package_script_command(
                scripts,
                ["build:contracts", "build", "compile"],
                package_manager=package_manager,
            ),
            _package_script_command(
                scripts,
                ["test:contracts", "test", "test:unit"],
                package_manager=package_manager,
            ),
        )
    if project_type == "solidity-foundry":
        compile_command, test_command = _recommended_script_commands(
            scripts,
            package_manager,
            ["build", "compile", "contracts:build"],
            ["test", "test:contracts", "test:solidity"],
        )
        return compile_command or "forge build", test_command or "forge test"
    if project_type == "solidity-hardhat":
        compile_command, test_command = _recommended_script_commands(
            scripts,
            package_manager,
            ["build", "compile", "contracts:build", "hardhat:compile"],
            ["test", "test:contracts", "test:solidity", "hardhat:test"],
        )
        return compile_command or "npx hardhat compile", test_command or "npx hardhat test"
    if project_type == "solidity-truffle":
        compile_command, test_command = _recommended_script_commands(
            scripts,
            package_manager,
            ["build", "compile", "contracts:build", "truffle:compile"],
            ["test", "test:contracts", "test:solidity", "truffle:test"],
        )
        return compile_command or "npx truffle compile", test_command or "npx truffle test"
    if project_type in {"solidity-generic", "vyper", "fe"}:
        return (
            _package_script_command(
                scripts,
                ["build:contracts", "build", "compile"],
                package_manager=package_manager,
            ),
            _package_script_command(
                scripts,
                ["test:contracts", "test", "test:unit"],
                package_manager=package_manager,
            ),
        )
    return None, None


def detect_um_capabilities(command_runner=None, package_probe=None):
    command_runner = command_runner or _run_command_probe
    package_probe = package_probe or _probe_installed_um_package
    commands = {}
    notes = []

    command_names = (
        "mutate",
        "analyze_mutants",
        "show_mutants",
        "prioritize_mutants",
        "prune_mutants",
        "intersect_mutants",
        "check_covered",
    )

    for command_name in command_names:
        help_result = command_runner([command_name, "--help"])
        commands[command_name] = {
            "found": bool(help_result.get("found")),
            "path": help_result.get("path"),
            "help_returncode": help_result.get("returncode"),
            "help_timed_out": bool(help_result.get("timed_out")),
            "version": None,
        }
        if help_result.get("found"):
            commands[command_name]["version"] = _probe_version(command_name, command_runner)
        else:
            notes.append(f"{command_name} command not found")

    mutate_help_result = command_runner(["mutate", "--help"])
    mutate_help_text = ((mutate_help_result.get("stdout") or "") + "\n" + (mutate_help_result.get("stderr") or "")).strip()
    analyze_help_result = command_runner(["analyze_mutants", "--help"])
    analyze_help_text = ((analyze_help_result.get("stdout") or "") + "\n" + (analyze_help_result.get("stderr") or "")).strip()
    show_help_result = command_runner(["show_mutants", "--help"])
    show_help_text = ((show_help_result.get("stdout") or "") + "\n" + (show_help_result.get("stderr") or "")).strip()
    prioritize_help_result = command_runner(["prioritize_mutants", "--help"])
    prioritize_help_text = ((prioritize_help_result.get("stdout") or "") + "\n" + (prioritize_help_result.get("stderr") or "")).strip()

    mutate_flag_names = (
        "--cmd",
        "--mutantDir",
        "--noCheck",
        "--swap",
        "--ignore",
        "--lines",
        "--noFastCheck",
        "--comby",
        "--only",
        "--showRules",
        "--printStat",
    )
    mutate_flags = {
        flag: (flag in mutate_help_text if mutate_help_result.get("found") else False)
        for flag in mutate_flag_names
    }
    analyze_flag_names = (
        "--mutantDir",
        "--prefix",
        "--numMutants",
        "--noShuffle",
        "--timeout",
        "--sourceDir",
        "--fromFile",
        "--compileCommand",
    )
    analyze_flags = {
        flag: (flag in analyze_help_text if analyze_help_result.get("found") else False)
        for flag in analyze_flag_names
    }
    show_flag_names = ("--mutantDir", "--sourceDir", "--prefix", "--concise")
    show_flags = {
        flag: (flag in show_help_text if show_help_result.get("found") else False)
        for flag in show_flag_names
    }
    prioritize_flag_names = ("--mutantDir", "--sourceDir", "--cutoff", "--noSDPriority")
    prioritize_flags = {
        flag: (flag in prioritize_help_text if prioritize_help_result.get("found") else False)
        for flag in prioritize_flag_names
    }

    ton_languages = {
        "tact": (re.search(r"\btact\b", mutate_help_text, re.IGNORECASE) is not None) if mutate_help_result.get("found") else False,
        "tolk": (re.search(r"\btolk\b", mutate_help_text, re.IGNORECASE) is not None) if mutate_help_result.get("found") else False,
        "func": (re.search(r"\bfunc\b", mutate_help_text, re.IGNORECASE) is not None) if mutate_help_result.get("found") else False,
    }

    package_info = package_probe()
    if "rule_files" not in package_info:
        rule_files = {language: False for language in WEB3_SUPPORTED_LANGUAGES["ton"] + WEB3_SUPPORTED_LANGUAGES["evm"]}
        for name, supported in (package_info.get("ton_languages") or {}).items():
            rule_files[name] = bool(supported)
        package_info = dict(package_info)
        package_info["rule_files"] = rule_files
    ton_support_source = "mutate --help" if any(ton_languages.values()) else "unverified"
    package_rules_match_command = _package_rules_match_command_environment(
        mutate_help_result.get("path"),
        package_info,
    )
    for name, supported in package_info.get("ton_languages", {}).items():
        if name in ton_languages and not ton_languages[name] and supported and package_rules_match_command:
            ton_languages[name] = True
            ton_support_source = "installed package rule files matching resolved command environment"
    if any(package_info.get("ton_languages", {}).values()) and not package_rules_match_command and not any(ton_languages.values()):
        notes.append("current Python package rule files do not match the resolved mutate command environment")

    if mutate_help_result.get("found") and mutate_help_result.get("timed_out"):
        notes.append("mutate --help timed out")
    if analyze_help_result.get("found") and analyze_help_result.get("timed_out"):
        notes.append("analyze_mutants --help timed out")
    if show_help_result.get("found") and show_help_result.get("timed_out"):
        notes.append("show_mutants --help timed out")
    if prioritize_help_result.get("found") and prioritize_help_result.get("timed_out"):
        notes.append("prioritize_mutants --help timed out")

    post_processing_names = ("prioritize_mutants", "prune_mutants", "intersect_mutants", "check_covered")
    language_capabilities = {
        language: _language_capability(
            language,
            mutate_help_text,
            package_info,
            package_rules_match_command,
        )
        for language in WEB3_SUPPORTED_LANGUAGES["ton"] + WEB3_SUPPORTED_LANGUAGES["evm"]
    }

    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "python": sys.version.split()[0],
        },
        "package": package_info,
        "commands": commands,
        "mutate_help": {
            "available": bool(mutate_help_result.get("found")),
            "returncode": mutate_help_result.get("returncode"),
            "timed_out": bool(mutate_help_result.get("timed_out")),
            "excerpt": "\n".join(mutate_help_text.splitlines()[:20]),
        },
        "analyze_help": {
            "available": bool(analyze_help_result.get("found")),
            "returncode": analyze_help_result.get("returncode"),
            "timed_out": bool(analyze_help_result.get("timed_out")),
            "excerpt": "\n".join(analyze_help_text.splitlines()[:20]),
        },
        "show_help": {
            "available": bool(show_help_result.get("found")),
            "returncode": show_help_result.get("returncode"),
            "timed_out": bool(show_help_result.get("timed_out")),
            "excerpt": "\n".join(show_help_text.splitlines()[:20]),
        },
        "prioritize_help": {
            "available": bool(prioritize_help_result.get("found")),
            "returncode": prioritize_help_result.get("returncode"),
            "timed_out": bool(prioritize_help_result.get("timed_out")),
            "excerpt": "\n".join(prioritize_help_text.splitlines()[:20]),
        },
        "flags": mutate_flags,
        "mutate_flags": mutate_flags,
        "analyze_flags": analyze_flags,
        "show_flags": show_flags,
        "prioritize_flags": prioritize_flags,
        "post_processing_commands": {
            name: bool(commands[name]["found"])
            for name in post_processing_names
        },
        "ton_languages": ton_languages,
        "ton_support_source": ton_support_source,
        "language_capabilities": language_capabilities,
        "notes": notes,
    }


def detect_project(root):
    root = Path(root).resolve()
    files = list(_iter_files(root))
    scripts = _load_package_scripts(root)
    package_manager = _detect_package_manager(root)
    package_json_exists = (root / "package.json").exists()
    package_manager_ambiguous = package_json_exists and package_manager is None

    blueprint_configs = sorted(_relative(path, root) for path in root.glob("blueprint.config.*"))
    acton_manifest_exists = (root / "Acton.toml").exists()
    jest_configs = sorted(_relative(path, root) for path in root.glob("jest.config.*"))
    tsconfig_exists = (root / "tsconfig.json").exists()
    hardhat_configs = sorted(
        _relative(path, root)
        for pattern in ("hardhat.config.*",)
        for path in root.glob(pattern)
    )
    truffle_configs = sorted(
        _relative(path, root)
        for pattern in ("truffle-config.*",)
        for path in root.glob(pattern)
    )
    foundry_exists = (root / "foundry.toml").exists()
    cargo_exists = (root / "Cargo.toml").exists()
    go_mod_exists = (root / "go.mod").exists()
    maven_exists = (root / "pom.xml").exists()
    gradle_exists = _has_any(root, ["build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"])
    swift_exists = (root / "Package.swift").exists()
    r_description_exists = (root / "DESCRIPTION").exists()
    fortran_exists = (root / "fpm.toml").exists()

    ton_contracts = []
    ton_languages = set()
    wrappers = []
    tests = []
    language_counts = {}

    for path in files:
        relative_path = _relative(path, root)
        relative_path_obj = Path(relative_path)
        relative_parts = relative_path_obj.parts
        if _is_generated_mutant_path(relative_path_obj) or _is_skill_local_detection_path(relative_path_obj, root):
            continue
        suffix = path.suffix.lower()
        if suffix in TON_SUFFIXES and not any(part in {"tests", "wrappers", "wrappers-ts"} for part in relative_parts):
            ton_contracts.append(relative_path)
            ton_languages.add(TON_SUFFIXES[suffix])
        if any(part in {"wrappers", "wrappers-ts"} for part in relative_parts) and suffix in {".ts", ".js", ".tolk"}:
            wrappers.append(relative_path)
        if "tests" in relative_parts or "test" in relative_parts or ".spec." in path.name or ".test." in path.name:
            if suffix in {".ts", ".js", ".py", ".tolk"}:
                tests.append(relative_path)
        if suffix in LANGUAGE_HINTS:
            language_counts[LANGUAGE_HINTS[suffix]] = language_counts.get(LANGUAGE_HINTS[suffix], 0) + 1

    has_blueprint_script = any("blueprint" in command for command in scripts.values())
    has_acton_script = any(re.search(r"\bacton\b", command) for command in scripts.values())
    has_hardhat_script = any("hardhat" in command for command in scripts.values())
    has_truffle_script = any("truffle" in command for command in scripts.values())
    has_foundry_script = any("forge " in command or command.startswith("forge") for command in scripts.values())
    has_ton_layout = all((root / name).exists() for name in ("contracts", "wrappers", "tests"))
    has_acton_layout = (root / "contracts" / "src").exists()
    primary_ton_contracts = [contract for contract in ton_contracts if _is_primary_contract_path(contract)]
    has_solidity = language_counts.get("solidity", 0) > 0
    has_vyper = language_counts.get("vyper", 0) > 0
    has_fe = language_counts.get("fe", 0) > 0
    has_ton = bool(primary_ton_contracts)
    has_evm = has_solidity or has_vyper or has_fe
    project_family = "mixed" if has_ton and has_evm else "ton" if has_ton else "evm" if has_evm else "non-web3"
    evm_project_type = _derive_evm_project_type(
        {
            "foundry_exists": foundry_exists,
            "has_foundry_script": has_foundry_script,
            "hardhat_configs": hardhat_configs,
            "has_hardhat_script": has_hardhat_script,
            "truffle_configs": truffle_configs,
            "has_truffle_script": has_truffle_script,
            "has_solidity": has_solidity,
            "has_vyper": has_vyper,
            "has_fe": has_fe,
        }
    )

    if primary_ton_contracts and (acton_manifest_exists or has_acton_script or has_acton_layout):
        project_type = "acton-ton"
    elif primary_ton_contracts and (blueprint_configs or has_blueprint_script or has_ton_layout):
        project_type = "blueprint-ton"
    elif primary_ton_contracts:
        project_type = "ton"
    elif foundry_exists or has_foundry_script:
        project_type = "solidity-foundry"
    elif hardhat_configs or has_hardhat_script:
        project_type = "solidity-hardhat"
    elif truffle_configs or has_truffle_script:
        project_type = "solidity-truffle"
    elif has_solidity:
        project_type = "solidity-generic"
    elif has_vyper:
        project_type = "vyper"
    elif has_fe:
        project_type = "fe"
    elif scripts and (jest_configs or tsconfig_exists):
        project_type = "typescript-jest"
    elif cargo_exists:
        project_type = "rust"
    elif go_mod_exists:
        project_type = "go"
    elif maven_exists:
        project_type = "java-maven"
    elif gradle_exists:
        project_type = "java-gradle"
    elif swift_exists:
        project_type = "swift"
    elif fortran_exists:
        project_type = "fortran"
    elif r_description_exists:
        project_type = "r"
    else:
        project_type = "generic"

    recommended_compile_command, recommended_test_command = _recommended_commands_for_project_type(
        project_type,
        scripts,
        package_manager,
    )
    evm_recommended_compile_command, evm_recommended_test_command = _recommended_commands_for_project_type(
        evm_project_type,
        scripts,
        package_manager,
    )

    contract_mappings = []
    contracts_for_mapping = primary_ton_contracts or ton_contracts
    for contract in sorted(contracts_for_mapping):
        contract_name = _normalize_contract_name(contract)
        contract_mappings.append(
            {
                "contract": contract,
                "language": TON_SUFFIXES[Path(contract).suffix.lower()],
                "wrapper": _choose_best_match(contract_name, wrappers),
                "test": _choose_best_match(contract_name, tests),
            }
        )
    entrypoint_contracts = []
    shared_dependency_files = []
    for mapping in contract_mappings:
        contract = mapping["contract"]
        if _looks_like_shared_ton_dependency(contract, mapping.get("wrapper"), mapping.get("test")):
            shared_dependency_files.append(contract)
        else:
            entrypoint_contracts.append(contract)

    return {
        "root": str(root),
        "project_type": project_type,
        "project_family": project_family,
        "evm_project_type": evm_project_type,
        "markers": {
            "blueprint_configs": blueprint_configs,
            "acton_toml": acton_manifest_exists,
            "hardhat_configs": hardhat_configs,
            "jest_configs": jest_configs,
            "tsconfig": tsconfig_exists,
            "truffle_configs": truffle_configs,
            "foundry_toml": foundry_exists,
            "cargo_toml": cargo_exists,
            "go_mod": go_mod_exists,
            "pom_xml": maven_exists,
            "gradle": gradle_exists,
            "package_swift": swift_exists,
            "description": r_description_exists,
            "fpm_toml": fortran_exists,
            "package_json": package_json_exists,
        },
        "package_scripts": scripts,
        "package_manager": package_manager,
        "package_manager_ambiguous": package_manager_ambiguous,
        "ton_languages": sorted(ton_languages),
        "ton_contracts": sorted(ton_contracts),
        "entrypoint_contracts": sorted(entrypoint_contracts),
        "shared_dependency_files": sorted(shared_dependency_files),
        "contract_mappings": contract_mappings,
        "language_counts": dict(sorted(language_counts.items())),
        "recommended_compile_command": recommended_compile_command,
        "recommended_test_command": recommended_test_command,
        "evm_recommended_compile_command": evm_recommended_compile_command,
        "evm_recommended_test_command": evm_recommended_test_command,
    }


def _jest_test_name_detected(root, test_file, target_stem):
    if root is None or not test_file:
        return False
    path = Path(root) / Path(test_file)
    if not path.exists():
        return False
    text = _safe_read_text(path)
    pattern = rf"\b(?:describe|it|test)\s*\(\s*['\"]{re.escape(target_stem)}['\"]"
    return re.search(pattern, text) is not None


def _find_matching_test(target_path, test_files, project_type, recommended_test_command=None, root=None):
    target_name = _normalize_contract_name(target_path)
    match = _choose_best_match(target_name, test_files)
    if project_type == "solidity-foundry":
        if match:
            return shell_join(["forge", "test", "--match-path", match])
        return recommended_test_command or "forge test"
    if project_type == "solidity-hardhat":
        base_command = recommended_test_command or "npx hardhat test"
        if not match:
            return base_command
        if base_command.startswith("yarn "):
            return f"{base_command} {shell_quote(match)}"
        if base_command.startswith("npm run ") or base_command.startswith("pnpm run ") or base_command.startswith("bun run "):
            return f"{base_command} -- {shell_quote(match)}"
        if base_command.startswith("npx hardhat test"):
            return f"{base_command} {shell_quote(match)}"
        return f"{base_command} {shell_quote(match)}"
    if project_type == "solidity-truffle":
        base_command = recommended_test_command or "npx truffle test"
        if match:
            return f"{base_command} {shell_quote(match)}"
        return base_command
    if match and Path(match).suffix.lower() in {".ts", ".js"}:
        test_name = Path(target_path).stem
        command = ["npx", "jest", "--runInBand", match]
        if _jest_test_name_detected(root, match, test_name):
            command.extend(["-t", test_name])
        return shell_join(command)
    return recommended_test_command


def _fallback_compile_commands(project):
    project_type = project["project_type"]
    commands = []
    if project_type == "acton-ton":
        _append_unique(commands, "acton build")
    elif project_type == "blueprint-ton":
        _append_unique(commands, project.get("recommended_compile_command"))
        _append_unique(commands, "npx blueprint build --all")
    elif project_type == "solidity-foundry":
        _append_unique(commands, project.get("recommended_compile_command") or "forge build")
        _append_unique(commands, "forge build")
    elif project_type == "solidity-hardhat":
        _append_unique(commands, project.get("recommended_compile_command") or "npx hardhat compile")
        _append_unique(commands, "npx hardhat compile")
    elif project_type == "solidity-truffle":
        _append_unique(commands, project.get("recommended_compile_command") or "npx truffle compile")
        _append_unique(commands, "npx truffle compile")
    else:
        _append_unique(commands, project.get("recommended_compile_command"))
    return commands


def _explicit_supported_target(root, target):
    relative = _target_hint_is_existing_file(root, target)
    if not relative:
        return None
    suffix = Path(relative).suffix.lower()
    if suffix in TON_SUFFIXES:
        return relative, TON_SUFFIXES[suffix], "ton"
    if suffix in EVM_SUFFIXES:
        return relative, EVM_SUFFIXES[suffix], "evm"
    return None


def _evm_candidates_for_project(root, project_type, include_skipped=False):
    if include_skipped:
        candidates = []
        for path in _iter_files(root):
            relative_path = _relative(path, root)
            if _is_generated_mutant_path(Path(relative_path)) or _is_skill_local_detection_path(Path(relative_path), root):
                continue
            if Path(relative_path).suffix.lower() in EVM_SUFFIXES and not Path(relative_path).name.endswith(".t.sol"):
                candidates.append(relative_path)
        return _rank_evm_sources(root, candidates, _test_files(root), explicit=True)
    return _solidity_sources(root) if project_type and project_type.startswith("solidity-") else _evm_sources(root)


def _select_plan_target(root, project, target=None):
    project_type = project["project_type"]
    explicit = _explicit_supported_target(root, target)
    if explicit:
        selected, language, family = explicit
        if family == "evm":
            command_project_type = project.get("evm_project_type") or (
                "solidity-generic" if language == "solidity" else language
            )
            return {
                "target": selected,
                "language": language,
                "wrapper": None,
                "test": _choose_best_match(_normalize_contract_name(selected), _test_files(root)),
                "project_type": "mixed-evm-target" if project.get("project_family") == "mixed" else command_project_type,
                "command_project_type": command_project_type,
                "recommended_compile_command": project.get("evm_recommended_compile_command"),
                "recommended_test_command": project.get("evm_recommended_test_command"),
                "explicit_target": True,
            }
        mapping = next((item for item in project["contract_mappings"] if item["contract"] == selected), None)
        command_project_type = project_type if project_type in {"ton", "blueprint-ton", "acton-ton"} else "ton"
        return {
            "target": selected,
            "language": language,
            "wrapper": mapping.get("wrapper") if mapping else None,
            "test": mapping.get("test") if mapping else None,
            "project_type": "mixed-ton-target" if project.get("project_family") == "mixed" else command_project_type,
            "command_project_type": command_project_type,
            "explicit_target": True,
        }

    if project_type in {"ton", "blueprint-ton", "acton-ton", "mixed"}:
        directory_scope = _target_hint_is_existing_directory(root, target)
        if directory_scope:
            scoped_entrypoints = _filter_paths_under_directory(project.get("entrypoint_contracts", []), directory_scope)
            contracts = scoped_entrypoints
        elif target:
            contracts = [mapping["contract"] for mapping in project["contract_mappings"]] or project["ton_contracts"]
        else:
            contracts = project.get("entrypoint_contracts") or [mapping["contract"] for mapping in project["contract_mappings"]] or project["ton_contracts"]
        selected = _choose_best_target_match(target, contracts)
        if not selected:
            return None
        mapping = next((item for item in project["contract_mappings"] if item["contract"] == selected), None)
        language = mapping["language"] if mapping else TON_SUFFIXES[Path(selected).suffix.lower()]
        return {
            "target": selected,
            "language": language,
            "wrapper": mapping.get("wrapper") if mapping else None,
            "test": mapping.get("test") if mapping else None,
        }
    effective_evm_type = project.get("evm_project_type") if project_type == "mixed" else project_type
    if effective_evm_type in {"solidity-foundry", "solidity-hardhat", "solidity-truffle", "solidity-generic", "vyper", "fe"}:
        candidates = _evm_candidates_for_project(root, effective_evm_type, include_skipped=bool(target))
        selected = _choose_best_target_match(target, candidates)
        if not selected:
            return None
        return {
            "target": selected,
            "language": EVM_SUFFIXES[Path(selected).suffix.lower()],
            "wrapper": None,
            "test": _choose_best_match(_normalize_contract_name(selected), _test_files(root)),
            "project_type": effective_evm_type,
            "command_project_type": effective_evm_type,
            "recommended_compile_command": project.get("evm_recommended_compile_command") or project.get("recommended_compile_command"),
            "recommended_test_command": project.get("evm_recommended_test_command") or project.get("recommended_test_command"),
        }
    return None


def _build_scope_summary(root, project, selected, target=None):
    requested_scope = _target_hint_relative_path(root, target) if target else selected["target"]
    project_type = selected.get("command_project_type") or project["project_type"]
    if project_type in {"ton", "blueprint-ton", "acton-ton"}:
        directory_scope = _target_hint_is_existing_directory(root, target)
        if directory_scope:
            entrypoints = _filter_paths_under_directory(project.get("entrypoint_contracts", []), directory_scope)
            shared_files = _filter_paths_under_directory(project.get("shared_dependency_files", []), directory_scope)
            execution_scope = "entrypoint-contracts"
            completeness = "entrypoint-focused-not-full-directory" if shared_files else "entrypoint-directory"
            unmutated_shared_files = shared_files
            mutated_files = entrypoints
        elif selected.get("explicit_target") and selected["target"] in set(project.get("shared_dependency_files", [])):
            entrypoints = []
            shared_files = [selected["target"]]
            unmutated_shared_files = []
            mutated_files = [selected["target"]]
            execution_scope = "explicit-shared-dependency-target"
            completeness = "explicit-shared-dependency-target"
        else:
            entrypoints = [selected["target"]]
            parent = Path(selected["target"]).parent.as_posix()
            shared_files = _filter_paths_under_directory(project.get("shared_dependency_files", []), parent)
            unmutated_shared_files = shared_files
            mutated_files = [selected["target"]]
            execution_scope = "single-entrypoint-contract"
            completeness = "single-target" if not shared_files else "single-entrypoint-not-full-directory"
        return {
            "requested_scope": requested_scope,
            "execution_scope": execution_scope,
            "entrypoint_targets": entrypoints,
            "mutated_files": mutated_files,
            "shared_dependency_files": shared_files,
            "unmutated_shared_dependency_files": unmutated_shared_files,
            "completeness": completeness,
        }
    return {
        "requested_scope": requested_scope,
        "execution_scope": "single-source-file",
        "entrypoint_targets": [selected["target"]],
        "mutated_files": [selected["target"]],
        "shared_dependency_files": [],
        "unmutated_shared_dependency_files": [],
        "completeness": "target-file-only",
    }


def _project_for_selected(project, selected):
    effective = dict(project)
    command_project_type = selected.get("command_project_type") or project.get("project_type")
    effective["project_type"] = command_project_type
    if selected.get("recommended_compile_command") is not None:
        effective["recommended_compile_command"] = selected.get("recommended_compile_command")
    if selected.get("recommended_test_command") is not None:
        effective["recommended_test_command"] = selected.get("recommended_test_command")
    return effective


def _command_dict(argv):
    return command_spec(argv).to_dict()


def _build_plan_for_selected(root, project, selected, target=None, directory_limited=False):
    effective_project = _project_for_selected(project, selected)
    display_project_type = selected.get("project_type") or project["project_type"]
    command_project_type = effective_project["project_type"]
    target_path = selected["target"]
    language = selected["language"]
    scope = _build_scope_summary(root, effective_project, selected, target=target)
    slug = _safe_target_slug(target_path)
    mutant_dir = f"mutants/{slug}"
    report_path = "mutants/REPORT.md"
    mutate_argv = ["mutate", target_path, language, "--mutantDir", mutant_dir]
    initial_mutate_command = shell_join(mutate_argv)
    fallback_compile_commands = _fallback_compile_commands(effective_project)
    fallback_mutate_command_specs = [
        _command_dict(["mutate", target_path, language, "--cmd", command, "--mutantDir", mutant_dir])
        for command in fallback_compile_commands
    ]
    fallback_mutate_commands = [
        command["shell"]
        for command in fallback_mutate_command_specs
    ]
    if selected.get("test"):
        narrow_test_command = _find_matching_test(
            target_path,
            [selected["test"]],
            command_project_type,
            effective_project.get("recommended_test_command"),
            root=root,
        )
    else:
        narrow_test_command = _find_matching_test(
            target_path,
            _test_files(root),
            command_project_type,
            effective_project.get("recommended_test_command"),
            root=root,
        )

    analyze_test_command = narrow_test_command
    if fallback_compile_commands and narrow_test_command:
        analyze_test_command = f"{fallback_compile_commands[0]} && {narrow_test_command}"
    analyze_command = None
    analyze_argv = None
    if analyze_test_command:
        analyze_argv = ["analyze_mutants", target_path, analyze_test_command, "--mutantDir", mutant_dir, "--prefix", slug]
        analyze_command = shell_join(analyze_argv)

    preflight_steps = [
        "Run scripts/detect_um_capabilities.py --format markdown and confirm mutate/analyze_mutants are available.",
        "Treat planned mutate/analyze commands as templates until detect_um_capabilities confirms command and flag support.",
        "Do not run mutate or analyze_mutants in parallel inside one project checkout; run this target sequentially. If parallel work is required, use an isolated git worktree or copy the repository to .tmp/um-runs/<target-slug> for each target.",
    ]
    if narrow_test_command:
        preflight_steps.append(f"Run baseline narrow test command: {narrow_test_command}")
    else:
        preflight_steps.append("No baseline test command was detected; inspect the project and choose a real test command before mutation generation.")
    preflight_steps.append("Do not start mutation generation if the baseline tests fail.")
    preflight_steps.append(
        f"Run baseline compile command: {fallback_compile_commands[0]}" if fallback_compile_commands else "No compile command was detected; inspect the project before running mutation analysis."
    )
    preflight_steps.extend(
        [
            "Warn the user that mutation analysis can run for a long time or appear stuck while tests execute repeatedly; keep logs and report progress before long analyze runs.",
            f"Run default compile-check mutation first: {initial_mutate_command}",
            "If default compile check fails because the language compiler is missing or the file is not standalone, rerun mutation with the first fallback_mutate_commands entry.",
            f"Create or update {report_path} after mutation generation with target, commands, total mutants, and non-compiling mutants.",
            "Only run analyze_mutants after one mutation generation path produces compilable mutants.",
            f"Update {report_path} after analysis with killed, survived, timeout, compile-error, and flaky counts plus next test recommendations.",
        ]
    )

    commands = {
        "mutate": _command_dict(mutate_argv),
    }
    if fallback_mutate_command_specs:
        commands["fallback_mutate"] = fallback_mutate_command_specs
    if fallback_compile_commands:
        commands["build"] = {"shell": fallback_compile_commands[0], "argv": shlex.split(fallback_compile_commands[0], posix=False)}
    if narrow_test_command:
        commands["test"] = {"shell": narrow_test_command, "argv": shlex.split(narrow_test_command, posix=False)}
    if analyze_argv:
        commands["analyze"] = _command_dict(analyze_argv)

    plan = {
        "root": str(root),
        "project_type": display_project_type,
        "project_family": project.get("project_family"),
        "command_project_type": command_project_type,
        "package_manager": project["package_manager"],
        "supported_web3_languages": supported_web3_languages(),
        "target": target_path,
        "language": language,
        "scope": scope,
        "wrapper": selected.get("wrapper"),
        "test": selected.get("test"),
        "mutant_dir": mutant_dir,
        "report_path": report_path,
        "execution_mode": "sequential-in-project",
        "command_status": "templates-until-capability-verification",
        "prefix": slug,
        "initial_mutate_command": initial_mutate_command,
        "compile_check_strategy": "try-default-then-project-compile",
        "fallback_compile_commands": fallback_compile_commands,
        "fallback_mutate_commands": fallback_mutate_commands,
        "fallback_mutate_command_specs": fallback_mutate_command_specs,
        "narrow_test_command": narrow_test_command,
        "analyze_command": analyze_command,
        "commands": commands,
        "preflight_steps": preflight_steps,
        "notes": [
            "Use the initial mutate command first so Universal Mutator performs its default compile check.",
            "Use fallback_mutate_commands when direct language compiler checks fail or project compilation requires wrappers/generated artifacts.",
            f"Store mutants under {mutant_dir}, derived from mutants/<safe-target-path>.",
            f"Maintain the campaign report at {report_path}.",
        ],
    }
    if directory_limited:
        plan["notes"].append(
            "Directory target detected. Planned the highest-confidence entrypoint only. Use --all-entrypoints to generate commands for every entrypoint."
        )
    if scope["completeness"] in {"entrypoint-focused-not-full-directory", "single-entrypoint-not-full-directory"}:
        plan["notes"].append("This is an entrypoint-focused campaign, not full directory mutation coverage.")
    if scope["execution_scope"] == "explicit-shared-dependency-target":
        plan["notes"].append("This shared dependency was explicitly selected and will be mutated.")
    if scope["unmutated_shared_dependency_files"]:
        plan["notes"].append("Shared dependency files were observed but are not mutated by default.")
    return plan


def _directory_entrypoint_targets(root, project, target):
    directory_scope = _target_hint_is_existing_directory(root, target)
    if not directory_scope:
        return []
    ton_entrypoints = _filter_paths_under_directory(project.get("entrypoint_contracts", []), directory_scope)
    if ton_entrypoints:
        return ton_entrypoints
    evm_sources = _filter_paths_under_directory(_evm_candidates_for_project(root, project.get("evm_project_type") or project.get("project_type")), directory_scope)
    return evm_sources


def plan_mutation_run(root, target=None, all_entrypoints=False):
    root = Path(root).resolve()
    project = detect_project(root)
    if all_entrypoints and _target_hint_is_existing_directory(root, target):
        runs = []
        for entrypoint in _directory_entrypoint_targets(root, project, target):
            run = plan_mutation_run(root, target=entrypoint, all_entrypoints=False)
            if run.get("target"):
                runs.append(run)
        if runs:
            return {
                "root": str(root),
                "project_type": project["project_type"],
                "project_family": project.get("project_family"),
                "campaign_scope": "entrypoint-focused-directory",
                "runs": runs,
                "notes": ["Directory target detected. Planned one campaign block per entrypoint."],
            }

    selected = _select_plan_target(root, project, target=target)
    if selected is None:
        command_status = "no-target"
        note = "No mutation target was detected. Provide --target or inspect project layout manually."
        if project["project_type"] not in WEB3_PROJECT_TYPES:
            command_status = "unsupported-non-web3"
            note = (
                f"{project['project_type']} is not a supported Web3 smart-contract project for this skill. "
                "Supported language families are TON (tact, tolk, func) and EVM (solidity, vyper, fe)."
            )
        return {
            "root": str(root),
            "project_type": project["project_type"],
            "target": None,
            "language": None,
            "scope": {
                "requested_scope": _target_hint_relative_path(root, target) if target else None,
                "execution_scope": None,
                "entrypoint_targets": [],
                "shared_dependency_files": project.get("shared_dependency_files", []),
                "unmutated_shared_dependency_files": project.get("shared_dependency_files", []),
                "completeness": "no-target",
            },
            "mutant_dir": None,
            "report_path": "mutants/REPORT.md",
            "execution_mode": "sequential-in-project",
            "command_status": command_status,
            "initial_mutate_command": None,
            "fallback_compile_commands": [],
            "fallback_mutate_commands": [],
            "narrow_test_command": project.get("recommended_test_command"),
            "analyze_command": None,
            "compile_check_strategy": "no-target",
            "preflight_steps": [
                "Run scripts/detect_project.py and choose an explicit supported Web3 source or contract target.",
            ],
            "notes": [note],
        }
    return _build_plan_for_selected(
        root,
        project,
        selected,
        target=target,
        directory_limited=bool(_target_hint_is_existing_directory(root, target)),
    )


def _target_language_from_path(target):
    suffix = Path(target).suffix.lower()
    if suffix in TON_SUFFIXES:
        return TON_SUFFIXES[suffix]
    if suffix in EVM_SUFFIXES:
        return EVM_SUFFIXES[suffix]
    return None


def _custom_rule_ideas_for_source(language, text):
    ideas = []

    def add(name, pattern, mutation, why, expected, duplicate="maybe", risk="medium"):
        if pattern in text or language in {"solidity", "vyper", "fe", "tact", "tolk", "func"}:
            ideas.append(
                {
                    "name": name,
                    "target language": language,
                    "code pattern": pattern,
                    "mutation": mutation,
                    "why this is useful": why,
                    "expected test that should kill it": expected,
                    "duplicate with default Universal Mutator rules": duplicate,
                    "risk level": risk,
                    "generated rule lines": [f"{re.escape(pattern)} ==> {mutation}"],
                }
            )

    if language == "solidity":
        if "msg.sender" in text:
            add(
                "sender-access-check",
                "msg.sender == owner",
                "msg.sender != owner",
                "Checks whether owner/admin authorization assertions observe the caller.",
                "A non-owner call should fail and an owner call should succeed.",
                duplicate="maybe",
            )
            add(
                "sender-comparison-direction",
                "owner == msg.sender",
                "owner != msg.sender",
                "Checks access-control comparisons written with owner on the left.",
                "Only-owner tests should kill the flipped comparison.",
                duplicate="maybe",
            )
        if "tx.origin" in text:
            add(
                "tx-origin-check",
                "tx.origin == msg.sender",
                "tx.origin != msg.sender",
                "Checks tests around caller/origin assumptions without treating the mutation as an exploit recipe.",
                "Proxy or delegated caller tests should observe the origin/caller distinction.",
            )
        if "address(0)" in text:
            add(
                "zero-address-guard",
                "recipient != address(0)",
                "recipient == address(0)",
                "Checks whether zero-address rejection is asserted.",
                "A zero-address recipient test should kill it.",
            )
        if "<=" in text:
            add(
                "inclusive-boundary",
                "<=",
                "<",
                "Checks boundary-value tests at the exact maximum.",
                "A test at the boundary value should kill it.",
                duplicate="maybe",
                risk="low",
            )
        if "block.timestamp" in text or "deadline" in text:
            add(
                "deadline-boundary",
                "block.timestamp <= deadline",
                "block.timestamp < deadline",
                "Checks deadline equality behavior.",
                "A transaction exactly at the deadline should kill it.",
            )
        if "safeTransferFrom" in text:
            add(
                "safe-transfer-assumption",
                "safeTransferFrom",
                "transferFrom",
                "Checks token-transfer behavior assumptions in tests.",
                "A token receiver-safety test should kill it.",
                duplicate="maybe",
            )
    elif language in {"tact", "tolk", "func"}:
        if "sender" in text or "myAddress" in text:
            add(
                "ton-sender-guard",
                "sender() == self.owner",
                "sender() != self.owner",
                "Checks whether TON owner/sender authorization is asserted.",
                "A non-owner internal message test should kill it.",
            )
        if "throwIf" in text:
            add(
                "tact-throwif-guard",
                "throwIf",
                "throwUnless",
                "Checks negative-path tests for guard conditions.",
                "A failing guard test should kill it.",
                duplicate="yes",
            )
        if "op" in text or "opcode" in text:
            add(
                "ton-opcode-check",
                "op ==",
                "op !=",
                "Checks message opcode dispatch assertions.",
                "A wrong-opcode message test should kill it.",
            )

    if not ideas:
        add(
            "comparison-boundary",
            "==",
            "!=",
            "Checks whether tests observe a critical equality or guard expression.",
            "A focused negative-path or boundary test should kill it.",
            duplicate="maybe",
            risk="low",
        )
    return ideas[:5]


def _format_rule_ideas_markdown(ideas):
    sections = []
    for idea in ideas:
        lines = ["Rule idea:"]
        for key in [
            "name",
            "target language",
            "code pattern",
            "mutation",
            "why this is useful",
            "expected test that should kill it",
            "duplicate with default Universal Mutator rules",
            "risk level",
        ]:
            lines.append(f"- {key}: {idea[key]}")
        lines.append("- generated rule lines:")
        for rule_line in idea["generated rule lines"]:
            lines.append(f"  {rule_line}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def propose_custom_rules(root, target, write_path=None):
    root = Path(root).resolve()
    relative_target = _target_hint_is_existing_file(root, target) or _target_hint_relative_path(root, target)
    if not relative_target:
        raise FileNotFoundError(f"Target not found: {target}")
    language = _target_language_from_path(relative_target)
    if language is None:
        raise ValueError(f"Unsupported custom-rule target language for {target}")
    text = _safe_read_text(root / Path(relative_target))
    ideas = _custom_rule_ideas_for_source(language, text)
    markdown = _format_rule_ideas_markdown(ideas)
    result = {
        "target": relative_target,
        "language": language,
        "ideas": ideas,
        "markdown": markdown,
        "written_path": None,
    }
    if write_path:
        output_path = Path(write_path)
        if not output_path.is_absolute():
            output_path = root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rule_lines = []
        for idea in ideas:
            rule_lines.append(f"# {idea['name']}: {idea['why this is useful']}")
            rule_lines.extend(idea["generated rule lines"])
        output_path.write_text("\n".join(rule_lines).rstrip() + "\n", encoding="utf-8")
        result["written_path"] = output_path.relative_to(root).as_posix()
    return result


KNOWN_DEFAULT_RULE_PATTERNS = {
    "<=",
    "<",
    ">=",
    ">",
    "==",
    "!=",
    "true",
    "false",
    "0",
    "1",
}


def _line_for_offset(text, offset):
    return text.count("\n", 0, offset) + 1


def _excerpt_for_match(text, match, limit=120):
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    excerpt = text[line_start:line_end].strip()
    if len(excerpt) > limit:
        excerpt = excerpt[: limit - 3].rstrip() + "..."
    return excerpt


def _rule_matches(source_text, pattern):
    try:
        return list(re.finditer(pattern, source_text))
    except re.error:
        return list(re.finditer(re.escape(pattern), source_text))


def _is_broad_rule_pattern(pattern, match_count):
    normalized = pattern.strip()
    unescaped = normalized.replace("\\", "")
    if len(unescaped) <= 2:
        return True
    if unescaped in KNOWN_DEFAULT_RULE_PATTERNS:
        return True
    if re.fullmatch(r"[<>=!&|+\-*/%^~]+", unescaped):
        return True
    if unescaped.lower() in {"true", "false"}:
        return True
    if unescaped in {"0", "1"}:
        return True
    return match_count > 10


def _dry_run_custom_rules(root, relative_target, language, rules_path, command_runner=None):
    with tempfile.TemporaryDirectory(prefix="um-custom-rules-") as tmp:
        mutant_dir = Path(tmp) / "mutants"
        command = [
            "mutate",
            str(root / Path(relative_target)),
            language or "unknown",
            str(rules_path),
            "--mutantDir",
            str(mutant_dir),
        ]
        runner = command_runner or (lambda argv: _run_command_probe(argv, timeout=10))
        result = runner(command)
        return {
            "attempted": True,
            "argv": command,
            "returncode": result.get("returncode"),
            "found": bool(result.get("found", True)),
            "timed_out": bool(result.get("timed_out")),
            "stdout_excerpt": (result.get("stdout") or "")[:1000],
            "stderr_excerpt": (result.get("stderr") or "")[:1000],
        }


def validate_custom_rules_file(root, target, rules, dry_run_mutants=False, command_runner=None):
    root = Path(root).resolve()
    relative_target = _target_hint_is_existing_file(root, target) or _target_hint_relative_path(root, target)
    language = _target_language_from_path(relative_target)
    rules_path = Path(rules)
    if not rules_path.is_absolute():
        rules_path = root / rules_path
    errors = []
    warnings = []
    if not rules_path.exists():
        errors.append(f"rules file not found: {rules}")
        return {"valid": False, "target": relative_target, "language": language, "rules": str(rules), "errors": errors, "warnings": warnings, "rule_checks": [], "auto_usable": False}
    source_text = _safe_read_text(root / Path(relative_target)) if relative_target and (root / Path(relative_target)).exists() else ""
    rule_count = 0
    rule_checks = []
    for lineno, line in enumerate(_safe_read_text(rules_path).splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "==>" not in stripped:
            errors.append(f"line {lineno}: missing ==> separator")
            continue
        left, right = stripped.split("==>", 1)
        pattern = left.strip()
        if not pattern:
            errors.append(f"line {lineno}: empty source pattern")
        if right is None:
            errors.append(f"line {lineno}: invalid replacement")
        matches = _rule_matches(source_text, pattern) if pattern and source_text else []
        broad = _is_broad_rule_pattern(pattern, len(matches)) if pattern else False
        duplicate = pattern.replace("\\", "") in KNOWN_DEFAULT_RULE_PATTERNS
        check = {
            "line": lineno,
            "pattern": pattern,
            "replacement": right.strip(),
            "match_count": len(matches),
            "broad": broad,
            "possible_default_duplicate": duplicate,
            "matches": [
                {
                    "line": _line_for_offset(source_text, match.start()),
                    "excerpt": _excerpt_for_match(source_text, match),
                }
                for match in matches[:20]
            ],
        }
        rule_checks.append(check)
        if len(matches) == 0:
            warnings.append(f"line {lineno}: pattern matched 0 locations in target source")
        if broad:
            warnings.append(f"line {lineno}: broad rule pattern; narrow it to project-specific context before autonomous use")
        if duplicate:
            warnings.append(f"line {lineno}: possible duplicate with default Universal Mutator operator rules")
        rule_count += 1
    if rule_count == 0:
        errors.append("no rule lines found")
    if language is None:
        warnings.append("target language could not be inferred from extension")
    valid = not errors
    auto_usable = valid and bool(rule_checks) and all(check["match_count"] > 0 and not check["broad"] for check in rule_checks)
    dry_run_result = {"attempted": False}
    if dry_run_mutants and valid and relative_target and language:
        dry_run_result = _dry_run_custom_rules(root, relative_target, language, rules_path, command_runner=command_runner)
    return {
        "valid": valid,
        "target": relative_target,
        "language": language,
        "rules": rules_path.relative_to(root).as_posix() if _path_is_under(rules_path, root) else str(rules_path),
        "rule_count": rule_count,
        "rule_checks": rule_checks,
        "auto_usable": auto_usable,
        "dry_run_mutants": dry_run_result,
        "errors": errors,
        "warnings": warnings,
    }


def _count_lines(path):
    if path is None:
        return 0
    text = _safe_read_text(path).splitlines()
    return len([line for line in text if line.strip()])


def _read_entries(path, limit=20):
    if path is None:
        return []
    entries = [line.strip() for line in _safe_read_text(path).splitlines() if line.strip()]
    return entries[:limit]


def _log_hints(stdout_path, stderr_path):
    hints = []
    combined = ""
    for path in (stdout_path, stderr_path):
        if path and path.exists():
            combined += "\n" + _safe_read_text(path)
    if "HAD TO TERMINATE ANALYSIS" in combined:
        hints.append("timeout marker detected in stdout/stderr")
    if "Traceback" in combined:
        hints.append("python traceback detected in stdout/stderr")
    if re.search(r"\b(error|exception|failed)\b", combined, re.IGNORECASE):
        hints.append("error marker detected in stdout/stderr")
    return hints


def _infer_mutant_dir(prefix, mutant_dirs):
    if prefix == "default":
        for path in mutant_dirs:
            if Path(path).name == "mutants":
                return path
        return mutant_dirs[0] if mutant_dirs else None
    normalized_prefix = prefix.replace("_", "-").lower()
    for path in mutant_dirs:
        name = Path(path).name.lower()
        if normalized_prefix == name or normalized_prefix in name:
            return path
    return None


def collect_artifacts(root):
    root = Path(root).resolve()
    runs = {}
    mutant_dirs = []
    manifests = {}

    for path in root.rglob("*"):
        if _is_in_skipped_dir(path, root):
            continue
        if path.is_dir() and (path.name.startswith("mutants") or "mutants" in path.relative_to(root).parts):
            mutant_dirs.append(_relative(path, root))
            continue
        if not path.is_file():
            continue
        relative_path = _relative(path, root)
        if path.name in {"manifest.json", "plan.json"}:
            try:
                manifest = json.loads(_safe_read_text(path))
            except json.JSONDecodeError:
                manifest = None
            if manifest and (manifest.get("schema_version") == 1 or path.name == "manifest.json"):
                prefix = manifest.get("prefix") or _safe_target_slug(manifest.get("target") or path.parent.name)
                if path.name == "plan.json" and "mutation" not in manifest and "commands" in manifest:
                    continue
                manifests[prefix] = manifest
                run = runs.setdefault(prefix, {"prefix": prefix})
                run["manifest_file"] = relative_path
                run["target"] = manifest.get("target")
                run["language"] = manifest.get("language")
                run["mutant_dir"] = manifest.get("mutant_dir") or _relative(path.parent, root)
            continue
        match = RESULT_RE.match(path.name)
        if match:
            prefix = match.group("prefix") or "default"
            run = runs.setdefault(prefix, {"prefix": prefix})
            kind = match.group("kind").replace("-", "")
            if kind == "killed":
                run["killed_file"] = relative_path
            elif kind == "notkilled":
                run["notkilled_file"] = relative_path
                run["notkilled_kind"] = "notkilled"
            else:
                normalized = {"compileerror": "compile_error", "compile_error": "compile_error", "presumedequivalent": "presumed_equivalent"}.get(kind, kind)
                run[normalized + "_file"] = relative_path
            continue
        if path.suffix.lower() in {".out", ".err"}:
            prefix = path.stem
            run = runs.setdefault(prefix, {"prefix": prefix})
            if path.suffix.lower() == ".out":
                run["stdout_log"] = relative_path
            else:
                run["stderr_log"] = relative_path

    for prefix, run in runs.items():
        killed_path = root / run["killed_file"] if "killed_file" in run else None
        notkilled_path = root / run["notkilled_file"] if "notkilled_file" in run else None
        stdout_path = root / run["stdout_log"] if "stdout_log" in run else None
        stderr_path = root / run["stderr_log"] if "stderr_log" in run else None

        killed_count = _count_lines(killed_path)
        survived_count = _count_lines(notkilled_path)
        total = killed_count + survived_count
        run["killed_count"] = killed_count
        run["survived_count"] = survived_count
        run["mutation_score"] = (killed_count / total) if total else None
        run["score_formula"] = "killed / (killed + survived); other outcomes excluded"
        for kind in ("timeout", "compile_error", "invalid", "flaky", "skipped", "equivalent", "presumed_equivalent"):
            if kind + "_file" in run:
                count = _count_lines(root / run[kind + "_file"])
                run[kind + "_count"] = count
                total += count
        run["total_mutants"] = total
        if not run.get("mutant_dir"):
            parent_dir = None
            for key in ("notkilled_file", "killed_file"):
                if key in run and "mutants" in Path(run[key]).parts:
                    parent_dir = Path(run[key]).parent.as_posix()
                    break
            run["mutant_dir"] = parent_dir or _infer_mutant_dir(prefix, mutant_dirs)
        run["survivors"] = _read_entries(notkilled_path)
        run["log_hints"] = _log_hints(stdout_path, stderr_path)
        if prefix in manifests:
            run["manifest"] = manifests[prefix]

    return {
        "root": str(root),
        "mutant_dirs": sorted(mutant_dirs),
        "runs": dict(sorted(runs.items())),
    }


def _command_found(capabilities, command_name, default=True):
    if capabilities is None:
        return None
    command_info = capabilities.get("commands", {}).get(command_name)
    if command_info is None:
        if command_name == "prioritize_mutants":
            return bool(capabilities.get("post_processing_commands", {}).get(command_name, default))
        return default
    return bool(command_info.get("found"))


def _flag_supported(capabilities, group_name, flag):
    if capabilities is None:
        return None
    return bool(capabilities.get(group_name, {}).get(flag))


def _format_next_command_templates(notkilled_file, mutant_dir, source_dir):
    source_arg = source_dir or "<source_dir>"
    suffix = "(verify flags with scripts/detect_um_capabilities.py first)"
    return [
        f"- Template: {shell_join(['show_mutants', notkilled_file, '--mutantDir', mutant_dir, '--sourceDir', source_arg, '--concise'])} {suffix}",
        f"- Template: {shell_join(['prioritize_mutants', notkilled_file, 'prioritized.txt', '20', '--mutantDir', mutant_dir, '--sourceDir', source_arg])} {suffix}",
    ]


def _format_next_commands(notkilled_file, mutant_dir, source_dir, capabilities):
    if capabilities is None:
        return _format_next_command_templates(notkilled_file, mutant_dir, source_dir)

    lines = []
    source_requested = bool(source_dir)
    unsupported_source_dir = False

    if _command_found(capabilities, "show_mutants"):
        show_parts = ["show_mutants", notkilled_file]
        if _flag_supported(capabilities, "show_flags", "--mutantDir"):
            show_parts.extend(["--mutantDir", mutant_dir])
        if source_dir and _flag_supported(capabilities, "show_flags", "--sourceDir"):
            show_parts.extend(["--sourceDir", source_dir])
        elif source_requested:
            unsupported_source_dir = True
        if _flag_supported(capabilities, "show_flags", "--concise"):
            show_parts.append("--concise")
        lines.append("- " + shell_join(show_parts))
    else:
        lines.append(
            f"- Template: {shell_join(['show_mutants', notkilled_file, '--mutantDir', mutant_dir])} "
            "(show_mutants was not found; verify/install before use)"
        )

    if _command_found(capabilities, "prioritize_mutants"):
        prioritize_parts = ["prioritize_mutants", notkilled_file, "prioritized.txt", "20"]
        if _flag_supported(capabilities, "prioritize_flags", "--mutantDir"):
            prioritize_parts.extend(["--mutantDir", mutant_dir])
        if source_dir and _flag_supported(capabilities, "prioritize_flags", "--sourceDir"):
            prioritize_parts.extend(["--sourceDir", source_dir])
        elif source_requested:
            unsupported_source_dir = True
        lines.append("- " + shell_join(prioritize_parts))
    else:
        lines.append(
            f"- Template: {shell_join(['prioritize_mutants', notkilled_file, 'prioritized.txt', '20', '--mutantDir', mutant_dir])} "
            "(prioritize_mutants was not found; verify/install before use)"
        )

    if unsupported_source_dir:
        lines.append("- sourceDir was requested but is not supported by detected show_mutants/prioritize_mutants flags.")
    return lines


def _format_scope_lines(scope):
    if not scope:
        return []
    lines = [
        "",
        "Scope:",
        f"- Requested: {scope.get('requested_scope') or 'unknown'}",
        f"- Executed: {scope.get('execution_scope') or 'unknown'}",
        f"- Completeness: {scope.get('completeness') or 'unknown'}",
    ]
    entrypoints = scope.get("entrypoint_targets") or []
    if entrypoints:
        lines.append("- Entrypoints mutated/planned: " + ", ".join(entrypoints))
    shared_files = scope.get("unmutated_shared_dependency_files") or scope.get("shared_dependency_files") or []
    if shared_files:
        lines.append("- Shared dependency files observed but not mutated by default: " + ", ".join(shared_files))
    return lines


def format_single_run_summary(run, target=None, project_type="web3", commands=None, source_dir=None, capabilities=None):
    commands = commands or []
    target = target or run.get("target") or run.get("prefix") or "unknown"
    lines = [
        "Target:",
        str(target),
    ]
    lines.extend(_format_scope_lines(run.get("scope")))
    lines.extend([
        "",
        "Commands:",
    ])
    if commands:
        lines.extend(f"- {command}" for command in commands)
    else:
        lines.append("- Command history not provided.")
    lines.extend(
        [
            "",
            "Results:",
            f"- Total mutants: {run.get('total_mutants', run.get('killed_count', 0) + run.get('survived_count', 0))}",
            f"- Killed: {run.get('killed_count', 0)}",
            f"- Survived: {run.get('survived_count', 0)}",
            f"- Timeout: {run.get('timeout_count', 'unknown')}",
            f"- Compile-error: {run.get('compile_error_count', 'unknown')}",
            f"- Flaky: {run.get('flaky_count', 'unknown')}",
            f"- Non-compiling mutants: {run.get('non_compiling_count', run.get('compile_error_count', 'unknown'))}",
        ]
    )
    if run.get("mutation_score") is not None:
        lines.append(f"- Mutation score: {run['mutation_score']:.3f}")
        lines.append("- Formula: killed / (killed + survived); compile, timeout and other categories excluded.")
    if run.get("mutant_dir"):
        lines.append(f"- Mutant directory: {run['mutant_dir']}")
    if run.get("stdout_log") or run.get("stderr_log"):
        lines.append(
            f"- Logs: stdout={run.get('stdout_log', 'n/a')}, stderr={run.get('stderr_log', 'n/a')}"
        )
    if run.get("log_hints"):
        lines.extend(f"- {hint}" for hint in run["log_hints"])

    lines.extend(["", "Survivors:"])
    survivors = run.get("survivors") or []
    if survivors:
        lines.extend(f"- {survivor}" for survivor in survivors)
    else:
        lines.append("- No surviving mutants were listed in the collected artifacts.")

    lines.extend(["", "Likely gaps:", "- Inspect surviving mutants with show_mutants before labeling them equivalent."])
    if run.get("log_hints"):
        lines.extend(f"- {hint}" for hint in run["log_hints"])
    else:
        lines.append("- No extra timeout or error markers were detected in the collected logs.")

    lines.extend(["", "Recommended tests:", "- Add assertions that directly observe the changed behavior for each surviving mutant."])
    if project_type in {"ton", "blueprint-ton", "acton-ton"}:
        lines.append("- TON-specific review: inspect message, opcode, storage/state, deploy/init, and negative-path coverage.")
    else:
        lines.append("- Add boundary, negative-path, and state-observation tests before rerunning mutation analysis.")

    lines.extend(["", "Next commands:"])
    notkilled_file = run.get("notkilled_file") or "notkilled.txt"
    mutant_dir = run.get("mutant_dir") or "mutants"
    lines.extend(_format_next_commands(notkilled_file, mutant_dir, source_dir, capabilities))
    return "\n".join(lines)


def format_multi_run_summary(report):
    lines = [
        "# Mutation Testing Summary",
        "",
        "## Targets tested",
        "",
        "| Target | Killed | Survived | Mutant dir | Logs | Main finding |",
        "|---|---:|---:|---|---|---|",
    ]
    for prefix, run in report["runs"].items():
        finding = run["log_hints"][0] if run.get("log_hints") else "inspect surviving mutants"
        logs = ", ".join(filter(None, [run.get("stdout_log"), run.get("stderr_log")])) or "n/a"
        lines.append(
            f"| {prefix} | {run.get('killed_count', 0)} | {run.get('survived_count', 0)} | "
            f"{run.get('mutant_dir') or 'n/a'} | {logs} | {finding} |"
        )
    lines.extend(
        [
            "",
            "## Cross-target findings",
            "",
            "- Compare survivors per target before merging them into one backlog.",
            "",
            "## Surviving mutants by priority",
            "",
            "- Use show_mutants and prioritize_mutants per target first.",
            "",
            "## TON-specific findings",
            "",
            "- If any target is TON, check message, opcode, storage/state, deploy/init, and negative-path coverage.",
            "",
            "## Recommended next actions",
            "",
            "- Re-run the highest-value survivors with narrower tests or prioritized subsets.",
        ]
    )
    return "\n".join(lines)
