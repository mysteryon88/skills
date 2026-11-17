#!/usr/bin/env python3
"""Read-only triage scanner for refactor-codebase; standard library only.

Finds large files, Python functions/classes with structural warning signals,
TODO markers and exact normalized repeated text blocks. These are candidates,
not confirmed defects. No files are modified.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import re
import stat
import sys
from collections import defaultdict
from pathlib import Path

with contextlib.suppress(AttributeError):
    sys.stdout.reconfigure(encoding="utf-8")

SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "vendor",
             "dist", "build", "coverage", ".next", ".nuxt", ".cache", "__pycache__",
             ".tox", ".mypy_cache", ".pytest_cache", "target", "bin", "obj"}
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java",
                   ".kt", ".go", ".rs", ".rb", ".php", ".cs", ".swift", ".scala",
                   ".vue", ".svelte"}
TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
MAX_FILE_BYTES = 2_000_000
MAX_AST_BYTES = 512_000
MAX_DIRS = 20_000
MAX_DIR_ENTRIES = 20_000
MAX_ENTRIES = 200_000
MAX_LINE_CHARS = 512
MAX_FINDINGS = 2_000
MAX_TODOS = 500
MAX_DUPLICATE_CANDIDATES = 200
MAX_DUPLICATE_LOCATIONS = 20
MAX_LARGEST_FILES = 30
# Bump the revision when scan selection, limits, or result semantics change.
SCANNER_REVISION = "refactor-scan-v1"
DUPLICATE_ALGORITHM = "normalized-lines-sha256-v1"


def is_redirect(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def checked_root(value):
    """Reject links in the user-supplied path rather than silently following them."""
    path = Path(os.path.abspath(value))
    info = None
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if is_redirect(info):
            raise OSError("Redirected root path refused")
    if info is None or not stat.S_ISDIR(info.st_mode):
        raise OSError("Root is not a directory")
    # Do not resolve the path after checking it: a swapped final component could
    # redirect resolve() outside the intended root. Directory access is re-opened
    # component by component without following links in safe_directory().
    return path


@contextlib.contextmanager
def posix_directory(root: Path, relative: Path):
    """Open each directory without following links, anchored at the filesystem root."""
    if not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise OSError("Safe directory opening is unavailable")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors = []
    try:
        fd = os.open(root.anchor, flags)
        descriptors.append(fd)
        for part in (*root.parts[1:], *relative.parts):
            if part in ("", "."):
                continue
            if part == "..":
                raise OSError("Parent path is not allowed")
            fd = os.open(part, flags, dir_fd=fd)
            descriptors.append(fd)
        yield fd
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


@contextlib.contextmanager
def windows_directory(path: Path):
    """Hold each ancestor without delete-sharing while accessing the directory."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    invalid = ctypes.c_void_p(-1).value
    handles = []
    try:
        for part in (*reversed(path.parents), path):
            # FILE_LIST_DIRECTORY makes Windows enforce the no-delete share mode.
            handle = create(str(part), 0x1, 0x1 | 0x2, None, 3, 0x02000000 | 0x00200000, None)
            if handle == invalid:
                raise OSError(ctypes.get_last_error(), "Cannot safely open directory")
            handles.append(handle)
            info = part.lstat()
            if is_redirect(info) or not stat.S_ISDIR(info.st_mode):
                raise OSError("Redirected or non-directory path")
        yield
    finally:
        for handle in reversed(handles):
            close(handle)


@contextlib.contextmanager
def safe_directory(root: Path, relative: Path):
    if os.name == "nt":
        with windows_directory(root / relative):
            yield root / relative
    else:
        with posix_directory(root, relative) as fd:
            yield fd


def list_directory(root: Path, relative: Path, state):
    with safe_directory(root, relative) as directory, os.scandir(directory) as entries:
        result = []
        for count, entry in enumerate(entries):
            if count >= MAX_DIR_ENTRIES or state["entries_seen"] >= MAX_ENTRIES:
                cutoff = (
                    "max_entries"
                    if state["entries_seen"] >= MAX_ENTRIES
                    else "max_directory_entries"
                )
                state["cutoffs"].add(cutoff)
                break
            state["entries_seen"] += 1
            if entry.name.startswith(".") or entry.name.lower() in SKIP_DIRS:
                continue
            try:
                info = (
                    (root / relative / entry.name).lstat()
                    if os.name == "nt" else entry.stat(follow_symlinks=False)
                )
                result.append((entry.name, info))
            except OSError:
                state["skipped"]["unreadable"] += 1
        return sorted(result, key=lambda item: (item[0].casefold(), item[0]))


