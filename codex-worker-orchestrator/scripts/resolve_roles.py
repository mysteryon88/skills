#!/usr/bin/env python3
"""Compile a validated route from a request and discovered inventories.

This compiler reads the canonical registries and referenced planning evidence,
applies conservative safety and budget rules, and never spawns agents, writes
state, or installs skills. The command line wrapper handles JSON I/O and exits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrator_lib import (
    RoleSpec,
    artifact_identity,
    artifact_path,
    atomic_write_json,
    canonical_relative_path,
    load_capability_packs,
    load_install_profiles,
    load_json,
    load_role_registry,
    validate_instance,
)
from run_state import RunStateError, show_run


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ROLE_SCHEMA_NAME = "route-request"
ROUTE_SCHEMA_NAME = "route"

READ_ONLY_INTENTS = {
    "explore-code", "research-docs", "architecture", "skeptic-review",
    "spec-review", "plan-gap-analysis", "plan-review", "task-review", "final-review",
    "security-review", "deep-analysis", "visual-analysis",
}
IMPLEMENTATION_INTENTS = {
    "quick-implementation", "bounded-implementation", "deep-fixed-implementation",
    "test-authoring", "documentation", "content-writing",
}
NATIVE_PARALLEL_INTENTS = (READ_ONLY_INTENTS - {"deep-analysis"}) | {"test-execution"}
REVIEW_INTENTS = {
    "skeptic-review", "spec-review", "plan-gap-analysis", "plan-review", "task-review",
    "final-review", "security-review",
}
WRITER_MUTATIONS = {"write", "documentation-only"}


class ResolutionInputError(ValueError):
    """The request or caller-supplied inventory is not a valid input."""


def _load_routing_policy(package_root: Path) -> dict[str, Any]:
    path = Path(package_root) / "config" / "routing-policy.toml"
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ResolutionInputError(f"cannot load routing policy: {exc}") from exc
    if not isinstance(payload, dict):
        raise ResolutionInputError("routing policy must be a TOML table")
    workflow = payload.get("workflow")
    budgets = payload.get("budgets")
    parallelism = payload.get("parallelism")
    test_routing = payload.get("test_routing")
    lite_workflow = payload.get("lite_workflow")
    capabilities = payload.get("capabilities")
    if not isinstance(workflow, dict) or workflow.get("root_owner") != "root" or workflow.get("root_is_spawnable") is not False:
        raise ResolutionInputError("routing policy must keep root as the non-spawnable workflow owner")
    if not isinstance(budgets, dict):
        raise ResolutionInputError("routing policy is missing budgets")
    required_budgets = {"max_agents", "max_writers", "max_read_only", "max_reviewers"}
    if set(budgets) != required_budgets or any(
        not isinstance(budgets[key], int) or isinstance(budgets[key], bool) or budgets[key] < 0
        for key in required_budgets
    ):
        raise ResolutionInputError("routing policy budgets are invalid")
    required_parallel = {
        "second_writer_requires_independent_packages",
        "second_writer_requires_disjoint_write_surfaces",
        "second_writer_requires_separate_worktrees",
        "second_writer_requires_validated_overlay",
        "ask_user_before_creating_worktrees",
    }
    if not isinstance(parallelism, dict) or set(parallelism) != required_parallel or any(
        parallelism.get(key) is not True for key in required_parallel
    ):
        raise ResolutionInputError("routing policy must require evidence and user approval for a second writer")
    if (
        not isinstance(test_routing, dict)
        or set(test_routing) != {"spawn_threshold_seconds", "max_parallel_runners"}
        or not isinstance(test_routing.get("spawn_threshold_seconds"), int)
        or isinstance(test_routing.get("spawn_threshold_seconds"), bool)
        or test_routing["spawn_threshold_seconds"] < 1
        or not isinstance(test_routing.get("max_parallel_runners"), int)
        or isinstance(test_routing.get("max_parallel_runners"), bool)
        or test_routing["max_parallel_runners"] < 1
    ):
        raise ResolutionInputError("routing policy test_routing is invalid")
    required_lite_workflow = {
        "root_authors_detailed_plan",
        "requires_ordered_steps",
        "requires_allowed_files",
        "requires_acceptance_criteria",
        "requires_verification_commands",
        "requires_stop_conditions",
        "test_runner_required_after_write",
        "root_reviews_actual_diff",
    }
    if (
        not isinstance(lite_workflow, dict)
        or set(lite_workflow) != required_lite_workflow
        or any(lite_workflow.get(key) is not True for key in required_lite_workflow - {"test_runner_required_after_write"})
        or lite_workflow.get("test_runner_required_after_write") is not False
    ):
        raise ResolutionInputError(
            "routing policy must require a detailed root-authored Lite plan, "
            "proportionate post-write tests, and root diff review"
        )
    if not isinstance(capabilities, dict) or capabilities.get("auto_install") is not False or capabilities.get("discovered_skills_only") is not True:
        raise ResolutionInputError("routing policy must disable capability auto-install")
    return payload

def _validate_request(request: Mapping[str, Any], package_root: Path) -> None:
    if not isinstance(request, Mapping):
        raise ResolutionInputError("request must be a JSON object")
    try:
        schema = load_json(Path(package_root) / "schemas" / "route-request.schema.json")
    except ValueError as exc:
        raise ResolutionInputError(str(exc)) from exc
    errors = validate_instance(request, schema, schema_name=ROLE_SCHEMA_NAME)
    if errors:
        raise ResolutionInputError("invalid route request: " + "; ".join(errors))


def _normalize_inventory(
    value: Sequence[Any] | Mapping[str, Any] | None,
    *,
    label: str,
    known: set[str] | None,
    default: Iterable[str],
) -> list[str]:
    if value is None:
        raw: Any = list(default)
    elif isinstance(value, Mapping):
        if set(value) != {"names"} or not isinstance(value.get("names"), list):
            raise ResolutionInputError(f"{label} inventory must be an array or {{\"names\": [...]}}")
        raw = value["names"]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw = value
    else:
        raise ResolutionInputError(f"{label} inventory must be an array or object with names")
    normalized: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ResolutionInputError(f"{label} inventory names must be non-empty strings")
        normalized.add(item.strip())
    if known is not None:
        unknown = sorted(normalized - known)
        if unknown:
            raise ResolutionInputError(f"unknown {label} role(s): {', '.join(unknown)}")
    return sorted(normalized)


def normalize_available_agents(
    available_agents: Sequence[Any] | Mapping[str, Any] | None,
    registry: Mapping[str, RoleSpec],
) -> list[str]:
    """Normalize an explicit role inventory, or default to bundled role names."""

    if isinstance(available_agents, Mapping) and "roles" in available_agents:
        rows = available_agents["roles"]
        if not isinstance(rows, list):
            raise ResolutionInputError("preflight roles must be an array")
        names: list[str] = []
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise ResolutionInputError(f"preflight roles[{index}] must be an object")
            name = row.get("name")
            valid = row.get("valid")
            if not isinstance(name, str) or not name.strip() or not isinstance(valid, bool):
                raise ResolutionInputError(
                    f"preflight roles[{index}] must contain a non-empty name and boolean valid"
                )
            if valid:
                names.append(name)
        available_agents = names

    return _normalize_inventory(
        available_agents,
        label="agent",
        known=set(registry),
        default=registry,
    )



def _detect_install_mode(
    available_agents: Sequence[Any] | Mapping[str, Any] | None,
    normalized_agents: Sequence[str],
    profiles: Mapping[str, Any],
) -> str:
    """Detect Lite exactly and otherwise retain the stricter Hard review floor."""

    agent_names = set(normalized_agents)
    explicit: str | None = None
    if isinstance(available_agents, Mapping):
        raw_mode = available_agents.get("install_mode")
        if raw_mode is not None:
            if not isinstance(raw_mode, str) or raw_mode not in profiles:
                raise ResolutionInputError("preflight install_mode must be lite or hard")
            explicit = raw_mode

    if explicit is not None:
        unexpected = sorted(agent_names - set(profiles[explicit].roles))
        if unexpected:
            raise ResolutionInputError(
                f"agent inventory contains roles outside explicit {explicit} profile: "
                + ", ".join(unexpected)
            )
        return explicit

    matches = [
        profile.name
        for profile in profiles.values()
        if set(profile.roles) == agent_names
    ]
    if len(matches) == 1:
        return matches[0]
    return "hard"


def normalize_available_skills(
    available_skills: Sequence[Any] | Mapping[str, Any] | None,
) -> list[str]:
    """Normalize discovered skill identifiers without treating them as installable."""

    names, _ = normalize_skill_inventory(available_skills)
    return names


def normalize_skill_inventory(
    available_skills: Sequence[Any] | Mapping[str, Any] | None,
) -> tuple[list[str], list[str]]:
    """Return discovered and incompatible skill names from preflight inventory."""

    if isinstance(available_skills, Mapping) and "skill_inventory" in available_skills:
        nested = available_skills["skill_inventory"]
        if not isinstance(nested, Mapping):
            raise ResolutionInputError("preflight skill_inventory must be an object")
        return normalize_skill_inventory(nested)

    if isinstance(available_skills, Mapping) and "incompatible" in available_skills:
        if set(available_skills) != {"names", "incompatible"}:
            raise ResolutionInputError(
                'skill inventory with compatibility must contain only "names" and "incompatible"'
            )
        names = _normalize_inventory(
            available_skills["names"], label="skill", known=None, default=()
        )
        incompatible = _normalize_inventory(
            available_skills["incompatible"],
            label="incompatible skill",
            known=None,
            default=(),
        )
        unknown = sorted(set(incompatible) - set(names))
        if unknown:
            raise ResolutionInputError(
                "incompatible skill inventory contains undiscovered name(s): "
                + ", ".join(unknown)
            )
        return names, incompatible
    return (
        _normalize_inventory(
            available_skills,
            label="skill",
            known=None,
            default=(),
        ),
        [],
    )


def _canonical_surfaces(request: Mapping[str, Any]) -> tuple[list[str], bool]:
    values = request.get("write_surfaces", [])
    if not isinstance(values, list):  # Schema validation normally catches this.
        raise ResolutionInputError("write_surfaces must be an array")
    surfaces: list[str] = []
    for value in values:
        try:
            normalized = canonical_relative_path(value)
        except ValueError as exc:
            raise ResolutionInputError(f"invalid write surface {value!r}: {exc}") from exc
        if normalized not in surfaces:
            surfaces.append(normalized)
    overlap = any(
        left == right or left.startswith(right + "/") or right.startswith(left + "/")
        for index, left in enumerate(surfaces)
        for right in surfaces[index + 1:]
    )
    return surfaces, overlap


def _is_read_only(spec: RoleSpec) -> bool:
    return spec.sandbox_mode == "read-only" and spec.mutation_class == "read-only"


def _is_writer(spec: RoleSpec) -> bool:
    return spec.sandbox_mode == "workspace-write" and spec.mutation_class in WRITER_MUTATIONS


def _is_diagnostic(spec: RoleSpec) -> bool:
    return spec.sandbox_mode == "workspace-write" and spec.mutation_class == "diagnostic"


def _is_reviewer(spec: RoleSpec) -> bool:
    return _is_read_only(spec) and bool(set(spec.intents) & REVIEW_INTENTS)


def _is_role_allowed(
    spec: RoleSpec,
    request: Mapping[str, Any],
    *,
    intent: str,
    review_gate: bool = False,
    test_gate: bool = False,
    pressure_gate: bool = False,
) -> tuple[bool, str]:
    mutation = request["mutation"]
    if test_gate:
        if spec.mutation_class != "test-only" or "test-execution" not in spec.intents:
            return False, "Lite post-write validation requires luna_test_runner"
        return True, ""
    if review_gate:
        if not _is_reviewer(spec) or not _is_read_only(spec):
            return False, "mandatory review gate must use a read-only reviewer"
        return True, ""
    if pressure_gate:
        if not _is_read_only(spec) or "skeptic-review" not in spec.intents:
            return False, "high-rigor pressure gate must use the read-only skeptic"
        return True, ""
    if intent in READ_ONLY_INTENTS and mutation not in {"none", "read"}:
        return False, "read-only intent cannot delegate with write or diagnostic mutation"
    if request["security_sensitive"] and "security-review" in spec.intents:
        if not _is_read_only(spec):
            return False, "security review must remain read-only"
        return True, ""
    if intent in READ_ONLY_INTENTS or intent == "inline":
        if not _is_read_only(spec):
            return False, "read-only request cannot select a writer or diagnostic role"
    elif intent == "reproduce-runtime":
        if not (_is_diagnostic(spec) or _is_read_only(spec)):
            return False, "runtime reproduction cannot select an implementation writer"
        if mutation not in {"diagnostic", "read", "none"}:
            return False, "runtime reproduction requires diagnostic or read mutation"
    elif intent == "integration-debugging" and not request["confirmed_root_cause"]:
        if not (_is_diagnostic(spec) or _is_read_only(spec)):
            return False, "unconfirmed integration work remains investigative"
        if mutation not in {"diagnostic", "read", "none"}:
            return False, "unconfirmed integration debugging requires diagnostic or read mutation"
    elif intent == "test-execution":
        if "test-execution" not in spec.intents or spec.mutation_class != "test-only":
            return False, "test execution requires the execution-only Luna runner"
        if mutation not in {"diagnostic", "read", "none"}:
            return False, "test execution cannot authorize production writes"
    elif intent in IMPLEMENTATION_INTENTS:
        if intent == "test-authoring":
            if "test-authoring" not in spec.intents or not _is_writer(spec):
                return False, "test authoring requires the bounded implementation writer"
        elif intent == "documentation":
            if "documentation" not in spec.intents or not _is_writer(spec):
                return False, "documentation requires the documentation-only writer"
        elif not _is_writer(spec):
            return False, "implementation requires a workspace-write implementation role"
        if mutation != "write":
            return False, "implementation route requires write mutation"
        if intent != "quick-implementation" and not request["approved_design"]:
            return False, "write implementation requires an approved design"
    elif intent == "integration-debugging":
        if not _is_writer(spec):
            return False, "confirmed integration debugging requires a workspace-write role"
        if mutation != "write":
            return False, "confirmed integration debugging requires write mutation"
        if not request["approved_design"]:
            return False, "confirmed integration debugging requires an approved design"
    return True, ""

def _high_rigor(request: Mapping[str, Any]) -> bool:
    return (
        request["complexity"] in {"high", "extreme"}
        or request["uncertainty"] == "high"
        or request["risk"] in {"high", "critical"}
    )


def _root_owns_architecture(request: Mapping[str, Any]) -> bool:
    return (
        request.get("root_model") in {"gpt-6-astra", "gpt-6.1-sol", "gpt-6-sol", "gpt-5.6-sol"}
        and not request.get("independent_analysis_required", False)
    )


def _small_inline_task(request: Mapping[str, Any]) -> bool:
    return (
        request["complexity"] in {"trivial", "low"}
        and request["risk"] == "low"
        and request["uncertainty"] == "low"
        and not request["security_sensitive"]
        and not request["requires_runtime_reproduction"]
        and not (request.get("delegation") and request["delegated_execution_selected"])
        and (not request.get("delegation") or len(request["independent_packages"]) < 2)
        and (
            (request["complexity"] == "trivial" and request["mutation"] == "none"
             and request["intent"] not in REVIEW_INTENTS | {"architecture", "deep-analysis"})
            or
            (request["intent"] in {"explore-code", "research-docs", "visual-analysis"} and request["mutation"] in {"none", "read"})
            or (
                request["intent"] == "architecture"
                and request["mutation"] in {"none", "read"}
                and not request.get("independent_analysis_required", False)
            )
            or (
                request["intent"] in IMPLEMENTATION_INTENTS | {"inline"}
                and request["mutation"] == "write"
                and bool(request["write_surfaces"])
                and (request["approved_design"] or request["intent"] == "quick-implementation")
            )
        )
    )


def _role_sort_key(spec: RoleSpec, registry_order: Mapping[str, int]) -> tuple[int, int, str]:
    return spec.cost_rank, registry_order[spec.name], spec.name


def _cheapest_registered_role(
    registry: Mapping[str, RoleSpec],
    intent: str,
    model: str | None = None,
) -> str | None:
    registry_order = {name: index for index, name in enumerate(registry)}
    candidates = [spec for spec in registry.values()
                  if intent in spec.intents and (model is None or spec.model == model)]
    if not candidates:
        return None
    return min(candidates, key=lambda spec: _role_sort_key(spec, registry_order)).name


def _primary_model(request: Mapping[str, Any], install_mode: str) -> str | None:
    intent = request["intent"]
    if intent in {"quick-implementation", "bounded-implementation"}:
        if _high_rigor(request):
            return "gpt-6.1-sol"
        if install_mode == "hard":
            return "gpt-6.1-terra"
    if intent == "deep-fixed-implementation" and (
        request["uncertainty"] == "high" or request["risk"] in {"high", "critical"}
    ):
        return "gpt-6.1-sol"
    if intent in {"visual-analysis", "content-writing", "test-authoring"} and _high_rigor(request):
        return "gpt-6.1-sol"
    if intent == "integration-debugging" and request["confirmed_root_cause"]:
        return "gpt-6.1-sol"
    return None


def _candidate_roles(
    request: Mapping[str, Any],
    registry: Mapping[str, RoleSpec],
    install_mode: str = "hard",
) -> tuple[list[str], bool]:
    intent = str(request["intent"])
    if intent == "inline":
        return [], False
    if intent == "integration-debugging" and not request["confirmed_root_cause"]:
        investigative = _cheapest_registered_role(registry, "reproduce-runtime")
        return ([investigative] if investigative else []), False
    if intent == "architecture":
        architect = None if _root_owns_architecture(request) else _cheapest_registered_role(registry, "architecture")
        skeptic = _cheapest_registered_role(registry, "skeptic-review")
        return ([name for name in (architect, skeptic) if name is not None], bool(skeptic))
    if intent in {"skeptic-review", "spec-review", "plan-gap-analysis", "plan-review"}:
        skeptic = _cheapest_registered_role(registry, intent)
        return ([skeptic] if skeptic else []), _high_rigor(request)
    primary = _cheapest_registered_role(registry, intent, _primary_model(request, install_mode))
    if primary is None:
        raise ResolutionInputError(f"no canonical role is registered for intent: {intent}")
    return [primary], False

def _fallback_chain(
    name: str,
    registry: Mapping[str, RoleSpec],
) -> list[str]:
    result: list[str] = []
    pending = list(registry[name].fallbacks)
    visited = {name}
    while pending:
        candidate = pending.pop(0)
        if candidate in visited:
            continue
        visited.add(candidate)
        result.append(candidate)
        pending.extend(registry[candidate].fallbacks)
    return result


def _accepted_artifact(
    project_root: Path, reference: Mapping[str, Any], kind: str,
    registry: Mapping[str, RoleSpec],
) -> tuple[str, datetime, datetime, Mapping[str, Any]]:
    root = project_root.resolve(strict=True)
    path = canonical_relative_path(reference["path"])
    artifact = artifact_path(root, path)
    path = artifact.relative_to(root).as_posix()
    with artifact.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    state = show_run(root, reference["review_run_id"])
    candidates = []
    referenced_index = next((index for index, report in enumerate(state["reports"])
                             if report.get("report_id", report["task_id"]) == reference["review_report_id"]), -1)
    for index, report in enumerate(state["reports"]):
        metadata = report.get("artifact_review", {})
        if metadata.get("kind") != kind:
            continue
        report_path = canonical_relative_path(metadata["path"])
        report_identity = metadata.get("filesystem_identity")
        try:
            report_artifact = artifact_path(root, report_path)
            report_path = report_artifact.relative_to(root).as_posix()
            if report_identity is None:
                report_identity = artifact_identity(report_artifact)
        except FileNotFoundError:
            if report_identity is None and index > referenced_index and report_path != path:
                raise ValueError("later missing artifact has no recorded filesystem identity; obtain a fresh review")
        candidates.append((report, report_path, report_identity))
    identity = artifact_identity(artifact)
    identities = {identity} if identity is not None else set()
    # Preserve target history without merging later files occupying an alias.
    identities.update(report_identity for _, report_path, report_identity in candidates
                      if report_path == path and report_identity is not None)
    matching = [report for report, report_path, report_identity in candidates
                if report_path == path or report_identity in identities]
    if not matching or matching[-1].get("report_id", matching[-1]["task_id"]) != reference["review_report_id"]:
        raise ValueError("reference must identify the latest applicable artifact review report")
    report = matching[-1]
    metadata = report["artifact_review"]
    role = registry.get(report["role"])
    if report["role"] not in {"skeptic", "sol_reviewer"} or role is None or not _is_read_only(role):
        raise ValueError("artifact review requires a dispatched read-only skeptic or Sol reviewer")
    if state["status"] in {"blocked", "failed"} or report["status"] != "DONE" or report["findings"] or report["changed_files"]:
        raise ValueError("artifact review has unresolved findings, unsuccessful status, or authoring changes")
    if metadata["author_id"] != reference["author_id"] or metadata["sha256"] != digest:
        raise ValueError("artifact author or current SHA256 differs from the reviewed artifact")
    if metadata["author_id"].strip().casefold() == metadata["reviewer_id"].strip().casefold():
        raise ValueError("artifact reviewer must be independent of its author")
    report_id = reference["review_report_id"]
    decisions = [entry for entry in state["reconciliation"]["decisions"] if entry["report_id"] == report_id]
    if not decisions or decisions[-1]["decision"] != "ACCEPT":
        raise ValueError("artifact review needs a current root ACCEPT ruling")
    recorded = [entry["at"] for entry in state["history"] if entry["reason"] == f"report:{report_id}"]
    if not recorded:
        raise ValueError("artifact review has no recorded report event")
    return (digest, datetime.fromisoformat(decisions[-1]["at"].replace("Z", "+00:00")),
            datetime.fromisoformat(recorded[-1].replace("Z", "+00:00")), metadata)


def _planning_prerequisites(
    request: Mapping[str, Any], registry: Mapping[str, RoleSpec],
    project_root: Path | None, *, simple: bool,
) -> list[str]:
    if simple:
        return []
    plan_stage = (
        (request["phase"] == "planning" and request["intent"] != "spec-review")
        or request["intent"] in {"plan-review", "plan-gap-analysis"}
    )
    write_stage = request["mutation"] == "write"
    if not plan_stage and not write_stage:
        return []
    planning = request.get("planning", {"kind": "substantive"})
    if planning["kind"] == "settled":
        if (request["approved_design"] and not _high_rigor(request)
                and not request["security_sensitive"] and not request.get("independent_analysis_required", False)):
            return []
        return ["Settled recipes require an approved design without high-rigor, security, or independent-analysis work; supply accepted substantive planning evidence."]
    if project_root is None:
        return ["Substantive planning requires explicit --project-root and accepted specification/plan evidence."]
    try:
        if "specification" not in planning:
            raise ValueError("accepted specification evidence is required before plan inputs or implementation")
        spec = _accepted_artifact(project_root, planning["specification"], "specification", registry)
        if write_stage:
            if "plan" not in planning:
                raise ValueError("accepted plan evidence is required before implementation")
            plan = _accepted_artifact(project_root, planning["plan"], "plan", registry)
            if plan[3].get("specification_sha256") != spec[0] or plan[2] <= spec[1]:
                raise ValueError("plan review must follow acceptance of and bind the current specification SHA256")
    except (OSError, ValueError, RunStateError) as exc:
        return [f"Unmet substantive planning prerequisite: {exc}"]
    return []


def _workflow_gates(
    request: Mapping[str, Any],
    selected_roles: Sequence[str],
    registry: Mapping[str, RoleSpec],
    install_mode: str,
    *,
    blocked: bool,
) -> tuple[list[str], list[str]]:
    intent = str(request["intent"])
    if blocked:
        return [], ["Resolve the reported blocking prerequisites before execution."]
    if not selected_roles:
        quality = [
            "Root performs the work, inspects the actual diff, and runs proportionate verification; no independent review is claimed.",
        ]
        if request["security_sensitive"]:
            quality.append("Root must verify trust boundaries and failure behavior; if safety cannot be established, report the limitation before proceeding.")
        return [], quality
    approval: list[str] = []
    if intent in {"architecture", "research-docs"}:
        approval.append("superpowers:brainstorming owns requirements and design approval")
    if intent in {"skeptic-review", "spec-review", "plan-gap-analysis", "plan-review"}:
        approval.append("The root owns the skeptic ruling and any replan decision")
    if intent in IMPLEMENTATION_INTENTS:
        if install_mode == "lite":
            approval.append(
                "Before dispatch, the root must author and approve a detailed, unambiguous Lite execution plan."
            )
        else:
            approval.append(
                "superpowers:subagent-driven-development owns the implementation and review loop"
            )
    if intent == "test-execution":
        approval.append("Root owns test dispatch economics and result reconciliation")
    if intent == "integration-debugging":
        approval.append("superpowers:systematic-debugging owns root-cause investigation")
    if intent in {"task-review", "final-review", "security-review"}:
        approval.append("superpowers:verification-before-completion owns fresh verification")
    if request["security_sensitive"]:
        approval.append("Root approval is required before security-sensitive dispatch")
    quality = [
        "Root owns workflow sequencing, dispatch, state, write isolation, and completion.",
        "Validate task packets and agent reports against the bundled schemas.",
        "Child roles may not recursively delegate or invoke the orchestrator.",
    ]
    if intent in {"architecture", "spec-review", "plan-gap-analysis", "plan-review"}:
        quality.extend([
            "Independently review each substantive specification before drafting its plan, then review the plan before implementation; root resolves material findings before dependent work.",
            "The critic must be distinct from the artifact author and remain read-only; record artifact revision/digest, author, critic, accepted report, and root ruling before reusing unchanged review evidence.",
            "Reuse an equivalent accepted review and resume the same critic across stages where useful; re-review load-bearing changes, not unchanged content or routine checklists.",
            "Root adjudicates planning refinement rounds; the maximum is 3 rounds before escalating unresolved material findings without starting dependent work.",
        ])
    if intent == "deep-analysis":
        quality.append(
            "Astra is a last resort for extreme complexity: supply the prior Sol analysis, decisive evidence check, and unresolved question before dispatch."
        )
    write_selected = request["mutation"] == "write" or (
        request["mutation"] == "diagnostic" and bool(request["write_surfaces"])
    ) or any(
        _is_writer(registry[role]) or _is_diagnostic(registry[role])
        for role in selected_roles
    )
    if write_selected:
        if install_mode == "lite":
            quality.extend(
                [
                    "The detailed Lite plan must include ordered steps, exact allowed files and write surfaces, protected interfaces, acceptance criteria, exact verification commands, dependencies, and stop conditions.",
                    "luna_worker executes only the approved plan; the root runs short quiet non-build checks, and luna_test_runner runs builds, noisy checks, and worthwhile long/independent checks from the same plan.",
                    "The root inspects the actual diff and test evidence and owns the completion decision; luna_test_runner is not a reviewer.",
                ]
            )
        else:
            quality.append(
                "Mandatory sol_reviewer / gpt-6.1-sol / xhigh review must accept the final integrated diff; no weaker fallback is allowed."
            )
        quality.append(
            "Use only write isolation supplied by the selected owner workflow; a route declaration is not a filesystem lock or worktree proof."
        )
    if _high_rigor(request):
        quality.append("Root adjudicates high-rigor refinement rounds; the maximum is 3 rounds.")
    return approval, quality


def _should_delegate_test(
    request: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> bool:
    context = request.get("test_context")
    if not isinstance(context, Mapping):
        return (
            request["complexity"] in {"high", "extreme"}
            or len(request["independent_packages"]) > 1
        )
    threshold = int(policy["spawn_threshold_seconds"])
    if context.get("is_build", False) or context["noisy_output"]:
        return True
    if int(context["estimated_seconds"]) < threshold and context["blocks_next_step"]:
        return False
    return bool(
        int(context["estimated_seconds"]) >= threshold
        or context["parallel_value"]
        or len(request["independent_packages"]) > 1
    )

def _canonical_route(route: dict[str, Any], registry: Mapping[str, RoleSpec]) -> dict[str, Any]:
    """Sort only semantically unordered collections while preserving wave order."""

    role_order = {name: index for index, name in enumerate(registry)}
    route["selected_roles"] = list(route["selected_roles"])
    route["rejected_roles"] = sorted(
        route["rejected_roles"], key=lambda item: role_order.get(item["role"], 999)
    )
    route["capability_packs"] = sorted(route["capability_packs"], key=lambda item: item["name"])
    route["write_ownership"] = sorted(
        route["write_ownership"], key=lambda item: role_order.get(item["role"], 999)
    )
    return route


def resolve_request(
    request: Mapping[str, Any],
    available_agents: Sequence[Any] | Mapping[str, Any] | None = None,
    available_skills: Sequence[Any] | Mapping[str, Any] | None = None,
    *,
    package_root: Path | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Return a deterministic, schema-valid route without dispatch side effects."""

    root = Path(package_root) if package_root is not None else PACKAGE_ROOT
    _validate_request(request, root)
    policy = _load_routing_policy(root)
    try:
        registry = load_role_registry(root)
        profiles = load_install_profiles(root, registry)
        packs = load_capability_packs(root)
        route_schema = load_json(root / "schemas" / "route.schema.json")
    except ValueError as exc:
        raise ResolutionInputError(str(exc)) from exc
    normalized_agents = normalize_available_agents(available_agents, registry)
    agents = set(normalized_agents)
    install_mode = _detect_install_mode(available_agents, normalized_agents, profiles)
    normalized_skills, incompatible_skill_names = normalize_skill_inventory(available_skills)
    skills = set(normalized_skills)
    incompatible_skills = set(incompatible_skill_names)
    surfaces, surfaces_overlap = _canonical_surfaces(request)

    requested_capabilities = request["required_capabilities"]
    if not isinstance(requested_capabilities, list):
        raise ResolutionInputError("required_capabilities must be an array")
    unknown_capabilities = sorted(set(requested_capabilities) - set(packs))
    if unknown_capabilities:
        raise ResolutionInputError(
            "unknown capability pack(s): " + ", ".join(unknown_capabilities)
        )
    capability_decisions: list[dict[str, Any]] = []
    missing_capabilities: list[str] = []
    requested_set = set(requested_capabilities)
    for name in sorted(packs):
        if name not in requested_set:
            capability_decisions.append(
                {"name": name, "status": "not-required", "discovered_skills": []}
            )
            continue
        discovered = sorted(set(packs[name].skill_alternatives) & skills)
        status = "satisfied" if discovered else "missing"
        if not discovered:
            missing_capabilities.append(name)
        capability_decisions.append(
            {"name": name, "status": status, "discovered_skills": discovered}
        )

    intent = str(request["intent"])
    selected_names: list[str] = []
    selected_reasons: dict[str, str] = {}
    rejected_reasons: dict[str, str] = {}
    fallbacks: list[str] = []
    warnings: list[str] = []
    blocked_reasons: list[str] = []
    force_inline = _small_inline_task(request)
    root_execution = intent == "inline" or (not request.get("delegation") and intent not in REVIEW_INTENTS)
    write_route = (
        intent in IMPLEMENTATION_INTENTS
        or (intent == "inline" and request["mutation"] == "write")
        or (intent == "integration-debugging" and request["confirmed_root_cause"])
    )
    file_change_route = request["mutation"] == "write" or (
        request["mutation"] == "diagnostic" and bool(surfaces)
    )
    parallel_strategy = "none"
    packages = request["independent_packages"]
    test_context = request.get("test_context")
    shared_test_resources = (
        list(test_context.get("shared_resources", []))
        if isinstance(test_context, Mapping)
        else []
    )
    if intent == "test-execution":
        if not _should_delegate_test(request, policy["test_routing"]):
            root_execution = True
            force_inline = not file_change_route and not request["security_sensitive"]
            warnings.append("Quiet blocking check is below the delegation threshold; root runs it while retaining required file-change/security review.")
        elif request.get("delegation"):
            force_inline = False

    native_applicable = (
        len(packages) > 1
        and intent in NATIVE_PARALLEL_INTENTS
        and not request["user_forbids_subagents"]
        and not force_inline
        and not root_execution
        and bool(request.get("delegation"))
    )
    native_parallel = native_applicable and not (intent == "test-execution" and shared_test_resources)

    if intent in READ_ONLY_INTENTS and request["mutation"] not in {"none", "read"}:
        blocked_reasons.append("Read-only intent cannot use write or diagnostic mutation.")
    if intent in IMPLEMENTATION_INTENTS and request["mutation"] != "write" and not force_inline:
        blocked_reasons.append("Implementation route requires write mutation.")
    if intent in {"reproduce-runtime", "test-execution"} and request["mutation"] not in {"none", "read", "diagnostic"}:
        blocked_reasons.append("Runtime reproduction/test execution requires diagnostic or read mutation.")
    if intent == "integration-debugging":
        if request["confirmed_root_cause"] and request["mutation"] != "write":
            blocked_reasons.append("Confirmed integration debugging requires write mutation.")
        elif not request["confirmed_root_cause"] and request["mutation"] not in {"none", "read", "diagnostic"}:
            blocked_reasons.append("Unconfirmed integration debugging requires diagnostic or read mutation.")
    if intent == "deep-analysis" and not request["user_forbids_subagents"] and (
        not request.get("escalation_reason") or request["complexity"] != "extreme"
    ):
        blocked_reasons.append("Astra analysis is reserved for extreme complexity with a recorded escalation reason; use Sol analysis for other tasks.")
    if write_route and request["mutation"] == "write":
        if not surfaces:
            blocked_reasons.append("A writing route requires at least one canonical write surface.")
        if not request["approved_design"] and intent != "quick-implementation":
            if request["user_forbids_subagents"]:
                warnings.append("Approved-design prerequisite is unmet; do not begin dependent implementation.")
            else:
                blocked_reasons.append("Write implementation requires an approved design.")
    if install_mode == "lite" and file_change_route and (
        _high_rigor(request) or intent == "integration-debugging" and request["confirmed_root_cause"]
    ):
        blocked_reasons.append("High-rigor risk or integration-debugging file changes, including diagnostics, require Hard mode.")
    prerequisites = _planning_prerequisites(request, registry, Path(project_root) if project_root is not None else None,
                                           simple=force_inline)
    if request["user_forbids_subagents"]:
        warnings.extend(prerequisites)
        if prerequisites or file_change_route or intent in REVIEW_INTENTS | {"architecture"}:
            warnings.append("Independent-review prerequisite is unmet when subagents are forbidden; do not claim independent acceptance or begin dependent work requiring it.")
    else:
        blocked_reasons.extend(prerequisites)
    if (
        request["mutation"] == "write"
        and request["requires_runtime_reproduction"]
        and not request["confirmed_root_cause"]
    ):
        blocked_reasons.append(
            "Required runtime reproduction must establish the root cause before implementation; "
            "complete a reproduce-runtime investigation, reconcile its evidence, then reroute."
        )
    elif blocked_reasons:
        pass
    elif request["user_forbids_subagents"]:
        warnings.append("User forbids subagents; the root agent must execute this request inline.")
    elif force_inline:
        warnings.append("Root handles this task directly; delegation would duplicate work or add overhead.")
    elif root_execution and not file_change_route and intent != "architecture" and not request["security_sensitive"]:
        warnings.append("No bounded delegation benefit was supplied; root performs the optional work.")
    else:
        desired, _ = _candidate_roles(request, registry, install_mode)
        if root_execution:
            desired = [name for name in desired if "skeptic-review" in registry[name].intents] if intent == "architecture" else []
        if intent == "architecture" and not any("skeptic-review" in registry[name].intents for name in desired):
            blocked_reasons.append(
                "Substantive architecture requires architectural judgment and an independent skeptic stage."
            )
        if intent in {"spec-review", "plan-gap-analysis", "plan-review"} and not desired:
            blocked_reasons.append("Planning review requires a registered independent critic.")
        def choose(
            required: str,
            *,
            selection_intent: str = intent,
            review_gate: bool = False,
            test_gate: bool = False,
            pressure_gate: bool = False,
            selected_reason: str | None = None,
        ) -> str | None:
            chain = [required] + _fallback_chain(required, registry)
            for candidate in chain:
                if candidate != required:
                    diagnostic_fallback = selection_intent in {"reproduce-runtime", "integration-debugging"} and not request["confirmed_root_cause"]
                    if selection_intent not in registry[candidate].intents and not diagnostic_fallback:
                        rejected_reasons.setdefault(candidate, "Fallback does not support the requested intent.")
                        continue
                    if _is_writer(registry[required]) or selection_intent == "visual-analysis":
                        tiers = {"gpt-6-luna": 1, "gpt-6.1-terra": 2, "gpt-6.1-sol": 3, "gpt-6-astra": 4}
                        if tiers.get(registry[candidate].model, 0) < tiers.get(registry[required].model, 0):
                            rejected_reasons.setdefault(candidate, "Required model tier cannot fall back to a lower tier.")
                            continue
                if candidate not in agents:
                    rejected_reasons.setdefault(
                        candidate,
                        f"role is not present in the available agent inventory (required by {required})",
                    )
                    continue
                allowed, reason = _is_role_allowed(
                    registry[candidate],
                    request,
                    intent=selection_intent,
                    review_gate=review_gate,
                    test_gate=test_gate,
                    pressure_gate=pressure_gate,
                )
                if not allowed:
                    rejected_reasons.setdefault(candidate, reason)
                    continue
                if candidate in selected_names:
                    return candidate
                if candidate != required:
                    fallbacks.append(
                        f"{required} unavailable; selected declared fallback {candidate}."
                    )
                    selected_reasons[candidate] = (
                        f"Declared fallback for unavailable {required}."
                    )
                else:
                    selected_reasons[candidate] = selected_reason or (
                        f"Sufficient canonical role under the complexity and risk policy for intent {selection_intent}."
                    )
                selected_names.append(candidate)
                return candidate
            blocked_reasons.append(
                f"No available safe role can satisfy required role {required}."
            )
            return None

        if not blocked_reasons:
            for required in desired:
                choose(required)

            if file_change_route:
                if install_mode == "lite" and _should_delegate_test(request, policy["test_routing"]):
                    runner = _cheapest_registered_role(registry, "test-execution")
                    if runner is None:
                        blocked_reasons.append(
                            "Lite write routes require a registered luna_test_runner stage."
                        )
                    else:
                        chosen_runner = choose(
                            runner,
                            selection_intent="test-execution",
                            test_gate=True,
                            selected_reason=(
                                "Worthwhile Lite post-write execution of the root plan's exact verification commands."
                            ),
                        )
                        if chosen_runner != "luna_test_runner":
                            blocked_reasons.append(
                                "Lite post-write validation must resolve to luna_test_runner without fallback."
                            )
                elif install_mode == "hard":
                    reviewer = _cheapest_registered_role(registry, "final-review")
                    if reviewer is None:
                        blocked_reasons.append(
                            "Every Hard write route requires a registered final-review role."
                        )
                    else:
                        chosen_reviewer = choose(
                            reviewer,
                            selection_intent="final-review",
                            review_gate=True,
                            selected_reason=(
                                "Mandatory independent Sol xhigh review for every Hard file-changing result."
                            ),
                        )
                        if chosen_reviewer != "sol_reviewer":
                            blocked_reasons.append(
                                "Mandatory Hard review must resolve to sol_reviewer without fallback."
                            )

            if request["security_sensitive"] and not any(
                "security-review" in registry[name].intents for name in selected_names
            ):
                security_role = _cheapest_registered_role(registry, "security-review")
                if security_role is None:
                    blocked_reasons.append(
                        "Security-sensitive work requires a registered security-review role."
                    )
                else:
                    choose(
                        security_role,
                        selection_intent="security-review",
                        review_gate=True,
                        selected_reason="Additional security-sensitive trust-boundary review.",
                    )

    if surfaces_overlap:
        warnings.append("Canonical write surfaces overlap; writer dispatch is serialized.")
    if intent == "test-execution" and shared_test_resources and len(packages) > 1:
        warnings.append(
            "Test packets share mutable resources ("
            + ", ".join(shared_test_resources)
            + "); execute them sequentially."
        )
    if native_parallel:
        warnings.append(
            "Use conservative native parallel dispatch only for independent read/test packets."
        )
    elif len(packages) > 1:
        if intent == "test-execution" and shared_test_resources:
            pass
        else:
            warnings.append(
                "Parallel writer dispatch requires an approved, semantically validated worktree overlay and user-approved worktrees in the separate V2 executor; use sequential dispatch."
            )

    if missing_capabilities:
        blocked_reasons.append(
            "Required capability pack(s) are not discovered: "
            + ", ".join(missing_capabilities)
            + "."
        )
        warnings.append(
            "Capability packs are satisfied only by caller-discovered skills; no automatic installation is performed."
        )
    if request["requires_external_docs"] and intent != "research-docs":
        warnings.append(
            "External documentation is requested; use discovered documentation skills where applicable."
        )
    if request["visual_or_browser"] and "frontend-browser" not in requested_set:
        warnings.append(
            "Visual/browser work was flagged without an explicit frontend-browser capability requirement."
        )

    max_agents = int(policy["budgets"]["max_agents"])
    max_writers = int(policy["budgets"]["max_writers"])
    max_read_only = int(policy["budgets"]["max_read_only"])
    max_reviewers = int(policy["budgets"]["max_reviewers"])
    writer_count = sum(
        1
        for name in selected_names
        if _is_writer(registry[name]) or _is_diagnostic(registry[name])
    )
    read_only_count = sum(1 for name in selected_names if _is_read_only(registry[name]))
    reviewer_count = sum(
        1
        for name in selected_names
        if _is_reviewer(registry[name])
    )
    planned_instance_count = (
        len(packages) + max(0, len(selected_names) - 1)
        if native_applicable and selected_names
        else len(selected_names)
    )
    if planned_instance_count > max_agents:
        blocked_reasons.append(
            f"Planned task-instance count exceeds max_agents={max_agents}."
        )
    if writer_count > max_writers:
        blocked_reasons.append(
            f"Selected writer count exceeds max_writers={max_writers}."
        )
    if read_only_count > max_read_only:
        blocked_reasons.append(
            f"Selected read-only count exceeds max_read_only={max_read_only}."
        )
    if reviewer_count > max_reviewers:
        blocked_reasons.append(
            f"Selected reviewer count exceeds max_reviewers={max_reviewers}."
        )

    selected_set = set(selected_names)
    for name in registry:
        if name not in selected_set:
            rejected_reasons.setdefault(
                name, f"Not selected: no sufficient role requirement for intent {intent}."
            )
    rejected_roles = [
        {"role": name, "reason": reason}
        for name, reason in rejected_reasons.items()
        if name not in selected_set
    ]
    selected_roles = [
        {
            "role": name,
            "reason": selected_reasons.get(name, f"Selected for intent {intent}."),
            "model": registry[name].model,
            "reasoning_effort": registry[name].model_reasoning_effort,
            "fork_turns": "none",
        }
        for name in selected_names
    ]

    write_ownership: list[dict[str, Any]] = []
    if root_execution and file_change_route and surfaces and not blocked_reasons:
        write_ownership.append({"role": "root", "surfaces": list(surfaces)})
    for name in selected_names:
        if (
            _is_writer(registry[name]) or _is_diagnostic(registry[name])
        ) and surfaces:
            write_ownership.append({"role": name, "surfaces": list(surfaces)})

    approval_gates, quality_gates = _workflow_gates(
        request, selected_names, registry, install_mode, blocked=bool(blocked_reasons)
    )
    if root_execution and file_change_route and selected_names and not blocked_reasons:
        quality_gates.append("Root completes implementation, diff inspection, and proportionate verification before dispatching the required final/security reviewers.")
    write_route_selected = any(
        _is_writer(registry[name]) for name in selected_names
    )
    if len(packages) > 1 and write_route_selected:
        approval_gates.append(
            "Ask the user before creating separate Git worktrees for parallel writers."
        )
        quality_gates.append(
            "Without explicit user worktree approval and validated isolation, keep writer packets sequential."
        )
    if not approval_gates and selected_names:
        approval_gates.append("Root approval is required before delegated dispatch.")
    if blocked_reasons:
        warnings.extend(blocked_reasons)

    inline_condition = (
        request["user_forbids_subagents"]
        or force_inline
        or (root_execution and not selected_names)
    )
    if blocked_reasons:
        mode = "blocked"
    elif inline_condition:
        mode = "inline"
    elif native_parallel:
        mode = "parallel"
        parallel_strategy = "native"
    else:
        mode = "sequential"

    if intent == "integration-debugging" and not request["confirmed_root_cause"]:
        classification = "integration-debugging:investigative"
        warnings.append(
            "Root cause is unconfirmed; the route stops at investigation and cannot dispatch a fixer."
        )
    elif _high_rigor(request):
        classification = f"{intent}:high-rigor"
    else:
        classification = intent

    task_instances: list[dict[str, Any]] = []
    parallel_waves: list[dict[str, Any]] = []
    if selected_names and mode not in {"inline", "blocked", "handoff"}:
        if native_applicable:
            primary = selected_names[0]
            primary_instances = [
                {
                    "task_id": f"task-{index:02d}-{primary}",
                    "role": primary,
                    "package": package,
                }
                for index, package in enumerate(packages, start=1)
            ]
            task_instances.extend(primary_instances)
            batch_size = 1 if mode == "sequential" else (
                int(policy["test_routing"]["max_parallel_runners"])
                if intent == "test-execution"
                else len(primary_instances)
            )
            for offset in range(0, len(primary_instances), batch_size):
                batch = primary_instances[offset : offset + batch_size]
                parallel_waves.append(
                    {
                        "id": len(parallel_waves) + 1,
                        "roles": [primary] * len(batch),
                        "task_ids": [item["task_id"] for item in batch],
                    }
                )
            for role in selected_names[1:]:
                wave_id = len(parallel_waves) + 1
                instance = {
                    "task_id": f"task-{wave_id:02d}-{role}",
                    "role": role,
                    "package": None,
                }
                task_instances.append(instance)
                parallel_waves.append(
                    {
                        "id": wave_id,
                        "roles": [role],
                        "task_ids": [instance["task_id"]],
                    }
                )
            quality_gates.append(
                "Instantiate one instance per independent package, give each a distinct task packet, and collect every result before dependent work or completion."
            )
        else:
            for index, role in enumerate(selected_names, start=1):
                instance = {
                    "task_id": f"task-{index:02d}-{role}",
                    "role": role,
                    "package": None,
                }
                task_instances.append(instance)
                parallel_waves.append(
                    {
                        "id": index,
                        "roles": [role],
                        "task_ids": [instance["task_id"]],
                    }
                )
    route: dict[str, Any] = {
        "workflow_owner": str(policy["workflow"]["root_owner"]),
        "root_work": mode == "inline" or (mode == "sequential" and (
            root_execution or intent == "architecture" and _root_owns_architecture(request)
        )),
        "mode": mode,
        "parallel_strategy": parallel_strategy,
        "classification": classification,
        "selected_roles": selected_roles,
        "rejected_roles": rejected_roles,
        "capability_packs": capability_decisions,
        "task_instances": task_instances,
        "parallel_waves": parallel_waves,
        "write_ownership": write_ownership,
        "approval_gates": approval_gates,
        "quality_gates": quality_gates,
        "fallbacks": fallbacks,
        "warnings": warnings,
    }
    route = _canonical_route(route, registry)
    errors = validate_instance(route, route_schema, schema_name=ROUTE_SCHEMA_NAME)
    if errors:
        raise ResolutionInputError(
            "resolver emitted an invalid route: " + "; ".join(errors)
        )
    return route

