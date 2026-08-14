#!/usr/bin/env python3
"""Evaluate the preregistered, source-complete gate for stable V2.0."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
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
REQUIRED_TRIAL_FIELDS = {
    "trial_id",
    "registration_sequence",
    "source_id",
    "task_id",
    "skill_candidate_commit",
    "request_evidence",
    "request_evidence_sha256",
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


class ReleaseGateError(ValueError):
    pass


def require_non_empty(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseGateError(f"{label} must be a non-empty string")


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
    if not FULL_SHA.fullmatch(str(data["candidate_commit"])):
        raise ReleaseGateError("candidate_commit must be a full 40-character SHA")
    if manifest_time(data["registry_closed_at"], "registry_closed_at") <= manifest_time(
        data["candidate_frozen_at"], "candidate_frozen_at"
    ):
        raise ReleaseGateError("registry_closed_at must be after candidate_frozen_at")
    require_non_empty(data["source_registry"], "source_registry")
    if not SHA256.fullmatch(str(data["source_registry_sha256"])):
        raise ReleaseGateError("source_registry_sha256 must be SHA-256")
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
        if not SAFE_REF.fullmatch(source["stable_branch"]):
            raise ReleaseGateError(f"{label}.stable_branch is not a safe Git ref")
        prefix_bytes = source["ledger_prefix_bytes"]
        if (
            isinstance(prefix_bytes, bool)
            or not isinstance(prefix_bytes, int)
            or prefix_bytes < 0
        ):
            raise ReleaseGateError(f"{label}.ledger_prefix_bytes must be non-negative")
        if not SHA256.fullmatch(str(source["ledger_prefix_sha256"])):
            raise ReleaseGateError(f"{label}.ledger_prefix_sha256 must be SHA-256")
        if not SHA256.fullmatch(str(source["ledger_sha256"])):
            raise ReleaseGateError(f"{label}.ledger_sha256 must be a SHA-256 digest")

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
        if not FULL_SHA.fullmatch(str(trial["skill_candidate_commit"])):
            raise ReleaseGateError(f"{label}.skill_candidate_commit must be a full SHA")
        if not SHA256.fullmatch(str(trial["request_evidence_sha256"])):
            raise ReleaseGateError(f"{label}.request_evidence_sha256 must be SHA-256")
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
            require_non_empty(trial["v1_baseline_stratum"], f"{label}.v1_baseline_stratum")
        else:
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
                if not FULL_SHA.fullmatch(str(trial[field])):
                    raise ReleaseGateError(f"{label}.{field} must be a full SHA")
            require_non_empty(trial["acceptance_evidence"], f"{label}.acceptance_evidence")
            if not SHA256.fullmatch(str(trial["acceptance_evidence_sha256"])):
                raise ReleaseGateError(f"{label}.acceptance_evidence_sha256 must be SHA-256")
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
    except OSError as exc:
        return subprocess.CompletedProcess(command, 127, stdout="", stderr=str(exc))


def git_commit_exists(repo: Path, commit: str) -> bool:
    return run_git(repo, "cat-file", "-e", f"{commit}^{{commit}}").returncode == 0


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
        branch_result = run_git(
            repo, "rev-parse", "--verify", f"{source['stable_branch']}^{{commit}}"
        )
        if branch_result.returncode != 0 or not FULL_SHA.fullmatch(
            branch_result.stdout.strip()
        ):
            issues.append(issue("stable_branch_error", "stable_branch is not a Commit"))
        else:
            branch_commit = branch_result.stdout.strip().casefold()
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
    manifest: dict[str, Any], manifest_path: Path
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
    allowed_top = {"schema_version", "candidate_commit", "candidate_frozen_at", "sources"}
    if set(registry) != allowed_top:
        issues.append(issue("source_registry_fields", "source registry top-level fields differ"))
    for field in ("schema_version", "candidate_commit", "candidate_frozen_at"):
        if registry.get(field) != manifest.get(field):
            issues.append(issue(f"source_registry_{field}_mismatch", f"{field} differs"))
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
    try:
        if file_sha256(path).casefold() != expected_hash.casefold():
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
    except team_metrics.LedgerError:
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
            if str(evidence.get(field, "")).casefold() != trial[field].casefold():
                issues.append(
                    issue(
                        f"acceptance_evidence_{field}_mismatch",
                        f"evidence {field} does not match the trial",
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


def evaluate_trial(
    trial: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    source: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    task_events = [
        event for event in source["events"] if event["task_id"] == trial["task_id"]
    ]
    ready_events = [event for event in task_events if event["event"] == "task_ready"]
    accepted_events = [event for event in task_events if event["event"] == "accepted"]
    ready = ready_events[0] if len(ready_events) == 1 else None
    accepted = accepted_events[0] if len(accepted_events) == 1 else None
    ready_time = team_metrics.parse_time(ready["timestamp"]) if ready else None
    accepted_time = team_metrics.parse_time(accepted["timestamp"]) if accepted else None
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
            "v1_baseline_stratum": trial["v1_baseline_stratum"],
        }
        for field, expected in ready_checks.items():
            actual = ready.get(field)
            matches = (
                actual.casefold() == str(expected).casefold()
                if field == "skill_candidate_commit" and isinstance(actual, str)
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
            if accepted.get("commit", "").casefold() != trial["candidate_commit"].casefold():
                issues.append(
                    issue("candidate_commit_mismatch", "accepted candidate Commit differs")
                )
            if accepted.get("stable_commit", "").casefold() != trial[
                "stable_commit"
            ].casefold():
                issues.append(
                    issue("stable_commit_mismatch", "accepted stable Commit differs")
                )
        repo = Path(source["project_repo"])
        if not git_commit_exists(repo, trial["candidate_commit"]):
            issues.append(issue("candidate_commit_missing", "candidate Commit is absent"))
        if not git_commit_exists(repo, trial["stable_commit"]):
            issues.append(issue("stable_commit_missing", "stable Commit is absent"))
        elif source["stable_branch_commit"] and run_git(
            repo,
            "merge-base",
            "--is-ancestor",
            trial["stable_commit"],
            source["stable_branch_commit"],
        ).returncode != 0:
            issues.append(
                issue("stable_commit_not_on_branch", "stable Commit is not on stable_branch")
            )
    else:
        if accepted_events:
            issues.append(issue("disposition_mismatch", "accepted event contradicts disposition"))
        if trial["comparable"]:
            issues.append(issue("comparable_task_not_accepted", "comparable task is not accepted"))

    issues.extend(
        validate_evidence(
            path=resolve_path(manifest_path, trial["request_evidence"]),
            expected_hash=trial["request_evidence_sha256"],
            evidence_type="request",
            source=source,
            trial=trial,
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
        "comparable": trial["comparable"],
        "disposition": trial["disposition"],
        "ready_timestamp": ready["timestamp"] if ready else None,
        "issues": issues,
        "passed": not issues,
        "hard_gates_passed": not hard_gate_issues,
        "quality_passed": not any(quality_failures.values()),
    }


def evaluate_manifest(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    frozen = team_metrics.parse_time(manifest["candidate_frozen_at"])
    closed = team_metrics.parse_time(manifest["registry_closed_at"])
    source_registry = validate_source_registry(manifest, manifest_path)
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
                issue("duplicate_ledger", f"ledger duplicates source {canonical_ledgers[ledger_key]}")
            )
        else:
            canonical_ledgers[ledger_key] = source["source_id"]
        source["integrity_passed"] = not source["issues"]

    registry_entries: list[dict[str, Any]] = []
    for source in source_results.values():
        for event in source["events"]:
            if event["event"] != "task_ready":
                continue
            timestamp = team_metrics.parse_time(event["timestamp"])
            if frozen < timestamp <= closed:
                registry_entries.append(
                    {
                        "source_id": source["source_id"],
                        "task_id": event["task_id"],
                        "timestamp": timestamp,
                        "sequence": event.get("release_trial_registration_sequence"),
                    }
                )

    registry_keys = [(entry["source_id"], entry["task_id"]) for entry in registry_entries]
    registry_key_set = set(registry_keys)
    trial_key_set = {
        (trial["source_id"], trial["task_id"]) for trial in manifest["trials"]
    }
    missing_trials = sorted(registry_key_set - trial_key_set)
    extra_trials = sorted(trial_key_set - registry_key_set)
    duplicate_registry_keys = sorted(
        {key for key in registry_keys if registry_keys.count(key) > 1}
    )
    raw_sequences = [entry["sequence"] for entry in registry_entries]
    sequence_types_valid = all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0
        for value in raw_sequences
    )
    sequence_set_valid = sequence_types_valid and sorted(raw_sequences) == list(
        range(1, len(registry_entries) + 1)
    )
    chronology_valid = False
    if sequence_set_valid:
        ordered_registry = sorted(registry_entries, key=lambda item: item["sequence"])
        chronology_valid = all(
            left["timestamp"] <= right["timestamp"]
            for left, right in zip(ordered_registry, ordered_registry[1:])
        )
    order_established = sequence_set_valid and chronology_valid
    registry_complete = not missing_trials and not extra_trials and not duplicate_registry_keys

    evaluated = [
        evaluate_trial(
            trial,
            manifest,
            manifest_path,
            source_results[trial["source_id"]],
        )
        for trial in manifest["trials"]
    ]
    result_by_key = {
        (item["source_id"], item["task_id"]): item for item in evaluated
    }
    for key in extra_trials:
        result_by_key[key]["issues"].append(
            issue(
                "task_not_in_registry_window",
                "trial has no task_ready in the frozen registry window",
            )
        )
        result_by_key[key]["passed"] = False
    comparable = sorted(
        [result for result in evaluated if result["comparable"]],
        key=lambda result: result["registration_sequence"],
    )
    required = manifest["required_comparable_tasks"]
    first_required = comparable[:required]
    enough = len(comparable) >= required
    sources_integrity = source_registry["passed"] and all(
        source["integrity_passed"] for source in source_results.values()
    )
    first_required_pass = (
        enough
        and registry_complete
        and order_established
        and sources_integrity
        and all(result["passed"] for result in first_required)
    )
    passed_comparable = sum(result["passed"] for result in comparable)
    public_sources = [
        {
            key: value
            for key, value in source.items()
            if key not in {"events", "audit"}
        }
        | {"hard_gate_violations": source["audit"]["violations"]}
        for source in source_results.values()
    ]
    return {
        "schema_version": "2.0",
        "candidate_version": manifest["candidate_version"],
        "candidate_commit": manifest["candidate_commit"],
        "candidate_frozen_at": manifest["candidate_frozen_at"],
        "registry_closed_at": manifest["registry_closed_at"],
        "required_comparable_tasks": required,
        "registered_sources": len(source_results),
        "source_registry": source_registry,
        "registered_task_ready_events": len(registry_entries),
        "listed_trials": len(evaluated),
        "comparable_trials": len(comparable),
        "passed_comparable_trials": passed_comparable,
        "missing_trial_identities": [list(key) for key in missing_trials],
        "extra_trial_identities": [list(key) for key in extra_trials],
        "duplicate_registry_identities": [list(key) for key in duplicate_registry_keys],
        "first_comparable_trial_ids": [
            result["trial_id"] for result in first_required
        ],
        "sources": public_sources,
        "trials": evaluated,
        "gates": {
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
            and passed_comparable >= 15
        ),
        "limitations": [
            "This gate proves registered ledger snapshots, Git ancestry, evidence digests, recorded mechanisms, and quality fields only.",
            "It cannot prove an external task never recorded in a registered ledger or authenticity beyond supplied private evidence.",
            "It does not prove efficiency improvement; that needs the preregistered stratified comparison.",
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
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        path = Path(args.manifest).resolve()
        result = evaluate_manifest(load_manifest(path), path)
        write_or_print(result, args.output)
        return 0 if result["stable_v2_ready"] else 1
    except (ReleaseGateError, team_metrics.LedgerError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
