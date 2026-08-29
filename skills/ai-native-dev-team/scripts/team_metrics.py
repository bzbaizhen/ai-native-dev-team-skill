#!/usr/bin/env python3
"""Optional local prospective delivery metrics, implemented with the standard library."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
from statistics import mean, median
import sys
from typing import Any, Iterable


EVENT_SCHEMA_VERSION = "team-metrics-event-v1"
SNAPSHOT_SCHEMA_VERSION = "team-metrics-snapshot-v1"
AUDIT_SCHEMA_VERSION = "team-metrics-audit-v1"
COMPARE_SCHEMA_VERSION = "team-metrics-compare-v1"

# Windows device and NT namespace paths must never become ordinary path anchors.
WINDOWS_NAMESPACE_PREFIXES = (
    "\\\\?\\",
    "\\\\.\\",
    "\\??\\",
    "\\\\??\\",
    "//?/",
    "//./",
    "/??/",
    "//??/",
)

LIFECYCLE = (
    "task_ready",
    "worker_started",
    "dev_complete",
    "qa_complete",
    "accepted",
    "blocked",
    "reopened",
    "cancelled",
)
EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "task_id",
    "event",
    "at",
    "ledger_writer",
    "routing",
    "material",
    "writer",
    "candidate",
    "validation",
    "rollback",
    "owner_approval",
    "integration_backlog_reason",
    "reason",
    "observations",
}
ROUTING_FIELDS = {
    "layer",
    "complexity",
    "risk",
    "capability",
    "reasoning_tier",
}
OBSERVATION_FIELDS = (
    "model",
    "provider",
    "reasoning",
    "input_tokens",
    "output_tokens",
    "cost",
    "cost_currency",
)
WORKER_CONTEXT_FIELDS = (
    "skill_loaded",
    "repo_wide_search_used",
    "out_of_scope_reads",
)
HARD_GATE_CODES = {
    "UNAPPROVED_WRITER",
    "WRITER_LOADED_FULL_TEAM_SKILL",
    "WRITER_OUT_OF_SCOPE_READS",
    "INVALID_WRITER_PATH",
    "OVERLAPPING_PATH_OWNERSHIP",
    "NEW_WRITER_WITH_INTEGRATION_BACKLOG",
    "MATERIAL_ACCEPTANCE_WITHOUT_SAME_CANDIDATE_INDEPENDENT_VALIDATION",
    "ACCEPTANCE_WITHOUT_EXACT_IDENTITY_OR_EXECUTABLE_ROLLBACK",
    "R3_WITHOUT_OWNER_APPROVAL",
    "EVIDENCE_REUSE_AFTER_REOPEN_OR_CANDIDATE_CHANGE",
}
ALLOWED_TRANSITIONS = {
    None: {"task_ready"},
    "task_ready": {"worker_started", "dev_complete", "blocked", "cancelled"},
    "worker_started": {"dev_complete", "blocked", "cancelled"},
    "dev_complete": {"qa_complete", "accepted", "reopened", "blocked", "cancelled"},
    "qa_complete": {"accepted", "reopened", "blocked", "cancelled"},
    "blocked": {"reopened", "cancelled"},
    "reopened": {"worker_started", "dev_complete", "blocked", "cancelled"},
    "accepted": set(),
    "cancelled": set(),
}


class MetricsError(ValueError):
    """Raise a controlled input or ledger error."""


def _is_nonempty_string(value: Any) -> bool:
    return type(value) is str and bool(value.strip())


def _require_nonempty_string(event: dict[str, Any], field: str) -> None:
    if not _is_nonempty_string(event.get(field)):
        raise MetricsError(f"{field} must be a non-empty string")


def _parse_time(value: Any) -> datetime:
    if not _is_nonempty_string(value):
        raise MetricsError("at must be an ISO-8601 timestamp with a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetricsError(f"at is not ISO-8601: {value}") from exc
    if parsed.tzinfo is None:
        raise MetricsError("at must include a timezone")
    return parsed


def _validate_routing(value: Any) -> None:
    if type(value) is not dict or set(value) != ROUTING_FIELDS:
        raise MetricsError("routing must contain exactly the selected routing fields")
    allowed = {
        "layer": {"core", "controlled"},
        "complexity": {"C0", "C1", "C2", "C3"},
        "risk": {"R0", "R1", "R2", "R3"},
        "capability": {
            "main-agent",
            "economy",
            "standard",
            "advanced",
            "frontier",
        },
        "reasoning_tier": {"current", "low", "medium", "high", "max"},
    }
    for field, choices in allowed.items():
        if value.get(field) not in choices:
            raise MetricsError(f"routing.{field} is invalid")


def _validate_writer(value: Any) -> None:
    expected_fields = {"id", "approved", "paths", *WORKER_CONTEXT_FIELDS}
    if type(value) is not dict or set(value) != expected_fields:
        raise MetricsError(
            "writer must contain id, approved, paths, and worker context fields"
        )
    if not _is_nonempty_string(value.get("id")):
        raise MetricsError("writer.id must be a non-empty string")
    if type(value.get("approved")) is not bool:
        raise MetricsError("writer.approved must be boolean")
    paths = value.get("paths")
    if type(paths) is not list or not paths or not all(_is_nonempty_string(path) for path in paths):
        raise MetricsError("writer.paths must be a non-empty list of paths")
    for field in WORKER_CONTEXT_FIELDS:
        if type(value.get(field)) is not bool:
            raise MetricsError(f"writer.{field} must be boolean")


def _worker_context(writer: dict[str, Any]) -> dict[str, bool]:
    return {field: writer[field] for field in WORKER_CONTEXT_FIELDS}


def _context_saving_claim(worker_context: dict[str, bool] | None) -> bool | None:
    if worker_context is None:
        return None
    return not worker_context["repo_wide_search_used"]


def _context_snapshot(worker_context: dict[str, bool] | None) -> dict[str, bool] | None:
    if worker_context is None:
        return None
    return {
        **worker_context,
        "context_saving_claim": _context_saving_claim(worker_context),
    }


def _validate_candidate(value: Any) -> None:
    if type(value) is not dict or set(value) != {"id", "stable_identity"}:
        raise MetricsError("candidate must contain id and stable_identity")
    if not _is_nonempty_string(value.get("id")):
        raise MetricsError("candidate.id must be a non-empty immutable identity")
    stable_identity = value.get("stable_identity")
    if stable_identity is not None and not _is_nonempty_string(stable_identity):
        raise MetricsError("candidate.stable_identity must be null or a non-empty string")


def _validate_validation(value: Any) -> None:
    if type(value) is not dict or set(value) != {
        "independent",
        "same_candidate",
        "result",
        "evidence_reused",
    }:
        raise MetricsError(
            "validation must contain independent, same_candidate, result, and evidence_reused"
        )
    if type(value.get("independent")) is not bool:
        raise MetricsError("validation.independent must be boolean")
    if type(value.get("same_candidate")) is not bool:
        raise MetricsError("validation.same_candidate must be boolean")
    if value.get("result") not in {"passed", "failed", "blocked"}:
        raise MetricsError("validation.result is invalid")
    if type(value.get("evidence_reused")) is not bool:
        raise MetricsError("validation.evidence_reused must be boolean")


def _validate_rollback(value: Any) -> None:
    if type(value) is not dict or set(value) != {"executable", "command"}:
        raise MetricsError("rollback must contain executable and command")
    if type(value.get("executable")) is not bool:
        raise MetricsError("rollback.executable must be boolean")
    command = value.get("command")
    if command is not None and not _is_nonempty_string(command):
        raise MetricsError("rollback.command must be null or a non-empty string")


def _validate_observations(value: Any) -> None:
    if type(value) is not dict or not set(value) <= set(OBSERVATION_FIELDS):
        raise MetricsError("observations contains an unsupported field")
    for field in {"model", "provider", "reasoning", "cost_currency"}:
        item = value.get(field)
        if item is not None and not _is_nonempty_string(item):
            raise MetricsError(f"observations.{field} must be null or a non-empty string")
    for field in {"input_tokens", "output_tokens"}:
        item = value.get(field)
        if item is not None and (type(item) is not int or item < 0):
            raise MetricsError(f"observations.{field} must be null or a non-negative integer")
    cost = value.get("cost")
    if cost is not None and (
        type(cost) not in {int, float} or isinstance(cost, bool) or cost < 0 or not math.isfinite(cost)
    ):
        raise MetricsError("observations.cost must be null or a finite non-negative number")


def validate_event(event: Any) -> dict[str, Any]:
    """Validate one ledger event without inferring absent observations."""

    if type(event) is not dict:
        raise MetricsError("event must be a JSON object")
    extra = set(event) - EVENT_FIELDS
    if extra:
        raise MetricsError(f"event contains unsupported fields: {', '.join(sorted(extra))}")
    for field in ("schema_version", "task_id", "event", "at", "ledger_writer"):
        if field not in event:
            raise MetricsError(f"event is missing {field}")
    if event["schema_version"] != EVENT_SCHEMA_VERSION:
        raise MetricsError(f"schema_version must be {EVENT_SCHEMA_VERSION}")
    _require_nonempty_string(event, "task_id")
    if event["event"] not in LIFECYCLE:
        raise MetricsError("event is not a supported lifecycle value")
    _parse_time(event["at"])
    if event["ledger_writer"] != "main-agent":
        raise MetricsError("only the main-agent may write this ledger")
    if "event_id" in event:
        _require_nonempty_string(event, "event_id")
    if "routing" in event:
        _validate_routing(event["routing"])
    if "material" in event and type(event["material"]) is not bool:
        raise MetricsError("material must be boolean")
    if "writer" in event:
        _validate_writer(event["writer"])
    if "candidate" in event:
        _validate_candidate(event["candidate"])
    if "validation" in event:
        _validate_validation(event["validation"])
    if "rollback" in event:
        _validate_rollback(event["rollback"])
    for field in ("owner_approval",):
        if field in event and event[field] is not None and type(event[field]) is not bool:
            raise MetricsError(f"{field} must be boolean or null")
    for field in ("integration_backlog_reason", "reason"):
        if field in event and event[field] is not None and not _is_nonempty_string(event[field]):
            raise MetricsError(f"{field} must be null or a non-empty string")
    if "observations" in event:
        _validate_observations(event["observations"])
    if event["event"] == "task_ready":
        if "routing" not in event or type(event.get("material")) is not bool:
            raise MetricsError("task_ready requires routing and material")
    return event


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MetricsError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MetricsError(f"invalid JSON in {path}: {exc}") from exc


def load_ledger(path: Path) -> list[Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MetricsError(f"cannot read ledger {path}: {exc}") from exc
    events: list[Any] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise MetricsError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
    return events


def record_event(ledger: Path, event: Any) -> None:
    validate_event(event)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    try:
        with ledger.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise MetricsError(f"cannot append ledger {ledger}: {exc}") from exc


def _new_state(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": None,
        "routing": None,
        "material": None,
        "task_ready_at": None,
        "dev_complete_at": None,
        "accepted_at": None,
        "last_at": None,
        "clock": None,
        "active_minutes": 0.0,
        "governance_minutes": 0.0,
        "candidate_id": None,
        "last_validation": None,
        "evidence_invalidated": False,
        "reopen_count": 0,
        "first_pass_independent_validation": None,
        "active_paths": set(),
        "worker_context": None,
        "observed": {field: None for field in OBSERVATION_FIELDS},
    }


def _violation(
    violations: list[dict[str, Any]],
    code: str,
    task_id: str | None,
    event_index: int,
    message: str,
) -> None:
    violations.append(
        {
            "code": code,
            "hard_gate": code in HARD_GATE_CODES,
            "task_id": task_id,
            "event_index": event_index,
            "message": message,
        }
    )


def _clean_path_component(raw_component: str, *, allow_navigation: bool) -> str:
    if allow_navigation and raw_component in {".", ".."}:
        return raw_component
    if not allow_navigation and raw_component in {".", ".."}:
        raise MetricsError("UNC server/share components cannot be dot navigation")

    component = raw_component.rstrip(" .")
    if not component:
        raise MetricsError(
            "path component becomes empty after trimming trailing spaces/dots"
        )
    if ":" in component:
        raise MetricsError("path component contains an NTFS alternate-data-stream separator")
    return component.casefold()


def _canonical_path_identity(path: str) -> tuple[str, tuple[str, ...]]:
    if type(path) is not str or not path.strip():
        raise MetricsError("writer path must be a non-empty string")

    unified = path.replace("\\", "/")
    if any(path.startswith(prefix) for prefix in WINDOWS_NAMESPACE_PREFIXES) or any(
        unified.startswith(prefix.replace("\\", "/"))
        for prefix in WINDOWS_NAMESPACE_PREFIXES
    ):
        raise MetricsError(
            "writer path uses a Windows device or NT namespace prefix"
        )

    anchor: str
    raw_components: list[str]
    if (
        len(unified) >= 2
        and "A" <= unified[0].upper() <= "Z"
        and unified[1] == ":"
    ):
        drive = unified[0].casefold() + ":"
        rest = unified[2:]
        if rest.startswith("/"):
            anchor = drive + "/"
            rest = rest.lstrip("/")
        else:
            anchor = drive
        raw_components = [component for component in rest.split("/") if component]
    elif unified.startswith("//"):
        unc_components = [component for component in unified[2:].split("/") if component]
        if len(unc_components) < 2:
            raise MetricsError("UNC path must contain a server and share")
        server = _clean_path_component(unc_components[0], allow_navigation=False)
        share = _clean_path_component(unc_components[1], allow_navigation=False)
        anchor = f"//{server}/{share}"
        raw_components = unc_components[2:]
    elif unified.startswith("/"):
        anchor = "/"
        raw_components = [component for component in unified[1:].split("/") if component]
    else:
        anchor = ""
        raw_components = [component for component in unified.split("/") if component]

    components: list[str] = []
    for raw_component in raw_components:
        if raw_component == ".":
            continue
        if raw_component == "..":
            if not components:
                raise MetricsError("dot-dot traversal escapes the path root")
            components.pop()
            continue
        components.append(_clean_path_component(raw_component, allow_navigation=True))

    if anchor == "":
        normalized = "/".join(components) or "."
    elif anchor == "/":
        normalized = anchor + "/".join(components)
    elif anchor.startswith("//"):
        normalized = anchor + ("/" + "/".join(components) if components else "")
    elif anchor.endswith("/"):
        normalized = anchor + "/".join(components)
    else:
        normalized = anchor + "/".join(components)
    return normalized, (anchor, *components)


def _normalize_path(path: str) -> str:
    return _canonical_path_identity(path)[0]


def _path_parts(path: str) -> tuple[str, ...]:
    return _canonical_path_identity(path)[1]


def _paths_overlap(left: str, right: str) -> bool:
    left_parts = _path_parts(left)
    right_parts = _path_parts(right)
    shorter, longer = sorted((left_parts, right_parts), key=len)
    return longer[: len(shorter)] == shorter


def _release_paths(state: dict[str, Any], active_paths: dict[str, tuple[str, str]]) -> None:
    for path in state["active_paths"]:
        if active_paths.get(path, (None, None))[0] == state["task_id"]:
            active_paths.pop(path, None)
    state["active_paths"] = set()


def _candidate_id(event: dict[str, Any]) -> str | None:
    candidate = event.get("candidate")
    if type(candidate) is dict and _is_nonempty_string(candidate.get("id")):
        return candidate["id"]
    return None


def _has_executable_rollback(event: dict[str, Any]) -> bool:
    rollback = event.get("rollback")
    return bool(
        type(rollback) is dict
        and rollback.get("executable") is True
        and _is_nonempty_string(rollback.get("command"))
    )


def _is_actual_observation(value: Any) -> bool:
    return value is not None and value != "unknown"


def _advance_clock(
    state: dict[str, Any],
    at: datetime,
    violations: list[dict[str, Any]],
    event_index: int,
) -> None:
    prior = state["last_at"]
    if prior is not None:
        elapsed = (at - prior).total_seconds() / 60
        if elapsed < 0:
            _violation(
                violations,
                "EVENT_TIME_OUT_OF_ORDER",
                state["task_id"],
                event_index,
                "Task event time moved backwards.",
            )
        elif state["clock"] in {"active", "governance"}:
            state[f"{state['clock']}_minutes"] += elapsed
    if prior is None or at >= prior:
        state["last_at"] = at


def replay_events(events: Iterable[Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Replay the ledger and return task state plus audit findings."""

    states: dict[str, dict[str, Any]] = {}
    violations: list[dict[str, Any]] = []
    active_paths: dict[str, tuple[str, str]] = {}

    for event_index, raw_event in enumerate(events, start=1):
        try:
            event = validate_event(raw_event)
        except MetricsError as exc:
            task_id = raw_event.get("task_id") if type(raw_event) is dict else None
            _violation(
                violations,
                "INVALID_EVENT",
                task_id if _is_nonempty_string(task_id) else None,
                event_index,
                str(exc),
            )
            continue

        task_id = event["task_id"]
        state = states.setdefault(task_id, _new_state(task_id))
        event_type = event["event"]
        at = _parse_time(event["at"])
        _advance_clock(state, at, violations, event_index)
        if event_type not in ALLOWED_TRANSITIONS[state["status"]]:
            _violation(
                violations,
                "INVALID_LIFECYCLE_TRANSITION",
                task_id,
                event_index,
                f"{event_type} cannot follow {state['status']}.",
            )

        observations = event.get("observations")
        if type(observations) is dict:
            for field in OBSERVATION_FIELDS:
                value = observations.get(field)
                if _is_actual_observation(value):
                    state["observed"][field] = value

        if event_type == "task_ready":
            state["routing"] = event["routing"]
            state["material"] = event["material"]
            state["task_ready_at"] = at

        elif event_type == "worker_started":
            backlog = [
                other_id
                for other_id, other in states.items()
                if other_id != task_id and other["status"] in {"dev_complete", "qa_complete"}
            ]
            if backlog and not _is_nonempty_string(event.get("integration_backlog_reason")):
                _violation(
                    violations,
                    "NEW_WRITER_WITH_INTEGRATION_BACKLOG",
                    task_id,
                    event_index,
                    "A new Writer started while another task awaited integration without a reason.",
                )
            writer = event.get("writer")
            canonical_paths: set[str] = set()
            invalid_writer_path = False
            if type(writer) is dict:
                worker_context = _worker_context(writer)
                state["worker_context"] = worker_context
                if worker_context["skill_loaded"]:
                    _violation(
                        violations,
                        "WRITER_LOADED_FULL_TEAM_SKILL",
                        task_id,
                        event_index,
                        "Writer loaded the full team Skill.",
                    )
                if worker_context["out_of_scope_reads"]:
                    _violation(
                        violations,
                        "WRITER_OUT_OF_SCOPE_READS",
                        task_id,
                        event_index,
                        "Writer read out-of-scope content.",
                    )
                for raw_path in writer["paths"]:
                    try:
                        canonical_paths.add(_normalize_path(raw_path))
                    except MetricsError as exc:
                        _violation(
                            violations,
                            "INVALID_WRITER_PATH",
                            task_id,
                            event_index,
                            f"Path {raw_path!r} is invalid: {exc}",
                        )
                        invalid_writer_path = True
            if type(writer) is not dict or writer.get("approved") is not True:
                _violation(
                    violations,
                    "UNAPPROVED_WRITER",
                    task_id,
                    event_index,
                    "Writer start lacks explicit approval.",
                )
            else:
                writer_id = writer["id"]
                leased_paths = set() if invalid_writer_path else canonical_paths
                for path in sorted(leased_paths):
                    existing = next(
                        (
                            (existing_path, owner)
                            for existing_path, owner in sorted(active_paths.items())
                            if owner[0] != task_id and _paths_overlap(path, existing_path)
                        ),
                        None,
                    )
                    if existing:
                        existing_path, owner = existing
                        _violation(
                            violations,
                            "OVERLAPPING_PATH_OWNERSHIP",
                            task_id,
                            event_index,
                            f"Path {path} overlaps active lease {existing_path} owned by task {owner[0]}.",
                        )
                    else:
                        active_paths[path] = (task_id, writer_id)
                state["active_paths"] = leased_paths

        elif event_type == "dev_complete":
            _release_paths(state, active_paths)
            candidate_id = _candidate_id(event)
            if candidate_id is not None:
                if state["candidate_id"] is not None and candidate_id != state["candidate_id"]:
                    state["evidence_invalidated"] = True
                state["candidate_id"] = candidate_id
            state["last_validation"] = None
            state["dev_complete_at"] = at

        elif event_type == "qa_complete":
            candidate_id = _candidate_id(event)
            validation = event.get("validation")
            matches_current_candidate = (
                candidate_id is not None and candidate_id == state["candidate_id"]
            )
            if not matches_current_candidate:
                _violation(
                    violations,
                    "VALIDATION_CANDIDATE_MISMATCH",
                    task_id,
                    event_index,
                    "Validation does not identify the current dev_complete candidate.",
                )
            if type(validation) is dict:
                if validation["evidence_reused"] and state["evidence_invalidated"]:
                    _violation(
                        violations,
                        "EVIDENCE_REUSE_AFTER_REOPEN_OR_CANDIDATE_CHANGE",
                        task_id,
                        event_index,
                        "Validation reused evidence after a reopen or candidate change.",
                    )
                state["last_validation"] = {
                    "candidate_id": candidate_id,
                    **validation,
                }
                if state["first_pass_independent_validation"] is None:
                    state["first_pass_independent_validation"] = bool(
                        matches_current_candidate
                        and validation["independent"]
                        and validation["same_candidate"]
                        and validation["result"] == "passed"
                    )
                if (
                    matches_current_candidate
                    and validation["independent"]
                    and validation["same_candidate"]
                    and not validation["evidence_reused"]
                ):
                    state["evidence_invalidated"] = False

        elif event_type == "reopened":
            _release_paths(state, active_paths)
            state["reopen_count"] += 1
            state["evidence_invalidated"] = True
            state["last_validation"] = None

        elif event_type in {"blocked", "cancelled"}:
            _release_paths(state, active_paths)

        elif event_type == "accepted":
            _release_paths(state, active_paths)
            candidate = event.get("candidate")
            candidate_id = _candidate_id(event)
            has_exact_identity = bool(
                candidate_id
                and candidate_id == state["candidate_id"]
                and type(candidate) is dict
                and _is_nonempty_string(candidate.get("stable_identity"))
            )
            if not has_exact_identity or not _has_executable_rollback(event):
                _violation(
                    violations,
                    "ACCEPTANCE_WITHOUT_EXACT_IDENTITY_OR_EXECUTABLE_ROLLBACK",
                    task_id,
                    event_index,
                    "Acceptance needs the current candidate, stable identity, and executable rollback.",
                )
            validation = state["last_validation"]
            validation_supports_acceptance = bool(
                type(validation) is dict
                and validation.get("candidate_id") == candidate_id
                and validation.get("independent") is True
                and validation.get("same_candidate") is True
                and validation.get("result") == "passed"
                and not state["evidence_invalidated"]
            )
            if state["material"] is True and not validation_supports_acceptance:
                _violation(
                    violations,
                    "MATERIAL_ACCEPTANCE_WITHOUT_SAME_CANDIDATE_INDEPENDENT_VALIDATION",
                    task_id,
                    event_index,
                    "Material acceptance lacks a current independent same-candidate pass.",
                )
            routing = state["routing"] or {}
            if routing.get("risk") == "R3" and event.get("owner_approval") is not True:
                _violation(
                    violations,
                    "R3_WITHOUT_OWNER_APPROVAL",
                    task_id,
                    event_index,
                    "R3 acceptance lacks explicit Owner approval.",
                )
            state["accepted_at"] = at

        state["status"] = event_type
        state["clock"] = {
            "task_ready": "governance",
            "worker_started": "active",
            "dev_complete": "governance",
            "qa_complete": "governance",
            "reopened": "governance",
        }.get(event_type)

    return states, violations


