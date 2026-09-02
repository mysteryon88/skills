#!/usr/bin/env python3
"""Compile a validated route from a request and discovered inventories.

This module is deliberately a pure compiler.  It reads the canonical role and
capability registries, applies conservative safety and budget rules, and never
spawns agents, writes state, or installs skills.  The command line wrapper only
handles JSON I/O and exit codes.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from orchestrator_lib import (
    RoleSpec,
    atomic_write_json,
    canonical_relative_path,
    load_capability_packs,
    load_install_profiles,
    load_json,
    load_role_registry,
    validate_instance,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ROLE_SCHEMA_NAME = "route-request"
ROUTE_SCHEMA_NAME = "route"

READ_ONLY_INTENTS = {
    "explore-code", "research-docs", "architecture", "skeptic-review",
    "plan-gap-analysis", "plan-review", "task-review", "final-review",
    "security-review",
}
IMPLEMENTATION_INTENTS = {
    "quick-implementation", "bounded-implementation", "deep-fixed-implementation",
    "test-authoring", "documentation",
}
NATIVE_PARALLEL_INTENTS = READ_ONLY_INTENTS | {"test-execution"}
REVIEW_INTENTS = {
    "skeptic-review", "plan-gap-analysis", "plan-review", "task-review",
    "final-review", "security-review",
}
WRITER_MUTATIONS = {"write", "documentation-only"}
PARALLEL_COMPANION = "parallelizing-subagent-plans"


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
        or any(lite_workflow.get(key) is not True for key in required_lite_workflow)
    ):
        raise ResolutionInputError(
            "routing policy must require a detailed root-authored Lite plan, "
            "post-write Luna tests, and root diff review"
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


def _role_sort_key(spec: RoleSpec, registry_order: Mapping[str, int]) -> tuple[int, int, str]:
    return spec.cost_rank, registry_order[spec.name], spec.name


def _cheapest_registered_role(
    registry: Mapping[str, RoleSpec],
    intent: str,
) -> str | None:
    registry_order = {name: index for index, name in enumerate(registry)}
    candidates = [spec for spec in registry.values() if intent in spec.intents]
    if not candidates:
        return None
    return min(candidates, key=lambda spec: _role_sort_key(spec, registry_order)).name


def _candidate_roles(
    request: Mapping[str, Any],
    registry: Mapping[str, RoleSpec],
) -> tuple[list[str], bool]:
    intent = str(request["intent"])
    if intent == "inline":
        return [], False
    if intent == "integration-debugging" and not request["confirmed_root_cause"]:
        investigative = _cheapest_registered_role(registry, "reproduce-runtime")
        return ([investigative] if investigative else []), False
    if intent == "architecture":
        architect = _cheapest_registered_role(registry, "architecture")
        skeptic = _cheapest_registered_role(registry, "skeptic-review") if _high_rigor(request) else None
        return ([name for name in (architect, skeptic) if name is not None], bool(skeptic))
    if intent in {"skeptic-review", "plan-gap-analysis", "plan-review"}:
        skeptic = _cheapest_registered_role(registry, intent)
        return ([skeptic] if skeptic else []), _high_rigor(request)
    primary = _cheapest_registered_role(registry, intent)
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


def _workflow_gates(
    request: Mapping[str, Any],
    selected_roles: Sequence[str],
    registry: Mapping[str, RoleSpec],
    install_mode: str,
) -> tuple[list[str], list[str]]:
    intent = str(request["intent"])
    approval: list[str] = []
    if intent in {"architecture", "research-docs"}:
        approval.append("superpowers:brainstorming owns requirements and design approval")
    if intent in {"skeptic-review", "plan-gap-analysis", "plan-review"}:
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
    write_selected = any(
        _is_writer(registry[role]) or _is_diagnostic(registry[role])
        for role in selected_roles
    )
    if write_selected:
        if install_mode == "lite":
            quality.extend(
                [
                    "The detailed Lite plan must include ordered steps, exact allowed files and write surfaces, protected interfaces, acceptance criteria, exact verification commands, dependencies, and stop conditions.",
                    "luna_worker executes only the approved plan; luna_test_runner runs the exact verification commands after implementation.",
                    "The root inspects the actual diff and test evidence and owns the completion decision; luna_test_runner is not a reviewer.",
                ]
            )
        else:
            quality.append(
                "Mandatory sol_reviewer / gpt-5.6-sol / xhigh review must accept the final integrated diff; no Terra fallback is allowed."
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
    if int(context["estimated_seconds"]) < threshold and context["blocks_next_step"]:
        return False
    return bool(
        int(context["estimated_seconds"]) >= threshold
        or context["parallel_value"]
        or context["noisy_output"]
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
    force_inline = False
    hard_write_skeptic: str | None = None
    parallel_strategy = "none"
    packages = request["independent_packages"]
    test_context = request.get("test_context")
    shared_test_resources = (
        list(test_context.get("shared_resources", []))
        if isinstance(test_context, Mapping)
        else []
    )

    companion_applicable = (
        request["approved_numbered_plan"]
        and request["delegated_execution_selected"]
        and not request["user_forbids_subagents"]
    )
    companion_discovered = PARALLEL_COMPANION in skills
    companion_compatible = (
        companion_discovered and PARALLEL_COMPANION not in incompatible_skills
    )
    native_applicable = (
        len(packages) > 1
        and intent in NATIVE_PARALLEL_INTENTS
        and not request["user_forbids_subagents"]
        and (not companion_applicable or not companion_discovered)
        and not (intent == "test-execution" and shared_test_resources)
    )

    if request["user_forbids_subagents"]:
        warnings.append("User forbids subagents; the root agent must execute this request inline.")
    elif intent == "inline":
        warnings.append("Explicit inline intent produces a zero-agent route.")
    elif (
        request["complexity"] == "trivial"
        and request["risk"] == "low"
        and request["mutation"] in {"none", "read"}
    ):
        warnings.append("Trivial low-risk request remains inline.")
    elif intent == "test-execution" and not _should_delegate_test(
        request, policy["test_routing"]
    ):
        force_inline = True
        warnings.append(
            "Focused blocking test is below the delegation threshold; run it in the root to avoid subagent overhead."
        )
    else:
        desired, high_rigor = _candidate_roles(request, registry)
        if high_rigor and intent == "architecture" and len(desired) < 2:
            blocked_reasons.append(
                "High-rigor architecture requires both sol_architect and skeptic stages."
            )
        if intent in READ_ONLY_INTENTS and request["mutation"] not in {"none", "read"}:
            blocked_reasons.append(
                "Read-only intent cannot delegate with write or diagnostic mutation."
            )
        if (
            intent == "integration-debugging"
            and not request["confirmed_root_cause"]
            and request["mutation"] not in {"none", "read", "diagnostic"}
        ):
            blocked_reasons.append(
                "Unconfirmed integration debugging requires diagnostic or read mutation."
            )
        if intent == "deep-fixed-implementation" and not request["approved_design"]:
            blocked_reasons.append("Deep fixed implementation requires an approved design.")
        if (
            intent in IMPLEMENTATION_INTENTS
            and intent != "quick-implementation"
            and not request["approved_design"]
        ):
            blocked_reasons.append("Write implementation requires an approved design.")
        if (
            intent == "integration-debugging"
            and request["confirmed_root_cause"]
            and not request["approved_design"]
        ):
            blocked_reasons.append(
                "Confirmed integration debugging requires an approved design."
            )
        write_route = (
            intent in IMPLEMENTATION_INTENTS
            or (
                intent == "integration-debugging"
                and request["confirmed_root_cause"]
            )
        )
        file_change_route = write_route or (
            request["mutation"] == "diagnostic" and bool(surfaces)
        )
        if write_route and request["mutation"] == "write" and not surfaces:
            blocked_reasons.append(
                "A writing route requires at least one canonical write surface."
            )
        if install_mode == "lite" and write_route and _high_rigor(request):
            blocked_reasons.append(
                "High-rigor writes (including high/critical risk) require Hard mode; "
                "Lite cannot provide the mandatory independent review stages."
            )
        if (
            install_mode == "lite"
            and intent == "integration-debugging"
            and request["confirmed_root_cause"]
        ):
            blocked_reasons.append(
                "Confirmed integration-debugging writes require Hard mode; "
                "Lite cannot provide the mandatory independent review stages."
            )
        if install_mode == "hard" and write_route and _high_rigor(request):
            hard_write_skeptic = _cheapest_registered_role(registry, "skeptic-review")
            if hard_write_skeptic is None:
                blocked_reasons.append(
                    "High-rigor Hard writes require a registered skeptic stage."
                )

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
                        f"Cheapest sufficient canonical role for intent {selection_intent}."
                    )
                selected_names.append(candidate)
                return candidate
            blocked_reasons.append(
                f"No available safe role can satisfy required role {required}."
            )
            return None

        if not blocked_reasons:
            if hard_write_skeptic is not None:
                choose(
                    hard_write_skeptic,
                    selection_intent="skeptic-review",
                    pressure_gate=True,
                    selected_reason=(
                        "Mandatory pre-write pressure test for a high-rigor Hard route."
                    ),
                )
            for required in desired:
                choose(required)

            if file_change_route:
                if install_mode == "lite":
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
                                "Required Lite post-write execution of the root plan's exact verification commands."
                            ),
                        )
                        if chosen_runner != "luna_test_runner":
                            blocked_reasons.append(
                                "Lite post-write validation must resolve to luna_test_runner without fallback."
                            )
                else:
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
    if companion_applicable and companion_discovered and not companion_compatible:
        blocked_reasons.append(
            f"Installed companion {PARALLEL_COMPANION} is incompatible; repair or remove it before this handoff."
        )
    elif companion_applicable and companion_compatible:
        warnings.append(
            f"Delegate dependency topology to {PARALLEL_COMPANION}; it alone may emit the V2 executor overlay."
        )
    elif native_applicable:
        warnings.append(
            "Use conservative native parallel dispatch only for independent read/test packets."
        )
    elif len(packages) > 1:
        if intent == "test-execution" and shared_test_resources:
            pass
        else:
            warnings.append(
                "Parallel writer dispatch requires a compatible plan compiler, validated worktree overlay, and user-approved worktrees; use sequential dispatch."
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
        if _is_reviewer(registry[name]) and name != hard_write_skeptic
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
        }
        for name in selected_names
    ]

    write_ownership: list[dict[str, Any]] = []
    for name in selected_names:
        if (
            _is_writer(registry[name]) or _is_diagnostic(registry[name])
        ) and surfaces:
            write_ownership.append({"role": name, "surfaces": list(surfaces)})

    approval_gates, quality_gates = _workflow_gates(
        request, selected_names, registry, install_mode
    )
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
        or intent == "inline"
        or force_inline
        or (
            request["complexity"] == "trivial"
            and request["risk"] == "low"
            and request["mutation"] in {"none", "read"}
        )
    )
    if blocked_reasons:
        mode = "blocked"
    elif inline_condition:
        mode = "inline"
    elif companion_applicable and companion_compatible:
        mode = "handoff"
        parallel_strategy = "companion"
    elif native_applicable:
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
        if mode == "parallel":
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
            batch_size = (
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
    if mode == "handoff":
        approval_gates.append(
            f"Read and follow {PARALLEL_COMPANION}; its PARALLEL overlay may target only orchestrating-parallel-worktree-changes-v2."
        )

    route: dict[str, Any] = {
        "workflow_owner": str(policy["workflow"]["root_owner"]),
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
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        request = _load_any_json(args.request, label="request")
        if not isinstance(request, dict):
            raise ResolutionInputError("request JSON root must be an object")
        agents = _load_any_json(args.available_agents, label="available-agents") if args.available_agents else None
        skills = _load_any_json(args.available_skills, label="available-skills") if args.available_skills else None
        route = resolve_request(request, agents, skills)
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
