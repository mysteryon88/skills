from __future__ import annotations

import os
import re
from collections.abc import Callable


PathPredicate = Callable[[str], bool]


def _normalise(path: str) -> str:
    normalised = path.replace("\\", "/")
    return normalised.casefold() if os.name == "nt" else normalised


def _name_is(*names: str) -> PathPredicate:
    approved = {name.casefold() if os.name == "nt" else name for name in names}
    return lambda path: path in approved


def _basename_is(*names: str) -> PathPredicate:
    approved = {name.casefold() for name in names}
    return lambda path: path.rsplit("/", 1)[-1].casefold() in approved


def _matches(pattern: str) -> PathPredicate:
    compiled = re.compile(pattern, re.IGNORECASE)
    return lambda path: compiled.search(path) is not None


def _under(*directories: str) -> PathPredicate:
    prefixes = tuple(
        directory.casefold() if os.name == "nt" else directory for directory in directories
    )
    return lambda path: any(path == prefix[:-1] or path.startswith(prefix) for prefix in prefixes)


def _has_directory_component(*directories: str) -> PathPredicate:
    """Match directory names independent of checkout platform and path case."""
    approved = {directory.casefold() for directory in directories}
    return lambda path: any(
        component.casefold() in approved for component in path.split("/")[:-1]
    )


def _is_env_template(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].casefold()
    return name in {
        ".env.example",
        ".env.sample",
        ".env.template",
        ".env.dist",
        ".env.defaults",
    } or (name.startswith(".env") and name.endswith((".example", ".sample", ".template", ".dist")))


AI_PATHS = (
    _basename_is(
        "AGENTS.md",
        "AGENTS.local.md",
        "CHATGPT.md",
        "CLAUDE.md",
        "CLAUDE.local.md",
        "CODEX.md",
        "COPILOT.md",
        "CODY.md",
        "GEMINI.md",
        "GEMINI.local.md",
        ".clinerules",
        ".cursorrules",
        ".roorules",
        ".roomodes",
        ".windsurfrules",
    ),
    _has_directory_component(
        ".agents",
        ".amazonq",
        ".anthropic",
        ".chatgpt",
        ".claude",
        ".cline",
        ".codeium",
        ".codex",
        ".continue",
        ".copilot",
        ".cody",
        ".cursor",
        ".gemini",
        ".kiro",
        ".openai",
        ".qodo",
        ".roo",
        ".roocode",
        ".sourcegraph",
        ".tabnine",
        ".windsurf",
    ),
    _matches(r"(?:^|/)agents/openai\.yaml$"),
    _matches(r"(?:^|/)\.github/(?:agents|chatmodes|instructions|prompts)/"),
    _matches(r"(?:^|/)\.github/copilot-instructions\.md$"),
    _matches(r"(?:^|/)(?:\.mcp|mcp)\.json$"),
    _matches(r"(?:^|/)[^/]+\.(?:agent|chatmode|instructions|prompt)\.md$"),
    _matches(r"(?:^|/)\.aider[^/]*$"),
    _matches(
        r"(?:^|/)(?:chat|session|prompt)(?:[-_](?:session|prompt))?"
        r"[-_](?:dump|history|transcript)[^/]*$"
    ),
)
BUILD_PATHS = (
    _has_directory_component(
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        ".next",
        ".gradle",
        "dist",
        "build",
        "target",
    ),
)
ENVIRONMENT_PATH = _matches(r"(?:^|/)\.env(?:\.[^/]+)?$")
SENSITIVE_PATH = _matches(
    r"(?:^|/)(?:\.npmrc|\.pypirc|\.netrc|_netrc|\.htpasswd|\.envrc|\.dev\.vars|"
    r"\.git-credentials|\.sentryclirc|\.terraformrc|terraform\.rc|auth\.json|"
    r"credentials(?:\.(?:json|toml))?|secrets\.(?:json|ya?ml)|kubeconfig|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)|application_default_credentials\.json)$|"
    r"(?:^|/)(?:\.aws/credentials|\.azure/accessTokens\.json|\.docker/config\.json|"
    r"\.kube/config|\.config/gcloud/application_default_credentials\.json|"
    r"\.config/gh/hosts\.yml|\.config/glab-cli/config\.yml|"
    r"\.cargo/credentials\.toml|\.gem/credentials)$|"
    r"(?:^|/)(?:service[-_]?account|firebase-adminsdk)[^/]*\.json$|"
    r"\.(?:key|p12|pfx|jks|keystore|kdbx|ovpn|mobileprovision|tfstate|"
    r"tfstate\.backup|tfvars|tfvars\.json)$"
)
REVIEW_ARTIFACT_PATH = _matches(
    r"\.(?:pem|sql|dump|sqlite|sqlite3|db|bak|orig|rej|zip|7z|rar|tar|tgz|gz)$"
)
ABSOLUTE_LOCAL_PATH = _matches(r"^(?:/|[A-Za-z]:/|//)")


