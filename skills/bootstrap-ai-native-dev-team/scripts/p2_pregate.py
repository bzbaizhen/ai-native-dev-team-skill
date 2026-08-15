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
from datetime import datetime
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
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
_PROTOCOL_VERSION = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
_RELATIVE_PROOF_PATH = re.compile(r"^[a-zA-Z0-9._/-]+$")
_PUBLIC_REF = re.compile(r"^refs/(?:heads|tags)/[A-Za-z0-9][A-Za-z0-9._/-]*$")
_PUBLIC_RECEIPT_PATH = re.compile(
    r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\.json$"
)
_PRINTABLE_TOKEN = re.compile(r"^[!-~]+$")
_LOWER_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_MANIFEST_SHA1 = re.compile(r"^[0-9a-fA-F]{40}$")
_MANIFEST_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
GIT_TIMEOUT_SECONDS = 5.0

PUBLIC_ANCHOR_MANIFEST_FIELDS = {
    "schema_version",
    "public_ref",
    "freeze_commit",
    "head_commit",
    "receipts",
}
PUBLIC_ANCHOR_RECEIPT_FIELDS = {
    "sequence",
    "commit",
    "path",
    "envelope_sha256",
}
MANIFEST_ALIGNMENT_FIELDS = {
    "schema_version",
    "candidate_commit",
    "tasks",
}
MANIFEST_ALIGNMENT_TASK_FIELDS = {
    "task_id",
    "ready_binding_sequence",
    "outcome_binding_sequence",
}


def _is_normalized_relative_posix_path(path: str) -> bool:
    """Accept one normalized relative POSIX path, with no aliases or repeats."""

    try:
        pure = PurePosixPath(path)
    except (TypeError, ValueError):
        return False
    if not pure.parts or pure.is_absolute() or pure.as_posix() != path:
        return False
    return all(part not in {"", ".", ".."} for part in pure.parts)


def _is_public_receipt_path(path: str) -> bool:
    """Accept one normalized relative POSIX JSON path for a public receipt."""

    if not isinstance(path, str) or not _PUBLIC_RECEIPT_PATH.fullmatch(path):
        return False
    return _is_normalized_relative_posix_path(path)


def _is_strict_full_git_ref(value: Any) -> bool:
    """Apply the RC.5 full-ref boundary without relying on a caller's Git repo."""

    if not isinstance(value, str) or not _PUBLIC_REF.fullmatch(value):
        return False
    if any(ord(char) < 0x20 or ord(char) == 0x7F or char.isspace() for char in value):
        return False
    if any(token in value for token in ("^", "~", "@{")):
        return False
    prefix = "refs/heads/" if value.startswith("refs/heads/") else "refs/tags/"
    name = value[len(prefix) :]
    if not name or ".." in name or "//" in name or name.endswith(("/", ".")):
        return False
    segments = name.split("/")
    if any(
        not segment
        or segment in {".", ".."}
        or segment.startswith(".")
        or segment.endswith(".")
        or segment.endswith(".lock")
        for segment in segments
    ):
        return False
    return True


