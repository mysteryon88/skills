#!/usr/bin/env python3
"""Validate the bundled schema and cross-field semantics of a TON ZK proof-context manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

TOP_LEVEL_FIELDS = {
    "schemaVersion",
    "protocol",
    "curve",
    "status",
    "circuitId",
    "verifyingKey",
    "setup",
    "networkDomain",
    "contract",
    "action",
    "publicInputs",
    "domainSeparation",
    "replayProtection",
    "expiry",
    "stateBinding",
    "experimentalApproval",
}
REQUIRED_TOP_LEVEL = {
    "schemaVersion",
    "protocol",
    "curve",
    "status",
    "circuitId",
    "verifyingKey",
    "setup",
    "networkDomain",
    "contract",
    "action",
    "publicInputs",
    "domainSeparation",
    "replayProtection",
}
PROTOCOLS = {"groth16", "plonk"}
STATUSES = {"development", "experimental", "production-candidate"}
NETWORKS = {"sandbox", "testnet", "mainnet", "custom"}
INPUT_TYPES = {
    "field",
    "uint",
    "boolean",
    "address-hash",
    "cell-hash",
    "merkle-root",
    "nullifier",
    "nonce",
    "timestamp",
}
REPLAY_TYPES = {
    "nullifier": {"nullifier"},
    "nonce": {"nonce", "uint"},
    "seqno": {"nonce", "uint"},
    "one-shot": {"nullifier", "boolean", "uint"},
}
NAME_RE = re.compile(r"^[a-z][a-zA-Z0-9_]*$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
DECIMAL_RE = re.compile(r"^(0|[1-9][0-9]*)$")
ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
PROFILE_REGISTRY_PATH = ASSETS_DIR / "proof-context-profiles.json"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_object(parent: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return {}
    return value


def _require_string(parent: dict[str, Any], key: str, path: str, errors: list[str]) -> str | None:
    value = parent.get(key)
    if not _nonempty_string(value):
        errors.append(f"{path}.{key} must be a non-empty string")
        return None
    return value.strip()


def _duplicates(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    duplicates: list[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


class DuplicateKeyError(ValueError):
    """Raised when a JSON object contains the same member name more than once."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    except DuplicateKeyError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _load_profile_registry(path: Path = PROFILE_REGISTRY_PATH) -> dict[str, Any]:
    registry = _load_json(path)
    if not isinstance(registry, dict):
        raise ValueError(f"profile registry root must be an object: {path}")
    if registry.get("registryVersion") != 1:
        raise ValueError(f"unsupported profile registry version: {path}")
    if registry.get("curve") != "bls12-381":
        raise ValueError(f"profile registry must target bls12-381: {path}")
    if not isinstance(registry.get("domainProfiles"), dict):
        raise ValueError(f"profile registry domainProfiles must be an object: {path}")
    if not isinstance(registry.get("inputEncodings"), dict):
        raise ValueError(f"profile registry inputEncodings must be an object: {path}")
    return registry


def _validate_range(item: dict[str, Any], path: str, input_type: Any, bits: Any, errors: list[str]) -> None:
    value = item.get("range")
    required = input_type in {"uint", "nonce", "timestamp"}
    if value is None:
        if required:
            errors.append(f"{path}.range is required for type {input_type}")
        return
    if not isinstance(value, dict):
        errors.append(f"{path}.range must be an object with decimal minimum, maximum, and unit")
        return
    minimum = value.get("minimum")
    maximum = value.get("maximum")
    unit = value.get("unit")
    if not isinstance(minimum, str) or DECIMAL_RE.fullmatch(minimum) is None:
        errors.append(f"{path}.range.minimum must be an unsigned canonical decimal string")
    if not isinstance(maximum, str) or DECIMAL_RE.fullmatch(maximum) is None:
        errors.append(f"{path}.range.maximum must be an unsigned canonical decimal string")
    if not _nonempty_string(unit):
        errors.append(f"{path}.range.unit must be a non-empty string")
    if (
        isinstance(minimum, str)
        and isinstance(maximum, str)
        and DECIMAL_RE.fullmatch(minimum)
        and DECIMAL_RE.fullmatch(maximum)
    ):
        minimum_int = int(minimum)
        maximum_int = int(maximum)
        if minimum_int > maximum_int:
            errors.append(f"{path}.range.minimum must not exceed range.maximum")
        if _is_int(bits) and maximum_int >= 2**bits:
            errors.append(f"{path}.range.maximum does not fit in declared bits")


