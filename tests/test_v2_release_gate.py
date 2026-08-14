import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
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
        repo = root / "project"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main", str(repo)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Release Gate Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        ledger = root / "events.jsonl"
        evidence_dir = root / "evidence"
        evidence_dir.mkdir()
        frozen_prefix = json.dumps(
            {
                "schema_version": "2.0",
                "timestamp": "2026-08-13T00:00:00Z",
                "task_id": "HISTORICAL-001",
                "event": "task_ready",
                "complexity": "C1",
                "risk": "R1",
                "topology": "no-delegation",
                "governance_profile": "lean",
                "material_behavior_change": False,
            },
            sort_keys=True,
        ) + "\n"
        events = []
        trials = []
        for index in range(1, count + 1):
            task = f"T-{index:02d}"
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "commit",
                    "--allow-empty",
                    "-m",
                    f"accept {task}",
                ],
                check=True,
                capture_output=True,
            )
            stable = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            candidate = stable
            ready_timestamp = f"2026-08-14T00:{index:02d}:00Z"
            accepted_timestamp = f"2026-08-14T02:{index:02d}:00Z"
            events.extend(
                [
                    {
                        "schema_version": "2.0",
                        "timestamp": ready_timestamp,
                        "task_id": task,
                        "event": "task_ready",
                        "complexity": "C1",
                        "risk": "R1",
                        "topology": "no-delegation",
                        "governance_profile": "lean",
                        "material_behavior_change": False,
                        "release_trial_registration_sequence": index,
                        "skill_candidate_commit": SKILL_COMMIT,
                        "release_trial_comparable": True,
                        "v1_baseline_stratum": "C1|R1|no-delegation",
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
                        "timestamp": accepted_timestamp,
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
            request_evidence = evidence_dir / f"request-{index:02d}.json"
            request_evidence.write_text(
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "evidence_type": "task_request",
                        "project_evidence_id": "project-a-evidence",
                        "task_id": task,
                        "occurred_at": "2026-08-14T00:00:30Z",
                        "genuine_request": True,
                        "synthetic": False,
                        "summary": f"Genuine request for {task}",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            acceptance_evidence = evidence_dir / f"acceptance-{index:02d}.json"
            acceptance_evidence.write_text(
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "evidence_type": "task_acceptance",
                        "project_evidence_id": "project-a-evidence",
                        "task_id": task,
                        "occurred_at": accepted_timestamp,
                        "accepted": True,
                        "accepted_by_role": "business-owner",
                        "candidate_commit": candidate,
                        "stable_commit": stable,
                        "critical_defect_escape": False,
                        "material_quality_regression": index == failing_index,
                        "scope_violation": False,
                        "write_conflict": False,
                        "recovery_executable": True,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            trials.append(
                {
                    "trial_id": f"TRIAL-{index:03d}",
                    "registration_sequence": index,
                    "source_id": "source-a",
                    "task_id": task,
                    "skill_candidate_commit": SKILL_COMMIT,
                    "request_evidence": str(request_evidence.relative_to(root)),
                    "request_evidence_sha256": hashlib.sha256(
                        request_evidence.read_bytes()
                    ).hexdigest(),
                    "v1_baseline_stratum": "C1|R1|no-delegation",
                    "comparable": True,
                    "disposition": "accepted",
                    "genuine_request": True,
                    "synthetic": False,
                    "candidate_commit": candidate,
                    "stable_commit": stable,
                    "acceptance_evidence": str(acceptance_evidence.relative_to(root)),
                    "acceptance_evidence_sha256": hashlib.sha256(
                        acceptance_evidence.read_bytes()
                    ).hexdigest(),
                    "critical_defect_escape": False,
                    "material_quality_regression": index == failing_index,
                    "scope_violation": False,
                    "write_conflict": False,
                    "recovery_executable": True,
                    "notes": [],
                }
            )
        ledger.write_text(
            frozen_prefix
            + "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
            encoding="utf-8",
            newline="\n",
        )
        prefix_bytes = frozen_prefix.encode("utf-8")
        frozen_source = {
            "source_id": "source-a",
            "project_alias": "project-a",
            "project_evidence_id": "project-a-evidence",
            "project_repo": "project",
            "stable_branch": "main",
            "ledger": "events.jsonl",
            "ledger_prefix_bytes": len(prefix_bytes),
            "ledger_prefix_sha256": hashlib.sha256(prefix_bytes).hexdigest(),
        }
        source_registry = root / "source-registry.json"
        source_registry.write_text(
            json.dumps(
                {
                    "schema_version": "2.0",
                    "candidate_commit": SKILL_COMMIT,
                    "candidate_frozen_at": "2026-08-14T00:00:00Z",
                    "sources": [frozen_source],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "2.0",
                    "candidate_version": "v2.0.0-rc.2",
                    "candidate_commit": SKILL_COMMIT,
                    "candidate_frozen_at": "2026-08-14T00:00:00Z",
                    "registry_closed_at": "2026-08-14T23:59:59Z",
                    "source_registry": "source-registry.json",
                    "source_registry_sha256": hashlib.sha256(
                        source_registry.read_bytes()
                    ).hexdigest(),
                    "required_comparable_tasks": 5,
                    "sources": [
                        frozen_source
                        | {
                            "ledger_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
                        }
                    ],
                    "trials": trials,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return manifest

    def refresh_ledger_digest(self, manifest_path: Path) -> dict:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        ledger = manifest_path.parent / data["sources"][0]["ledger"]
        data["sources"][0]["ledger_sha256"] = hashlib.sha256(
            ledger.read_bytes()
        ).hexdigest()
        manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

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
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
                newline="\n",
            )
            result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path),
                manifest_path,
            )

        self.assertFalse(result["stable_v2_ready"])
        self.assertFalse(result["gates"]["registry_complete"])

    def test_non_comparable_trial_requires_exclusion_reason(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            data["trials"][0]["comparable"] = False
            data["trials"][0]["v1_baseline_stratum"] = None
            manifest_path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaises(v2_release_gate.ReleaseGateError):
                v2_release_gate.load_manifest(manifest_path)

    def test_duplicate_real_task_cannot_count_twice(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(Path(raw), 5)
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            duplicate = dict(data["trials"][0])
            duplicate["trial_id"] = "TRIAL-006"
            duplicate["registration_sequence"] = 6
            data["trials"].append(duplicate)
            manifest_path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError, "duplicate trial task identity"
            ):
                v2_release_gate.load_manifest(manifest_path)

    def test_cross_task_writer_overlap_and_backlog_are_audited(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            ledger = root / "events.jsonl"
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
            starts = [
                ("2026-08-14T00:10:00Z", "T-01", "writer-1", ["src"]),
                ("2026-08-14T00:11:00Z", "T-02", "writer-2", ["src/file.py"]),
                ("2026-08-14T01:01:30Z", "T-03", "writer-3", ["docs"]),
            ]
            for timestamp, task, actor, paths in starts:
                events.append(
                    {
                        "schema_version": "2.0",
                        "timestamp": timestamp,
                        "task_id": task,
                        "event": "worker_started",
                        "actor": actor,
                        "capability_tier": "standard",
                        "reasoning_tier": "medium",
                        "approved_writer": True,
                        "team_skill_loaded": False,
                        "owned_paths": paths,
                    }
                )
            events.sort(key=lambda event: event["timestamp"])
            ledger.write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
                newline="\n",
            )
            self.refresh_ledger_digest(manifest_path)
            result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path), manifest_path
            )

        codes = {
            item["code"]
            for trial in result["trials"]
            for item in trial["issues"]
        }
        self.assertFalse(result["stable_v2_ready"])
        self.assertIn("hard_gate:overlapping_writer_paths", codes)
        self.assertIn("hard_gate:writer_started_with_integration_backlog", codes)

    def test_explicit_sequence_prevents_boundary_tie_reordering(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 6, failing_index=5)
            ledger = root / "events.jsonl"
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
            for event in events:
                if event["task_id"] == "T-06" and event["event"] == "task_ready":
                    event["timestamp"] = "2026-08-14T00:05:00Z"
            ledger.write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
                newline="\n",
            )
            data = self.refresh_ledger_digest(manifest_path)
            result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path), manifest_path
            )
            self.assertEqual(result["first_comparable_trial_ids"][-1], "TRIAL-005")
            self.assertFalse(result["stable_v2_ready"])

            data["trials"][4]["registration_sequence"] = 6
            data["trials"][5]["registration_sequence"] = 5
            manifest_path.write_text(json.dumps(data), encoding="utf-8")
            swapped = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path), manifest_path
            )

        self.assertFalse(swapped["stable_v2_ready"])
        swapped_codes = {
            item["code"]
            for trial in swapped["trials"]
            for item in trial["issues"]
        }
        self.assertIn(
            "task_ready_release_trial_registration_sequence_mismatch",
            swapped_codes,
        )

    def test_omitted_task_ready_fails_registry_completeness(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(Path(raw), 6)
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            del data["trials"][0]
            manifest_path.write_text(json.dumps(data), encoding="utf-8")
            result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path), manifest_path
            )

        self.assertFalse(result["gates"]["registry_complete"])
        self.assertEqual(result["missing_trial_identities"], [["source-a", "T-01"]])
        self.assertFalse(result["stable_v2_ready"])

    def test_evidence_digest_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            request = root / "evidence" / "request-01.json"
            request.write_text(request.read_text() + "\n", encoding="utf-8")
            result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path), manifest_path
            )

        codes = {item["code"] for item in result["trials"][0]["issues"]}
        self.assertIn("request_evidence_digest_mismatch", codes)
        self.assertFalse(result["stable_v2_ready"])

    def test_frozen_source_registry_and_ledger_prefix_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            registry = root / "source-registry.json"
            registry.write_text(registry.read_text() + "\n", encoding="utf-8")
            registry_result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path), manifest_path
            )
            self.assertFalse(registry_result["gates"]["source_snapshots_integral"])

            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            data["source_registry_sha256"] = hashlib.sha256(
                registry.read_bytes()
            ).hexdigest()
            ledger = root / "events.jsonl"
            ledger.write_text(" " + ledger.read_text(), encoding="utf-8")
            data["sources"][0]["ledger_sha256"] = hashlib.sha256(
                ledger.read_bytes()
            ).hexdigest()
            manifest_path.write_text(json.dumps(data), encoding="utf-8")
            prefix_result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path), manifest_path
            )

        source_codes = {
            item["code"] for item in prefix_result["sources"][0]["issues"]
        }
        self.assertIn("ledger_prefix_digest_mismatch", source_codes)
        self.assertFalse(prefix_result["stable_v2_ready"])

    def test_fifteen_unique_tasks_are_required_for_formal_sample(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(Path(raw), 15)
            result = v2_release_gate.evaluate_manifest(
                v2_release_gate.load_manifest(manifest_path), manifest_path
            )
            self.assertTrue(result["formal_efficiency_sample_size_ready"])

            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            duplicate = dict(data["trials"][0])
            duplicate["trial_id"] = "TRIAL-016"
            duplicate["registration_sequence"] = 16
            data["trials"].append(duplicate)
            manifest_path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError, "duplicate trial task identity"
            ):
                v2_release_gate.load_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
