"""Deterministic, offline route binding and evidence reconciliation probe."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PlannedRoute:
    logical_provider: str
    runtime_provider: str | None
    model: str
    reasoning: str
    marker: str
    workdir: str
    run_budget: str = "120"

    def __post_init__(self) -> None:
        _validate_field("logical_provider", self.logical_provider)
        if self.runtime_provider is not None:
            _validate_field("runtime_provider", self.runtime_provider)
        _validate_field("model", self.model)
        _validate_field("reasoning", self.reasoning)
        _validate_field("marker", self.marker)
        _validate_field("workdir", self.workdir)
        _validate_field("run_budget", self.run_budget)
        if not self.run_budget.isdigit() or not 1 <= int(self.run_budget) <= 600:
            raise ValueError("run_budget must be a positive integer string within 1..600")


_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
# Keep transcript normalization deliberately narrow and bounded.  CSI matches
# standard parameter/intermediate bytes and a final byte; OSC accepts only a
# finite payload terminated by BEL or ST.  Neither pattern crosses a line.
_ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ANSI_OSC = re.compile(r"\x1b\][^\x07\x1b]{0,4096}(?:\x07|\x1b\\)")


def _validate_field(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if _CONTROL_CHARACTER.search(value):
        raise ValueError(f"{name} contains a control character")


def _normalize_ansi_line(line: str) -> str:
    """Return a comparison-only line with bounded ANSI CSI/OSC sequences removed."""
    return _ANSI_OSC.sub("", _ANSI_CSI.sub("", line))


def _validate_executable(executable: str) -> None:
    _validate_field("executable", executable)


def build_hermes_argv(route: PlannedRoute, executable: str = "hermes") -> list[str]:
    """Build the bounded Hermes chat argv without executing it."""
    _validate_executable(executable)
    if route.runtime_provider is None:
        raise ValueError("Hermes requires an explicit runtime provider")
    return [
        executable,
        "chat",
        "--provider",
        route.runtime_provider,
        "-m",
        route.model,
        "--reasoning",
        route.reasoning,
        "--ignore-rules",
        "--in",
        route.workdir,
        "--max-turns",
        "1",
        "--run-budget",
        route.run_budget,
        "-q",
        f"Return exactly {route.marker} and nothing else.",
    ]


def build_codex_argv(route: PlannedRoute, executable: str = "codex") -> list[str]:
    """Build the read-only, ephemeral Codex exec argv without executing it."""
    _validate_executable(executable)
    argv = [
        executable,
        "exec",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--cd",
        route.workdir,
        "-m",
        route.model,
        "-c",
        f"model_reasoning_effort={route.reasoning}",
        "--ignore-rules",
    ]
    if route.runtime_provider is not None:
        argv.extend(["-c", f"model_provider={route.runtime_provider}"])
    argv.append(f"Return exactly {route.marker} and nothing else.")
    return argv


_TEXT_METADATA = re.compile(
    r"^\s*(?:\[[^\]]+\]\s*)?"
    r"(provider|model_provider|model|reasoning(?:[_ ]effort)?)\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)
_JSON_METADATA_KEYS = {
    "provider": "provider",
    "model_provider": "provider",
    "model": "model",
    "reasoning": "reasoning",
    "reasoning_effort": "reasoning",
    "reasoning effort": "reasoning",
}
_JSON_EVENT_TYPES = {"session_meta", "session.metadata", "turn.started"}


def _metadata_key(key: object) -> str | None:
    if not isinstance(key, str):
        return None
    return _JSON_METADATA_KEYS.get(key.strip().lower())


def _record_metadata(observations: dict[str, list[str]], key: str, value: object) -> None:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        text = str(value).strip()
        if text:
            observations[key].append(text)


def _parse_whitelisted_json(
    event: object, observations: dict[str, list[str]]
) -> bool:
    if not isinstance(event, dict):
        return False
    event_type = event.get("type")
    if not isinstance(event_type, str) or event_type.strip().lower() not in _JSON_EVENT_TYPES:
        return False
    before = sum(len(values) for values in observations.values())
    for key, value in event.items():
        metadata_key = _metadata_key(key)
        if metadata_key is not None:
            _record_metadata(observations, metadata_key, value)
    metadata = event.get("metadata")
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            metadata_key = _metadata_key(key)
            if metadata_key is not None:
                _record_metadata(observations, metadata_key, value)
    return sum(len(values) for values in observations.values()) > before


def parse_process_evidence(
    stdout: str, stderr: str = "", marker: str | None = None, host: str = "codex"
) -> dict[str, Any]:
    """Parse only completed-process output; never inspect a planned argv."""
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise TypeError("stdout and stderr must be strings")
    if marker is not None:
        _validate_field("marker", marker)

    observations: dict[str, list[str]] = {
        "provider": [],
        "model": [],
        "reasoning": [],
    }
    sources: list[str] = []
    marker_seen = False
    for source_name, text in (("stdout", stdout), ("stderr", stderr)):
        source_had_evidence = False
        phase = "preamble" if host == "codex" else "hermes"
        for line in text.splitlines():
            normalized_line = _normalize_ansi_line(line)
            stripped = normalized_line.strip()
            if host == "codex" and stripped in {"user", "codex", "assistant"}:
                phase = "response" if stripped in {"codex", "assistant"} else "body"
                continue
            if marker is not None and stripped == marker and (
                host == "hermes" or phase == "response"
            ):
                source_had_evidence = True
                marker_seen = True
                continue
            if host == "codex" and phase == "preamble":
                match = _TEXT_METADATA.match(normalized_line)
                if match:
                    key = _metadata_key(match.group(1))
                    if key is not None:
                        _record_metadata(observations, key, match.group(2))
                        source_had_evidence = True
                        continue
                try:
                    event = json.loads(normalized_line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if _parse_whitelisted_json(event, observations):
                    source_had_evidence = True
        if source_had_evidence:
            sources.append(source_name)

    observed: dict[str, str | None] = {}
    limitations: list[str] = []
    for key, values in observations.items():
        unique_values = list(dict.fromkeys(values))
        if len(unique_values) == 1:
            observed[key] = unique_values[0]
        elif len(unique_values) > 1:
            observed[key] = None
            limitations.append(f"conflicting observed {key} values")
        else:
            observed[key] = None

    return {
        "marker_seen": marker_seen,
        "observed_mapping": observed,
        "evidence_source": "+".join(sources) if sources else "none",
        "limitations": limitations,
    }


def reconcile(
    host: str,
    planned: PlannedRoute,
    stdout: str,
    stderr: str,
    exit_code: int,
) -> dict[str, Any]:
    """Reconcile a completed synthetic/live-process transcript into JSON-safe data."""
    if host not in {"hermes", "codex"}:
        raise ValueError("host must be hermes or codex")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise TypeError("exit_code must be an integer")

    evidence = parse_process_evidence(stdout, stderr, planned.marker, host=host)
    limitations = list(evidence["limitations"])
    observed = evidence["observed_mapping"]
    marker_seen = evidence["marker_seen"]
    status = "verified"

    if exit_code != 0 or not marker_seen:
        status = "failed"
        if exit_code != 0:
            limitations.append("process exited nonzero")
        if not marker_seen:
            limitations.append("marker was not observed")
    else:
        expected_provider = planned.runtime_provider
        observed_provider = observed["provider"]
        observed_model = observed["model"]
        observed_reasoning = observed["reasoning"]
        if expected_provider is None:
            limitations.append("runtime provider was not configured")
        elif observed_provider is None:
            limitations.append("provider was not observable")
        elif observed_provider != expected_provider:
            status = "mismatch"
        if observed_model is None:
            limitations.append("model was not observable")
        elif observed_model != planned.model:
            status = "mismatch"
        if observed_reasoning is None:
            limitations.append("reasoning was not observable")
        elif observed_reasoning != planned.reasoning:
            status = "mismatch"
        if status == "verified" and (
            expected_provider is None
            or observed_provider is None
            or observed_model is None
        ):
            status = "advisory"

    return {
        "status": status,
        "host": host,
        "planned_route": {
            "logical_provider": planned.logical_provider,
            "runtime_provider": planned.runtime_provider,
            "model": planned.model,
            "reasoning": planned.reasoning,
            "marker": planned.marker,
            "workdir": planned.workdir,
            "run_budget": planned.run_budget,
        },
        "observed_mapping": observed,
        "marker_seen": marker_seen,
        "exit_code": exit_code,
        "evidence_source": evidence["evidence_source"],
        "limitations": limitations,
    }


def _route_from_json(path: str) -> PlannedRoute:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "planned_route" in payload:
        payload = payload["planned_route"]
    if not isinstance(payload, dict):
        raise ValueError("planned file must contain a route object")
    return PlannedRoute(**payload)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="output deterministic argv JSON")
    plan.add_argument("--host", choices=("hermes", "codex"), required=True)
    plan.add_argument("--logical-provider", required=True)
    plan.add_argument("--runtime-provider")
    plan.add_argument("--model", required=True)
    plan.add_argument("--reasoning", required=True)
    plan.add_argument("--marker", required=True)
    plan.add_argument("--workdir", required=True)
    plan.add_argument("--run-budget", default="120")
    plan.add_argument("--executable")

    reconcile_parser = subparsers.add_parser(
        "reconcile", help="reconcile completed-process output files"
    )
    reconcile_parser.add_argument("--host", choices=("hermes", "codex"), required=True)
    reconcile_parser.add_argument("--planned", required=True)
    reconcile_parser.add_argument("--stdout", required=True)
    reconcile_parser.add_argument("--stderr", required=True)
    reconcile_parser.add_argument("--exit-code", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "plan":
        route = PlannedRoute(
            logical_provider=args.logical_provider,
            runtime_provider=args.runtime_provider,
            model=args.model,
            reasoning=args.reasoning,
            marker=args.marker,
            workdir=args.workdir,
            run_budget=args.run_budget,
        )
        executable = args.executable or ("hermes" if args.host == "hermes" else "codex")
        command = (
            build_hermes_argv(route, executable)
            if args.host == "hermes"
            else build_codex_argv(route, executable)
        )
        json.dump(command, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    route = _route_from_json(args.planned)
    result = reconcile(
        host=args.host,
        planned=route,
        stdout=Path(args.stdout).read_text(encoding="utf-8"),
        stderr=Path(args.stderr).read_text(encoding="utf-8"),
        exit_code=args.exit_code,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
