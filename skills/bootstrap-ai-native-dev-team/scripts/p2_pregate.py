#!/usr/bin/env python3
"""Dependency-free, fail-closed local P2 hybrid pre-gate.

This module implements only the local contract selected by the P2 task.  It does
not contain a Rekor, TSA, OpenTimestamps, or other P3 verifier, and it never
invokes the existing V2 release gate.  A retained proof package is an inventory
of evidence until a separately approved adapter verifies it cryptographically.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


PROFILE = "ai-native-cj-1"
SCHEMA_VERSION = "1.0"
CONTROL_PROFILE = "p2-hybrid"
SAFE_INTEGER_MIN = -9007199254740991
SAFE_INTEGER_MAX = 9007199254740991
PRIVATE_BINDING_DOMAIN = b"ai-native-v2-private-binding\x00"
WINDOW_DOMAIN = b"ai-native-v2-window\x00"
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
SHA1_HEX = re.compile(r"^[0-9a-f]{40}$")
WINDOW_HEX = SHA256_HEX
KEY = re.compile(r"^[a-z][a-z0-9_]*$")
TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:"
    r"[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
RECORD_KINDS = {"window_freeze", "task_ready", "task_outcome", "window_closure"}
PRIVATE_FIELDS = {
    "schema_version",
    "window_id",
    "sequence",
    "record_kind",
    "private_anchor_commit",
    "private_object_sha256",
    "candidate_commit",
    "previous_private_binding_sha256",
    "created_at",
}
PUBLIC_FIELDS = {
    "schema_version",
    "receipt_type",
    "opaque_window_id",
    "sequence",
    "commitment_sha256",
    "previous_envelope_sha256",
}
PROOF_FIELDS = {
    "schema_version",
    "proof_type",
    "provider",
    "protocol_version",
    "submitted_digest_sha256",
    "retained_files",
    "verification_policy",
    "acquired_at",
}


class P2PregateError(ValueError):
    """Raised when an input cannot be accepted by the P2 contract."""


class CanonicalizationError(P2PregateError):
    """Raised for an invalid ai-native-cj-1 JSON value or byte stream."""


class SchemaValidationError(P2PregateError):
    """Raised for a valid JSON value that violates a P2 object schema."""


def _error(code: str, message: str) -> P2PregateError:
    return CanonicalizationError(f"{code}: {message}")


def _parse_int(token: str) -> int:
    if token == "-0":
        raise _error("negative_zero_forbidden", "negative zero is not an integer spelling")
    try:
        value = int(token, 10)
    except ValueError as exc:  # pragma: no cover - json normally rejects this first
        raise _error("invalid_integer", token) from exc
    if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
        raise _error("unsafe_integer", "integer is outside the safe range")
    return value


def _reject_float(token: str) -> None:
    raise _error("float_forbidden", f"floating-point token {token!r} is not allowed")


def _reject_constant(token: str) -> None:
    raise _error("nonstandard_number", f"non-standard number {token!r} is not allowed")


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error("duplicate_key", f"duplicate object key {key!r}")
        result[key] = value
    return result


def parse_json_bytes(data: bytes) -> Any:
    """Parse UTF-8 JSON with duplicate-key and number-token rejection.

    JSON whitespace around the root is accepted for authoring convenience.  The
    canonical-byte check below rejects that whitespace when bytes are used as an
    identity.  No BOM or non-whitespace trailing data is accepted.
    """

    if not isinstance(data, bytes):
        raise TypeError("parse_json_bytes requires bytes")
    if data.startswith(b"\xef\xbb\xbf"):
        raise _error("bom_forbidden", "UTF-8 BOM is not part of ai-native-cj-1")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _error("invalid_utf8", "input is not valid UTF-8") from exc
    decoder = json.JSONDecoder(
        parse_int=_parse_int,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
        object_pairs_hook=_pairs_without_duplicates,
    )
    try:
        value, end = decoder.raw_decode(text.lstrip(" \t\r\n"))
    except P2PregateError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error("invalid_json", str(exc)) from exc
    # raw_decode operates on the lstripped view.  Whitespace is harmless, but
    # any non-whitespace bytes after the root would create an ambiguous record.
    tail = text.lstrip(" \t\r\n")[end:]
    if tail.strip(" \t\r\n"):
        raise _error("trailing_data", "non-whitespace data follows the JSON value")
    return value


def _validate_cj_value(value: Any, location: str = "root") -> None:
    """Validate the recursive restricted data model before rendering."""

    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
            raise _error("unsafe_integer", f"{location} is outside the safe range")
        return
    if isinstance(value, float):
        raise _error("float_forbidden", f"{location} contains a float")
    if isinstance(value, str):
        if any(not 0x20 <= ord(char) <= 0x7E for char in value):
            raise _error("non_ascii_or_control", f"{location} is not printable ASCII")
        if "\\" in value or '"' in value:
            raise _error("string_escape_forbidden", f"{location} contains a forbidden escape character")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_cj_value(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not KEY.fullmatch(key):
                raise _error("invalid_key", f"{location} has an invalid object key")
            _validate_cj_value(item, f"{location}.{key}")
        return
    raise _error("unsupported_type", f"{location} has unsupported type {type(value).__name__}")


def validate_cj_value(value: Any) -> None:
    """Public recursive validator for the ai-native-cj-1 profile."""

    _validate_cj_value(value)


def canonicalize_value(value: Any) -> bytes:
    """Render a validated value as canonical ai-native-cj-1 UTF-8 bytes."""

    _validate_cj_value(value)
    if not isinstance(value, dict):
        raise _error("root_not_object", "the canonical root must be an object")
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # pragma: no cover - pre-validation catches it
        raise _error("render_failed", str(exc)) from exc
    return rendered.encode("utf-8")


def canonicalize_json_bytes(data: bytes) -> bytes:
    """Parse and canonicalize a JSON object without changing its values."""

    return canonicalize_value(parse_json_bytes(data))


def is_canonical_bytes(data: bytes) -> bool:
    """Return whether bytes are exactly their ai-native-cj-1 rendering."""

    try:
        return data == canonicalize_json_bytes(data)
    except (P2PregateError, TypeError):
        return False


def canonical_sha256(value_or_bytes: Any) -> str:
    """Hash the canonical rendering of an object, or verify/hash canonical bytes."""

    if isinstance(value_or_bytes, bytes):
        if not is_canonical_bytes(value_or_bytes):
            raise _error("noncanonical_bytes", "identity bytes are not canonical")
        data = value_or_bytes
    else:
        data = canonicalize_value(value_or_bytes)
    return hashlib.sha256(data).hexdigest()


def _require_exact_fields(value: Any, fields: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaValidationError(f"{location}: object required")
    actual = set(value)
    missing = fields - actual
    unknown = actual - fields
    if missing:
        raise SchemaValidationError(f"{location}: missing fields {sorted(missing)}")
    if unknown:
        raise SchemaValidationError(f"{location}: unknown fields {sorted(unknown)}")
    return value


def _require_string(value: Any, field: str, pattern: re.Pattern[str], location: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise SchemaValidationError(f"{location}.{field}: invalid string")
    return value


def _require_int(value: Any, field: str, location: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaValidationError(f"{location}.{field}: safe integer required")
    if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
        raise SchemaValidationError(f"{location}.{field}: unsafe integer")
    if positive and value < 1:
        raise SchemaValidationError(f"{location}.{field}: positive integer required")
    return value


def validate_private_binding(value: Any, location: str = "private_binding") -> dict[str, Any]:
    """Validate one strict private-binding object and return it unchanged."""

    _validate_cj_value(value, location)
    obj = _require_exact_fields(value, PRIVATE_FIELDS, location)
    if obj["schema_version"] != SCHEMA_VERSION:
        raise SchemaValidationError(f"{location}.schema_version: unsupported version")
    _require_string(obj["window_id"], "window_id", WINDOW_HEX, location)
    _require_int(obj["sequence"], "sequence", location, positive=True)
    _require_string(obj["record_kind"], "record_kind", re.compile(r"^(?:window_freeze|task_ready|task_outcome|window_closure)$"), location)
    anchor = obj["private_anchor_commit"]
    if anchor is not None:
        _require_string(anchor, "private_anchor_commit", SHA1_HEX, location)
    _require_string(obj["private_object_sha256"], "private_object_sha256", SHA256_HEX, location)
    _require_string(obj["candidate_commit"], "candidate_commit", SHA1_HEX, location)
    previous = obj["previous_private_binding_sha256"]
    if previous is not None:
        _require_string(previous, "previous_private_binding_sha256", SHA256_HEX, location)
    _require_string(obj["created_at"], "created_at", TIMESTAMP, location)
    return obj


def validate_opaque_envelope(value: Any, location: str = "opaque_envelope") -> dict[str, Any]:
    """Validate one public allowlisted opaque envelope."""

    _validate_cj_value(value, location)
    obj = _require_exact_fields(value, PUBLIC_FIELDS, location)
    if obj["schema_version"] != SCHEMA_VERSION:
        raise SchemaValidationError(f"{location}.schema_version: unsupported version")
    if obj["receipt_type"] != "opaque_release_audit_commitment":
        raise SchemaValidationError(f"{location}.receipt_type: unsupported receipt type")
    _require_string(obj["opaque_window_id"], "opaque_window_id", SHA256_HEX, location)
    _require_int(obj["sequence"], "sequence", location, positive=True)
    _require_string(obj["commitment_sha256"], "commitment_sha256", SHA256_HEX, location)
    previous = obj["previous_envelope_sha256"]
    if previous is not None:
        _require_string(previous, "previous_envelope_sha256", SHA256_HEX, location)
    return obj


_PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_TOKEN = re.compile(r"^[a-zA-Z0-9._-]{1,96}$")
_RELATIVE_PROOF_PATH = re.compile(r"^[a-zA-Z0-9._/-]+$")


def validate_external_proof_package(value: Any, location: str = "proof_package") -> dict[str, Any]:
    """Validate an inventory of retained proof bytes without qualifying it."""

    _validate_cj_value(value, location)
    obj = _require_exact_fields(value, PROOF_FIELDS, location)
    if obj["schema_version"] != SCHEMA_VERSION:
        raise SchemaValidationError(f"{location}.schema_version: unsupported version")
    if obj["proof_type"] != "external_time_transparency_proof":
        raise SchemaValidationError(f"{location}.proof_type: unsupported proof type")
    _require_string(obj["provider"], "provider", _PROVIDER, location)
    _require_string(obj["protocol_version"], "protocol_version", _TOKEN, location)
    _require_string(obj["submitted_digest_sha256"], "submitted_digest_sha256", SHA256_HEX, location)
    files = obj["retained_files"]
    if not isinstance(files, list) or not files:
        raise SchemaValidationError(f"{location}.retained_files: non-empty array required")
    seen: set[str] = set()
    for index, item in enumerate(files):
        item_location = f"{location}.retained_files[{index}]"
        _validate_cj_value(item, item_location)
        item_obj = _require_exact_fields(item, {"path", "sha256"}, item_location)
        path = _require_string(item_obj["path"], "path", _RELATIVE_PROOF_PATH, item_location)
        if path.startswith("/") or path.startswith(".") or "//" in path or "/../" in f"/{path}/" or path.endswith("/.."):
            raise SchemaValidationError(f"{item_location}.path: path must be normalized and relative")
        if path in seen:
            raise SchemaValidationError(f"{item_location}.path: duplicate retained path")
        seen.add(path)
        _require_string(item_obj["sha256"], "sha256", SHA256_HEX, item_location)
    policy_location = f"{location}.verification_policy"
    _validate_cj_value(obj["verification_policy"], policy_location)
    policy = _require_exact_fields(obj["verification_policy"], {"policy_id", "tool_version", "trust_root_sha256"}, policy_location)
    _require_string(policy["policy_id"], "policy_id", _TOKEN, policy_location)
    _require_string(policy["tool_version"], "tool_version", _TOKEN, policy_location)
    _require_string(policy["trust_root_sha256"], "trust_root_sha256", SHA256_HEX, policy_location)
    _require_string(obj["acquired_at"], "acquired_at", TIMESTAMP, location)
    return obj


def commitment_sha256(private_binding: Mapping[str, Any], window_salt: bytes) -> str:
    """Compute the salted, domain-separated private-binding commitment."""

    if not isinstance(window_salt, bytes) or len(window_salt) != 32:
        raise P2PregateError("salt_length_invalid: window salt must be exactly 32 bytes")
    binding = validate_private_binding(dict(private_binding))
    return hashlib.sha256(PRIVATE_BINDING_DOMAIN + window_salt + canonicalize_value(binding)).hexdigest()


def opaque_window_id(window_id: str, window_salt: bytes) -> str:
    """Derive the public opaque window identifier from private random material."""

    if not isinstance(window_id, str) or not WINDOW_HEX.fullmatch(window_id):
        raise P2PregateError("window_id_invalid: expected 64 lowercase hexadecimal characters")
    if not isinstance(window_salt, bytes) or len(window_salt) != 32:
        raise P2PregateError("salt_length_invalid: window salt must be exactly 32 bytes")
    return hashlib.sha256(WINDOW_DOMAIN + window_salt + bytes.fromhex(window_id)).hexdigest()


def envelope_sha256(envelope: Mapping[str, Any]) -> str:
    """Hash canonical public envelope bytes."""

    return canonical_sha256(validate_opaque_envelope(dict(envelope)))


def _salt_bytes(value: bytes | str | None) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        if len(value) != 32:
            raise P2PregateError("salt_length_invalid: window salt must be exactly 32 bytes")
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value):
        return bytes.fromhex(value)
    raise P2PregateError("salt_encoding_invalid: expected 32 bytes or 64 hexadecimal characters")


def _load_documents(source: Any, label: str) -> list[tuple[str, Any, bytes]]:
    """Load exactly the caller-supplied file or JSON files in a caller-supplied directory."""

    if source is None:
        return []
    if isinstance(source, Mapping):
        return [(label, dict(source), canonicalize_value(dict(source)))]
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.is_file():
            raw = path.read_bytes()
            return [(str(path), parse_json_bytes(raw), raw)]
        if path.is_dir():
            files = sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() == ".json")
            return [(str(item), parse_json_bytes(item.read_bytes()), item.read_bytes()) for item in files]
        raise P2PregateError(f"{label}_path_missing: supplied path does not exist")
    if isinstance(source, Iterable) and not isinstance(source, (str, bytes, bytearray)):
        result: list[tuple[str, Any, bytes]] = []
        for index, item in enumerate(source):
            if isinstance(item, Mapping):
                obj = dict(item)
                result.append((f"{label}[{index}]", obj, canonicalize_value(obj)))
            elif isinstance(item, (str, Path)):
                result.extend(_load_documents(item, f"{label}[{index}]"))
            else:
                raise P2PregateError(f"{label}[{index}]: expected object or JSON path")
        return result
    raise P2PregateError(f"{label}: expected path, object, or iterable")


def _add_issue(issues: list[dict[str, str]], code: str, message: str) -> None:
    if not any(issue["code"] == code for issue in issues):
        issues.append({"code": code, "message": message})


def _validate_private_documents(documents: list[tuple[str, Any, bytes]], issues: list[dict[str, str]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for label, value, _raw in documents:
        try:
            values.append(validate_private_binding(value, label))
        except P2PregateError as exc:
            _add_issue(issues, "private_binding_invalid", str(exc))
    return values


def _validate_public_documents(documents: list[tuple[str, Any, bytes]], issues: list[dict[str, str]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for label, value, _raw in documents:
        try:
            values.append(validate_opaque_envelope(value, label))
        except P2PregateError as exc:
            _add_issue(issues, "public_envelope_invalid", str(exc))
    return values


def _private_chain(values: list[dict[str, Any]], issues: list[dict[str, str]]) -> tuple[bool, str | None, str | None, list[str]]:
    if not values:
        _add_issue(issues, "private_chain_missing", "no valid private bindings were supplied")
        return False, None, None, []
    ordered = sorted(values, key=lambda item: item["sequence"])
    valid = True
    window = ordered[0]["window_id"]
    candidate = ordered[0]["candidate_commit"]
    hashes: list[str] = []
    for index, value in enumerate(ordered, start=1):
        if value["sequence"] != index:
            _add_issue(issues, "private_sequence_invalid", "private binding sequence is not gap-free")
            valid = False
        if value["window_id"] != window or value["candidate_commit"] != candidate:
            _add_issue(issues, "private_window_mismatch", "private bindings do not share one window and candidate")
            valid = False
        expected_previous = None if index == 1 else hashes[-1]
        if value["previous_private_binding_sha256"] != expected_previous:
            _add_issue(issues, "private_chain_link_invalid", "private binding previous digest does not match")
            valid = False
        try:
            hashes.append(canonical_sha256(value))
        except P2PregateError as exc:
            _add_issue(issues, "private_canonical_invalid", str(exc))
            valid = False
    kinds = [value["record_kind"] for value in ordered]
    if kinds[0] != "window_freeze":
        _add_issue(issues, "private_freeze_missing", "private sequence must begin with window_freeze")
        valid = False
    if kinds.count("window_freeze") != 1:
        _add_issue(issues, "private_freeze_invalid", "private sequence must contain exactly one window_freeze")
        valid = False
    if kinds.count("window_closure") != 1 or kinds[-1] != "window_closure":
        _add_issue(issues, "private_closure_missing", "private sequence must end with one window_closure")
        valid = False
    if "window_closure" in kinds[:-1]:
        _add_issue(issues, "private_post_closure", "private records cannot follow closure")
        valid = False
    ready_count = kinds.count("task_ready")
    outcome_count = kinds.count("task_outcome")
    if ready_count != outcome_count:
        _add_issue(issues, "task_outcome_pair_missing", "every task-ready binding requires one task-outcome binding")
        valid = False
    if outcome_count and ("task_ready" not in kinds or kinds.index("task_outcome") < kinds.index("task_ready")):
        _add_issue(issues, "task_outcome_before_ready", "task outcome cannot precede the first task-ready binding")
        valid = False
    return valid, window, candidate, hashes


def _public_chain(values: list[dict[str, Any]], issues: list[dict[str, str]]) -> tuple[bool, str | None, list[str]]:
    if not values:
        _add_issue(issues, "public_chain_missing", "no valid public envelopes were supplied")
        return False, None, []
    ordered = sorted(values, key=lambda item: item["sequence"])
    valid = True
    opaque_window = ordered[0]["opaque_window_id"]
    hashes: list[str] = []
    for index, value in enumerate(ordered, start=1):
        if value["sequence"] != index:
            _add_issue(issues, "public_sequence_invalid", "public envelope sequence is not gap-free")
            valid = False
        if value["opaque_window_id"] != opaque_window:
            _add_issue(issues, "public_window_mismatch", "public envelopes do not share one opaque window")
            valid = False
        expected_previous = None if index == 1 else hashes[-1]
        if value["previous_envelope_sha256"] != expected_previous:
            _add_issue(issues, "public_chain_link_invalid", "public previous digest does not match")
            valid = False
        try:
            hashes.append(envelope_sha256(value))
        except P2PregateError as exc:
            _add_issue(issues, "public_canonical_invalid", str(exc))
            valid = False
    return valid, opaque_window, hashes


def _git_commit_exists(repo: Path, commit: str) -> bool:
    if not SHA1_HEX.fullmatch(commit):
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def _verify_git_chain(repo: Any, freeze: Any, head: Any, issues: list[dict[str, str]], prefix: str) -> bool:
    if not isinstance(repo, (str, Path)) or not isinstance(freeze, str) or not isinstance(head, str):
        _add_issue(issues, f"{prefix}_anchor_missing", f"{prefix} Git root and trusted freeze/head are required")
        return False
    repo_path = Path(repo)
    if not repo_path.is_dir() or not _git_commit_exists(repo_path, freeze) or not _git_commit_exists(repo_path, head):
        _add_issue(issues, f"{prefix}_anchor_invalid", f"{prefix} trusted Git commits are not available")
        return False
    try:
        ancestor = subprocess.run(
            ["git", "-C", str(repo_path), "merge-base", "--is-ancestor", freeze, head],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        ancestor = None
    if ancestor is None or ancestor.returncode != 0:
        _add_issue(issues, f"{prefix}_anchor_disconnected", f"{prefix} freeze is not an ancestor of head")
        return False
    return True


def _proof_documents(source: Any, issues: list[dict[str, str]]) -> list[dict[str, Any]]:
    try:
        documents = _load_documents(source, "proof_packages")
    except P2PregateError as exc:
        _add_issue(issues, "proof_package_missing", str(exc))
        return []
    values: list[dict[str, Any]] = []
    for label, value, _raw in documents:
        if isinstance(value, dict) and "verified" in value:
            _add_issue(issues, "proof_self_reported_verification", "proof package self-reports verified and is rejected")
        try:
            values.append(validate_external_proof_package(value, label))
        except P2PregateError as exc:
            _add_issue(issues, "proof_package_invalid", str(exc))
    return values


def _validate_recovery_inventory(source: Any, issues: list[dict[str, str]]) -> bool:
    if source is None:
        _add_issue(issues, "recovery_missing", "no independent recovery inventory was supplied")
        return False
    try:
        documents = _load_documents(source, "recovery_inventory")
    except P2PregateError as exc:
        _add_issue(issues, "recovery_invalid", str(exc))
        return False
    if len(documents) != 1 or not isinstance(documents[0][1], dict):
        _add_issue(issues, "recovery_invalid", "recovery inventory must be one object")
        return False
    value = documents[0][1]
    # The local P2 contract can establish inventory presence and declared clean
    # restore status, but it cannot turn a declaration into a recovery proof.
    if value.get("restore_verified") is not True:
        _add_issue(issues, "recovery_unproven", "recovery inventory is not a verified clean restore")
        return False
    source_digest = value.get("source_bundle_sha256")
    restored_digest = value.get("restored_bundle_sha256")
    if not isinstance(source_digest, str) or not SHA256_HEX.fullmatch(source_digest):
        _add_issue(issues, "recovery_invalid", "recovery source bundle digest is invalid")
        return False
    if not isinstance(restored_digest, str) or not SHA256_HEX.fullmatch(restored_digest):
        _add_issue(issues, "recovery_invalid", "recovery restored bundle digest is invalid")
        return False
    if source_digest != restored_digest:
        _add_issue(issues, "recovery_mismatch", "recovery restored bytes differ from the source bundle")
        return False
    return True


def evaluate_pregate(
    *,
    private_bindings: Any = None,
    public_envelopes: Any = None,
    proof_packages: Any = None,
    window_salt: bytes | str | None = None,
    private_anchor_repo: Any = None,
    private_freeze_commit: Any = None,
    private_head_commit: Any = None,
    public_anchor_repo: Any = None,
    public_freeze_commit: Any = None,
    public_head_commit: Any = None,
    final_manifest: Any = None,
    recovery_inventory: Any = None,
    expected_candidate_commit: str | None = None,
) -> dict[str, Any]:
    """Evaluate local P2 inputs and return stable machine-readable status.

    ``eligible_for_v2_release_gate`` is intentionally false for every invocation
    in this implementation because no Owner-approved P3 cryptographic adapter is
    present.  The function never imports or executes the existing release gate.
    """

    issues: list[dict[str, str]] = []
    try:
        salt = _salt_bytes(window_salt)
    except P2PregateError as exc:
        salt = None
        _add_issue(issues, "salt_invalid", str(exc))
    try:
        private_docs = _load_documents(private_bindings, "private_bindings")
    except P2PregateError as exc:
        private_docs = []
        _add_issue(issues, "private_binding_missing", str(exc))
    try:
        public_docs = _load_documents(public_envelopes, "public_envelopes")
    except P2PregateError as exc:
        public_docs = []
        _add_issue(issues, "public_envelope_missing", str(exc))
    private_values = _validate_private_documents(private_docs, issues)
    public_values = _validate_public_documents(public_docs, issues)
    private_chain_ok, window_id, candidate_commit, _private_hashes = _private_chain(private_values, issues)
    public_chain_ok, _opaque_window, public_hashes = _public_chain(public_values, issues)
    if expected_candidate_commit is not None and candidate_commit != expected_candidate_commit:
        _add_issue(issues, "candidate_mismatch", "private binding candidate differs from trusted candidate")
        private_chain_ok = False

    private_anchor_ok = _verify_git_chain(
        private_anchor_repo,
        private_freeze_commit,
        private_head_commit,
        issues,
        "private",
    )
    public_anchor_ok = _verify_git_chain(
        public_anchor_repo,
        public_freeze_commit,
        public_head_commit,
        issues,
        "public",
    )
    if salt is None:
        _add_issue(issues, "salt_missing", "private window salt is required to recompute commitments")
    if salt is not None and window_id is not None:
        expected_opaque = opaque_window_id(window_id, salt)
        for value in public_values:
            if value["opaque_window_id"] != expected_opaque:
                _add_issue(issues, "opaque_window_mismatch", "public opaque window does not bind the private window")
                public_chain_ok = False
                break
        if len(private_values) != len(public_values):
            _add_issue(issues, "receipt_count_mismatch", "private and public chains have different record counts")
            public_chain_ok = False
        by_sequence = {value["sequence"]: value for value in private_values}
        for envelope in public_values:
            binding = by_sequence.get(envelope["sequence"])
            if binding is None or commitment_sha256(binding, salt) != envelope["commitment_sha256"]:
                _add_issue(issues, "commitment_mismatch", "public commitment does not bind private bytes")
                public_chain_ok = False
                break
    proofs = _proof_documents(proof_packages, issues)
    if not proofs:
        _add_issue(issues, "trusted_time_missing", "no retained external proof package is available")
    else:
        expected_public_digests = set(public_hashes)
        proof_digests = [proof["submitted_digest_sha256"] for proof in proofs]
        if len(proofs) != len(public_values):
            _add_issue(issues, "proof_count_mismatch", "each public envelope requires one retained proof package")
        if len(set(proof_digests)) != len(proof_digests):
            _add_issue(issues, "proof_duplicate_digest", "proof packages must bind distinct public envelopes")
        for proof in proofs:
            if proof["submitted_digest_sha256"] not in expected_public_digests:
                _add_issue(issues, "proof_digest_mismatch", "proof package digest does not match a public envelope")
        # Presence and schema validity are deliberately not qualification.  A P3
        # adapter must be separately approved and implemented before this turns true.
        _add_issue(issues, "trusted_time_missing", "retained proof is not cryptographically qualified by a P3 adapter")
    _add_issue(issues, "external_receipts_unproven", "external receipt time and transparency are not verified")
    _add_issue(issues, "pre_outcome_order_unproven", "task-ready to outcome order lacks trusted external time")
    _add_issue(issues, "public_control_unproven", "local evidence cannot prove public append-only controls")

    privacy_allowlist_ok = bool(public_values) and not any(issue["code"] == "public_envelope_invalid" for issue in issues)
    if not privacy_allowlist_ok:
        _add_issue(issues, "privacy_allowlist_failed", "public envelope allowlist is absent or invalid")
    recovery_ok = _validate_recovery_inventory(recovery_inventory, issues)

    # The final Manifest is an input boundary for the future full verifier.  The
    # local contract only rejects a missing path if a caller supplied one.
    if final_manifest is not None:
        try:
            _load_documents(final_manifest, "final_manifest")
        except P2PregateError as exc:
            _add_issue(issues, "manifest_invalid", str(exc))

    issues.sort(key=lambda item: item["code"])
    return {
        "schema_version": SCHEMA_VERSION,
        "control_profile": CONTROL_PROFILE,
        "canonicalization_profile": PROFILE,
        "private_anchor_integral": bool(private_chain_ok and private_anchor_ok),
        "public_chain_integral": bool(public_chain_ok),
        "public_control_proven": False,
        "external_receipts_integral": False,
        "pre_outcome_order_proven": False,
        "privacy_allowlist_passed": privacy_allowlist_ok,
        "recovery_demonstrated": recovery_ok,
        "eligible_for_v2_release_gate": False,
        "trusted_private_freeze_commit": private_freeze_commit if private_anchor_ok else None,
        "trusted_private_head_commit": private_head_commit if private_anchor_ok else None,
        "release_gate_invoked": False,
        "issues": issues,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-bindings", required=True)
    parser.add_argument("--public-envelopes", required=True)
    parser.add_argument("--proof-packages")
    parser.add_argument("--window-salt-hex")
    parser.add_argument("--private-anchor-repo")
    parser.add_argument("--private-freeze-commit")
    parser.add_argument("--private-head-commit")
    parser.add_argument("--public-anchor-repo")
    parser.add_argument("--public-freeze-commit")
    parser.add_argument("--public-head-commit")
    parser.add_argument("--final-manifest")
    parser.add_argument("--recovery-inventory")
    parser.add_argument("--expected-candidate-commit")
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = evaluate_pregate(
        private_bindings=args.private_bindings,
        public_envelopes=args.public_envelopes,
        proof_packages=args.proof_packages,
        window_salt=args.window_salt_hex,
        private_anchor_repo=args.private_anchor_repo,
        private_freeze_commit=args.private_freeze_commit,
        private_head_commit=args.private_head_commit,
        public_anchor_repo=args.public_anchor_repo,
        public_freeze_commit=args.public_freeze_commit,
        public_head_commit=args.public_head_commit,
        final_manifest=args.final_manifest,
        recovery_inventory=args.recovery_inventory,
        expected_candidate_commit=args.expected_candidate_commit,
    )
    rendered = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8", newline="\n")
    else:
        print(rendered)
    return 0 if result["eligible_for_v2_release_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


# Small, explicit aliases keep the contract convenient for validators without
# introducing a second implementation or a compatibility dependency.
parse_cj1 = parse_json_bytes
canonicalize_cj1 = canonicalize_json_bytes
render_cj1 = canonicalize_value
verify_p2_pregate = evaluate_pregate
verify_pregate = evaluate_pregate
