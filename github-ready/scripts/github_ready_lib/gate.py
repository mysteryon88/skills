from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import posixpath
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

from .git_repo import GitCommandError, GitRepository
from .model import coverage_gap
from .scanner import (
    SECRET_DETECTORS,
    _redact_result,
    masked_fingerprint,
    scan_secret_candidates,
)


GATE_VERSION = 1
_ALLOW_AI_FILE = ".github-ready-allow-ai"
_REVIEWED_FINDINGS_FILE = ".github-ready-reviewed-findings.json"
_ENV_TEMPLATE_NAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    ".env.defaults",
}

# These are local assistant state/instruction artefacts, not ordinary source files.
_AI_BASENAMES = {
    "agents.md",
    "agents.local.md",
    "chatgpt.md",
    "claude.md",
    "claude.local.md",
    "codex.md",
    "copilot.md",
    "cody.md",
    "gemini.md",
    "gemini.local.md",
    ".aider.chat.history.md",
    ".aider.input.history",
    ".clinerules",
    ".cursorrules",
    ".roorules",
    ".roomodes",
    ".windsurfrules",
    ".mcp.json",
    "mcp.json",
}
_AI_DIRECTORY_NAMES = {
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
}
_AI_EXACT_PATHS = {
    ".github/copilot-instructions.md",
    "agents/openai.yaml",
}
_AI_PREFIXES = (
    ".github/agents/",
    ".github/chatmodes/",
    ".github/instructions/",
    ".github/prompts/",
)
_AI_MARKDOWN_RE = re.compile(
    r"(?:^|/)[^/]+\.(?:agent|chatmode|instructions|prompt)\.md$",
    re.IGNORECASE,
)
_AI_DUMP_RE = re.compile(
    r"(?:^|/)(?:chat|session|prompt)(?:[-_](?:session|prompt))?"
    r"[-_](?:dump|history|transcript)[^/]*$",
    re.IGNORECASE,
)

_SENSITIVE_EXACT = {
    ".env",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "_netrc",
    ".htpasswd",
    ".envrc",
    ".dev.vars",
    ".dockercfg",
    ".git-credentials",
    ".sentryclirc",
    ".terraformrc",
    "terraform.rc",
    "auth.json",
    "credentials",
    "credentials.toml",
    "credentials.json",
    "application_default_credentials.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "kubeconfig",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
_SENSITIVE_PATH_SUFFIXES = (
    "/.aws/credentials",
    "/.azure/accesstokens.json",
    "/.config/gcloud/application_default_credentials.json",
    "/.docker/config.json",
    "/.kube/config",
    "/.config/gh/hosts.yml",
    "/.config/glab-cli/config.yml",
    "/.cargo/credentials.toml",
    "/.gem/credentials",
)
_PRIVATE_KEY_SUFFIXES = (
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".kdbx",
    ".ovpn",
    ".mobileprovision",
)
_REVIEW_CERTIFICATE_SUFFIXES = (
    ".pem",
    ".crt",
    ".cer",
    ".der",
    ".p7b",
    ".p7c",
)
_STATE_SUFFIXES = (
    ".tfstate",
    ".tfstate.backup",
)
_REVIEW_SUFFIXES = (
    ".sql",
    ".dump",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".bak",
    ".orig",
    ".rej",
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".tgz",
    ".gz",
)
_OS_AND_TEMP_BASENAMES = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
    ".coverage",
    "coverage.xml",
    "junit.xml",
}

_GENERIC_IGNORE_PROBES: tuple[tuple[str, str], ...] = (
    ("secrets", ".env"),
    ("secrets", ".env.local"),
    ("secrets", ".npmrc.local"),
    ("ai", ".claude/session.json"),
    ("ai", ".codex/history.json"),
    ("ai", ".cursor/state.json"),
    ("ai", ".aider.chat.history.md"),
    ("os-temp", ".DS_Store"),
    ("os-temp", "debug.log"),
)
_ECOSYSTEM_PROBES: dict[str, tuple[tuple[str, str], ...]] = {
    "python": (
        ("python", "__pycache__/github_ready_probe.pyc"),
        ("python", ".pytest_cache/github-ready"),
        ("python", ".venv/github-ready"),
        ("python", "coverage.xml"),
    ),
    "node": (
        ("node", "node_modules/github-ready/index.js"),
        ("node", ".next/github-ready"),
        ("node", "coverage/github-ready"),
    ),
    "gradle": (
        ("gradle", ".gradle/github-ready"),
        ("gradle", "build/github-ready"),
    ),
    "rust": (("rust", "target/github-ready"),),
    "terraform": (
        ("terraform", ".terraform/github-ready"),
        ("terraform", "terraform.tfstate"),
        ("terraform", "local.auto.tfvars"),
    ),
}