def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def render_text(route: Mapping[str, Any]) -> str:
    lines = [
        f"workflow_owner: {route['workflow_owner']}",
        f"root_work: {str(route.get('root_work', False)).lower()}",
        f"mode: {route['mode']}",
        f"parallel_strategy: {route['parallel_strategy']}",
        f"classification: {route['classification']}",
        "selected_roles:",
    ]
    for item in route["selected_roles"]:
        lines.append(f"  - {item['role']}: {item['reason']}")
    lines.append("rejected_roles:")
    for item in route["rejected_roles"]:
        lines.append(f"  - {item['role']}: {item['reason']}")
    lines.append("capability_packs:")
    for item in route["capability_packs"]:
        discovered = ", ".join(item["discovered_skills"]) or "-"
        lines.append(f"  - {item['name']}: {item['status']} ({discovered})")
    lines.append("task_instances:")
    for item in route["task_instances"]:
        package = item["package"] if item["package"] is not None else "-"
        lines.append(f"  - {item['task_id']}: {item['role']} ({package})")
    lines.append("parallel_waves:")
    for item in route["parallel_waves"]:
        pairs = ", ".join(
            f"{task_id}={role}"
            for task_id, role in zip(item["task_ids"], item["roles"])
        )
        lines.append(f"  - {item['id']}: {pairs}")
    lines.append("write_ownership:")
    for item in route["write_ownership"]:
        lines.append(f"  - {item['role']}: {', '.join(item['surfaces'])}")
    for field in ("approval_gates", "quality_gates", "fallbacks", "warnings"):
        lines.append(f"{field}:")
        for value in route[field]:
            lines.append(f"  - {value}")
    return "\n".join(lines) + "\n"