def _require_manifest_string(value: Any, field: str, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{location}.{field}: non-empty string required")
    return value


def _require_manifest_sha(value: Any, field: str, location: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise SchemaValidationError(f"{location}.{field}: invalid digest")
    return value


def _is_valid_expected_candidate(value: Any) -> bool:
    return value is None or (isinstance(value, str) and _LOWER_SHA1.fullmatch(value) is not None)


def _manifest_time(value: Any, field: str, location: str) -> datetime:
    text = _require_manifest_string(value, field, location)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SchemaValidationError(f"{location}.{field}: invalid RFC 3339 date-time") from exc
    if parsed.tzinfo is None:
        raise SchemaValidationError(f"{location}.{field}: timezone is required")
    return parsed


def _validate_integration_proof_local(value: Any, location: str) -> dict[str, Any]:
    """Mirror the validation-only shape contract of v2_release_gate."""

    if not isinstance(value, dict):
        raise SchemaValidationError(f"{location}: object required")
    mode = value.get("mode")
    if mode == "same_commit":
        if set(value) != {"mode"}:
            raise SchemaValidationError(f"{location}: same_commit fields differ")
        return value
    if mode != "same_tree" or set(value) != {
        "mode",
        "candidate_ref",
        "candidate_tree",
        "stable_tree",
        "tree_scope",
    }:
        raise SchemaValidationError(f"{location}: integration proof fields differ")
    candidate_ref = value["candidate_ref"]
    if not _is_strict_full_git_ref(candidate_ref):
        raise SchemaValidationError(f"{location}.candidate_ref: invalid full Git ref")
    _require_manifest_sha(value["candidate_tree"], "candidate_tree", location, _MANIFEST_SHA1)
    _require_manifest_sha(value["stable_tree"], "stable_tree", location, _MANIFEST_SHA1)
    tree_scope = value["tree_scope"]
    if not isinstance(tree_scope, dict) or set(tree_scope) != {
        "history_sensitive",
        "non_tree_dependencies",
    }:
        raise SchemaValidationError(f"{location}.tree_scope: fields differ")
    if tree_scope["history_sensitive"] is not False:
        raise SchemaValidationError(f"{location}.tree_scope.history_sensitive: must be false")
    dependencies = tree_scope["non_tree_dependencies"]
    if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
        raise SchemaValidationError(f"{location}.tree_scope.non_tree_dependencies: string array required")
    if dependencies:
        raise SchemaValidationError(f"{location}.tree_scope.non_tree_dependencies: must be empty")
    return value


def validate_public_anchor_manifest(
    value: Any,
    location: str = "public_anchor_manifest",
) -> dict[str, Any]:
    """Validate the explicit public ref and one-envelope-per-Commit index."""

    _validate_cj_value(value, location)
    obj = _require_exact_fields(value, PUBLIC_ANCHOR_MANIFEST_FIELDS, location)
    if obj["schema_version"] != SCHEMA_VERSION:
        raise SchemaValidationError(f"{location}.schema_version: unsupported version")
    public_ref = obj["public_ref"]
    if not _is_strict_full_git_ref(public_ref):
        raise SchemaValidationError(f"{location}.public_ref: unsafe Git ref")
    _require_manifest_sha(obj["freeze_commit"], "freeze_commit", location, SHA1_HEX)
    _require_manifest_sha(obj["head_commit"], "head_commit", location, SHA1_HEX)
    receipts = obj["receipts"]
    if not isinstance(receipts, list) or not receipts:
        raise SchemaValidationError(f"{location}.receipts: non-empty array required")
    seen_sequences: set[int] = set()
    seen_commits: set[str] = set()
    seen_paths: set[str] = set()
    for index, item in enumerate(receipts):
        item_location = f"{location}.receipts[{index}]"
        _validate_cj_value(item, item_location)
        receipt = _require_exact_fields(item, PUBLIC_ANCHOR_RECEIPT_FIELDS, item_location)
        sequence = _require_int(receipt["sequence"], "sequence", item_location, positive=True)
        if sequence in seen_sequences:
            raise SchemaValidationError(f"{item_location}.sequence: duplicate sequence")
        seen_sequences.add(sequence)
        commit = _require_manifest_sha(receipt["commit"], "commit", item_location, SHA1_HEX)
        if commit in seen_commits:
            raise SchemaValidationError(f"{item_location}.commit: duplicate Commit")
        seen_commits.add(commit)
        path = receipt["path"]
        if not _is_public_receipt_path(path):
            raise SchemaValidationError(f"{item_location}.path: normalized relative JSON path required")
        if path in seen_paths:
            raise SchemaValidationError(f"{item_location}.path: duplicate path")
        seen_paths.add(path)
        _require_manifest_sha(receipt["envelope_sha256"], "envelope_sha256", item_location, SHA256_HEX)
    if sorted(seen_sequences) != list(range(1, len(receipts) + 1)):
        raise SchemaValidationError(f"{location}.receipts: sequence must be gap-free from 1")
    return obj


def validate_manifest_alignment_index(
    value: Any,
    location: str = "manifest_alignment",
) -> dict[str, Any]:
    """Validate the task-to-private-binding sequence index."""

    _validate_cj_value(value, location)
    obj = _require_exact_fields(value, MANIFEST_ALIGNMENT_FIELDS, location)
    if obj["schema_version"] != SCHEMA_VERSION:
        raise SchemaValidationError(f"{location}.schema_version: unsupported version")
    _require_manifest_sha(obj["candidate_commit"], "candidate_commit", location, _LOWER_SHA1)
    tasks = obj["tasks"]
    if not isinstance(tasks, list):
        raise SchemaValidationError(f"{location}.tasks: array required")
    seen_task_ids: set[str] = set()
    for index, item in enumerate(tasks):
        item_location = f"{location}.tasks[{index}]"
        _validate_cj_value(item, item_location)
        task = _require_exact_fields(item, MANIFEST_ALIGNMENT_TASK_FIELDS, item_location)
        task_id = task["task_id"]
        if not isinstance(task_id, str) or not _PRINTABLE_TOKEN.fullmatch(task_id):
            raise SchemaValidationError(f"{item_location}.task_id: printable ASCII token required")
        if task_id in seen_task_ids:
            raise SchemaValidationError(f"{item_location}.task_id: duplicate task_id")
        seen_task_ids.add(task_id)
        ready = _require_int(task["ready_binding_sequence"], "ready_binding_sequence", item_location, positive=True)
        outcome = _require_int(task["outcome_binding_sequence"], "outcome_binding_sequence", item_location, positive=True)
        if outcome <= ready:
            raise SchemaValidationError(f"{item_location}.outcome_binding_sequence: must follow ready sequence")
    return obj


def validate_external_proof_package(value: Any, location: str = "proof_package") -> dict[str, Any]:
    """Validate an inventory of retained proof bytes without qualifying it."""

    _validate_cj_value(value, location)
    obj = _require_exact_fields(value, PROOF_FIELDS, location)
    if obj["schema_version"] != SCHEMA_VERSION:
        raise SchemaValidationError(f"{location}.schema_version: unsupported version")
    if obj["proof_type"] != "external_time_transparency_proof":
        raise SchemaValidationError(f"{location}.proof_type: unsupported proof type")
    _require_string(obj["provider"], "provider", _PROVIDER, location)
    _require_string(obj["protocol_version"], "protocol_version", _PROTOCOL_VERSION, location)
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
        if not _is_normalized_relative_posix_path(path):
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
        try:
            path = Path(source)
            if path.is_file():
                raw = path.read_bytes()
                return [(str(path), parse_json_bytes(raw), raw)]
            if path.is_dir():
                # Preserve the caller/file enumeration order.  Sorting here would
                # silently repair a reversed receipt chain before sequence checks.
                children = list(path.iterdir())
                if any(not item.is_file() or item.suffix.lower() != ".json" for item in children):
                    raise P2PregateError(f"{label}_path_invalid: directory contains a non-JSON child")
                result: list[tuple[str, Any, bytes]] = []
                for item in children:
                    raw = item.read_bytes()
                    result.append((str(item), parse_json_bytes(raw), raw))
                return result
            raise P2PregateError(f"{label}_path_missing: supplied path does not exist")
        except (OSError, TypeError, ValueError) as exc:
            raise P2PregateError(f"{label}_path_invalid: {exc}") from exc
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


def _validate_private_documents(
    documents: list[tuple[str, Any, bytes]], issues: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], bool]:
    values: list[dict[str, Any]] = []
    complete = True
    for label, value, _raw in documents:
        try:
            validated = validate_private_binding(value, label)
            if _raw != canonicalize_value(validated):
                _add_issue(issues, "private_binding_noncanonical", f"{label}: raw bytes are not canonical")
                complete = False
            values.append(validated)
        except P2PregateError as exc:
            _add_issue(issues, "private_binding_invalid", str(exc))
            complete = False
    return values, complete


def _validate_public_documents(
    documents: list[tuple[str, Any, bytes]], issues: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], list[bytes], bool]:
    values: list[dict[str, Any]] = []
    raw_values: list[bytes] = []
    complete = True
    for label, value, _raw in documents:
        try:
            validated = validate_opaque_envelope(value, label)
            if _raw != canonicalize_value(validated):
                _add_issue(issues, "public_envelope_noncanonical", f"{label}: raw bytes are not canonical")
                complete = False
            values.append(validated)
            raw_values.append(_raw)
        except P2PregateError as exc:
            _add_issue(issues, "public_envelope_invalid", str(exc))
            complete = False
    return values, raw_values, complete


def _private_chain(
    values: list[dict[str, Any]], issues: list[dict[str, str]], *, input_complete: bool = True
) -> tuple[bool, str | None, str | None, list[str]]:
    if not values:
        _add_issue(issues, "private_chain_missing", "no valid private bindings were supplied")
        return False, None, None, []
    valid = True
    if not input_complete:
        _add_issue(issues, "private_input_incomplete", "invalid or non-canonical private input cannot be ignored")
        valid = False
    window = values[0]["window_id"]
    candidate = values[0]["candidate_commit"]
    hashes: list[str] = []
    pending_ready = 0
    for index, value in enumerate(values, start=1):
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
        if value["record_kind"] == "task_ready":
            pending_ready += 1
        elif value["record_kind"] == "task_outcome":
            if pending_ready == 0:
                _add_issue(issues, "task_outcome_without_ready", "task outcome has no pending task-ready binding")
                valid = False
            else:
                pending_ready -= 1
        elif value["record_kind"] == "window_closure" and pending_ready != 0:
            _add_issue(issues, "pending_task_ready_at_closure", "window closure has pending task-ready bindings")
            valid = False
    kinds = [value["record_kind"] for value in values]
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
    if pending_ready != 0:
        _add_issue(issues, "pending_task_ready_at_end", "private sequence ends with pending task-ready bindings")
        valid = False
    return valid, window, candidate, hashes