_PROVIDER_SECRET_DETECTORS: tuple[tuple[str, re.Pattern[bytes], int], ...] = (
    (
        "openai-project-key",
        re.compile(rb"\bsk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,}\b"),
        0,
    ),
    ("anthropic-api-key", re.compile(rb"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), 0),
    ("github-fine-grained-token", re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), 0),
    (
        "aws-access-key-id",
        re.compile(rb"\b(?:AKIA|ASIA|AIDA|AROA|AIPA|ANPA|ANVA|ASCA)[A-Z0-9]{16}\b"),
        0,
    ),
    (
        "aws-secret-access-key",
        re.compile(
            rb"(?im)^[ \t]*(?:export[ \t]+)?AWS_SECRET_ACCESS_KEY[ \t]*[:=][ \t]*"
            rb"[\"']?([A-Za-z0-9/+=]{40})[\"']?[ \t]*(?:[#;].*)?$"
        ),
        1,
    ),
    ("google-api-key", re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"), 0),
    ("google-oauth-secret", re.compile(rb"\bGOCSPX-[0-9A-Za-z_-]{20,}\b"), 0),
    ("gitlab-token", re.compile(rb"\bglpat-[0-9A-Za-z_-]{20,}\b"), 0),
    ("npm-token", re.compile(rb"\bnpm_[0-9A-Za-z]{30,}\b"), 0),
    (
        "npm-auth-token",
        re.compile(
            rb"(?im)^[ \t]*(?://[^/\r\n]+/)?_authToken[ \t]*=[ \t]*"
            rb"([^\s#;]{8,})[ \t]*(?:[#;].*)?$"
        ),
        1,
    ),
    ("pypi-token", re.compile(rb"\bpypi-[0-9A-Za-z_-]{40,}\b"), 0),
    ("slack-token", re.compile(rb"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), 0),
    ("sendgrid-api-key", re.compile(rb"\bSG\.[0-9A-Za-z_-]{16,}\.[0-9A-Za-z_-]{16,}\b"), 0),
    ("huggingface-token", re.compile(rb"\bhf_[0-9A-Za-z]{30,}\b"), 0),
    ("linear-api-key", re.compile(rb"\blin_api_[0-9A-Za-z]{20,}\b"), 0),
    ("docker-pat", re.compile(rb"\bdckr_pat_[0-9A-Za-z_-]{20,}\b"), 0),
    ("digitalocean-pat", re.compile(rb"\bdop_v1_[0-9a-fA-F]{64}\b"), 0),
    ("sentry-auth-token", re.compile(rb"\bsntrys_[0-9A-Za-z_-]{20,}\b"), 0),
    ("pulumi-token", re.compile(rb"\bpul-[0-9A-Za-z]{40,}\b"), 0),
    ("terraform-cloud-token", re.compile(rb"\batlasv1\.[0-9A-Za-z_-]{40,}\b"), 0),
    ("datadog-api-key", re.compile(rb"\bddapi_[0-9A-Za-z]{20,}\b"), 0),
    ("twilio-api-key", re.compile(rb"\bSK[0-9a-fA-F]{32}\b"), 0),
    ("new-relic-api-key", re.compile(rb"\bNRAK-[0-9A-Z]{20,}\b"), 0),
    ("postman-api-key", re.compile(rb"\bPMAK-[0-9a-fA-F-]{40,}\b"), 0),
    ("grafana-token", re.compile(rb"\b(?:glc|glsa)_[0-9A-Za-z_+/=-]{20,}\b"), 0),
    ("telegram-bot-token", re.compile(rb"\b[0-9]{8,10}:[0-9A-Za-z_-]{35}\b"), 0),
    ("age-secret-key", re.compile(rb"\bAGE-SECRET-KEY-1[0-9A-Z]{20,}\b"), 0),
    (
        "stripe-secret",
        re.compile(rb"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}\b"),
        0,
    ),
    (
        "database-url-password",
        re.compile(
            rb"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis)://"
            rb"[^\s/:@]+:([^\s/@]{8,})@",
            re.IGNORECASE,
        ),
        1,
    ),
    (
        "url-embedded-password",
        re.compile(
            rb"\b(?:https?|amqps?|ftps?|sftp)://[^\s/:@]+:([^\s/@]{8,})@",
            re.IGNORECASE,
        ),
        1,
    ),
)
_QUOTED_ASSIGNMENT_RE = re.compile(
    rb"(?im)(?:^|[,{\s])['\"]?"
    rb"(?:[A-Za-z0-9]+[_-])*"
    rb"(?:api[_-]?key|auth[_-]?token|access[_-]?token|password|passwd|secret|token)"
    rb"['\"]?\s*[:=]\s*['\"]([^'\"\r\n]{8,})['\"]"
)
_ACTION_USES_RE = re.compile(r"^\s*-?\s*uses\s*:\s*([^\s#]+)", re.IGNORECASE)
_FULL_ACTION_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}(?:\s*#.*)?$")
_WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_WINDOWS_INVALID_COMPONENT_RE = re.compile(r'[<>:"\\|?*\x00-\x1f]')
_SUBMODULE_SECTION_RE = re.compile(
    r'^\s*\[\s*submodule\s+"([^"]+)"\s*\]\s*$',
    re.IGNORECASE,
)
_SUBMODULE_KEY_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9.-]*)\s*=\s*(.*?)\s*$")


@dataclass(frozen=True)
class IndexEntry:
    mode: str
    object_id: str
    stage: int
    path: str


@dataclass(frozen=True)
class IgnoreMatch:
    source: str
    line: int
    pattern: str
    path: str

    @property
    def ignored(self) -> bool:
        return not self.pattern.startswith("!")


def _normalise_path(path: str) -> str:
    return path.replace("\\", "/")


def _basename(path: str) -> str:
    return _normalise_path(path).rsplit("/", 1)[-1].casefold()


def _is_env_template(path: str) -> bool:
    name = _basename(path)
    return name in _ENV_TEMPLATE_NAMES or name.endswith(
        (".example", ".sample", ".template", ".dist")
    ) and name.startswith(".env")


def _is_ai_path(path: str) -> bool:
    normalised = _normalise_path(path)
    folded = normalised.casefold()
    parts = [part.casefold() for part in PurePosixPath(normalised).parts]
    if _basename(normalised) in _AI_BASENAMES:
        return True
    if any(part in _AI_DIRECTORY_NAMES for part in parts[:-1]):
        return True
    if len(parts) >= 2 and parts[-2:] == ["agents", "openai.yaml"]:
        return True
    for index, part in enumerate(parts):
        if part != ".github" or index + 1 >= len(parts):
            continue
        next_part = parts[index + 1]
        if next_part in {"agents", "chatmodes", "instructions", "prompts"}:
            return True
        if next_part == "copilot-instructions.md" and index + 2 == len(parts):
            return True
    if folded in _AI_EXACT_PATHS or folded.startswith(_AI_PREFIXES):
        return True
    if _AI_MARKDOWN_RE.search(normalised) is not None:
        return True
    if re.search(r"(?:^|/)\.aider[^/]*$", folded):
        return True
    return _AI_DUMP_RE.search(normalised) is not None


def _ai_allowlistable_path(path: str) -> bool:
    normalised = _normalise_path(path)
    parts = [part.casefold() for part in PurePosixPath(normalised).parts]
    name = _basename(normalised)
    if any(part in _AI_DIRECTORY_NAMES for part in parts[:-1]):
        return False
    if re.search(r"(?:^|/)\.aider[^/]*$", normalised, re.IGNORECASE):
        return False
    if _AI_DUMP_RE.search(normalised) is not None:
        return False
    if name in {
        "agents.md",
        "agents.local.md",
        "chatgpt.md",
        "claude.md",
        "claude.local.md",
        "codex.md",
        "copilot.md",
        "cody.md",
        "gemini.md",
        "gemini.local.md",
    }:
        return True
    if len(parts) >= 2 and parts[-2:] == ["agents", "openai.yaml"]:
        return True
    for index, part in enumerate(parts):
        if part != ".github" or index + 1 >= len(parts):
            continue
        next_part = parts[index + 1]
        if next_part in {"agents", "chatmodes", "instructions", "prompts"}:
            return True
        if next_part == "copilot-instructions.md" and index + 2 == len(parts):
            return True
    return False


def _ai_allow_pattern_is_narrow(pattern: str) -> bool:
    folded = _normalise_path(pattern).casefold()
    if "**" in folded or folded.count("*") + folded.count("?") > 2:
        return False
    parts = [part for part in PurePosixPath(folded).parts]
    name = parts[-1] if parts else ""
    if name in {
        "agents.md",
        "agents.local.md",
        "chatgpt.md",
        "claude.md",
        "claude.local.md",
        "codex.md",
        "copilot.md",
        "cody.md",
        "gemini.md",
        "gemini.local.md",
    }:
        return True
    if len(parts) >= 2 and parts[-2:] == ["agents", "openai.yaml"]:
        return True
    for index, part in enumerate(parts):
        if part != ".github" or index + 1 >= len(parts):
            continue
        if parts[index + 1] in {"agents", "chatmodes", "instructions", "prompts"}:
            return True
        if parts[index + 1] == "copilot-instructions.md" and index + 2 == len(parts):
            return True
    return False


def _sensitive_path_kind(path: str) -> tuple[str, str] | None:
    normalised = _normalise_path(path)
    folded = normalised.casefold()
    name = _basename(normalised)
    if _is_env_template(normalised):
        return None
    if name in _SENSITIVE_EXACT or any(
        folded == suffix.removeprefix("/") or folded.endswith(suffix)
        for suffix in _SENSITIVE_PATH_SUFFIXES
    ):
        return ("sensitive-file", "BLOCKER")
    if name.startswith(".env."):
        return ("sensitive-file", "BLOCKER")
    if name.startswith(("service-account", "service_account", "firebase-adminsdk")) and name.endswith(
        ".json"
    ):
        return ("sensitive-file", "BLOCKER")
    if name.endswith(_PRIVATE_KEY_SUFFIXES):
        return ("private-key-file", "BLOCKER")
    if name.endswith(_REVIEW_CERTIFICATE_SUFFIXES):
        return ("certificate-or-key-file", "WARNING")
    if name.endswith(_STATE_SUFFIXES) or name.endswith((".tfvars", ".tfvars.json")):
        return ("state-or-variable-file", "BLOCKER")
    if name in _OS_AND_TEMP_BASENAMES or name.endswith(("~", ".swp", ".swo", ".log")):
        return ("local-artifact", "WARNING")
    if name.endswith(_REVIEW_SUFFIXES):
        return ("archive-backup-or-dump", "WARNING")
    return None


def _candidate(
    *,
    kind: str,
    severity: str,
    action: str,
    evidence: str,
    recommendation: str,
    path: str | None = None,
    **extra: object,
) -> dict[str, object]:
    item: dict[str, object] = {
        "kind": kind,
        "severity": severity,
        "action": action,
        "evidence": evidence,
        "recommendation": recommendation,
    }
    if path is not None:
        item["path"] = path
    item.update(extra)
    return item


def _append_gap(
    result: dict[str, object],
    *,
    evidence: str,
    path: str | None = None,
    object_id: str | None = None,
    size: int | None = None,
) -> None:
    coverage = result.setdefault("coverage", {})
    if not isinstance(coverage, dict):
        raise ValueError("coverage must be an object")
    gaps = coverage.setdefault("gaps", [])
    if not isinstance(gaps, list):
        raise ValueError("coverage.gaps must be an array")
    item = coverage_gap(path=path, object_id=object_id, evidence=evidence, size=size)
    if item not in gaps:
        gaps.append(item)
    coverage["complete"] = False


def _parse_index(output: bytes) -> list[IndexEntry]:
    entries: list[IndexEntry] = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        try:
            metadata, raw_path = raw.split(b"\t", 1)
            mode, object_id, stage_text = metadata.split(b" ", 2)
            stage = int(stage_text)
        except (ValueError, UnicodeError) as error:
            raise GitCommandError("Git index metadata was malformed") from error
        entries.append(
            IndexEntry(
                mode=mode.decode("ascii", errors="strict"),
                object_id=object_id.decode("ascii", errors="strict"),
                stage=stage,
                path=raw_path.decode("utf-8", errors="surrogateescape"),
            )
        )
    return entries


def _batch_metadata(
    repository: GitRepository, object_ids: Sequence[str]
) -> dict[str, tuple[str, int]]:
    if not object_ids:
        return {}
    output = repository.run(
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    )
    result: dict[str, tuple[str, int]] = {}
    for raw in output.splitlines():
        parts = raw.decode("ascii", errors="strict").split(" ")
        if len(parts) == 2 and parts[1] == "missing":
            continue
        if len(parts) != 3:
            raise GitCommandError("Git object metadata was malformed")
        object_id, object_type, size_text = parts
        result[object_id] = (object_type, int(size_text))
    return result


def _batch_read(repository: GitRepository, object_ids: Sequence[str]) -> dict[str, bytes]:
    if not object_ids:
        return {}
    output = repository.run(
        "cat-file",
        "--batch",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    )
    contents: dict[str, bytes] = {}
    offset = 0
    for expected_id in object_ids:
        line_end = output.find(b"\n", offset)
        if line_end < 0:
            raise GitCommandError("Git object batch output was truncated")
        header = output[offset:line_end].decode("ascii", errors="strict").split(" ")
        offset = line_end + 1
        if len(header) == 2 and header[1] == "missing":
            continue
        if len(header) != 3:
            raise GitCommandError("Git object batch output was malformed")
        object_id, object_type, size_text = header
        size = int(size_text)
        end = offset + size
        if object_id != expected_id or object_type != "blob" or end >= len(output):
            raise GitCommandError("Git object batch output was malformed")
        if output[end : end + 1] != b"\n":
            raise GitCommandError("Git object batch output was malformed")
        contents[object_id] = output[offset:end]
        offset = end + 1
    return contents


def _batch_read_any(
    repository: GitRepository, object_ids: Sequence[str]
) -> dict[str, tuple[str, bytes]]:
    if not object_ids:
        return {}
    output = repository.run(
        "cat-file",
        "--batch",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    )
    contents: dict[str, tuple[str, bytes]] = {}
    offset = 0
    for expected_id in object_ids:
        line_end = output.find(b"\n", offset)
        if line_end < 0:
            raise GitCommandError("Git object batch output was truncated")
        header = output[offset:line_end].decode("ascii", errors="strict").split(" ")
        offset = line_end + 1
        if len(header) == 2 and header[1] == "missing":
            continue
        if len(header) != 3:
            raise GitCommandError("Git object batch output was malformed")
        object_id, object_type, size_text = header
        size = int(size_text)
        end = offset + size
        if object_id != expected_id or end >= len(output):
            raise GitCommandError("Git object batch output was malformed")
        if output[end : end + 1] != b"\n":
            raise GitCommandError("Git object batch output was malformed")
        contents[object_id] = (object_type, output[offset:end])
        offset = end + 1
    return contents


def _looks_like_placeholder(secret: bytes) -> bool:
    stripped = secret.strip().strip(b"'\"")
    lowered = stripped.lower()
    if not stripped:
        return True
    markers = (
        b"example",
        b"sample",
        b"placeholder",
        b"changeme",
        b"change-me",
        b"your_",
        b"your-",
        b"replace_",
        b"replace-",
        b"dummy",
        b"not-a-real",
        b"redacted",
    )
    if any(marker in lowered for marker in markers):
        return True
    if lowered.startswith((b"${", b"{{", b"<", b"process.env", b"os.environ")):
        return True
    return re.fullmatch(rb"(?:x{8,}|\*{8,}|-{8,}|_{8,})", lowered) is not None


def _placeholder_assignment_keys(data: bytes) -> set[tuple[int, str]]:
    """Return line/fingerprint pairs for obvious placeholders in generic assignments."""
    keys: set[tuple[int, str]] = set()
    for detector, pattern, group in SECRET_DETECTORS:
        if detector != "credential-assignment":
            continue
        for match in pattern.finditer(data):
            secret = match.group(group)
            if not _looks_like_placeholder(secret):
                continue
            keys.add(
                (
                    data.count(b"\n", 0, match.start(group)) + 1,
                    masked_fingerprint(secret),
                )
            )
    return keys


def _scan_base_secrets(
    data: bytes,
    *,
    path: str | None,
    object_id: str,
    source: str,
    budget: GitRepository | None = None,
) -> list[dict[str, object]]:
    candidates = scan_secret_candidates(
        data,
        location={"path": path, "object_id": object_id},
        budget=budget,
    )
    placeholders = (
        _placeholder_assignment_keys(data)
        if path is not None and _is_env_template(path)
        else set()
    )
    result: list[dict[str, object]] = []
    for candidate in candidates:
        if (
            candidate.get("detector") == "credential-assignment"
            and (candidate.get("line"), candidate.get("fingerprint")) in placeholders
        ):
            continue
        item = dict(candidate)
        item["source"] = source
        item["history_only"] = source in {"history", "metadata", "ref"}
        result.append(item)
    return result


def _scan_extra_secrets(
    data: bytes,
    *,
    path: str | None,
    object_id: str,
    source: str,
    budget: GitRepository | None = None,
    **location: object,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen: set[tuple[str, str, int]] = set()
    detectors = (*_PROVIDER_SECRET_DETECTORS, ("quoted-credential-assignment", _QUOTED_ASSIGNMENT_RE, 1))
    for detector, pattern, group in detectors:
        if budget is not None:
            budget.consume_work()
        for match in pattern.finditer(data):
            if budget is not None:
                budget.consume_work()
            secret = match.group(group)
            if detector == "quoted-credential-assignment" and _looks_like_placeholder(secret):
                continue
            fingerprint = masked_fingerprint(secret)
            line = data.count(b"\n", 0, match.start(group)) + 1
            key = (detector, fingerprint, line)
            if key in seen:
                continue
            seen.add(key)
            candidate = _candidate(
                    kind="secret",
                    severity="BLOCKER",
                    action="review",
                    path=path,
                    evidence="redacted secret candidate",
                    recommendation=(
                        "Triage without disclosure. If confirmed, revoke or rotate first, "
                        "then remove it from the index and every published ref."
                    ),
                    detector=detector,
                    fingerprint=fingerprint,
                    line=line,
                    object_id=object_id,
                    source=source,
                    history_only=source in {"history", "metadata", "ref"},
                    **location,
                )
            if budget is not None:
                budget.consume_work(
                    retained_bytes=sum(
                        len(value.encode("utf-8", errors="surrogateescape"))
                        for value in candidate.values()
                        if isinstance(value, str)
                    )
                )
            candidates.append(candidate)
    return candidates


def _redact_extra_string(value: str) -> str:
    data = value.encode("utf-8", errors="surrogateescape")
    spans: list[tuple[int, int, bytes]] = []
    detectors = (
        *SECRET_DETECTORS,
        *_PROVIDER_SECRET_DETECTORS,
        ("quoted-credential-assignment", _QUOTED_ASSIGNMENT_RE, 1),
    )
    for _detector, pattern, group in detectors:
        for match in pattern.finditer(data):
            secret = match.group(group)
            start, end = match.span(group)
            replacement = ("redacted:" + masked_fingerprint(secret)).encode("ascii")
            spans.append((start, end, replacement))
    if not spans:
        return value
    selected: list[tuple[int, int, bytes]] = []
    cursor = -1
    for start, end, replacement in sorted(spans, key=lambda item: (item[0], -item[1])):
        if start < cursor:
            continue
        selected.append((start, end, replacement))
        cursor = end
    chunks: list[bytes] = []
    cursor = 0
    for start, end, replacement in selected:
        chunks.append(data[cursor:start])
        chunks.append(replacement)
        cursor = end
    chunks.append(data[cursor:])
    return b"".join(chunks).decode("utf-8", errors="surrogateescape")


def _redact_extra(value: object) -> object:
    if isinstance(value, str):
        return _redact_extra_string(value)
    if isinstance(value, list):
        return [_redact_extra(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_extra(item) for item in value)
    if isinstance(value, dict):
        return {
            _redact_extra_string(key) if isinstance(key, str) else key: _redact_extra(item)
            for key, item in value.items()
        }
    return value


def redact_pre_push_result(result: dict[str, object]) -> dict[str, object]:
    extra_redacted = _redact_extra(result)
    if not isinstance(extra_redacted, dict):
        raise ValueError("audit result must be an object")
    return _redact_result(extra_redacted)


def _read_allow_ai_patterns(
    index_entries: Sequence[IndexEntry], contents: dict[str, bytes]
) -> tuple[list[str], list[dict[str, object]]]:
    patterns: list[str] = []
    findings: list[dict[str, object]] = []
    entry = next(
        (
            item
            for item in index_entries
            if item.stage == 0 and _normalise_path(item.path) == _ALLOW_AI_FILE
        ),
        None,
    )
    if entry is None:
        return patterns, findings
    data = contents.get(entry.object_id)
    if data is None:
        findings.append(
            _candidate(
                kind="ai-allowlist",
                severity="BLOCKER",
                action="review",
                path=_ALLOW_AI_FILE,
                evidence="AI allowlist could not be read from the Git index",
                recommendation="Make the allowlist readable or remove it before publication.",
            )
        )
        return patterns, findings
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        findings.append(
            _candidate(
                kind="ai-allowlist",
                severity="BLOCKER",
                action="fix",
                path=_ALLOW_AI_FILE,
                evidence="AI allowlist is not UTF-8 text",
                recommendation="Use one narrow repository-relative glob per line.",
            )
        )
        return patterns, findings
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        pattern = raw_line.strip()
        if not pattern or pattern.startswith("#"):
            continue
        normalised = _normalise_path(pattern)
        parts = PurePosixPath(normalised).parts
        invalid = (
            normalised.startswith(("/", "!"))
            or ".." in parts
            or normalised in {"*", "**", "**/*"}
            or not any(character not in "*?/" for character in normalised)
            or not _ai_allow_pattern_is_narrow(normalised)
        )
        if invalid:
            findings.append(
                _candidate(
                    kind="ai-allowlist",
                    severity="BLOCKER",
                    action="fix",
                    path=_ALLOW_AI_FILE,
                    evidence="AI allowlist contains an unsafe or overbroad pattern",
                    recommendation="Replace it with a narrow repository-relative glob.",
                    line=line_number,
                )
            )
            continue
        patterns.append(normalised)
    return patterns, findings


def _read_reviewed_findings(
    index_entries: Sequence[IndexEntry],
    contents: dict[str, bytes],
    approval: str | None,
    budget: GitRepository | None = None,
) -> tuple[set[tuple[object, ...]], list[dict[str, object]], str | None]:
    entries = [entry for entry in index_entries if entry.path == _REVIEWED_FINDINGS_FILE]
    if not entries and approval is None:
        return set(), [], None

    def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        if len(entries) != 1 or entries[0].stage != 0 or entries[0].mode not in {"100644", "100755"}:
            raise ValueError("policy provenance")
        data = contents[entries[0].object_id]
        if budget is not None:
            budget.consume_work(max(1, (len(data) + 4095) // 4096))
        digest = hashlib.sha256(data).hexdigest()
        if approval is not None and (
            not isinstance(approval, str)
            or re.fullmatch(r"[0-9a-f]{64}", approval) is None
            or digest != approval
        ):
            raise ValueError("policy approval")
        document = json.loads(data.decode("utf-8"), object_pairs_hook=unique_keys)
        if (
            not isinstance(document, dict)
            or set(document) != {"schema_version", "findings"}
            or type(document["schema_version"]) is not int
            or document["schema_version"] != 1
            or not isinstance(document["findings"], list)
            or len(document["findings"]) > 128
        ):
            raise ValueError("policy schema")
        records: set[tuple[object, ...]] = set()
        fields = {"path", "blob_sha256", "detector", "fingerprint", "line", "reason"}
        for record in document["findings"]:
            if budget is not None:
                budget.consume_work()
            if not isinstance(record, dict) or set(record) != fields:
                raise ValueError("record schema")
            if any(not isinstance(record[field], str) for field in fields - {"line"}):
                raise ValueError("record type")
            path = record["path"]
            if (
                any(part in {"", ".", ".."} for part in path.split("/"))
                or any(char in path for char in "\\:*?[]")
                or any(unicodedata.category(char).startswith("C") for char in path)
                or re.fullmatch(r"[0-9a-f]{64}", record["blob_sha256"]) is None
                or record["detector"] != "quoted-credential-assignment"
                or re.fullmatch(r"sha256:[0-9a-f]{12}", record["fingerprint"]) is None
                or type(record["line"]) is not int
                or not 1 <= record["line"] <= 2_147_483_647
                or not record["reason"].strip()
                or len(record["reason"]) > 1024
                or any(unicodedata.category(char).startswith("C") for char in record["reason"])
            ):
                raise ValueError("record identity")
            identity = tuple(record[field] for field in ("path", "blob_sha256", "detector", "fingerprint", "line"))
            if identity in records:
                raise ValueError("duplicate record")
            records.add(identity)
            if budget is not None:
                budget.consume_work(0, retained_bytes=sum(len(value.encode("utf-8")) for value in identity if isinstance(value, str)) + 4)
        return records if approval is not None else set(), [], digest if approval is not None else None
    except (KeyError, ValueError, UnicodeError, RecursionError):
        return set(), [_candidate(
            kind="reviewed-findings-policy", severity="BLOCKER", action="fix",
            path=_REVIEWED_FINDINGS_FILE,
            evidence="reviewed-findings policy or caller approval is invalid or unavailable",
            recommendation="Review the exact staged regular policy and supply its independently pinned SHA256 approval.",
        )], None


def _apply_reviewed_findings(
    candidates: Sequence[dict[str, object]],
    records: set[tuple[object, ...]],
    blob_hashes: dict[str, str],
    digest: str | None,
    repository: GitRepository,
) -> None:
    if not records or digest is None:
        return
    for candidate in candidates:
        repository.consume_work()
        if (
            candidate.get("kind") != "secret"
            or candidate.get("source") not in {"index", "history"}
            or candidate.get("mode") not in {"100644", "100755"}
            or candidate.get("detector") != "quoted-credential-assignment"
        ):
            continue
        identity = (
            candidate.get("path"), blob_hashes.get(str(candidate.get("object_id"))),
            candidate.get("detector"), candidate.get("fingerprint"), candidate.get("line"),
        )
        if identity in records:
            candidate.update(
                severity="INFO", action="keep", reviewed_false_positive=True,
                reviewed_policy_sha256=digest,
                evidence="exact generic candidate classified by caller-approved staged review policy",
                recommendation="Retain the reviewed classification only while its exact policy and blob identity remain approved.",
            )


def _ai_allowed(path: str, patterns: Sequence[str]) -> bool:
    normalised = _normalise_path(path)
    return _ai_allowlistable_path(normalised) and any(
        fnmatch.fnmatchcase(normalised, pattern) for pattern in patterns
    )


def _classify_extended_path(
    path: str,
    *,
    source: str,
    allow_ai_patterns: Sequence[str],
    object_id: str | None = None,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    if _is_ai_path(path):
        allowed = _ai_allowed(path, allow_ai_patterns)
        if allowed:
            candidates.append(
                _candidate(
                    kind="ai-file",
                    severity="INFO",
                    action="keep",
                    path=path,
                    evidence="AI-related file is explicitly allowlisted",
                    recommendation="Keep the allowlist narrow and review the file before every public release.",
                    source=source,
                    history_only=(source == "history"),
                    **({"object_id": object_id} if object_id else {}),
                )
            )
        elif source == "ignored":
            pass
        else:
            action = "purge" if source == "history" else ("ignore" if source == "untracked" else "review")
            candidates.append(
                _candidate(
                    kind="ai-file",
                    severity="BLOCKER" if source in {"index", "tracked", "history"} else "WARNING",
                    action=action,
                    path=path,
                    evidence=f"{source} AI instruction, state, prompt, or transcript artifact",
                    recommendation=(
                        "Remove it from every publishable surface, or narrowly allowlist it "
                        "only when it is intentional repository content."
                    ),
                    source=source,
                    history_only=(source == "history"),
                    **({"object_id": object_id} if object_id else {}),
                )
            )
    sensitive = _sensitive_path_kind(path)
    if sensitive is not None and source != "ignored":
        kind, severity = sensitive
        action = "purge" if source == "history" else ("ignore" if source == "untracked" else "review")
        candidates.append(
            _candidate(
                kind=kind,
                severity=severity if source != "untracked" else "WARNING",
                action=action,
                path=path,
                evidence=f"{source} path commonly contains local, credential, key, state, backup, or dump data",
                recommendation="Inspect without disclosure and remove or explicitly justify it before publication.",
                source=source,
                history_only=(source == "history"),
                **({"object_id": object_id} if object_id else {}),
            )
        )
    return candidates


def _ecosystems(paths: Iterable[str]) -> set[str]:
    names = {_basename(path) for path in paths}
    detected: set[str] = set()
    if names & {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "pipfile",
        "poetry.lock",
        "requirements.txt",
    } or any(name.startswith("requirements-") and name.endswith(".txt") for name in names):
        detected.add("python")
    if names & {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}:
        detected.add("node")
    if names & {"build.gradle", "build.gradle.kts", "gradlew"}:
        detected.add("gradle")
    if names & {"cargo.toml", "cargo.lock"}:
        detected.add("rust")
    if any(name.endswith(".tf") for name in names):
        detected.add("terraform")
    return detected


def _normalise_ignore_source(source: str, work_tree: Path | None) -> str:
    normalised = _normalise_path(source)
    if work_tree is None:
        return normalised
    source_path = Path(source)
    if source_path.is_absolute():
        try:
            return source_path.resolve(strict=False).relative_to(work_tree).as_posix()
        except (OSError, ValueError):
            return normalised
    return normalised


def _check_ignore(
    repository: GitRepository,
    paths: Sequence[str],
    *,
    work_tree: Path | None = None,
) -> dict[str, IgnoreMatch]:
    if not paths:
        return {}
    raw_paths = [path.encode("utf-8", errors="surrogateescape") for path in paths]
    options: list[str] = ["-c", f"core.excludesFile={os.devnull}"]
    if work_tree is not None:
        options.append(f"--work-tree={work_tree}")
    output = repository.run(
        *options,
        "check-ignore",
        "-v",
        "-z",
        "--no-index",
        "--stdin",
        "--non-matching",
        input_bytes=b"\0".join(raw_paths) + b"\0",
        literal_pathspecs=False,
        # No matching ignore rule is a normal check-ignore result.
        ok_returncodes=(0, 1),
    )
    fields = output.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 4 != 0:
        raise GitCommandError("Git ignore provenance was malformed")
    matches: dict[str, IgnoreMatch] = {}
    for offset in range(0, len(fields), 4):
        repository.consume_work()
        source_raw, line_raw, pattern_raw, path_raw = fields[offset : offset + 4]
        if not source_raw:
            continue
        path = path_raw.decode("utf-8", errors="surrogateescape")
        line_text = line_raw.decode("ascii", errors="strict")
        matches[path] = IgnoreMatch(
            source=_normalise_ignore_source(
                source_raw.decode("utf-8", errors="surrogateescape"),
                work_tree,
            ),
            line=int(line_text) if line_text else 0,
            pattern=pattern_raw.decode("utf-8", errors="surrogateescape"),
            path=path,
        )
    return matches


def _portable_ignore_source(source: str, tracked_paths: set[str]) -> bool:
    normalised = _normalise_path(source)
    if normalised == ".git/info/exclude" or normalised.endswith("/.git/info/exclude"):
        return False
    return normalised in tracked_paths and _basename(normalised) == ".gitignore"


def _write_staged_gitignores(
    directory: Path,
    index_entries: Sequence[IndexEntry],
    contents: dict[str, bytes],
    result: dict[str, object],
) -> set[str]:
    tracked_paths = {
        _normalise_path(entry.path)
        for entry in index_entries
        if entry.stage == 0
    }
    for entry in index_entries:
        normalised = _normalise_path(entry.path)
        if entry.stage != 0 or _basename(normalised) != ".gitignore":
            continue
        relative = PurePosixPath(normalised)
        if relative.is_absolute() or ".." in relative.parts:
            _append_gap(
                result,
                evidence="indexed .gitignore path is not repository-relative",
                path=entry.path,
                object_id=entry.object_id,
            )
            continue
        if entry.mode not in {"100644", "100755"}:
            _append_gap(
                result,
                evidence="indexed .gitignore is not a regular file",
                path=entry.path,
                object_id=entry.object_id,
            )
            continue
        data = contents.get(entry.object_id)
        if data is None:
            _append_gap(
                result,
                evidence="indexed .gitignore content could not be read",
                path=entry.path,
                object_id=entry.object_id,
            )
            continue
        target = directory.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return tracked_paths


def _ignore_checks(
    repository: GitRepository,
    result: dict[str, object],
    *,
    index_entries: Sequence[IndexEntry],
    contents: dict[str, bytes],
    allow_ai_patterns: Sequence[str],
) -> list[dict[str, object]]:
    inventory = result.get("inventory", {})
    if not isinstance(inventory, dict):
        raise ValueError("inventory must be an object")
    ignored = [str(path) for path in inventory.get("ignored", [])]
    indexed_paths = {
        _normalise_path(entry.path)
        for entry in index_entries
        if entry.stage == 0
    }

    probes = list(_GENERIC_IGNORE_PROBES)
    for ecosystem in sorted(_ecosystems(indexed_paths)):
        probes.extend(_ECOSYSTEM_PROBES[ecosystem])
    probe_paths = [path for _, path in probes]
    actual_risky_ignored = [
        path
        for path in ignored
        if (_is_ai_path(path) and not _ai_allowed(path, allow_ai_patterns))
        or _sensitive_path_kind(path) is not None
    ]
    requested = list(dict.fromkeys(probe_paths + actual_risky_ignored))
    temporary_base = Path(tempfile.gettempdir()).resolve(strict=False)
    repository_root = repository.root.resolve(strict=False)
    try:
        temporary_base.relative_to(repository_root)
    except ValueError:
        pass
    else:
        temporary_base = repository_root.parent
    with tempfile.TemporaryDirectory(
        prefix="github-ready-ignore-",
        dir=temporary_base,
    ) as temporary:
        staged_work_tree = Path(temporary)
        tracked_paths = _write_staged_gitignores(
            staged_work_tree,
            index_entries,
            contents,
            result,
        )
        matches = _check_ignore(
            repository,
            requested,
            work_tree=staged_work_tree,
        )

    candidates: list[dict[str, object]] = []
    missing_by_category: dict[str, list[str]] = {}
    local_by_category: dict[str, list[str]] = {}
    category_by_probe = {path: category for category, path in probes}
    for path in probe_paths:
        category = category_by_probe[path]
        match = matches.get(path)
        if match is None or not match.ignored:
            missing_by_category.setdefault(category, []).append(path)
        elif not _portable_ignore_source(match.source, tracked_paths):
            local_by_category.setdefault(category, []).append(path)

    for category, paths in sorted(missing_by_category.items()):
        candidates.append(
            _candidate(
                kind="ignore-policy",
                severity="WARNING",
                action="fix",
                evidence=f"the staged repository .gitignore lacks the {category} baseline",
                recommendation=(
                    "Add the minimal matching rules to an indexed .gitignore; "
                    "working-tree, .git/info/exclude, and global rules do not ship with the commit."
                ),
                paths=sorted(paths),
            )
        )
    for category, paths in sorted(local_by_category.items()):
        candidates.append(
            _candidate(
                kind="ignore-policy",
                severity="WARNING",
                action="fix",
                evidence=f"the staged {category} baseline resolves only to a non-portable ignore source",
                recommendation="Move the required rules into an indexed repository .gitignore.",
                paths=sorted(paths),
            )
        )

    for path in actual_risky_ignored:
        match = matches.get(path)
        if match is None or not match.ignored:
            candidates.append(
                _candidate(
                    kind="ignore-policy",
                    severity="BLOCKER",
                    action="fix",
                    path=path,
                    evidence="a risky local file is not ignored by the .gitignore version staged for publication",
                    recommendation="Stage a narrow matching rule in a repository .gitignore before publication.",
                )
            )
        elif not _portable_ignore_source(match.source, tracked_paths):
            candidates.append(
                _candidate(
                    kind="ignore-policy",
                    severity="BLOCKER",
                    action="fix",
                    path=path,
                    evidence="a risky local file is protected only by .git/info/exclude or another non-portable source",
                    recommendation="Stage a narrow equivalent rule in a repository .gitignore before publication.",
                )
            )
    return candidates



def _decode_nul_paths(output: bytes) -> list[str]:
    return sorted(
        entry.decode("utf-8", errors="surrogateescape")
        for entry in output.split(b"\0")
        if entry
    )


def _bounded_path_evidence(paths: Sequence[str], limit: int = 100) -> dict[str, object]:
    ordered = sorted(set(paths))
    evidence: dict[str, object] = {
        "count": len(ordered),
        "paths": ordered[:limit],
    }
    if len(ordered) > limit:
        evidence["paths_truncated"] = len(ordered) - limit
    return evidence


def _working_state_candidates(
    repository: GitRepository,
    inventory: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    unstaged = _decode_nul_paths(
        repository.run(
            "-c",
            "diff.external=",
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--name-only",
            "-z",
            "--",
        )
    )
    staged = _decode_nul_paths(
        repository.run(
            "-c",
            "diff.external=",
            "diff",
            "--cached",
            "--no-ext-diff",
            "--no-textconv",
            "--name-only",
            "-z",
            "--",
        )
    )
    untracked = sorted(str(path) for path in inventory.get("untracked", []))
    candidates: list[dict[str, object]] = []
    if untracked:
        candidates.append(
            _candidate(
                kind="untracked-files",
                severity="WARNING",
                action="review",
                evidence="untracked files are outside the commit that would be pushed",
                recommendation="Add, narrowly ignore, or delete each file so nothing is silently forgotten.",
                **_bounded_path_evidence(untracked),
            )
        )
    if unstaged:
        candidates.append(
            _candidate(
                kind="unstaged-changes",
                severity="WARNING",
                action="review",
                evidence="tracked working-tree changes differ from the Git index",
                recommendation="Stage or discard them, then rerun the gate against the exact publication state.",
                **_bounded_path_evidence(unstaged),
            )
        )
    if staged:
        candidates.append(
            _candidate(
                kind="staged-changes",
                severity="INFO",
                action="review",
                evidence="the Git index contains changes not yet represented by HEAD",
                recommendation="Commit the reviewed index before push and rerun the gate on the resulting ref.",
                **_bounded_path_evidence(staged),
            )
        )
    return candidates, {
        "untracked": len(untracked),
        "unstaged": len(unstaged),
        "staged": len(staged),
    }


def _unquote_git_config_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1]
    return stripped


def _parse_gitmodules(
    data: bytes,
    *,
    object_id: str,
) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return [], [
            _candidate(
                kind="submodule-config",
                severity="BLOCKER",
                action="fix",
                path=".gitmodules",
                evidence=".gitmodules is not valid UTF-8 text",
                recommendation="Replace it with reviewable UTF-8 Git configuration.",
                object_id=object_id,
            )
        ]
    sections: list[dict[str, str]] = []
    findings: list[dict[str, object]] = []
    current: dict[str, str] | None = None
    seen_names: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        section = _SUBMODULE_SECTION_RE.match(raw_line)
        if section:
            name = section.group(1)
            folded_name = name.casefold()
            if folded_name in seen_names:
                findings.append(
                    _candidate(
                        kind="submodule-config",
                        severity="BLOCKER",
                        action="fix",
                        path=".gitmodules",
                        evidence=".gitmodules repeats a submodule section name",
                        recommendation="Keep one unambiguous section per submodule.",
                        line=line_number,
                        object_id=object_id,
                    )
                )
            seen_names.add(folded_name)
            current = {"name": name}
            sections.append(current)
            continue
        key_value = _SUBMODULE_KEY_RE.match(raw_line)
        if current is None or key_value is None:
            findings.append(
                _candidate(
                    kind="submodule-config",
                    severity="WARNING",
                    action="review",
                    path=".gitmodules",
                    evidence=".gitmodules contains an unrecognized line",
                    recommendation="Verify the syntax with Git before publication.",
                    line=line_number,
                    object_id=object_id,
                )
            )
            continue
        key = key_value.group(1).casefold()
        value = _unquote_git_config_value(key_value.group(2))
        if key in current:
            findings.append(
                _candidate(
                    kind="submodule-config",
                    severity="BLOCKER",
                    action="fix",
                    path=".gitmodules",
                    evidence="a submodule key is defined more than once",
                    recommendation="Keep one value for each submodule key.",
                    line=line_number,
                    object_id=object_id,
                )
            )
        current[key] = value
    return sections, findings


def _submodule_candidates(
    index_entries: Sequence[IndexEntry],
    contents: dict[str, bytes],
) -> list[dict[str, object]]:
    gitlinks = {
        _normalise_path(entry.path): entry
        for entry in index_entries
        if entry.stage == 0 and entry.mode == "160000"
    }
    modules_entry = next(
        (
            entry
            for entry in index_entries
            if entry.stage == 0 and _normalise_path(entry.path) == ".gitmodules"
        ),
        None,
    )
    candidates: list[dict[str, object]] = []
    if modules_entry is None:
        if gitlinks:
            candidates.append(
                _candidate(
                    kind="submodule-config",
                    severity="BLOCKER",
                    action="fix",
                    evidence="Git index contains gitlinks but no staged .gitmodules",
                    recommendation="Add a complete .gitmodules or remove the unintended gitlinks.",
                    paths=sorted(gitlinks),
                )
            )
        return candidates
    if modules_entry.mode not in {"100644", "100755"}:
        candidates.append(
            _candidate(
                kind="submodule-config",
                severity="BLOCKER",
                action="fix",
                path=".gitmodules",
                evidence=".gitmodules is not a regular file in the Git index",
                recommendation="Store it as a regular reviewable text file.",
                object_id=modules_entry.object_id,
            )
        )
        return candidates
    data = contents.get(modules_entry.object_id)
    if data is None:
        candidates.append(
            _candidate(
                kind="submodule-config",
                severity="BLOCKER",
                action="review",
                path=".gitmodules",
                evidence="staged .gitmodules content could not be inspected",
                recommendation="Make the file readable before publication.",
                object_id=modules_entry.object_id,
            )
        )
        return candidates
    sections, parse_findings = _parse_gitmodules(data, object_id=modules_entry.object_id)
    candidates.extend(parse_findings)
    declared: dict[str, str] = {}
    for section in sections:
        name = section.get("name", "")
        raw_path = section.get("path", "").strip()
        url = section.get("url", "").strip()
        update = section.get("update", "").strip()
        if not raw_path:
            candidates.append(
                _candidate(
                    kind="submodule-config",
                    severity="BLOCKER",
                    action="fix",
                    path=".gitmodules",
                    evidence="a submodule section has no path",
                    recommendation="Declare a unique repository-relative path.",
                    object_id=modules_entry.object_id,
                    submodule=name,
                )
            )
            continue
        normalised = _normalise_path(raw_path).rstrip("/")
        parts = PurePosixPath(normalised).parts
        invalid_path = (
            not normalised
            or PurePosixPath(normalised).is_absolute()
            or ".." in parts
            or raw_path.startswith(("~", "\\\\"))
            or re.match(r"^[A-Za-z]:[\\\\/]", raw_path) is not None
        )
        if invalid_path:
            candidates.append(
                _candidate(
                    kind="submodule-config",
                    severity="BLOCKER",
                    action="fix",
                    path=".gitmodules",
                    evidence="a submodule path is absolute, escaping, or platform-specific",
                    recommendation="Use a unique repository-relative POSIX path.",
                    object_id=modules_entry.object_id,
                    submodule=name,
                )
            )
            continue
        if normalised in declared:
            candidates.append(
                _candidate(
                    kind="submodule-config",
                    severity="BLOCKER",
                    action="fix",
                    path=".gitmodules",
                    evidence="multiple submodule sections declare the same path",
                    recommendation="Keep one section per gitlink path.",
                    object_id=modules_entry.object_id,
                    submodule=name,
                )
            )
        declared[normalised] = name
        if normalised not in gitlinks:
            candidates.append(
                _candidate(
                    kind="submodule-config",
                    severity="WARNING",
                    action="review",
                    path=".gitmodules",
                    evidence=".gitmodules declares a path that is not a staged gitlink",
                    recommendation="Stage the intended submodule or remove stale configuration.",
                    object_id=modules_entry.object_id,
                    submodule=name,
                    submodule_path=normalised,
                )
            )
        if not url:
            candidates.append(
                _candidate(
                    kind="submodule-config",
                    severity="BLOCKER",
                    action="fix",
                    path=".gitmodules",
                    evidence="a submodule section has no URL",
                    recommendation="Declare a reviewed, cloneable URL.",
                    object_id=modules_entry.object_id,
                    submodule=name,
                )
            )
        else:
            folded_url = url.casefold()
            dangerous_url = (
                folded_url.startswith(("file:", "ext::", "fd::", "~", "/", "\\\\"))
                or re.match(r"^[A-Za-z]:[\\\\/]", url) is not None
            )
            if dangerous_url:
                candidates.append(
                    _candidate(
                        kind="submodule-config",
                        severity="BLOCKER",
                        action="fix",
                        path=".gitmodules",
                        evidence="a submodule URL uses a local path or command-capable transport",
                        recommendation="Use a reviewed network URL owned by the project.",
                        object_id=modules_entry.object_id,
                        submodule=name,
                    )
                )
            elif folded_url.startswith("http://"):
                candidates.append(
                    _candidate(
                        kind="submodule-config",
                        severity="WARNING",
                        action="fix",
                        path=".gitmodules",
                        evidence="a submodule URL uses unencrypted HTTP",
                        recommendation="Use HTTPS or a reviewed authenticated Git transport.",
                        object_id=modules_entry.object_id,
                        submodule=name,
                    )
                )
            elif folded_url.startswith(("./", "../")):
                candidates.append(
                    _candidate(
                        kind="submodule-config",
                        severity="INFO",
                        action="review",
                        path=".gitmodules",
                        evidence="a submodule URL is relative to the superproject remote",
                        recommendation="Verify that it resolves correctly from the public GitHub remote.",
                        object_id=modules_entry.object_id,
                        submodule=name,
                    )
                )
        if update.startswith("!"):
            candidates.append(
                _candidate(
                    kind="submodule-config",
                    severity="BLOCKER",
                    action="fix",
                    path=".gitmodules",
                    evidence="a submodule update value requests command execution",
                    recommendation="Remove command-capable update configuration.",
                    object_id=modules_entry.object_id,
                    submodule=name,
                )
            )
    undeclared = sorted(set(gitlinks) - set(declared))
    if undeclared:
        candidates.append(
            _candidate(
                kind="submodule-config",
                severity="BLOCKER",
                action="fix",
                evidence="staged gitlinks are missing from .gitmodules",
                recommendation="Declare each intended submodule path or remove the gitlink.",
                paths=undeclared,
            )
        )
    return candidates


def _portable_path_checks(index_entries: Sequence[IndexEntry]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    by_casefold: dict[str, list[str]] = {}
    by_nfc_casefold: dict[str, list[str]] = {}
    for entry in index_entries:
        if entry.stage != 0:
            continue
        normalised = _normalise_path(entry.path)
        by_casefold.setdefault(normalised.casefold(), []).append(entry.path)
        nfc = unicodedata.normalize("NFC", normalised).casefold()
        by_nfc_casefold.setdefault(nfc, []).append(entry.path)

        unsafe_components: list[str] = []
        if "\\" in entry.path:
            unsafe_components.append("<backslash>")
        for component in PurePosixPath(normalised).parts:
            folded_stem = component.rstrip(" .").split(".", 1)[0].casefold()
            if (
                component.rstrip(" .") != component
                or folded_stem in _WINDOWS_RESERVED_NAMES
                or _WINDOWS_INVALID_COMPONENT_RE.search(component) is not None
            ):
                unsafe_components.append(component)
        if unsafe_components:
            candidates.append(
                _candidate(
                    kind="path-portability",
                    severity="BLOCKER",
                    action="move",
                    path=entry.path,
                    evidence="tracked path is invalid or ambiguous on Windows",
                    recommendation="Rename every unsafe component before publication.",
                    components=unsafe_components,
                )
            )
        if len(normalised.encode("utf-8", errors="surrogateescape")) > 240:
            candidates.append(
                _candidate(
                    kind="path-portability",
                    severity="WARNING",
                    action="move",
                    path=entry.path,
                    evidence="tracked path exceeds 240 UTF-8 bytes",
                    recommendation="Shorten it to avoid checkout and tooling failures on constrained platforms.",
                )
            )

    reported: set[tuple[str, ...]] = set()
    for mapping, evidence in (
        (by_casefold, "tracked paths collide on a case-insensitive filesystem"),
        (by_nfc_casefold, "tracked paths collide after Unicode normalization"),
    ):
        for paths in mapping.values():
            unique = tuple(sorted(set(paths)))
            if len(unique) < 2 or unique in reported:
                continue
            reported.add(unique)
            candidates.append(
                _candidate(
                    kind="path-collision",
                    severity="BLOCKER",
                    action="move",
                    evidence=evidence,
                    recommendation="Rename the paths so a GitHub checkout is unambiguous across platforms.",
                    paths=list(unique),
                )
            )
    return candidates


def _resolve_symlink_target(path: str, target: str) -> tuple[str | None, bool]:
    target_text = target.replace("\\", "/")
    target_path = PurePosixPath(target_text)
    if target_path.is_absolute():
        return None, True
    stack = [part for part in PurePosixPath(_normalise_path(path)).parent.parts if part not in {"", "."}]
    for part in target_path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not stack:
                return None, True
            stack.pop()
        else:
            stack.append(part)
    return posixpath.normpath("/".join(stack)), False


def _symlink_candidates(
    path: str,
    data: bytes,
    object_id: str,
    indexed_paths: set[str],
) -> list[dict[str, object]]:
    target = data.decode("utf-8", errors="surrogateescape")
    resolved, escapes = _resolve_symlink_target(path, target)
    candidates: list[dict[str, object]] = []
    if escapes:
        candidates.append(
            _candidate(
                kind="symlink",
                severity="WARNING",
                action="review",
                path=path,
                evidence="tracked symbolic link is absolute or escapes the repository",
                recommendation="Use a repository-relative in-tree target or document why the external link is intentional.",
                object_id=object_id,
            )
        )
        return candidates
    assert resolved is not None
    target_exists = resolved in indexed_paths or any(
        candidate.startswith(resolved.rstrip("/") + "/")
        for candidate in indexed_paths
    )
    if not target_exists:
        candidates.append(
            _candidate(
                kind="dangling-symlink",
                severity="WARNING",
                action="review",
                path=path,
                evidence="tracked symbolic link has no target in the staged repository tree",
                recommendation="Stage the target, correct the link, or document the runtime-generated target.",
                object_id=object_id,
                target=resolved,
            )
        )
    return candidates


def _line_indentation(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _checkout_persists_credentials(lines: Sequence[str], start_index: int) -> bool:
    start_indent = _line_indentation(lines[start_index])
    for following in lines[start_index + 1 :]:
        stripped = following.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = _line_indentation(following)
        if indent <= start_indent and stripped.startswith("-"):
            break
        if re.match(r"^persist-credentials\s*:\s*false\s*(?:#.*)?$", stripped, re.IGNORECASE):
            return False
    return True


def _workflow_candidates(path: str, data: bytes, object_id: str) -> list[dict[str, object]]:
    normalised = _normalise_path(path).casefold()
    if not normalised.startswith(".github/workflows/") or not normalised.endswith((".yml", ".yaml")):
        return []
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return [
            _candidate(
                kind="github-actions",
                severity="BLOCKER",
                action="fix",
                path=path,
                evidence="workflow file is not valid UTF-8 text",
                recommendation="Replace it with reviewable UTF-8 YAML.",
                object_id=object_id,
            )
        ]
    lines = text.splitlines()
    candidates: list[dict[str, object]] = []
    has_explicit_permissions = any(
        re.match(r"^\s*permissions\s*:", line, re.IGNORECASE)
        for line in lines
        if not line.lstrip().startswith("#")
    )
    if not has_explicit_permissions:
        candidates.append(
            _candidate(
                kind="github-actions",
                severity="WARNING",
                action="fix",
                path=path,
                evidence="workflow has no explicit permissions declaration",
                recommendation="Set read-only top-level permissions and grant only required job-level writes.",
                object_id=object_id,
            )
        )
    has_pull_request_target = False
    checks_out_pull_request_head = False
    for line_number, line in enumerate(lines, 1):
        if line.lstrip().startswith("#"):
            continue
        uses = _ACTION_USES_RE.match(line)
        if uses:
            target = uses.group(1).strip("'\"")
            if target.startswith("docker://"):
                if "@sha256:" not in target:
                    candidates.append(
                        _candidate(
                            kind="github-actions",
                            severity="WARNING",
                            action="fix",
                            path=path,
                            evidence="workflow container action is not pinned to a digest",
                            recommendation="Pin the image to a reviewed sha256 digest.",
                            line=line_number,
                            object_id=object_id,
                        )
                    )
            elif not target.startswith("./"):
                if "@" not in target:
                    candidates.append(
                        _candidate(
                            kind="github-actions",
                            severity="BLOCKER",
                            action="fix",
                            path=path,
                            evidence="external action reference has no immutable ref",
                            recommendation="Add a reviewed full commit SHA.",
                            line=line_number,
                            object_id=object_id,
                        )
                    )
                else:
                    action_name, ref = target.rsplit("@", 1)
                    if not _FULL_ACTION_SHA_RE.fullmatch(ref):
                        candidates.append(
                            _candidate(
                                kind="github-actions",
                                severity="WARNING",
                                action="fix",
                                path=path,
                                evidence="external action is not pinned to a full commit SHA",
                                recommendation="Pin the action to a reviewed full commit SHA and retain a version comment.",
                                line=line_number,
                                object_id=object_id,
                            )
                        )
                    if action_name.casefold() == "actions/checkout" and _checkout_persists_credentials(
                        lines, line_number - 1
                    ):
                        candidates.append(
                            _candidate(
                                kind="github-actions",
                                severity="WARNING",
                                action="fix",
                                path=path,
                                evidence="actions/checkout keeps credentials by default",
                                recommendation="Set persist-credentials: false unless a reviewed later step must write with the token.",
                                line=line_number,
                                object_id=object_id,
                            )
                        )
        folded = line.casefold()
        if re.search(r"^\s*permissions\s*:\s*write-all\s*(?:#.*)?$", folded):
            candidates.append(
                _candidate(
                    kind="github-actions",
                    severity="BLOCKER",
                    action="fix",
                    path=path,
                    evidence="workflow grants write-all permissions",
                    recommendation="Use read-only defaults and grant only the minimum job-level permissions.",
                    line=line_number,
                    object_id=object_id,
                )
            )
        write_scope = re.match(
            r"^\s*(actions|attestations|checks|contents|deployments|discussions|"
            r"id-token|issues|packages|pages|pull-requests|repository-projects|"
            r"security-events|statuses)\s*:\s*write\s*(?:#.*)?$",
            folded,
        )
        if write_scope:
            candidates.append(
                _candidate(
                    kind="github-actions",
                    severity="WARNING",
                    action="review",
                    path=path,
                    evidence=f"workflow grants write permission for {write_scope.group(1)}",
                    recommendation="Confirm that the job needs this scope and that untrusted inputs cannot reach it.",
                    line=line_number,
                    object_id=object_id,
                )
            )
        if re.search(r"\bpull_request_target\b", folded):
            has_pull_request_target = True
            candidates.append(
                _candidate(
                    kind="github-actions",
                    severity="WARNING",
                    action="review",
                    path=path,
                    evidence="workflow uses pull_request_target",
                    recommendation="Verify that untrusted pull-request code can never run with base-repository secrets or write permissions.",
                    line=line_number,
                    object_id=object_id,
                )
            )
        if "github.event.pull_request.head" in folded or "github.head_ref" in folded:
            checks_out_pull_request_head = True
        if re.search(r"\bworkflow_run\b", folded):
            candidates.append(
                _candidate(
                    kind="github-actions",
                    severity="WARNING",
                    action="review",
                    path=path,
                    evidence="workflow is triggered by workflow_run",
                    recommendation="Verify that artifacts or inputs from an untrusted workflow cannot reach privileged steps.",
                    line=line_number,
                    object_id=object_id,
                )
            )
        if re.search(r"^\s*persist-credentials\s*:\s*true\s*(?:#.*)?$", folded):
            candidates.append(
                _candidate(
                    kind="github-actions",
                    severity="WARNING",
                    action="fix",
                    path=path,
                    evidence="checkout credentials remain persisted in the worktree",
                    recommendation="Set persist-credentials: false unless later Git writes are explicitly required.",
                    line=line_number,
                    object_id=object_id,
                )
            )
        if re.search(r"(?:curl|wget)[^|\r\n]*\|\s*(?:sh|bash)\b", folded):
            candidates.append(
                _candidate(
                    kind="github-actions",
                    severity="WARNING",
                    action="review",
                    path=path,
                    evidence="workflow pipes a network download directly into a shell",
                    recommendation="Download, verify a pinned checksum or signature, then execute the reviewed file.",
                    line=line_number,
                    object_id=object_id,
                )
            )
        if re.search(r"^\s*secrets\s*:\s*inherit\s*(?:#.*)?$", folded):
            candidates.append(
                _candidate(
                    kind="github-actions",
                    severity="WARNING",
                    action="review",
                    path=path,
                    evidence="reusable workflow inherits all caller secrets",
                    recommendation="Pass only explicitly required secrets.",
                    line=line_number,
                    object_id=object_id,
                )
            )
    if has_pull_request_target and checks_out_pull_request_head:
        candidates.append(
            _candidate(
                kind="github-actions",
                severity="BLOCKER",
                action="fix",
                path=path,
                evidence="pull_request_target workflow references pull-request head code",
                recommendation="Do not execute or checkout untrusted head code in a privileged pull_request_target workflow.",
                object_id=object_id,
            )
        )
    return candidates


def _metadata_secret_candidates(
    data: bytes,
    *,
    object_id: str,
    source: str,
    **location: object,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for candidate in scan_secret_candidates(
        data,
        location={"object_id": object_id},
    ):
        item = dict(candidate)
        item["source"] = source
        item["history_only"] = True
        item.update(location)
        candidates.append(item)
    candidates.extend(
        _scan_extra_secrets(
            data,
            path=None,
            object_id=object_id,
            source=source,
            **location,
        )
    )
    return candidates


def _git_metadata_candidates(
    repository: GitRepository,
    refs: Sequence[object],
    result: dict[str, object],
    *,
    max_blob_bytes: int,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    tag_refs_by_object: dict[str, list[str]] = {}
    metadata_ids: set[str] = set()

    for ref in refs:
        name = str(getattr(ref, "name"))
        object_id = str(getattr(ref, "object_id"))
        object_type = str(getattr(ref, "object_type"))
        candidates.extend(
            _metadata_secret_candidates(
                name.encode("utf-8", errors="surrogateescape"),
                object_id=object_id,
                source="ref",
                ref=name,
            )
        )
        if object_type == "tag":
            metadata_ids.add(object_id)
            tag_refs_by_object.setdefault(object_id, []).append(name)

    commit_output = repository.run("rev-list", "--all", "--missing=print")
    for raw in commit_output.splitlines():
        if raw.startswith(b"?"):
            _append_gap(
                result,
                evidence="reachable commit metadata is missing locally",
                object_id=raw[1:].decode("ascii", errors="strict"),
            )
            continue
        metadata_ids.add(raw.decode("ascii", errors="strict"))

    metadata = _batch_metadata(repository, sorted(metadata_ids))
    readable: list[str] = []
    for object_id in sorted(metadata_ids):
        object_type, size = metadata.get(object_id, ("missing", 0))
        if object_type not in {"commit", "tag"}:
            _append_gap(
                result,
                evidence="reachable commit or tag metadata is unavailable",
                object_id=object_id,
            )
            continue
        if size > max_blob_bytes:
            _append_gap(
                result,
                evidence="reachable commit or tag metadata exceeds the configured scan limit",
                object_id=object_id,
                size=size,
            )
            continue
        readable.append(object_id)

    for object_id, (object_type, data) in _batch_read_any(repository, readable).items():
        location: dict[str, object] = {"metadata_type": object_type}
        if object_type == "commit":
            location["commit"] = object_id
        elif object_id in tag_refs_by_object:
            location["refs"] = sorted(tag_refs_by_object[object_id])
        candidates.extend(
            _metadata_secret_candidates(
                data,
                object_id=object_id,
                source="metadata",
                **location,
            )
        )
    return candidates


def _nested_repository_checks(
    root: Path,
    *,
    gitlink_paths: set[str] | None = None,
    max_entries: int = 100_000,
) -> tuple[list[dict[str, object]], bool]:
    findings: list[dict[str, object]] = []
    queue: list[Path] = [root]
    visited = 0
    complete = True
    gitlinks = {_normalise_path(path).rstrip("/") for path in (gitlink_paths or set())}
    skip_names = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".next",
        ".gradle",
        "target",
        "dist",
        "build",
    }
    while queue:
        directory = queue.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            complete = False
            continue
        for entry in entries:
            visited += 1
            if visited > max_entries:
                return findings, False
            try:
                relative = Path(entry.path).relative_to(root).as_posix()
            except ValueError:
                complete = False
                continue
            if entry.name.casefold() == ".git":
                parent_relative = Path(entry.path).parent.relative_to(root).as_posix()
                if Path(entry.path) != root / ".git" and parent_relative not in gitlinks:
                    findings.append(
                        _candidate(
                            kind="nested-repository",
                            severity="BLOCKER",
                            action="review",
                            path=relative,
                            evidence="nested Git metadata exists inside the repository working tree",
                            recommendation="Convert it to an intentional submodule or remove the nested metadata before publication.",
                        )
                    )
                continue
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
            except OSError:
                complete = False
                continue
            if (
                is_directory
                and entry.name.casefold() not in skip_names
                and _normalise_path(relative).rstrip("/") not in gitlinks
            ):
                queue.append(Path(entry.path))
    return findings, complete


def _candidate_identity(candidate: dict[str, object]) -> tuple[object, ...]:
    kind = candidate.get("kind")
    if kind == "secret":
        return (
            kind,
            candidate.get("path"),
            candidate.get("detector"),
            candidate.get("fingerprint"),
            candidate.get("line"),
            candidate.get("object_id"),
            candidate.get("mode"),
        )
    if kind in {
        "ai-file",
        "environment-file",
        "sensitive-file",
        "private-key-file",
        "certificate-or-key-file",
        "state-or-variable-file",
        "local-artifact",
        "archive-backup-or-dump",
    }:
        historical = candidate.get("history_only") is True or candidate.get("source") == "history"
        return (
            kind,
            candidate.get("path"),
            historical,
            candidate.get("object_id") if historical else None,
        )
    return (
        kind,
        candidate.get("path"),
        tuple(candidate.get("paths", [])) if isinstance(candidate.get("paths"), list) else None,
        candidate.get("line"),
        candidate.get("object_id"),
        candidate.get("evidence"),
    )


def _merge_string_list(existing: dict[str, object], field: str, value: object) -> None:
    values: set[str] = set()
    current = existing.get(field)
    if isinstance(current, str):
        values.add(current)
    elif isinstance(current, list):
        values.update(str(item) for item in current)
    if isinstance(value, str):
        values.add(value)
    elif isinstance(value, list):
        values.update(str(item) for item in value)
    if values:
        existing[field] = sorted(values)


def _deduplicate(candidates: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    index: dict[tuple[object, ...], dict[str, object]] = {}
    severity_order = {"INFO": 0, "WARNING": 1, "BLOCKER": 2}
    action_order = {
        "keep": 0,
        "document": 1,
        "review": 2,
        "ignore": 3,
        "fix": 4,
        "move": 5,
        "delete": 6,
        "purge": 7,
        "revoke": 8,
    }
    for candidate in candidates:
        key = _candidate_identity(candidate)
        existing = index.get(key)
        if existing is None:
            copied = dict(candidate)
            result.append(copied)
            index[key] = copied
            continue
        for field in ("source", "sources", "ref", "refs", "commit", "commits"):
            if field in candidate:
                if field in {"source", "sources"}:
                    target, singular = "sources", "source"
                elif field in {"ref", "refs"}:
                    target, singular = "refs", "ref"
                else:
                    target, singular = "commits", "commit"
                _merge_string_list(existing, target, existing.get(singular))
                _merge_string_list(existing, target, candidate[field])
                existing.pop(singular, None)
        if candidate.get("history_only") is False:
            existing["history_only"] = False
        candidate_severity = str(candidate.get("severity"))
        existing_severity = str(existing.get("severity"))
        if severity_order.get(candidate_severity, -1) > severity_order.get(existing_severity, -1):
            existing["severity"] = candidate["severity"]
            if "evidence" in candidate:
                existing["evidence"] = candidate["evidence"]
        candidate_action = str(candidate.get("action"))
        existing_action = str(existing.get("action"))
        if action_order.get(candidate_action, -1) > action_order.get(existing_action, -1):
            existing["action"] = candidate["action"]
            if "recommendation" in candidate:
                existing["recommendation"] = candidate["recommendation"]
        if existing.get("severity") != "INFO" or not candidate.get("reviewed_false_positive"):
            existing.pop("reviewed_false_positive", None)
            existing.pop("reviewed_policy_sha256", None)
    return result


def verdict_for(result: dict[str, object]) -> str:
    coverage = result.get("coverage", {})
    if not isinstance(coverage, dict) or coverage.get("complete") is not True:
        return "INCOMPLETE"
    candidates = result.get("candidates", [])
    if not isinstance(candidates, list):
        return "INCOMPLETE"
    severities = {str(item.get("severity")) for item in candidates if isinstance(item, dict)}
    if "BLOCKER" in severities:
        return "NOT READY"
    if "WARNING" in severities:
        return "READY WITH WARNINGS"
    return "READY"


def gate_exit_code(result: dict[str, object], fail_on: str = "blocker") -> int:
    verdict = verdict_for(result)
    if verdict == "INCOMPLETE":
        return 2
    if fail_on == "none":
        return 0
    if verdict == "NOT READY":
        return 1
    if fail_on == "warning" and verdict == "READY WITH WARNINGS":
        return 1
    return 0


def enhance_pre_push_audit(
    root: Path,
    result: dict[str, object],
    *,
    max_blob_bytes: int = 8_388_608,
    timeout_seconds: int = 30,
    deadline: float | None = None,
    max_work_units: int = 1_000_000,
    reviewed_findings_sha256: str | None = None,
) -> dict[str, object]:
    """Add index, portable-ignore, AI, sensitive-path and GitHub checks.

    The base scanner already covers the working tree and every blob reachable from
    local refs. This gate closes pre-commit/pre-push gaps without mutating the target.
    """
    repository = GitRepository(
        root,
        timeout_seconds=timeout_seconds,
        deadline=deadline,
        max_git_commands=32,
        max_total_bytes=max(268_435_456, max_blob_bytes * 32),
        max_work_units=max_work_units,
        max_locations=250_000,
    )
    start_refs = repository.ref_snapshot()
    start_inventory = repository.status_entries()
    raw_index = repository.run("ls-files", "--stage", "-z")
    index_entries = _parse_index(raw_index)

    base_inventory = result.get("inventory")
    redacted_start_inventory = _redact_result(
        {"inventory": start_inventory}
    )["inventory"]
    if base_inventory != redacted_start_inventory:
        _append_gap(
            result,
            evidence="repository inventory changed between the base scan and strict pre-push gate",
        )
        result["inventory"] = start_inventory
    coverage = result.get("coverage", {})
    base_refs = coverage.get("refs", []) if isinstance(coverage, dict) else []
    start_ref_names = [ref.name for ref in start_refs]
    redacted_start_ref_names = _redact_result(
        {"refs": start_ref_names}
    )["refs"]
    if sorted(str(ref) for ref in base_refs) != sorted(
        str(ref) for ref in redacted_start_ref_names
    ):
        _append_gap(
            result,
            evidence="local refs changed between the base scan and strict pre-push gate",
        )

    candidates = result.setdefault("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("candidates must be an array")

    object_ids = sorted(
        {
            entry.object_id
            for entry in index_entries
            if entry.stage == 0 and entry.mode != "160000"
        }
    )
    paths_by_object: dict[str, list[str]] = {}
    for entry in index_entries:
        if entry.stage == 0 and entry.mode != "160000":
            paths_by_object.setdefault(entry.object_id, []).append(entry.path)
    metadata = _batch_metadata(repository, object_ids)
    readable_ids: list[str] = []
    for object_id in object_ids:
        object_type, size = metadata.get(object_id, ("missing", 0))
        if object_type != "blob":
            _append_gap(
                result,
                evidence="Git index object is missing or is not a blob",
                object_id=object_id,
            )
            continue
        if size >= 100 * 1024 * 1024:
            candidates.append(
                _candidate(
                    kind="large-file",
                    severity="BLOCKER",
                    action="move",
                    evidence="Git index contains a file at or above 100 MiB",
                    recommendation="Remove it from normal Git history or use a reviewed Git LFS workflow.",
                    object_id=object_id,
                    size=size,
                    paths=sorted(paths_by_object.get(object_id, [])),
                )
            )
        elif size >= 50 * 1024 * 1024:
            candidates.append(
                _candidate(
                    kind="large-file",
                    severity="WARNING",
                    action="review",
                    evidence="Git index contains a file at or above 50 MiB",
                    recommendation="Confirm that the file belongs in Git and consider Git LFS.",
                    object_id=object_id,
                    size=size,
                    paths=sorted(paths_by_object.get(object_id, [])),
                )
            )
        if size > max_blob_bytes:
            affected_paths = sorted(paths_by_object.get(object_id, [])) or [None]
            for affected_path in affected_paths:
                _append_gap(
                    result,
                    evidence="Git index blob exceeds the configured scan limit",
                    path=affected_path,
                    object_id=object_id,
                    size=size,
                )
            continue
        readable_ids.append(object_id)
    contents = _batch_read(repository, readable_ids)
    reviewed_records, reviewed_findings, reviewed_digest = _read_reviewed_findings(
        index_entries, contents, reviewed_findings_sha256, repository,
    )
    candidates.extend(reviewed_findings)
    blob_hashes: dict[str, str] = {}

    def retain_blob_hash(object_id: str, data: bytes) -> None:
        if reviewed_records and object_id not in blob_hashes:
            repository.consume_work(max(1, (len(data) + 4095) // 4096), retained_bytes=len(object_id) + 64)
            blob_hashes[object_id] = hashlib.sha256(data).hexdigest()

    allow_ai_patterns, allowlist_findings = _read_allow_ai_patterns(index_entries, contents)
    candidates.extend(allowlist_findings)
    candidates.extend(_submodule_candidates(index_entries, contents))
    working_findings, working_counts = _working_state_candidates(
        repository,
        start_inventory,
    )
    candidates.extend(working_findings)
    candidates.extend(
        _git_metadata_candidates(
            repository,
            start_refs,
            result,
            max_blob_bytes=max_blob_bytes,
        )
    )

    # The base audit scans reachable blobs with the generic detectors. Provider-
    # specific patterns belong to the strict gate too, including blobs removed
    # from HEAD but still reachable from a local ref. Scan each object once and
    # attach every derived location without retaining secret bytes.
    history = repository.history_snapshot(
        start_refs,
        max_blob_bytes=max_blob_bytes,
    )
    for gap in history.gaps:
        _append_gap(
            result,
            evidence=gap.evidence,
            object_id=gap.object_id,
            size=gap.size,
        )
    for blob in history.blobs:
        if blob.data is None:
            continue
        retain_blob_hash(blob.object_id, blob.data)
        templates = _scan_extra_secrets(
            blob.data,
            path=None,
            object_id=blob.object_id,
            source="history",
            budget=repository,
        )
        for location in blob.locations:
            location_fields = {
                name: value
                for name, value in (
                    ("path", location.path),
                    ("commit", location.commit),
                    ("ref", location.ref),
                    ("mode", location.mode),
                )
                if value is not None
            }
            for template in templates:
                candidate = dict(template)
                candidate.update(location_fields)
                candidates.append(candidate)

    indexed_paths = {
        _normalise_path(entry.path)
        for entry in index_entries
        if entry.stage == 0
    }

    index_secret_templates: dict[str, list[dict[str, object]]] = {}
    for object_id, data in contents.items():
        retain_blob_hash(object_id, data)
        index_secret_templates[object_id] = [
            *_scan_base_secrets(
                data,
                path=None,
                object_id=object_id,
                source="index",
                budget=repository,
            ),
            *_scan_extra_secrets(
                data,
                path=None,
                object_id=object_id,
                source="index",
                budget=repository,
            ),
        ]

    for entry in index_entries:
        if entry.stage != 0:
            candidates.append(
                _candidate(
                    kind="merge-conflict",
                    severity="BLOCKER",
                    action="fix",
                    path=entry.path,
                    evidence="Git index contains an unresolved non-zero stage entry",
                    recommendation="Resolve the conflict and rebuild the index before publication.",
                    stage=entry.stage,
                )
            )
            continue
        if entry.mode == "160000":
            candidates.append(
                _candidate(
                    kind="submodule",
                    severity="WARNING",
                    action="review",
                    path=entry.path,
                    evidence="Git index contains a gitlink/submodule",
                    recommendation="Verify .gitmodules, commit reachability, URL ownership, and publication intent.",
                    object_id=entry.object_id,
                )
            )
            continue
        candidates.extend(
            _classify_extended_path(
                entry.path,
                source="index",
                allow_ai_patterns=allow_ai_patterns,
                object_id=entry.object_id,
            )
        )
        data = contents.get(entry.object_id)
        if data is None:
            continue
        for template in index_secret_templates.get(entry.object_id, []):
            candidate = dict(template)
            candidate["path"] = entry.path
            candidate["mode"] = entry.mode
            candidates.append(candidate)
        if entry.mode == "120000":
            candidates.extend(
                _symlink_candidates(
                    entry.path,
                    data,
                    entry.object_id,
                    indexed_paths,
                )
            )
        candidates.extend(_workflow_candidates(entry.path, data, entry.object_id))

    inventory = result.get("inventory", {})
    if isinstance(inventory, dict):
        for state in ("untracked",):
            for raw_path in inventory.get(state, []):
                candidates.extend(
                    _classify_extended_path(
                        str(raw_path),
                        source=state,
                        allow_ai_patterns=allow_ai_patterns,
                    )
                )

    # .env templates are legitimate only when their content scanners found no secret.
    candidates[:] = [
        item
        for item in candidates
        if not (
            isinstance(item, dict)
            and item.get("kind") == "environment-file"
            and isinstance(item.get("path"), str)
            and _is_env_template(str(item["path"]))
        )
    ]
    template_placeholders = {
        entry.path: _placeholder_assignment_keys(contents[entry.object_id])
        for entry in index_entries
        if entry.stage == 0
        and _is_env_template(entry.path)
        and entry.object_id in contents
    }
    candidates[:] = [
        item
        for item in candidates
        if not (
            isinstance(item, dict)
            and item.get("kind") == "secret"
            and item.get("detector") == "credential-assignment"
            and isinstance(item.get("path"), str)
            and (item.get("line"), item.get("fingerprint"))
            in template_placeholders.get(str(item["path"]), set())
        )
    ]

    candidates.extend(
        _ignore_checks(
            repository,
            result,
            index_entries=index_entries,
            contents=contents,
            allow_ai_patterns=allow_ai_patterns,
        )
    )
    candidates.extend(_portable_path_checks(index_entries))
    gitlink_paths = {
        _normalise_path(entry.path)
        for entry in index_entries
        if entry.stage == 0 and entry.mode == "160000"
    }
    nested_findings, nested_complete = _nested_repository_checks(
        repository.root,
        gitlink_paths=gitlink_paths,
    )
    candidates.extend(nested_findings)
    if not nested_complete:
        _append_gap(
            result,
            evidence="nested-repository filesystem inventory was incomplete or exceeded its entry budget",
        )

    # Upgrade legacy AI findings emitted by the base scanner to the strict gate policy.
    for item in candidates:
        if not isinstance(item, dict) or item.get("kind") != "ai-file":
            continue
        path = item.get("path")
        if isinstance(path, str) and _ai_allowed(path, allow_ai_patterns):
            item["severity"] = "INFO"
            item["action"] = "keep"
            continue
        source = str(item.get("source", ""))
        if item.get("history_only") is True or source == "history":
            item["severity"] = "BLOCKER"
            item["action"] = "purge"
        elif source != "ignored":
            item["severity"] = "BLOCKER"

    # A tracked symlink's Git blob was scanned above; following its filesystem target is
    # neither necessary nor safe. Remove only that obsolete base coverage gap.
    symlink_paths = {entry.path for entry in index_entries if entry.stage == 0 and entry.mode == "120000"}
    coverage = result.get("coverage", {})
    if isinstance(coverage, dict) and isinstance(coverage.get("gaps"), list):
        previous_complete = coverage.get("complete") is True
        previous_gaps = list(coverage["gaps"])
        coverage["gaps"] = [
            gap
            for gap in previous_gaps
            if not (
                isinstance(gap, dict)
                and gap.get("evidence") == "current symbolic link was not followed"
                and gap.get("path") in symlink_paths
            )
        ]
        removed_only_symlink_gaps = (
            len(coverage["gaps"]) < len(previous_gaps) and not coverage["gaps"]
        )
        coverage["complete"] = (
            previous_complete or removed_only_symlink_gaps
        ) and not bool(coverage["gaps"])

    end_index = repository.run("ls-files", "--stage", "-z")
    end_refs = repository.ref_snapshot()
    end_inventory = repository.status_entries()
    if end_index != raw_index or end_refs != start_refs or end_inventory != start_inventory:
        _append_gap(
            result,
            evidence="Git index, repository inventory, or local refs changed during the pre-push gate",
        )

    _apply_reviewed_findings(candidates, reviewed_records, blob_hashes, reviewed_digest, repository)
    result["candidates"] = _deduplicate(
        [item for item in candidates if isinstance(item, dict)]
    )
    result["gate_version"] = GATE_VERSION
    result["verdict"] = verdict_for(result)
    result["pre_push"] = {
        "index_entries": len(index_entries),
        "index_unique_objects": len(object_ids),
        "ai_allowlist": _ALLOW_AI_FILE if allow_ai_patterns else None,
        "reviewed_findings_policy": _REVIEWED_FINDINGS_FILE if reviewed_digest else None,
        "reviewed_findings_sha256": reviewed_digest,
        "strict_ai": True,
        "portable_ignore_provenance_checked": True,
        "working_state": working_counts,
    }
    return redact_pre_push_result(result)