def _validate_expected_address(value: Any, network_workchain: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("contract.expectedAddress must be a raw-workchain-account-id-v1 object")
        return
    if value.get("format") != "raw-workchain-account-id-v1":
        errors.append("contract.expectedAddress.format must be raw-workchain-account-id-v1")
    workchain = value.get("workchain")
    if not _is_int(workchain) or not -(2**31) <= workchain < 2**31:
        errors.append("contract.expectedAddress.workchain must be a signed int32")
    elif _is_int(network_workchain) and workchain != network_workchain:
        errors.append("contract.expectedAddress.workchain must match networkDomain.workchain")
    account_id = value.get("accountId")
    if not isinstance(account_id, str) or HASH_RE.fullmatch(account_id) is None:
        errors.append("contract.expectedAddress.accountId must be 64 lowercase hexadecimal characters")
    if value.get("anycast") != "none":
        errors.append("contract.expectedAddress.anycast must be none")


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return _is_int(value)
    if expected == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _resolve_local_ref(root_schema: dict[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        raise ValueError(f"unsupported schema reference: {reference}")
    current: Any = root_schema
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"unresolvable schema reference: {reference}")
        current = current[part]
    return current


def validate_schema(
    data: Any,
    schema: Any,
    path: str = "$",
    root_schema: dict[str, Any] | None = None,
) -> list[str]:
    """Validate the JSON Schema subset used by the bundled proof-context schema."""

    if not isinstance(schema, dict):
        return [f"{path}: schema node must be an object"]
    if root_schema is None:
        root_schema = schema
    reference = schema.get("$ref")
    if isinstance(reference, str):
        try:
            target = _resolve_local_ref(root_schema, reference)
        except ValueError as exc:
            return [f"{path}: {exc}"]
        return validate_schema(data, target, path, root_schema)
    errors: list[str] = []

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _json_type_matches(data, expected_type):
        return [f"{path}: expected {expected_type}"]
    if "const" in schema and data != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")
    if isinstance(schema.get("enum"), list) and data not in schema["enum"]:
        errors.append(f"{path}: value is not in the allowed enum")

    if isinstance(data, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in data:
                    errors.append(f"{path}: missing required property {key}")
        if isinstance(properties, dict):
            if schema.get("additionalProperties") is False:
                for key in sorted(set(data) - set(properties)):
                    errors.append(f"{path}: unexpected property {key}")
            for key, value in data.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    errors.extend(validate_schema(value, child_schema, f"{path}.{key}", root_schema))

    if isinstance(data, list):
        minimum_items = schema.get("minItems")
        if _is_int(minimum_items) and len(data) < minimum_items:
            errors.append(f"{path}: expected at least {minimum_items} items")
        if schema.get("uniqueItems") is True:
            encoded = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in data]
            if len(set(encoded)) != len(encoded):
                errors.append(f"{path}: array items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(data):
                errors.extend(validate_schema(value, item_schema, f"{path}[{index}]", root_schema))

    if isinstance(data, str):
        minimum_length = schema.get("minLength")
        maximum_length = schema.get("maxLength")
        if _is_int(minimum_length) and len(data) < minimum_length:
            errors.append(f"{path}: string is shorter than {minimum_length}")
        if _is_int(maximum_length) and len(data) > maximum_length:
            errors.append(f"{path}: string is longer than {maximum_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, data) is None:
            errors.append(f"{path}: string does not match {pattern}")

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and data < minimum:
            errors.append(f"{path}: value is less than {minimum}")
        if isinstance(maximum, (int, float)) and data > maximum:
            errors.append(f"{path}: value is greater than {maximum}")

    return errors


def validate_manifest(data: Any) -> list[str]:
    """Return semantic validation errors for a parsed proof-context manifest."""

    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest root must be an object"]
    try:
        registry = _load_profile_registry()
    except ValueError as exc:
        return [str(exc)]
    domain_profiles = registry["domainProfiles"]
    encoding_rules = registry["inputEncodings"]

    missing = sorted(REQUIRED_TOP_LEVEL - set(data))
    if missing:
        errors.append(f"missing required top-level fields: {', '.join(missing)}")
    unknown = sorted(set(data) - TOP_LEVEL_FIELDS)
    if unknown:
        errors.append(f"unknown top-level fields: {', '.join(unknown)}")

    if data.get("schemaVersion") != "4":
        errors.append("schemaVersion must be '4'")
    if data.get("protocol") not in PROTOCOLS:
        errors.append("protocol must be groth16 or plonk")
    if data.get("curve") != "bls12-381":
        errors.append("curve must be bls12-381")
    if data.get("status") not in STATUSES:
        errors.append("status must be development, experimental, or production-candidate")
    if not _nonempty_string(data.get("circuitId")):
        errors.append("circuitId must be a non-empty string")

    verifying_key = _require_object(data, "verifyingKey", errors)
    if verifying_key:
        if verifying_key.get("hashAlgorithm") != "sha256":
            errors.append("verifyingKey.hashAlgorithm must be sha256")
        vk_hash = verifying_key.get("hash")
        if not isinstance(vk_hash, str) or not HASH_RE.fullmatch(vk_hash):
            errors.append("verifyingKey.hash must be 64 lowercase hexadecimal characters")
        if verifying_key.get("hashScope") != "exact-source-bytes":
            errors.append("verifyingKey.hashScope must be exact-source-bytes")
        _require_string(verifying_key, "source", "verifyingKey", errors)

    setup = _require_object(data, "setup", errors)
    if setup:
        kind = setup.get("kind")
        if kind not in {"groth16-phase2", "plonk-universal-srs"}:
            errors.append("setup.kind must be groth16-phase2 or plonk-universal-srs")
        protocol = data.get("protocol")
        if protocol == "groth16" and kind != "groth16-phase2":
            errors.append("Groth16 requires setup.kind=groth16-phase2")
        if protocol == "plonk" and kind != "plonk-universal-srs":
            errors.append("PLONK requires setup.kind=plonk-universal-srs")
        if setup.get("curve") != "bls12-381":
            errors.append("setup.curve must be bls12-381")
        power = setup.get("power")
        capacity = setup.get("capacity")
        if not _is_int(power) or not 1 <= power <= 63:
            errors.append("setup.power must be an integer in 1..63")
        if not _is_int(capacity) or capacity < 2:
            errors.append("setup.capacity must be an integer greater than one")
        elif _is_int(power) and capacity != 2**power:
            errors.append("setup.capacity must equal 2^setup.power")
        artifacts = setup.get("artifacts")
        if not isinstance(artifacts, dict):
            errors.append("setup.artifacts must be an object")
            artifacts = {}
        for artifact_name in ("powersOfTau", "r1cs", "finalZkey"):
            descriptor = artifacts.get(artifact_name)
            path = f"setup.artifacts.{artifact_name}"
            if not isinstance(descriptor, dict):
                errors.append(f"{path} must be a hashed artifact descriptor")
                continue
            _require_string(descriptor, "source", path, errors)
            if descriptor.get("hashAlgorithm") != "sha256":
                errors.append(f"{path}.hashAlgorithm must be sha256")
            digest = descriptor.get("hash")
            if not isinstance(digest, str) or HASH_RE.fullmatch(digest) is None:
                errors.append(f"{path}.hash must be 64 lowercase hexadecimal characters")
            if descriptor.get("hashScope") != "exact-source-bytes":
                errors.append(f"{path}.hashScope must be exact-source-bytes")
        commands = setup.get("verificationCommands")
        if not isinstance(commands, dict):
            errors.append("setup.verificationCommands must be an object")
        else:
            _require_string(commands, "powersOfTau", "setup.verificationCommands", errors)
            _require_string(commands, "finalZkey", "setup.verificationCommands", errors)
        for field in ("verificationEvidence", "contributionEvidence"):
            evidence = setup.get(field)
            if not isinstance(evidence, list) or not evidence or not all(_nonempty_string(item) for item in evidence):
                errors.append(f"setup.{field} must be a non-empty string array")
        _require_string(setup, "releaseBinding", "setup", errors)

    network = _require_object(data, "networkDomain", errors)
    if network:
        if network.get("network") not in NETWORKS:
            errors.append("networkDomain.network must be sandbox, testnet, mainnet, or custom")
        if network.get("globalIdSource") != "tvm-config-19":
            errors.append("networkDomain.globalIdSource must be tvm-config-19")
        global_id = network.get("expectedGlobalId")
        if not _is_int(global_id) or not -(2**31) <= global_id < 2**31:
            errors.append("networkDomain.expectedGlobalId must be a signed int32")
        workchain = network.get("workchain")
        if not _is_int(workchain) or not -(2**31) <= workchain < 2**31:
            errors.append("networkDomain.workchain must be a signed int32")
        if network.get("runtimeCheck") != "required":
            errors.append("networkDomain.runtimeCheck must be required")

    contract = _require_object(data, "contract", errors)
    if contract:
        _require_string(contract, "domainId", "contract", errors)
        binding = contract.get("addressBinding")
        if binding not in {"public-input", "authenticated-state", "deployment-constant"}:
            errors.append("contract.addressBinding is invalid")
        if binding in {"public-input", "deployment-constant"}:
            if "expectedAddress" not in contract:
                errors.append("contract.expectedAddress is required for public-input or deployment-constant binding")
            else:
                _validate_expected_address(contract.get("expectedAddress"), network.get("workchain"), errors)
        code_hash = contract.get("codeHash")
        if code_hash is not None and (not isinstance(code_hash, str) or not HASH_RE.fullmatch(code_hash)):
            errors.append("contract.codeHash must be 64 lowercase hexadecimal characters when present")

    action = _require_object(data, "action", errors)
    if action:
        _require_string(action, "name", "action", errors)
        version = action.get("version")
        if not _is_int(version) or version < 1:
            errors.append("action.version must be a positive integer")
        opcode = action.get("opcode")
        if not _is_int(opcode) or not 0 <= opcode <= 0xFFFFFFFF:
            errors.append("action.opcode must be a uint32")

    public_inputs_raw = data.get("publicInputs")
    input_by_name: dict[str, dict[str, Any]] = {}
    indices: list[int] = []
    names: list[str] = []
    encoding_groups: dict[str, list[tuple[str, str]]] = {}
    if not isinstance(public_inputs_raw, list) or not public_inputs_raw:
        errors.append("publicInputs must be a non-empty array")
        public_inputs: list[Any] = []
    else:
        public_inputs = public_inputs_raw

    for position, item in enumerate(public_inputs):
        path = f"publicInputs[{position}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        index = item.get("index")
        if not _is_int(index) or index < 0:
            errors.append(f"{path}.index must be a non-negative integer")
        else:
            indices.append(index)
        name = item.get("name")
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            errors.append(f"{path}.name must match {NAME_RE.pattern}")
        else:
            names.append(name)
            input_by_name[name] = item
        input_type = item.get("type")
        if input_type not in INPUT_TYPES:
            errors.append(f"{path}.type is invalid")
        for field in ("source", "semantics", "applicationCheck"):
            if not _nonempty_string(item.get(field)):
                errors.append(f"{path}.{field} must be a non-empty string")
        bits = item.get("bits")
        if bits is not None and (not _is_int(bits) or not 1 <= bits <= 256):
            errors.append(f"{path}.bits must be an integer in 1..256")
        if input_type in {"uint", "nonce", "timestamp", "address-hash", "cell-hash"} and bits is None:
            errors.append(f"{path}.bits is required for type {input_type}")
        if input_type == "boolean" and bits not in (None, 1):
            errors.append(f"{path}.bits must be 1 for boolean")
        _validate_range(item, path, input_type, bits, errors)
        encoding = item.get("encoding")
        if not _nonempty_string(encoding):
            errors.append(f"{path}.encoding must be a non-empty versioned encoding")
        elif encoding not in encoding_rules:
            errors.append(f"{path}.encoding is not a supported versioned encoding")
        else:
            rule = encoding_rules[encoding]
            rule_types = rule.get("types")
            if not isinstance(rule_types, list) or input_type not in rule_types:
                errors.append(f"{path}.encoding is incompatible with type {input_type}")
            expected_bits = rule.get("bits")
            if expected_bits is not None and bits != expected_bits:
                errors.append(f"{path}.bits must be {expected_bits} for encoding {encoding}")
            pair_family = rule.get("pairFamily")
            pair_limb = rule.get("pairLimb")
            if isinstance(pair_family, str) and isinstance(pair_limb, str):
                encoding_group = item.get("encodingGroup")
                if not _nonempty_string(encoding_group):
                    errors.append(f"{path}.encodingGroup is required for paired 128-bit hash limbs")
                else:
                    encoding_groups.setdefault(encoding_group, []).append((pair_family, pair_limb))

    if indices and indices != list(range(len(public_inputs))):
        errors.append("public input indices must be unique and contiguous from zero in array order")
    duplicate_indices = _duplicates(indices)
    if duplicate_indices:
        errors.append(f"duplicate public input indices: {', '.join(map(str, duplicate_indices))}")
    duplicate_names = _duplicates(names)
    if duplicate_names:
        errors.append(f"duplicate public input names: {', '.join(duplicate_names)}")
    for group, pairs in sorted(encoding_groups.items()):
        families = {family for family, _ in pairs}
        limbs = {limb for _, limb in pairs}
        if len(pairs) != 2 or len(families) != 1 or limbs != {"high128", "low128"}:
            errors.append(
                f"encodingGroup {group} must contain exactly both high128 and low128 limbs from one encoding family"
            )

    domain = _require_object(data, "domainSeparation", errors)
    if domain:
        domain_input = domain.get("inputName")
        if not _nonempty_string(domain_input) or domain_input not in input_by_name:
            errors.append("domainSeparation.inputName must reference an existing public input")
        elif input_by_name[domain_input].get("type") != "field":
            errors.append("domainSeparation.inputName must reference a field public input")
        elif not _nonempty_string(input_by_name[domain_input].get("encoding")):
            errors.append("domainSeparation.inputName must define an explicit field encoding")
        profile_name = domain.get("profile")
        profile = domain_profiles.get(profile_name) if isinstance(profile_name, str) else None
        if not isinstance(profile, dict):
            errors.append("domainSeparation.profile is not registered")
        elif _nonempty_string(domain_input) and domain_input in input_by_name:
            expected_encoding = profile.get("publicInputEncoding")
            if input_by_name[domain_input].get("encoding") != expected_encoding:
                errors.append(
                    "domainSeparation.inputName encoding must match the registered domain profile"
                )
        fields = domain.get("fields")
        if not isinstance(fields, list) or not fields or not all(_nonempty_string(field) for field in fields):
            errors.append("domainSeparation.fields must be a non-empty string array")
        else:
            duplicates = _duplicates(fields)
            if duplicates:
                errors.append(f"duplicate domain separation fields: {', '.join(duplicates)}")
            field_set = set(fields)
            if isinstance(profile, dict):
                required_fields = profile.get("requiredFields")
                required_set = set(required_fields) if isinstance(required_fields, list) else set()
                missing_domain = sorted(required_set - field_set)
                if missing_domain:
                    errors.append(f"domainSeparation.fields is missing: {', '.join(missing_domain)}")
                unknown_domain = sorted(field_set - required_set)
                if unknown_domain:
                    errors.append(f"domainSeparation.fields contains unknown values: {', '.join(unknown_domain)}")

    replay = _require_object(data, "replayProtection", errors)
    if replay:
        mode = replay.get("mode")
        if mode not in REPLAY_TYPES:
            errors.append("replayProtection.mode is invalid")
        input_name = replay.get("inputName")
        if not _nonempty_string(input_name) or input_name not in input_by_name:
            errors.append("replayProtection.inputName must reference an existing public input")
        elif mode in REPLAY_TYPES and input_by_name[input_name].get("type") not in REPLAY_TYPES[mode]:
            allowed = ", ".join(sorted(REPLAY_TYPES[mode]))
            errors.append(f"replayProtection.inputName type must be one of: {allowed}")
        _require_string(replay, "storageKey", "replayProtection", errors)
        domain_fields = replay.get("domainFields")
        if not isinstance(domain_fields, list) or not domain_fields or not all(
            _nonempty_string(field) for field in domain_fields
        ):
            errors.append("replayProtection.domainFields must be a non-empty string array")
        else:
            duplicates = _duplicates(domain_fields)
            if duplicates:
                errors.append(f"duplicate replay domain fields: {', '.join(duplicates)}")
            missing_inputs = sorted(set(domain_fields) - set(input_by_name))
            if missing_inputs:
                errors.append(
                    "replayProtection.domainFields must reference public input names; missing: "
                    + ", ".join(missing_inputs)
                )
            domain_input = domain.get("inputName") if isinstance(domain, dict) else None
            if _nonempty_string(domain_input) and domain_input not in domain_fields:
                errors.append("replayProtection.domainFields must include domainSeparation.inputName")

    expiry = data.get("expiry")
    if expiry is not None:
        if not isinstance(expiry, dict):
            errors.append("expiry must be an object")
        else:
            input_name = expiry.get("inputName")
            if not _nonempty_string(input_name) or input_name not in input_by_name:
                errors.append("expiry.inputName must reference an existing public input")
            elif input_by_name[input_name].get("type") not in {"timestamp", "uint"}:
                errors.append("expiry.inputName must reference a timestamp or uint public input")
            if expiry.get("clock") != "blockchain-now":
                errors.append("expiry.clock must be blockchain-now")
            max_future = expiry.get("maxFutureSeconds")
            if max_future is not None and (not _is_int(max_future) or max_future < 1):
                errors.append("expiry.maxFutureSeconds must be a positive integer when present")

    state_binding = data.get("stateBinding")
    if state_binding is not None:
        if not isinstance(state_binding, dict):
            errors.append("stateBinding must be an object")
        else:
            input_name = state_binding.get("inputName")
            if not _nonempty_string(input_name) or input_name not in input_by_name:
                errors.append("stateBinding.inputName must reference an existing public input")
            elif input_by_name[input_name].get("type") not in {"merkle-root", "cell-hash", "field"}:
                errors.append("stateBinding.inputName must reference a merkle-root, cell-hash, or field input")
            _require_string(state_binding, "source", "stateBinding", errors)

    if data.get("protocol") == "plonk" and data.get("status") == "production-candidate":
        approval = data.get("experimentalApproval")
        if not isinstance(approval, dict) or approval.get("approved") is not True:
            errors.append("production-candidate PLONK requires experimentalApproval.approved=true")
        else:
            _require_string(approval, "rationale", "experimentalApproval", errors)
            evidence = approval.get("evidence")
            if not isinstance(evidence, list) or not evidence or not all(_nonempty_string(item) for item in evidence):
                errors.append("experimentalApproval.evidence must be a non-empty string array")
        if not isinstance(setup, dict) or setup.get("kind") != "plonk-universal-srs":
            errors.append("production-candidate PLONK requires setup.kind=plonk-universal-srs")
    if data.get("status") == "production-candidate" and isinstance(setup, dict):
        artifacts = setup.get("artifacts")
        commands = setup.get("verificationCommands")
        expected_suffixes = {
            "powersOfTau": ".ptau",
            "r1cs": ".r1cs",
            "finalZkey": ".zkey",
        }
        if isinstance(artifacts, dict):
            for name, suffix in expected_suffixes.items():
                descriptor = artifacts.get(name)
                source = descriptor.get("source") if isinstance(descriptor, dict) else None
                if not isinstance(source, str) or not source.lower().endswith(suffix):
                    errors.append(
                        f"production-candidate setup.artifacts.{name}.source must name the reviewed {suffix} artifact"
                    )
        if isinstance(commands, dict):
            powers_command = commands.get("powersOfTau")
            zkey_command = commands.get("finalZkey")
            if not isinstance(powers_command, str) or "powersoftau verify" not in powers_command.lower():
                errors.append("production-candidate setup verification must run powersoftau verify")
            if not isinstance(zkey_command, str) or "zkey verify" not in zkey_command.lower():
                errors.append("production-candidate setup verification must run zkey verify")
            if isinstance(artifacts, dict):
                descriptors = {
                    name: artifacts.get(name) if isinstance(artifacts.get(name), dict) else {}
                    for name in ("powersOfTau", "r1cs", "finalZkey")
                }
                powers_source = descriptors["powersOfTau"].get("source")
                r1cs_source = descriptors["r1cs"].get("source")
                zkey_source = descriptors["finalZkey"].get("source")
                if isinstance(powers_command, str) and isinstance(powers_source, str) and powers_source not in powers_command:
                    errors.append("powersoftau verify command must name setup.artifacts.powersOfTau.source")
                if isinstance(zkey_command, str):
                    for name, source in (
                        ("powersOfTau", powers_source),
                        ("r1cs", r1cs_source),
                        ("finalZkey", zkey_source),
                    ):
                        if isinstance(source, str) and source not in zkey_command:
                            errors.append(f"zkey verify command must name setup.artifacts.{name}.source")

    return errors


def _validate_hashed_artifact(
    descriptor: Any,
    project_root: Path,
    field: str,
    mismatch_label: str,
) -> list[str]:
    """Verify one descriptor's exact bytes inside a trusted project boundary."""

    errors: list[str] = []
    if not isinstance(descriptor, dict):
        return [f"artifact identity cannot be checked because {field} is not an object"]
    source = descriptor.get("source")
    if not _nonempty_string(source):
        return [f"{field}.source must be a non-empty project-relative path"]

    try:
        root = project_root.resolve(strict=True)
    except OSError as exc:
        return [f"project root cannot be resolved: {exc}"]
    if not root.is_dir():
        return [f"project root is not a directory: {root}"]

    relative = Path(source)
    if relative.is_absolute() or relative.anchor:
        return [f"{field}.source must be project-relative, not absolute"]
    if ".." in relative.parts:
        return [f"{field}.source escapes project root via '..'"]

    candidate = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            errors.append(f"{field}.source must not traverse a symlink: {current}")
            return errors

    resolved = candidate.resolve(strict=False)
    try:
        if os.path.commonpath((str(root), str(resolved))) != str(root):
            return [f"{field}.source escapes project root"]
    except ValueError:
        return [f"{field}.source escapes project root"]

    if not candidate.exists():
        return [f"{field}.source does not exist: {source}"]
    if not candidate.is_file():
        return [f"{field}.source is not a regular file: {source}"]

    try:
        actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    except OSError as exc:
        return [f"cannot read {field}.source {source}: {exc}"]
    expected_hash = descriptor.get("hash")
    if not isinstance(expected_hash, str) or HASH_RE.fullmatch(expected_hash) is None:
        return [f"{field}.hash is not a canonical SHA-256 hex digest"]
    if actual_hash != expected_hash:
        return [
            f"{mismatch_label} SHA-256 mismatch for {source}: expected {expected_hash}, got {actual_hash}"
        ]
    return []


def validate_artifact_identities(data: Any, project_root: Path) -> tuple[list[str], list[str]]:
    """Verify VK bytes and, for a release candidate, every declared setup artifact."""

    if not isinstance(data, dict):
        return ["artifact identity cannot be checked because manifest root is not an object"], []
    vk_errors = _validate_hashed_artifact(
        data.get("verifyingKey"), project_root, "verifyingKey", "verifyingKey"
    )
    setup_errors: list[str] = []
    if data.get("status") == "production-candidate":
        setup = data.get("setup")
        artifacts = setup.get("artifacts") if isinstance(setup, dict) else None
        if not isinstance(artifacts, dict):
            setup_errors.append("release setup artifact identity cannot be checked because setup.artifacts is not an object")
        else:
            for name, label in (
                ("powersOfTau", "Powers of Tau"),
                ("r1cs", "R1CS"),
                ("finalZkey", "final zkey"),
            ):
                setup_errors.extend(
                    _validate_hashed_artifact(
                        artifacts.get(name),
                        project_root,
                        f"setup.artifacts.{name}",
                        label,
                    )
                )
    return vk_errors, setup_errors


def validate_artifact_identity(data: Any, project_root: Path) -> list[str]:
    """Backward-compatible aggregate of exact-byte identity errors."""

    vk_errors, setup_errors = validate_artifact_identities(data, project_root)
    return vk_errors + setup_errors


def validate_document(data: Any, schema: Any) -> tuple[list[str], list[str]]:
    return validate_schema(data, schema), validate_manifest(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="proof-context JSON manifest")
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "proof-context.schema.json",
        help="JSON Schema path; defaults to the schema bundled with this skill",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        help="trusted project boundary for every declared artifact source; defaults to the manifest directory",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        data = _load_json(args.manifest)
        schema = _load_json(args.schema)
    except ValueError as exc:
        parser.error(str(exc))

    schema_errors, semantic_errors = validate_document(data, schema)
    vk_errors, setup_artifact_errors = validate_artifact_identities(
        data, args.project_root or args.manifest.parent
    )
    artifact_errors = vk_errors + setup_artifact_errors
    manifest_valid = not schema_errors and not semantic_errors
    verification_key_identity_verified = manifest_valid and not vk_errors
    release_artifacts_required = isinstance(data, dict) and data.get("status") == "production-candidate"
    setup_artifact_identity_status = (
        "verified"
        if release_artifacts_required and manifest_valid and not setup_artifact_errors
        else "failed"
        if release_artifacts_required
        else "not-required"
    )
    release_artifact_set_identity_verified = (
        release_artifacts_required and manifest_valid and not vk_errors and not setup_artifact_errors
    )
    errors = schema_errors + semantic_errors + artifact_errors
    if args.format == "json":
        print(
            json.dumps(
                {
                    "valid": not errors,
                    "manifestValid": manifest_valid,
                    "schemaValid": not schema_errors,
                    "semanticConsistencyVerified": not semantic_errors,
                    "verificationKeyIdentityVerified": verification_key_identity_verified,
                    "setupArtifactIdentityStatus": setup_artifact_identity_status,
                    "releaseArtifactSetIdentityVerified": release_artifact_set_identity_verified,
                    "setupVerificationEvidence": "recorded-not-executed",
                    "implementationVerification": "not-assessed",
                    "schemaErrors": schema_errors,
                    "semanticErrors": semantic_errors,
                    "artifactErrors": artifact_errors,
                    "errors": errors,
                },
                indent=2,
            )
        )
    elif errors:
        print(f"Proof-context validation failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        count = len(data.get("publicInputs", [])) if isinstance(data, dict) else 0
        protocol = data.get("protocol", "unknown") if isinstance(data, dict) else "unknown"
        print(
            f"Proof-context manifest and required artifact identity validation passed: "
            f"{count} public inputs, protocol {protocol}; release artifact set "
            f"{'verified' if release_artifact_set_identity_verified else 'not required'}, "
            f"implementation not assessed."
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
