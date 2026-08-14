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
V1_BASELINE_ID = "baseline-c1-r1-no-delegation"


class V2ReleaseGateTests(unittest.TestCase):
    def build_trial_files(
        self,
        root: Path,
        count: int,
        *,
        failing_index: int | None = None,
        receipt_stratum_override: tuple[int, str] | None = None,
        receipt_baseline_id_override: tuple[int, str] | None = None,
        baseline_digest_override: str | None = None,
        formal_efficiency_comparable: bool = True,
        baseline_evidence_scope: str = "task-level",
        baseline_extra_field: bool = False,
        baseline_source_digest_override: str | None = None,
        baseline_source_path_override: str | None = None,
        omit_acceptance_source: bool = False,
        omit_baseline_source_blob: bool = False,
        metrics_source_kind: str = "metrics_record",
        historical_backlog: bool = False,
        integration_mode: str = "same_commit",
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
        if historical_backlog:
            frozen_prefix += json.dumps(
                {
                    "schema_version": "2.0",
                    "timestamp": "2026-08-13T01:00:00Z",
                    "task_id": "HISTORICAL-001",
                    "event": "dev_complete",
                    "actor": "main-agent",
                    "commit": "d" * 40,
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
            if integration_mode == "same_tree":
                stable_tree = subprocess.run(
                    ["git", "-C", str(repo), "rev-parse", f"{stable}^{{tree}}"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                candidate = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(repo),
                        "commit-tree",
                        stable_tree,
                        "-m",
                        f"squash candidate {task}",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(repo),
                        "update-ref",
                        f"refs/heads/feature/{task}",
                        candidate,
                    ],
                    check=True,
                    capture_output=True,
                )
                integration_proof = {
                    "mode": "same_tree",
                    "candidate_ref": f"refs/heads/feature/{task}",
                    "candidate_tree": stable_tree,
                    "stable_tree": stable_tree,
                    "tree_scope": {
                        "history_sensitive": False,
                        "non_tree_dependencies": [],
                    },
                }
            else:
                candidate = stable
                integration_proof = {"mode": "same_commit"}
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
                        "v1_baseline_id": V1_BASELINE_ID,
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
                        "integration_proof": integration_proof,
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
                    "v1_baseline_id": V1_BASELINE_ID,
                    "v1_baseline_stratum": "C1|R1|no-delegation",
                    "comparable": True,
                    "disposition": "accepted",
                    "genuine_request": True,
                    "synthetic": False,
                    "candidate_commit": candidate,
                    "stable_commit": stable,
                    "integration_proof": integration_proof,
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
        baseline_contract = root / "v1-task-contract.md"
        baseline_contract.write_text(
            "# Historical task\n\nC1 / R1 / no-delegation\n",
            encoding="utf-8",
            newline="\n",
        )
        baseline_qa = root / "v1-qa-report.md"
        baseline_qa.write_text(
            "# QA\n\nPASSED\n", encoding="utf-8", newline="\n"
        )
        baseline_source_files = [baseline_contract, baseline_qa]
        source_evidence = [
            {
                "source_id": "historical-task-contract",
                "evidence_kind": "task_contract",
                "source_revision": "a" * 40,
                "evidence_path": baseline_source_path_override
                or baseline_contract.name,
                "evidence_sha256": baseline_source_digest_override
                or hashlib.sha256(baseline_contract.read_bytes()).hexdigest(),
                "supports": ["task_identity", "stratum"],
            }
        ]
        if not omit_acceptance_source:
            source_evidence.append(
                {
                    "source_id": "historical-qa-report",
                    "evidence_kind": "qa_report",
                    "source_revision": "b" * 40,
                    "evidence_path": baseline_qa.name,
                    "evidence_sha256": hashlib.sha256(
                        baseline_qa.read_bytes()
                    ).hexdigest(),
                    "supports": ["acceptance"],
                }
            )
        if formal_efficiency_comparable:
            baseline_metrics = root / "v1-metrics.json"
            baseline_metrics.write_text(
                json.dumps({"accepted_cycle_hours": 1.0}, sort_keys=True),
                encoding="utf-8",
            )
            baseline_source_files.append(baseline_metrics)
            source_evidence.append(
                {
                    "source_id": "historical-metrics",
                    "evidence_kind": metrics_source_kind,
                    "source_revision": "c" * 40,
                    "evidence_path": baseline_metrics.name,
                    "evidence_sha256": hashlib.sha256(
                        baseline_metrics.read_bytes()
                    ).hexdigest(),
                    "supports": ["efficiency_denominator"],
                }
            )
        baseline_evidence = root / "v1-baseline.json"
        baseline_data = {
            "schema_version": "1.0",
            "baseline_id": V1_BASELINE_ID,
            "baseline_version": "v1.0.0",
            "measurement_type": "historical_reconstruction",
            "stratum_id": "C1|R1|no-delegation",
            "evidence_scope": baseline_evidence_scope,
            "efficiency_denominators_available": formal_efficiency_comparable,
            "source_evidence": source_evidence,
            "limitations": ["test fixture"],
        }
        if baseline_extra_field:
            baseline_data["undeclared_claim"] = True
        baseline_evidence.write_text(
            json.dumps(baseline_data, sort_keys=True),
            encoding="utf-8",
        )
        frozen_baseline = {
            "baseline_id": V1_BASELINE_ID,
            "stratum_id": "C1|R1|no-delegation",
            "evidence_path": "v1-baseline.json",
            "evidence_sha256": baseline_digest_override
            or hashlib.sha256(baseline_evidence.read_bytes()).hexdigest(),
            "stable_release_comparable": True,
            "formal_efficiency_comparable": formal_efficiency_comparable,
        }
        source_registry = root / "source-registry.json"
        source_registry.write_text(
            json.dumps(
                {
                    "schema_version": "2.0",
                    "candidate_commit": SKILL_COMMIT,
                    "candidate_frozen_at": "2026-08-14T00:00:00Z",
                    "required_comparable_tasks": 5,
                    "v1_baselines": [frozen_baseline],
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
                    "candidate_version": "v2.0.0-rc.4",
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
        anchor_repo = root / "anchor"
        anchor_repo.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main", str(anchor_repo)],
            check=True,
            capture_output=True,
        )
        for key, value in (
            ("user.name", "Release Gate Test"),
            ("user.email", "test@example.invalid"),
        ):
            subprocess.run(
                ["git", "-C", str(anchor_repo), "config", key, value],
                check=True,
            )

        def anchor_commit(message: str) -> str:
            subprocess.run(
                ["git", "-C", str(anchor_repo), "add", "."],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(anchor_repo), "commit", "-m", message],
                check=True,
                capture_output=True,
            )
            return subprocess.run(
                ["git", "-C", str(anchor_repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        (anchor_repo / v2_release_gate.ANCHOR_REGISTRY_PATH).write_bytes(
            source_registry.read_bytes()
        )
        (anchor_repo / "v1-baseline.json").write_bytes(baseline_evidence.read_bytes())
        for source_file in baseline_source_files:
            if omit_baseline_source_blob and source_file == baseline_contract:
                continue
            (anchor_repo / source_file.name).write_bytes(source_file.read_bytes())
        freeze_commit = anchor_commit("freeze candidate and sources")
        registrations = anchor_repo / v2_release_gate.ANCHOR_RECEIPTS_DIR
        registrations.mkdir()
        ready_by_task = {
            event["task_id"]: event for event in events if event["event"] == "task_ready"
        }
        registration_commits = []
        for index, trial in enumerate(trials, 1):
            ready = ready_by_task[trial["task_id"]]
            stratum = trial["v1_baseline_stratum"]
            if receipt_stratum_override and receipt_stratum_override[0] == index:
                stratum = receipt_stratum_override[1]
            baseline_id = trial["v1_baseline_id"]
            if receipt_baseline_id_override and receipt_baseline_id_override[0] == index:
                baseline_id = receipt_baseline_id_override[1]
            receipt = {
                "schema_version": "2.0",
                "receipt_type": "task_ready_registration",
                "registration_sequence": index,
                "source_id": trial["source_id"],
                "project_evidence_id": "project-a-evidence",
                "task_id": trial["task_id"],
                "registered_at": ready["timestamp"],
                "skill_candidate_commit": trial["skill_candidate_commit"],
                "request_evidence": trial["request_evidence"],
                "request_evidence_sha256": trial["request_evidence_sha256"],
                "complexity": ready["complexity"],
                "risk": ready["risk"],
                "topology": ready["topology"],
                "release_trial_comparable": trial["comparable"],
                "v1_baseline_id": baseline_id,
                "v1_baseline_stratum": stratum,
                "genuine_request": trial["genuine_request"],
                "synthetic": trial["synthetic"],
            }
            (registrations / f"{index:06d}.json").write_text(
                json.dumps(receipt, sort_keys=True), encoding="utf-8"
            )
            registration_commits.append(anchor_commit(f"register task {index:06d}"))
        final_registration = registration_commits[-1] if registration_commits else freeze_commit
        (anchor_repo / v2_release_gate.ANCHOR_CLOSURE_PATH).write_text(
            json.dumps(
                {
                    "schema_version": "2.0",
                    "closure_type": "registration_window_closed",
                    "candidate_commit": SKILL_COMMIT,
                    "anchor_freeze_commit": freeze_commit,
                    "final_registration_commit": final_registration,
                    "closed_at": "2026-08-14T23:59:59Z",
                    "registration_count": count,
                    "trial_manifest_sha256": hashlib.sha256(
                        manifest.read_bytes()
                    ).hexdigest(),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        head_commit = anchor_commit("close registration window")
        (root / "_anchor-test.json").write_text(
            json.dumps(
                {
                    "repo": str(anchor_repo),
                    "freeze": freeze_commit,
                    "head": head_commit,
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def anchor_for(self, manifest_path: Path) -> dict:
        data = json.loads(
            (manifest_path.parent / "_anchor-test.json").read_text(encoding="utf-8")
        )
        return v2_release_gate.load_anchor(
            Path(data["repo"]), data["freeze"], data["head"]
        )

    def evaluate(self, manifest_path: Path) -> dict:
        return v2_release_gate.evaluate_manifest(
            v2_release_gate.load_manifest(manifest_path),
            manifest_path,
            self.anchor_for(manifest_path),
        )

    def main_args(self, manifest_path: Path) -> list[str]:
        data = json.loads(
            (manifest_path.parent / "_anchor-test.json").read_text(encoding="utf-8")
        )
        return [
            "--manifest",
            str(manifest_path),
            "--anchor-repo",
            data["repo"],
            "--anchor-freeze-commit",
            data["freeze"],
            "--anchor-head-commit",
            data["head"],
        ]

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
            result = self.evaluate(manifest_path)
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = v2_release_gate.main(self.main_args(manifest_path))

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
            result = self.evaluate(manifest_path)
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = v2_release_gate.main(self.main_args(manifest_path))

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
            result = self.evaluate(manifest_path)

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
            result = self.evaluate(manifest_path)

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
            result = self.evaluate(manifest_path)

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
            result = self.evaluate(manifest_path)
            self.assertEqual(result["first_comparable_trial_ids"][-1], "TRIAL-005")
            self.assertFalse(result["stable_v2_ready"])

            data["trials"][4]["registration_sequence"] = 6
            data["trials"][5]["registration_sequence"] = 5
            manifest_path.write_text(json.dumps(data), encoding="utf-8")
            swapped = self.evaluate(manifest_path)

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
            result = self.evaluate(manifest_path)

        self.assertFalse(result["gates"]["registry_complete"])
        self.assertEqual(result["missing_trial_identities"], [["source-a", "T-01"]])
        self.assertFalse(result["stable_v2_ready"])

    def test_evidence_digest_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            request = root / "evidence" / "request-01.json"
            request.write_text(request.read_text() + "\n", encoding="utf-8")
            result = self.evaluate(manifest_path)

        codes = {item["code"] for item in result["trials"][0]["issues"]}
        self.assertIn("request_evidence_digest_mismatch", codes)
        self.assertFalse(result["stable_v2_ready"])

    def test_frozen_source_registry_and_ledger_prefix_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            registry = root / "source-registry.json"
            registry.write_text(registry.read_text() + "\n", encoding="utf-8")
            registry_result = self.evaluate(manifest_path)
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
            prefix_result = self.evaluate(manifest_path)

        source_codes = {
            item["code"] for item in prefix_result["sources"][0]["issues"]
        }
        self.assertIn("ledger_prefix_digest_mismatch", source_codes)
        self.assertFalse(prefix_result["stable_v2_ready"])

    def test_same_commit_requires_candidate_and_stable_equality(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            repo = root / "project"
            empty_tree = subprocess.run(
                ["git", "-C", str(repo), "mktree"],
                input="",
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            candidate = subprocess.run(
                ["git", "-C", str(repo), "commit-tree", empty_tree, "-m", "isolated"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            trial = data["trials"][0]
            trial["candidate_commit"] = candidate
            acceptance_path = root / trial["acceptance_evidence"]
            acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
            acceptance["candidate_commit"] = candidate
            acceptance_path.write_text(json.dumps(acceptance, sort_keys=True), encoding="utf-8")
            trial["acceptance_evidence_sha256"] = hashlib.sha256(
                acceptance_path.read_bytes()
            ).hexdigest()
            ledger = root / "events.jsonl"
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
            for event in events:
                if event["task_id"] == "T-01" and event["event"] in {
                    "dev_complete", "accepted"
                }:
                    event["commit"] = candidate
            ledger.write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
                newline="\n",
            )
            manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            self.refresh_ledger_digest(manifest_path)
            result = self.evaluate(manifest_path)

        codes = {item["code"] for item in result["trials"][0]["issues"]}
        self.assertIn("same_commit_mismatch", codes)
        self.assertFalse(result["stable_v2_ready"])

    def test_non_ancestor_same_tree_candidate_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw), 5, integration_mode="same_tree"
            )
            result = self.evaluate(manifest_path)

        self.assertTrue(result["stable_v2_ready"])
        self.assertFalse(
            any(
                item["code"] == "candidate_commit_not_in_stable_commit"
                for trial in result["trials"]
                for item in trial["issues"]
            )
        )

    def test_same_tree_tree_label_and_ref_are_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(
                root, 5, integration_mode="same_tree"
            )
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            trial = data["trials"][0]
            trial["integration_proof"]["candidate_tree"] = "0" * 40
            acceptance_path = root / trial["acceptance_evidence"]
            acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
            acceptance["integration_proof"] = trial["integration_proof"]
            acceptance_path.write_text(
                json.dumps(acceptance, sort_keys=True), encoding="utf-8"
            )
            trial["acceptance_evidence_sha256"] = hashlib.sha256(
                acceptance_path.read_bytes()
            ).hexdigest()
            manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            result = self.evaluate(manifest_path)

        codes = {item["code"] for item in result["trials"][0]["issues"]}
        self.assertIn("candidate_tree_mismatch", codes)
        self.assertFalse(result["stable_v2_ready"])

    def test_same_tree_rejects_moved_candidate_ref(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(
                root, 5, integration_mode="same_tree"
            )
            repo = root / "project"
            moved = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "main"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", str(repo), "update-ref", "refs/heads/feature/T-01", moved],
                check=True,
                capture_output=True,
            )
            result = self.evaluate(manifest_path)

        codes = {item["code"] for item in result["trials"][0]["issues"]}
        self.assertIn("candidate_ref_invalid", codes)
        self.assertFalse(result["stable_v2_ready"])

    def test_integration_proof_rejects_non_string_and_non_tree_scope_values(self) -> None:
        cases = [
            {"mode": 1},
            {
                "mode": "same_tree",
                "candidate_ref": "refs/heads/feature/T-01",
                "candidate_tree": 1,
                "stable_tree": "a" * 40,
                "tree_scope": {
                    "history_sensitive": False,
                    "non_tree_dependencies": [],
                },
            },
            {
                "mode": "same_tree",
                "candidate_ref": "refs/heads/feature/T-01",
                "candidate_tree": "a" * 40,
                "stable_tree": "b" * 40,
                "tree_scope": {
                    "history_sensitive": True,
                    "non_tree_dependencies": [],
                },
            },
            {
                "mode": "same_tree",
                "candidate_ref": "refs/heads/feature/T-01",
                "candidate_tree": "a" * 40,
                "stable_tree": "b" * 40,
                "tree_scope": {
                    "history_sensitive": False,
                    "non_tree_dependencies": ["generated-output"],
                },
            },
        ]
        for proof in cases:
            with self.subTest(proof=proof):
                with self.assertRaises(v2_release_gate.ReleaseGateError):
                    v2_release_gate.validate_integration_proof(proof, "proof")

    def test_candidate_ref_shape_rejects_short_pseudo_and_other_namespaces(self) -> None:
        for raw_ref in (
            "feature/T-01",
            "a" * 40,
            "HEAD",
            "refs/remotes/origin/main",
            "refs/pull/1/head",
            "refs/heads/feature/T-01^",
            "refs/heads/feature/T-01~1",
            "refs/heads/feature/T-01@{1}",
        ):
            with self.subTest(ref=raw_ref):
                with self.assertRaises(v2_release_gate.ReleaseGateError):
                    v2_release_gate.validate_integration_proof(
                        {
                            "mode": "same_tree",
                            "candidate_ref": raw_ref,
                            "candidate_tree": "a" * 40,
                            "stable_tree": "a" * 40,
                            "tree_scope": {
                                "history_sensitive": False,
                                "non_tree_dependencies": [],
                            },
                        },
                        "proof",
                    )

    def test_manifest_proof_bound_scalars_require_string_types(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            original = json.loads(manifest_path.read_text(encoding="utf-8"))
            cases = [
                ("candidate_commit", 1),
                ("source_registry_sha256", 1),
                ("sources[0].ledger_prefix_sha256", 1),
                ("sources[0].ledger_sha256", 1),
                ("trials[0].skill_candidate_commit", 1),
                ("trials[0].request_evidence_sha256", 1),
                ("trials[0].candidate_commit", 1),
                ("trials[0].stable_commit", 1),
                ("trials[0].acceptance_evidence_sha256", 1),
            ]
            for field, value in cases:
                data = json.loads(json.dumps(original))
                if field.startswith("sources"):
                    data["sources"][0][field.split(".", 1)[1]] = value
                elif field.startswith("trials"):
                    data["trials"][0][field.split(".", 1)[1]] = value
                else:
                    data[field] = value
                manifest_path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(field=field):
                    with self.assertRaises(v2_release_gate.ReleaseGateError):
                        v2_release_gate.load_manifest(manifest_path)

    def test_unregistered_writer_violation_is_a_source_level_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            ledger = root / "events.jsonl"
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
            events.extend(
                [
                    {
                        "schema_version": "2.0",
                        "timestamp": "2026-08-14T00:10:00Z",
                        "task_id": "T-01",
                        "event": "worker_started",
                        "actor": "writer-1",
                        "capability_tier": "standard",
                        "reasoning_tier": "medium",
                        "approved_writer": True,
                        "team_skill_loaded": False,
                        "owned_paths": ["src"],
                    },
                    {
                        "schema_version": "2.0",
                        "timestamp": "2026-08-14T00:11:00Z",
                        "task_id": "UNREGISTERED",
                        "event": "worker_started",
                        "actor": "writer-x",
                        "capability_tier": "standard",
                        "reasoning_tier": "medium",
                        "approved_writer": False,
                        "team_skill_loaded": False,
                        "owned_paths": ["src/file.py"],
                    },
                ]
            )
            events.sort(key=lambda event: event["timestamp"])
            ledger.write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
                newline="\n",
            )
            self.refresh_ledger_digest(manifest_path)
            result = self.evaluate(manifest_path)

        codes = {item["code"] for item in result["sources"][0]["issues"]}
        self.assertIn("hard_gate:missing_task_ready", codes)
        self.assertIn("hard_gate:unapproved_writer", codes)
        self.assertIn("hard_gate:overlapping_writer_paths", codes)
        self.assertFalse(result["stable_v2_ready"])

    def test_pre_freeze_backlog_state_blocks_new_writer_in_window(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5, historical_backlog=True)
            ledger = root / "events.jsonl"
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
            events.append(
                {
                    "schema_version": "2.0",
                    "timestamp": "2026-08-14T00:10:00Z",
                    "task_id": "T-01",
                    "event": "worker_started",
                    "actor": "writer-1",
                    "capability_tier": "standard",
                    "reasoning_tier": "medium",
                    "approved_writer": True,
                    "team_skill_loaded": False,
                    "owned_paths": ["src"],
                }
            )
            events.sort(key=lambda event: event["timestamp"])
            ledger.write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
                newline="\n",
            )
            self.refresh_ledger_digest(manifest_path)
            result = self.evaluate(manifest_path)

        codes = {item["code"] for item in result["sources"][0]["issues"]}
        self.assertIn("hard_gate:writer_started_with_integration_backlog", codes)
        self.assertFalse(result["stable_v2_ready"])

    def test_deleted_failure_and_rewritten_sequence_cannot_replace_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 6, failing_index=1)
            ledger = root / "events.jsonl"
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
            events = [event for event in events if event["task_id"] != "T-01"]
            for event in events:
                if event.get("release_trial_registration_sequence"):
                    event["release_trial_registration_sequence"] -= 1
            ledger.write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
                newline="\n",
            )
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            data["trials"] = data["trials"][1:]
            for trial in data["trials"]:
                trial["registration_sequence"] -= 1
            manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            self.refresh_ledger_digest(manifest_path)
            result = self.evaluate(manifest_path)

        self.assertEqual(result["missing_trial_identities"], [["source-a", "T-01"]])
        self.assertEqual(
            result["missing_ledger_registration_identities"], [["source-a", "T-01"]]
        )
        self.assertIn(
            "manifest_anchor_digest_mismatch",
            {item["code"] for item in result["source_registry"]["issues"]},
        )
        self.assertFalse(result["stable_v2_ready"])

    def test_unanchored_task_ready_fails_registry_completeness(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            ledger = root / "events.jsonl"
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
            events.append(
                {
                    "schema_version": "2.0",
                    "timestamp": "2026-08-14T00:30:00Z",
                    "task_id": "UNANCHORED-READY",
                    "event": "task_ready",
                    "complexity": "C1",
                    "risk": "R1",
                    "topology": "no-delegation",
                    "governance_profile": "lean",
                    "material_behavior_change": False,
                }
            )
            events.sort(key=lambda event: event["timestamp"])
            ledger.write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
                newline="\n",
            )
            self.refresh_ledger_digest(manifest_path)
            result = self.evaluate(manifest_path)

        self.assertEqual(
            result["unanchored_ledger_registration_identities"],
            [["source-a", "UNANCHORED-READY"]],
        )
        self.assertFalse(result["stable_v2_ready"])

    def test_v1_stratum_must_equal_registered_complexity_risk_topology(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw), 5, receipt_stratum_override=(1, "C2|R1|no-delegation")
            )
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError, "stratum does not match"
            ):
                self.anchor_for(manifest_path)

    def test_comparable_receipt_must_reference_a_frozen_v1_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw),
                5,
                receipt_baseline_id_override=(1, "unfrozen-baseline"),
            )
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError, "V1 baseline is not frozen"
            ):
                self.anchor_for(manifest_path)

    def test_v1_baseline_evidence_digest_is_verified_at_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw), 5, baseline_digest_override="0" * 64
            )
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError, "evidence digest differs"
            ):
                self.anchor_for(manifest_path)

    def test_task_ready_baseline_identity_must_match_anchor_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            ledger = root / "events.jsonl"
            events = [json.loads(line) for line in ledger.read_text().splitlines()]
            for event in events:
                if event["task_id"] == "T-01" and event["event"] == "task_ready":
                    event["v1_baseline_id"] = "different-baseline"
            ledger.write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
                newline="\n",
            )
            self.refresh_ledger_digest(manifest_path)
            result = self.evaluate(manifest_path)

        codes = {item["code"] for item in result["trials"][0]["issues"]}
        self.assertIn("task_ready_v1_baseline_id_mismatch", codes)
        self.assertFalse(result["stable_v2_ready"])

    def test_post_close_receipt_edit_is_not_a_valid_anchor_head(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = self.build_trial_files(root, 5)
            metadata = json.loads((root / "_anchor-test.json").read_text())
            anchor_repo = Path(metadata["repo"])
            receipt = anchor_repo / v2_release_gate.ANCHOR_RECEIPTS_DIR / "000001.json"
            receipt.write_text(receipt.read_text() + "\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(anchor_repo), "add", "."],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(anchor_repo), "commit", "-m", "rewrite receipt"],
                check=True,
                capture_output=True,
            )
            rewritten_head = subprocess.run(
                ["git", "-C", str(anchor_repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError, "anchor head must add only"
            ):
                v2_release_gate.load_anchor(
                    anchor_repo, metadata["freeze"], rewritten_head
                )
            self.assertTrue(self.evaluate(manifest_path)["stable_v2_ready"])

    def test_fifteen_unique_tasks_are_required_for_formal_sample(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(Path(raw), 15)
            result = self.evaluate(manifest_path)
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

    def test_formal_sample_requires_efficiency_eligible_v1_baselines(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw), 15, formal_efficiency_comparable=False
            )
            result = self.evaluate(manifest_path)

        self.assertTrue(result["stable_v2_ready"])
        self.assertEqual(result["formal_efficiency_comparable_trials"], 0)
        self.assertFalse(result["formal_efficiency_sample_size_ready"])

    def test_formal_efficiency_baseline_must_be_task_level(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw), 5, baseline_evidence_scope="case-level"
            )
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError,
                "must be task-level for formal efficiency comparability",
            ):
                self.evaluate(manifest_path)

    def test_v1_baseline_evidence_contract_is_strict(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw), 5, baseline_extra_field=True
            )
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError,
                "fields differ from the contract",
            ):
                self.evaluate(manifest_path)

        baseline = {
            "baseline_id": V1_BASELINE_ID,
            "stratum_id": "C1|R1|no-delegation",
            "formal_efficiency_comparable": False,
        }
        valid = {
            "schema_version": "1.0",
            "baseline_id": V1_BASELINE_ID,
            "baseline_version": "v1.0.0",
            "measurement_type": "historical_reconstruction",
            "stratum_id": "C1|R1|no-delegation",
            "evidence_scope": "task-level",
            "efficiency_denominators_available": False,
            "source_evidence": [
                {
                    "source_id": "contract",
                    "evidence_kind": "task_contract",
                    "source_revision": "a" * 40,
                    "evidence_path": "contract.md",
                    "evidence_sha256": "1" * 64,
                    "supports": ["task_identity", "stratum"],
                },
                {
                    "source_id": "qa",
                    "evidence_kind": "qa_report",
                    "source_revision": "b" * 40,
                    "evidence_path": "qa.md",
                    "evidence_sha256": "2" * 64,
                    "supports": ["acceptance"],
                },
            ],
            "limitations": ["test fixture"],
        }
        cases = [
            (
                "numeric boolean",
                lambda data: data.__setitem__(
                    "efficiency_denominators_available", 0
                ),
                "must be boolean",
            ),
            (
                "non-string scope",
                lambda data: data.__setitem__("evidence_scope", []),
                "evidence_scope is invalid",
            ),
            (
                "non-string kind",
                lambda data: data["source_evidence"][0].__setitem__(
                    "evidence_kind", []
                ),
                "evidence_kind is invalid",
            ),
            (
                "numeric revision",
                lambda data: data["source_evidence"][0].__setitem__(
                    "source_revision", int("1" * 40)
                ),
                "source_revision must be a full SHA string",
            ),
            (
                "numeric digest",
                lambda data: data["source_evidence"][0].__setitem__(
                    "evidence_sha256", int("1" * 64)
                ),
                "evidence_sha256 must be a SHA-256 string",
            ),
            (
                "non-string claim",
                lambda data: data["source_evidence"][0].__setitem__(
                    "supports", [{}]
                ),
                "supports is invalid",
            ),
        ]
        for name, mutate, message in cases:
            with self.subTest(case=name):
                data = json.loads(json.dumps(valid))
                mutate(data)
                with self.assertRaisesRegex(v2_release_gate.ReleaseGateError, message):
                    v2_release_gate.validate_v1_baseline_evidence(
                        json.dumps(data).encode("utf-8"), baseline, "V1 baseline"
                    )

    def test_v1_baseline_source_blob_must_exist_at_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw), 5, omit_baseline_source_blob=True
            )
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError,
                "V1 baseline .* source historical-task-contract cannot be read",
            ):
                self.evaluate(manifest_path)

    def test_v1_baseline_source_digest_is_verified_at_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw), 5, baseline_source_digest_override="0" * 64
            )
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError,
                "source historical-task-contract evidence digest differs",
            ):
                self.evaluate(manifest_path)

    def test_v1_baseline_source_claims_must_cover_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw), 5, omit_acceptance_source=True
            )
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError,
                "source_evidence is missing claims:.*acceptance",
            ):
                self.evaluate(manifest_path)

    def test_efficiency_denominator_requires_metrics_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest_path = self.build_trial_files(
                Path(raw), 5, metrics_source_kind="qa_report"
            )
            with self.assertRaisesRegex(
                v2_release_gate.ReleaseGateError,
                "qa_report cannot support efficiency_denominator",
            ):
                self.evaluate(manifest_path)

    def test_v1_baseline_source_path_must_be_a_normalized_file_path(self) -> None:
        for invalid_path in ("../task-contract.md", "."):
            with self.subTest(path=invalid_path), tempfile.TemporaryDirectory() as raw:
                manifest_path = self.build_trial_files(
                    Path(raw), 5, baseline_source_path_override=invalid_path
                )
                with self.assertRaisesRegex(
                    v2_release_gate.ReleaseGateError,
                    "evidence_path must be a normalized relative POSIX path",
                ):
                    self.evaluate(manifest_path)


if __name__ == "__main__":
    unittest.main()