def _public_chain(
    values: list[dict[str, Any]], issues: list[dict[str, str]], *, input_complete: bool = True
) -> tuple[bool, str | None, list[str]]:
    if not values:
        _add_issue(issues, "public_chain_missing", "no valid public envelopes were supplied")
        return False, None, []
    valid = True
    if not input_complete:
        _add_issue(issues, "public_input_incomplete", "invalid or non-canonical public input cannot be ignored")
        valid = False
    opaque_window = values[0]["opaque_window_id"]
    hashes: list[str] = []
    for index, value in enumerate(values, start=1):
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


def _run_git(repo: Any, *args: str, text: bool = False) -> subprocess.CompletedProcess[Any] | None:
    """Run one bounded Git read and convert process failures into no-result."""

    try:
        command = ["git", "-C", str(repo), *args]
        kwargs: dict[str, Any] = {
            "check": False,
            "capture_output": True,
            "timeout": GIT_TIMEOUT_SECONDS,
        }
        if text:
            kwargs.update({"text": True, "encoding": "utf-8", "errors": "replace"})
        return subprocess.run(command, **kwargs)
    except (OSError, TypeError, ValueError, subprocess.TimeoutExpired):
        return None


def _git_commit_exists(repo: Path, commit: str) -> bool:
    if not isinstance(commit, str) or not SHA1_HEX.fullmatch(commit):
        return False
    result = _run_git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    try:
        return_code = getattr(result, "returncode")
        stdout = getattr(result, "stdout")
        stderr = getattr(result, "stderr")
    except Exception:
        return False
    return (
        type(return_code) is int
        and isinstance(stdout, (bytes, bytearray, memoryview))
        and isinstance(stderr, (bytes, bytearray, memoryview))
        and return_code == 0
    )


def _verify_git_chain(repo: Any, freeze: Any, head: Any, issues: list[dict[str, str]], prefix: str) -> bool:
    if not isinstance(repo, (str, Path)) or not isinstance(freeze, str) or not isinstance(head, str):
        _add_issue(issues, f"{prefix}_anchor_missing", f"{prefix} Git root and trusted freeze/head are required")
        return False
    try:
        repo_path = Path(repo)
    except (OSError, TypeError, ValueError) as exc:
        _add_issue(issues, f"{prefix}_anchor_invalid", f"{prefix} Git root is invalid: {exc}")
        return False
    if not repo_path.is_dir() or not _git_commit_exists(repo_path, freeze) or not _git_commit_exists(repo_path, head):
        _add_issue(issues, f"{prefix}_anchor_invalid", f"{prefix} trusted Git commits are not available")
        return False
    ancestor = _run_git_text(repo_path, "merge-base", "--is-ancestor", freeze, head)
    if ancestor is None or ancestor.returncode != 0:
        _add_issue(issues, f"{prefix}_anchor_disconnected", f"{prefix} freeze is not an ancestor of head")
        return False
    nonlinear = _run_git_text(repo_path, "rev-list", "--merges", f"{freeze}..{head}")
    if nonlinear is None or nonlinear.returncode != 0:
        _add_issue(issues, f"{prefix}_anchor_history_unreadable", f"{prefix} history could not be inspected")
        return False
    if nonlinear.stdout.strip():
        _add_issue(issues, f"{prefix}_anchor_nonlinear", f"{prefix} freeze/head history contains a merge")
        return False
    return True


def _verify_private_binding_anchors(
    repo: Any,
    freeze: Any,
    head: Any,
    values: list[dict[str, Any]],
    issues: list[dict[str, str]],
) -> bool:
    """Verify every private binding anchor and its ordered Git ancestry."""

    if not values:
        _add_issue(issues, "private_anchor_missing", "private binding anchors are absent")
        return False
    anchors = [value["private_anchor_commit"] for value in values]
    if any(anchor is None for anchor in anchors):
        _add_issue(issues, "private_anchor_missing", "every private binding must carry an anchor commit")
        return False
    if not isinstance(freeze, str) or not isinstance(head, str):
        _add_issue(issues, "private_anchor_unproven", "trusted private freeze/head commits are required")
        return False
    if anchors[0] != freeze or anchors[-1] != head:
        _add_issue(issues, "private_anchor_endpoint_mismatch", "first/last private anchors do not match trusted freeze/head")
        return False
    try:
        repo_path = Path(repo)
    except (OSError, TypeError, ValueError) as exc:
        _add_issue(issues, "private_anchor_unproven", f"private Git root is invalid: {exc}")
        return False
    if not repo_path.is_dir():
        _add_issue(issues, "private_anchor_unproven", "private Git root is required for event anchor verification")
        return False
    valid = True
    for anchor in anchors:
        if not isinstance(anchor, str) or not _git_commit_exists(repo_path, anchor):
            _add_issue(issues, "private_anchor_commit_missing", "a private event anchor commit is unavailable")
            valid = False
    for previous, current in zip(anchors, anchors[1:]):
        if previous == current:
            _add_issue(issues, "private_anchor_repeated", "private event anchors must advance by sequence")
            valid = False
            continue
        connected = _run_git_text(repo_path, "merge-base", "--is-ancestor", previous, current)
        if connected is None or connected.returncode != 0:
            _add_issue(issues, "private_anchor_disconnected", "private event anchors are not ordered ancestors")
            valid = False
    return valid


