#!/usr/bin/env python3
"""Evaluate the preregistered first-five-task gate for stable V2.0."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import team_metrics  # noqa: E402


FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
REQUIRED_TRIAL_FIELDS = {
    "trial_id",
    "project_alias",
    "ledger",
    "task_id",
    "skill_candidate_commit",
    "candidate_commit",
    "stable_commit",
    "comparable",
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
    "required_comparable_tasks",
    "trials",
}
TRIAL_FIELDS = REQUIRED_TRIAL_FIELDS | {"exclusion_reason", "notes"}


class ReleaseGateError(ValueError):
    pass


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

    required = {
        "schema_version",
        "candidate_version",
        "candidate_commit",
        "required_comparable_tasks",
        "trials",
    }
    missing = required - data.keys()
    if missing:
        raise ReleaseGateError(f"manifest missing fields: {sorted(missing)}")
    if data["schema_version"] != "2.0":
        raise ReleaseGateError("manifest schema_version must be 2.0")
    if not isinstance(data["candidate_version"], str) or not data["candidate_version"].strip():
        raise ReleaseGateError("candidate_version must be a non-empty string")
    if not FULL_SHA.fullmatch(str(data["candidate_commit"])):
        raise ReleaseGateError("candidate_commit must be a full 40-character SHA")
    required_count = data["required_comparable_tasks"]
    if isinstance(required_count, bool) or not isinstance(required_count, int) or required_count < 5:
        raise ReleaseGateError("required_comparable_tasks must be an integer of at least 5")
    if not isinstance(data["trials"], list):
        raise ReleaseGateError("trials must be an array")

    seen: set[str] = set()
    for index, trial in enumerate(data["trials"]):
        if not isinstance(trial, dict):
            raise ReleaseGateError(f"trials[{index}] must be an object")
        unknown_trial = set(trial) - TRIAL_FIELDS
        if unknown_trial:
            raise ReleaseGateError(
                f"trials[{index}] contains unknown fields: {sorted(unknown_trial)}"
            )
        missing_trial = REQUIRED_TRIAL_FIELDS - trial.keys()
        if missing_trial:
            raise ReleaseGateError(
                f"trials[{index}] missing fields: {sorted(missing_trial)}"
            )
        if not isinstance(trial["trial_id"], str) or not trial["trial_id"].strip():
            raise ReleaseGateError(f"trials[{index}].trial_id must be non-empty")
        if trial["trial_id"] in seen:
            raise ReleaseGateError(f"duplicate trial_id: {trial['trial_id']}")
        seen.add(trial["trial_id"])
        for field in ("project_alias", "ledger", "task_id"):
            if not isinstance(trial[field], str) or not trial[field].strip():
                raise ReleaseGateError(f"trials[{index}].{field} must be non-empty")
        for field in ("skill_candidate_commit", "candidate_commit", "stable_commit"):
            if not FULL_SHA.fullmatch(str(trial[field])):
                raise ReleaseGateError(
                    f"trials[{index}].{field} must be a full 40-character SHA"
                )
        boolean_fields = {
            "comparable",
            "critical_defect_escape",
            "material_quality_regression",
            "scope_violation",
            "write_conflict",
            "recovery_executable",
        }
        for field in boolean_fields:
            if not isinstance(trial[field], bool):
                raise ReleaseGateError(f"trials[{index}].{field} must be boolean")
        if "exclusion_reason" in trial and (
            not isinstance(trial["exclusion_reason"], str)
            or not trial["exclusion_reason"].strip()
        ):
            raise ReleaseGateError(
                f"trials[{index}].exclusion_reason must be a non-empty string"
            )
        if "notes" in trial and (
            not isinstance(trial["notes"], list)
            or any(not isinstance(note, str) for note in trial["notes"])
        ):
            raise ReleaseGateError(f"trials[{index}].notes must be a string array")
        if not trial["comparable"] and not str(trial.get("exclusion_reason", "")).strip():
            raise ReleaseGateError(
                f"trials[{index}] is non-comparable without exclusion_reason"
            )
    return data


def resolve_ledger(manifest_path: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (manifest_path.parent / path).resolve()


def issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def evaluate_trial(
    trial: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    ledger = resolve_ledger(manifest_path, trial["ledger"])
    task_events: list[dict[str, Any]] = []

    if trial["skill_candidate_commit"].casefold() != manifest["candidate_commit"].casefold():
        issues.append(
            issue(
                "skill_candidate_mismatch",
                "trial did not use the manifest candidate Commit",
            )
        )

    try:
        all_events = team_metrics.load_events(ledger)
        task_events = [
            event for event in all_events if event["task_id"] == trial["task_id"]
        ]
    except (team_metrics.LedgerError, OSError) as exc:
        issues.append(issue("ledger_error", str(exc)))

    ready_events = [event for event in task_events if event["event"] == "task_ready"]
    accepted_events = [event for event in task_events if event["event"] == "accepted"]

    if len(ready_events) != 1:
        issues.append(
            issue("task_ready_count", f"expected 1 task_ready, found {len(ready_events)}")
        )
    if len(accepted_events) != 1:
        issues.append(
            issue("accepted_count", f"expected 1 accepted, found {len(accepted_events)}")
        )

    ready_timestamp: str | None = None
    if ready_events:
        ready_timestamp = ready_events[0]["timestamp"]

    if task_events:
        audit = team_metrics.audit_events(task_events)
        for violation in audit["violations"]:
            issues.append(
                issue(
                    f"hard_gate:{violation['code']}",
                    violation["message"],
                )
            )
    else:
        audit = {"passed": False, "violations": []}

    if accepted_events:
        accepted = accepted_events[0]
        if accepted.get("commit", "").casefold() != trial["candidate_commit"].casefold():
            issues.append(
                issue(
                    "candidate_commit_mismatch",
                    "accepted event does not match trial candidate_commit",
                )
            )
        if accepted.get("stable_commit", "").casefold() != trial["stable_commit"].casefold():
            issues.append(
                issue(
                    "stable_commit_mismatch",
                    "accepted event does not match trial stable_commit",
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

    ledger_sha256: str | None = None
    if ledger.is_file():
        try:
            ledger_sha256 = hashlib.sha256(ledger.read_bytes()).hexdigest()
        except OSError as exc:
            issues.append(issue("ledger_hash_error", str(exc)))

    return {
        "trial_id": trial["trial_id"],
        "project_alias": trial["project_alias"],
        "task_id": trial["task_id"],
        "comparable": trial["comparable"],
        "ready_timestamp": ready_timestamp,
        "ledger_sha256": ledger_sha256,
        "issues": issues,
        "passed": not issues,
        "hard_gates_passed": audit["passed"],
        "quality_passed": not any(quality_failures.values()),
    }


def ready_sort_key(result: dict[str, Any]) -> tuple[datetime, str]:
    timestamp = result.get("ready_timestamp")
    if timestamp:
        try:
            return team_metrics.parse_time(timestamp), result["trial_id"]
        except team_metrics.LedgerError:
            pass
    return datetime.max.replace(tzinfo=timezone.utc), result["trial_id"]


def evaluate_manifest(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    evaluated = [
        evaluate_trial(trial, manifest, manifest_path)
        for trial in manifest["trials"]
    ]
    comparable = sorted(
        [result for result in evaluated if result["comparable"]],
        key=ready_sort_key,
    )
    required = manifest["required_comparable_tasks"]
    first_required = comparable[:required]
    enough = len(comparable) >= required
    ordering_complete = all(result["ready_timestamp"] for result in comparable)
    first_required_pass = (
        enough
        and ordering_complete
        and all(result["passed"] for result in first_required)
    )
    passed_comparable = sum(result["passed"] for result in comparable)

    return {
        "schema_version": "2.0",
        "candidate_version": manifest["candidate_version"],
        "candidate_commit": manifest["candidate_commit"],
        "required_comparable_tasks": required,
        "listed_trials": len(evaluated),
        "comparable_trials": len(comparable),
        "passed_comparable_trials": passed_comparable,
        "first_comparable_trial_ids": [
            result["trial_id"] for result in first_required
        ],
        "trials": evaluated,
        "gates": {
            "enough_comparable_tasks": enough,
            "comparable_order_established": ordering_complete,
            "first_comparable_tasks_pass": first_required_pass,
            "no_hard_gate_violations": enough
            and ordering_complete
            and all(result["hard_gates_passed"] for result in first_required),
            "no_material_quality_regression": enough
            and ordering_complete
            and all(result["quality_passed"] for result in first_required),
        },
        "stable_v2_ready": enough and first_required_pass,
        "formal_efficiency_sample_size_ready": passed_comparable >= 15,
        "limitations": [
            "This gate proves recorded mechanism and quality fields only.",
            "It does not prove an efficiency improvement or verify omitted external tasks.",
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
    except ReleaseGateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