def _load_any_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON constant {value}")),
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ResolutionInputError(f"cannot load {label} JSON {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile a deterministic Codex worker route.")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--available-agents", type=Path)
    parser.add_argument("--available-skills", type=Path)
    parser.add_argument("--project-root", type=Path, help="explicit trusted root for planning artifacts and review ledger")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        request = _load_any_json(args.request, label="request")
        if not isinstance(request, dict):
            raise ResolutionInputError("request JSON root must be an object")
        agents = _load_any_json(args.available_agents, label="available-agents") if args.available_agents else None
        skills = _load_any_json(args.available_skills, label="available-skills") if args.available_skills else None
        route = resolve_request(request, agents, skills, project_root=args.project_root)
    except ResolutionInputError as exc:
        print(f"invalid route input: {exc}", file=sys.stderr)
        return 2

    rendered = canonical_json(route) if args.format == "json" else render_text(route)
    if args.output is None:
        sys.stdout.write(rendered)
    elif args.format == "json":
        try:
            atomic_write_json(args.output, route)
        except OSError as exc:
            print(f"cannot write route output: {exc}", file=sys.stderr)
            return 2
    else:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
        except OSError as exc:
            print(f"cannot write route output: {exc}", file=sys.stderr)
            return 2
    return 3 if route["mode"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