def _run_git_text(repo: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    result = _run_git(repo, *args, text=True)
    if result is None or not isinstance(getattr(result, "stdout", None), str) or not isinstance(
        getattr(result, "stderr", None), str
    ):
        return None
    return result


def _git_blob_bytes(repo: Path, commit: str, path: str) -> bytes | None:
    result = _run_git(repo, "show", f"{commit}:{path}")
    if result is None or not isinstance(getattr(result, "stdout", None), (bytes, bytearray)) or not isinstance(
        getattr(result, "stderr", None), (bytes, bytearray)
    ):
        return None
    if result.returncode != 0:
        return None
    return bytes(result.stdout)


def _git_name_status(repo: Path, *args: str) -> list[tuple[str, str]] | None:
    result = _run_git_text(repo, *args)
    if result is None or result.returncode != 0:
        return None
    entries: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        status, separator, path = line.partition("\t")
        if not separator:
            return None
        entries.append((status, path))
    return entries


def _verify_public_ref(
    repo: Path,
    public_ref: str,
    expected_head: str,
    issues: list[dict[str, str]],
) -> bool:
    valid = True
    checked = _run_git_text(repo, "check-ref-format", public_ref)
    if checked is None or checked.returncode != 0:
        _add_issue(issues, "public_ref_invalid", "public ref fails git check-ref-format")
        return False
    resolved = _run_git_text(repo, "rev-parse", "--verify", f"{public_ref}^{{commit}}")
    target = resolved.stdout.strip() if resolved is not None else ""
    if resolved is None or resolved.returncode != 0 or not SHA1_HEX.fullmatch(target):
        _add_issue(issues, "public_ref_missing", "public ref does not resolve to a Commit")
        return False
    if target != expected_head:
        _add_issue(issues, "public_ref_head_mismatch", "public ref does not resolve to trusted head Commit")
        valid = False
    return valid


def _verify_public_anchor_manifest(
    repo: Any,
    source: Any,
    public_values: list[dict[str, Any]],
    public_raw_values: list[bytes],
    trusted_freeze: Any,
    trusted_head: Any,
    issues: list[dict[str, str]],
    *,
    public_input_complete: bool,
    public_chain_ok: bool,
    public_git_chain_ok: bool,
    private_chain_ok: bool,
    private_commitments_ok: bool,
) -> bool:
    """Verify exact public ref, history, Git changes and envelope bytes."""

    if source is None:
        _add_issue(issues, "public_anchor_unproven", "explicit public ref and Commit-to-envelope manifest are required")
        return False
    if not isinstance(repo, (str, Path)) or not isinstance(trusted_freeze, str) or not isinstance(trusted_head, str):
        _add_issue(issues, "public_anchor_unproven", "public anchor repo and trusted freeze/head are required")
        return False
    try:
        manifest = _load_single_object(source, "public_anchor_manifest")
        manifest = validate_public_anchor_manifest(manifest)
    except P2PregateError as exc:
        _add_issue(issues, "public_anchor_manifest_invalid", str(exc))
        return False
    if manifest["freeze_commit"] != trusted_freeze or manifest["head_commit"] != trusted_head:
        _add_issue(issues, "public_anchor_manifest_endpoint_mismatch", "public anchor freeze/head differs from trusted inputs")
        return False
    if not public_input_complete:
        _add_issue(issues, "public_mapping_input_incomplete", "public mapping requires every supplied envelope to be valid and canonical")
        return False
    if not public_chain_ok:
        _add_issue(issues, "public_mapping_chain_unproven", "public mapping requires the supplied envelope chain in caller order")
        return False
    if not public_git_chain_ok:
        _add_issue(issues, "public_mapping_git_chain_unproven", "public mapping requires an integral trusted Git chain")
        return False
    if not private_chain_ok:
        _add_issue(issues, "public_mapping_private_chain_unproven", "public mapping requires an integral private binding chain")
        return False
    if not private_commitments_ok:
        _add_issue(issues, "public_mapping_commitments_unproven", "public mapping requires private commitment alignment")
        return False
    try:
        repo_path = Path(repo)
    except (OSError, TypeError, ValueError) as exc:
        _add_issue(issues, "public_anchor_repo_not_root", f"public Git root is invalid: {exc}")
        return False
    root = _run_git_text(repo_path, "rev-parse", "--show-toplevel")
    if root is None or root.returncode != 0 or Path(root.stdout.strip()).resolve() != repo_path.resolve():
        _add_issue(issues, "public_anchor_repo_not_root", "public_anchor_repo must be the Git root")
        return False
    if not _verify_public_ref(repo_path, manifest["public_ref"], trusted_head, issues):
        return False

    receipt_commits = [receipt["commit"] for receipt in manifest["receipts"]]
    history = _run_git_text(
        repo_path,
        "rev-list",
        "--reverse",
        "--first-parent",
        f"{trusted_freeze}..{trusted_head}",
    )
    if history is None or history.returncode != 0:
        _add_issue(issues, "public_history_unreadable", "public first-parent history could not be read")
        return False
    history_commits = [line.strip() for line in history.stdout.splitlines() if line.strip()]
    count_result = _run_git_text(repo_path, "rev-list", "--count", f"{trusted_freeze}..{trusted_head}")
    try:
        all_count = int(count_result.stdout.strip()) if count_result is not None and count_result.returncode == 0 else -1
    except ValueError:
        all_count = -1
    valid = True
    if all_count != len(history_commits):
        _add_issue(issues, "public_history_side_branch", "public history contains side-history outside first-parent chain")
        valid = False
    if history_commits != receipt_commits:
        _add_issue(issues, "public_commit_sequence_mismatch", "public Git history does not equal manifest receipt Commit sequence")
        valid = False
    previous = trusted_freeze
    for commit in history_commits:
        parents_result = _run_git_text(repo_path, "show", "-s", "--format=%P", commit)
        parents = parents_result.stdout.split() if parents_result is not None and parents_result.returncode == 0 else []
        if parents != [previous]:
            _add_issue(issues, "public_history_nonlinear", "public history contains a merge or discontinuity")
            valid = False
        previous = commit

    values_by_sequence = {value["sequence"]: value for value in public_values}
    raw_by_sequence = {
        value["sequence"]: raw for value, raw in zip(public_values, public_raw_values, strict=True)
    }
    if len(values_by_sequence) != len(public_values) or len(public_values) != len(manifest["receipts"]):
        _add_issue(issues, "public_mapping_count_mismatch", "public anchor receipts and supplied envelopes differ in count")
        valid = False
    for receipt in manifest["receipts"]:
        sequence = receipt["sequence"]
        commit = receipt["commit"]
        path = receipt["path"]
        changes = _git_name_status(
            repo_path,
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "--no-renames",
            "-r",
            commit,
        )
        if changes != [("A", path)]:
            _add_issue(issues, "public_commit_change_invalid", "each public receipt Commit must add only its mapped path")
            valid = False
        if _git_blob_bytes(repo_path, trusted_freeze, path) is not None:
            _add_issue(issues, "public_freeze_contains_receipt", "public freeze tree already contains a mapped receipt path")
            valid = False
        raw = _git_blob_bytes(repo_path, commit, path)
        if raw is None:
            _add_issue(issues, "public_envelope_blob_missing", "mapped envelope bytes are absent from Commit")
            valid = False
            continue
        try:
            parsed = parse_json_bytes(raw)
            validate_opaque_envelope(parsed, f"public_git[{sequence}]")
            canonical = canonicalize_value(parsed)
        except P2PregateError as exc:
            _add_issue(issues, "public_envelope_noncanonical", str(exc))
            valid = False
            continue
        if raw != canonical:
            _add_issue(issues, "public_envelope_noncanonical", "mapped Git envelope bytes are not canonical")
            valid = False
        if hashlib.sha256(raw).hexdigest() != receipt["envelope_sha256"]:
            _add_issue(issues, "public_envelope_digest_mismatch", "mapped Git envelope digest differs from manifest")
            valid = False
        supplied = values_by_sequence.get(sequence)
        if supplied is None:
            _add_issue(issues, "public_envelope_sequence_missing", "mapped Commit has no supplied same-sequence envelope")
            valid = False
        else:
            supplied_raw = raw_by_sequence.get(sequence)
            if supplied_raw is None or supplied_raw != raw or envelope_sha256(supplied) != receipt["envelope_sha256"]:
                _add_issue(issues, "public_commit_envelope_mismatch", "mapped Commit bytes differ from supplied envelope")
                valid = False
    final_changes = _git_name_status(
        repo_path,
        "diff",
        "--name-status",
        "--no-renames",
        trusted_freeze,
        trusted_head,
    )
    expected_changes = sorted(("A", receipt["path"]) for receipt in manifest["receipts"])
    if final_changes is None or sorted(final_changes) != expected_changes:
        _add_issue(issues, "public_final_diff_invalid", "public freeze-to-head diff is not exactly the mapped additions")
        valid = False
    return valid


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
        _add_issue(issues, "recovery_unproven", "no local restore/bundle-byte verifier is implemented")
        return False
    try:
        documents = _load_documents(source, "recovery_inventory")
    except P2PregateError as exc:
        _add_issue(issues, "recovery_invalid", str(exc))
        _add_issue(issues, "recovery_unproven", "no local restore/bundle-byte verifier is implemented")
        return False
    if len(documents) != 1 or not isinstance(documents[0][1], dict):
        _add_issue(issues, "recovery_invalid", "recovery inventory must be one object")
        _add_issue(issues, "recovery_unproven", "no local restore/bundle-byte verifier is implemented")
        return False
    value = documents[0][1]
    # Inventory fields are shape-checked only.  The local P2 contract has no
    # restore/bundle-byte verifier, so neither a boolean nor caller-provided
    # digests may turn this into a demonstrated recovery.
    if "restore_verified" in value and not isinstance(value["restore_verified"], bool):
        _add_issue(issues, "recovery_invalid", "restore_verified must be boolean when present")
    source_digest = value.get("source_bundle_sha256")
    restored_digest = value.get("restored_bundle_sha256")
    if source_digest is not None and (not isinstance(source_digest, str) or not SHA256_HEX.fullmatch(source_digest)):
        _add_issue(issues, "recovery_invalid", "recovery source bundle digest is invalid")
    if restored_digest is not None and (not isinstance(restored_digest, str) or not SHA256_HEX.fullmatch(restored_digest)):
        _add_issue(issues, "recovery_invalid", "recovery restored bundle digest is invalid")
    _add_issue(issues, "recovery_unproven", "no local restore/bundle-byte verifier is implemented")
    return False


MANIFEST_REQUIRED_FIELDS = {
    "schema_version",
    "candidate_version",
    "candidate_commit",
    "candidate_frozen_at",
    "registry_closed_at",
    "source_registry",
    "source_registry_sha256",
    "required_comparable_tasks",
    "sources",
    "trials",
}
MANIFEST_DISPOSITIONS = {"accepted", "in_progress", "blocked", "cancelled", "rejected"}
MANIFEST_SOURCE_FIELDS = {
    "source_id",
    "project_alias",
    "project_evidence_id",
    "project_repo",
    "stable_branch",
    "ledger",
    "ledger_prefix_bytes",
    "ledger_prefix_sha256",
    "ledger_sha256",
}
MANIFEST_REQUIRED_TRIAL_FIELDS = {
    "trial_id",
    "registration_sequence",
    "source_id",
    "task_id",
    "skill_candidate_commit",
    "request_evidence",
    "request_evidence_sha256",
    "v1_baseline_id",
    "v1_baseline_stratum",
    "comparable",
    "disposition",
    "genuine_request",
    "synthetic",
    "critical_defect_escape",
    "material_quality_regression",
    "scope_violation",
    "write_conflict",
    "recovery_executable",
}
MANIFEST_ACCEPTED_FIELDS = {
    "candidate_commit",
    "stable_commit",
    "acceptance_evidence",
    "acceptance_evidence_sha256",
    "integration_proof",
}
MANIFEST_OPTIONAL_TRIAL_FIELDS = {"exclusion_reason", "notes"}
MANIFEST_TRIAL_FIELDS = (
    MANIFEST_REQUIRED_TRIAL_FIELDS
    | MANIFEST_ACCEPTED_FIELDS
    | MANIFEST_OPTIONAL_TRIAL_FIELDS
)
MANIFEST_QUALITY_FIELDS = {
    "critical_defect_escape",
    "material_quality_regression",
    "scope_violation",
    "write_conflict",
    "recovery_executable",
}


def _validate_manifest_object(
    value: Any,
    expected_candidate: str | None,
    location: str,
    *,
    p2_overlay: bool,
) -> dict[str, Any]:
    """Validate the frozen Manifest boundary without importing the V2 gate."""

    if not isinstance(value, dict):
        raise SchemaValidationError(f"{location}: object required")
    unknown = set(value) - MANIFEST_REQUIRED_FIELDS
    missing = MANIFEST_REQUIRED_FIELDS - set(value)
    if unknown or missing:
        raise SchemaValidationError(
            f"{location} fields differ; missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    if value["schema_version"] != "2.0":
        raise SchemaValidationError(f"{location}.schema_version: unsupported version")
    _require_manifest_string(value["candidate_version"], "candidate_version", location)
    candidate = _require_manifest_sha(value["candidate_commit"], "candidate_commit", location, _MANIFEST_SHA1)
    trusted_candidate = None
    if expected_candidate is not None:
        trusted_candidate = _require_manifest_sha(expected_candidate, "expected_candidate", location, _LOWER_SHA1).casefold()
    if trusted_candidate is not None and candidate.casefold() != trusted_candidate:
        raise SchemaValidationError(f"{location}.candidate_commit: differs from trusted candidate")
    frozen = _manifest_time(value["candidate_frozen_at"], "candidate_frozen_at", location)
    closed = _manifest_time(value["registry_closed_at"], "registry_closed_at", location)
    if closed <= frozen:
        raise SchemaValidationError(f"{location}.registry_closed_at: must be after candidate_frozen_at")
    _require_manifest_string(value["source_registry"], "source_registry", location)
    _require_manifest_sha(value["source_registry_sha256"], "source_registry_sha256", location, _MANIFEST_SHA256)
    required_count = value["required_comparable_tasks"]
    if isinstance(required_count, bool) or not isinstance(required_count, int) or required_count < 5:
        raise SchemaValidationError(f"{location}.required_comparable_tasks: integer of at least 5 required")

    sources = value["sources"]
    if not isinstance(sources, list) or not sources:
        raise SchemaValidationError(f"{location}.sources: non-empty array required")
    source_ids: set[str] = set()
    project_ids: set[str] = set()
    source_project_ids: dict[str, str] = {}
    for index, source in enumerate(sources):
        source_location = f"{location}.sources[{index}]"
        if not isinstance(source, dict):
            raise SchemaValidationError(f"{source_location}: object required")
        source_unknown = set(source) - MANIFEST_SOURCE_FIELDS
        source_missing = MANIFEST_SOURCE_FIELDS - set(source)
        if source_unknown or source_missing:
            raise SchemaValidationError(
                f"{source_location} fields differ; missing={sorted(source_missing)}, unknown={sorted(source_unknown)}"
            )
        source_id = _require_manifest_string(source["source_id"], "source_id", source_location)
        project_id = _require_manifest_string(source["project_evidence_id"], "project_evidence_id", source_location)
        if source_id in source_ids:
            raise SchemaValidationError(f"{source_location}.source_id: duplicate source_id")
        if project_id in project_ids:
            raise SchemaValidationError(f"{source_location}.project_evidence_id: duplicate project evidence identity")
        source_ids.add(source_id)
        project_ids.add(project_id)
        source_project_ids[source_id] = project_id
        for field in ("project_alias", "project_repo", "stable_branch", "ledger"):
            text = _require_manifest_string(source[field], field, source_location)
            if field == "stable_branch" and not _SAFE_REF.fullmatch(text):
                raise SchemaValidationError(f"{source_location}.stable_branch: unsafe Git ref")
        prefix_bytes = source["ledger_prefix_bytes"]
        if isinstance(prefix_bytes, bool) or not isinstance(prefix_bytes, int) or prefix_bytes < 0:
            raise SchemaValidationError(f"{source_location}.ledger_prefix_bytes: non-negative integer required")
        _require_manifest_sha(source["ledger_prefix_sha256"], "ledger_prefix_sha256", source_location, _MANIFEST_SHA256)
        _require_manifest_sha(source["ledger_sha256"], "ledger_sha256", source_location, _MANIFEST_SHA256)

    trials = value["trials"]
    if not isinstance(trials, list):
        raise SchemaValidationError(f"{location}.trials: array required")
    trial_ids: set[str] = set()
    identities: set[tuple[str, str, str]] = set()
    registration_sequences: set[int] = set()
    request_digests: set[str] = set()
    acceptance_digests: set[str] = set()
    for index, trial in enumerate(trials):
        trial_location = f"{location}.trials[{index}]"
        if not isinstance(trial, dict):
            raise SchemaValidationError(f"{trial_location}: object required")
        trial_unknown = set(trial) - MANIFEST_TRIAL_FIELDS
        trial_missing = MANIFEST_REQUIRED_TRIAL_FIELDS - set(trial)
        if trial_unknown or trial_missing:
            raise SchemaValidationError(
                f"{trial_location} fields differ; missing={sorted(trial_missing)}, unknown={sorted(trial_unknown)}"
            )
        for field in (
            "trial_id",
            "source_id",
            "task_id",
            "request_evidence",
            "request_evidence_sha256",
            "disposition",
        ):
            _require_manifest_string(trial[field], field, trial_location)
        trial_id = trial["trial_id"]
        if trial_id in trial_ids:
            raise SchemaValidationError(f"{trial_location}.trial_id: duplicate trial_id")
        trial_ids.add(trial_id)
        source_id = trial["source_id"]
        if source_id not in source_ids:
            raise SchemaValidationError(f"{trial_location}.source_id: source is not declared")
        identity = (candidate.casefold(), source_project_ids[source_id], trial["task_id"])
        if identity in identities:
            raise SchemaValidationError(f"{trial_location}: duplicate trial task identity")
        identities.add(identity)
        sequence = _require_int(trial["registration_sequence"], "registration_sequence", trial_location, positive=True)
        if sequence in registration_sequences:
            raise SchemaValidationError(f"{trial_location}.registration_sequence: duplicate sequence")
        registration_sequences.add(sequence)
        skill_candidate = _require_manifest_sha(
            trial["skill_candidate_commit"], "skill_candidate_commit", trial_location, _MANIFEST_SHA1
        )
        if skill_candidate.casefold() != candidate.casefold():
            raise SchemaValidationError(f"{trial_location}.skill_candidate_commit: differs from candidate")
        request_digest = _require_manifest_sha(
            trial["request_evidence_sha256"], "request_evidence_sha256", trial_location, _MANIFEST_SHA256
        ).casefold()
        if request_digest in request_digests:
            raise SchemaValidationError(f"{trial_location}.request_evidence_sha256: duplicate digest")
        request_digests.add(request_digest)
        for field in {"comparable", "genuine_request", "synthetic"} | MANIFEST_QUALITY_FIELDS:
            if not isinstance(trial[field], bool):
                raise SchemaValidationError(f"{trial_location}.{field}: boolean required")
        if trial["disposition"] not in MANIFEST_DISPOSITIONS:
            raise SchemaValidationError(f"{trial_location}.disposition: invalid disposition")
        if trial["comparable"]:
            _require_manifest_string(trial["v1_baseline_id"], "v1_baseline_id", trial_location)
            stratum = _require_manifest_string(trial["v1_baseline_stratum"], "v1_baseline_stratum", trial_location)
            if not re.fullmatch(r"^C[0-3]\|R[0-3]\|(no-delegation|single-worker|task-cell|team-required)$", stratum):
                raise SchemaValidationError(f"{trial_location}.v1_baseline_stratum: invalid stratum")
        else:
            if trial["v1_baseline_id"] is not None or trial["v1_baseline_stratum"] is not None:
                raise SchemaValidationError(f"{trial_location}: non-comparable baseline fields must be null")
            _require_manifest_string(trial.get("exclusion_reason"), "exclusion_reason", trial_location)

        if trial["disposition"] == "accepted":
            accepted_missing = MANIFEST_ACCEPTED_FIELDS - set(trial)
            if accepted_missing:
                raise SchemaValidationError(f"{trial_location}: accepted fields missing {sorted(accepted_missing)}")
            _require_manifest_sha(trial["candidate_commit"], "candidate_commit", trial_location, _MANIFEST_SHA1)
            _require_manifest_sha(trial["stable_commit"], "stable_commit", trial_location, _MANIFEST_SHA1)
            if trusted_candidate is not None and trial["candidate_commit"].casefold() != trusted_candidate:
                raise SchemaValidationError(f"{trial_location}.candidate_commit: differs from trusted candidate")
            _require_manifest_string(trial["acceptance_evidence"], "acceptance_evidence", trial_location)
            acceptance_digest = _require_manifest_sha(
                trial["acceptance_evidence_sha256"], "acceptance_evidence_sha256", trial_location, _MANIFEST_SHA256
            ).casefold()
            _validate_integration_proof_local(trial["integration_proof"], f"{trial_location}.integration_proof")
            if acceptance_digest in acceptance_digests:
                raise SchemaValidationError(f"{trial_location}.acceptance_evidence_sha256: duplicate digest")
            acceptance_digests.add(acceptance_digest)
        elif p2_overlay:
            # The P2 overlay retains an outcome artifact for every disposition;
            # candidate/stable/integration fields remain accepted-only fields.
            forbidden = {"candidate_commit", "stable_commit", "integration_proof"} & set(trial)
            if forbidden:
                raise SchemaValidationError(f"{trial_location}: non-accepted trial has accepted-only fields {sorted(forbidden)}")
            if "acceptance_evidence" not in trial or "acceptance_evidence_sha256" not in trial:
                raise SchemaValidationError(f"{trial_location}: P2 outcome evidence is required for every disposition")
            _require_manifest_string(trial["acceptance_evidence"], "acceptance_evidence", trial_location)
            acceptance_digest = _require_manifest_sha(
                trial["acceptance_evidence_sha256"], "acceptance_evidence_sha256", trial_location, _MANIFEST_SHA256
            ).casefold()
            if acceptance_digest in acceptance_digests:
                raise SchemaValidationError(f"{trial_location}.acceptance_evidence_sha256: duplicate digest")
            acceptance_digests.add(acceptance_digest)
        elif set(trial) & MANIFEST_ACCEPTED_FIELDS:
            raise SchemaValidationError(f"{trial_location}: non-accepted trial has acceptance-only fields")

        if "notes" in trial:
            notes = trial["notes"]
            if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
                raise SchemaValidationError(f"{trial_location}.notes: string array required")
    return value


def _load_single_object(source: Any, label: str) -> dict[str, Any] | None:
    documents = _load_documents(source, label)
    if len(documents) != 1 or not isinstance(documents[0][1], dict):
        raise P2PregateError(f"{label}: exactly one JSON object is required")
    return documents[0][1]


def _validated_final_manifest(
    source: Any,
    expected_candidate: str | None,
    issues: list[dict[str, str]],
    *,
    p2_overlay: bool,
) -> dict[str, Any] | None:
    if source is None:
        _add_issue(issues, "manifest_missing", "final private trial Manifest is required")
        return None
    try:
        value = _load_single_object(source, "final_manifest")
        return _validate_manifest_object(
            value,
            expected_candidate,
            "final_manifest",
            p2_overlay=p2_overlay,
        )
    except P2PregateError as exc:
        _add_issue(issues, "manifest_invalid", str(exc))
        return None


def _validate_final_manifest(source: Any, expected_candidate: str | None, issues: list[dict[str, str]]) -> bool:
    """Compatibility wrapper for strict base Manifest validation."""

    return _validated_final_manifest(source, expected_candidate, issues, p2_overlay=False) is not None


def _verify_manifest_alignment(
    final_manifest: Any,
    alignment_source: Any,
    expected_candidate: str | None,
    private_values: list[dict[str, Any]],
    issues: list[dict[str, str]],
    *,
    private_input_complete: bool,
    private_chain_ok: bool,
) -> bool:
    """Bind every Manifest trial to exactly one ready/outcome binding pair."""

    start = len(issues)
    manifest = _validated_final_manifest(
        final_manifest,
        expected_candidate,
        issues,
        p2_overlay=True,
    )
    if alignment_source is None:
        _add_issue(issues, "manifest_alignment_missing", "explicit Manifest alignment index is required")
        return False
    try:
        alignment = validate_manifest_alignment_index(
            _load_single_object(alignment_source, "manifest_alignment")
        )
    except P2PregateError as exc:
        _add_issue(issues, "manifest_alignment_invalid", str(exc))
        return False
    if manifest is None:
        return False
    if not private_input_complete:
        _add_issue(issues, "manifest_alignment_private_input_incomplete", "alignment cannot ignore invalid or non-canonical private input")
    if not private_chain_ok:
        _add_issue(issues, "manifest_alignment_private_chain_invalid", "alignment requires an integral private binding chain")
    if not manifest["trials"] or not alignment["tasks"]:
        _add_issue(issues, "manifest_alignment_empty", "Manifest and alignment must contain at least one task")
    if not any(binding["record_kind"] == "task_ready" for binding in private_values) or not any(
        binding["record_kind"] == "task_outcome" for binding in private_values
    ):
        _add_issue(issues, "manifest_alignment_no_task_pair", "alignment requires at least one task-ready/task-outcome pair")
    if expected_candidate is not None and alignment["candidate_commit"] != expected_candidate:
        _add_issue(issues, "manifest_alignment_candidate_mismatch", "alignment candidate differs from trusted candidate")
    if alignment["candidate_commit"] != manifest["candidate_commit"].casefold():
        _add_issue(issues, "manifest_alignment_candidate_mismatch", "alignment candidate differs from Manifest")

    trials = manifest["trials"]
    trial_by_task: dict[str, dict[str, Any]] = {}
    for trial in trials:
        task_id = trial["task_id"]
        if task_id in trial_by_task:
            _add_issue(issues, "manifest_alignment_task_duplicate", "Manifest task_id is ambiguous for alignment")
        trial_by_task[task_id] = trial
    alignment_by_task = {task["task_id"]: task for task in alignment["tasks"]}
    if set(alignment_by_task) != set(trial_by_task) or len(alignment_by_task) != len(trial_by_task):
        _add_issue(issues, "manifest_alignment_task_set_mismatch", "alignment tasks must equal Manifest trials one-to-one")

    ready_by_sequence: dict[int, dict[str, Any]] = {}
    outcome_by_sequence: dict[int, dict[str, Any]] = {}
    for binding in private_values:
        sequence = binding["sequence"]
        if binding["record_kind"] == "task_ready":
            if sequence in ready_by_sequence:
                _add_issue(issues, "manifest_alignment_ready_duplicate", "task_ready binding sequence is duplicated")
            ready_by_sequence[sequence] = binding
        elif binding["record_kind"] == "task_outcome":
            if sequence in outcome_by_sequence:
                _add_issue(issues, "manifest_alignment_outcome_duplicate", "task_outcome binding sequence is duplicated")
            outcome_by_sequence[sequence] = binding
    referenced_ready: set[int] = set()
    referenced_outcome: set[int] = set()
    for task_id, trial in trial_by_task.items():
        task = alignment_by_task.get(task_id)
        if task is None:
            continue
        ready_sequence = task["ready_binding_sequence"]
        outcome_sequence = task["outcome_binding_sequence"]
        referenced_ready.add(ready_sequence)
        referenced_outcome.add(outcome_sequence)
        ready = ready_by_sequence.get(ready_sequence)
        outcome = outcome_by_sequence.get(outcome_sequence)
        if ready is None:
            _add_issue(issues, "manifest_alignment_ready_missing", f"task {task_id} ready binding is missing")
        elif ready["private_object_sha256"].casefold() != trial["request_evidence_sha256"].casefold():
            _add_issue(issues, "manifest_alignment_request_digest_mismatch", f"task {task_id} request evidence digest differs")
        if outcome is None:
            _add_issue(issues, "manifest_alignment_outcome_missing", f"task {task_id} outcome binding is missing")
        elif outcome["private_object_sha256"].casefold() != trial["acceptance_evidence_sha256"].casefold():
            _add_issue(issues, "manifest_alignment_outcome_digest_mismatch", f"task {task_id} outcome evidence digest differs")
        if ready_sequence >= outcome_sequence:
            _add_issue(issues, "manifest_alignment_order_invalid", f"task {task_id} outcome does not follow ready")
    if referenced_ready != set(ready_by_sequence) or len(referenced_ready) != len(ready_by_sequence):
        _add_issue(issues, "manifest_alignment_ready_set_mismatch", "every task_ready binding must be used exactly once")
    if referenced_outcome != set(outcome_by_sequence) or len(referenced_outcome) != len(outcome_by_sequence):
        _add_issue(issues, "manifest_alignment_outcome_set_mismatch", "every task_outcome binding must be used exactly once")

    pending = 0
    for binding in private_values:
        if binding["record_kind"] == "task_ready":
            pending += 1
        elif binding["record_kind"] == "task_outcome":
            if pending == 0:
                _add_issue(issues, "manifest_alignment_prefix_invalid", "outcome appears without a pending ready binding")
            else:
                pending -= 1
        elif binding["record_kind"] == "window_closure" and pending:
            _add_issue(issues, "manifest_alignment_prefix_invalid", "closure has pending task-ready bindings")
    if pending:
        _add_issue(issues, "manifest_alignment_prefix_invalid", "bindings end with pending task-ready records")
    return len(issues) == start


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
    public_anchor_manifest: Any = None,
    final_manifest: Any = None,
    manifest_alignment_index: Any = None,
    recovery_inventory: Any = None,
    expected_candidate_commit: str | None = None,
) -> dict[str, Any]:
    """Evaluate local P2 inputs and return stable machine-readable status.

    ``eligible_for_v2_release_gate`` is intentionally false for every invocation
    in this implementation because no Owner-approved P3 cryptographic adapter is
    present.  The function never imports or executes the existing release gate.
    """

    issues: list[dict[str, str]] = []
    expected_candidate_valid = _is_valid_expected_candidate(expected_candidate_commit)
    if not expected_candidate_valid:
        _add_issue(issues, "expected_candidate_invalid", "expected_candidate_commit must be a full lowercase SHA-1 string")
        _add_issue(issues, "manifest_invalid", "expected_candidate_commit: invalid full lowercase SHA-1")
    try:
        salt = _salt_bytes(window_salt)
    except P2PregateError as exc:
        salt = None
        _add_issue(issues, "salt_invalid", str(exc))
    private_load_ok = private_bindings is not None
    try:
        private_docs = _load_documents(private_bindings, "private_bindings")
    except P2PregateError as exc:
        private_docs = []
        private_load_ok = False
        _add_issue(issues, "private_binding_missing", str(exc))
    public_load_ok = public_envelopes is not None
    try:
        public_docs = _load_documents(public_envelopes, "public_envelopes")
    except P2PregateError as exc:
        public_docs = []
        public_load_ok = False
        _add_issue(issues, "public_envelope_missing", str(exc))
    private_values, private_validation_complete = _validate_private_documents(private_docs, issues)
    public_values, public_raw_values, public_validation_complete = _validate_public_documents(public_docs, issues)
    private_input_complete = private_load_ok and private_validation_complete and len(private_values) == len(private_docs)
    public_input_complete = public_load_ok and public_validation_complete and len(public_values) == len(public_docs)
    if not private_input_complete:
        _add_issue(issues, "private_input_incomplete", "invalid private bindings cannot be dropped or repaired")
    if not public_input_complete:
        _add_issue(issues, "public_input_incomplete", "invalid public envelopes cannot be dropped or repaired")
    private_chain_ok, window_id, candidate_commit, _private_hashes = _private_chain(
        private_values, issues, input_complete=private_input_complete
    )
    public_chain_ok, _opaque_window, public_hashes = _public_chain(
        public_values, issues, input_complete=public_input_complete
    )
    if not expected_candidate_valid:
        _add_issue(issues, "candidate_mismatch", "private binding candidate differs from trusted candidate")
        private_chain_ok = False
    elif expected_candidate_commit is not None and candidate_commit != expected_candidate_commit:
        _add_issue(issues, "candidate_mismatch", "private binding candidate differs from trusted candidate")
        private_chain_ok = False

    private_anchor_ok = _verify_git_chain(
        private_anchor_repo,
        private_freeze_commit,
        private_head_commit,
        issues,
        "private",
    )
    private_event_anchor_ok = _verify_private_binding_anchors(
        private_anchor_repo,
        private_freeze_commit,
        private_head_commit,
        private_values,
        issues,
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
    private_commitments_ok = False
    if salt is not None and window_id is not None:
        private_commitments_ok = True
        expected_opaque = opaque_window_id(window_id, salt)
        for value in public_values:
            if value["opaque_window_id"] != expected_opaque:
                _add_issue(issues, "opaque_window_mismatch", "public opaque window does not bind the private window")
                public_chain_ok = False
                private_commitments_ok = False
                break
        if len(private_values) != len(public_values):
            _add_issue(issues, "receipt_count_mismatch", "private and public chains have different record counts")
            public_chain_ok = False
            private_commitments_ok = False
        by_sequence = {value["sequence"]: value for value in private_values}
        for envelope in public_values:
            binding = by_sequence.get(envelope["sequence"])
            if binding is None or commitment_sha256(binding, salt) != envelope["commitment_sha256"]:
                _add_issue(issues, "commitment_mismatch", "public commitment does not bind private bytes")
                public_chain_ok = False
                private_commitments_ok = False
                break
    public_content_mapping_proven = _verify_public_anchor_manifest(
        public_anchor_repo,
        public_anchor_manifest,
        public_values,
        public_raw_values,
        public_freeze_commit,
        public_head_commit,
        issues,
        public_input_complete=public_input_complete,
        public_chain_ok=public_chain_ok,
        public_git_chain_ok=public_anchor_ok,
        private_chain_ok=private_chain_ok,
        private_commitments_ok=private_commitments_ok,
    )
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
    _validate_recovery_inventory(recovery_inventory, issues)

    alignment_expected_candidate = expected_candidate_commit if expected_candidate_commit is not None else candidate_commit
    manifest_alignment_proven = _verify_manifest_alignment(
        final_manifest,
        manifest_alignment_index,
        alignment_expected_candidate,
        private_values,
        issues,
        private_input_complete=private_input_complete,
        private_chain_ok=private_chain_ok,
    )
    if not manifest_alignment_proven:
        _add_issue(
            issues,
            "manifest_alignment_unproven",
            "Manifest outcomes and private ready/outcome bindings are not one-to-one aligned",
        )

    issues.sort(key=lambda item: item["code"])
    return {
        "schema_version": SCHEMA_VERSION,
        "control_profile": CONTROL_PROFILE,
        "canonicalization_profile": PROFILE,
        "private_anchor_integral": bool(private_chain_ok and private_anchor_ok and private_event_anchor_ok),
        "public_chain_integral": bool(public_chain_ok and public_anchor_ok and public_content_mapping_proven),
        "public_control_proven": False,
        "public_content_mapping_proven": public_content_mapping_proven,
        "external_receipts_integral": False,
        "pre_outcome_order_proven": False,
        "privacy_allowlist_passed": privacy_allowlist_ok,
        "recovery_demonstrated": False,
        "manifest_alignment_proven": manifest_alignment_proven,
        "eligible_for_v2_release_gate": False,
        "trusted_private_freeze_commit": private_freeze_commit if private_anchor_ok and private_event_anchor_ok else None,
        "trusted_private_head_commit": private_head_commit if private_anchor_ok and private_event_anchor_ok else None,
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
    parser.add_argument("--public-anchor-manifest")
    parser.add_argument("--final-manifest")
    parser.add_argument("--manifest-alignment-index")
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
        public_anchor_manifest=args.public_anchor_manifest,
        final_manifest=args.final_manifest,
        manifest_alignment_index=args.manifest_alignment_index,
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
