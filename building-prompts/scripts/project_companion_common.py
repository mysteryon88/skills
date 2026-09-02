from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if sys.version_info < (3, 11):  # pragma: no cover - exercised with a version-gate subprocess
    raise RuntimeError("building-prompts project companion scripts require Python 3.11 or newer")

import tomllib

SCHEMA_VERSION = 3
SUPPORTED_OWNED_SCHEMA_VERSIONS = {1, 2, SCHEMA_VERSION}
SKILL_SUFFIX = "-project-context"
GENERATED_BY = "building-prompts/bootstrap_project_companion.py"

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
}

ROOT_SIGNAL_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "CONTRIBUTING.md",
    "README.md",
    "README.rst",
    "README.txt",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "go.work",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "composer.json",
    "Gemfile",
    "mix.exs",
    "Package.swift",
    "pubspec.yaml",
    "CMakeLists.txt",
    "Makefile",
    "justfile",
    "Taskfile.yml",
    "Taskfile.yaml",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "pnpm-workspace.yaml",
    "turbo.json",
    "nx.json",
    "lerna.json",
    "rush.json",
    "workspace.json",
    "deno.json",
    "deno.jsonc",
    "bun.lock",
    "bun.lockb",
]

INSTRUCTION_NAMES = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", "CONTRIBUTING.md"}
WORKSPACE_NAMES = {
    "pnpm-workspace.yaml",
    "turbo.json",
    "nx.json",
    "lerna.json",
    "rush.json",
    "workspace.json",
    "go.work",
}
SENSITIVE_NAME_PATTERNS = [
    re.compile(r"^\.env(?:\..+)?$", re.IGNORECASE),
    re.compile(r".*\.(?:pem|key|p12|pfx)$", re.IGNORECASE),
    re.compile(r"^(?:id_rsa|id_ed25519)$", re.IGNORECASE),
    re.compile(
        r".*(?:^|[._-])(?:credential|credentials|secret|secrets|token|tokens)(?:[._-]|$).*",
        re.IGNORECASE,
    ),
]


@dataclass(frozen=True)
class GitInfo:
    branch: str
    commit: str
    remote: str