def iter_files(root: Path, state):
    stack = [Path()]
    directories = 0
    while stack:
        relative = stack.pop()
        if directories >= MAX_DIRS:
            state["cutoffs"].add("max_directories")
            return
        directories += 1
        try:
            entries = list_directory(root, relative, state)
        except OSError:
            state["skipped"]["unreadable"] += 1
            continue
        children = []
        for name, info in entries:
            rel = relative / name
            if is_redirect(info):
                state["skipped"]["redirected"] += 1
            elif stat.S_ISDIR(info.st_mode):
                children.append(rel)
            elif Path(name).suffix.lower() in SOURCE_SUFFIXES:
                if not stat.S_ISREG(info.st_mode):
                    state["skipped"]["special"] += 1
                else:
                    yield rel, info
        if "max_entries" in state["cutoffs"]:
            return
        stack.extend(reversed(children))


def safe_read(root: Path, relative: Path, expected, limit: int):
    """Read only the same regular file observed in an anchored directory."""
    if is_redirect(expected) or not stat.S_ISREG(expected.st_mode):
        raise OSError("Redirect or special file refused")
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        with windows_directory(root / relative.parent):
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            create = kernel.CreateFileW
            create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            create.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = create(str(root / relative), 0x80000000, 0x1 | 0x2, None, 3, 0x00200000, None)
            if handle == ctypes.c_void_p(-1).value:
                raise OSError(ctypes.get_last_error(), "Cannot safely open file")
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
            except OSError:
                kernel.CloseHandle(handle)
                raise
            return read_descriptor(fd, expected, limit)
    with posix_directory(root, relative.parent) as parent:
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(relative.name, flags, dir_fd=parent)
        return read_descriptor(fd, expected, limit)


def read_descriptor(fd, expected, limit):
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (is_redirect(opened) or not stat.S_ISREG(opened.st_mode)
                or not opened.st_ino
                or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
                or (opened.st_size, opened.st_mtime_ns)
                != (expected.st_size, expected.st_mtime_ns)):
            raise OSError("File changed during scan")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise OSError("File grew beyond the limit")
        after = os.fstat(stream.fileno())
        if (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
            raise OSError("File changed during read")
        return data


def write_report(project: Path, destination: Path, content: str):
    """Create a new Windows report directly under the project's existing .tmp."""
    if os.name != "nt":
        raise ValueError("File reports are supported only on Windows; use stdout on POSIX")
    temp = project / ".tmp"
    destination = destination if destination.is_absolute() else project / destination
    destination = Path(os.path.abspath(destination))
    if destination.parent != temp or destination.name in ("", ".", ".."):
        raise ValueError("Report must be a new file directly under <project>/.tmp")
    name = destination.name
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                *(f"lpt{i}" for i in range(1, 10))}
    if (name.endswith((".", " ")) or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
            or name.split(".")[0].lower() in reserved):
        raise ValueError("Unsafe report filename")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    with windows_directory(temp):
        fd = os.open(destination, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)


def nesting_depth(node: ast.AST) -> int:
    controls = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With,
                ast.AsyncWith, ast.ExceptHandler)
    controls += tuple(getattr(ast, name) for name in ("Match", "TryStar") if hasattr(ast, name))
    maximum = 0

    def walk(current, depth):
        nonlocal maximum
        next_depth = depth + (1 if isinstance(current, controls) else 0)
        maximum = max(maximum, next_depth)
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            walk(child, next_depth)

    walk(node, 0)
    return maximum


def python_findings(rel: str, source: str):
    found = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [{"kind": "python_parse_error", "file": rel,
                 "line": exc.lineno, "message": "Python syntax error"}]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            args = node.args
            count = (len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
                     + (1 if args.vararg else 0) + (1 if args.kwarg else 0))
            depth = nesting_depth(node)
            loc = end - start + 1
            if loc >= 40 or count >= 6 or depth >= 4:
                found.append({"kind": "python_function_candidate", "file": rel,
                              "start_line": start, "end_line": end,
                              "loc": loc, "parameter_count": count,
                              "max_control_nesting": depth})
        elif isinstance(node, ast.ClassDef):
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            methods = [
                n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            loc = end - start + 1
            if loc >= 250 or len(methods) >= 15:
                found.append({"kind": "python_class_candidate", "file": rel,
                              "start_line": start, "end_line": end,
                              "loc": loc, "method_count": len(methods)})
    return found


def bounded_int(minimum, maximum):
    def parse(value):
        try:
            number = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError("Expected an integer") from error
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"Expected {minimum}..{maximum}")
        return number
    return parse


