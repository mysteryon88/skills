"""Validate and render one finding. Report text is data, never executable input."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import sys
import tempfile
import textwrap
from urllib.parse import quote


ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z", re.ASCII)
DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
STATUSES = {"source-supported", "observed", "hypothetical", "unknown"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def obj(value, fields, label):
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == set(fields.split()), f"{label} fields must be exactly: {fields}")


def text(value, label, empty=False):
    require(isinstance(value, str) and (empty or bool(value.strip())), f"{label} must be a {'possibly empty ' if empty else 'nonempty '}string")
    require(not any(ord(c) < 32 and c not in "\n\r\t" or 0xD800 <= ord(c) <= 0xDFFF for c in value), f"{label} contains unsupported control or surrogate characters")


def identifier(value, label):
    require(isinstance(value, str) and ID.fullmatch(value), f"{label} must be an ASCII identifier")


def array(value, label):
    require(isinstance(value, list), f"{label} must be an array")


def local_path(value):
    text(value, "path")
    require(not any(ord(c) < 32 for c in value), "path contains control characters")
    posix = value.startswith("/") and not value.startswith("//")
    windows = bool(re.match(r"^[A-Za-z]:[/\\]", value)) and PureWindowsPath(value).is_absolute()
    require(posix or windows, "path must be a POSIX or drive-absolute local path")
    if windows:
        require(not any(c in value[2:] for c in ':<>"|?*'), "path contains invalid drive path characters")
    if os.name == "nt" and posix:
        require(":" not in value, "rooted Windows path must not reference an alternate stream")
    require(not value.startswith("/\\"), "UNC/device paths are not supported")


def digest(value, label, nullable=False):
    require(nullable and value is None or isinstance(value, str) and DIGEST.fullmatch(value), f"{label} must be a lowercase SHA-256{' or null' if nullable else ''}")


def refs(value, known, label):
    array(value, label)
    for item in value:
        identifier(item, label)
        require(item in known, f"{label}: unknown reference {item}")
    require(len(value) == len(set(value)), f"{label} contains duplicate references")


def indexed(items, fields, label):
    array(items, label)
    result = {}
    for item in items:
        obj(item, fields, label)
        identifier(item["id"], f"{label}.id")
        require(item["id"] not in result, f"duplicate {label} ID: {item['id']}")
        result[item["id"]] = item
    return result


def claim(item, evidence, gaps, label, excerpts=False):
    require(isinstance(item["status"], str) and item["status"] in STATUSES, f"{label}: invalid epistemic status")
    refs(item["evidence_ids"], evidence, f"{label}.evidence_ids")
    refs(item["gap_ids"], gaps, f"{label}.gap_ids")
    if item["status"] in {"hypothetical", "unknown"}:
        require(item["gap_ids"], f"{label}: hypothetical/unknown requires a gap")
    else:
        kind = "source" if item["status"] == "source-supported" else "runtime"
        positive = [e for e in item["evidence_ids"] if evidence[e]["kind"] == kind and evidence[e]["sha256"] is not None]
        require(positive, f"{label}: {item['status']} requires hashed {kind} evidence")
        if excerpts and kind == "source":
            require(any(s["evidence_id"] in positive for s in item["sources"]), f"{label}: source-supported step requires matching source excerpt")


def validate_report(data):
    obj(data, "schema_version finding context prerequisites entities evidence steps outcome gaps author", "report")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1, "schema_version must be 1")
    text(data["author"], "author")
    obj(data["finding"], "id title summary", "finding")
    identifier(data["finding"]["id"], "finding.id")
    for key in ("title", "summary"):
        text(data["finding"][key], f"finding.{key}")
    obj(data["context"], "repository revision environment reproduction_status", "context")
    for key in ("repository", "revision", "environment"):
        text(data["context"][key], f"context.{key}")
    require(data["context"]["reproduction_status"] in ("not-run", "run"), "invalid reproduction_status")
    entities = indexed(data["entities"], "id name kind", "entities")
    require(entities, "entities must not be empty")
    for item in entities.values():
        text(item["name"], "entity.name")
        text(item["kind"], "entity.kind")
    gaps = indexed(data["gaps"], "id description needed verification impact", "gaps")
    for item in gaps.values():
        for key in ("description", "needed", "verification", "impact"):
            text(item[key], f"gap.{key}")
    evidence = indexed(data["evidence"], "id kind path sha256 description", "evidence")
    for item in evidence.values():
        require(item["kind"] in ("source", "runtime"), "evidence.kind must be source or runtime")
        local_path(item["path"])
        digest(item["sha256"], "evidence.sha256", nullable=True)
        text(item["description"], "evidence.description")
    prerequisites = indexed(data["prerequisites"], "id description status evidence_ids gap_ids", "prerequisites")
    for item in prerequisites.values():
        text(item["description"], "prerequisite.description")
        claim(item, evidence, gaps, "prerequisite")
    steps = indexed(data["steps"], "id title from to kind status input operation checks state_before state_after output next sources evidence_ids gap_ids", "steps")
    require(steps, "steps must not be empty")
    for i, step in enumerate(data["steps"]):
        label = f"step {step['id']}"
        for key in ("title", "operation", "state_before", "state_after", "output"):
            text(step[key], f"{label}.{key}")
        for key in ("from", "to"):
            identifier(step[key], f"{label}.{key}")
            require(step[key] in entities, f"{label}: unknown entity {step[key]}")
        require(step["kind"] in ("call", "message", "return", "internal"), f"{label}: invalid kind")
        expected = data["steps"][i + 1]["id"] if i + 1 < len(steps) else None
        require(step["next"] == expected, f"{label}.next must match array order (terminal null)")
        obj(step["input"], "format value", f"{label}.input")
        text(step["input"]["format"], "input.format")
        text(step["input"]["value"], "input.value", empty=True)
        array(step["checks"], "checks")
        for check in step["checks"]:
            obj(check, "condition values result", "check")
            for key in check:
                text(check[key], f"check.{key}")
        array(step["sources"], "sources")
        refs(step["evidence_ids"], evidence, f"{label}.evidence_ids")
        for source in step["sources"]:
            obj(source, "path symbol start_line end_line language code evidence_id", "source")
            local_path(source["path"])
            for key in ("symbol", "language", "code"):
                text(source[key], f"source.{key}")
            for key in ("start_line", "end_line"):
                require(type(source[key]) is int and source[key] >= 1, f"source.{key} must be a positive integer")
            require(source["end_line"] >= source["start_line"], "source end_line precedes start_line")
            identifier(source["evidence_id"], "source.evidence_id")
            entry = evidence.get(source["evidence_id"])
            require(entry is not None and entry["kind"] == "source" and entry["sha256"] is not None and entry["path"] == source["path"], "source must match hashed source evidence path")
            require(source["evidence_id"] in step["evidence_ids"], "source evidence must be referenced by its step")
        claim(step, evidence, gaps, label, excerpts=True)
    obj(data["outcome"], "summary status evidence_ids gap_ids verification", "outcome")
    text(data["outcome"]["summary"], "outcome.summary")
    text(data["outcome"]["verification"], "outcome.verification")
    claim(data["outcome"], evidence, gaps, "outcome")
    observations = [*prerequisites.values(), *steps.values(), data["outcome"]]
    if data["context"]["reproduction_status"] == "run":
        require(any(e["kind"] == "runtime" and e["sha256"] for e in evidence.values()) and any(c["status"] == "observed" for c in observations), "run requires hashed runtime evidence and observations")
    else:
        require(not any(c["status"] == "observed" for c in observations), "not-run cannot contain observed claims")
    return data


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"nonfinite JSON number: {value}")


def _float(value):
    result = float(value)
    require(math.isfinite(result), "nonfinite JSON number")
    return result


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)


def load_report(path):
    return validate_report(_load_json(path))


def literal(value):
    value = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#+.!|~$\-])", r"\\\1", value).replace("\r", "&#13;").replace("\n", "&#10;")


def fence(value, language=""):
    # A longer delimiter keeps nested payload fences literal.
    longest = max((len(m.group()) for m in re.finditer(r"`+", value)), default=0)
    delimiter = "`" * max(3, longest + 1)
    return f"{delimiter}{language}\n{value.replace(chr(13), '&#13;')}\n{delimiter}\n"


def mermaid(value, limit=None):
    flat = " ".join(str(value).split())
    if limit is not None and len(flat) > limit:
        flat = flat[:limit - 3] + "..."
    lines = []
    for line in textwrap.wrap(flat, width=36, break_on_hyphens=False):
        encoded = "".join(c if c.isascii() and c.isalnum() or c == " " else f"#{ord(c)};" for c in line)
        # Only generated breaks are markup; report content remains entity-escaped.
        lines.append(re.sub(r"\bend\b", "#101;nd", encoded))
    return "<br/>".join(lines)


def source_uri(path, line):
    normalized = path.replace("\\", "/") if PureWindowsPath(path).drive else path
    return quote(normalized, safe="/:") + f":{line}"


def fields(values):
    lines = []
    for key, value in values.items():
        label = key.replace("_", " ")
        shown = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) or value is None else str(value)
        lines.append(f"- **{label}:** {literal(shown)}")
    return "\n".join(lines) + "\n"


def render_report(data):
    validate_report(data)
    parts = [f"# {literal(data['finding']['title'])}\n", fields({"schema_version": data["schema_version"], "author": data["author"], "finding_id": data["finding"]["id"], "summary": data["finding"]["summary"]}), "## Context\n", fields(data["context"]), "## Prerequisites\n"]
    for item in data["prerequisites"]:
        parts.append(fields(item))
    if not data["prerequisites"]:
        parts.append("None declared; reviewer must check completeness.\n")
    parts.append("## Entities\n")
    for item in data["entities"]:
        parts.append(fields(item))
    parts.append("## Evidence and provenance\n")
    for item in data["evidence"]:
        parts.append(fields(item))
    if not data["evidence"]:
        parts.append("None declared.\n")
    participants = {item["id"]: f"p{i}" for i, item in enumerate(data["entities"])}
    diagram = ["sequenceDiagram"]
    for item in data["entities"]:
        label = mermaid(item["id"])
        diagram.append(f"    participant {participants[item['id']]} as {label}")
    for i, step in enumerate(data["steps"], 1):
        arrow = "-->>" if step["kind"] == "return" else "->>"
        label = "<br/>".join((mermaid(f"{i}. [{step['id']}]"), mermaid(step["title"], limit=72), mermaid(f"{step['status']}; {step['kind']}")))
        diagram.append(f"    {participants[step['from']]}{arrow}{participants[step['to']]}: {label}")
        note = mermaid("Checks and state: see numbered detail")
        diagram.append(f"    Note over {participants[step['to']]}: {note}")
    parts += ["## Selected path\n", "Arrows describe the classified step; a message arrow alone does not establish receipt or successful completion. The diagram is an overview using stable entity IDs and compact step titles. Full entity names appear above; the matching numbered step below contains the full title, checks, values and state.\n", fence("\n".join(diagram), "mermaid"), "## Steps\n"]
    for i, step in enumerate(data["steps"], 1):
        parts += [f"### {i}. {literal(step['id'])}: {literal(step['title'])}\n", fields({k: v for k, v in step.items() if k not in ("title", "input", "checks", "sources")}), "#### Input\n", fields({"format": step["input"]["format"]}), fence(step["input"]["value"]), "#### Checks\n"]
        for check in step["checks"]:
            parts.append(fields(check))
        if not step["checks"]:
            parts.append("No checks declared; see operation and epistemic status.\n")
        parts.append("#### Sources\n")
        for source in step["sources"]:
            parts += [f"[{literal(source['path'] + ':' + str(source['start_line']))}](<{source_uri(source['path'], source['start_line'])}>)\n", fields({k: v for k, v in source.items() if k != "code"}), fence(source["code"])]
        if not step["sources"]:
            parts.append("No source excerpt; see status, evidence and gaps.\n")
    parts += ["## Outcome\n", fields(data["outcome"]), "## Gaps and verification\n"]
    for item in data["gaps"]:
        parts.append(fields(item))
    if not data["gaps"]:
        parts.append("None declared.\n")
    return "\n".join(parts)


def select_step(data, step_id):
    validate_report(data)
    for i, step in enumerate(data["steps"]):
        if step["id"] == step_id:
            return {"schema_version": data["schema_version"], "finding": data["finding"], "context": data["context"], "author": data["author"], "step": step, "previous": data["steps"][i - 1]["id"] if i else None, "next": step["next"], "entities": [e for e in data["entities"] if e["id"] in (step["from"], step["to"])], "evidence": [e for e in data["evidence"] if e["id"] in step["evidence_ids"]], "gaps": [g for g in data["gaps"] if g["id"] in step["gap_ids"]]}
    raise ValueError(f"unknown step ID: {step_id}")


def _reject_links(path):
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0), f"path must not use symlink, junction or reparse point: {candidate}")


def _protected(data, report_path):
    return [Path(report_path), *(Path(e["path"]) for e in data["evidence"]), *(Path(s["path"]) for step in data["steps"] for s in step["sources"])]


def _output_path(output, protected):
    path = Path(os.path.abspath(output))
    require(path.suffix.lower() == ".md", "output must have .md extension")
    _reject_links(path)
    require(path.parent.is_dir(), "output parent directory must already exist")
    for item in protected:
        require(path != Path(os.path.abspath(item)), "output collides with a protected input")
        if path.exists() and item.exists():
            require(not os.path.samefile(path, item), "output aliases a protected input")
    if path.exists():
        require(stat.S_ISREG(path.lstat().st_mode), "output must be a regular file")
    return path


def write_markdown(data, report_path, output, replace=False):
    rendered = render_report(data).encode("utf-8")
    path = _output_path(output, _protected(data, report_path))
    if path.exists():
        if path.read_bytes() == rendered:
            return
        require(replace, "different output already exists; use --replace explicitly")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix="walkthrough-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(rendered)
            _output_path(path, _protected(data, report_path))
            try:
                os.replace(temporary, path)
            except OSError as error:
                raise ValueError(f"cannot replace output atomically; existing bytes preserved: {error}") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    else:
        with path.open("xb") as stream:
            stream.write(rendered)


def check_markdown(data, report_path, markdown_path, receipt_path=None):
    protected = _protected(data, report_path)
    if receipt_path is not None:
        protected.append(Path(receipt_path))
    path = _output_path(markdown_path, protected)
    require(path.read_bytes() == render_report(data).encode("utf-8"), "stale Markdown: regenerate from current JSON")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_check(data, report_path, markdown_path, receipt_path):
    check_markdown(data, report_path, markdown_path, receipt_path)
    receipt = _load_json(receipt_path)
    obj(receipt, "schema_version author reviewer verdict json_sha256 markdown_sha256 evidence_sha256 findings", "receipt")
    require(type(receipt["schema_version"]) is int and receipt["schema_version"] == 1, "receipt.schema_version must be 1")
    for key in ("author", "reviewer"):
        text(receipt[key], f"receipt.{key}")
    require(receipt["author"] == data["author"] and receipt["reviewer"].strip().casefold() != receipt["author"].strip().casefold(), "receipt requires matching author and different reviewer identity")
    require(receipt["verdict"] in ("accepted", "changes-requested", "unreviewed"), "invalid receipt verdict")
    array(receipt["findings"], "receipt.findings")
    for item in receipt["findings"]:
        text(item, "receipt finding")
    require(receipt["verdict"] == "accepted" and not receipt["findings"], "review not accepted or unresolved findings remain")
    for key, path in (("json_sha256", report_path), ("markdown_sha256", markdown_path)):
        digest(receipt[key], f"receipt.{key}")
        require(receipt[key] == sha256(path), f"stale receipt {key}")
    require(isinstance(receipt["evidence_sha256"], dict), "receipt.evidence_sha256 must be an object")
    require(set(receipt["evidence_sha256"]) == {e["id"] for e in data["evidence"]}, "receipt evidence ID set differs")
    for entry in data["evidence"]:
        fingerprint = receipt["evidence_sha256"][entry["id"]]
        digest(fingerprint, "receipt evidence fingerprint", nullable=True)
        require(fingerprint == entry["sha256"], "receipt evidence fingerprint differs from report")
        path = Path(entry["path"])
        _reject_links(path)
        if fingerprint is None:
            require(not path.exists(), "declared missing evidence is now available; update report and review")
        else:
            require(path.is_file() and stat.S_ISREG(path.lstat().st_mode), f"reviewed evidence is not a regular file: {path}")
            require(sha256(path) == fingerprint, f"reviewed evidence changed: {entry['id']}")
    for step in data["steps"]:
        for source in step["sources"]:
            lines = Path(source["path"]).read_text(encoding="utf-8").splitlines()
            require(source["end_line"] <= len(lines), "source excerpt range exceeds current file")
            actual = "\n".join(lines[source["start_line"] - 1:source["end_line"]])
            excerpt = source["code"].replace("\r\n", "\n")
            require(excerpt in (actual, actual + "\n"), f"source excerpt differs at {source['path']}:{source['start_line']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "render", "check", "show", "review-check"):
        command = commands.add_parser(name)
        command.add_argument("report")
        if name == "render":
            command.add_argument("--output", required=True)
            command.add_argument("--replace", action="store_true")
        elif name in ("check", "review-check"):
            command.add_argument("markdown")
            if name == "review-check":
                command.add_argument("receipt")
        elif name == "show":
            selection = command.add_mutually_exclusive_group(required=True)
            selection.add_argument("--step")
            selection.add_argument("--index", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = load_report(args.report)
        if args.command == "render":
            write_markdown(data, args.report, args.output, args.replace)
        elif args.command == "check":
            check_markdown(data, args.report, args.markdown)
        elif args.command == "review-check":
            review_check(data, args.report, args.markdown, args.receipt)
        elif args.command == "show":
            selected = [{"ordinal": i, "id": s["id"], "title": s["title"], "status": s["status"], "next": s["next"]} for i, s in enumerate(data["steps"], 1)] if args.index else select_step(data, args.step)
            print(json.dumps(selected, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError, RecursionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


# Compatibility implementation used only by explicitly named read-only commands.