def _candidate(
    *,
    kind: str,
    severity: str,
    action: str,
    path: str,
    evidence: str,
    recommendation: str,
) -> dict[str, object]:
    return {
        "kind": kind,
        "severity": severity,
        "action": action,
        "path": path,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def _state_action(state: str, tracked_action: str) -> str | None:
    if state == "ignored":
        return None
    if state == "history":
        return "purge"
    return tracked_action if state == "tracked" else "ignore"


def classify_path(path: str, state: str) -> list[dict[str, object]]:
    """Return publication-risk candidates for one slash-normalized repository path."""
    normalised = _normalise(path)
    if state == "missing":
        name = normalised.rsplit("/", 1)[-1].casefold()
        if name in {"readme.md", "readme", "readme.rst", "readme.txt"}:
            return [
                _candidate(
                    kind="readme",
                    severity="WARNING",
                    action="document",
                    path=path,
                    evidence="README evidence is missing",
                    recommendation="Add a README that explains the repository before publication.",
                )
            ]
        if name in {"license", "license.md", "license.txt", "copying", "copying.md", "copying.txt"}:
            return [
                _candidate(
                    kind="license",
                    severity="WARNING",
                    action="review",
                    path=path,
                    evidence="license evidence is missing",
                    recommendation="Add an explicit license before publication.",
                )
            ]
        return []
    if state == "conflicting-lockfile":
        return [
            _candidate(
                kind="lockfile",
                severity="WARNING",
                action="review",
                path=path,
                evidence="conflicting dependency lockfile",
                recommendation="Keep one authoritative lockfile for the package manager in use.",
            )
        ]
    if any(predicate(normalised) for predicate in AI_PATHS):
        if state == "ignored":
            return []
        if state == "history":
            return [
                _candidate(
                    kind="ai-file",
                    severity="BLOCKER",
                    action="purge",
                    path=path,
                    evidence="AI instruction, state, prompt, or transcript artifact remains in reachable history",
                    recommendation="Remove it from every public ref unless a narrow explicit allowlist justifies it.",
                )
            ]
        action = _state_action(state, "review")
        if action is None:
            return []
        return [
            _candidate(
                kind="ai-file",
                severity="BLOCKER" if state == "tracked" else "WARNING",
                action=action,
                path=path,
                evidence=f"{state} AI instruction, state, prompt, or transcript artifact",
                recommendation=(
                    "Delete it, or keep it local and remove it from the Git index with "
                    "portable ignore coverage."
                ),
            )
        ]
    if ENVIRONMENT_PATH(normalised) and not _is_env_template(normalised):
        action = _state_action(state, "review")
        if action is None:
            return []
        return [
            _candidate(
                kind="environment-file",
                severity="BLOCKER",
                action=action,
                path=path,
                evidence=f"{state} environment file",
                recommendation="Review it without disclosure and keep environment files out of every publishable Git surface.",
            )
        ]
    if SENSITIVE_PATH(normalised):
        action = _state_action(state, "review")
        if action is None:
            return []
        return [
            _candidate(
                kind="sensitive-file",
                severity="BLOCKER" if state in {"tracked", "history"} else "WARNING",
                action=action,
                path=path,
                evidence=f"{state} path commonly contains credentials, private keys, local state, or authentication data",
                recommendation="Inspect without disclosure and remove it from all publishable Git surfaces unless explicitly proven safe.",
            )
        ]
    if REVIEW_ARTIFACT_PATH(normalised):
        action = _state_action(state, "review")
        if action is None:
            return []
        return [
            _candidate(
                kind="archive-backup-or-dump",
                severity="WARNING",
                action=action,
                path=path,
                evidence=f"{state} archive, backup, dump, database, or certificate-like artifact",
                recommendation="Review its publication intent and contents; purge historical copies when they contain private data.",
            )
        ]
    if any(predicate(normalised) for predicate in BUILD_PATHS):
        action = _state_action(state, "ignore")
        if action is None:
            return []
        recommendation = "Add matching ignore coverage."
        if state == "tracked":
            recommendation = "Remove it from the Git index and add matching ignore coverage."
        elif state == "history":
            recommendation = "Review whether generated output must be purged from public history."
        return [
            _candidate(
                kind="build-output",
                severity="WARNING",
                action=action,
                path=path,
                evidence=f"{state} generated build output or cache",
                recommendation=recommendation,
            )
        ]
    if ABSOLUTE_LOCAL_PATH(normalised):
        action = _state_action(state, "review")
        if action is None:
            return []
        return [
            _candidate(
                kind="local-dependency-path",
                severity="WARNING",
                action=action,
                path=path,
                evidence="absolute local dependency path",
                recommendation="Replace it with a portable dependency reference before publication.",
            )
        ]
    return []
