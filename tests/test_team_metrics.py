import contextlib
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "ai-native-dev-team" / "scripts" / "team_metrics.py"
SPEC = importlib.util.spec_from_file_location("team_metrics_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
team_metrics = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = team_metrics
SPEC.loader.exec_module(team_metrics)

BASE_TIME = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
ROUTING = {
    "layer": "controlled",
    "complexity": "C2",
    "risk": "R2",
    "capability": "advanced",
    "reasoning_tier": "high",
}


def at(minutes: int) -> str:
    return (BASE_TIME + timedelta(minutes=minutes)).isoformat()


def event(task_id: str, event_type: str, minute: int, **fields: object) -> dict:
    result = {
        "schema_version": "team-metrics-event-v1",
        "task_id": task_id,
        "event": event_type,
        "at": at(minute),
        "ledger_writer": "main-agent",
    }
    result.update(fields)
    return result


def ready(task_id: str, minute: int, risk: str = "R2", material: bool = True) -> dict:
    routing = dict(ROUTING, risk=risk)
    return event(task_id, "task_ready", minute, routing=routing, material=material)


def worker(
    task_id: str,
    minute: int,
    approved: bool,
    paths: list[str],
    *,
    skill_loaded: bool = False,
    repo_wide_search_used: bool = False,
    out_of_scope_reads: bool = False,
    **fields: object,
) -> dict:
    return event(
        task_id,
        "worker_started",
        minute,
        writer={
            "id": f"{task_id}-writer",
            "approved": approved,
            "paths": paths,
            "skill_loaded": skill_loaded,
            "repo_wide_search_used": repo_wide_search_used,
            "out_of_scope_reads": out_of_scope_reads,
        },
        **fields,
    )


def dev(task_id: str, candidate_id: str, minute: int, **fields: object) -> dict:
    return event(
        task_id,
        "dev_complete",
        minute,
        candidate={"id": candidate_id, "stable_identity": None},
        **fields,
    )


def qa(
    task_id: str,
    candidate_id: str,
    minute: int,
    *,
    reused: bool = False,
    result: str = "passed",
) -> dict:
    return event(
        task_id,
        "qa_complete",
        minute,
        candidate={"id": candidate_id, "stable_identity": None},
        validation={
            "independent": True,
            "same_candidate": True,
            "result": result,
            "evidence_reused": reused,
        },
    )


def accepted(
    task_id: str,
    candidate_id: str,
    minute: int,
    *,
    owner_approval: bool = True,
    rollback: bool = True,
) -> dict:
    return event(
        task_id,
        "accepted",
        minute,
        candidate={"id": candidate_id, "stable_identity": f"stable-{candidate_id}"},
        rollback={
            "executable": rollback,
            "command": "git revert <exact-candidate>" if rollback else None,
        },
        owner_approval=owner_approval,
    )


class TeamMetricsTests(unittest.TestCase):
    def test_record_snapshot_audit_and_compare(self) -> None:
        events = [
            ready("MET-1", 0),
            worker(
                "MET-1",
                10,
                True,
                ["src/owned"],
                observations={
                    "model": "observed-model",
                    "provider": "observed-provider",
                    "reasoning": "high",
                    "input_tokens": None,
                    "output_tokens": None,
                    "cost": None,
                    "cost_currency": None,
                },
            ),
            dev(
                "MET-1",
                "candidate-1",
                40,
                observations={
                    "model": None,
                    "provider": None,
                    "reasoning": None,
                    "input_tokens": 120,
                    "output_tokens": 60,
                    "cost": 0.42,
                    "cost_currency": "USD",
                },
            ),
            qa("MET-1", "candidate-1", 50),
            accepted("MET-1", "candidate-1", 60),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "events.jsonl"
            event_file = root / "event.json"
            for item in events:
                event_file.write_text(json.dumps(item), encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        team_metrics.main(
                            [
                                "record",
                                "--ledger",
                                str(ledger),
                                "--event-file",
                                str(event_file),
                            ]
                        ),
                        0,
                    )

            recorded = team_metrics.load_ledger(ledger)
            audit = team_metrics.build_audit(recorded)
            self.assertTrue(audit["passed"])
            self.assertTrue(audit["hard_gate_passed"])
            audit_file = root / "audit.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    team_metrics.main(
                        [
                            "audit",
                            "--ledger",
                            str(ledger),
                            "--output",
                            str(audit_file),
                        ]
                    ),
                    0,
                )
            self.assertTrue(json.loads(audit_file.read_text(encoding="utf-8"))["passed"])

            snapshot_file = root / "snapshot.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    team_metrics.main(
                        [
                            "snapshot",
                            "--ledger",
                            str(ledger),
                            "--output",
                            str(snapshot_file),
                            "--label",
                            "first",
                        ]
                    ),
                    0,
                )
            snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
            task = snapshot["tasks"][0]
            self.assertEqual(task["task_ready_to_accepted_minutes"], 60)
            self.assertEqual(task["dev_complete_to_accepted_minutes"], 20)
            self.assertEqual(task["active_minutes"], 30)
            self.assertEqual(task["governance_minutes"], 30)
            self.assertTrue(task["first_pass_independent_validation"])
            self.assertEqual(task["observed"]["model"], "observed-model")
            self.assertEqual(task["observed"]["input_tokens"], 120)
            self.assertEqual(task["observed"]["cost"], 0.42)

            second = copy.deepcopy(snapshot)
            second["label"] = "second"
            second["summary"]["task_ready_to_accepted_minutes"]["mean"] = 75
            second_file = root / "second.json"
            second_file.write_text(json.dumps(second), encoding="utf-8")
            compare_file = root / "compare.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    team_metrics.main(
                        [
                            "compare",
                            "--left",
                            str(snapshot_file),
                            "--right",
                            str(second_file),
                            "--output",
                            str(compare_file),
                        ]
                    ),
                    0,
                )
            comparison = json.loads(compare_file.read_text(encoding="utf-8"))
            self.assertTrue(comparison["descriptive_only"])
            self.assertEqual(comparison["deltas"]["task_ready_to_accepted_mean_minutes"], 15)

    def test_audit_reports_each_required_hard_gate(self) -> None:
        events = [
            ready("UNAPPROVED", 0),
            worker("UNAPPROVED", 1, False, ["src/unapproved"]),
            ready("ACTIVE", 2),
            worker("ACTIVE", 3, True, ["src/shared"]),
            ready("OVERLAP", 4),
            worker("OVERLAP", 5, True, ["src/shared"]),
            ready("BACKLOG", 6),
            dev("BACKLOG", "backlog-candidate", 7),
            ready("NEW-WRITER", 8),
            worker("NEW-WRITER", 9, True, ["src/new"]),
            ready("FULL-SKILL", 10, material=False),
            worker("FULL-SKILL", 11, True, ["src/full-skill"], skill_loaded=True),
            ready("OUT-OF-SCOPE", 12, material=False),
            worker(
                "OUT-OF-SCOPE",
                13,
                True,
                ["src/out-of-scope"],
                out_of_scope_reads=True,
            ),
            ready("MISSING-VALIDATION", 14),
            dev("MISSING-VALIDATION", "missing-candidate", 15),
            accepted("MISSING-VALIDATION", "missing-candidate", 16),
            ready("R3", 17, risk="R3"),
            dev("R3", "r3-candidate", 18),
            qa("R3", "r3-candidate", 19),
            accepted("R3", "r3-candidate", 20, owner_approval=False),
            ready("REUSED", 21),
            dev("REUSED", "candidate-a", 22),
            qa("REUSED", "candidate-a", 23),
            event("REUSED", "reopened", 24, reason="fix required"),
            dev("REUSED", "candidate-b", 25),
            qa("REUSED", "candidate-b", 26, reused=True),
            ready("MISSING-IDENTITY", 27, material=False),
            dev("MISSING-IDENTITY", "identity-candidate", 28),
            accepted(
                "MISSING-IDENTITY",
                "identity-candidate",
                29,
                rollback=False,
            ),
            ready("INVALID-PATH", 30, material=False),
            worker("INVALID-PATH", 31, True, ["src:stream"]),
        ]
        audit = team_metrics.build_audit(events)
        codes = {item["code"] for item in audit["violations"]}
        self.assertFalse(audit["hard_gate_passed"])
        self.assertTrue(team_metrics.HARD_GATE_CODES <= codes)

    def test_non_main_agent_cannot_record_and_unknown_stays_null(self) -> None:
        invalid = ready("NOT-MAIN", 0)
        invalid["ledger_writer"] = "writer"
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "events.jsonl"
            with self.assertRaises(team_metrics.MetricsError):
                team_metrics.record_event(ledger, invalid)
            self.assertFalse(ledger.exists())

        events = [
            ready("UNKNOWN", 0, material=False),
            dev(
                "UNKNOWN",
                "candidate-unknown",
                1,
                observations={
                    "model": "unknown",
                    "provider": None,
                    "reasoning": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "cost": None,
                    "cost_currency": None,
                },
            ),
            accepted("UNKNOWN", "candidate-unknown", 2),
        ]
        snapshot = team_metrics.build_snapshot(events)
        observed = snapshot["tasks"][0]["observed"]
        self.assertIsNone(observed["model"])
        self.assertIsNone(observed["provider"])
        self.assertIsNone(observed["cost"])

    def test_writer_context_is_required_and_exposed_without_repo_search_failure(self) -> None:
        valid = worker("CONTEXT", 1, True, ["src/context"])
        for field in ("skill_loaded", "repo_wide_search_used", "out_of_scope_reads"):
            missing = copy.deepcopy(valid)
            del missing["writer"][field]
            with self.subTest(field=field, case="missing"):
                with self.assertRaises(team_metrics.MetricsError):
                    team_metrics.validate_event(missing)

            wrong_type = copy.deepcopy(valid)
            wrong_type["writer"][field] = "false"
            with self.subTest(field=field, case="wrong_type"):
                with self.assertRaises(team_metrics.MetricsError):
                    team_metrics.validate_event(wrong_type)

        search_events = [
            ready("SEARCH", 0, material=False),
            worker("SEARCH", 1, True, ["src/search"], repo_wide_search_used=True),
        ]
        search_audit = team_metrics.build_audit(search_events)
        self.assertTrue(search_audit["passed"])
        self.assertTrue(search_audit["hard_gate_passed"])
        search_context = search_audit["context"]["worker_context"]["SEARCH"]
        self.assertTrue(search_context["repo_wide_search_used"])
        self.assertFalse(search_context["context_saving_claim"])
        search_snapshot = team_metrics.build_snapshot(search_events)
        self.assertEqual(
            search_snapshot["tasks"][0]["worker_context"],
            search_context,
        )

        gated_audit = team_metrics.build_audit(
            [
                ready("GATED", 0, material=False),
                worker(
                    "GATED",
                    1,
                    True,
                    ["src/gated"],
                    skill_loaded=True,
                    out_of_scope_reads=True,
                ),
            ]
        )
        gated_codes = {item["code"] for item in gated_audit["violations"]}
        self.assertIn("WRITER_LOADED_FULL_TEAM_SKILL", gated_codes)
        self.assertIn("WRITER_OUT_OF_SCOPE_READS", gated_codes)
        self.assertNotIn("REPO_WIDE_SEARCH_USED", gated_codes)

    def test_path_ownership_overlap_is_boundary_aware(self) -> None:
        identities = (
            ("src/../lib", "lib"),
            ("/src/../lib", "/lib"),
            (r"src\.\lib", "src/lib"),
            (r"C:\src\..\lib", "c:/lib"),
            (r"\\SERVER\SHARE\src\..\lib", "//server/share/lib"),
            ("SRC/FILE.PY", "src/file.py"),
            ("src ", "src"),
            ("src.", "src"),
        )
        for raw_path, expected in identities:
            with self.subTest(case="canonical_identity", raw_path=raw_path):
                self.assertEqual(team_metrics._normalize_path(raw_path), expected)

        namespace_paths = (
            (r"\\?\C:\repo\file.py", "extended_drive_backslash"),
            ("//?/C:/repo/file.py", "extended_drive_slash"),
            (r"\\?\UNC\server\share\repo", "extended_unc_backslash"),
            ("//?/UNC/server/share/repo", "extended_unc_slash"),
            (r"\\.\PIPE\name", "device_pipe_backslash"),
            ("//./PIPE/name", "device_pipe_slash"),
            (r"\??\C:\repo", "nt_namespace_backslash"),
            ("/??/C:/repo", "nt_namespace_slash"),
            (r"\\??\C:\repo", "nt_namespace_double_backslash"),
            ("//??/C:/repo", "nt_namespace_double_slash"),
        )
        for raw_path, label in namespace_paths:
            with self.subTest(case=label, raw_path=raw_path):
                with self.assertRaisesRegex(
                    team_metrics.MetricsError,
                    "Windows device or NT namespace prefix",
                ):
                    team_metrics._normalize_path(raw_path)

        ordinary_controls = (
            (r"C:\repo\file.py", "c:/repo/file.py"),
            ("C:/repo/file.py", "c:/repo/file.py"),
            (r"\\server\share\repo\file.py", "//server/share/repo/file.py"),
            ("//server/share/repo/file.py", "//server/share/repo/file.py"),
            ("/repo/file.py", "/repo/file.py"),
            ("repo/file.py", "repo/file.py"),
        )
        for raw_path, expected in ordinary_controls:
            with self.subTest(case="ordinary_control", raw_path=raw_path):
                self.assertEqual(team_metrics._normalize_path(raw_path), expected)

        invalid_paths = (
            "../lib",
            "src/../../lib",
            "/../lib",
            "C:/../lib",
            r"\\server\share\..\lib",
            "src/   ",
            "src/...",
            "src:stream",
            r"C:\src:stream",
        )
        for raw_path in invalid_paths:
            with self.subTest(case="invalid_identity", raw_path=raw_path):
                with self.assertRaises(team_metrics.MetricsError):
                    team_metrics._normalize_path(raw_path)

        cases = (
            ("parent_before_child", "src", "src/file.py", True),
            ("child_before_parent", "src/file.py", "src", True),
            ("exact_path", "src/file.py", "src/file.py", True),
            ("case_and_separator_equivalence", r"SRC\File.py", "src/file.py", True),
            ("relative_dot_dot", "src/../lib", "lib/file.py", True),
            ("relative_dot_dot_sibling", "src/../lib", "lib2/file.py", False),
            ("rooted_dot_dot", "/src/../lib", "/lib/file.py", True),
            ("drive_parent_child", r"C:\src", "c:/src/file.py", True),
            ("drive_dot_dot", r"C:\src\..\lib", "c:/lib/file.py", True),
            ("different_drives", "C:/src", "D:/src", False),
            (
                "unc_parent_child",
                r"\\server\share\src",
                "//SERVER/SHARE/src/file.py",
                True,
            ),
            (
                "different_unc_shares",
                r"\\server\share-a\src",
                r"\\server\share\src",
                False,
            ),
            ("trailing_space_component", "src ", "src/file.py", True),
            ("trailing_dot_component", "src.", "src/file.py", True),
            ("boundary_control", "src-a", "src", False),
            ("relative_and_drive_are_distinct", "src", "C:/src", False),
        )
        for label, first_path, second_path, overlaps in cases:
            with self.subTest(case=label):
                audit = team_metrics.build_audit(
                    [
                        ready("OWNER-A", 0, material=False),
                        worker("OWNER-A", 1, True, [first_path]),
                        ready("OWNER-B", 2, material=False),
                        worker("OWNER-B", 3, True, [second_path]),
                    ]
                )
                codes = {item["code"] for item in audit["violations"]}
                self.assertEqual(
                    "OVERLAPPING_PATH_OWNERSHIP" in codes,
                    overlaps,
                )

        states, violations = team_metrics.replay_events(
            [
                ready("VALID-OWNER", 0, material=False),
                worker("VALID-OWNER", 1, True, ["src"]),
                ready("INVALID-PATH", 2, material=False),
                worker(
                    "INVALID-PATH",
                    3,
                    True,
                    ["src:stream", "../src"],
                ),
            ]
        )
        invalid_codes = {
            item["code"]
            for item in violations
            if item["task_id"] == "INVALID-PATH"
        }
        self.assertIn("INVALID_WRITER_PATH", invalid_codes)
        self.assertNotIn("OVERLAPPING_PATH_OWNERSHIP", invalid_codes)
        self.assertEqual(states["INVALID-PATH"]["active_paths"], set())
        self.assertEqual(states["VALID-OWNER"]["active_paths"], {"src"})

        states, violations = team_metrics.replay_events(
            [
                ready("LEASE-KEEP", 0, material=False),
                worker("LEASE-KEEP", 1, True, ["src/kept"]),
                ready("NAMESPACE-PATH", 2, material=False),
                worker(
                    "NAMESPACE-PATH",
                    3,
                    True,
                    ["src/must-not-lease", r"\\?\C:\repo"],
                ),
                ready("AFTER-NAMESPACE", 4, material=False),
                worker("AFTER-NAMESPACE", 5, True, ["src/must-not-lease"]),
            ]
        )
        namespace_codes = {
            item["code"]
            for item in violations
            if item["task_id"] == "NAMESPACE-PATH"
        }
        self.assertIn("INVALID_WRITER_PATH", namespace_codes)
        self.assertNotIn("OVERLAPPING_PATH_OWNERSHIP", namespace_codes)
        self.assertNotIn(
            "OVERLAPPING_PATH_OWNERSHIP",
            {
                item["code"]
                for item in violations
                if item["task_id"] == "AFTER-NAMESPACE"
            },
        )
        self.assertEqual(states["NAMESPACE-PATH"]["active_paths"], set())
        self.assertEqual(states["LEASE-KEEP"]["active_paths"], {"src/kept"})
        self.assertEqual(
            states["AFTER-NAMESPACE"]["active_paths"],
            {"src/must-not-lease"},
        )

    def test_audit_requires_a_reason_for_writer_start_during_integration_backlog(self) -> None:
        events = [
            ready("WAITING", 0, material=False),
            dev("WAITING", "waiting-candidate", 1),
            ready("EXPLAINED", 2, material=False),
            worker(
                "EXPLAINED",
                3,
                True,
                ["src/explained"],
                integration_backlog_reason="Independent integration owner is available.",
            ),
        ]
        audit = team_metrics.build_audit(events)
        self.assertNotIn(
            "NEW_WRITER_WITH_INTEGRATION_BACKLOG",
            {item["code"] for item in audit["violations"]},
        )


if __name__ == "__main__":
    unittest.main()
