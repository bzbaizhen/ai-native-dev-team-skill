"""Deterministic, local route/v1 resolution.

This module reads immutable package data and a validated project selection.  It
does not invoke a host, provider, process, network, or credential store.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from router_config import CONVENTIONAL_CONFIG, config_digest, resolve_config_path, validate_config


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
PROFILE_DIR = ASSET_DIR / "profiles"
CATALOG_PATH = ASSET_DIR / "provider-catalog.json"
PROFILE_ID = "openai-glm5.3-deepseek-fallback-2026-08-28"
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
    profile_id: str = PROFILE_ID,
    *,
    project_root: Any = None,
    project_profile_dirs: list[str] | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _string(profile_id, "profile_id")
    catalog = validate_catalog(catalog if catalog is not None else load_catalog())
    bundled_path = PROFILE_DIR / f"{PROFILE_ID}.json"
    project = Path(project_root) if project_root is not None else Path.cwd()
    candidates = _profile_candidates(profile_id, project, project_profile_dirs or [])
    if profile_id == PROFILE_ID:
        if not bundled_path.is_file():
            _fail("bundled profile is missing")
        bundled_bytes = bundled_path.read_bytes()
        for candidate in candidates:
            if candidate.read_bytes() != bundled_bytes:
                _fail("project profile collides with immutable bundled profile")
        return validate_profile(_load_json(bundled_path), catalog)
    if len(candidates) != 1:
        _fail(f"profile not found or ambiguous: {profile_id}")
    return validate_profile(_load_json(candidates[0]), catalog)


def _default_config(profile_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "router_api_version": "route/v1",
        "config_id": "bundled-selection",
        "active_profile": profile_id,
        "project_profile_dirs": [],
        "updated_reason": "Explicit route request selects the bundled profile.",
    }


def load_config(*, explicit_path: Any = None, injected_config: Any = None, cwd: Any = None, profile_id: str | None = None) -> tuple[dict[str, Any], str, Path | None]:
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
        payload = _default_config(profile_id)
    normalized = validate_config(payload)
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
    request = validate_route_request(request)
    base = Path(cwd) if cwd is not None else Path.cwd()
    config, digest, _ = load_config(explicit_path=config_path, injected_config=injected_config, cwd=base, profile_id=request["profile_id"])
    if config["active_profile"] != request["profile_id"]:
        _fail("request profile_id does not match active_profile")
    catalog = load_catalog()
    profile = load_profile(
        request["profile_id"],
        project_root=base,
        project_profile_dirs=config["project_profile_dirs"],
        catalog=catalog,
    )
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="resolve route/v1 without executing a host")
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
    found = {PROFILE_ID}
    dirs = config["project_profile_dirs"] if config else []
    for raw_dir in dirs:
        directory = project_root / _safe_relative(raw_dir)
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name.casefold()):
            try:
                item = _load_json(path)
            except ValueError:
                continue
            if isinstance(item, dict) and isinstance(item.get("profile_id"), str):
                found.add(item["profile_id"])
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
        return load_profile(args.profile, project_root=project_root, project_profile_dirs=config["project_profile_dirs"] if config else [])
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
