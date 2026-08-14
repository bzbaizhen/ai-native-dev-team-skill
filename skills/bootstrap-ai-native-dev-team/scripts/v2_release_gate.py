#!/usr/bin/env python3
"""Evaluate the preregistered, source-complete gate for stable V2.0."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import team_metrics  # noqa: E402


FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
FULL_CANDIDATE_REF = re.compile(r"^refs/(?:heads|tags)/.+$")
STRATUM = re.compile(
    r"^(C[0-3])\|(R[0-3])\|(no-delegation|single-worker|task-cell|team-required)$"
)
SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
BASELINE_SOURCE_KINDS = {
    "task_contract",
    "qa_report",
    "acceptance_record",
    "git_record",
    "metrics_record",
}
BASELINE_SOURCE_CLAIMS = {
    "task_identity",
    "stratum",
    "acceptance",
    "efficiency_denominator",
}
CLAIM_ALLOWED_KINDS = {
    "task_identity": BASELINE_SOURCE_KINDS,
    "stratum": {"task_contract"},
    "acceptance": {"qa_report", "acceptance_record", "git_record"},
    "efficiency_denominator": {"metrics_record"},
}
ANCHOR_REGISTRY_PATH = "release-source-registry.json"
ANCHOR_RECEIPTS_DIR = "registrations"
ANCHOR_CLOSURE_PATH = "release-window-closure.json"
ANCHOR_REGISTRY_FIELDS = {
    "schema_version",
    "candidate_commit",
    "candidate_frozen_at",
    "required_comparable_tasks",
    "v1_baselines",
    "sources",
}
ANCHOR_BASELINE_FIELDS = {
    "baseline_id",
    "stratum_id",
    "evidence_path",
    "evidence_sha256",
    "stable_release_comparable",
    "formal_efficiency_comparable",
}
ANCHOR_RECEIPT_FIELDS = {
    "schema_version",
    "receipt_type",
    "registration_sequence",
    "source_id",
    "project_evidence_id",
    "task_id",
    "registered_at",
    "skill_candidate_commit",
    "request_evidence",
    "request_evidence_sha256",
    "complexity",
    "risk",
    "topology",
    "release_trial_comparable",
    "v1_baseline_id",
    "v1_baseline_stratum",
    "genuine_request",
    "synthetic",
}
ANCHOR_CLOSURE_FIELDS = {
    "schema_version",
    "closure_type",
    "candidate_commit",
    "anchor_freeze_commit",
    "final_registration_commit",
    "closed_at",
    "registration_count",
    "trial_manifest_sha256",
}
REQUIRED_TRIAL_FIELDS = {
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
MANIFEST_FIELDS = {
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
REQUIRED_SOURCE_FIELDS = {
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
SOURCE_FIELDS = REQUIRED_SOURCE_FIELDS
ACCEPTED_ONLY_FIELDS = {
    "candidate_commit",
    "stable_commit",
    "acceptance_evidence",
    "acceptance_evidence_sha256",
    "integration_proof",
}
TRIAL_FIELDS = REQUIRED_TRIAL_FIELDS | ACCEPTED_ONLY_FIELDS | {
    "exclusion_reason",
    "notes",
}
DISPOSITIONS = {"accepted", "in_progress", "blocked", "cancelled", "rejected"}
QUALITY_FIELDS = {
    "critical_defect_escape",
    "material_quality_regression",
    "scope_violation",
    "write_conflict",
    "recovery_executable",
}
SAME_COMMIT_PROOF_FIELDS = {"mode"}
SAME_TREE_PROOF_FIELDS = {
    "mode",
    "candidate_ref",
    "candidate_tree",
    "stable_tree",
    "tree_scope",
}
TREE_SCOPE_FIELDS = {"history_sensitive", "non_tree_dependencies"}
INTEGRATION_MODES = {"same_commit", "same_tree"}


class ReleaseGateError(ValueError):
    pass


def require_non_empty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseGateError(f"{label} must be a non-empty string")
    return value


def require_full_sha(value: Any, label: str) -> str:
    value = require_non_empty(value, label)
    if not FULL_SHA.fullmatch(value):
        raise ReleaseGateError(f"{label} must be a full 40-character SHA")
    return value


def require_sha256(value: Any, label: str) -> str:
    value = require_non_empty(value, label)
    if not SHA256.fullmatch(value):
        raise ReleaseGateError(f"{label} must be a SHA-256 digest")
    return value


def require_no_ascii_controls(value: str, label: str) -> str:
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ReleaseGateError(f"{label} contains ASCII control characters")
    return value


def require_candidate_ref_shape(value: Any, label: str) -> str:
    value = require_non_empty(value, label)
    require_no_ascii_controls(value, label)
    if not FULL_CANDIDATE_REF.fullmatch(value) or any(
        token in value for token in ("^", "~", "@{")
    ):
        raise ReleaseGateError(
            f"{label} must be a full refs/heads/* or refs/tags/* ref"
        )
    return value


def validate_tree_scope(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != TREE_SCOPE_FIELDS:
        raise ReleaseGateError(f"{label} fields differ from the contract")
    if not isinstance(value["history_sensitive"], bool):
        raise ReleaseGateError(f"{label}.history_sensitive must be boolean")
    if value["history_sensitive"]:
        raise ReleaseGateError(
            f"{label}.history_sensitive must be false for same_tree"
        )
    dependencies = value["non_tree_dependencies"]
    if not isinstance(dependencies, list) or any(
        not isinstance(item, str) for item in dependencies
    ):
        raise ReleaseGateError(
            f"{label}.non_tree_dependencies must be a string array"
        )
    if dependencies:
        raise ReleaseGateError(
            f"{label}.non_tree_dependencies must be empty for same_tree"
        )
    return value


def validate_integration_proof(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReleaseGateError(f"{label} must be an object")
    mode = value.get("mode")
    if not isinstance(mode, str) or mode not in INTEGRATION_MODES:
        raise ReleaseGateError(f"{label}.mode is invalid")
    if mode == "same_commit":
        if set(value) != SAME_COMMIT_PROOF_FIELDS:
            raise ReleaseGateError(
                f"{label} same_commit fields must contain only mode"
            )
        return value
    if set(value) != SAME_TREE_PROOF_FIELDS:
        raise ReleaseGateError(f"{label} same_tree fields differ from the contract")
    require_candidate_ref_shape(value.get("candidate_ref"), f"{label}.candidate_ref")
    require_full_sha(value.get("candidate_tree"), f"{label}.candidate_tree")
    require_full_sha(value.get("stable_tree"), f"{label}.stable_tree")
    validate_tree_scope(value.get("tree_scope"), f"{label}.tree_scope")
    return value


def manifest_time(value: Any, label: str) -> datetime:
    require_non_empty(value, label)
    try:
        return team_metrics.parse_time(value)
    except team_metrics.LedgerError as exc:
        raise ReleaseGateError(f"{label} must be an RFC 3339 date-time") from exc


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseGateError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ReleaseGateError("manifest must be a JSON object")
    unknown = set(data) - MANIFEST_FIELDS
    if unknown:
        raise ReleaseGateError(f"manifest contains unknown fields: {sorted(unknown)}")
    missing = MANIFEST_FIELDS - data.keys()
    if missing:
        raise ReleaseGateError(f"manifest missing fields: {sorted(missing)}")
    if data["schema_version"] != "2.0":
        raise ReleaseGateError("manifest schema_version must be 2.0")
    require_non_empty(data["candidate_version"], "candidate_version")
    require_full_sha(data["candidate_commit"], "candidate_commit")
    if manifest_time(data["registry_closed_at"], "registry_closed_at") <= manifest_time(
        data["candidate_frozen_at"], "candidate_frozen_at"
    ):
        raise ReleaseGateError("registry_closed_at must be after candidate_frozen_at")
    require_non_empty(data["source_registry"], "source_registry")
    require_sha256(data["source_registry_sha256"], "source_registry_sha256")
    required_count = data["required_comparable_tasks"]
    if isinstance(required_count, bool) or not isinstance(required_count, int) or required_count < 5:
        raise ReleaseGateError("required_comparable_tasks must be an integer of at least 5")
    if not isinstance(data["sources"], list) or not data["sources"]:
        raise ReleaseGateError("sources must be a non-empty array")
    if not isinstance(data["trials"], list):
        raise ReleaseGateError("trials must be an array")

    source_ids: set[str] = set()
    project_ids: set[str] = set()
    for index, source in enumerate(data["sources"]):
        label = f"sources[{index}]"
        if not isinstance(source, dict):
            raise ReleaseGateError(f"{label} must be an object")
        unknown_source = set(source) - SOURCE_FIELDS
        missing_source = REQUIRED_SOURCE_FIELDS - source.keys()
        if unknown_source or missing_source:
            raise ReleaseGateError(
                f"{label} fields invalid; missing={sorted(missing_source)}, "
                f"unknown={sorted(unknown_source)}"
            )
        for field in REQUIRED_SOURCE_FIELDS - {
            "ledger_prefix_bytes",
            "ledger_prefix_sha256",
            "ledger_sha256",
        }:
            require_non_empty(source[field], f"{label}.{field}")
        if source["source_id"] in source_ids:
            raise ReleaseGateError(f"duplicate source_id: {source['source_id']}")
        source_ids.add(source["source_id"])
        if source["project_evidence_id"] in project_ids:
            raise ReleaseGateError(
                f"duplicate project_evidence_id: {source['project_evidence_id']}"
            )
        project_ids.add(source["project_evidence_id"])
        stable_branch = require_non_empty(
            source["stable_branch"], f"{label}.stable_branch"
        )
        if not SAFE_REF.fullmatch(stable_branch):
            raise ReleaseGateError(f"{label}.stable_branch is not a safe Git ref")
        prefix_bytes = source["ledger_prefix_bytes"]
        if (
            isinstance(prefix_bytes, bool)
            or not isinstance(prefix_bytes, int)
            or prefix_bytes < 0
        ):
            raise ReleaseGateError(f"{label}.ledger_prefix_bytes must be non-negative")
        require_sha256(source["ledger_prefix_sha256"], f"{label}.ledger_prefix_sha256")
        require_sha256(source["ledger_sha256"], f"{label}.ledger_sha256")

    source_project_ids = {
        source["source_id"]: source["project_evidence_id"] for source in data["sources"]
    }
    trial_ids: set[str] = set()
    identities: set[tuple[str, str, str]] = set()
    sequences: set[int] = set()
    request_digests: set[str] = set()
    acceptance_digests: set[str] = set()
    for index, trial in enumerate(data["trials"]):
        label = f"trials[{index}]"
        if not isinstance(trial, dict):
            raise ReleaseGateError(f"{label} must be an object")
        unknown_trial = set(trial) - TRIAL_FIELDS
        missing_trial = REQUIRED_TRIAL_FIELDS - trial.keys()
        if unknown_trial or missing_trial:
            raise ReleaseGateError(
                f"{label} fields invalid; missing={sorted(missing_trial)}, "
                f"unknown={sorted(unknown_trial)}"
            )
        for field in (
            "trial_id",
            "source_id",
            "task_id",
            "skill_candidate_commit",
            "request_evidence",
            "request_evidence_sha256",
            "disposition",
        ):
            require_non_empty(trial[field], f"{label}.{field}")
        if trial["trial_id"] in trial_ids:
            raise ReleaseGateError(f"duplicate trial_id: {trial['trial_id']}")
        trial_ids.add(trial["trial_id"])
        if trial["source_id"] not in source_ids:
            raise ReleaseGateError(f"{label}.source_id is not declared in sources")
        identity = (
            data["candidate_commit"].casefold(),
            source_project_ids[trial["source_id"]],
            trial["task_id"],
        )
        if identity in identities:
            raise ReleaseGateError(
                f"duplicate trial task identity: ({trial['source_id']}, {trial['task_id']})"
            )
        identities.add(identity)
        sequence = trial["registration_sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ReleaseGateError(f"{label}.registration_sequence must be positive")
        if sequence in sequences:
            raise ReleaseGateError(f"duplicate registration_sequence: {sequence}")
        sequences.add(sequence)
        require_full_sha(
            trial["skill_candidate_commit"], f"{label}.skill_candidate_commit"
        )
        require_sha256(
            trial["request_evidence_sha256"], f"{label}.request_evidence_sha256"
        )
        request_digest = trial["request_evidence_sha256"].casefold()
        if request_digest in request_digests:
            raise ReleaseGateError(f"duplicate request evidence digest: {request_digest}")
        request_digests.add(request_digest)
        for field in {"comparable", "genuine_request", "synthetic"} | QUALITY_FIELDS:
            if not isinstance(trial[field], bool):
                raise ReleaseGateError(f"{label}.{field} must be boolean")
        if trial["disposition"] not in DISPOSITIONS:
            raise ReleaseGateError(f"{label}.disposition is invalid")
        if trial["comparable"]:
            require_non_empty(trial["v1_baseline_id"], f"{label}.v1_baseline_id")
            require_non_empty(trial["v1_baseline_stratum"], f"{label}.v1_baseline_stratum")
        else:
            if trial["v1_baseline_id"] is not None:
                raise ReleaseGateError(
                    f"{label}.v1_baseline_id must be null when non-comparable"
                )
            if trial["v1_baseline_stratum"] is not None:
                raise ReleaseGateError(
                    f"{label}.v1_baseline_stratum must be null when non-comparable"
                )
            require_non_empty(trial.get("exclusion_reason"), f"{label}.exclusion_reason")
        if trial["disposition"] == "accepted":
            missing_accepted = ACCEPTED_ONLY_FIELDS - trial.keys()
            if missing_accepted:
                raise ReleaseGateError(
                    f"{label} accepted disposition missing {sorted(missing_accepted)}"
                )
            for field in ("candidate_commit", "stable_commit"):
                require_full_sha(trial[field], f"{label}.{field}")
            require_non_empty(trial["acceptance_evidence"], f"{label}.acceptance_evidence")
            require_sha256(
                trial["acceptance_evidence_sha256"],
                f"{label}.acceptance_evidence_sha256",
            )
            validate_integration_proof(
                trial["integration_proof"], f"{label}.integration_proof"
            )
            acceptance_digest = trial["acceptance_evidence_sha256"].casefold()
            if acceptance_digest in acceptance_digests:
                raise ReleaseGateError(
                    f"duplicate acceptance evidence digest: {acceptance_digest}"
                )
            acceptance_digests.add(acceptance_digest)
        elif set(trial) & ACCEPTED_ONLY_FIELDS:
            raise ReleaseGateError(f"{label} has acceptance-only fields before acceptance")
        if "notes" in trial and (
            not isinstance(trial["notes"], list)
            or any(not isinstance(note, str) for note in trial["notes"])
        ):
            raise ReleaseGateError(f"{label}.notes must be a string array")
    return data


def resolve_path(manifest_path: Path, raw: str) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()


def issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(repo), *args]
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, TypeError, ValueError) as exc:
        return subprocess.CompletedProcess(command, 127, stdout="", stderr=str(exc))


def git_commit_exists(repo: Path, commit: str) -> bool:
    if not isinstance(commit, str) or not FULL_SHA.fullmatch(commit):
        return False
    return run_git(repo, "cat-file", "-e", f"{commit}^{{commit}}").returncode == 0


def git_object_id(repo: Path, revision: str, object_type: str, label: str) -> str:
    if not isinstance(revision, str) or not FULL_SHA.fullmatch(revision):
        raise ReleaseGateError(f"{label} must be a full 40-character SHA")
    result = run_git(repo, "rev-parse", "--verify", f"{revision}^{{{object_type}}}")
    value = result.stdout.strip()
    if result.returncode != 0 or not FULL_SHA.fullmatch(value):
        detail = result.stderr.strip() or result.stdout.strip() or "Git object is absent"
        raise ReleaseGateError(f"{label} cannot be resolved: {detail}")
    return value.casefold()


def resolve_candidate_ref(
    repo: Path, raw_ref: Any, expected_commit: str, label: str
) -> str:
    ref = require_candidate_ref_shape(raw_ref, label)
    check = run_git(repo, "check-ref-format", ref)
    if check.returncode != 0:
        raise ReleaseGateError(f"{label} is not a valid Git ref")
    result = run_git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    target = result.stdout.strip()
    if result.returncode != 0 or not FULL_SHA.fullmatch(target):
        raise ReleaseGateError(f"{label} is missing or does not resolve to a Commit")
    if target.casefold() != expected_commit.casefold():
        raise ReleaseGateError(f"{label} does not resolve to candidate_commit")
    return target.casefold()


def resolve_stable_branch(repo: Path, raw_branch: Any, label: str) -> str:
    branch = require_non_empty(raw_branch, label)
    require_no_ascii_controls(branch, label)
    if branch == "HEAD" or FULL_SHA.fullmatch(branch):
        raise ReleaseGateError(f"{label} must identify a stable branch")
    if branch.startswith("refs/"):
        if not branch.startswith("refs/heads/"):
            raise ReleaseGateError(f"{label} must use the refs/heads namespace")
        ref = branch
        branch_name = branch.removeprefix("refs/heads/")
    else:
        ref = f"refs/heads/{branch}"
        branch_name = branch
    if not branch_name or any(token in branch_name for token in ("^", "~", "@{")):
        raise ReleaseGateError(f"{label} must identify a stable branch")
    check = run_git(repo, "check-ref-format", "--branch", branch_name)
    if check.returncode != 0:
        raise ReleaseGateError(f"{label} is not a valid Git branch")
    result = run_git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    target = result.stdout.strip()
    if result.returncode != 0 or not FULL_SHA.fullmatch(target):
        raise ReleaseGateError(f"{label} is missing or does not resolve to a Commit")
    return target.casefold()


def git_text(repo: Path, *args: str) -> str:
    result = run_git(repo, *args)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise ReleaseGateError(detail)
    return result.stdout


def git_blob_bytes(repo: Path, commit: str, path: str, label: str) -> bytes:
    command = ["git", "-C", str(repo), "show", f"{commit}:{path}"]
    try:
        result = subprocess.run(command, check=False, capture_output=True)
    except OSError as exc:
        raise ReleaseGateError(f"{label} cannot be read: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {detail}" if detail else ""
        raise ReleaseGateError(f"{label} cannot be read{suffix}")
    return result.stdout


def anchor_relative_path(raw: Any, label: str) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ReleaseGateError(f"{label} must be a normalized relative POSIX path")
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or not path.parts
        or raw != path.as_posix()
        or ".." in path.parts
    ):
        raise ReleaseGateError(f"{label} must be a normalized relative POSIX path")
    return raw


def validate_v1_baseline_evidence(
    raw: bytes, baseline: dict[str, Any], label: str
) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseGateError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ReleaseGateError(f"{label} must be a JSON object")
    required = {
        "schema_version",
        "baseline_id",
        "baseline_version",
        "measurement_type",
        "stratum_id",
        "evidence_scope",
        "efficiency_denominators_available",
        "source_evidence",
        "limitations",
    }
    if set(data) != required:
        raise ReleaseGateError(f"{label} fields differ from the contract")
    efficiency_available = data["efficiency_denominators_available"]
    if not isinstance(efficiency_available, bool):
        raise ReleaseGateError(
            f"{label}.efficiency_denominators_available must be boolean"
        )
    expected = {
        "schema_version": "1.0",
        "baseline_id": baseline["baseline_id"],
        "baseline_version": "v1.0.0",
        "measurement_type": "historical_reconstruction",
        "stratum_id": baseline["stratum_id"],
        "efficiency_denominators_available": baseline[
            "formal_efficiency_comparable"
        ],
    }
    for field, value in expected.items():
        if data.get(field) != value:
            raise ReleaseGateError(f"{label}.{field} differs from the frozen registry")
    evidence_scope = data["evidence_scope"]
    if not isinstance(evidence_scope, str) or evidence_scope not in {
        "case-level",
        "task-level",
    }:
        raise ReleaseGateError(f"{label}.evidence_scope is invalid")
    if (
        baseline["formal_efficiency_comparable"]
        and evidence_scope != "task-level"
    ):
        raise ReleaseGateError(
            f"{label} must be task-level for formal efficiency comparability"
        )
    sources = data["source_evidence"]
    if not isinstance(sources, list) or not sources:
        raise ReleaseGateError(f"{label}.source_evidence must be a non-empty array")
    source_fields = {
        "source_id",
        "evidence_kind",
        "source_revision",
        "evidence_path",
        "evidence_sha256",
        "supports",
    }
    source_ids: set[str] = set()
    source_paths: set[str] = set()
    covered_claims: set[str] = set()
    for index, source in enumerate(sources):
        source_label = f"{label}.source_evidence[{index}]"
        if not isinstance(source, dict) or set(source) != source_fields:
            raise ReleaseGateError(f"{source_label} fields differ from the contract")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id):
            raise ReleaseGateError(f"{source_label}.source_id is invalid")
        if source_id in source_ids:
            raise ReleaseGateError(f"{label} has duplicate source_evidence source_id")
        source_ids.add(source_id)
        kind = source.get("evidence_kind")
        if not isinstance(kind, str) or kind not in BASELINE_SOURCE_KINDS:
            raise ReleaseGateError(f"{source_label}.evidence_kind is invalid")
        revision = source.get("source_revision")
        if not isinstance(revision, str) or not FULL_SHA.fullmatch(revision):
            raise ReleaseGateError(
                f"{source_label}.source_revision must be a full SHA string"
            )
        path = anchor_relative_path(
            source.get("evidence_path"), f"{source_label}.evidence_path"
        )
        if path in source_paths:
            raise ReleaseGateError(f"{label} has duplicate source_evidence path")
        source_paths.add(path)
        digest = source.get("evidence_sha256")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ReleaseGateError(
                f"{source_label}.evidence_sha256 must be a SHA-256 string"
            )
        supports = source.get("supports")
        if (
            not isinstance(supports, list)
            or not supports
            or any(not isinstance(claim, str) for claim in supports)
            or len(supports) != len(set(supports))
            or any(claim not in BASELINE_SOURCE_CLAIMS for claim in supports)
        ):
            raise ReleaseGateError(f"{source_label}.supports is invalid")
        for claim in supports:
            if kind not in CLAIM_ALLOWED_KINDS[claim]:
                raise ReleaseGateError(
                    f"{source_label}.{kind} cannot support {claim}"
                )
        covered_claims.update(supports)
    required_claims = {"task_identity", "stratum", "acceptance"}
    if baseline["formal_efficiency_comparable"]:
        required_claims.add("efficiency_denominator")
    missing_claims = required_claims - covered_claims
    if missing_claims:
        raise ReleaseGateError(
            f"{label}.source_evidence is missing claims: {sorted(missing_claims)}"
        )
    limitations = data["limitations"]
    if not isinstance(limitations, list) or not limitations or any(
        not isinstance(item, str) or not item.strip() for item in limitations
    ):
        raise ReleaseGateError(f"{label}.limitations must be a non-empty string array")
    return data


def git_json(repo: Path, commit: str, path: str, label: str) -> dict[str, Any]:
    try:
        data = json.loads(git_text(repo, "show", f"{commit}:{path}"))
    except json.JSONDecodeError as exc:
        raise ReleaseGateError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ReleaseGateError(f"{label} must be a JSON object")
    return data


def validate_anchor_registry(data: dict[str, Any]) -> dict[str, Any]:
    if set(data) != ANCHOR_REGISTRY_FIELDS:
        raise ReleaseGateError("anchor source registry fields differ from the contract")
    if data.get("schema_version") != "2.0":
        raise ReleaseGateError("anchor source registry schema_version must be 2.0")
    require_full_sha(data.get("candidate_commit"), "anchor candidate_commit")
    manifest_time(data.get("candidate_frozen_at"), "anchor candidate_frozen_at")
    required = data.get("required_comparable_tasks")
    if isinstance(required, bool) or not isinstance(required, int) or required < 5:
        raise ReleaseGateError("anchor required_comparable_tasks must be at least 5")
    baselines = data.get("v1_baselines")
    if not isinstance(baselines, list) or not baselines:
        raise ReleaseGateError("anchor v1_baselines must be a non-empty array")
    baseline_ids: set[str] = set()
    evidence_paths: set[str] = set()
    for index, baseline in enumerate(baselines):
        label = f"anchor v1_baselines[{index}]"
        if not isinstance(baseline, dict) or set(baseline) != ANCHOR_BASELINE_FIELDS:
            raise ReleaseGateError(f"{label} fields differ from the contract")
        for field in ("baseline_id", "stratum_id", "evidence_path", "evidence_sha256"):
            require_non_empty(baseline.get(field), f"{label}.{field}")
        if baseline["baseline_id"] in baseline_ids:
            raise ReleaseGateError(f"duplicate anchor baseline_id: {baseline['baseline_id']}")
        baseline_ids.add(baseline["baseline_id"])
        if not STRATUM.fullmatch(baseline["stratum_id"]):
            raise ReleaseGateError(f"{label}.stratum_id is invalid")
        path = anchor_relative_path(baseline["evidence_path"], f"{label}.evidence_path")
        if path in evidence_paths:
            raise ReleaseGateError(f"duplicate anchor baseline evidence_path: {path}")
        evidence_paths.add(path)
        require_sha256(baseline["evidence_sha256"], f"{label}.evidence_sha256")
        for field in ("stable_release_comparable", "formal_efficiency_comparable"):
            if not isinstance(baseline[field], bool):
                raise ReleaseGateError(f"{label}.{field} must be boolean")
        if baseline["formal_efficiency_comparable"] and not baseline[
            "stable_release_comparable"
        ]:
            raise ReleaseGateError(
                f"{label} cannot support formal efficiency without stable comparability"
            )
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ReleaseGateError("anchor sources must be a non-empty array")
    frozen_fields = REQUIRED_SOURCE_FIELDS - {"ledger_sha256"}
    source_ids: set[str] = set()
    project_ids: set[str] = set()
    for index, source in enumerate(sources):
        label = f"anchor sources[{index}]"
        if not isinstance(source, dict) or set(source) != frozen_fields:
            raise ReleaseGateError(f"{label} fields differ from the contract")
        for field in frozen_fields - {"ledger_prefix_bytes", "ledger_prefix_sha256"}:
            require_non_empty(source.get(field), f"{label}.{field}")
        source_id = source["source_id"]
        project_id = source["project_evidence_id"]
        if source_id in source_ids:
            raise ReleaseGateError(f"duplicate anchor source_id: {source_id}")
        if project_id in project_ids:
            raise ReleaseGateError(f"duplicate anchor project_evidence_id: {project_id}")
        source_ids.add(source_id)
        project_ids.add(project_id)
        stable_branch = require_non_empty(
            source["stable_branch"], f"{label}.stable_branch"
        )
        if not SAFE_REF.fullmatch(stable_branch):
            raise ReleaseGateError(f"{label}.stable_branch is not a safe Git ref")
        prefix_bytes = source["ledger_prefix_bytes"]
        if (
            isinstance(prefix_bytes, bool)
            or not isinstance(prefix_bytes, int)
            or prefix_bytes < 0
        ):
            raise ReleaseGateError(f"{label}.ledger_prefix_bytes must be non-negative")
        require_sha256(
            source["ledger_prefix_sha256"], f"{label}.ledger_prefix_sha256"
        )
    return data


def validate_anchor_receipt(
    data: dict[str, Any],
    *,
    expected_sequence: int,
    registry_sources: dict[str, dict[str, Any]],
    registry_baselines: dict[str, dict[str, Any]],
    candidate_commit: str,
) -> dict[str, Any]:
    allowed = ANCHOR_RECEIPT_FIELDS | {"exclusion_reason"}
    if set(data) - allowed or ANCHOR_RECEIPT_FIELDS - data.keys():
        raise ReleaseGateError(
            f"registration {expected_sequence} fields differ from the contract"
        )
    if data.get("schema_version") != "2.0" or data.get("receipt_type") != (
        "task_ready_registration"
    ):
        raise ReleaseGateError(f"registration {expected_sequence} type is invalid")
    if data.get("registration_sequence") != expected_sequence:
        raise ReleaseGateError(f"registration {expected_sequence} sequence differs")
    for field in (
        "source_id",
        "project_evidence_id",
        "task_id",
        "registered_at",
        "skill_candidate_commit",
        "request_evidence",
        "request_evidence_sha256",
        "complexity",
        "risk",
        "topology",
    ):
        require_non_empty(data.get(field), f"registration {expected_sequence}.{field}")
    source = registry_sources.get(data["source_id"])
    if not source:
        raise ReleaseGateError(f"registration {expected_sequence} source is not frozen")
    if data["project_evidence_id"] != source["project_evidence_id"]:
        raise ReleaseGateError(f"registration {expected_sequence} project identity differs")
    skill_candidate_commit = require_full_sha(
        data["skill_candidate_commit"],
        f"registration {expected_sequence}.skill_candidate_commit",
    )
    if skill_candidate_commit.casefold() != candidate_commit.casefold():
        raise ReleaseGateError(f"registration {expected_sequence} candidate differs")
    require_sha256(
        data["request_evidence_sha256"],
        f"registration {expected_sequence}.request_evidence_sha256",
    )
    if data["complexity"] not in team_metrics.COMPLEXITIES:
        raise ReleaseGateError(f"registration {expected_sequence} complexity is invalid")
    if data["risk"] not in team_metrics.RISKS:
        raise ReleaseGateError(f"registration {expected_sequence} risk is invalid")
    if data["topology"] not in team_metrics.TOPOLOGIES:
        raise ReleaseGateError(f"registration {expected_sequence} topology is invalid")
    for field in ("release_trial_comparable", "genuine_request", "synthetic"):
        if not isinstance(data.get(field), bool):
            raise ReleaseGateError(f"registration {expected_sequence}.{field} must be boolean")
    expected_stratum = f"{data['complexity']}|{data['risk']}|{data['topology']}"
    if data["release_trial_comparable"]:
        baseline_id = data.get("v1_baseline_id")
        if not isinstance(baseline_id, str) or not baseline_id.strip():
            raise ReleaseGateError(f"registration {expected_sequence} baseline_id is invalid")
        baseline = registry_baselines.get(baseline_id)
        if not baseline:
            raise ReleaseGateError(
                f"registration {expected_sequence} V1 baseline is not frozen"
            )
        if not baseline["stable_release_comparable"]:
            raise ReleaseGateError(
                f"registration {expected_sequence} V1 baseline is not release-comparable"
            )
        if not isinstance(data.get("v1_baseline_stratum"), str) or not STRATUM.fullmatch(
            data["v1_baseline_stratum"]
        ):
            raise ReleaseGateError(f"registration {expected_sequence} stratum is invalid")
        if data["v1_baseline_stratum"] != expected_stratum:
            raise ReleaseGateError(
                f"registration {expected_sequence} stratum does not match C/R/topology"
            )
        if baseline["stratum_id"] != expected_stratum:
            raise ReleaseGateError(
                f"registration {expected_sequence} frozen V1 baseline stratum differs"
            )
        if "exclusion_reason" in data:
            raise ReleaseGateError(
                f"registration {expected_sequence} comparable work has exclusion_reason"
            )
    else:
        if data.get("v1_baseline_id") is not None:
            raise ReleaseGateError(
                f"registration {expected_sequence} non-comparable baseline_id must be null"
            )
        if data.get("v1_baseline_stratum") is not None:
            raise ReleaseGateError(
                f"registration {expected_sequence} non-comparable stratum must be null"
            )
        require_non_empty(
            data.get("exclusion_reason"),
            f"registration {expected_sequence}.exclusion_reason",
        )
    manifest_time(data["registered_at"], f"registration {expected_sequence}.registered_at")
    return data


def load_anchor(repo: Path, freeze_commit: str, head_commit: str) -> dict[str, Any]:
    repo = repo.resolve()
    require_full_sha(freeze_commit, "anchor_freeze_commit")
    require_full_sha(head_commit, "anchor_head_commit")
    root = git_text(repo, "rev-parse", "--show-toplevel").strip()
    if Path(root).resolve() != repo:
        raise ReleaseGateError("anchor_repo must be the Git root")
    freeze_commit = freeze_commit.casefold()
    head_commit = head_commit.casefold()
    if not git_commit_exists(repo, freeze_commit) or not git_commit_exists(repo, head_commit):
        raise ReleaseGateError("trusted anchor Commit is absent")
    if run_git(
        repo, "merge-base", "--is-ancestor", freeze_commit, head_commit
    ).returncode != 0:
        raise ReleaseGateError("anchor freeze Commit is not an ancestor of anchor head")

    first_parent = [
        line.strip().casefold()
        for line in git_text(
            repo,
            "rev-list",
            "--first-parent",
            "--reverse",
            f"{freeze_commit}..{head_commit}",
        ).splitlines()
        if line.strip()
    ]
    all_count = int(git_text(repo, "rev-list", "--count", f"{freeze_commit}..{head_commit}"))
    if not first_parent or len(first_parent) != all_count or first_parent[-1] != head_commit:
        raise ReleaseGateError("anchor history must be a closed linear first-parent chain")
    previous = freeze_commit
    for commit in first_parent:
        parents = git_text(repo, "show", "-s", "--format=%P", commit).split()
        if parents != [previous]:
            raise ReleaseGateError("anchor history contains a merge or discontinuity")
        previous = commit

    if git_text(
        repo, "ls-tree", "-r", "--name-only", freeze_commit, ANCHOR_RECEIPTS_DIR
    ).strip():
        raise ReleaseGateError("anchor freeze Commit already contains registrations")
    registry = validate_anchor_registry(
        git_json(repo, freeze_commit, ANCHOR_REGISTRY_PATH, "anchor source registry")
    )
    baseline_evidence: dict[str, dict[str, Any]] = {}
    for baseline in registry["v1_baselines"]:
        label = f"V1 baseline {baseline['baseline_id']}"
        raw = git_blob_bytes(repo, freeze_commit, baseline["evidence_path"], label)
        actual_digest = hashlib.sha256(raw).hexdigest()
        if actual_digest.casefold() != baseline["evidence_sha256"].casefold():
            raise ReleaseGateError(f"{label} evidence digest differs")
        evidence = validate_v1_baseline_evidence(raw, baseline, label)
        for source in evidence["source_evidence"]:
            source_label = f"{label} source {source['source_id']}"
            source_raw = git_blob_bytes(
                repo, freeze_commit, source["evidence_path"], source_label
            )
            source_digest = hashlib.sha256(source_raw).hexdigest()
            if source_digest.casefold() != source["evidence_sha256"].casefold():
                raise ReleaseGateError(f"{source_label} evidence digest differs")
        baseline_evidence[baseline["baseline_id"]] = evidence
    candidate_commit = registry["candidate_commit"]
    frozen = manifest_time(registry["candidate_frozen_at"], "anchor candidate_frozen_at")

    closure_changes = [
        line.split("\t", 1)
        for line in git_text(
            repo, "diff-tree", "--no-commit-id", "--name-status", "-r", head_commit
        ).splitlines()
        if line.strip()
    ]
    if closure_changes != [["A", ANCHOR_CLOSURE_PATH]]:
        raise ReleaseGateError("anchor head must add only the window closure")
    closure = git_json(repo, head_commit, ANCHOR_CLOSURE_PATH, "anchor closure")
    if set(closure) != ANCHOR_CLOSURE_FIELDS:
        raise ReleaseGateError("anchor closure fields differ from the contract")
    if closure.get("schema_version") != "2.0" or closure.get("closure_type") != (
        "registration_window_closed"
    ):
        raise ReleaseGateError("anchor closure type is invalid")
    closure_candidate = require_full_sha(
        closure.get("candidate_commit"), "anchor closure candidate_commit"
    )
    if closure_candidate.casefold() != candidate_commit.casefold():
        raise ReleaseGateError("anchor closure candidate differs")
    closure_freeze = require_full_sha(
        closure.get("anchor_freeze_commit"), "anchor closure anchor_freeze_commit"
    )
    if closure_freeze.casefold() != freeze_commit:
        raise ReleaseGateError("anchor closure freeze Commit differs")
    closed = manifest_time(closure.get("closed_at"), "anchor closed_at")
    if closed <= frozen:
        raise ReleaseGateError("anchor closed_at must be after candidate_frozen_at")

    registration_commits = first_parent[:-1]
    expected_final = registration_commits[-1] if registration_commits else freeze_commit
    final_registration = require_full_sha(
        closure.get("final_registration_commit"),
        "anchor closure final_registration_commit",
    )
    if final_registration.casefold() != expected_final:
        raise ReleaseGateError("anchor closure final registration Commit differs")
    count = closure.get("registration_count")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(
        registration_commits
    ):
        raise ReleaseGateError("anchor closure registration_count differs")
    require_sha256(
        closure.get("trial_manifest_sha256"),
        "anchor closure trial_manifest_sha256",
    )

    sources = {source["source_id"]: source for source in registry["sources"]}
    baselines = {
        baseline["baseline_id"]: baseline for baseline in registry["v1_baselines"]
    }
    receipts: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str]] = set()
    request_digests: set[str] = set()
    last_registered = frozen
    for sequence, commit in enumerate(registration_commits, 1):
        path = f"{ANCHOR_RECEIPTS_DIR}/{sequence:06d}.json"
        changes = [
            line.split("\t", 1)
            for line in git_text(
                repo, "diff-tree", "--no-commit-id", "--name-status", "-r", commit
            ).splitlines()
            if line.strip()
        ]
        if changes != [["A", path]]:
            raise ReleaseGateError(
                f"anchor registration Commit {sequence} must add only {path}"
            )
        receipt = validate_anchor_receipt(
            git_json(repo, commit, path, f"registration {sequence}"),
            expected_sequence=sequence,
            registry_sources=sources,
            registry_baselines=baselines,
            candidate_commit=candidate_commit,
        )
        registered = manifest_time(receipt["registered_at"], f"registration {sequence}")
        if not frozen < registered <= closed or registered < last_registered:
            raise ReleaseGateError(
                f"registration {sequence} time is outside or reorders the anchor window"
            )
        last_registered = registered
        identity = (
            candidate_commit.casefold(),
            receipt["project_evidence_id"],
            receipt["task_id"],
        )
        if identity in identities:
            raise ReleaseGateError(f"registration {sequence} duplicates a task identity")
        identities.add(identity)
        digest = receipt["request_evidence_sha256"].casefold()
        if digest in request_digests:
            raise ReleaseGateError(f"registration {sequence} duplicates request evidence")
        request_digests.add(digest)
        receipts.append(receipt | {"anchor_commit": commit, "anchor_path": path})
    return {
        "repo": str(repo),
        "freeze_commit": freeze_commit,
        "head_commit": head_commit,
        "registry": registry,
        "baseline_evidence": baseline_evidence,
        "closure": closure,
        "receipts": receipts,
        "passed": True,
    }


def load_source(source: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    ledger = resolve_path(manifest_path, source["ledger"])
    repo = resolve_path(manifest_path, source["project_repo"])
    events: list[dict[str, Any]] = []
    audit = {"passed": False, "violations": []}
    actual_hash: str | None = None
    repo_root: Path | None = None
    branch_commit: str | None = None
    try:
        ledger_bytes = ledger.read_bytes()
        actual_hash = hashlib.sha256(ledger_bytes).hexdigest()
        if actual_hash.casefold() != source["ledger_sha256"].casefold():
            issues.append(
                issue("ledger_digest_mismatch", "ledger does not match registered SHA-256")
            )
        prefix_bytes = source["ledger_prefix_bytes"]
        if len(ledger_bytes) < prefix_bytes:
            issues.append(issue("ledger_prefix_truncated", "ledger is shorter than frozen prefix"))
        elif hashlib.sha256(ledger_bytes[:prefix_bytes]).hexdigest().casefold() != source[
            "ledger_prefix_sha256"
        ].casefold():
            issues.append(
                issue("ledger_prefix_digest_mismatch", "frozen ledger prefix changed")
            )
        events = team_metrics.load_events(ledger)
        audit = team_metrics.audit_events(events)
    except (OSError, team_metrics.LedgerError) as exc:
        issues.append(issue("ledger_error", str(exc)))

    root_result = run_git(repo, "rev-parse", "--show-toplevel")
    if root_result.returncode != 0:
        issues.append(
            issue("project_repo_error", root_result.stderr.strip() or "not a Git repository")
        )
    else:
        repo_root = Path(root_result.stdout.strip()).resolve()
        if repo_root != repo:
            issues.append(issue("project_repo_not_root", "project_repo must be the Git root"))
        try:
            branch_commit = resolve_stable_branch(
                repo, source["stable_branch"], "stable_branch"
            )
        except ReleaseGateError as exc:
            issues.append(issue("stable_branch_error", str(exc)))
    return {
        "source_id": source["source_id"],
        "project_alias": source["project_alias"],
        "project_evidence_id": source["project_evidence_id"],
        "ledger": str(ledger),
        "ledger_prefix_bytes": source["ledger_prefix_bytes"],
        "ledger_prefix_sha256": source["ledger_prefix_sha256"],
        "ledger_sha256": actual_hash,
        "project_repo": str(repo),
        "repo_root": str(repo_root) if repo_root else None,
        "stable_branch": source["stable_branch"],
        "stable_branch_commit": branch_commit,
        "events": events,
        "audit": audit,
        "issues": issues,
        "integrity_passed": not issues,
    }


def validate_source_registry(
    manifest: dict[str, Any], manifest_path: Path, anchor: dict[str, Any]
) -> dict[str, Any]:
    path = resolve_path(manifest_path, manifest["source_registry"])
    issues: list[dict[str, str]] = []
    actual_hash: str | None = None
    try:
        actual_hash = file_sha256(path)
        if actual_hash.casefold() != manifest["source_registry_sha256"].casefold():
            issues.append(
                issue("source_registry_digest_mismatch", "source registry SHA-256 differs")
            )
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": str(path),
            "sha256": actual_hash,
            "issues": [issue("source_registry_error", str(exc))],
            "passed": False,
        }
    if not isinstance(registry, dict):
        issues.append(issue("source_registry_invalid", "source registry must be an object"))
        registry = {}
    allowed_top = {
        "schema_version",
        "candidate_commit",
        "candidate_frozen_at",
        "required_comparable_tasks",
        "v1_baselines",
        "sources",
    }
    if set(registry) != allowed_top:
        issues.append(issue("source_registry_fields", "source registry top-level fields differ"))
    for field in (
        "schema_version",
        "candidate_commit",
        "candidate_frozen_at",
        "required_comparable_tasks",
    ):
        if registry.get(field) != manifest.get(field):
            issues.append(issue(f"source_registry_{field}_mismatch", f"{field} differs"))
    if registry != anchor["registry"]:
        issues.append(
            issue(
                "source_registry_anchor_mismatch",
                "source registry differs from the trusted Git freeze Commit",
            )
        )
    registry_sources = registry.get("sources")
    if not isinstance(registry_sources, list):
        issues.append(issue("source_registry_sources_invalid", "sources must be an array"))
        registry_sources = []
    frozen_fields = {
        "source_id",
        "project_alias",
        "project_evidence_id",
        "project_repo",
        "stable_branch",
        "ledger",
        "ledger_prefix_bytes",
        "ledger_prefix_sha256",
    }
    normalized: dict[str, dict[str, Any]] = {}
    for entry in registry_sources:
        if not isinstance(entry, dict) or set(entry) != frozen_fields:
            issues.append(issue("source_registry_source_fields", "source entry fields differ"))
            continue
        source_id = entry.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in normalized:
            issues.append(issue("source_registry_source_id", "source_id is missing or duplicated"))
            continue
        normalized[source_id] = entry
    manifest_sources = {source["source_id"]: source for source in manifest["sources"]}
    if set(normalized) != set(manifest_sources):
        issues.append(issue("source_registry_roster_mismatch", "source roster differs"))
    for source_id in set(normalized) & set(manifest_sources):
        for field in frozen_fields:
            if normalized[source_id].get(field) != manifest_sources[source_id].get(field):
                issues.append(
                    issue(
                        "source_registry_source_mismatch",
                        f"{source_id}.{field} differs from frozen registry",
                    )
                )
    return {
        "path": str(path),
        "sha256": actual_hash,
        "anchor_freeze_commit": anchor["freeze_commit"],
        "issues": issues,
        "passed": not issues,
    }


def validate_evidence(
    *,
    path: Path,
    expected_hash: str,
    evidence_type: str,
    source: dict[str, Any],
    trial: dict[str, Any],
    ready_time: datetime | None,
    accepted_time: datetime | None,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    registered_hash: str | None = None
    try:
        registered_hash = require_sha256(expected_hash, f"{evidence_type} evidence digest")
    except ReleaseGateError as exc:
        issues.append(issue(f"{evidence_type}_evidence_digest_invalid", str(exc)))
    try:
        if registered_hash and file_sha256(path).casefold() != registered_hash.casefold():
            issues.append(
                issue(
                    f"{evidence_type}_evidence_digest_mismatch",
                    "evidence does not match registered SHA-256",
                )
            )
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [issue(f"{evidence_type}_evidence_error", str(exc))]
    if not isinstance(evidence, dict):
        return [issue(f"{evidence_type}_evidence_error", "evidence must be an object")]
    common_fields = {
        "schema_version",
        "evidence_type",
        "project_evidence_id",
        "task_id",
        "occurred_at",
        "source_locator",
    }
    allowed_fields = (
        common_fields | {"genuine_request", "synthetic", "summary"}
        if evidence_type == "request"
        else common_fields
        | {
            "accepted",
            "accepted_by_role",
            "candidate_commit",
            "stable_commit",
            "critical_defect_escape",
            "material_quality_regression",
            "scope_violation",
            "write_conflict",
            "recovery_executable",
            "integration_proof",
        }
    )
    unknown_fields = set(evidence) - allowed_fields
    if unknown_fields:
        issues.append(
            issue(
                f"{evidence_type}_evidence_unknown_fields",
                f"unknown evidence fields: {sorted(unknown_fields)}",
            )
        )
    if "source_locator" in evidence and (
        not isinstance(evidence["source_locator"], str)
        or not evidence["source_locator"].strip()
    ):
        issues.append(
            issue(
                f"{evidence_type}_evidence_source_locator_invalid",
                "source_locator must be a non-empty string",
            )
        )
    expected = {
        "schema_version": "2.0",
        "evidence_type": f"task_{evidence_type}",
        "project_evidence_id": source["project_evidence_id"],
        "task_id": trial["task_id"],
    }
    for field, value in expected.items():
        if evidence.get(field) != value:
            issues.append(
                issue(
                    f"{evidence_type}_evidence_{field}_mismatch",
                    f"evidence {field} does not match the registry",
                )
            )
    try:
        occurred_at = team_metrics.parse_time(evidence.get("occurred_at", ""))
    except (team_metrics.LedgerError, AttributeError, TypeError):
        issues.append(
            issue(f"{evidence_type}_evidence_time_invalid", "occurred_at is invalid")
        )
        occurred_at = None
    if evidence_type == "request":
        if evidence.get("genuine_request") is not True:
            issues.append(issue("request_not_genuine", "request is not marked genuine"))
        if evidence.get("synthetic") is not False:
            issues.append(issue("request_is_synthetic", "request evidence is synthetic"))
        if not isinstance(evidence.get("summary"), str) or not evidence["summary"].strip():
            issues.append(issue("request_summary_missing", "request summary is missing"))
        if occurred_at and ready_time and occurred_at > ready_time:
            issues.append(issue("request_after_task_ready", "request occurred after task_ready"))
    else:
        if evidence.get("accepted") is not True:
            issues.append(issue("acceptance_not_confirmed", "acceptance is not confirmed"))
        for field in ("candidate_commit", "stable_commit"):
            actual = evidence.get(field)
            if not isinstance(actual, str) or not FULL_SHA.fullmatch(actual):
                issues.append(
                    issue(
                        f"acceptance_evidence_{field}_invalid",
                        f"evidence {field} must be a full 40-character SHA",
                    )
                )
            elif actual.casefold() != trial[field].casefold():
                issues.append(
                    issue(
                        f"acceptance_evidence_{field}_mismatch",
                        f"evidence {field} does not match the trial",
                    )
                )
        try:
            evidence_proof = validate_integration_proof(
                evidence.get("integration_proof"),
                "acceptance evidence integration_proof",
            )
        except ReleaseGateError as exc:
            issues.append(issue("acceptance_evidence_integration_proof_invalid", str(exc)))
        else:
            if evidence_proof != trial["integration_proof"]:
                issues.append(
                    issue(
                        "acceptance_evidence_integration_proof_mismatch",
                        "evidence integration_proof does not match the trial",
                    )
                )
        for field in QUALITY_FIELDS:
            if evidence.get(field) is not trial[field]:
                issues.append(
                    issue(
                        f"acceptance_evidence_{field}_mismatch",
                        f"evidence {field} does not match the trial",
                    )
                )
        if not isinstance(evidence.get("accepted_by_role"), str) or not evidence[
            "accepted_by_role"
        ].strip():
            issues.append(issue("acceptance_role_missing", "accepted_by_role is missing"))
        if occurred_at and ready_time and occurred_at < ready_time:
            issues.append(issue("acceptance_before_task_ready", "acceptance predates task_ready"))
        if occurred_at and accepted_time and occurred_at > accepted_time:
            issues.append(
                issue("acceptance_after_ledger_event", "acceptance postdates accepted event")
            )
    return issues


def evaluate_integration_proof(
    repo: Path, trial: dict[str, Any], issues: list[dict[str, str]]
) -> None:
    try:
        proof = validate_integration_proof(
            trial.get("integration_proof"), "trial integration_proof"
        )
    except ReleaseGateError as exc:
        issues.append(issue("integration_proof_invalid", str(exc)))
        return

    candidate = trial["candidate_commit"]
    stable = trial["stable_commit"]
    if proof["mode"] == "same_commit":
        if candidate.casefold() != stable.casefold():
            issues.append(
                issue(
                    "same_commit_mismatch",
                    "same_commit requires candidate_commit and stable_commit to be equal",
                )
            )
        return

    try:
        resolve_candidate_ref(
            repo,
            proof["candidate_ref"],
            candidate,
            "integration_proof.candidate_ref",
        )
    except ReleaseGateError as exc:
        issues.append(issue("candidate_ref_invalid", str(exc)))
    try:
        candidate_tree = git_object_id(
            repo, candidate, "tree", "candidate_commit tree"
        )
    except ReleaseGateError as exc:
        issues.append(issue("candidate_tree_missing", str(exc)))
        candidate_tree = None
    try:
        stable_tree = git_object_id(repo, stable, "tree", "stable_commit tree")
    except ReleaseGateError as exc:
        issues.append(issue("stable_tree_missing", str(exc)))
        stable_tree = None

    declared_candidate_tree = proof["candidate_tree"]
    declared_stable_tree = proof["stable_tree"]
    if candidate_tree and candidate_tree != declared_candidate_tree.casefold():
        issues.append(
            issue(
                "candidate_tree_mismatch",
                "integration proof candidate_tree differs from Git",
            )
        )
    if stable_tree and stable_tree != declared_stable_tree.casefold():
        issues.append(
            issue(
                "stable_tree_mismatch",
                "integration proof stable_tree differs from Git",
            )
        )
    if candidate_tree and stable_tree and candidate_tree != stable_tree:
        issues.append(
            issue(
                "integration_tree_mismatch",
                "candidate and stable Git trees differ",
            )
        )


def evaluate_trial(
    trial: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    source: dict[str, Any],
    receipt: dict[str, Any] | None,
    closed: datetime,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    task_events = [
        event for event in source["events"] if event["task_id"] == trial["task_id"]
    ]
    ready_events = [event for event in task_events if event["event"] == "task_ready"]
    dev_complete_events = [
        event for event in task_events if event["event"] == "dev_complete"
    ]
    accepted_events = [event for event in task_events if event["event"] == "accepted"]
    ready = ready_events[0] if len(ready_events) == 1 else None
    accepted = accepted_events[0] if len(accepted_events) == 1 else None
    ready_time = team_metrics.parse_time(ready["timestamp"]) if ready else None
    accepted_time = team_metrics.parse_time(accepted["timestamp"]) if accepted else None
    if receipt is None:
        issues.append(
            issue(
                "task_not_in_trusted_anchor",
                "trial has no registration in the trusted Git anchor history",
            )
        )
    else:
        anchored_fields = {
            "registration_sequence": "registration_sequence",
            "source_id": "source_id",
            "task_id": "task_id",
            "skill_candidate_commit": "skill_candidate_commit",
            "request_evidence": "request_evidence",
            "request_evidence_sha256": "request_evidence_sha256",
            "v1_baseline_id": "v1_baseline_id",
            "v1_baseline_stratum": "v1_baseline_stratum",
            "comparable": "release_trial_comparable",
            "genuine_request": "genuine_request",
            "synthetic": "synthetic",
        }
        for trial_field, receipt_field in anchored_fields.items():
            actual = trial.get(trial_field)
            expected = receipt.get(receipt_field)
            matches = (
                isinstance(actual, str)
                and isinstance(expected, str)
                and actual.casefold() == expected.casefold()
                if trial_field in {"skill_candidate_commit", "request_evidence_sha256"}
                else actual == expected
            )
            if not matches:
                issues.append(
                    issue(
                        f"anchor_{trial_field}_mismatch",
                        f"trial {trial_field} differs from the trusted registration receipt",
                    )
                )
        registered_time = team_metrics.parse_time(receipt["registered_at"])
        if ready_time and ready_time != registered_time:
            issues.append(
                issue(
                    "task_ready_anchor_time_mismatch",
                    "task_ready timestamp differs from the trusted registration receipt",
                )
            )
    if trial["skill_candidate_commit"].casefold() != manifest["candidate_commit"].casefold():
        issues.append(
            issue("skill_candidate_mismatch", "trial did not use the candidate Commit")
        )
    if len(ready_events) != 1:
        issues.append(
            issue("task_ready_count", f"expected 1 task_ready, found {len(ready_events)}")
        )
    if ready:
        ready_checks = {
            "release_trial_registration_sequence": trial["registration_sequence"],
            "skill_candidate_commit": manifest["candidate_commit"],
            "release_trial_comparable": trial["comparable"],
            "v1_baseline_id": trial["v1_baseline_id"],
            "v1_baseline_stratum": trial["v1_baseline_stratum"],
        }
        if receipt:
            ready_checks.update(
                {
                    "complexity": receipt["complexity"],
                    "risk": receipt["risk"],
                    "topology": receipt["topology"],
                }
            )
        for field, expected in ready_checks.items():
            actual = ready.get(field)
            matches = (
                isinstance(actual, str)
                and isinstance(expected, str)
                and actual.casefold() == expected.casefold()
                if field == "skill_candidate_commit"
                else actual == expected
            )
            if not matches:
                issues.append(
                    issue(
                        f"task_ready_{field}_mismatch",
                        f"task_ready {field} does not match the registry",
                    )
                )
    for violation in source["audit"]["violations"]:
        if violation["task_id"] == trial["task_id"]:
            issues.append(
                issue(f"hard_gate:{violation['code']}", violation["message"])
            )

    if trial["disposition"] == "accepted":
        if len(accepted_events) != 1:
            issues.append(
                issue("accepted_count", f"expected 1 accepted, found {len(accepted_events)}")
            )
        if accepted:
            accepted_commit = accepted.get("commit")
            if not isinstance(accepted_commit, str) or not FULL_SHA.fullmatch(
                accepted_commit
            ):
                issues.append(
                    issue(
                        "candidate_commit_mismatch",
                        "accepted candidate Commit is not a full SHA",
                    )
                )
            elif accepted_commit.casefold() != trial["candidate_commit"].casefold():
                issues.append(
                    issue("candidate_commit_mismatch", "accepted candidate Commit differs")
                )
            accepted_stable = accepted.get("stable_commit")
            if not isinstance(accepted_stable, str) or not FULL_SHA.fullmatch(
                accepted_stable
            ):
                issues.append(
                    issue(
                        "stable_commit_mismatch",
                        "accepted stable Commit is not a full SHA",
                    )
                )
            elif accepted_stable.casefold() != trial["stable_commit"].casefold():
                issues.append(
                    issue("stable_commit_mismatch", "accepted stable Commit differs")
                )
        if len(dev_complete_events) == 1:
            dev_commit = dev_complete_events[0].get("commit")
            if not isinstance(dev_commit, str) or not FULL_SHA.fullmatch(dev_commit):
                issues.append(
                    issue(
                        "dev_complete_commit_mismatch",
                        "dev_complete candidate Commit is not a full SHA",
                    )
                )
            elif dev_commit.casefold() != trial["candidate_commit"].casefold():
                issues.append(
                    issue(
                        "dev_complete_commit_mismatch",
                        "dev_complete candidate Commit differs",
                    )
                )
        repo = Path(source["project_repo"])
        candidate_exists = git_commit_exists(repo, trial["candidate_commit"])
        stable_exists = git_commit_exists(repo, trial["stable_commit"])
        if not candidate_exists:
            issues.append(issue("candidate_commit_missing", "candidate Commit is absent"))
        if not stable_exists:
            issues.append(issue("stable_commit_missing", "stable Commit is absent"))
        evaluate_integration_proof(repo, trial, issues)
        if stable_exists:
            if source["stable_branch_commit"] and run_git(
                repo,
                "merge-base",
                "--is-ancestor",
                trial["stable_commit"],
                source["stable_branch_commit"],
            ).returncode != 0:
                issues.append(
                    issue("stable_commit_not_on_branch", "stable Commit is not on stable_branch")
                )
        if accepted_time and accepted_time > closed:
            issues.append(
                issue("acceptance_after_anchor_close", "accepted event postdates anchor close")
            )
    else:
        if accepted_events:
            issues.append(issue("disposition_mismatch", "accepted event contradicts disposition"))
        if trial["comparable"]:
            issues.append(issue("comparable_task_not_accepted", "comparable task is not accepted"))

    issues.extend(
        validate_evidence(
            path=resolve_path(
                manifest_path,
                receipt["request_evidence"] if receipt else trial["request_evidence"],
            ),
            expected_hash=(
                receipt["request_evidence_sha256"]
                if receipt
                else trial["request_evidence_sha256"]
            ),
            evidence_type="request",
            source=source,
            trial=receipt if receipt else trial,
            ready_time=ready_time,
            accepted_time=accepted_time,
        )
    )
    if trial["genuine_request"] is not True:
        issues.append(issue("trial_not_genuine", "trial is not marked genuine"))
    if trial["synthetic"] is not False:
        issues.append(issue("trial_is_synthetic", "synthetic work cannot count"))
    if trial["disposition"] == "accepted":
        issues.extend(
            validate_evidence(
                path=resolve_path(manifest_path, trial["acceptance_evidence"]),
                expected_hash=trial["acceptance_evidence_sha256"],
                evidence_type="acceptance",
                source=source,
                trial=trial,
                ready_time=ready_time,
                accepted_time=accepted_time,
            )
        )

    quality_failures = {
        "critical_defect_escape": trial["critical_defect_escape"] is True,
        "material_quality_regression": trial["material_quality_regression"] is True,
        "scope_violation": trial["scope_violation"] is True,
        "write_conflict": trial["write_conflict"] is True,
        "recovery_not_executable": trial["recovery_executable"] is not True,
    }
    for code, failed in quality_failures.items():
        if failed:
            issues.append(issue(code, code.replace("_", " ")))

    hard_gate_issues = [item for item in issues if item["code"].startswith("hard_gate:")]
    return {
        "trial_id": trial["trial_id"],
        "registration_sequence": trial["registration_sequence"],
        "source_id": trial["source_id"],
        "project_alias": source["project_alias"],
        "task_id": trial["task_id"],
        "anchor_commit": receipt["anchor_commit"] if receipt else None,
        "v1_baseline_id": trial["v1_baseline_id"],
        "v1_baseline_stratum": trial["v1_baseline_stratum"],
        "comparable": trial["comparable"],
        "disposition": trial["disposition"],
        "ready_timestamp": ready["timestamp"] if ready else None,
        "issues": issues,
        "passed": not issues,
        "hard_gates_passed": not hard_gate_issues,
        "quality_passed": not any(quality_failures.values()),
    }


def evaluate_manifest(
    manifest: dict[str, Any],
    manifest_path: Path,
    anchor: dict[str, Any],
) -> dict[str, Any]:
    anchor_registry = anchor["registry"]
    anchor_closure = anchor["closure"]
    frozen = team_metrics.parse_time(anchor_registry["candidate_frozen_at"])
    closed = team_metrics.parse_time(anchor_closure["closed_at"])
    anchor_alignment_issues: list[dict[str, str]] = []
    expected_manifest_values = {
        "candidate_commit": anchor_registry["candidate_commit"],
        "candidate_frozen_at": anchor_registry["candidate_frozen_at"],
        "registry_closed_at": anchor_closure["closed_at"],
        "required_comparable_tasks": anchor_registry["required_comparable_tasks"],
    }
    for field, expected in expected_manifest_values.items():
        actual = manifest[field]
        matches = (
            isinstance(actual, str)
            and isinstance(expected, str)
            and actual.casefold() == expected.casefold()
            if field == "candidate_commit"
            else actual == expected
        )
        if not matches:
            anchor_alignment_issues.append(
                issue(f"manifest_{field}_anchor_mismatch", f"manifest {field} differs")
            )
    if file_sha256(manifest_path).casefold() != anchor_closure[
        "trial_manifest_sha256"
    ].casefold():
        anchor_alignment_issues.append(
            issue(
                "manifest_anchor_digest_mismatch",
                "trial Manifest differs from the trusted anchor closure digest",
            )
        )

    source_registry = validate_source_registry(manifest, manifest_path, anchor)
    if anchor_alignment_issues:
        source_registry["issues"].extend(anchor_alignment_issues)
        source_registry["passed"] = False
    source_results = {
        source["source_id"]: load_source(source, manifest_path)
        for source in manifest["sources"]
    }

    canonical_repos: dict[str, str] = {}
    canonical_ledgers: dict[str, str] = {}
    for source in source_results.values():
        repo_key = source["repo_root"] or source["project_repo"]
        ledger_key = str(Path(source["ledger"]).resolve())
        if repo_key in canonical_repos:
            source["issues"].append(
                issue(
                    "duplicate_project_repo",
                    f"project_repo duplicates source {canonical_repos[repo_key]}",
                )
            )
        else:
            canonical_repos[repo_key] = source["source_id"]
        if ledger_key in canonical_ledgers:
            source["issues"].append(
                issue(
                    "duplicate_ledger",
                    f"ledger duplicates source {canonical_ledgers[ledger_key]}",
                )
            )
        else:
            canonical_ledgers[ledger_key] = source["source_id"]

        window_violations = []
        for violation in source["audit"]["violations"]:
            timestamp = team_metrics.parse_time(violation["timestamp"])
            if frozen < timestamp <= closed:
                window_violations.append(violation)
                source["issues"].append(
                    issue(f"hard_gate:{violation['code']}", violation["message"])
                )
        source["window_hard_gate_violations"] = window_violations
        source["integrity_passed"] = not source["issues"]

    receipt_by_key = {
        (receipt["source_id"], receipt["task_id"]): receipt
        for receipt in anchor["receipts"]
    }
    anchor_keys = list(receipt_by_key)
    anchor_key_set = set(anchor_keys)
    manifest_key_set = {
        (trial["source_id"], trial["task_id"]) for trial in manifest["trials"]
    }
    ledger_entries: list[dict[str, Any]] = []
    for source in source_results.values():
        for event in source["events"]:
            if event["event"] != "task_ready":
                continue
            timestamp = team_metrics.parse_time(event["timestamp"])
            if frozen < timestamp <= closed:
                ledger_entries.append(
                    {
                        "source_id": source["source_id"],
                        "task_id": event["task_id"],
                        "timestamp": timestamp,
                        "sequence": event.get("release_trial_registration_sequence"),
                    }
                )
    ledger_keys = [(entry["source_id"], entry["task_id"]) for entry in ledger_entries]
    ledger_key_set = set(ledger_keys)
    missing_trials = sorted(anchor_key_set - manifest_key_set)
    extra_trials = sorted(manifest_key_set - anchor_key_set)
    missing_ledger_registrations = sorted(anchor_key_set - ledger_key_set)
    unanchored_ledger_registrations = sorted(ledger_key_set - anchor_key_set)
    duplicate_ledger_keys = sorted(
        {key for key in ledger_keys if ledger_keys.count(key) > 1}
    )
    registry_complete = not any(
        (
            missing_trials,
            extra_trials,
            missing_ledger_registrations,
            unanchored_ledger_registrations,
            duplicate_ledger_keys,
        )
    )
    order_established = [
        receipt["registration_sequence"] for receipt in anchor["receipts"]
    ] == list(range(1, len(anchor["receipts"]) + 1))

    evaluated = [
        evaluate_trial(
            trial,
            manifest,
            manifest_path,
            source_results[trial["source_id"]],
            receipt_by_key.get((trial["source_id"], trial["task_id"])),
            closed,
        )
        for trial in manifest["trials"]
    ]
    result_by_key = {
        (item["source_id"], item["task_id"]): item for item in evaluated
    }
    anchored_comparable_keys = [
        (receipt["source_id"], receipt["task_id"])
        for receipt in anchor["receipts"]
        if receipt["release_trial_comparable"]
    ]
    comparable = [
        result_by_key[key] for key in anchored_comparable_keys if key in result_by_key
    ]
    baselines_by_id = {
        baseline["baseline_id"]: baseline
        for baseline in anchor_registry["v1_baselines"]
    }
    anchored_efficiency_keys = [
        (receipt["source_id"], receipt["task_id"])
        for receipt in anchor["receipts"]
        if receipt["release_trial_comparable"]
        and baselines_by_id[receipt["v1_baseline_id"]][
            "formal_efficiency_comparable"
        ]
    ]
    required = anchor_registry["required_comparable_tasks"]
    first_required_keys = anchored_comparable_keys[:required]
    first_required = [
        result_by_key[key] for key in first_required_keys if key in result_by_key
    ]
    enough = len(anchored_comparable_keys) >= required
    sources_integrity = source_registry["passed"] and all(
        source["integrity_passed"] for source in source_results.values()
    )
    first_required_pass = (
        enough
        and registry_complete
        and order_established
        and sources_integrity
        and len(first_required) == required
        and all(result["passed"] for result in first_required)
    )
    passed_comparable = sum(result["passed"] for result in comparable)
    passed_efficiency_comparable = sum(
        result_by_key[key]["passed"]
        for key in anchored_efficiency_keys
        if key in result_by_key
    )
    public_sources = [
        {
            key: value
            for key, value in source.items()
            if key not in {"events", "audit"}
        }
        | {"hard_gate_violations": source["audit"]["violations"]}
        for source in source_results.values()
    ]
    public_anchor = {
        "repo": anchor["repo"],
        "freeze_commit": anchor["freeze_commit"],
        "head_commit": anchor["head_commit"],
        "registration_commits": [
            receipt["anchor_commit"] for receipt in anchor["receipts"]
        ],
        "registration_count": len(anchor["receipts"]),
        "passed": anchor["passed"] and not anchor_alignment_issues,
        "issues": anchor_alignment_issues,
    }
    return {
        "schema_version": "2.0",
        "candidate_version": manifest["candidate_version"],
        "candidate_commit": anchor_registry["candidate_commit"],
        "candidate_frozen_at": anchor_registry["candidate_frozen_at"],
        "registry_closed_at": anchor_closure["closed_at"],
        "required_comparable_tasks": required,
        "frozen_v1_baselines": len(anchor_registry["v1_baselines"]),
        "trusted_anchor": public_anchor,
        "registered_sources": len(source_results),
        "source_registry": source_registry,
        "anchored_registrations": len(anchor["receipts"]),
        "ledger_task_ready_events": len(ledger_entries),
        "listed_trials": len(evaluated),
        "comparable_trials": len(anchored_comparable_keys),
        "passed_comparable_trials": passed_comparable,
        "formal_efficiency_comparable_trials": len(anchored_efficiency_keys),
        "passed_formal_efficiency_comparable_trials": passed_efficiency_comparable,
        "missing_trial_identities": [list(key) for key in missing_trials],
        "extra_trial_identities": [list(key) for key in extra_trials],
        "missing_ledger_registration_identities": [
            list(key) for key in missing_ledger_registrations
        ],
        "unanchored_ledger_registration_identities": [
            list(key) for key in unanchored_ledger_registrations
        ],
        "duplicate_ledger_registration_identities": [
            list(key) for key in duplicate_ledger_keys
        ],
        "first_comparable_trial_ids": [
            result_by_key[key]["trial_id"]
            for key in first_required_keys
            if key in result_by_key
        ],
        "sources": public_sources,
        "trials": evaluated,
        "gates": {
            "trusted_anchor_integral": public_anchor["passed"],
            "source_snapshots_integral": sources_integrity,
            "registry_complete": registry_complete,
            "registration_order_established": order_established,
            "enough_comparable_tasks": enough,
            "first_comparable_tasks_pass": first_required_pass,
            "no_hard_gate_violations": first_required_pass
            and all(result["hard_gates_passed"] for result in first_required),
            "no_material_quality_regression": first_required_pass
            and all(result["quality_passed"] for result in first_required),
        },
        "stable_v2_ready": first_required_pass,
        "formal_efficiency_sample_size_ready": (
            registry_complete
            and order_established
            and sources_integrity
            and passed_efficiency_comparable >= 15
        ),
        "limitations": [
            "The verifier must supply freeze and head Commit SHAs from an independently protected append-only ref or trusted timestamp record.",
            "Local Git cannot prove remote protection, push time, or authenticity beyond the supplied private evidence.",
            "The gate does not prove efficiency improvement; that needs the preregistered stratified comparison.",
        ],
    }


def write_or_print(data: dict[str, Any], output: str | None) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--anchor-repo", required=True)
    parser.add_argument("--anchor-freeze-commit", required=True)
    parser.add_argument("--anchor-head-commit", required=True)
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        path = Path(args.manifest).resolve()
        anchor = load_anchor(
            Path(args.anchor_repo),
            args.anchor_freeze_commit,
            args.anchor_head_commit,
        )
        result = evaluate_manifest(load_manifest(path), path, anchor)
        write_or_print(result, args.output)
        return 0 if result["stable_v2_ready"] else 1
    except (ReleaseGateError, team_metrics.LedgerError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
