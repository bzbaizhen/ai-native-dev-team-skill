import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "skills"
    / "bootstrap-ai-native-dev-team"
    / "scripts"
    / "team_metrics.py"
)
SPEC = importlib.util.spec_from_file_location("team_metrics", SCRIPT)
assert SPEC and SPEC.loader
team_metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(team_metrics)

A = "a" * 40
B = "b" * 40


class TeamMetricsTests(unittest.TestCase):
    def write_events(self, path: Path, events: list[dict]) -> None:
        path.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
            encoding="utf-8",
        )

    def happy_events(self) -> list[dict]:
        return [
            {
                "schema_version": "2.0",
                "timestamp": "2026-08-14T00:00:00Z",
                "task_id": "T-1",
                "event": "task_ready",
                "complexity": "C1",
                "risk": "R1",
                "topology": "task-cell",
                "governance_profile": "controlled",
                "material_behavior_change": True,
                "active_minutes": 5,
                "governance_minutes": 1,
            },
            {
                "schema_version": "2.0",
                "timestamp": "2026-08-14T01:00:00Z",
                "task_id": "T-1",
                "event": "worker_started",
                "actor": "writer-1",
                "capability_tier": "standard",
                "reasoning_tier": "medium",
                "approved_writer": True,
                "team_skill_loaded": False,
                "owned_paths": ["src/a.py"],
                "active_minutes": 30,
                "governance_minutes": 1,
            },
            {
                "schema_version": "2.0",
                "timestamp": "2026-08-14T02:00:00Z",
                "task_id": "T-1",
                "event": "dev_complete",
                "actor": "writer-1",
                "commit": A,
                "active_minutes": 10,
                "governance_minutes": 0,
            },
            {
                "schema_version": "2.0",
                "timestamp": "2026-08-14T03:00:00Z",
                "task_id": "T-1",
                "event": "qa_complete",
                "commit": A,
                "result": "PASSED",
                "independent_validation": True,
                "active_minutes": 10,
                "governance_minutes": 2,
            },
            {
                "schema_version": "2.0",
                "timestamp": "2026-08-14T04:00:00Z",
                "task_id": "T-1",
                "event": "accepted",
                "commit": A,
                "stable_commit": B,
                "status_truth_match": True,
                "rollback_executable": True,
                "owner_approval": False,
                "active_minutes": 5,
                "governance_minutes": 1,
            },
        ]

    def test_happy_path_snapshot_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            ledger = Path(raw) / "events.jsonl"
            self.write_events(ledger, self.happy_events())
            events = team_metrics.load_events(ledger)
            audit = team_metrics.audit_events(events)
            snapshot = team_metrics.snapshot_with_strata(events)

        self.assertTrue(audit["passed"])
        self.assertEqual(snapshot["hard_gate_violations"], 0)
        self.assertEqual(snapshot["accepted_tasks"], 1)
        self.assertEqual(snapshot["median_ready_to_accepted_hours"], 4)
        self.assertEqual(snapshot["median_dev_complete_to_accepted_hours"], 2)
        self.assertEqual(snapshot["cumulative_active_agent_hours"], 1)
        self.assertEqual(snapshot["accepted_tasks_per_active_agent_hour"], 1)
        self.assertAlmostEqual(snapshot["governance_share_percent"], 8.3333)
        self.assertEqual(snapshot["economy_standard_routing_percent"], 100)
        self.assertEqual(snapshot["first_pass_independent_qa_percent"], 100)

    def test_audit_finds_routing_wip_and_evidence_violations(self) -> None:
        events = self.happy_events()
        events[0]["complexity"] = "C0"
        events[1]["approved_writer"] = False
        events[1]["team_skill_loaded"] = True
        events[1]["capability_tier"] = "frontier"
        events[4]["status_truth_match"] = False
        events[4]["rollback_executable"] = False
        events[3]["commit"] = B
        events.extend(
            [
                {
                    "schema_version": "2.0",
                    "timestamp": "2026-08-14T01:10:00Z",
                    "task_id": "T-2",
                    "event": "task_ready",
                    "complexity": "C0",
                    "risk": "R1",
                    "topology": "single-worker",
                    "governance_profile": "lean",
                    "material_behavior_change": False,
                },
                {
                    "schema_version": "2.0",
                    "timestamp": "2026-08-14T01:20:00Z",
                    "task_id": "T-2",
                    "event": "worker_started",
                    "actor": "writer-2",
                    "capability_tier": "economy",
                    "reasoning_tier": "low",
                    "approved_writer": True,
                    "team_skill_loaded": False,
                    "owned_paths": ["src"],
                },
                {
                    "schema_version": "2.0",
                    "timestamp": "2026-08-14T01:30:00Z",
                    "task_id": "T-2",
                    "event": "dev_complete",
                    "actor": "writer-2",
                    "commit": B,
                },
                {
                    "schema_version": "2.0",
                    "timestamp": "2026-08-14T02:05:00Z",
                    "task_id": "T-3",
                    "event": "task_ready",
                    "complexity": "C1",
                    "risk": "R1",
                    "topology": "single-worker",
                    "governance_profile": "lean",
                    "material_behavior_change": False,
                },
                {
                    "schema_version": "2.0",
                    "timestamp": "2026-08-14T02:10:00Z",
                    "task_id": "T-3",
                    "event": "worker_started",
                    "actor": "writer-3",
                    "capability_tier": "standard",
                    "reasoning_tier": "medium",
                    "approved_writer": True,
                    "team_skill_loaded": False,
                    "owned_paths": ["docs/new.md"],
                },
            ]
        )

        with tempfile.TemporaryDirectory() as raw:
            ledger = Path(raw) / "events.jsonl"
            self.write_events(ledger, events)
            audit = team_metrics.audit_events(team_metrics.load_events(ledger))

        codes = {item["code"] for item in audit["violations"]}
        self.assertIn("unapproved_writer", codes)
        self.assertIn("worker_loaded_team_skill", codes)
        self.assertIn("unreasoned_c0_frontier", codes)
        self.assertIn("overlapping_writer_paths", codes)
        self.assertIn("writer_started_with_integration_backlog", codes)
        self.assertIn("status_truth_mismatch", codes)
        self.assertIn("rollback_not_executable", codes)
        self.assertIn("missing_independent_validation", codes)

    def test_record_and_compare_preserve_missing_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            ledger = root / "nested" / "events.jsonl"
            with contextlib.redirect_stdout(io.StringIO()):
                rc = team_metrics.main(
                    [
                        "record",
                        "--ledger",
                        str(ledger),
                        "--task",
                        "T-2",
                        "--event",
                        "task_ready",
                        "--timestamp",
                        "2026-08-14T00:00:00Z",
                        "--complexity",
                        "C0",
                        "--risk",
                        "R0",
                        "--topology",
                        "no-delegation",
                        "--governance-profile",
                        "lean",
                        "--material-behavior-change",
                        "false",
                        "--release-trial-registration-sequence",
                        "1",
                        "--skill-candidate-commit",
                        A,
                        "--release-trial-comparable",
                        "true",
                        "--v1-baseline-id",
                        "baseline-c0-r0-no-delegation",
                        "--v1-baseline-stratum",
                        "C0|R0|no-delegation",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertTrue(ledger.exists())
            recorded = team_metrics.load_events(ledger)[0]
            self.assertEqual(recorded["release_trial_registration_sequence"], 1)
            self.assertEqual(recorded["skill_candidate_commit"], A)
            self.assertEqual(
                recorded["v1_baseline_id"], "baseline-c0-r0-no-delegation"
            )

            baseline = root / "baseline.json"
            current = root / "current.json"
            baseline.write_text(
                json.dumps({"median_ready_to_accepted_hours": None}), encoding="utf-8"
            )
            current.write_text(
                json.dumps(
                    {
                        "median_ready_to_accepted_hours": 1,
                        "hard_gate_violations": 0,
                    }
                ),
                encoding="utf-8",
            )
            result = team_metrics.compare_field(
                json.loads(baseline.read_text()),
                json.loads(current.read_text()),
                "median_ready_to_accepted_hours",
                lower_is_better=True,
                target=20,
            )
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(result["improvement_percent"])


class RoutingScenarioContractTests(unittest.TestCase):
    def test_scenario_matrix_preserves_cost_and_risk_separation(self) -> None:
        scenarios = json.loads(
            (ROOT / "tests" / "routing-scenarios.json").read_text(encoding="utf-8")
        )
        capability = {
            "C0": {"main-agent", "economy"},
            "C1": {"standard"},
            "C2": {"advanced"},
            "C3": {"frontier"},
        }
        reasoning = {
            "C0": {"current", "low"},
            "C1": {"medium"},
            "C2": {"high"},
            "C3": {"max"},
        }
        self.assertGreaterEqual(len(scenarios), 8)
        for case in scenarios:
            self.assertIn(case["capability"], capability[case["complexity"]])
            self.assertIn(case["reasoning"], reasoning[case["complexity"]])
            if case["risk"] == "R3" or case["complexity"] == "C3":
                self.assertEqual(case["profile"], "strict")
            if case["risk"] == "R3":
                self.assertTrue(case["owner_approval"])
            if case["route"] == "task-cell":
                self.assertTrue(case["independent_validator"])


if __name__ == "__main__":
    unittest.main()
