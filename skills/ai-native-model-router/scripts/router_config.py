"""Safe, project-local route/v1 configuration helpers.

This module deliberately contains no host, credential, endpoint, transport, or
global-configuration logic.  It validates and moves the small project config
document only; a Host Adapter remains responsible for execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ROUTER_API_VERSION = "route/v1"
VERIFIED_PROFILE_ID = "openai-glm5.3-deepseek-fallback-2026-08-28"
CONVENTIONAL_CONFIG = Path(".ai-native") / "model-router.json"
CONFIG_KEYS = (
    "schema_version",
    "router_api_version",
    "config_id",
    "active_profile",
    "project_profile_dirs",
    "updated_reason",
)
FORBIDDEN_KEY_NAMES = frozenset(
    {
        "auth",
        "authentication",
        "command",
        "commands",
        "credential",
        "credentials",
        "endpoint",
        "endpoints",
        "override",
        "overrides",
        "script",
        "scripts",
        "secret",
        "secrets",
        "token",
        "tokens",
        "transport",
        "transports",
    }
)
SAFE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
DRIVE_OR_UNC = re.compile(r"^(?:[A-Za-z]:|\\\\|//)")

MIGRATION_REASON = (
    "Migrated from legacy embedded profile; explicit profile selection remains required."
)


def _fail(message: str) -> None:
    raise ValueError(message)


def _scan_forbidden_keys(value: Any, location: str = "$") -> None:
    if isinstance(value, dict):
        for key in sorted(value, key=lambda item: str(item).casefold()):
            if not isinstance(key, str):
                _fail(f"forbidden key: non-string key at {location}")
            if key.casefold() in FORBIDDEN_KEY_NAMES:
                _fail(f"forbidden key: {key}")
            _scan_forbidden_keys(value[key], f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_forbidden_keys(item, f"{location}[{index}]")


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{field} must be a non-empty string")
    if value != value.strip():
        _fail(f"{field} must not have leading or trailing whitespace")
    if CONTROL_CHARS.search(value):
        _fail(f"{field} contains control characters")
    return value


def _is_safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or CONTROL_CHARS.search(value):
        return False
    if DRIVE_OR_UNC.match(value) or value.startswith(("/", "\\")):
        return False
    segments = re.split(r"[/\\]", value)
    if any(segment in ("", ".", "..") for segment in segments):
        return False
    if any(":" in segment for segment in segments):
        return False
    return True


def validate_config(payload: Any) -> dict[str, Any]:
    """Validate and return a shallowly independent normalized v1 config."""

    _scan_forbidden_keys(payload)
    if not isinstance(payload, dict):
        _fail("config must be an object")
    if tuple(payload.keys()) != CONFIG_KEYS and set(payload.keys()) != set(CONFIG_KEYS):
        _fail("config keys must be exactly: " + ", ".join(CONFIG_KEYS))
    if type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version must be exactly 1")
    if payload["router_api_version"] != ROUTER_API_VERSION:
        _fail("router_api_version must be exactly route/v1")
    if not isinstance(payload["router_api_version"], str):
        _fail("router_api_version must be exactly route/v1")
    config_id = _require_string(payload["config_id"], "config_id")
    active_profile = _require_string(payload["active_profile"], "active_profile")
    updated_reason = _require_string(payload["updated_reason"], "updated_reason")
    del config_id, active_profile, updated_reason
    directories = payload["project_profile_dirs"]
    if not isinstance(directories, list):
        _fail("project_profile_dirs must be an array")
    normalized_dirs = []
    for index, directory in enumerate(directories):
        if not _is_safe_relative_path(directory):
            _fail(f"project_profile_dirs[{index}] must be a safe relative path")
        normalized_dirs.append(directory)
    return {
        "schema_version": 1,
        "router_api_version": ROUTER_API_VERSION,
        "config_id": payload["config_id"],
        "active_profile": payload["active_profile"],
        "project_profile_dirs": normalized_dirs,
        "updated_reason": payload["updated_reason"],
    }


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        validate_config(payload),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def config_digest(payload: dict[str, Any]) -> str:
    """Return the SHA-256 digest of canonical, validated JSON."""

    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _as_path(value: Any, field: str) -> Path:
    if isinstance(value, (str, Path)):
        if isinstance(value, str) and not value:
            _fail(f"{field} must be a path")
        return Path(value)
    try:
        return Path(os.fspath(value))
    except (TypeError, ValueError):
        _fail(f"{field} must be a path")
    raise AssertionError("unreachable")


def resolve_config_path(
    explicit_path: Any, injected_path: Any, cwd: Any
) -> Path | None:
    """Resolve explicit CLI, injected Hermes, then project conventional config."""

    if explicit_path is not None:
        return _as_path(explicit_path, "explicit_path")
    if injected_path is not None:
        return _as_path(injected_path, "injected_path")
    base = _as_path(cwd, "cwd")
    conventional = base / CONVENTIONAL_CONFIG
    return conventional if conventional.exists() else None


def migrate_legacy_profile(profile: Any) -> dict[str, Any]:
    """Select a profile from the legacy embedded-profile document."""

    if not isinstance(profile, dict):
        _fail("legacy profile must be an object")
    if "profile_id" not in profile:
        _fail("legacy profile requires profile_id")
    if "default_active" not in profile or "activation" not in profile:
        _fail("legacy profile activation is ambiguous")
    profile_id = _require_string(profile["profile_id"], "profile_id")
    if profile_id != VERIFIED_PROFILE_ID:
        _fail("legacy profile_id is not the current verified profile")
    if type(profile["default_active"]) is not bool or profile["default_active"]:
        _fail("legacy profile must not be active by default")
    if profile["activation"] != "explicit-owner-selection":
        _fail("legacy profile activation must be explicit-owner-selection")
    return validate_config(
        {
            "schema_version": 1,
            "router_api_version": ROUTER_API_VERSION,
            "config_id": f"migrated-{profile_id}",
            "active_profile": profile_id,
            "project_profile_dirs": [],
            "updated_reason": MIGRATION_REASON,
        }
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SAFE_SHA256.fullmatch(value):
        _fail(f"{field} must be 64 lowercase hexadecimal characters")
    return value


def _fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_bytes(path: Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _config_bytes(payload: dict[str, Any]) -> bytes:
    normalized = validate_config(payload)
    return (json.dumps(normalized, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write_config(
    path: Any,
    payload: dict[str, Any],
    expected_preimage_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate, optionally back up, and atomically replace a project config."""

    normalized = validate_config(payload)
    target = _as_path(path, "config path")
    if not target.parent.exists() or not target.parent.is_dir():
        _fail("config parent directory must already exist")
    if target.exists() and not target.is_file():
        _fail("config path must be a regular file")
    if expected_preimage_sha256 is not None:
        expected = _require_sha256(expected_preimage_sha256, "expected_preimage_sha256")
    else:
        expected = None
    preimage_hash = _sha256_file(target) if target.exists() else None
    if expected is not None and preimage_hash != expected:
        _fail("preimage sha256 mismatch")

    backup_path: Path | None = None
    backup_hash: str | None = None
    if expected is not None and target.exists():
        backup_data = target.read_bytes()
        backup_hash = hashlib.sha256(backup_data).hexdigest()
        backup_path = target.parent / f".{target.name}.backup-{backup_hash}"
        if backup_path.exists():
            if not backup_path.is_file() or _sha256_file(backup_path) != backup_hash:
                _fail("preimage backup path collision")
        else:
            _replace_bytes(backup_path, backup_data)

    _replace_bytes(target, _config_bytes(normalized))
    readback = json.loads(target.read_text(encoding="utf-8"))
    readback_normalized = validate_config(readback)
    if config_digest(readback_normalized) != config_digest(normalized):
        _fail("config readback digest mismatch")
    current_hash = _sha256_file(target)
    return {
        "path": str(target),
        "config_digest": config_digest(normalized),
        "preimage_sha256": preimage_hash,
        "backup_path": str(backup_path) if backup_path else None,
        "backup_sha256": backup_hash,
        "current_sha256": current_hash,
        "readback_digest": config_digest(readback_normalized),
    }


