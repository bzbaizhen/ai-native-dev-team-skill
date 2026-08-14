#!/usr/bin/env python3
"""Record and audit prospective AI-native delivery metrics using only stdlib."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "2.0"
EVENTS = {
    "task_ready", "worker_started", "dev_complete", "qa_complete", "accepted",
    "blocked", "reopened", "cancelled",
}
COMPLEXITIES = {"C0", "C1", "C2", "C3"}
RISKS = {"R0", "R1", "R2", "R3"}
TOPOLOGIES = {"no-delegation", "single-worker", "task-cell", "team-required"}
PROFILES = {"lean", "controlled", "strict"}
CAPABILITIES = {"economy", "standard", "advanced", "frontier", "main-agent"}
REASONING = {"low", "medium", "high", "max", "current"}
QA_RESULTS = {"PASSED", "FAILED", "BLOCKED"}
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
ALLOWED_FIELDS = {
    "schema_version", "timestamp", "task_id", "event", "actor", "complexity",
    "risk", "topology", "governance_profile", "material_behavior_change",
    "release_trial_registration_sequence", "skill_candidate_commit",
    "release_trial_comparable", "v1_baseline_stratum",
    "capability_tier", "reasoning_tier", "actual_model", "escalation_reason",
    "approved_writer", "team_skill_loaded", "owned_paths",
    "backlog_override_reason", "commit", "stable_commit", "result",
    "independent_validation", "status_truth_match", "rollback_executable",
    "owner_approval", "reason", "active_minutes", "governance_minutes",
    "metadata",
}

EVENT_REQUIRED = {
    "task_ready": {
        "complexity", "risk", "topology", "governance_profile",
        "material_behavior_change",
    },
    "worker_started": {
        "actor", "capability_tier", "reasoning_tier", "approved_writer",
        "team_skill_loaded", "owned_paths",
    },
    "dev_complete": {"actor", "commit"},
    "qa_complete": {"commit", "result", "independent_validation"},
    "accepted": {
        "commit", "stable_commit", "status_truth_match",
        "rollback_executable", "owner_approval",
    },
    "blocked": {"reason"},
    "reopened": {"reason"},
    "cancelled": {"reason"},
}


class LedgerError(ValueError):
    pass


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LedgerError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise LedgerError(f"timestamp must include a timezone: {value}")
    return parsed


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_events(path: Path, *, missing_ok: bool = False) -> list[dict[str, Any]]:
    if not path.exists():
        if missing_ok:
            return []
        raise LedgerError(f"ledger does not exist: {path}")
    events: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(event, dict):
            raise LedgerError(f"{path}:{line_number}: event must be a JSON object")
        validate_event(event, location=f"{path}:{line_number}")
        event["_line"] = line_number
        events.append(event)
    return events


def validate_event(event: dict[str, Any], *, location: str = "event") -> None:
    unknown = set(event) - ALLOWED_FIELDS
    if unknown:
        raise LedgerError(f"{location}: unknown fields: {sorted(unknown)}")
    for field in ("schema_version", "timestamp", "task_id", "event"):
        if field not in event:
            raise LedgerError(f"{location}: missing required field {field}")
    if event["schema_version"] != SCHEMA_VERSION:
        raise LedgerError(f"{location}: unsupported schema_version {event['schema_version']!r}")
    if event["event"] not in EVENTS:
        raise LedgerError(f"{location}: unknown event {event['event']!r}")
    if not isinstance(event["task_id"], str) or not event["task_id"].strip():
        raise LedgerError(f"{location}: task_id must be a non-empty string")
    parse_time(event["timestamp"])

    missing = EVENT_REQUIRED[event["event"]] - event.keys()
    if missing:
        raise LedgerError(f"{location}: missing fields for {event['event']}: {sorted(missing)}")

    enums = (
        ("complexity", COMPLEXITIES), ("risk", RISKS),
        ("topology", TOPOLOGIES), ("governance_profile", PROFILES),
        ("capability_tier", CAPABILITIES), ("reasoning_tier", REASONING),
        ("result", QA_RESULTS),
    )
    for field, allowed in enums:
        if field in event and event[field] not in allowed:
            raise LedgerError(f"{location}: invalid {field} {event[field]!r}")

    bool_fields = {
        "material_behavior_change", "approved_writer", "team_skill_loaded",
        "independent_validation", "status_truth_match", "rollback_executable",
        "owner_approval", "release_trial_comparable",
    }
    for field in bool_fields:
        if field in event and not isinstance(event[field], bool):
            raise LedgerError(f"{location}: {field} must be boolean")

    string_fields = {
        "actor", "actual_model", "escalation_reason", "backlog_override_reason",
        "reason", "v1_baseline_stratum",
    }
    for field in string_fields:
        if field in event and (
            not isinstance(event[field], str) or not event[field].strip()
        ):
            raise LedgerError(f"{location}: {field} must be a non-empty string")

    if "owned_paths" in event:
        paths = event["owned_paths"]
        if not isinstance(paths, list) or not paths or any(
            not isinstance(item, str) or not item.strip() for item in paths
        ):
            raise LedgerError(f"{location}: owned_paths must be a non-empty string array")
        if len(paths) != len(set(paths)):
            raise LedgerError(f"{location}: owned_paths must be unique")

    for field in ("commit", "stable_commit", "skill_candidate_commit"):
        if field in event and not FULL_SHA.fullmatch(str(event[field])):
            raise LedgerError(f"{location}: {field} must be a full 40-character SHA")

    if "release_trial_registration_sequence" in event:
        sequence = event["release_trial_registration_sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise LedgerError(
                f"{location}: release_trial_registration_sequence must be positive"
            )

    for field in ("active_minutes", "governance_minutes"):
        if field in event:
            value = event[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise LedgerError(f"{location}: {field} must be a non-negative number")
    if event.get("governance_minutes", 0) > event.get("active_minutes", 0):
        raise LedgerError(f"{location}: governance_minutes cannot exceed active_minutes")
    if "metadata" in event and not isinstance(event["metadata"], dict):
        raise LedgerError(f"{location}: metadata must be an object")


def event_from_args(args: argparse.Namespace) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": args.timestamp or now_iso(),
        "task_id": args.task,
        "event": args.event,
    }
    mappings = {
        "actor": args.actor,
        "complexity": args.complexity,
        "risk": args.risk,
        "topology": args.topology,
        "governance_profile": args.governance_profile,
        "material_behavior_change": args.material_behavior_change,
        "release_trial_registration_sequence": args.release_trial_registration_sequence,
        "skill_candidate_commit": args.skill_candidate_commit,
        "release_trial_comparable": args.release_trial_comparable,
        "v1_baseline_stratum": args.v1_baseline_stratum,
        "capability_tier": args.capability_tier,
        "reasoning_tier": args.reasoning_tier,
        "actual_model": args.actual_model,
        "escalation_reason": args.escalation_reason,
        "approved_writer": args.approved_writer,
        "team_skill_loaded": args.team_skill_loaded,
        "backlog_override_reason": args.backlog_override_reason,
        "commit": args.commit,
        "stable_commit": args.stable_commit,
        "result": args.result,
        "independent_validation": args.independent_validation,
        "status_truth_match": args.status_truth_match,
        "rollback_executable": args.rollback_executable,
        "owner_approval": args.owner_approval,
        "reason": args.reason,
        "active_minutes": args.active_minutes,
        "governance_minutes": args.governance_minutes,
    }
    event.update({key: value for key, value in mappings.items() if value is not None})
    if args.owned_path:
        event["owned_paths"] = list(dict.fromkeys(args.owned_path))
    if args.metadata_json:
        try:
            metadata = json.loads(args.metadata_json)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"--metadata-json is invalid: {exc.msg}") from exc
        if not isinstance(metadata, dict):
            raise LedgerError("--metadata-json must decode to an object")
        event["metadata"] = metadata
    validate_event(event)
    return event


def cmd_record(args: argparse.Namespace) -> int:
    ledger = Path(args.ledger)
    existing = load_events(ledger, missing_ok=True)
    event = event_from_args(args)
    same_task = [item for item in existing if item["task_id"] == event["task_id"]]
    if same_task and parse_time(event["timestamp"]) < parse_time(same_task[-1]["timestamp"]):
        raise LedgerError("new event timestamp precedes the last event for this task")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def task_groups(events: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        groups[event["task_id"]].append(event)
    for task_events in groups.values():
        task_events.sort(key=lambda item: (parse_time(item["timestamp"]), item.get("_line", 0)))
    return dict(groups)


def rounded(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def summarize(events: list[dict[str, Any]], *, include_audit: bool = True) -> dict[str, Any]:
    groups = task_groups(events)
    ready_to_accepted: list[float] = []
    dev_to_accepted: list[float] = []
    accepted_tasks = 0
    qa_first: list[bool] = []
    reopened_tasks = 0
    eligible_starts = 0
    routed_economy_standard = 0

    for task_events in groups.values():
        ready = next((item for item in task_events if item["event"] == "task_ready"), None)
        accepted = next((item for item in reversed(task_events) if item["event"] == "accepted"), None)
        if accepted:
            accepted_tasks += 1
        if ready and accepted:
            ready_to_accepted.append(
                (parse_time(accepted["timestamp"]) - parse_time(ready["timestamp"])).total_seconds()
                / 3600
            )
            dev_candidates = [
                item for item in task_events
                if item["event"] == "dev_complete"
                and parse_time(item["timestamp"]) <= parse_time(accepted["timestamp"])
            ]
            if dev_candidates:
                dev_to_accepted.append(
                    (parse_time(accepted["timestamp"]) - parse_time(dev_candidates[-1]["timestamp"]))
                    .total_seconds() / 3600
                )
        qa_events = [item for item in task_events if item["event"] == "qa_complete"]
        if qa_events:
            qa_first.append(
                qa_events[0].get("result") == "PASSED"
                and qa_events[0].get("independent_validation") is True
            )
        if any(item["event"] == "reopened" for item in task_events):
            reopened_tasks += 1

        complexity = ready.get("complexity") if ready else None
        for item in task_events:
            if item["event"] == "worker_started" and complexity in {"C0", "C1"}:
                eligible_starts += 1
                if item.get("capability_tier") in {"economy", "standard"}:
                    routed_economy_standard += 1

    active_minutes = sum(float(item.get("active_minutes", 0)) for item in events)
    governance_minutes = sum(float(item.get("governance_minutes", 0)) for item in events)
    active_hours = active_minutes / 60
    result = {
        "schema_version": SCHEMA_VERSION,
        "tasks": len(groups),
        "accepted_tasks": accepted_tasks,
        "median_ready_to_accepted_hours": rounded(median_or_none(ready_to_accepted)),
        "median_dev_complete_to_accepted_hours": rounded(median_or_none(dev_to_accepted)),
        "cumulative_active_agent_hours": rounded(active_hours),
        "accepted_tasks_per_active_agent_hour": rounded(
            accepted_tasks / active_hours if active_hours else None
        ),
        "governance_share_percent": rounded(
            governance_minutes / active_minutes * 100 if active_minutes else None
        ),
        "eligible_c0_c1_worker_starts": eligible_starts,
        "economy_standard_routing_percent": rounded(
            routed_economy_standard / eligible_starts * 100 if eligible_starts else None
        ),
        "first_pass_independent_qa_percent": rounded(
            sum(qa_first) / len(qa_first) * 100 if qa_first else None
        ),
        "reopened_task_percent": rounded(
            reopened_tasks / len(groups) * 100 if groups else None
        ),
    }
    if include_audit:
        result["hard_gate_violations"] = len(audit_events(events)["violations"])
    return result


def snapshot_with_strata(events: list[dict[str, Any]]) -> dict[str, Any]:
    result = summarize(events)
    groups = task_groups(events)
    strata_events: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for task_events in groups.values():
        ready = next((item for item in task_events if item["event"] == "task_ready"), None)
        if ready:
            key = (ready["complexity"], ready["risk"], ready["topology"])
            strata_events[key].extend(task_events)
    result["strata"] = {
        "|".join(key): summarize(value, include_audit=False)
        for key, value in sorted(strata_events.items())
    }
    return result


def paths_overlap(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        return value.replace("\\", "/").rstrip("/").casefold()
    a, b = normalize(left), normalize(right)
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def add_violation(
    output: list[dict[str, Any]], event: dict[str, Any], code: str, message: str
) -> None:
    output.append({
        "code": code, "task_id": event["task_id"],
        "line": event.get("_line"), "message": message,
    })


def audit_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        events, key=lambda item: (parse_time(item["timestamp"]), item.get("_line", 0))
    )
    metadata: dict[str, dict[str, Any]] = {}
    states: dict[str, str] = {}
    active_writers: dict[tuple[str, str], dict[str, Any]] = {}
    qa_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    violations: list[dict[str, Any]] = []

    for event in ordered:
        task, kind = event["task_id"], event["event"]

        if kind == "task_ready":
            if task in metadata:
                add_violation(
                    violations, event, "duplicate_task_ready",
                    "task_ready was recorded more than once",
                )
            metadata[task] = event
            states[task] = "ready"
            continue

        task_meta = metadata.get(task)
        if not task_meta:
            add_violation(
                violations, event, "missing_task_ready", "event occurred before task_ready"
            )

        if kind == "worker_started":
            if states.get(task) in {"dev_complete", "qa_complete"}:
                add_violation(
                    violations, event, "writer_started_without_reopen",
                    "Writer restarted after delivery without a reopened event",
                )
            backlog = [
                other for other, state in states.items()
                if other != task and state in {"dev_complete", "qa_complete"}
            ]
            if backlog and not event.get("backlog_override_reason"):
                add_violation(
                    violations, event, "writer_started_with_integration_backlog",
                    f"new Writer started while integration backlog existed: {sorted(backlog)}",
                )
            if event.get("approved_writer") is not True:
                add_violation(
                    violations, event, "unapproved_writer",
                    "Writer was not explicitly approved",
                )
            if event.get("team_skill_loaded") is not False:
                add_violation(
                    violations, event, "worker_loaded_team_skill",
                    "ordinary Worker loaded the complete team Skill",
                )
            if (
                task_meta and task_meta.get("complexity") == "C0"
                and event.get("capability_tier") == "frontier"
                and not event.get("escalation_reason")
            ):
                add_violation(
                    violations, event, "unreasoned_c0_frontier",
                    "C0 delegated work used Frontier without an escalation reason",
                )
            for active in active_writers.values():
                for owned in event.get("owned_paths", []):
                    for other_owned in active.get("owned_paths", []):
                        if paths_overlap(owned, other_owned):
                            add_violation(
                                violations, event, "overlapping_writer_paths",
                                f"declared path {owned!r} overlaps active Writer path {other_owned!r}",
                            )
            active_writers[(task, event.get("actor", "<unknown>"))] = event
            states[task] = "in_progress"

        elif kind == "dev_complete":
            for key in [key for key in active_writers if key[0] == task]:
                del active_writers[key]
            states[task] = "dev_complete"

        elif kind == "qa_complete":
            qa_history[task].append(event)
            states[task] = "qa_complete"

        elif kind == "accepted":
            if event.get("status_truth_match") is not True:
                add_violation(
                    violations, event, "status_truth_mismatch",
                    "task status does not agree with Git or acceptance evidence",
                )
            if event.get("rollback_executable") is not True:
                add_violation(
                    violations, event, "rollback_not_executable",
                    "acceptance lacks an executable rollback",
                )
            if task_meta and task_meta.get("risk") == "R3" and event.get("owner_approval") is not True:
                add_violation(
                    violations, event, "missing_owner_approval",
                    "R3 acceptance lacks explicit Owner approval",
                )
            if task_meta and task_meta.get("material_behavior_change") is True:
                matching = [
                    qa for qa in qa_history.get(task, [])
                    if qa.get("commit", "").casefold() == event.get("commit", "").casefold()
                    and qa.get("result") == "PASSED"
                    and qa.get("independent_validation") is True
                ]
                if not matching:
                    add_violation(
                        violations, event, "missing_independent_validation",
                        "material change lacks passed independent validation on the candidate Commit",
                    )
            states[task] = "accepted"
            for key in [key for key in active_writers if key[0] == task]:
                del active_writers[key]

        elif kind == "reopened":
            states[task] = "reopened"
        elif kind == "blocked":
            states[task] = "blocked"
        elif kind == "cancelled":
            states[task] = "cancelled"
            for key in [key for key in active_writers if key[0] == task]:
                del active_writers[key]

    return {
        "schema_version": SCHEMA_VERSION,
        "events": len(events),
        "tasks": len(task_groups(events)),
        "violations": violations,
        "passed": not violations,
    }


def write_or_print(data: dict[str, Any], output: str | None) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")


def cmd_snapshot(args: argparse.Namespace) -> int:
    write_or_print(snapshot_with_strata(load_events(Path(args.ledger))), args.output)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    result = audit_events(load_events(Path(args.ledger)))
    write_or_print(result, args.output)
    return 0 if result["passed"] else 1


def load_snapshot(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"cannot read snapshot {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LedgerError(f"snapshot must be an object: {path}")
    return data


def compare_field(
    baseline: dict[str, Any], current: dict[str, Any], field: str,
    *, lower_is_better: bool, target: float,
) -> dict[str, Any]:
    before, after = baseline.get(field), current.get(field)
    result: dict[str, Any] = {
        "baseline": before, "current": after,
        "target_improvement_percent": target,
        "direction": "lower_is_better" if lower_is_better else "higher_is_better",
    }
    valid_before = (
        isinstance(before, (int, float)) and not isinstance(before, bool) and before != 0
    )
    valid_after = isinstance(after, (int, float)) and not isinstance(after, bool)
    if not valid_before or not valid_after:
        result.update({"status": "unavailable", "improvement_percent": None, "passes": None})
        return result
    change = (
        (before - after) / before * 100
        if lower_is_better else (after - before) / before * 100
    )
    result.update({
        "status": "available", "improvement_percent": rounded(change),
        "passes": change >= target,
    })
    return result


def cmd_compare(args: argparse.Namespace) -> int:
    baseline, current = load_snapshot(Path(args.baseline)), load_snapshot(Path(args.current))
    comparisons = {
        "median_ready_to_accepted_hours": compare_field(
            baseline, current, "median_ready_to_accepted_hours",
            lower_is_better=True, target=20,
        ),
        "median_dev_complete_to_accepted_hours": compare_field(
            baseline, current, "median_dev_complete_to_accepted_hours",
            lower_is_better=True, target=30,
        ),
        "accepted_tasks_per_active_agent_hour": compare_field(
            baseline, current, "accepted_tasks_per_active_agent_hour",
            lower_is_better=False, target=20,
        ),
        "governance_share_percent": compare_field(
            baseline, current, "governance_share_percent",
            lower_is_better=True, target=25,
        ),
    }
    governance_current = current.get("governance_share_percent")
    comparisons["governance_share_percent"]["current_at_most_15_percent"] = (
        governance_current <= 15
        if isinstance(governance_current, (int, float))
        and not isinstance(governance_current, bool) else None
    )
    routing_current = current.get("economy_standard_routing_percent")
    result = {
        "schema_version": SCHEMA_VERSION,
        "baseline": str(Path(args.baseline)),
        "current": str(Path(args.current)),
        "comparisons": comparisons,
        "current_hard_gates": {
            "violations": current.get("hard_gate_violations"),
            "passes": current.get("hard_gate_violations") == 0,
        },
        "current_routing_gate": {
            "economy_standard_routing_percent": routing_current,
            "target_at_least_80_percent": (
                routing_current >= 80
                if isinstance(routing_current, (int, float))
                and not isinstance(routing_current, bool) else None
            ),
        },
    }
    write_or_print(result, args.output)
    return 0


def add_record_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ledger", default=".ai-team/metrics/events.jsonl")
    parser.add_argument("--task", required=True)
    parser.add_argument("--event", required=True, choices=sorted(EVENTS))
    parser.add_argument("--timestamp")
    parser.add_argument("--actor")
    parser.add_argument("--complexity", choices=sorted(COMPLEXITIES))
    parser.add_argument("--risk", choices=sorted(RISKS))
    parser.add_argument("--topology", choices=sorted(TOPOLOGIES))
    parser.add_argument("--governance-profile", choices=sorted(PROFILES))
    parser.add_argument("--material-behavior-change", type=parse_bool)
    parser.add_argument("--release-trial-registration-sequence", type=int)
    parser.add_argument("--skill-candidate-commit")
    parser.add_argument("--release-trial-comparable", type=parse_bool)
    parser.add_argument("--v1-baseline-stratum")
    parser.add_argument("--capability-tier", choices=sorted(CAPABILITIES))
    parser.add_argument("--reasoning-tier", choices=sorted(REASONING))
    parser.add_argument("--actual-model")
    parser.add_argument("--escalation-reason")
    parser.add_argument("--approved-writer", type=parse_bool)
    parser.add_argument("--team-skill-loaded", type=parse_bool)
    parser.add_argument("--owned-path", action="append")
    parser.add_argument("--backlog-override-reason")
    parser.add_argument("--commit")
    parser.add_argument("--stable-commit")
    parser.add_argument("--result", choices=sorted(QA_RESULTS))
    parser.add_argument("--independent-validation", type=parse_bool)
    parser.add_argument("--status-truth-match", type=parse_bool)
    parser.add_argument("--rollback-executable", type=parse_bool)
    parser.add_argument("--owner-approval", type=parse_bool)
    parser.add_argument("--reason")
    parser.add_argument("--active-minutes", type=float)
    parser.add_argument("--governance-minutes", type=float)
    parser.add_argument("--metadata-json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="validate and append one event")
    add_record_arguments(record)
    record.set_defaults(func=cmd_record)

    snapshot = subparsers.add_parser("snapshot", help="calculate delivery metrics")
    snapshot.add_argument("--ledger", default=".ai-team/metrics/events.jsonl")
    snapshot.add_argument("--output")
    snapshot.set_defaults(func=cmd_snapshot)

    audit = subparsers.add_parser("audit", help="check hard mechanism gates")
    audit.add_argument("--ledger", default=".ai-team/metrics/events.jsonl")
    audit.add_argument("--output")
    audit.set_defaults(func=cmd_audit)

    compare_parser = subparsers.add_parser("compare", help="compare compatible snapshots")
    compare_parser.add_argument("--baseline", required=True)
    compare_parser.add_argument("--current", required=True)
    compare_parser.add_argument("--output")
    compare_parser.set_defaults(func=cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except LedgerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
