#!/usr/bin/env python3
"""Read-only detector for TON zero-knowledge project structure and artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".venv",
    "node_modules",
    "target",
    "dist",
    "build",
    ".next",
    "coverage",
    ".turbo",
    ".cache",
}

CURVE_ALIASES = {
    "bls12381": "bls12-381",
    "bn128": "bn254",
    "bn254": "bn254",
    "altbn128": "bn254",
}

NATIVE_VK_NAMES = {
    "vk.bin",
    "verifying_key.bin",
    "verification_key.bin",
}

PUBLIC_SIGNAL_NAMES = {
    "public.json",
    "public_signals.json",
    "public-signals.json",
    "publicsignals.json",
}

PROOF_NAMES = {
    "proof.json",
    "proof_groth16.json",
    "proof_plonk.json",
    "groth16_proof.json",
    "plonk_proof.json",
}

VK_NAMES = {
    "verification_key.json",
    "verification-key.json",
    "verifying_key.json",
    "verifying-key.json",
    "verification_key_gnark.json",
    "groth16_artifacts.json",
    "vk.json",
}

PACKAGE_MANIFEST_NAMES = {"package.json", "go.mod", "cargo.toml", "acton.toml"}


def _relative_display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix() or "."
    except ValueError:
        return str(path)


def _iter_files(
    root: Path,
    max_files: int,
    scan_errors: list[dict[str, str]],
    skipped_paths: list[dict[str, str]],
) -> Iterable[Path]:
    """Yield regular files deterministically without following symlinks."""

    seen = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name.lower())
        except (OSError, PermissionError) as exc:
            scan_errors.append(
                {
                    "path": _relative_display(directory, root),
                    "operation": "list-directory",
                    "error": str(exc),
                }
            )
            continue

        child_dirs: list[Path] = []
        for entry in entries:
            try:
                if entry.is_symlink():
                    skipped_paths.append(
                        {
                            "path": _relative_display(Path(entry.path), root),
                            "reason": "symlink",
                        }
                    )
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in EXCLUDED_DIRS:
                        skipped_paths.append(
                            {
                                "path": _relative_display(Path(entry.path), root),
                                "reason": "excluded-directory",
                            }
                        )
                    else:
                        child_dirs.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
            except OSError as exc:
                scan_errors.append(
                    {
                        "path": _relative_display(Path(entry.path), root),
                        "operation": "inspect-entry",
                        "error": str(exc),
                    }
                )
                continue

            seen += 1
            if seen > max_files:
                return
            yield Path(entry.path)

        # Stack is LIFO; reverse to visit lexicographically smaller directories first.
        stack.extend(reversed(child_dirs))


def _read_small_text(
    path: Path,
    limit: int = 2_000_000,
    *,
    root: Path | None = None,
    scan_errors: list[dict[str, str]] | None = None,
    skipped_paths: list[dict[str, str]] | None = None,
) -> str:
    try:
        if path.stat().st_size > limit:
            if skipped_paths is not None and root is not None:
                skipped_paths.append(
                    {
                        "path": _relative_display(path, root),
                        "reason": f"file-larger-than-{limit}-bytes",
                    }
                )
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        if scan_errors is not None and root is not None:
            scan_errors.append(
                {
                    "path": _relative_display(path, root),
                    "operation": "read-file",
                    "error": str(exc),
                }
            )
        return ""


def _load_small_json(
    path: Path,
    *,
    root: Path | None = None,
    scan_errors: list[dict[str, str]] | None = None,
    skipped_paths: list[dict[str, str]] | None = None,
) -> Any | None:
    text = _read_small_text(
        path,
        root=root,
        scan_errors=scan_errors,
        skipped_paths=skipped_paths,
    )
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _normalize_curve(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    compact = re.sub(r"[^a-z0-9]", "", value.lower())
    return CURVE_ALIASES.get(compact, compact or None)


def _is_verification_key_json(basename: str, value: Any) -> bool:
    strong_filename_hint = (
        basename in VK_NAMES - {"vk.json"}
        or basename.startswith(("verification_key", "verification-key", "verifying_key", "verifying-key"))
    )
    if not isinstance(value, dict):
        return strong_filename_hint

    keys = {str(key).lower() for key in value}
    snarkjs_markers = {"vk_alpha_1", "vk_beta_2", "vk_gamma_2", "vk_delta_2"}
    native_markers = {"vk", "verification_key", "verifying_key"}
    has_snarkjs_shape = bool(keys & snarkjs_markers) and "ic" in keys
    has_generic_groth16_shape = {"alpha", "beta", "gamma", "delta", "ic"}.issubset(keys)
    has_native_shape = bool(keys & native_markers) and bool(keys & {"curve", "protocol", "npublic"})
    return strong_filename_hint or has_snarkjs_shape or has_generic_groth16_shape or has_native_shape


def _is_proof_json(basename: str, value: Any) -> bool:
    filename_hint = basename in PROOF_NAMES or basename.endswith(("_proof.json", "-proof.json"))
    if not isinstance(value, dict):
        return filename_hint
    keys = {str(key).lower() for key in value}
    return filename_hint or {"pi_a", "pi_b", "pi_c"}.issubset(keys)


def _is_public_signals_json(basename: str) -> bool:
    return basename in PUBLIC_SIGNAL_NAMES or basename.endswith(
        ("_public.json", "-public.json", "_public_signals.json", "-public-signals.json")
    )


def _package_boundary(relative_path: str, manifest_dirs: set[str]) -> str:
    parent = Path(relative_path).parent.as_posix()
    candidates = [
        directory
        for directory in manifest_dirs
        if directory == "." or parent == directory or parent.startswith(directory + "/")
    ]
    if not candidates:
        return "."
    return max(candidates, key=lambda value: len(Path(value).parts))


def _select_scan_root(root: Path, package: Path | None) -> tuple[Path, str | None]:
    repository_root = root.expanduser().resolve()
    if not repository_root.is_dir():
        raise ValueError(f"project root is not a directory: {repository_root}")
    if package is None:
        return repository_root, None
    candidate = package.expanduser()
    if not candidate.is_absolute():
        candidate = repository_root / candidate
    selected = candidate.resolve()
    try:
        if os.path.commonpath((str(repository_root), str(selected))) != str(repository_root):
            raise ValueError("--package must resolve inside --root")
    except ValueError as exc:
        if str(exc) == "--package must resolve inside --root":
            raise
        raise ValueError("--package must resolve inside --root") from exc
    if not selected.is_dir():
        raise ValueError(f"selected package is not a directory: {selected}")
    return selected, selected.relative_to(repository_root).as_posix() or "."


def detect_project(
    root: Path,
    max_files: int = 20_000,
    package: Path | None = None,
    artifact_packages: list[Path] | None = None,
) -> dict[str, Any]:
    repository_root = root.expanduser().resolve()
    root, selected_package = _select_scan_root(repository_root, package)
    if max_files < 1:
        raise ValueError("max_files must be positive")

    explicit_artifact_roots: list[Path] = []
    explicit_artifact_packages: list[str] = []
    for artifact_package in artifact_packages or []:
        artifact_root, artifact_name = _select_scan_root(repository_root, artifact_package)
        if artifact_root == root or artifact_root in explicit_artifact_roots:
            continue
        explicit_artifact_roots.append(artifact_root)
        explicit_artifact_packages.append(artifact_name or ".")

    scan_errors: list[dict[str, str]] = []
    skipped_paths: list[dict[str, str]] = []
    candidate_paths: dict[Path, Path] = {}
    for scan_root in (root, *explicit_artifact_roots):
        for candidate in _iter_files(scan_root, max_files + 1, scan_errors, skipped_paths):
            candidate_paths.setdefault(candidate.resolve(), candidate)
    candidates = sorted(
        candidate_paths.values(),
        key=lambda path: path.relative_to(repository_root).as_posix().lower(),
    )
    scan_truncated = len(candidates) > max_files
    files = candidates[:max_files]
    rels = {path.relative_to(repository_root).as_posix(): path for path in files}
    names_lower = {path.name.lower() for path in files}
    manifest_dirs = {
        Path(rel).parent.as_posix()
        for rel, path in rels.items()
        if path.name.lower() in PACKAGE_MANIFEST_NAMES
    }
    boundaries: dict[str, dict[str, Any]] = {}

    def boundary_for(rel: str) -> dict[str, Any]:
        boundary_name = _package_boundary(rel, manifest_dirs)
        return boundaries.setdefault(
            boundary_name,
            {
                "path": boundary_name,
                "curves": set(),
                "protocols": set(),
                "artifacts": [],
                "tonSignals": set(),
                "manifests": [],
            },
        )

    proving: set[str] = set()
    languages: set[str] = set()
    frameworks: set[str] = set()
    protocols: set[str] = set()
    curves: set[str] = set()
    artifacts: dict[str, list[str]] = {
        "zkey": [],
        "verificationKeys": [],
        "proofs": [],
        "publicSignals": [],
        "nativeBinary": [],
    }
    declared_dependency_specs: dict[str, set[str]] = {}
    dependency_locations: dict[str, list[dict[str, str]]] = {}
    manifests: list[dict[str, Any]] = []

    for rel, path in rels.items():
        lower = rel.lower()
        suffix = path.suffix.lower()
        boundary = boundary_for(rel)
        if any(path.is_relative_to(explicit_root) for explicit_root in explicit_artifact_roots):
            boundary["tonSignals"].add("explicit-artifact-package")

        if suffix == ".circom":
            proving.add("circom")
        elif suffix == ".no":
            proving.add("noname")
        elif suffix == ".go":
            text = _read_small_text(
                path,
                300_000,
                root=root,
                scan_errors=scan_errors,
                skipped_paths=skipped_paths,
            ).lower()
            if "gnark" in text or "frontend.define" in text:
                proving.add("gnark")
        elif suffix == ".rs":
            text = _read_small_text(
                path,
                300_000,
                root=root,
                scan_errors=scan_errors,
                skipped_paths=skipped_paths,
            ).lower()
            if "ark_groth16" in text or "ark-groth16" in text or "constraintsynthesizer" in text:
                proving.add("arkworks")

        if suffix == ".tolk":
            languages.add("tolk")
            boundary["tonSignals"].add("language:tolk")
        elif suffix == ".fc":
            languages.add("func")
            boundary["tonSignals"].add("language:func")
        elif suffix == ".tact":
            languages.add("tact")
            boundary["tonSignals"].add("language:tact")

        if path.name.lower().startswith("blueprint.config."):
            boundary["tonSignals"].add("framework:blueprint")
        if path.name.lower().startswith("tact.config."):
            boundary["tonSignals"].add("framework:tact")

        if lower.endswith(".zkey"):
            artifacts["zkey"].append(rel)
        if lower.endswith(".bin") and (
            path.name.lower() in NATIVE_VK_NAMES
            or "verification" in lower
            or "verifying" in lower
            or "/vk" in lower
        ):
            artifacts["nativeBinary"].append(rel)

        if suffix != ".json":
            continue

        basename = path.name.lower()
        value = _load_small_json(
            path,
            root=root,
            scan_errors=scan_errors,
            skipped_paths=skipped_paths,
        )
        is_vk = _is_verification_key_json(basename, value)
        is_proof = _is_proof_json(basename, value)
        is_public = _is_public_signals_json(basename)

        if is_vk:
            artifacts["verificationKeys"].append(rel)
            boundary["artifacts"].append(rel)
        if is_proof:
            artifacts["proofs"].append(rel)
            boundary["artifacts"].append(rel)
        if is_public:
            artifacts["publicSignals"].append(rel)

        # Only interpret generic "curve" or "protocol" fields in files that
        # structurally look like proof-system artifacts. This avoids blocking on
        # unrelated application JSON such as TLS or wallet curve configuration.
        if (is_vk or is_proof) and isinstance(value, dict):
            protocol = value.get("protocol")
            if isinstance(protocol, str):
                protocols.add(protocol.lower())
                boundary["protocols"].add(protocol.lower())
            curve = _normalize_curve(value.get("curve"))
            if curve:
                curves.add(curve)
                boundary["curves"].add(curve)

    if "acton.toml" in names_lower:
        frameworks.add("acton")
    if any(name.startswith("blueprint.config.") for name in names_lower):
        frameworks.add("blueprint")
    if any(name.startswith("tact.config.") for name in names_lower):
        frameworks.add("tact")

    tracked_npm_dependencies = (
        "export-ton-verifier",
        "snarkjs",
        "@ton/blueprint",
        "@ton/sandbox",
        "@tact-lang/compiler",
        "@ton/tolk-js",
    )
    for rel, path in sorted(rels.items()):
        basename = path.name.lower()
        if basename == "package.json":
            package = _load_small_json(
                path,
                root=root,
                scan_errors=scan_errors,
                skipped_paths=skipped_paths,
            )
            entry: dict[str, Any] = {"path": rel, "kind": "npm"}
            selected: dict[str, str] = {}
            if isinstance(package, dict):
                for section in ("dependencies", "devDependencies", "optionalDependencies"):
                    deps = package.get(section, {})
                    if not isinstance(deps, dict):
                        continue
                    for dependency in tracked_npm_dependencies:
                        version = deps.get(dependency)
                        if isinstance(version, str):
                            selected[dependency] = version
                            declared_dependency_specs.setdefault(dependency, set()).add(version)
                            dependency_locations.setdefault(dependency, []).append(
                                {"path": rel, "version": version}
                            )
                engines = package.get("engines")
                if isinstance(engines, dict) and isinstance(engines.get("node"), str):
                    entry["nodeEngine"] = engines["node"]
                if isinstance(package.get("packageManager"), str):
                    entry["packageManager"] = package["packageManager"]
            if selected:
                entry["dependencies"] = dict(sorted(selected.items()))
            manifests.append(entry)
            package_boundary = boundary_for(rel)
            package_boundary["manifests"].append(rel)
            if "@ton/blueprint" in selected:
                frameworks.add("blueprint")
                package_boundary["tonSignals"].add("dependency:@ton/blueprint")
            if "@tact-lang/compiler" in selected:
                frameworks.add("tact")
                package_boundary["tonSignals"].add("dependency:@tact-lang/compiler")
            if "export-ton-verifier" in selected or "@ton/tolk-js" in selected:
                package_boundary["tonSignals"].add("dependency:ton-zk-tooling")
            continue

        if basename == "go.mod":
            text = _read_small_text(
                path,
                root=root,
                scan_errors=scan_errors,
                skipped_paths=skipped_paths,
            ).lower()
            signals: list[str] = []
            if "gnark" in text:
                proving.add("gnark")
                signals.append("gnark")
            entry = {"path": rel, "kind": "go"}
            if signals:
                entry["signals"] = signals
            manifests.append(entry)
            boundary_for(rel)["manifests"].append(rel)
            continue

        if basename == "cargo.toml":
            text = _read_small_text(
                path,
                root=root,
                scan_errors=scan_errors,
                skipped_paths=skipped_paths,
            ).lower()
            signals = []
            if "ark-groth16" in text or "ark_groth16" in text or "ark-snarkjs" in text:
                proving.add("arkworks")
                signals.append("arkworks")
            entry = {"path": rel, "kind": "cargo"}
            if signals:
                entry["signals"] = signals
            manifests.append(entry)
            boundary_for(rel)["manifests"].append(rel)
            continue

        if basename == "acton.toml":
            manifests.append({"path": rel, "kind": "acton"})
            acton_boundary = boundary_for(rel)
            acton_boundary["manifests"].append(rel)
            acton_boundary["tonSignals"].add("framework:acton")

    blocking: list[str] = []
    advisories: list[str] = []
    if scan_truncated:
        advisories.append(f"File scan reached the --max-files limit ({max_files}); results may be incomplete.")
    for dependency, locations in sorted(dependency_locations.items()):
        versions = sorted({item["version"] for item in locations})
        if len(versions) > 1:
            advisories.append(
                f"Multiple {dependency} dependency specs were found across manifests: {', '.join(versions)}; inspect the owning lockfile and installed dependency before selecting target artifacts."
            )
    for skipped in skipped_paths:
        if skipped["reason"] == "excluded-directory" and Path(skipped["path"]).name.lower() in {"build", "dist"}:
            advisories.append(f"Skipped potentially relevant artifact directory: {skipped['path']}")
    if scan_errors:
        advisories.append(f"Project scan encountered {len(scan_errors)} read error(s); inspect scanErrors before relying on the inventory.")
    has_ton_signals = any(item["tonSignals"] for item in boundaries.values())
    package_boundaries: list[dict[str, Any]] = []
    for boundary_name, item in sorted(boundaries.items()):
        has_artifacts = bool(item["artifacts"])
        ton_applicable = bool(item["tonSignals"]) or (has_artifacts and not has_ton_signals)
        boundary_curves = sorted(item["curves"])
        boundary_protocols = sorted(item["protocols"])
        incompatible_curves = [curve for curve in boundary_curves if curve != "bls12-381"]
        if ton_applicable and incompatible_curves:
            blocking.append(
                f"TON package {boundary_name} has non-BLS12-381 verifier artifacts "
                f"({', '.join(incompatible_curves)}); BN254/bn128 is not accepted by this workflow."
            )
        elif not ton_applicable and incompatible_curves:
            advisories.append(
                f"Ignored non-BLS12-381 artifacts in non-TON package {boundary_name}; select it explicitly with --package if it consumes TON contracts."
            )
        if ton_applicable and "plonk" in boundary_protocols and "language:tact" in item["tonSignals"]:
            blocking.append(
                f"TON package {boundary_name} selects experimental PLONK with Tact; the documented path targets Tolk/FunC."
            )
        package_boundaries.append(
            {
                "path": boundary_name,
                "tonApplicable": ton_applicable,
                "curves": boundary_curves,
                "protocols": boundary_protocols,
                "artifacts": sorted(set(item["artifacts"])),
                "tonSignals": sorted(item["tonSignals"]),
                "manifests": sorted(set(item["manifests"])),
            }
        )
    if artifacts["verificationKeys"] and not curves:
        advisories.append(
            "Verification-key artifacts were found, but their curve was not detected; run export-ton-verifier doctor."
        )
    if artifacts["zkey"] and not protocols:
        advisories.append("A .zkey was found; inspect it with export-ton-verifier doctor before selecting a target template.")
    if languages and not any(artifacts.values()):
        advisories.append("TON contract sources were found without proof/VK artifacts; confirm generated verifiers are reproducible.")

    recommended = ["ton-zk-proofs"]
    if proving:
        recommended.append("ton-zk-circuit-workflows")
    if artifacts["zkey"] or artifacts["verificationKeys"] or artifacts["nativeBinary"]:
        recommended.append("ton-zk-verifier-generation")
    if languages or frameworks:
        recommended.extend(["ton-zk-contract-integration", "ton-zk-testing"])
    if languages and (artifacts["verificationKeys"] or artifacts["zkey"] or artifacts["nativeBinary"]):
        recommended.append("ton-zk-integration-review")

    return {
        "root": str(root),
        "repositoryRoot": str(repository_root),
        "selectedPackage": selected_package,
        "explicitArtifactPackages": explicit_artifact_packages,
        "filesScanned": len(files),
        "scanTruncated": scan_truncated,
        "provingStacks": sorted(proving),
        "contractLanguages": sorted(languages),
        "frameworks": sorted(frameworks),
        "protocols": sorted(protocols),
        "curves": sorted(curves),
        "artifacts": {key: sorted(value) for key, value in artifacts.items()},
        "declaredDependencySpecs": {
            key: sorted(values) for key, values in sorted(declared_dependency_specs.items())
        },
        "dependencyLocations": {key: value for key, value in sorted(dependency_locations.items())},
        "manifests": manifests,
        "packageBoundaries": package_boundaries,
        "scanErrors": scan_errors,
        "skippedPaths": skipped_paths,
        "blockingWarnings": blocking,
        "advisories": advisories,
        "recommendedSkills": list(dict.fromkeys(recommended)),
    }


def format_text(result: dict[str, Any]) -> str:
    lines = [f"TON ZK project: {result['root']}", f"Files scanned: {result['filesScanned']}"]
    for key, label in (
        ("provingStacks", "Proving stacks"),
        ("contractLanguages", "Contract languages"),
        ("frameworks", "Frameworks"),
        ("protocols", "Protocols"),
        ("curves", "Curves"),
        ("recommendedSkills", "Recommended skills"),
    ):
        values = result[key]
        lines.append(f"{label}: {', '.join(values) if values else 'none detected'}")
    if result.get("manifests"):
        lines.append("Manifests:")
        for manifest in result["manifests"]:
            details = manifest.get("dependencies") or manifest.get("signals") or ""
            lines.append(f"  - {manifest['path']} ({manifest['kind']}){f': {details}' if details else ''}")
    if result.get("scanErrors"):
        lines.append("Scan errors:")
        lines.extend(
            f"  - {item['path']} ({item['operation']}): {item['error']}" for item in result["scanErrors"]
        )
    if result.get("skippedPaths"):
        lines.append("Skipped paths:")
        lines.extend(f"  - {item['path']} ({item['reason']})" for item in result["skippedPaths"])
    if result["blockingWarnings"]:
        lines.append("Blocking warnings:")
        lines.extend(f"  - {item}" for item in result["blockingWarnings"])
    if result["advisories"]:
        lines.append("Advisories:")
        lines.extend(f"  - {item}" for item in result["advisories"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root to inspect")
    parser.add_argument(
        "--package",
        type=Path,
        help="optional package/module path inside --root; limits scanning and blockers to that boundary",
    )
    parser.add_argument(
        "--artifact-package",
        action="append",
        default=[],
        type=Path,
        help="package/module path inside --root whose proof artifacts are consumed by the selected TON package; repeat as needed",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--max-files", type=int, default=20_000)
    args = parser.parse_args(argv)

    try:
        result = detect_project(args.root, args.max_files, args.package, args.artifact_package)
    except ValueError as exc:
        parser.error(str(exc))

    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result), end="")
    return 2 if result["blockingWarnings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