def rollback_config(
    path: Any,
    backup_path: Any,
    expected_current_sha256: str,
    expected_backup_sha256: str,
) -> dict[str, Any]:
    """Restore a validated same-directory backup only if current bytes match."""

    target = _as_path(path, "config path")
    backup = _as_path(backup_path, "backup path")
    if target.resolve().parent != backup.resolve().parent:
        _fail("backup must be in the config directory")
    if target.resolve() == backup.resolve():
        _fail("backup must differ from config path")
    expected_name = re.compile(
        rf"^\.{re.escape(target.name)}\.backup-([0-9a-f]{{64}})$"
    )
    match = expected_name.fullmatch(backup.name)
    if match is None:
        _fail("backup filename must bind to the target and a lowercase sha256")
    expected = _require_sha256(expected_current_sha256, "expected_current_sha256")
    expected_backup = _require_sha256(expected_backup_sha256, "expected_backup_sha256")
    if not target.exists() or not target.is_file():
        _fail("config path must be an existing regular file")
    if not backup.exists() or not backup.is_file():
        _fail("backup path must be an existing regular file")
    current_hash = _sha256_file(target)
    if current_hash != expected:
        _fail("current sha256 mismatch")
    data = backup.read_bytes()
    backup_hash = hashlib.sha256(data).hexdigest()
    if match.group(1) != backup_hash:
        _fail("backup filename sha256 does not match backup bytes")
    if expected_backup != backup_hash:
        _fail("backup sha256 does not match expected receipt")
    try:
        restored = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"backup is not valid UTF-8 JSON: {exc}")
    normalized = validate_config(restored)
    _replace_bytes(target, data)
    if target.read_bytes() != data:
        _fail("rollback readback bytes mismatch")
    return {
        "path": str(target),
        "backup_path": str(backup),
        "restored_sha256": hashlib.sha256(data).hexdigest(),
        "config_digest": config_digest(normalized),
    }


