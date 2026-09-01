"""Deterministic, local route/v1 and route/v2 resolution.

This module supports versioned route/v1 and route/v2 contracts.  It reads
immutable package data and a validated project selection.  It does not invoke a
host, provider, process, network, or credential store.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from router_config import (
    CONVENTIONAL_CONFIG,
    config_digest,
    reject_retired_profile_id,
    resolve_config_path,
    validate_config_for_version,
    validate_config_versioned,
)


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
PROFILE_DIR = ASSET_DIR / "profiles"
CATALOG_PATH = ASSET_DIR / "provider-catalog.json"
V2_PROFILE_ID = "gpt5.6"
ROUTE_SLOTS = (
    "control-plane",
    "writer.c0-batch",
    "writer.c1",
    "writer.c2",
    "writer.c3",
    "validator.independent",
    "writer.high-volume-deterministic",
)
WRITER_ROUTE_SLOTS = (
    "writer.c0-batch",
    "writer.c1",
    "writer.c2",
    "writer.c3",
)
ROUTE_SLOTS_V2 = (
    "control-plane",
    "writer.c0-batch",
    "writer.c1",
    "writer.c2",
    "writer.c3",
    "validator.assurance",
    "writer.high-volume-deterministic",
)
PROFILE_IDS = (V2_PROFILE_ID,)
EVIDENCE = (
    "model-not-found",
    "authenticated-provider-outage",
    "quota-exhaustion",
    "repeated-bounded-transport-failure",
)
LIMITATION = "Host execution is not performed by this router; enforcement status is not-executed."
FORBIDDEN_KEYS = {
    "auth", "authentication", "command", "commands", "credential", "credentials",
    "endpoint", "endpoints", "price", "prices", "secret", "secrets", "token",
    "tokens", "transport", "transports", "password", "key", "keys",
}
SAFE_RELATIVE = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f\x7f]+(?:[/\\][^\\/:*?\"<>|\x00-\x1f\x7f]+)*$")
V2_ROUTE_KEY = re.compile(r"^[^/\s]+/[^/\s]+$")
OWNER_R3_LIMITATION = (
    "Owner boundary: R3 dual assurance cannot proceed without both required "
    "Validator routes; single-validator degradation is forbidden."
)


def _fail(message: str) -> None:
    raise ValueError(message)


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        _fail(f"{field} must be a non-empty clean string")
    return value


def _scan_forbidden(value: Any, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                _fail(f"non-string key at {location}")
            if key.casefold() in FORBIDDEN_KEYS:
                _fail(f"forbidden key: {key}")
            _scan_forbidden(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{location}[{index}]")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail(f"cannot read JSON input {path}: {exc}")


def _json_value(value: Any, field: str) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return None
    path = Path(value)
    if path.exists():
        return _load_json(path)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            _fail(f"{field} must be a JSON path or value: {exc}")
    _fail(f"{field} must be a JSON path or value")


def validate_catalog(catalog: Any) -> dict[str, Any]:
    _scan_forbidden(catalog)
    if not isinstance(catalog, dict) or set(catalog) != {"schema_version", "catalog_id", "providers"}:
        _fail("catalog keys are invalid")
    if type(catalog["schema_version"]) is not int or catalog["schema_version"] != 1:
        _fail("catalog schema_version must be 1")
    _string(catalog["catalog_id"], "catalog_id")
    providers = catalog["providers"]
    if not isinstance(providers, dict) or set(providers) != {"openai", "zai", "deepseek"}:
        _fail("catalog providers are not exact")
    expected = {
        "openai": ("custom", {
            "gpt-5.6-luna": (["max"], "explicit"),
            "gpt-5.6-terra": (["max"], "explicit"),
            "gpt-5.6-sol": (["high"], "explicit"),
        }),
        "zai": ("zai", {
            "glm-5.3": (["low", "high", "max"], "provider-default"),
            "glm-5.3-flash": (["low", "high", "max"], "provider-default"),
        }),
        "deepseek": ("deepseek", {
            "deepseek-v4-pro": (["max"], "explicit"),
            "deepseek-v4-flash": (["max"], "explicit"),
        }),
    }
    for provider, (runtime_provider, models) in expected.items():
        item = providers[provider]
        if not isinstance(item, dict) or set(item) != {"runtime_provider", "models"}:
            _fail(f"provider {provider} shape is invalid")
        if item["runtime_provider"] != runtime_provider or set(item["models"]) != set(models):
            _fail(f"provider {provider} identity drifted")
        for model, (reasoning, delivery) in models.items():
            definition = item["models"][model]
            if not isinstance(definition, dict) or set(definition) != {"reasoning", "reasoning_delivery"}:
                _fail(f"model {provider}/{model} shape is invalid")
            if definition["reasoning"] != reasoning or definition["reasoning_delivery"] != delivery:
                _fail(f"model {provider}/{model} capability drifted")
    return json.loads(json.dumps(catalog))


def load_catalog(path: Any = None) -> dict[str, Any]:
    return validate_catalog(_load_json(Path(path) if path is not None else CATALOG_PATH))


def _validate_route(route: Any, catalog: dict[str, Any], field: str) -> dict[str, str]:
    if not isinstance(route, dict) or set(route) != {"provider", "model", "reasoning", "reasoning_delivery"}:
        _fail(f"{field} route shape is invalid")
    provider = _string(route["provider"], f"{field}.provider")
    model = _string(route["model"], f"{field}.model")
    reasoning = _string(route["reasoning"], f"{field}.reasoning")
    delivery = _string(route["reasoning_delivery"], f"{field}.reasoning_delivery")
    try:
        definition = catalog["providers"][provider]["models"][model]
    except KeyError:
        _fail(f"{field} is not in provider catalog")
    if reasoning not in definition["reasoning"] or delivery != definition["reasoning_delivery"]:
        _fail(f"{field} capability does not match provider catalog")
    return {"provider": provider, "model": model, "reasoning": reasoning, "reasoning_delivery": delivery}


def validate_profile(profile: Any, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(profile, dict):
        reject_retired_profile_id(profile.get("profile_id"))
    catalog = validate_catalog(catalog if catalog is not None else load_catalog())
    _scan_forbidden(profile)
    required = {"schema_version", "profile_id", "default_active", "activation", "evidence_date", "slots", "forbidden_defaults"}
    if not isinstance(profile, dict) or set(profile) != required:
        _fail("profile keys are invalid")
    if type(profile["schema_version"]) is not int or profile["schema_version"] != 1:
        _fail("profile schema_version must be 1")
    _string(profile["profile_id"], "profile_id")
    if profile["default_active"] is not False or profile["activation"] != "explicit-owner-selection":
        _fail("profile identity or activation drifted")
    if profile["evidence_date"] != "2026-08-28":
        _fail("profile evidence date drifted")
    slots = profile["slots"]
    if not isinstance(slots, dict) or set(slots) != set(ROUTE_SLOTS):
        _fail("profile slots are not exact")
    for slot in ROUTE_SLOTS[:5]:
        item = slots[slot]
        if not isinstance(item, dict) or set(item) != {"primary"}:
            _fail(f"{slot} shape is invalid")
        _validate_route(item["primary"], catalog, f"slots.{slot}.primary")
    validator = slots["validator.independent"]
    if not isinstance(validator, dict) or set(validator) != {
        "primary", "fallback", "accepted_primary_unavailable_evidence", "independent_validator_source"
    }:
        _fail("validator slot shape is invalid")
    _validate_route(validator["primary"], catalog, "validator.primary")
    _validate_route(validator["fallback"], catalog, "validator.fallback")
    if validator["accepted_primary_unavailable_evidence"] != list(EVIDENCE) or validator["independent_validator_source"] != "openai-complexity-map":
        _fail("validator fallback contract drifted")
    high = slots["writer.high-volume-deterministic"]
    if not isinstance(high, dict) or set(high) != {
        "primary", "fallback", "accepted_primary_unavailable_evidence", "independent_validator_source",
        "default", "requires_explicit_task_selection"
    }:
        _fail("high-volume slot shape is invalid")
    _validate_route(high["primary"], catalog, "high-volume.primary")
    _validate_route(high["fallback"], catalog, "high-volume.fallback")
    if (
        high["accepted_primary_unavailable_evidence"] != list(EVIDENCE)
        or high["independent_validator_source"] != "openai-complexity-map"
        or high["default"] is not False
        or high["requires_explicit_task_selection"] is not True
    ):
        _fail("high-volume fallback contract drifted")
    expected_forbidden = [
        "gpt-5.6-sol:xhigh", "gpt-5.6-sol:max", "gpt-5.6-sol:ultra",
        "gpt-5.6-luna:low", "gpt-5.6-luna:medium", "gpt-5.6-luna:high", "gpt-5.6-luna:xhigh",
        "gpt-5.6-terra:low", "gpt-5.6-terra:medium", "gpt-5.6-terra:high", "gpt-5.6-terra:xhigh",
        "gpt-5.5:*", "gpt-5.4:*",
    ]
    if profile["forbidden_defaults"] != expected_forbidden:
        _fail("forbidden defaults drifted")
    return json.loads(json.dumps(profile))


def validate_profile_v2(profile: Any, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate the additive route/v2 assurance profile contract."""

    if isinstance(profile, dict):
        reject_retired_profile_id(profile.get("profile_id"))
    catalog = validate_catalog(catalog if catalog is not None else load_catalog())
    _scan_forbidden(profile)
    required = {"schema_version", "profile_id", "default_active", "activation", "evidence_date", "slots", "forbidden_defaults"}
    if not isinstance(profile, dict) or set(profile) != required:
        _fail("profile keys are invalid")
    if type(profile["schema_version"]) is not int or profile["schema_version"] != 2:
        _fail("profile schema_version must be 2")
    _string(profile["profile_id"], "profile_id")
    if profile["default_active"] is not False or profile["activation"] != "explicit-owner-selection":
        _fail("profile identity or activation drifted")
    if profile["evidence_date"] != "2026-08-31":
        _fail("profile evidence date drifted")

    slots = profile["slots"]
    if not isinstance(slots, dict) or set(slots) != set(ROUTE_SLOTS_V2):
        _fail("profile slots are not exact")
    for slot in ROUTE_SLOTS_V2[:5]:
        item = slots[slot]
        if not isinstance(item, dict) or set(item) != {"primary"}:
            _fail(f"{slot} shape is invalid")
        _validate_route(item["primary"], catalog, f"slots.{slot}.primary")

    assurance = slots["validator.assurance"]
    if not isinstance(assurance, dict) or set(assurance) != {
        "allow_same_model_as_writer",
        "accepted_route_failure_evidence",
        "routes_by_risk",
        "exhaustion_action",
    }:
        _fail("assurance validator slot shape is invalid")
    if assurance["allow_same_model_as_writer"] is not True:
        _fail("assurance validator same-model policy drifted")
    if assurance["accepted_route_failure_evidence"] != list(EVIDENCE):
        _fail("assurance validator evidence contract drifted")
    if assurance["exhaustion_action"] != "blocked-owner":
        _fail("assurance validator exhaustion action drifted")
    expected_routes = {
        "R1": [
            {"provider": "openai", "model": "gpt-5.6-luna", "reasoning": "max", "reasoning_delivery": "explicit"},
            {"provider": "openai", "model": "gpt-5.6-terra", "reasoning": "max", "reasoning_delivery": "explicit"},
            {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high", "reasoning_delivery": "explicit"},
        ],
        "R2": [
            {"provider": "openai", "model": "gpt-5.6-terra", "reasoning": "max", "reasoning_delivery": "explicit"},
            {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high", "reasoning_delivery": "explicit"},
        ],
        "R3": [
            {"provider": "openai", "model": "gpt-5.6-terra", "reasoning": "max", "reasoning_delivery": "explicit"},
            {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high", "reasoning_delivery": "explicit"},
        ],
    }
    routes_by_risk = assurance["routes_by_risk"]
    if not isinstance(routes_by_risk, dict) or set(routes_by_risk) != set(expected_routes):
        _fail("assurance validator risk routes are invalid")
    for risk, expected in expected_routes.items():
        routes = routes_by_risk[risk]
        if not isinstance(routes, list) or len(routes) != len(expected):
            _fail(f"assurance validator {risk} route chain is invalid")
        for index, (route, expected_route) in enumerate(zip(routes, expected)):
            actual = _validate_route(route, catalog, f"slots.validator.assurance.routes_by_risk.{risk}[{index}]")
            if actual != expected_route:
                _fail(f"assurance validator {risk} route chain drifted")

    expected_forbidden = [
        "gpt-5.6-sol:xhigh", "gpt-5.6-sol:max", "gpt-5.6-sol:ultra",
        "gpt-5.6-luna:low", "gpt-5.6-luna:medium", "gpt-5.6-luna:high", "gpt-5.6-luna:xhigh",
        "gpt-5.6-terra:low", "gpt-5.6-terra:medium", "gpt-5.6-terra:high", "gpt-5.6-terra:xhigh",
        "gpt-5.5:*", "gpt-5.4:*",
    ]
    if profile["forbidden_defaults"] != expected_forbidden:
        _fail("forbidden defaults drifted")
    high = slots["writer.high-volume-deterministic"]
    if not isinstance(high, dict) or set(high) != {
        "primary", "fallback", "accepted_primary_unavailable_evidence", "independent_validator_source",
        "default", "requires_explicit_task_selection"
    }:
        _fail("high-volume slot shape is invalid")
    _validate_route(high["primary"], catalog, "high-volume.primary")
    _validate_route(high["fallback"], catalog, "high-volume.fallback")
    if (
        high["accepted_primary_unavailable_evidence"] != list(EVIDENCE)
        or high["independent_validator_source"] != "openai-complexity-map"
        or high["default"] is not False
        or high["requires_explicit_task_selection"] is not True
    ):
        _fail("high-volume fallback contract drifted")
    return json.loads(json.dumps(profile))


def validate_profile_versioned(profile: Any, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch profile validation by its explicit schema version."""

    if isinstance(profile, dict):
        reject_retired_profile_id(profile.get("profile_id"))
    if not isinstance(profile, dict):
        _fail("profile must be an object")
    if profile.get("schema_version") == 1:
        return validate_profile(profile, catalog)
    if profile.get("schema_version") == 2:
        return validate_profile_v2(profile, catalog)
    _fail("profile schema_version is unsupported")


def _safe_relative(path: Any) -> str:
    if not isinstance(path, str) or not SAFE_RELATIVE.fullmatch(path):
        _fail("project profile directory must be a safe relative path")
    if any(part in {".", ".."} for part in re.split(r"[/\\]", path)):
        _fail("project profile directory contains dot segments")
    return path


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _profile_candidates(profile_id: str, project_root: Path, dirs: list[str]) -> list[Path]:
    reject_retired_profile_id(profile_id)
    candidates: list[Path] = []
    for raw_dir in dirs:
        directory = project_root / _safe_relative(raw_dir)
        if directory.exists() and not _inside(directory, project_root):
            _fail("project profile directory resolves outside project root")
        if not directory.exists():
            continue
        if not directory.is_dir():
            _fail("project profile directory is not a directory")
        exact = directory / f"{profile_id}.json"
        if exact.is_file():
            candidates.append(exact)
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name.casefold()):
            if path not in candidates:
                try:
                    payload = _load_json(path)
                except ValueError:
                    continue
                if isinstance(payload, dict) and payload.get("profile_id") == profile_id:
                    candidates.append(path)
    return sorted(candidates, key=lambda item: str(item).casefold())


def load_profile(
    profile_id: str = V2_PROFILE_ID,
    *,
    project_root: Any = None,
    project_profile_dirs: list[str] | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reject_retired_profile_id(profile_id)
    _string(profile_id, "profile_id")
    catalog = validate_catalog(catalog if catalog is not None else load_catalog())
    bundled_path = PROFILE_DIR / f"{profile_id}.json"
    project = Path(project_root) if project_root is not None else Path.cwd()
    candidates = _profile_candidates(profile_id, project, project_profile_dirs or [])
    if profile_id in PROFILE_IDS:
        if not bundled_path.is_file():
            _fail("bundled profile is missing")
        bundled_bytes = bundled_path.read_bytes()
        for candidate in candidates:
            if candidate.read_bytes() != bundled_bytes:
                _fail("project profile collides with immutable bundled profile")
        normalized = validate_profile_versioned(_load_json(bundled_path), catalog)
        if normalized["profile_id"] != profile_id:
            _fail("profile_id does not match bundled profile path")
        if normalized["schema_version"] != 2:
            _fail("bundled profile schema version drifted")
        return normalized
    if len(candidates) != 1:
        _fail(f"profile not found or ambiguous: {profile_id}")
    normalized = validate_profile_versioned(_load_json(candidates[0]), catalog)
    if normalized["profile_id"] != profile_id:
        _fail("profile_id does not match requested profile")
    return normalized


def _default_config(profile_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "router_api_version": "route/v1",
        "config_id": "bundled-selection",
        "active_profile": profile_id,
        "project_profile_dirs": [],
        "updated_reason": "Explicit route request selects the bundled profile.",
    }


def _default_config_v2(profile_id: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "router_api_version": "route/v2",
        "config_id": "bundled-selection",
        "active_profile": profile_id,
        "project_profile_dirs": [],
        "updated_reason": "Explicit route request selects the bundled profile.",
    }


def load_config(*, explicit_path: Any = None, injected_config: Any = None, cwd: Any = None, profile_id: str | None = None, router_api_version: str | None = None) -> tuple[dict[str, Any], str, Path | None]:
    if profile_id is not None:
        reject_retired_profile_id(profile_id)
    base = Path(cwd) if cwd is not None else Path.cwd()
    injected_path = injected_config if isinstance(injected_config, (str, Path)) and Path(injected_config).exists() else None
    selected = resolve_config_path(explicit_path, injected_path, base)
    if explicit_path is not None:
        payload = _load_json(Path(selected))
    elif injected_path is not None:
        payload = _load_json(Path(selected))
    elif injected_config is not None:
        payload = _json_value(injected_config, "injected_config")
        selected = None
    elif selected is not None:
        payload = _load_json(selected)
    else:
        if profile_id is None:
            _fail(f"no config found; expected {CONVENTIONAL_CONFIG}")
        if router_api_version == "route/v2":
            payload = _default_config_v2(profile_id)
        elif router_api_version == "route/v1":
            payload = _default_config(profile_id)
        elif router_api_version is None and profile_id == V2_PROFILE_ID:
            payload = _default_config_v2(profile_id)
        elif router_api_version is None:
            payload = _default_config(profile_id)
        else:
            _fail("router_api_version is unsupported")
    if router_api_version is None:
        normalized = validate_config_versioned(payload)
    else:
        normalized = validate_config_for_version(payload, router_api_version)
    return normalized, config_digest(normalized), selected


def validate_route_request(request: Any) -> dict[str, Any]:
    required = {
        "router_api_version", "request_id", "route_slot", "writer_route_slot", "profile_id", "explicit_profile_selection",
        "explicit_high_volume_selection", "availability", "primary_failure_evidence", "writer_identity", "candidate_id",
    }
    if not isinstance(request, dict) or set(request) != required:
        _fail("RouteRequest keys are invalid")
    if request["router_api_version"] != "route/v1":
        _fail("router_api_version must be route/v1")
    _string(request["request_id"], "request_id")
    if request["route_slot"] not in ROUTE_SLOTS:
        _fail("route_slot is invalid")
    writer_route_slot = request["writer_route_slot"]
    if writer_route_slot is not None and writer_route_slot not in WRITER_ROUTE_SLOTS:
        _fail("writer_route_slot is invalid")
    if request["route_slot"] == "validator.independent" and writer_route_slot is None:
        _fail("validator.independent requires writer_route_slot")
    if request["route_slot"] != "validator.independent" and writer_route_slot is not None:
        _fail("writer_route_slot is only allowed for validator.independent")
    _string(request["profile_id"], "profile_id")
    reject_retired_profile_id(request["profile_id"])
    if type(request["explicit_profile_selection"]) is not bool or not request["explicit_profile_selection"]:
        _fail("profile selection must be explicit")
    if type(request["explicit_high_volume_selection"]) is not bool:
        _fail("explicit_high_volume_selection must be boolean")
    if request["route_slot"] == "writer.high-volume-deterministic" and not request["explicit_high_volume_selection"]:
        _fail("high-volume selection must be explicit")
    availability = request["availability"]
    if not isinstance(availability, dict):
        _fail("availability must be an object")
    for key, value in availability.items():
        _string(key, "availability key")
        if value not in {"available", "unavailable", "unknown"}:
            _fail("availability value is invalid")
    evidence = request["primary_failure_evidence"]
    if not isinstance(evidence, list) or len(set(evidence)) != len(evidence):
        _fail("primary_failure_evidence must be a unique array")
    for item in evidence:
        _string(item, "primary_failure_evidence item")
    identity = request["writer_identity"]
    if identity is not None:
        if not isinstance(identity, dict) or set(identity) != {"provider", "runtime_provider", "model"}:
            _fail("writer_identity shape is invalid")
        _string(identity["provider"], "writer_identity.provider")
        _string(identity["runtime_provider"], "writer_identity.runtime_provider")
        _string(identity["model"], "writer_identity.model")
    if request["candidate_id"] is not None:
        _string(request["candidate_id"], "candidate_id")
    return json.loads(json.dumps(request))


def validate_route_request_v2(request: Any) -> dict[str, Any]:
    """Validate and return a normalized route/v2 request."""

    required = {
        "router_api_version", "request_id", "route_slot", "writer_route_slot", "profile_id", "explicit_profile_selection",
        "explicit_high_volume_selection", "availability", "route_failure_evidence", "risk_level", "writer_identity",
        "candidate_id",
    }
    if not isinstance(request, dict) or set(request) != required:
        _fail("RouteRequest v2 keys are invalid")
    if request["router_api_version"] != "route/v2":
        _fail("router_api_version must be route/v2")
    _string(request["request_id"], "request_id")
    if request["route_slot"] not in ROUTE_SLOTS_V2:
        _fail("route_slot is invalid")
    writer_route_slot = request["writer_route_slot"]
    if writer_route_slot is not None and writer_route_slot not in WRITER_ROUTE_SLOTS:
        _fail("writer_route_slot is invalid")
    assurance_request = request["route_slot"] == "validator.assurance"
    if assurance_request and writer_route_slot is None:
        _fail("validator.assurance requires writer_route_slot")
    if not assurance_request and writer_route_slot is not None:
        _fail("writer_route_slot is only allowed for validator.assurance")
    _string(request["profile_id"], "profile_id")
    reject_retired_profile_id(request["profile_id"])
    if type(request["explicit_profile_selection"]) is not bool or not request["explicit_profile_selection"]:
        _fail("profile selection must be explicit")
    if type(request["explicit_high_volume_selection"]) is not bool:
        _fail("explicit_high_volume_selection must be boolean")
    if request["route_slot"] == "writer.high-volume-deterministic" and not request["explicit_high_volume_selection"]:
        _fail("high-volume selection must be explicit")

    availability = request["availability"]
    if not isinstance(availability, dict):
        _fail("availability must be an object")
    for key, value in availability.items():
        _string(key, "availability key")
        if value not in {"available", "unavailable", "unknown"}:
            _fail("availability value is invalid")

    route_failure_evidence = request["route_failure_evidence"]
    if not isinstance(route_failure_evidence, dict):
        _fail("route_failure_evidence must be an object")
    for key, evidence in route_failure_evidence.items():
        _string(key, "route_failure_evidence key")
        if V2_ROUTE_KEY.fullmatch(key) is None:
            _fail("route_failure_evidence key must be an exact logical route")
        if not isinstance(evidence, list):
            _fail("route_failure_evidence values must be arrays")
        seen: set[str] = set()
        for item in evidence:
            _string(item, "route_failure_evidence item")
            if item in seen:
                _fail("route_failure_evidence values must be unique arrays")
            seen.add(item)

    risk_level = request["risk_level"]
    if assurance_request:
        if risk_level not in {"R1", "R2", "R3"}:
            _fail("validator.assurance requires risk_level R1, R2, or R3")
    elif risk_level is not None:
        _fail("risk_level is only allowed for validator.assurance")

    identity = request["writer_identity"]
    if assurance_request:
        if not isinstance(identity, dict) or set(identity) != {"provider", "runtime_provider", "model"}:
            _fail("validator.assurance requires writer_identity")
    elif identity is not None:
        _fail("writer_identity is only allowed for validator.assurance")
    if identity is not None:
        _string(identity["provider"], "writer_identity.provider")
        _string(identity["runtime_provider"], "writer_identity.runtime_provider")
        _string(identity["model"], "writer_identity.model")

    candidate_id = request["candidate_id"]
    if assurance_request:
        if candidate_id is None:
            _fail("validator.assurance requires candidate_id")
    elif candidate_id is not None:
        _fail("candidate_id is only allowed for validator.assurance")
    if candidate_id is not None:
        _string(candidate_id, "candidate_id")
    return json.loads(json.dumps(request))


def _availability(availability: dict[str, str], route: dict[str, str]) -> str:
    keys = (
        f"{route['provider']}/{route['model']}",
        f"{route['provider']}:{route['model']}",
        route["model"],
    )
    for key in keys:
        if key in availability:
            return availability[key]
    return "unknown"


def _expand_route(route: dict[str, str], catalog: dict[str, Any]) -> dict[str, str]:
    runtime_provider = catalog["providers"][route["provider"]]["runtime_provider"]
    return {**route, "runtime_provider": runtime_provider}


def _same_writer_identity(selected: dict[str, str], writer: dict[str, str]) -> bool:
    return (
        (selected["provider"], selected["model"]) == (writer["provider"], writer["model"])
        or (selected["runtime_provider"], selected["model"])
        == (writer["runtime_provider"], writer["model"])
    )


def _decision(request: dict[str, Any], digest: str, *, status: str, selected: dict[str, str] | None, fallback: bool, evidence: list[str], source: str, limitations: list[str]) -> dict[str, Any]:
    return {
        "router_api_version": "route/v1",
        "request_id": request["request_id"],
        "profile_id": request["profile_id"],
        "route_slot": request["route_slot"],
        "decision_status": status,
        "enforcement_status": "not-executed",
        "selected_route": selected,
        "fallback_used": fallback,
        "fallback_evidence": list(evidence),
        "independent_validator_source": source,
        "config_digest": digest,
        "limitations": [LIMITATION, *limitations],
    }


def resolve_route(request: Any, *, cwd: Any = None, config_path: Any = None, injected_config: Any = None) -> dict[str, Any]:
    if isinstance(request, dict) and request.get("router_api_version") == "route/v2":
        return _resolve_route_v2(
            request,
            cwd=cwd,
            config_path=config_path,
            injected_config=injected_config,
        )
    request = validate_route_request(request)
    base = Path(cwd) if cwd is not None else Path.cwd()
    config, digest, _ = load_config(
        explicit_path=config_path,
        injected_config=injected_config,
        cwd=base,
        profile_id=request["profile_id"],
        router_api_version=request["router_api_version"],
    )
    if config["active_profile"] != request["profile_id"]:
        _fail("request profile_id does not match active_profile")
    catalog = load_catalog()
    profile = load_profile(
        request["profile_id"],
        project_root=base,
        project_profile_dirs=config["project_profile_dirs"],
        catalog=catalog,
    )
    if profile.get("schema_version") != 1:
        _fail("profile schema version does not match route/v1")
    slot = profile["slots"][request["route_slot"]]
    source = "not-applicable"
    primary = slot["primary"]
    reverse_validator_path = False
    if request["route_slot"] == "writer.high-volume-deterministic":
        source = slot["independent_validator_source"]
    if request["route_slot"] == "validator.independent":
        identity = request["writer_identity"]
        if identity is None:
            return _decision(request, digest, status="blocked", selected=None, fallback=False, evidence=[], source=source, limitations=["independent validator identity is required"])
        if identity["provider"] == "openai":
            source = "router-selected"
        else:
            reverse_validator_path = True
            primary = profile["slots"][request["writer_route_slot"]]["primary"]
            source = "openai-complexity-map"
    state = _availability(request["availability"], primary)
    if state == "available":
        selected = _expand_route(primary, catalog)
        if request["route_slot"] == "validator.independent" and _same_writer_identity(selected, request["writer_identity"]):
            return _decision(request, digest, status="blocked", selected=None, fallback=False, evidence=[], source=source, limitations=["independent validator cannot equal writer identity"])
        return _decision(request, digest, status="selected", selected=selected, fallback=False, evidence=[], source=source, limitations=[])
    if state == "unknown":
        limitation = "primary availability is unknown; no fallback is permitted"
        if reverse_validator_path:
            limitation = "writer route availability is unknown; validator fallback is forbidden"
        return _decision(request, digest, status="unknown", selected=None, fallback=False, evidence=[], source=source, limitations=[limitation])
    if reverse_validator_path:
        return _decision(request, digest, status="blocked", selected=None, fallback=False, evidence=request["primary_failure_evidence"], source=source, limitations=["writer route is unavailable; validator fallback is forbidden"])
    accepted = slot.get("accepted_primary_unavailable_evidence", [])
    evidence = request["primary_failure_evidence"]
    if not evidence or any(item not in accepted for item in evidence):
        return _decision(request, digest, status="blocked", selected=None, fallback=False, evidence=evidence, source=source, limitations=["primary unavailable evidence is absent or unaccepted"])
    fallback = slot.get("fallback")
    if fallback is None:
        return _decision(request, digest, status="blocked", selected=None, fallback=False, evidence=evidence, source=source, limitations=["no fallback is defined for this slot"])
    fallback_state = _availability(request["availability"], fallback)
    if fallback_state == "available":
        selected = _expand_route(fallback, catalog)
        if request["route_slot"] == "validator.independent" and _same_writer_identity(selected, request["writer_identity"]):
            return _decision(request, digest, status="blocked", selected=None, fallback=False, evidence=evidence, source=source, limitations=["independent validator cannot equal writer identity"])
        return _decision(request, digest, status="selected", selected=selected, fallback=True, evidence=evidence, source=source, limitations=[])
    return _decision(request, digest, status="unknown", selected=None, fallback=False, evidence=evidence, source=source, limitations=["fallback availability is not confirmed"])


def _logical_route_key(route: dict[str, str]) -> str:
    return f"{route['provider']}/{route['model']}"


def _availability_v2(availability: dict[str, str], route: dict[str, str]) -> str:
    """Read only the exact logical route key supplied by the caller."""

    return availability.get(_logical_route_key(route), "unknown")


def _route_failure_evidence_v2(
    request: dict[str, Any], route: dict[str, str], accepted: list[str]
) -> tuple[list[str], bool]:
    key = _logical_route_key(route)
    evidence = request["route_failure_evidence"].get(key)
    if not evidence or any(item not in accepted for item in evidence):
        return list(evidence or []), False
    return list(evidence), True


def _decision_v2(
    request: dict[str, Any],
    digest: str,
    *,
    status: str,
    selected: list[dict[str, str]],
    validation_mode: str,
    escalation_used: bool,
    evidence: dict[str, list[str]],
    limitations: list[str],
) -> dict[str, Any]:
    identity = request["writer_identity"]
    same_model = bool(
        identity
        and any(_same_writer_identity(route, identity) for route in selected)
    )
    return {
        "router_api_version": "route/v2",
        "request_id": request["request_id"],
        "profile_id": request["profile_id"],
        "route_slot": request["route_slot"],
        "decision_status": status,
        "enforcement_status": "not-executed",
        "selected_routes": [dict(route) for route in selected],
        "validation_mode": validation_mode,
        "risk_level": request["risk_level"],
        "escalation_used": escalation_used,
        "escalation_evidence": {key: list(value) for key, value in evidence.items()},
        "same_model_as_writer": same_model,
        "validator_source": (
            "router-selected"
            if request["route_slot"] == "validator.assurance"
            else "not-applicable"
        ),
        "config_digest": digest,
        "limitations": [LIMITATION, *limitations],
    }


def _resolve_assurance_single(
    request: dict[str, Any],
    digest: str,
    catalog: dict[str, Any],
    routes: list[dict[str, str]],
    accepted: list[str],
) -> dict[str, Any]:
    evidence_by_route: dict[str, list[str]] = {}
    for index, route in enumerate(routes):
        key = _logical_route_key(route)
        state = _availability_v2(request["availability"], route)
        if state == "available":
            return _decision_v2(
                request,
                digest,
                status="selected",
                selected=[_expand_route(route, catalog)],
                validation_mode="single",
                escalation_used=bool(evidence_by_route),
                evidence=evidence_by_route,
                limitations=[],
            )
        if state == "unknown":
            return _decision_v2(
                request,
                digest,
                status="unknown",
                selected=[],
                validation_mode="single",
                escalation_used=bool(evidence_by_route),
                evidence=evidence_by_route,
                limitations=[
                    f"availability is unknown for {key}; no route may be selected without exact availability"
                ],
            )

        route_evidence, accepted_evidence = _route_failure_evidence_v2(
            request, route, accepted
        )
        evidence_by_route[key] = route_evidence
        if not accepted_evidence:
            return _decision_v2(
                request,
                digest,
                status="blocked",
                selected=[],
                validation_mode="single",
                escalation_used=bool(evidence_by_route) and index > 0,
                evidence=evidence_by_route,
                limitations=[
                    f"unavailable route {key} has missing or unaccepted route-bound failure evidence"
                ],
            )
        if index == len(routes) - 1:
            return _decision_v2(
                request,
                digest,
                status="blocked",
                selected=[],
                validation_mode="single",
                escalation_used=bool(evidence_by_route),
                evidence=evidence_by_route,
                limitations=[
                    "Owner boundary: assurance route chain is exhausted; Owner action is required."
                ],
            )

    raise AssertionError("assurance route chain must not be empty")


def _resolve_assurance_dual(
    request: dict[str, Any],
    digest: str,
    catalog: dict[str, Any],
    routes: list[dict[str, str]],
    accepted: list[str],
) -> dict[str, Any]:
    evidence_by_route: dict[str, list[str]] = {}
    unknown_seen = False
    unavailable_seen = False
    invalid_unavailable = False
    for route in routes:
        key = _logical_route_key(route)
        state = _availability_v2(request["availability"], route)
        if state == "unknown":
            unknown_seen = True
        elif state == "unavailable":
            unavailable_seen = True
            route_evidence, accepted_evidence = _route_failure_evidence_v2(
                request, route, accepted
            )
            evidence_by_route[key] = route_evidence
            if not accepted_evidence:
                invalid_unavailable = True

    if invalid_unavailable:
        return _decision_v2(
            request,
            digest,
            status="blocked",
            selected=[],
            validation_mode="dual",
            escalation_used=False,
            evidence=evidence_by_route,
            limitations=[
                OWNER_R3_LIMITATION,
                "one or more unavailable required routes has missing or unaccepted route-bound failure evidence",
            ],
        )
    if unknown_seen:
        return _decision_v2(
            request,
            digest,
            status="unknown",
            selected=[],
            validation_mode="dual",
            escalation_used=False,
            evidence=evidence_by_route,
            limitations=[OWNER_R3_LIMITATION, "one or more required routes has unknown availability"],
        )
    if unavailable_seen:
        return _decision_v2(
            request,
            digest,
            status="blocked",
            selected=[],
            validation_mode="dual",
            escalation_used=False,
            evidence=evidence_by_route,
            limitations=[
                OWNER_R3_LIMITATION,
                "one or more required routes is unavailable even with accepted failure evidence",
            ],
        )
    return _decision_v2(
        request,
        digest,
        status="selected",
        selected=[_expand_route(route, catalog) for route in routes],
        validation_mode="dual",
        escalation_used=False,
        evidence={},
        limitations=[],
    )


def _resolve_v2_common_slot(
    request: dict[str, Any],
    digest: str,
    catalog: dict[str, Any],
    slot: dict[str, Any],
) -> dict[str, Any]:
    primary = slot["primary"]
    primary_key = _logical_route_key(primary)
    state = _availability_v2(request["availability"], primary)
    if state == "available":
        return _decision_v2(
            request,
            digest,
            status="selected",
            selected=[_expand_route(primary, catalog)],
            validation_mode="not-applicable",
            escalation_used=False,
            evidence={},
            limitations=[],
        )
    if state == "unknown":
        return _decision_v2(
            request,
            digest,
            status="unknown",
            selected=[],
            validation_mode="not-applicable",
            escalation_used=False,
            evidence={},
            limitations=[f"availability is unknown for {primary_key}"],
        )

    accepted = slot.get("accepted_primary_unavailable_evidence", [])
    primary_evidence, accepted_evidence = _route_failure_evidence_v2(
        request, primary, accepted
    )
    evidence = {primary_key: primary_evidence}
    fallback = slot.get("fallback")
    if not accepted_evidence:
        return _decision_v2(
            request,
            digest,
            status="blocked",
            selected=[],
            validation_mode="not-applicable",
            escalation_used=False,
            evidence=evidence,
            limitations=[
                f"unavailable route {primary_key} has missing or unaccepted route-bound failure evidence"
            ],
        )
    if fallback is None:
        return _decision_v2(
            request,
            digest,
            status="blocked",
            selected=[],
            validation_mode="not-applicable",
            escalation_used=False,
            evidence=evidence,
            limitations=["no fallback is defined for this slot"],
        )
    fallback_key = _logical_route_key(fallback)
    fallback_state = _availability_v2(request["availability"], fallback)
    if fallback_state == "available":
        return _decision_v2(
            request,
            digest,
            status="selected",
            selected=[_expand_route(fallback, catalog)],
            validation_mode="not-applicable",
            escalation_used=True,
            evidence=evidence,
            limitations=[],
        )
    if fallback_state == "unknown":
        return _decision_v2(
            request,
            digest,
            status="unknown",
            selected=[],
            validation_mode="not-applicable",
            escalation_used=True,
            evidence=evidence,
            limitations=[f"availability is unknown for fallback route {fallback_key}"],
        )
    return _decision_v2(
        request,
        digest,
        status="blocked",
        selected=[],
        validation_mode="not-applicable",
        escalation_used=True,
        evidence=evidence,
        limitations=[f"fallback route {fallback_key} is unavailable"],
    )


def _resolve_route_v2(
    request: Any,
    *,
    cwd: Any = None,
    config_path: Any = None,
    injected_config: Any = None,
) -> dict[str, Any]:
    request = validate_route_request_v2(request)
    base = Path(cwd) if cwd is not None else Path.cwd()
    config, digest, _ = load_config(
        explicit_path=config_path,
        injected_config=injected_config,
        cwd=base,
        profile_id=request["profile_id"],
        router_api_version="route/v2",
    )
    if config["active_profile"] != request["profile_id"]:
        _fail("request profile_id does not match active_profile")
    catalog = load_catalog()
    profile = load_profile(
        request["profile_id"],
        project_root=base,
        project_profile_dirs=config["project_profile_dirs"],
        catalog=catalog,
    )
    if profile.get("schema_version") != 2:
        _fail("profile schema version does not match route/v2")

    if request["route_slot"] == "validator.assurance":
        assurance = profile["slots"]["validator.assurance"]
        routes = assurance["routes_by_risk"][request["risk_level"]]
        accepted = assurance["accepted_route_failure_evidence"]
        if request["risk_level"] == "R3":
            return _resolve_assurance_dual(request, digest, catalog, routes, accepted)
        return _resolve_assurance_single(request, digest, catalog, routes, accepted)
    return _resolve_v2_common_slot(
        request,
        digest,
        catalog,
        profile["slots"][request["route_slot"]],
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="resolve versioned route/v1 and route/v2 contracts without executing a host or provider"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("list-profiles",):
        command = commands.add_parser(name)
        command.add_argument("--project-root", default=".")
        command.add_argument("--config")
        command.add_argument("--injected-config")
    validate = commands.add_parser("validate-profile")
    validate.add_argument("--profile", required=True)
    validate.add_argument("--project-root", default=".")
    validate.add_argument("--config")
    resolve = commands.add_parser("resolve")
    resolve.add_argument("--request", required=True)
    resolve.add_argument("--config")
    resolve.add_argument("--injected-config")
    resolve.add_argument("--project-root", default=".")
    return parser


def _profiles(project_root: Path, config: dict[str, Any] | None) -> list[str]:
    found = set(PROFILE_IDS)
    dirs = config["project_profile_dirs"] if config else []
    for raw_dir in dirs:
        directory = project_root / _safe_relative(raw_dir)
        if directory.exists() and not _inside(directory, project_root):
            _fail("project profile directory resolves outside project root")
        if not directory.exists():
            continue
        if not directory.is_dir():
            _fail("project profile directory is not a directory")
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name.casefold()):
            try:
                item = _load_json(path)
            except ValueError:
                continue
            if isinstance(item, dict):
                profile_id = item.get("profile_id")
                reject_retired_profile_id(profile_id)
                if isinstance(profile_id, str):
                    found.add(profile_id)
    return sorted(found)


def _run(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    if args.command == "resolve":
        request = _json_value(args.request, "request")
        return resolve_route(request, cwd=project_root, config_path=args.config, injected_config=args.injected_config)
    config = None
    injected = getattr(args, "injected_config", None)
    if args.config or injected:
        config, _, _ = load_config(explicit_path=args.config, injected_config=injected, cwd=project_root, profile_id=args.profile if args.command == "validate-profile" else None)
    if args.command == "list-profiles":
        return {"profiles": _profiles(project_root, config)}
    if args.command == "validate-profile":
        profile = load_profile(
            args.profile,
            project_root=project_root,
            project_profile_dirs=config["project_profile_dirs"] if config else [],
        )
        if config is not None:
            expected_api = "route/v2" if profile["schema_version"] == 2 else "route/v1"
            if config["router_api_version"] != expected_api:
                _fail("profile and config versions do not match")
        return profile
    _fail(f"unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        print(json.dumps(_run(args), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
