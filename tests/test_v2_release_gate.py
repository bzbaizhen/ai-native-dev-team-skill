import contextlib
import importlib.util
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
    / "v2_release_gate.py"
)
SPEC = importlib.util.spec_from_file_location("v2_release_gate", SCRIPT)
assert SPEC and SPEC.loader
v2_release_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v2_release_gate)

SKILL_COMMIT = "c" * 40


class V2ReleaseGateTests(unittest.TestCase):
    def build_trial_files(
        self,
        root: Path,
        count: int,
        *,
        failing_index: int | None = None,
    ) -> Path:
        ledger = root / "events.jsonl"
        events = []
        trials = []
        for index in range(1, count + 1):
            task = f"T-{index:02d}"
            candidate = f"{index:040x}"
            stable = f"{100 + index:040x}"
            events.extend(
                [
                    {
                        "schema_version": "2.0",
                        "timestamp": f"2026-08-14T00:{index:02d}:00Z",
                        "task_id": task,
                        "event": "task_ready",
                        "complexity": "C1",
                        "risk": "R1",
                        "topology": "no-delegation",
                        "governance_profile": "lean",
                        "material_behavior_change": False,
                    },
                    {
                        "schema_version": "2.0",
                        "timestamp": f"2026-08-14T01:{index:02d}:00Z",
                        "task_id": task,
                        "event": "dev_complete",
                        "actor": "main-agent",
                        "commit": candidate,
                    },
                    {
                        "schema_version": "2.0",
                        "timestamp": f"2026-08-14T02:{index:02d}:00Z",
                        "task_id": task,
                        "event": "accepted",
                        "commit": candidate,
                        "stable_commit": stable,
                        "status_truth_match": True,
                        "rollback_executable": True,
                        "owner_approval": False,
                    },
                ]
            )
            trials.append(
                {
                    "trial_id": f"TRIAL-{index:03d}",
                    "project_alias": "project-a",
                    "ledger": "events.jsonl",
                    "task_id": task,
                    "skill_candidate_commit": SKILL_COMMIT,
                    "candidate_commit": candidate,
                    "stable_commit": stable,
                    "comparable": True,
                    "critical_defect_escape": False,
                    "material_quality_regression": index == failing_index,
                    "scope_violation": False,
                    "write_conflict": False,
                    "recovery_executable": True,
                    "notes": [],
                }
            )
        ledger.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
            encoding="utf-8",
        )
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "2.0",
                    "candidate_version": "v2.0.0-rc.2",
                    "candidate_commit": SKILL_COMMIT,
                    "required_comparable_tasks": 5,
                    "trials": trials,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return manifest

    def test_first_five_passing_trials_open_stable_gate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(Path(raw), 5)
            manifest = v2_release_gate.load_manifest(manifest_path)
            result = v2_release_gate.evaluate_manifest(manifest, manifest_path)
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = v2_release_gate.main(["--manifest", str(manifest_path)])

        self.assertTrue(result["stable_v2_ready"])
        self.assertTrue(result["gates"]["no_hard_gate_violations"])
        self.assertEqual(result["first_comparable_trial_ids"], [
            "TRIAL-001",
            "TRIAL-002",
            "TRIAL-003",
            "TRIAL-004",
            "TRIAL-005",
        ])
        self.assertEqual(exit_code, 0)

    def test_later_success_cannot_hide_failure_in_first_five(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(Path(raw), 6, failing_index=3)
            result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path),
                manifest_path,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = v2_release_gate.main(["--manifest", str(manifest_path)])

        self.assertFalse(result["stable_v2_ready"])
        self.assertIn("material_quality_regression", {
            issue["code"]
            for issue in result["trials"][2]["issues"]
        })
        self.assertNotIn("TRIAL-006", result["first_comparable_trial_ids"])
        self.assertEqual(exit_code, 1)

    def test_fewer_than_five_trials_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(Path(raw), 4)
            result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path),
                manifest_path,
            )

        self.assertFalse(result["stable_v2_ready"])
        self.assertFalse(result["gates"]["enough_comparable_tasks"])

    def test_missing_ready_event_cannot_be_sorted_behind_successes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 6)
            ledger = root / "events.jsonl"
            events = [
                json.loads(line)
                for line in ledger.read_text(encoding="utf-8").splitlines()
            ]
            events = [
                event
                for event in events
                if not (
                    event["task_id"] == "T-01"
                    and event["event"] == "task_ready"
                )
            ]
            ledger.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path),
                manifest_path,
            )

        self.assertFalse(result["stable_v2_ready"])
        self.assertFalse(result["gates"]["comparable_order_established"])

    def test_non_comparable_trial_requires_exclusion_reason(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            data["trials"][0]["comparable"] = False
            manifest_path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaises(v2_release_gate.ReleaseGateError):
                v2_release_gate.load_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