def _load_json(path: Any) -> Any:
    source = _as_path(path, "input path")
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail(f"cannot read JSON input: {exc}")


def _payload_argument(value: str) -> Any:
    candidate = Path(value)
    if candidate.exists():
        return _load_json(candidate)
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        _fail(f"payload must be a JSON file path or JSON object: {exc}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="validate and atomically manage route/v1 config")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "digest"):
        command = commands.add_parser(name)
        command.add_argument("--config", required=True)
    migrate = commands.add_parser("migrate-legacy")
    migrate.add_argument("--input", required=True)
    migrate.add_argument("--output", required=True)
    write = commands.add_parser("write")
    write.add_argument("--config", required=True)
    write.add_argument("--payload", required=True)
    write.add_argument("--expected-preimage-sha256")
    rollback = commands.add_parser("rollback")
    rollback.add_argument("--config", required=True)
    rollback.add_argument("--backup", required=True)
    rollback.add_argument("--expected-current-sha256", required=True)
    rollback.add_argument("--expected-backup-sha256", required=True)
    return parser


def _run(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.command == "validate":
        return validate_config(_load_json(arguments.config))
    if arguments.command == "digest":
        return {"config_digest": config_digest(_load_json(arguments.config))}
    if arguments.command == "migrate-legacy":
        migrated = migrate_legacy_profile(_load_json(arguments.input))
        output = _as_path(arguments.output, "output path")
        if output.exists():
            _fail("migration output already exists")
        atomic_write_config(output, migrated)
        return migrated
    if arguments.command == "write":
        return atomic_write_config(
            arguments.config,
            _payload_argument(arguments.payload),
            arguments.expected_preimage_sha256,
        )
    if arguments.command == "rollback":
        return rollback_config(
            arguments.config,
            arguments.backup,
            arguments.expected_current_sha256,
            arguments.expected_backup_sha256,
        )
    raise ValueError(f"unknown command: {arguments.command}")


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        print(json.dumps(_run(arguments), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