@dataclass(frozen=True)
class DiscoveryResult:
    paths: list[Path]
    files_examined: int
    errors: list[str]

    def manifest_record(self) -> dict[str, Any]:
        return {
            "max_depth": None,
            "file_limit": None,
            "truncated": False,
            "files_examined": self.files_examined,
            "errors": self.errors,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_git(project_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def get_git_info(project_root: Path) -> GitInfo:
    branch = run_git(project_root, "branch", "--show-current") or "not available"
    commit = run_git(project_root, "rev-parse", "HEAD") or "not available"
    remote = run_git(project_root, "remote", "get-url", "origin") or "not available"
    return GitInfo(branch=branch, commit=commit, remote=remote)


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def read_toml(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        return {}
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def clean_display_name(value: str) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.replace(":", " -").replace("#", " number ")
    value = re.sub(r"\s+", " ", value).strip()
    return value[:120] or "Project"


CYRILLIC_TRANSLITERATION = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya",
    }
)


def slugify(value: str, max_length: int = 48) -> str:
    original = value.strip()
    value = original.lower().translate(CYRILLIC_TRANSLITERATION)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.replace("@", "")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    if not value:
        digest = hashlib.sha256(original.encode("utf-8", errors="ignore")).hexdigest()[:8]
        value = f"project-{digest}"
    value = value[:max_length].rstrip("-")
    return value or "project"


def name_from_git_remote(remote: str) -> str:
    if not remote or remote == "not available":
        return ""
    tail = remote.rstrip("/").rsplit("/", 1)[-1]
    if ":" in tail and "/" not in tail:
        tail = tail.rsplit(":", 1)[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    return tail


def detect_project_name(project_root: Path, explicit_name: str | None = None) -> str:
    if explicit_name:
        return clean_display_name(explicit_name)

    package = read_json(project_root / "package.json")
    if isinstance(package.get("name"), str) and package["name"].strip():
        return clean_display_name(package["name"])

    pyproject = read_toml(project_root / "pyproject.toml")
    project_table = pyproject.get("project") if isinstance(pyproject.get("project"), dict) else {}
    poetry_table = (
        pyproject.get("tool", {}).get("poetry", {})
        if isinstance(pyproject.get("tool"), dict)
        and isinstance(pyproject.get("tool", {}).get("poetry"), dict)
        else {}
    )
    for table in (project_table, poetry_table):
        if isinstance(table.get("name"), str) and table["name"].strip():
            return clean_display_name(table["name"])

    cargo = read_toml(project_root / "Cargo.toml")
    cargo_package = cargo.get("package") if isinstance(cargo.get("package"), dict) else {}
    if isinstance(cargo_package.get("name"), str) and cargo_package["name"].strip():
        return clean_display_name(cargo_package["name"])

    go_mod = project_root / "go.mod"
    if go_mod.is_file() and not go_mod.is_symlink():
        try:
            first = go_mod.read_text(encoding="utf-8").splitlines()[0].strip()
        except (OSError, UnicodeDecodeError, IndexError):
            first = ""
        if first.startswith("module "):
            return clean_display_name(first.removeprefix("module ").rstrip("/").rsplit("/", 1)[-1])

    composer = read_json(project_root / "composer.json")
    if isinstance(composer.get("name"), str) and composer["name"].strip():
        return clean_display_name(composer["name"].rsplit("/", 1)[-1])

    git_name = name_from_git_remote(get_git_info(project_root).remote)
    if git_name:
        return clean_display_name(git_name)

    return clean_display_name(project_root.name)


def choose_skills_dir(project_root: Path, explicit: str | None = None) -> Path:
    if explicit:
        supplied = Path(explicit).expanduser()
        return supplied.resolve() if supplied.is_absolute() else (project_root / supplied).resolve()

    for relative in (Path(".agents/skills"), Path(".claude/skills")):
        candidate = project_root / relative
        if candidate.is_dir():
            return candidate.resolve()
    return (project_root / ".agents/skills").resolve()


def relative_posix(path: Path, root: Path) -> str:
    return Path(os.path.relpath(path, root)).as_posix()


def iter_project_files(project_root: Path, max_depth: int | None = 5) -> Iterable[Path]:
    root_parts = len(project_root.resolve().parts)
    for current_root, dirs, files in os.walk(project_root):
        current = Path(current_root)
        depth = len(current.resolve().parts) - root_parts
        dirs[:] = [
            name
            for name in dirs
            if name not in IGNORED_DIRS
            and not name.startswith(".tox")
            and (max_depth is None or depth < max_depth)
        ]
        for name in files:
            path = current / name
            if path.is_symlink():
                continue
            yield path


def _is_high_signal(path: Path, project_root: Path) -> bool:
    relative = Path(relative_posix(path, project_root))
    parts = relative.parts
    if path.name in ROOT_SIGNAL_FILES or path.name in INSTRUCTION_NAMES:
        return True
    if relative.as_posix() == ".github/copilot-instructions.md":
        return True
    if path.suffix.lower() in {".sln", ".csproj"}:
        return True
    return (
        len(parts) >= 3
        and parts[-3:-1] == (".github", "workflows")
        and path.suffix.lower() in {".yml", ".yaml"}
    )


def scan_high_signal_files(project_root: Path) -> DiscoveryResult:
    found: set[Path] = set()
    errors: list[str] = []
    files_examined = 0

    def record_walk_error(error: OSError) -> None:
        filename = str(error.filename or project_root)
        try:
            relative = relative_posix(Path(filename), project_root)
        except ValueError:
            relative = filename
        errors.append(f"{relative}: {error.strerror or type(error).__name__}")

    for current_root, dirs, files in os.walk(project_root, onerror=record_walk_error):
        current = Path(current_root)
        dirs[:] = [
            name
            for name in dirs
            if name not in IGNORED_DIRS and not name.startswith(".tox")
        ]
        for name in files:
            files_examined += 1
            path = current / name
            if path.is_symlink():
                continue
            if _is_high_signal(path, project_root):
                found.add(path)

    paths = sorted(found, key=lambda item: relative_posix(item, project_root))
    return DiscoveryResult(paths=paths, files_examined=files_examined, errors=sorted(set(errors)))


def collect_instruction_files(project_root: Path) -> list[Path]:
    result: list[Path] = []
    for path in scan_high_signal_files(project_root).paths:
        relative = relative_posix(path, project_root)
        if (
            path.name in INSTRUCTION_NAMES
            or relative == ".github/copilot-instructions.md"
            or (path.parent == project_root and path.name in {"README.md", "README.rst", "README.txt"})
        ):
            result.append(path)
    return result


def collect_high_signal_files(project_root: Path) -> list[Path]:
    return scan_high_signal_files(project_root).paths


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_files(
    paths: Iterable[Path],
    project_root: Path,
    *,
    errors: list[str] | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in paths:
        if path.is_symlink():
            continue
        try:
            stat = path.stat()
            digest = sha256_file(path)
        except OSError as exc:
            if errors is not None:
                relative = relative_posix(path, project_root)
                errors.append(f"{relative}: {exc.strerror or str(exc) or type(exc).__name__}")
            continue
        result.append(
            {
                "path": relative_posix(path, project_root),
                "sha256": digest,
                "size": stat.st_size,
            }
        )
    return result


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def inventory_sha256(inventory: dict[str, Any]) -> str:
    stable = {
        key: inventory[key]
        for key in (
            "instructions",
            "high_signal",
            "fingerprints",
            "stack",
            "top_level",
            "workspace",
            "commands",
            "excluded",
            "sensitive",
        )
        if key in inventory
    }
    return canonical_sha256(stable)


def package_version() -> str:
    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        value = version_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return value or "unknown"


def detect_stack_signals(project_root: Path) -> list[str]:
    signals: list[str] = []
    checks = [
        ("package.json", "JavaScript/TypeScript package manifest"),
        ("pyproject.toml", "Python project manifest"),
        ("requirements.txt", "Python requirements"),
        ("Cargo.toml", "Rust Cargo manifest"),
        ("go.mod", "Go module"),
        ("pom.xml", "Java/Kotlin Maven project"),
        ("build.gradle", "Gradle project"),
        ("build.gradle.kts", "Gradle Kotlin project"),
        ("composer.json", "PHP Composer project"),
        ("Gemfile", "Ruby Bundler project"),
        ("mix.exs", "Elixir Mix project"),
        ("Package.swift", "Swift package"),
        ("pubspec.yaml", "Dart/Flutter project"),
        ("CMakeLists.txt", "C/C++ CMake project"),
        ("Dockerfile", "Docker build"),
        ("terraform", "Terraform directory"),
        ("Chart.yaml", "Helm chart"),
    ]
    for name, label in checks:
        if (project_root / name).exists():
            signals.append(label)

    package = read_json(project_root / "package.json")
    dependencies: dict[str, Any] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        table = package.get(key)
        if isinstance(table, dict):
            dependencies.update(table)
    framework_map = {
        "next": "Next.js",
        "react": "React",
        "vue": "Vue",
        "@angular/core": "Angular",
        "svelte": "Svelte",
        "vite": "Vite",
        "electron": "Electron",
        "nestjs": "NestJS",
        "@nestjs/core": "NestJS",
    }
    for dependency, label in framework_map.items():
        if dependency in dependencies and label not in signals:
            signals.append(label)

    if not signals:
        signals.append("No standard stack manifest detected at repository root")
    return signals


def collect_top_level_entries(project_root: Path) -> list[str]:
    entries: list[str] = []
    try:
        children = sorted(project_root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError:
        return entries
    for child in children:
        if child.name in IGNORED_DIRS or child.name in {".agents", ".claude"}:
            continue
        kind = "directory" if child.is_dir() else "file"
        entries.append(f"{child.name} ({kind})")
        if len(entries) >= 60:
            break
    return entries


def detect_workspace_signals(project_root: Path) -> list[str]:
    result: list[str] = []
    for name in sorted(WORKSPACE_NAMES):
        if (project_root / name).is_file():
            result.append(name)

    package = read_json(project_root / "package.json")
    if "workspaces" in package:
        result.append("package.json#workspaces")

    cargo = read_toml(project_root / "Cargo.toml")
    if isinstance(cargo.get("workspace"), dict):
        result.append("Cargo.toml#[workspace]")

    pyproject = read_toml(project_root / "pyproject.toml")
    tool = pyproject.get("tool") if isinstance(pyproject.get("tool"), dict) else {}
    uv = tool.get("uv") if isinstance(tool, dict) and isinstance(tool.get("uv"), dict) else {}
    if isinstance(uv, dict) and "workspace" in uv:
        result.append("pyproject.toml#tool.uv.workspace")

    return sorted(set(result)) or ["No explicit root workspace signal detected"]


def detect_explicit_commands(project_root: Path) -> list[str]:
    commands: list[str] = []

    package = read_json(project_root / "package.json")
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    package_manager = str(package.get("packageManager", "")).split("@", 1)[0]
    if not package_manager:
        if (project_root / "pnpm-lock.yaml").is_file():
            package_manager = "pnpm"
        elif (project_root / "yarn.lock").is_file():
            package_manager = "yarn"
        elif (project_root / "bun.lock").is_file() or (project_root / "bun.lockb").is_file():
            package_manager = "bun"
        else:
            package_manager = "npm"
    for name, value in sorted(scripts.items()):
        if not isinstance(value, str):
            continue
        if package_manager == "npm":
            invocation = f"npm run {name}"
        elif package_manager == "yarn":
            invocation = f"yarn {name}"
        else:
            invocation = f"{package_manager} {name}"
        commands.append(f"{markdown_code_span(invocation)} declared in {markdown_code_span(f'package.json#scripts.{name}')}")

    pyproject = read_toml(project_root / "pyproject.toml")
    project_table = pyproject.get("project") if isinstance(pyproject.get("project"), dict) else {}
    project_scripts = project_table.get("scripts") if isinstance(project_table.get("scripts"), dict) else {}
    for name, value in sorted(project_scripts.items()):
        if isinstance(value, str):
            commands.append(f"CLI entry point {markdown_code_span(name)} declared in {markdown_code_span('pyproject.toml#project.scripts')}")

    composer = read_json(project_root / "composer.json")
    composer_scripts = composer.get("scripts") if isinstance(composer.get("scripts"), dict) else {}
    for name, value in sorted(composer_scripts.items()):
        commands.append(f"{markdown_code_span(f'composer run-script {name}')} declared in {markdown_code_span(f'composer.json#scripts.{name}')}")

    for filename, prefix in (("Makefile", "make"), ("justfile", "just")):
        path = project_root / filename
        if not path.is_file() or path.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        pattern = r"^([A-Za-z0-9][A-Za-z0-9_.-]*):(?:\s|$)" if filename == "Makefile" else r"^([A-Za-z0-9][A-Za-z0-9_-]*):(?:\s|$)"
        seen: set[str] = set()
        for match in re.finditer(pattern, text, flags=re.MULTILINE):
            target = match.group(1)
            if target in seen:
                continue
            seen.add(target)
            commands.append(f"{markdown_code_span(f'{prefix} {target}')} from {markdown_code_span(filename)}")
            if len(seen) >= 30:
                break

    return commands or ["No explicit executable command was discovered by bootstrap"]


def detect_excluded_areas(project_root: Path) -> list[str]:
    names = {
        "node_modules",
        "vendor",
        "dist",
        "build",
        "target",
        "coverage",
        ".venv",
        "venv",
        "generated",
        "gen",
        "out",
    }
    result = [name for name in sorted(names) if (project_root / name).exists()]
    return result or ["No common generated, vendored, or dependency directory detected at repository root"]


def detect_sensitive_file_signals(project_root: Path) -> list[str]:
    result: list[str] = []
    for path in iter_project_files(project_root, max_depth=3):
        if any(pattern.match(path.name) for pattern in SENSITIVE_NAME_PATTERNS):
            result.append(relative_posix(path, project_root))
            if len(result) >= 40:
                break
    return sorted(set(result)) or ["No common sensitive filename signal detected within bootstrap scan depth"]


def single_line(value: str, max_length: int = 400) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_length]


def markdown_code_span(value: str) -> str:
    value = single_line(value)
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * (longest + 1)
    padding = " " if value.startswith("`") or value.endswith("`") else ""
    return f"{fence}{padding}{value}{padding}{fence}"


def bullet_list(items: Iterable[str], code: bool = False) -> str:
    values = list(items)
    if not values:
        return "- None detected"
    if code:
        return "\n".join(f"- {markdown_code_span(value)}" for value in values)
    return "\n".join(f"- {single_line(value)}" for value in values)


def compact_summary(items: Iterable[str], limit: int = 8) -> str:
    values = list(items)
    if not values:
        return "none detected"
    shown = [single_line(value, max_length=160) for value in values[:limit]]
    suffix = f"; plus {len(values) - limit} more" if len(values) > limit else ""
    return "; ".join(shown) + suffix


def safe_description(project_name: str) -> str:
    short_name = clean_display_name(project_name)[:80]
    description = (
        "Use when preparing, reviewing, or executing development-agent work inside the "
        f"{short_name} repository and project-specific architecture, commands, constraints, or verification paths may affect the result."
    )
    return description[:490].rstrip(" .") + "."
