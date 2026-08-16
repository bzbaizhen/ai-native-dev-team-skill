#!/usr/bin/env python3
"""Offline verifier for the frozen Sigstore/Rekor/GitHub TSA P3 profile.

The adapter is deliberately local-only. It reads an exact inventory and the
retained bytes below one proof root, recomputes every size and digest, and
invokes only pinned local verification binaries with fail-closed proxy settings.
There is no HTTP, OIDC, Fulcio, Rekor lookup, TSA request, or retry path.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.0"
PROFILE_ID = "p3-sigstore-rekor-v1-sigstore-tsa-github-rfc3161-v1"
VERIFICATION_POLICY_ID = PROFILE_ID
SAFE_INTEGER_MAX = 9007199254740991
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:"
    r"[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
RFC3161_POLICY = "1.3.6.1.4.1.57264.2"
TIMESTAMPING_EKU = "1.3.6.1.5.5.7.3.8"
MAX_OUTPUT_BYTES = 16_384

FROZEN_TOOLS: dict[str, tuple[str, str, int, str]] = {
    "cosign": (
        "cosign",
        "v3.1.3",
        198_819_314,
        "9fe59be0eca1271873ce019061335eb1ac419b7059202e797828467ddabe33be",
    ),
    "sigstore-trusted-root": (
        "sigstore-trusted-root",
        "0.1",
        5_747,
        "844a1c6de3986c9f02070266b25e0d1a2fa99ceccc89f6b9ad90aae47b62a16e",
    ),
    "timestamp-cli": (
        "timestamp-cli",
        "v2.1.3",
        22_052_352,
        "ef4bbf7715445f0c26a0fcdcd89162afab7d8dea64e5a8091ea3a1f804f22bd2",
    ),
    "openssl": (
        "openssl",
        "3.5.6",
        1_005_028,
        "063e62dcc027fc5dbb1343de631f02a9291f8b1df0b4e37012e49a03d525aad4",
    ),
    "openssl-config": (
        "openssl-config",
        "3.5.6",
        12_411,
        "e4c87d84d4650c39a0163544a4107842b2ca42487cb61ba570b03b011275d6c3",
    ),
}
FROZEN_PROVIDER_ARTIFACTS: dict[str, tuple[int, str]] = {
    "github_leaf": (790, "06940aa850c0912e7cf8d893b6bf509c719060f94eaa0a8b5deb5d7194e4bc77"),
    "github_intermediate": (802, "ebfcb01e412d295adcfd67fe3e7546a1f01b033074da03abdde0de9e99c96eac"),
    "github_root": (741, "6d6734c76d4280033315c30f63d20b7a8d5d4dd6d77c7446b08c93443beec26e"),
}

ARTIFACT_FIELDS = (
    "cosign_bundle",
    "cosign_public_key",
    "sigstore_trusted_root",
    "raw_signature",
    "github_timestamp_token",
    "github_leaf",
    "github_intermediate",
    "github_root",
)
RESULT_BOOLEAN_FIELDS = (
    "artifact_binding_proven",
    "rekor_inclusion_proven",
    "sigstore_timestamp_proven",
    "github_timestamp_proven",
    "two_operator_policy_proven",
    "offline_verification_proven",
    "privacy_allowlist_passed",
    "proof_set_integral",
)
STABLE_CODES = {
    "provider_profile_unsupported",
    "provider_profile_drift",
    "proof_inventory_invalid",
    "proof_path_unsafe",
    "proof_file_missing",
    "proof_digest_mismatch",
    "envelope_digest_mismatch",
    "cosign_signature_invalid",
    "rekor_inclusion_invalid",
    "checkpoint_signature_invalid",
    "sigstore_timestamp_invalid",
    "raw_signature_mismatch",
    "github_timestamp_invalid",
    "github_chain_invalid",
    "github_policy_invalid",
    "github_nonce_present",
    "message_imprint_mismatch",
    "signed_time_order_invalid",
    "privacy_allowlist_violation",
    "offline_material_missing",
    "external_receipt_unverified",
    "recovery_unproven",
}


class AdapterError(ValueError):
    """Controlled validation error carrying a stable issue code."""

    def __init__(self, code: str, message: str = "invalid input") -> None:
        self.code = code if code in STABLE_CODES else "proof_inventory_invalid"
        super().__init__(message)


class InventoryError(AdapterError):
    pass


class ProofPathError(AdapterError):
    pass


class ToolTimeout(AdapterError):
    """A local verifier exceeded its bound; the child is not terminated here."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        super().__init__("offline_material_missing", f"local verifier timed out; pid={pid}")

def _issue(code: str, message: str = "verification failed") -> dict[str, str]:
    safe = re.sub(r"(?:[A-Za-z]:)?[/\\][^ ]+", "[redacted-path]", str(message))
    safe = safe.replace("\r", " ").replace("\n", " ")[:512]
    return {"code": code if code in STABLE_CODES else "proof_inventory_invalid", "message": safe}