def build_audit(events: Iterable[Any]) -> dict[str, Any]:
    event_list = list(events)
    states, violations = replay_events(event_list)
    hard_gate_violations = [item for item in violations if item["hard_gate"]]
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "event_count": len(event_list),
        "task_count": len(states),
        "passed": not violations,
        "hard_gate_passed": not hard_gate_violations,
        "hard_gate_violation_count": len(hard_gate_violations),
        "violations": violations,
        "context": {
            "worker_context": {
                task_id: _context_snapshot(states[task_id]["worker_context"])
                for task_id in sorted(states)
            }
        },
    }


def _round_minutes(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _duration(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return _round_minutes((end - start).total_seconds() / 60)


def _descriptive(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": _round_minutes(mean(values)),
        "median": _round_minutes(median(values)),
        "min": _round_minutes(min(values)),
        "max": _round_minutes(max(values)),
    }


def build_snapshot(events: list[Any], label: str | None = None) -> dict[str, Any]:
    states, violations = replay_events(events)
    task_rows: list[dict[str, Any]] = []
    cycle_values: list[float] = []
    integration_values: list[float] = []
    active_values: list[float] = []
    governance_values: list[float] = []
    first_pass_values: list[bool] = []
    reopened_task_ids: list[str] = []

    for task_id in sorted(states):
        state = states[task_id]
        completed = state["accepted_at"] is not None
        cycle = _duration(state["task_ready_at"], state["accepted_at"]) if completed else None
        integration_wait = (
            _duration(state["dev_complete_at"], state["accepted_at"]) if completed else None
        )
        active_minutes = _round_minutes(state["active_minutes"]) if completed else None
        governance_minutes = _round_minutes(state["governance_minutes"]) if completed else None
        if cycle is not None:
            cycle_values.append(cycle)
        if integration_wait is not None:
            integration_values.append(integration_wait)
        if active_minutes is not None:
            active_values.append(active_minutes)
        if governance_minutes is not None:
            governance_values.append(governance_minutes)
        if state["first_pass_independent_validation"] is not None:
            first_pass_values.append(state["first_pass_independent_validation"])
        if state["reopen_count"]:
            reopened_task_ids.append(task_id)
        task_rows.append(
            {
                "task_id": task_id,
                "status": state["status"],
                "routing": state["routing"],
                "task_ready_to_accepted_minutes": cycle,
                "dev_complete_to_accepted_minutes": integration_wait,
                "active_minutes": active_minutes,
                "governance_minutes": governance_minutes,
                "first_pass_independent_validation": state[
                    "first_pass_independent_validation"
                ],
                "reopened": bool(state["reopen_count"]),
                "reopen_count": state["reopen_count"],
                "worker_context": _context_snapshot(state["worker_context"]),
                "observed": state["observed"],
            }
        )

    passed_first_pass = sum(first_pass_values)
    task_count = len(task_rows)
    hard_gate_violations = [item for item in violations if item["hard_gate"]]
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "label": label,
        "event_count": len(events),
        "tasks": task_rows,
        "summary": {
            "task_count": task_count,
            "accepted_task_count": sum(row["status"] == "accepted" for row in task_rows),
            "task_ready_to_accepted_minutes": _descriptive(cycle_values),
            "dev_complete_to_accepted_minutes": _descriptive(integration_values),
            "active_minutes": _descriptive(active_values),
            "governance_minutes": _descriptive(governance_values),
            "first_pass_independent_validation": {
                "known_task_count": len(first_pass_values),
                "passed_task_count": passed_first_pass,
                "rate": (
                    round(passed_first_pass / len(first_pass_values), 6)
                    if first_pass_values
                    else None
                ),
            },
            "reopen_visibility": {
                "reopened_task_count": len(reopened_task_ids),
                "reopen_event_count": sum(row["reopen_count"] for row in task_rows),
                "reopen_rate": (
                    round(len(reopened_task_ids) / task_count, 6) if task_count else None
                ),
                "reopened_task_ids": reopened_task_ids,
            },
            "hard_gate_violations": {
                "count": len(hard_gate_violations),
                "codes": sorted({item["code"] for item in hard_gate_violations}),
            },
        },
        "audit": {
            "passed": not violations,
            "hard_gate_passed": not hard_gate_violations,
            "violation_count": len(violations),
        },
    }


def _load_snapshot(path: Path) -> dict[str, Any]:
    snapshot = _load_json(path)
    if type(snapshot) is not dict or snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise MetricsError(f"{path} is not a {SNAPSHOT_SCHEMA_VERSION} snapshot")
    if type(snapshot.get("summary")) is not dict:
        raise MetricsError(f"{path} is missing snapshot summary")
    return snapshot


def _mean_value(snapshot: dict[str, Any], metric: str) -> float | None:
    value = snapshot["summary"].get(metric)
    if type(value) is not dict:
        return None
    result = value.get("mean")
    return result if type(result) in {int, float} and not isinstance(result, bool) else None


def _rate_value(snapshot: dict[str, Any], section: str, field: str) -> float | None:
    value = snapshot["summary"].get(section)
    if type(value) is not dict:
        return None
    result = value.get(field)
    return result if type(result) in {int, float} and not isinstance(result, bool) else None


def _delta(left: float | None, right: float | None) -> float | None:
    return _round_minutes(right - left) if left is not None and right is not None else None


def compare_snapshots(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Compare two snapshots without adding a threshold or qualification rule."""

    cycle_left = _mean_value(left, "task_ready_to_accepted_minutes")
    cycle_right = _mean_value(right, "task_ready_to_accepted_minutes")
    wait_left = _mean_value(left, "dev_complete_to_accepted_minutes")
    wait_right = _mean_value(right, "dev_complete_to_accepted_minutes")
    active_left = _mean_value(left, "active_minutes")
    active_right = _mean_value(right, "active_minutes")
    governance_left = _mean_value(left, "governance_minutes")
    governance_right = _mean_value(right, "governance_minutes")
    first_pass_left = _rate_value(left, "first_pass_independent_validation", "rate")
    first_pass_right = _rate_value(right, "first_pass_independent_validation", "rate")
    reopen_left = _rate_value(left, "reopen_visibility", "reopen_rate")
    reopen_right = _rate_value(right, "reopen_visibility", "reopen_rate")
    hard_left = left["summary"].get("hard_gate_violations", {}).get("count")
    hard_right = right["summary"].get("hard_gate_violations", {}).get("count")
    if type(hard_left) is not int:
        hard_left = None
    if type(hard_right) is not int:
        hard_right = None
    return {
        "schema_version": COMPARE_SCHEMA_VERSION,
        "descriptive_only": True,
        "note": "No fixed threshold or qualification decision is applied.",
        "left_label": left.get("label"),
        "right_label": right.get("label"),
        "deltas": {
            "accepted_task_count": _delta(
                left["summary"].get("accepted_task_count"),
                right["summary"].get("accepted_task_count"),
            ),
            "task_ready_to_accepted_mean_minutes": _delta(cycle_left, cycle_right),
            "dev_complete_to_accepted_mean_minutes": _delta(wait_left, wait_right),
            "active_mean_minutes": _delta(active_left, active_right),
            "governance_mean_minutes": _delta(governance_left, governance_right),
            "first_pass_independent_validation_rate": _delta(first_pass_left, first_pass_right),
            "reopen_rate": _delta(reopen_left, reopen_right),
            "hard_gate_violation_count": _delta(hard_left, hard_right),
        },
    }


def _emit(payload: dict[str, Any], output: Path | None) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8", newline="\n")
    print(serialized, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Optional local prospective delivery metrics (standard library only)."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    record = commands.add_parser("record", help="append one main-agent event")
    record.add_argument("--ledger", type=Path, required=True)
    record.add_argument("--event-file", type=Path, required=True)

    snapshot = commands.add_parser("snapshot", help="create a descriptive task snapshot")
    snapshot.add_argument("--ledger", type=Path, required=True)
    snapshot.add_argument("--output", type=Path)
    snapshot.add_argument("--label")

    audit = commands.add_parser("audit", help="audit local ledger hard gates")
    audit.add_argument("--ledger", type=Path, required=True)
    audit.add_argument("--output", type=Path)

    compare = commands.add_parser("compare", help="compare two descriptive snapshots")
    compare.add_argument("--left", type=Path, required=True)
    compare.add_argument("--right", type=Path, required=True)
    compare.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "record":
            event = _load_json(args.event_file)
            record_event(args.ledger, event)
            _emit(
                {
                    "status": "recorded",
                    "ledger": str(args.ledger),
                    "task_id": event["task_id"],
                    "event": event["event"],
                },
                None,
            )
        elif args.command == "snapshot":
            events = load_ledger(args.ledger)
            _emit(build_snapshot(events, args.label), args.output)
        elif args.command == "audit":
            events = load_ledger(args.ledger)
            _emit(build_audit(events), args.output)
        elif args.command == "compare":
            _emit(compare_snapshots(_load_snapshot(args.left), _load_snapshot(args.right)), args.output)
        else:
            raise MetricsError(f"unsupported command: {args.command}")
    except MetricsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