def scan(root: Path, max_files: int, max_total_bytes: int, duplicate_lines: int, max_windows: int):
    state = {"skipped": defaultdict(int), "cutoffs": set(), "entries_seen": 0}
    inventory, findings, todos = [], [], []
    blocks = {}
    total_bytes = 0
    windows = 0
    considered = 0
    for relative, info in iter_files(root, state):
        if considered >= max_files:
            state["cutoffs"].add("max_files")
            break
        considered += 1
        if info.st_size > MAX_FILE_BYTES:
            state["skipped"]["file_too_large"] += 1
            continue
        if total_bytes + info.st_size > max_total_bytes:
            state["cutoffs"].add("max_total_bytes")
            break
        try:
            data = safe_read(
                root, relative, info, min(MAX_FILE_BYTES, max_total_bytes - total_bytes)
            )
        except OSError:
            state["skipped"]["unreadable_or_changed"] += 1
            continue
        total_bytes += len(data)
        try:
            source = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            state["skipped"]["non_utf8"] += 1
            continue
        rel = relative.as_posix()
        lines = source.splitlines()
        inventory.append({"file": rel, "loc": len(lines), "bytes": len(data)})
        if relative.suffix.lower() == ".py":
            if len(data) > MAX_AST_BYTES:
                state["skipped"]["ast_too_large"] += 1
            else:
                try:
                    candidates = python_findings(rel, source)
                    if any(item["kind"] == "python_parse_error" for item in candidates):
                        state["skipped"]["python_parse_error"] += 1
                    if len(findings) + len(candidates) > MAX_FINDINGS:
                        state["cutoffs"].add("max_python_candidates")
                    findings.extend(candidates[:max(0, MAX_FINDINGS - len(findings))])
                except (MemoryError, RecursionError, ValueError):
                    state["skipped"]["ast_error"] += 1
        for line_no, line in enumerate(lines, 1):
            match = TODO_RE.search(line)
            if match:
                if len(todos) < MAX_TODOS:
                    todos.append({"kind": "todo_marker", "file": rel,
                                  "line": line_no, "marker": match.group(1)})
                else:
                    state["cutoffs"].add("max_todo_markers")
        normalized = [re.sub(r"\s+", " ", line.strip()) if len(line) <= MAX_LINE_CHARS else None
                      for line in lines]
        for index in range(max(0, len(normalized) - duplicate_lines + 1)):
            block = normalized[index:index + duplicate_lines]
            if any(line is None for line in block):
                state["cutoffs"].add("long_duplicate_lines")
                continue
            if not all(block) or all(
                line in {"{", "}", "};", ")", "],", "},", "pass"} for line in block
            ):
                continue
            if windows >= max_windows:
                state["cutoffs"].add("max_duplicate_windows")
                break
            windows += 1
            key = hashlib.sha256("\n".join(block).encode("utf-8")).digest()
            group = blocks.setdefault(
                key, {"first_file": rel, "different_file": False, "locations": []}
            )
            if group["first_file"] != rel:
                group["different_file"] = True
            location = {"file": rel, "start_line": index + 1}
            if len(group["locations"]) < MAX_DUPLICATE_LOCATIONS:
                group["locations"].append(location)
            else:
                state["cutoffs"].add("max_locations_per_duplicate")
                if group["different_file"] and all(
                    item["file"] == group["first_file"] for item in group["locations"]
                ):
                    group["locations"][-1] = location
    duplicates = [
        {"kind": "normalized_text_duplicate_candidate", "line_count": duplicate_lines,
         "locations": group["locations"],
         "note": "Normalized text only; inspect semantic equivalence manually."}
        for group in blocks.values() if group["different_file"]
    ]
    duplicates.sort(key=lambda group: (-len(group["locations"]), group["locations"][0]["file"],
                                       group["locations"][0]["start_line"]))
    if len(duplicates) > MAX_DUPLICATE_CANDIDATES:
        state["cutoffs"].add("max_duplicate_candidates")
    inventory.sort(key=lambda item: (-item["loc"], item["file"]))
    skipped = dict(sorted((key, value) for key, value in state["skipped"].items() if value))
    cutoffs = sorted(state["cutoffs"])
    return {
        "root": str(root), "files_scanned": len(inventory), "files_considered": considered,
        "bytes_scanned": total_bytes,
        "partial": bool(skipped or cutoffs), "skipped": skipped, "cutoffs": cutoffs,
        "limits": {"max_files": max_files, "max_total_bytes": max_total_bytes,
                   "max_file_bytes": MAX_FILE_BYTES, "max_duplicate_windows": max_windows},
        "scan_profile": {
            "scanner_revision": SCANNER_REVISION,
            "duplicate_algorithm": DUPLICATE_ALGORITHM,
            "python_version": ".".join(str(part) for part in sys.version_info[:3]),
            "platform": sys.platform,
            "duplicate_lines": duplicate_lines,
            "max_files": max_files,
            "max_total_bytes": max_total_bytes,
            "max_duplicate_windows": max_windows,
            "source_suffixes": sorted(SOURCE_SUFFIXES),
            "excluded_directories": sorted(SKIP_DIRS),
            "exclude_hidden": True,
            "fixed_limits": {
                "max_file_bytes": MAX_FILE_BYTES,
                "max_ast_bytes": MAX_AST_BYTES,
                "max_directories": MAX_DIRS,
                "max_directory_entries": MAX_DIR_ENTRIES,
                "max_entries": MAX_ENTRIES,
                "max_line_chars": MAX_LINE_CHARS,
                "max_python_candidates": MAX_FINDINGS,
                "max_todo_markers": MAX_TODOS,
                "max_duplicate_candidates": MAX_DUPLICATE_CANDIDATES,
                "max_duplicate_locations": MAX_DUPLICATE_LOCATIONS,
                "max_largest_files": MAX_LARGEST_FILES,
            },
        },
        "largest_files": inventory[:MAX_LARGEST_FILES],
        "largest_files_truncated": len(inventory) > MAX_LARGEST_FILES,
        "python_candidates": findings,
        "duplicate_candidates": duplicates[:MAX_DUPLICATE_CANDIDATES], "todo_markers": todos,
        "limitations": [
            "Heuristics identify candidates, not confirmed defects.",
            "Hidden, generated, dependency and vendor directories are excluded.",
            "Python AST metrics are structural and do not understand business meaning.",
            "Normalized duplicates can be false positives; semantic duplicates can be missed.",
            "File paths can contain sensitive information; review the report before sharing it.",
            "Dynamic calls, reflection, generated code and runtime configuration "
            "need separate inspection.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Directory to inspect (default: .)")
    parser.add_argument("--project-root", help="Project root; required with --json")
    parser.add_argument("--json", dest="json_path", help="New report directly under <project>/.tmp")
    parser.add_argument("--max-files", type=bounded_int(1, 100_000), default=20_000)
    parser.add_argument(
        "--max-total-bytes", type=bounded_int(1, 256 * 1024 * 1024), default=64 * 1024 * 1024
    )
    parser.add_argument("--duplicate-lines", type=bounded_int(2, 32), default=6)
    parser.add_argument("--max-duplicate-windows", type=bounded_int(1, 500_000), default=100_000)
    args = parser.parse_args()
    if args.json_path and os.name != "nt":
        parser.error("--json is supported only on Windows; use stdout on POSIX")
    try:
        root = checked_root(args.root)
        project = checked_root(args.project_root) if args.project_root else None
    except OSError as error:
        print(f"Invalid root: {error}", file=sys.stderr)
        return 2
    if args.json_path and project is None:
        parser.error("--project-root is required with --json")
    if project is not None and (not project.is_dir() or not root.is_relative_to(project)):
        parser.error("--root must be inside the existing --project-root")
    report = scan(
        root, args.max_files, args.max_total_bytes, args.duplicate_lines, args.max_duplicate_windows
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_path:
        try:
            write_report(project, Path(args.json_path), rendered + "\n")
        except (OSError, ValueError) as error:
            print(f"Report not written: {error}", file=sys.stderr)
            return 2
    print(rendered)
    return int(report["partial"])


if __name__ == "__main__":
    raise SystemExit(main())