def _parse_int(token: str) -> int:
    value = int(token, 10)
    if not -SAFE_INTEGER_MAX <= value <= SAFE_INTEGER_MAX:
        raise AdapterError("proof_inventory_invalid", "unsafe integer")
    return value


def _protobuf_uint(value: Any, code: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise AdapterError(code, "protobuf unsigned integer is invalid")
    parsed = int(value, 10)
    if parsed > SAFE_INTEGER_MAX:
        raise AdapterError(code, "protobuf unsigned integer is unsafe")
    return parsed


def _reject_float(token: str) -> None:
    raise AdapterError("proof_inventory_invalid", "floating-point values are forbidden")


def _reject_constant(token: str) -> None:
    raise AdapterError("proof_inventory_invalid", "non-standard number is forbidden")


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AdapterError("proof_inventory_invalid", "duplicate JSON key")
        result[key] = value
    return result


def parse_json_bytes(data: bytes) -> Any:
    """Parse strict UTF-8 JSON with duplicate-key and trailing-data rejection."""

    if not isinstance(data, bytes):
        raise TypeError("bytes required")
    if data.startswith(b"\xef\xbb\xbf"):
        raise AdapterError("proof_inventory_invalid", "UTF-8 BOM is forbidden")
    try:
        text = data.decode("utf-8", errors="strict")
        decoder = json.JSONDecoder(
            parse_int=_parse_int,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_pairs_without_duplicates,
        )
        view = text.lstrip(" \t\r\n")
        value, end = decoder.raw_decode(view)
    except AdapterError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AdapterError("proof_inventory_invalid", "invalid JSON") from exc
    if view[end:].strip(" \t\r\n"):
        raise AdapterError("proof_inventory_invalid", "trailing JSON data")
    return value


def _require_exact(value: Any, fields: Iterable[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InventoryError("proof_inventory_invalid", f"{location} must be an object")
    expected = set(fields)
    actual = set(value)
    if actual != expected:
        raise InventoryError("proof_inventory_invalid", f"{location} fields differ")
    return value


def _is_safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    try:
        pure = PurePosixPath(value)
    except (TypeError, ValueError):
        return False
    return bool(pure.parts) and not pure.is_absolute() and pure.as_posix() == value and all(
        part not in {"", ".", ".."} for part in pure.parts
    ) and all(re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in pure.parts)


def _validate_artifact(value: Any, location: str) -> dict[str, Any]:
    item = _require_exact(value, {"path", "bytes", "sha256"}, location)
    if not _is_safe_relative_path(item["path"]):
        raise ProofPathError("proof_path_unsafe", f"{location}.path is unsafe")
    if isinstance(item["bytes"], bool) or not isinstance(item["bytes"], int) or not 0 <= item["bytes"] <= SAFE_INTEGER_MAX:
        raise InventoryError("proof_inventory_invalid", f"{location}.bytes is invalid")
    if not isinstance(item["sha256"], str) or not SHA256_HEX.fullmatch(item["sha256"]):
        raise InventoryError("proof_inventory_invalid", f"{location}.sha256 is invalid")
    return item


def _normalise_tools(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise InventoryError("proof_inventory_invalid", "tool_inventory must be an array")
    items = value
    if len(items) != len(FROZEN_TOOLS):
        raise InventoryError("proof_inventory_invalid", "tool_inventory must contain five tools")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        item_obj = _require_exact(item, {"name", "version", "bytes", "sha256"}, f"tool_inventory[{index}]")
        name = item_obj["name"]
        if not isinstance(name, str) or name not in FROZEN_TOOLS or name in seen:
            raise InventoryError("provider_profile_drift", "tool identity is not frozen")
        expected_name, expected_version, expected_bytes, expected_sha = FROZEN_TOOLS[name]
        if (
            name != expected_name
            or item_obj["version"] != expected_version
            or item_obj["bytes"] != expected_bytes
            or item_obj["sha256"] != expected_sha
        ):
            raise InventoryError("provider_profile_drift", "tool identity is not frozen")
        if not isinstance(item_obj["version"], str) or not isinstance(item_obj["bytes"], int) or not isinstance(item_obj["sha256"], str):
            raise InventoryError("proof_inventory_invalid", "tool entry has invalid types")
        seen.add(name)
        result.append(dict(item_obj))
    return result


def validate_proof_inventory(value: Any, location: str = "proof_inventory") -> dict[str, Any]:
    """Validate one profile-specific inventory; never trust its digests."""

    obj = _require_exact(value, {
        "schema_version", "profile_id", "submitted_envelope_sha256",
        *ARTIFACT_FIELDS, "verification_policy_id", "tool_inventory", "acquired_at",
    }, location)
    if obj["schema_version"] != SCHEMA_VERSION:
        raise InventoryError("proof_inventory_invalid", "unsupported schema version")
    if obj["profile_id"] != PROFILE_ID:
        raise InventoryError("provider_profile_unsupported", "profile is not qualified")
    if obj["verification_policy_id"] != VERIFICATION_POLICY_ID:
        raise InventoryError("provider_profile_drift", "verification policy drift")
    if not isinstance(obj["submitted_envelope_sha256"], str) or not SHA256_HEX.fullmatch(obj["submitted_envelope_sha256"]):
        raise InventoryError("proof_inventory_invalid", "submitted digest is invalid")
    if not isinstance(obj["acquired_at"], str) or not TIMESTAMP.fullmatch(obj["acquired_at"]):
        raise InventoryError("proof_inventory_invalid", "acquired_at is operational metadata")
    paths: set[str] = set()
    normalised = dict(obj)
    for field in ARTIFACT_FIELDS:
        item = _validate_artifact(obj[field], f"{location}.{field}")
        if item["path"] in paths:
            raise ProofPathError("proof_path_unsafe", "duplicate retained path")
        paths.add(item["path"])
        if field in FROZEN_PROVIDER_ARTIFACTS:
            expected_bytes, expected_sha = FROZEN_PROVIDER_ARTIFACTS[field]
            if item["bytes"] != expected_bytes or item["sha256"] != expected_sha:
                raise InventoryError("provider_profile_drift", "provider certificate identity drifted")
        normalised[field] = dict(item)
    normalised["tool_inventory"] = _normalise_tools(obj["tool_inventory"])
    return normalised


def _load_json_input(value: Any, label: str) -> tuple[Any, Path | None]:
    if isinstance(value, Mapping):
        return dict(value), None
    if isinstance(value, (str, Path)):
        path = Path(value)
        try:
            raw = path.read_bytes()
            return parse_json_bytes(raw), path
        except AdapterError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise InventoryError("proof_inventory_invalid", f"{label} cannot be read") from exc
    if isinstance(value, bytes):
        return parse_json_bytes(value), None
    raise InventoryError("proof_inventory_invalid", f"{label} must be JSON or a path")


def _proof_root(root: Any, inventory_path: Path | None) -> Path:
    candidate = Path(root) if root is not None else (inventory_path.parent if inventory_path else None)
    if candidate is None:
        raise ProofPathError("proof_path_unsafe", "an explicit proof root is required")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ProofPathError("proof_path_unsafe", "proof root is unavailable") from exc
    if not resolved.is_dir():
        raise ProofPathError("proof_path_unsafe", "proof root is not a directory")
    return resolved


def _read_retained_files(inventory: Mapping[str, Any], root: Path) -> dict[str, bytes]:
    listed: dict[str, bytes] = {}
    for field in ARTIFACT_FIELDS:
        item = inventory[field]
        relative = item["path"]
        try:
            target = root.joinpath(*PurePosixPath(relative).parts)
            resolved = target.resolve(strict=True)
            if os.path.commonpath((str(root), str(resolved))) != str(root):
                raise ProofPathError("proof_path_unsafe", "retained file escapes proof root")
            current = root
            for part in PurePosixPath(relative).parts:
                current = current / part
                stat = current.lstat()
                if os.path.islink(current) or getattr(stat, "st_reparse_tag", 0):
                    raise ProofPathError("proof_path_unsafe", "symlinks and reparse points are forbidden")
            data = target.read_bytes()
        except ProofPathError:
            raise
        except FileNotFoundError as exc:
            raise AdapterError("proof_file_missing", "retained file is missing") from exc
        except (OSError, RuntimeError, ValueError) as exc:
            raise AdapterError("proof_file_missing", "retained file cannot be read") from exc
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise AdapterError("proof_digest_mismatch", "retained file bytes differ from inventory")
        listed[relative] = data

    # Inventory completeness is part of the proof-root boundary.  There must
    # be no unlisted regular file or alternate-data-stream-looking name.
    actual: set[str] = set()
    for current_root, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(directories)
        for name in sorted(files):
            path = Path(current_root) / name
            try:
                stat = path.lstat()
            except OSError as exc:
                raise AdapterError("proof_file_missing", "proof root changed during read") from exc
            if os.path.islink(path) or getattr(stat, "st_reparse_tag", 0) or ":" in name:
                raise ProofPathError("proof_path_unsafe", "proof root contains a link or alternate stream")
            rel = PurePosixPath(path.relative_to(root).as_posix()).as_posix()
            actual.add(rel)
    if actual != set(listed):
        raise ProofPathError("proof_path_unsafe", "proof root contains unlisted files")
    return listed


def _b64(value: Any) -> bytes:
    if not isinstance(value, str):
        raise ValueError("base64 string required")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64") from exc


def _hex_or_b64(value: Any) -> bytes:
    if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]+", value) and len(value) % 2 == 0:
        try:
            return bytes.fromhex(value)
        except ValueError:
            pass
    return _b64(value)


def _json_artifact(data: bytes, field: str) -> dict[str, Any]:
    value = parse_json_bytes(data)
    if not isinstance(value, dict):
        raise AdapterError("proof_inventory_invalid", f"{field} must contain an object")
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _envelope_bytes(value: Any) -> tuple[bytes, str]:
    if isinstance(value, (str, Path)):
        try:
            raw = Path(value).read_bytes()
        except (OSError, TypeError, ValueError) as exc:
            raise AdapterError("offline_material_missing", "public envelope is unavailable") from exc
        return _validated_envelope_bytes(raw)
    if isinstance(value, bytes):
        return _validated_envelope_bytes(value)
    if not isinstance(value, Mapping):
        raise AdapterError("offline_material_missing", "public envelope is unavailable")
    obj = dict(value)
    expected = {"schema_version", "receipt_type", "opaque_window_id", "sequence", "commitment_sha256", "previous_envelope_sha256"}
    if set(obj) != expected:
        raise AdapterError("privacy_allowlist_violation", "public envelope is outside the allowlist")
    if obj.get("schema_version") != "1.0" or obj.get("receipt_type") != "opaque_release_audit_commitment":
        raise AdapterError("privacy_allowlist_violation", "public envelope type is unsupported")
    raw = _canonical_json(obj)
    return raw, hashlib.sha256(raw).hexdigest()


def _validated_envelope_bytes(raw: bytes) -> tuple[bytes, str]:
    if re.fullmatch(rb"[0-9a-f]{64}", raw):
        return raw, hashlib.sha256(raw).hexdigest()
    try:
        parsed = parse_json_bytes(raw)
    except AdapterError as exc:
        raise AdapterError("privacy_allowlist_violation", "public envelope is outside the allowlist") from exc
    if not isinstance(parsed, dict):
        raise AdapterError("privacy_allowlist_violation", "public envelope is outside the allowlist")
    canonical = _canonical_json(parsed)
    if raw != canonical:
        raise AdapterError("proof_inventory_invalid", "public envelope is not canonical")
    expected = {"schema_version", "receipt_type", "opaque_window_id", "sequence", "commitment_sha256", "previous_envelope_sha256"}
    if set(parsed) != expected or parsed.get("schema_version") != "1.0" or parsed.get("receipt_type") != "opaque_release_audit_commitment":
        raise AdapterError("privacy_allowlist_violation", "public envelope is outside the allowlist")
    return raw, hashlib.sha256(raw).hexdigest()

def _result() -> dict[str, Any]:
    output: dict[str, Any] = {
        "profile_id": PROFILE_ID,
        "submitted_envelope_sha256": None,
        "sigstore_signed_time": None,
        "github_signed_time": None,
        "issues": [],
    }
    output.update({field: False for field in RESULT_BOOLEAN_FIELDS})
    return output


def _add_issue(result: dict[str, Any], code: str, message: str = "verification failed") -> None:
    issues = result.setdefault("issues", [])
    if not any(isinstance(item, dict) and item.get("code") == code for item in issues):
        issues.append(_issue(code, message))


def _extract_bundle_parts(bundle: Mapping[str, Any]) -> tuple[bytes, bytes, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    if bundle.get("mediaType") != "application/vnd.dev.sigstore.bundle.v0.3+json":
        raise AdapterError("provider_profile_drift", "unsupported Sigstore bundle media type")
    material = bundle.get("verificationMaterial")
    if not isinstance(material, dict):
        raise AdapterError("proof_inventory_invalid", "verification material is missing")
    message = _require_exact(
        bundle.get("messageSignature"),
        {"messageDigest", "signature"},
        "messageSignature",
    )
    digest_obj = _require_exact(
        message.get("messageDigest"),
        {"algorithm", "digest"},
        "messageSignature.messageDigest",
    )
    if digest_obj.get("algorithm") not in {"SHA2_256", "sha256", "SHA256"}:
        raise AdapterError("cosign_signature_invalid", "Cosign digest algorithm is unsupported")
    digest = _b64(digest_obj.get("digest"))
    signature = _b64(message.get("signature"))
    entries = material.get("tlogEntries")
    if not isinstance(entries, list):
        raise AdapterError("rekor_inclusion_invalid", "Rekor entries are missing")
    timestamp_data = _require_exact(
        material.get("timestampVerificationData"),
        {"rfc3161Timestamps"},
        "verificationMaterial.timestampVerificationData",
    )
    timestamps = timestamp_data.get("rfc3161Timestamps")
    if not isinstance(timestamps, list):
        raise AdapterError("sigstore_timestamp_invalid", "Sigstore timestamp is missing")
    return digest, signature, material, entries, timestamps


@dataclass(frozen=True)
class ToolPaths:
    cosign: Path
    timestamp_cli: Path
    openssl: Path
    openssl_config: Path

    @classmethod
    def from_value(cls, value: Any) -> "ToolPaths":
        if isinstance(value, cls):
            return value
        obj = _require_exact(value, {"cosign", "timestamp_cli", "openssl", "openssl_config"}, "tool_paths")
        return cls(*(Path(obj[name]) for name in ("cosign", "timestamp_cli", "openssl", "openssl_config")))


def _path_identity(path: Path, *, code: str = "provider_profile_drift") -> tuple[int, str]:
    try:
        resolved = path.resolve(strict=True)
        stat = resolved.lstat()
        if not resolved.is_file() or os.path.islink(resolved) or getattr(stat, "st_reparse_tag", 0):
            raise AdapterError(code, "tool path is not a regular file")
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except AdapterError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise AdapterError("offline_material_missing", "pinned local tool is unavailable") from exc
    return stat.st_size, digest.hexdigest()


def _verify_tool_paths(inventory: Mapping[str, Any], retained: Mapping[str, bytes], tools: ToolPaths) -> None:
    by_name = {entry["name"]: entry for entry in inventory["tool_inventory"]}
    actual_paths = {
        "cosign": tools.cosign,
        "timestamp-cli": tools.timestamp_cli,
        "openssl": tools.openssl,
        "openssl-config": tools.openssl_config,
    }
    for name, path in actual_paths.items():
        size, digest = _path_identity(path)
        entry = by_name[name]
        if size != entry["bytes"] or digest != entry["sha256"]:
            raise AdapterError("provider_profile_drift", "pinned local tool identity drifted")
    trusted = retained[inventory["sigstore_trusted_root"]["path"]]
    root_entry = by_name["sigstore-trusted-root"]
    if len(trusted) != root_entry["bytes"] or hashlib.sha256(trusted).hexdigest() != root_entry["sha256"]:
        raise AdapterError("provider_profile_drift", "trusted root identity drifted")


def _offline_environment(openssl_config: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "",
        "no_proxy": "",
        "OPENSSL_CONF": str(openssl_config),
    })
    return env


def _run_local(command: list[str], *, cwd: Path, env: Mapping[str, str], timeout: float = 20.0) -> subprocess.CompletedProcess[bytes]:
    # Regular files keep memory bounded even if a local verifier emits a large
    # stream. On timeout do not kill, terminate, or retry the child; ToolTimeout
    # carries its exact PID for Owner direction.
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=dict(env),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
            )
        except (OSError, ValueError) as exc:
            raise AdapterError("offline_material_missing", "pinned local verifier could not start") from exc
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ToolTimeout(process.pid) from exc
        stdout_size = stdout_file.tell()
        stderr_size = stderr_file.tell()
        if stdout_size > MAX_OUTPUT_BYTES or stderr_size > MAX_OUTPUT_BYTES:
            raise AdapterError("proof_inventory_invalid", "local verifier output exceeded the bound")
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(MAX_OUTPUT_BYTES + 1)
        stderr = stderr_file.read(MAX_OUTPUT_BYTES + 1)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _strict_bundle(bundle: Mapping[str, Any], envelope_digest: str, public_key: bytes, raw_signature: bytes) -> tuple[bytes, dict[str, Any]]:
    obj = _require_exact(bundle, {"mediaType", "verificationMaterial", "messageSignature"}, "cosign_bundle")
    digest, signature, material, entries, timestamps = _extract_bundle_parts(obj)
    if digest != bytes.fromhex(envelope_digest):
        raise AdapterError("envelope_digest_mismatch", "bundle digest does not bind the public envelope")
    if signature != raw_signature:
        raise AdapterError("raw_signature_mismatch", "bundle signature differs from retained raw signature")
    _require_exact(material, {"publicKey", "tlogEntries", "timestampVerificationData"}, "verificationMaterial")
    _require_exact(material["publicKey"], {"hint"}, "verificationMaterial.publicKey")
    if len(entries) != 1 or not isinstance(entries[0], dict):
        raise AdapterError("rekor_inclusion_invalid", "exactly one Rekor entry is required")
    entry = _require_exact(entries[0], {
        "logIndex", "logId", "kindVersion", "integratedTime", "inclusionPromise",
        "inclusionProof", "canonicalizedBody",
    }, "tlogEntries[0]")
    if entry["kindVersion"] != {"kind": "hashedrekord", "version": "0.0.1"}:
        raise AdapterError("rekor_inclusion_invalid", "Rekor entry kind/version drifted")
    log_id = _require_exact(entry["logId"], {"keyId"}, "tlogEntries[0].logId")
    if len(_b64(log_id["keyId"])) != 32:
        raise AdapterError("rekor_inclusion_invalid", "Rekor log identity is invalid")
    log_index = _protobuf_uint(entry["logIndex"], "rekor_inclusion_invalid")
    integrated_time = _protobuf_uint(entry["integratedTime"], "rekor_inclusion_invalid")
    if log_index < 0 or integrated_time <= 0:
        raise AdapterError("rekor_inclusion_invalid", "Rekor index/time is invalid")
    _require_exact(entry["inclusionPromise"], {"signedEntryTimestamp"}, "inclusionPromise")
    if not _b64(entry["inclusionPromise"]["signedEntryTimestamp"]):
        raise AdapterError("rekor_inclusion_invalid", "Rekor SET is empty")
    proof = _require_exact(entry["inclusionProof"], {"logIndex", "rootHash", "treeSize", "hashes", "checkpoint"}, "inclusionProof")
    local_index = _protobuf_uint(proof["logIndex"], "rekor_inclusion_invalid")
    tree_size = _protobuf_uint(proof["treeSize"], "rekor_inclusion_invalid")
    if local_index < 0 or tree_size <= local_index:
        raise AdapterError("rekor_inclusion_invalid", "tree-local Rekor proof is invalid")
    if len(_b64(proof["rootHash"])) != 32 or not isinstance(proof["hashes"], list) or not proof["hashes"]:
        raise AdapterError("rekor_inclusion_invalid", "Rekor proof hashes are invalid")
    if any(len(_b64(item)) != 32 for item in proof["hashes"]):
        raise AdapterError("rekor_inclusion_invalid", "Rekor proof hash width is invalid")
    checkpoint = _require_exact(proof["checkpoint"], {"envelope"}, "checkpoint")
    if not isinstance(checkpoint["envelope"], str) or "rekor.sigstore.dev" not in checkpoint["envelope"]:
        raise AdapterError("checkpoint_signature_invalid", "checkpoint envelope is unavailable")
    body = parse_json_bytes(_b64(entry["canonicalizedBody"]))
    body_obj = _require_exact(body, {"apiVersion", "kind", "spec"}, "rekor_body")
    if body_obj["apiVersion"] != "0.0.1" or body_obj["kind"] != "hashedrekord":
        raise AdapterError("rekor_inclusion_invalid", "Rekor body profile drifted")
    spec = _require_exact(body_obj["spec"], {"data", "signature"}, "rekor_body.spec")
    data = _require_exact(spec["data"], {"hash"}, "rekor_body.spec.data")
    hash_obj = _require_exact(data["hash"], {"algorithm", "value"}, "rekor_body.spec.data.hash")
    if hash_obj["algorithm"] != "sha256" or hash_obj["value"] != envelope_digest:
        raise AdapterError("envelope_digest_mismatch", "Rekor body digest differs")
    sig_obj = _require_exact(spec["signature"], {"content", "publicKey"}, "rekor_body.spec.signature")
    if _b64(sig_obj["content"]) != raw_signature:
        raise AdapterError("raw_signature_mismatch", "Rekor body signature differs")
    key_obj = _require_exact(sig_obj["publicKey"], {"content"}, "rekor_body.spec.signature.publicKey")
    if _b64(key_obj["content"]) != public_key:
        raise AdapterError("cosign_signature_invalid", "Rekor body public key differs")
    if len(timestamps) != 1 or not isinstance(timestamps[0], dict):
        raise AdapterError("sigstore_timestamp_invalid", "exactly one Sigstore timestamp is required")
    timestamp = _require_exact(timestamps[0], {"signedTimestamp"}, "rfc3161Timestamps[0]")
    return _b64(timestamp["signedTimestamp"]), entry


def _timestamp_text(
    openssl: Path,
    token: Path,
    *,
    cwd: Path,
    env: Mapping[str, str],
    error_code: str,
) -> tuple[datetime, str, str | None, str, str]:
    completed = _run_local([str(openssl), "ts", "-reply", "-in", str(token), "-text"], cwd=cwd, env=env)
    if completed.returncode != 0:
        raise AdapterError(error_code, "RFC3161 token cannot be decoded")
    try:
        text = completed.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AdapterError(error_code, "RFC3161 text is not UTF-8") from exc
    policy_match = re.search(r"^Policy OID:\s*(\S+)\s*$", text, re.MULTILINE)
    time_match = re.search(r"^Time stamp:\s*(.+?)\s*$", text, re.MULTILINE)
    nonce_match = re.search(r"^Nonce:\s*(.+?)\s*$", text, re.MULTILINE)
    hash_match = re.search(r"^Hash Algorithm:\s*(\S+)\s*$", text, re.MULTILINE)
    if not policy_match or not time_match or not hash_match:
        raise AdapterError(error_code, "RFC3161 semantic fields are missing")
    lines = text.splitlines()
    imprint_parts: list[str] = []
    capture = False
    for line in lines:
        if line.strip() == "Message data:":
            capture = True
            continue
        if capture:
            match = re.match(r"^\s*[0-9a-fA-F]{4}\s*-\s*([0-9a-fA-F -]+?)(?:\s{3,}.*)?$", line)
            if not match:
                break
            imprint_parts.append(re.sub(r"[^0-9a-fA-F]", "", match.group(1)))
    imprint = "".join(imprint_parts).lower()
    if len(imprint) != 64 or not SHA256_HEX.fullmatch(imprint):
        raise AdapterError(error_code, "RFC3161 message imprint is invalid")
    try:
        signed_time = datetime.strptime(time_match.group(1), "%b %d %H:%M:%S %Y GMT").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise AdapterError(error_code, "RFC3161 signed time is invalid") from exc
    nonce = nonce_match.group(1) if nonce_match else None
    return signed_time, policy_match.group(1), nonce, hash_match.group(1).lower(), imprint


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_signed_time_order(sigstore_time: datetime, github_time: datetime) -> None:
    if github_time < sigstore_time:
        raise AdapterError("signed_time_order_invalid", "GitHub signed time is earlier than Sigstore time")


def _privacy_structure_passes(bundle: Mapping[str, Any], rekor_entry: Mapping[str, Any]) -> bool:
    forbidden_keys = {
        "project", "project_id", "task", "task_id", "candidate", "candidate_sha",
        "outcome", "local_path", "private_path", "password", "salt", "private_key",
        "canonical_private_input", "window_id",
    }
    def visit(value: Any) -> bool:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).casefold() in forbidden_keys or not visit(child):
                    return False
        elif isinstance(value, list):
            return all(visit(child) for child in value)
        elif isinstance(value, str):
            if re.search(r"(?i)(?:[A-Z]:\\|/[U]sers/|/[h]ome/)", value):
                return False
        return True
    return visit(bundle) and visit(rekor_entry)


def verify_proof(
    inventory: Mapping[str, Any] | str | Path | bytes,
    public_envelope: Mapping[str, Any] | str | Path | bytes,
    *,
    proof_root: str | Path,
    tool_paths: Mapping[str, Any] | ToolPaths,
) -> dict[str, Any]:
    """Verify one retained proof set. All failures become stable computed issues."""

    result = _result()
    try:
        inventory_value, inventory_path = _load_json_input(inventory, "proof_inventory")
        validated = validate_proof_inventory(inventory_value)
        root = _proof_root(proof_root, inventory_path)
        retained = _read_retained_files(validated, root)
        tools = ToolPaths.from_value(tool_paths)
        _verify_tool_paths(validated, retained, tools)
        envelope_bytes, envelope_digest = _envelope_bytes(public_envelope)
        result["submitted_envelope_sha256"] = envelope_digest
        if envelope_digest != validated["submitted_envelope_sha256"]:
            raise AdapterError("envelope_digest_mismatch", "inventory digest differs from public envelope")
        bundle_bytes = retained[validated["cosign_bundle"]["path"]]
        public_key = retained[validated["cosign_public_key"]["path"]]
        raw_signature = retained[validated["raw_signature"]["path"]]
        bundle = _json_artifact(bundle_bytes, "cosign_bundle")
        sigstore_token, rekor_entry = _strict_bundle(bundle, envelope_digest, public_key, raw_signature)
        env = _offline_environment(tools.openssl_config)
        with tempfile.TemporaryDirectory(prefix="p3-offline-") as temporary:
            temp_root = Path(temporary)
            envelope_path = temp_root / "public-envelope.bin"
            sigstore_path = temp_root / "sigstore-tsa.tsr"
            envelope_path.write_bytes(envelope_bytes)
            sigstore_path.write_bytes(sigstore_token)
            cosign_command = [
                str(tools.cosign), "verify-blob",
                "--bundle", str(root / validated["cosign_bundle"]["path"]),
                "--trusted-root", str(root / validated["sigstore_trusted_root"]["path"]),
                "--key", str(root / validated["cosign_public_key"]["path"]),
                "--use-signed-timestamps", "--timeout", "15s", str(envelope_path),
            ]
            cosign = _run_local(cosign_command, cwd=root, env=env)
            if cosign.returncode != 0:
                raise AdapterError("cosign_signature_invalid", "offline Cosign verification failed")
            result["artifact_binding_proven"] = True
            result["rekor_inclusion_proven"] = True
            sigstore_time, _sig_policy, _sig_nonce, sig_hash, sigstore_imprint = _timestamp_text(
                tools.openssl, sigstore_path, cwd=root, env=env, error_code="sigstore_timestamp_invalid"
            )
            if sig_hash != "sha256":
                raise AdapterError("sigstore_timestamp_invalid", "Sigstore timestamp hash algorithm drifted")
            if sigstore_imprint != hashlib.sha256(raw_signature).hexdigest():
                raise AdapterError("message_imprint_mismatch", "Sigstore timestamp imprint differs")
            result["sigstore_timestamp_proven"] = True
            github_token = root / validated["github_timestamp_token"]["path"]
            leaf = root / validated["github_leaf"]["path"]
            intermediate = root / validated["github_intermediate"]["path"]
            github_root = root / validated["github_root"]["path"]
            github_time, github_policy, github_nonce, github_hash, github_imprint = _timestamp_text(
                tools.openssl, github_token, cwd=root, env=env, error_code="github_timestamp_invalid"
            )
            if github_hash != "sha256":
                raise AdapterError("message_imprint_mismatch", "GitHub timestamp hash algorithm drifted")
            if github_imprint != hashlib.sha256(raw_signature).hexdigest():
                raise AdapterError("message_imprint_mismatch", "GitHub timestamp imprint differs")
            if github_policy != RFC3161_POLICY:
                raise AdapterError("github_policy_invalid", "GitHub timestamp policy drifted")
            if github_nonce not in {None, "unspecified"}:
                raise AdapterError("github_nonce_present", "GitHub timestamp nonce is present")
            chain = _run_local(
                [str(tools.openssl), "verify", "-purpose", "timestampsign", "-CAfile", str(github_root),
                 "-untrusted", str(intermediate), str(leaf)], cwd=root, env=env
            )
            if chain.returncode != 0:
                raise AdapterError("github_chain_invalid", "GitHub TSA chain or EKU is invalid")
            leaf_text = _run_local(
                [str(tools.openssl), "x509", "-in", str(leaf), "-noout", "-subject", "-ext", "extendedKeyUsage"],
                cwd=root, env=env,
            )
            decoded_leaf = (leaf_text.stdout + leaf_text.stderr).decode("utf-8", errors="replace")
            if leaf_text.returncode != 0 or "TSA Timestamping" not in decoded_leaf or "Time Stamping" not in decoded_leaf:
                raise AdapterError("github_chain_invalid", "GitHub TSA CN or EKU is invalid")
            verified = _run_local(
                [str(tools.openssl), "ts", "-verify", "-in", str(github_token), "-data", str(root / validated["raw_signature"]["path"]),
                 "-CAfile", str(github_root), "-untrusted", str(intermediate)], cwd=root, env=env
            )
            if verified.returncode != 0:
                raise AdapterError("github_timestamp_invalid", "GitHub timestamp verification failed")
            result["github_timestamp_proven"] = True
            result["sigstore_signed_time"] = _iso_utc(sigstore_time)
            result["github_signed_time"] = _iso_utc(github_time)
            _require_signed_time_order(sigstore_time, github_time)
            result["two_operator_policy_proven"] = True
            result["offline_verification_proven"] = True
        if not _privacy_structure_passes(bundle, rekor_entry):
            raise AdapterError("privacy_allowlist_violation", "proof structure contains private metadata")
        result["privacy_allowlist_passed"] = True
        result["proof_set_integral"] = all(result[field] for field in RESULT_BOOLEAN_FIELDS if field != "proof_set_integral")
    except AdapterError as exc:
        _add_issue(result, exc.code, str(exc))
    except Exception:
        _add_issue(result, "proof_inventory_invalid", "controlled verifier failure")
    result["issues"].sort(key=lambda item: item["code"])
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--public-envelope", required=True)
    parser.add_argument("--proof-root", required=True)
    parser.add_argument("--cosign", required=True)
    parser.add_argument("--timestamp-cli", required=True)
    parser.add_argument("--openssl", required=True)
    parser.add_argument("--openssl-config", required=True)
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        result = verify_proof(
            args.inventory,
            args.public_envelope,
            proof_root=args.proof_root,
            tool_paths={
                "cosign": args.cosign,
                "timestamp_cli": args.timestamp_cli,
                "openssl": args.openssl,
                "openssl_config": args.openssl_config,
            },
        )
    except SystemExit:
        raise
    except Exception:
        result = _result()
        _add_issue(result, "proof_inventory_invalid", "controlled CLI failure")
    rendered = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if len(rendered.encode("utf-8")) > MAX_OUTPUT_BYTES:
        rendered = json.dumps({"profile_id": PROFILE_ID, "proof_set_integral": False, "issues": [_issue("proof_inventory_invalid", "bounded output failure")]}, separators=(",", ":"))
    if getattr(locals().get("args", None), "output", None):
        try:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8", newline="\n")
        except (OSError, TypeError, ValueError):
            result = _result()
            _add_issue(result, "proof_inventory_invalid", "controlled output failure")
            rendered = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            print(rendered)
            return 1
    else:
        print(rendered)
    return 0 if result.get("proof_set_integral") else 1


verify_p3_proof = verify_proof


if __name__ == "__main__":
    raise SystemExit(main())