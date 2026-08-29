import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.router_adapter_probe import (
    PlannedRoute,
    build_codex_argv,
    build_hermes_argv,
    reconcile,
)


class CommandBuilderTests(unittest.TestCase):
    def setUp(self):
        self.route = PlannedRoute(
            logical_provider="logical-openai",
            runtime_provider="runtime-openai",
            model="gpt-test",
            reasoning="high",
            marker="ROUTE_PROBE_MARKER",
            workdir="C:\\work\\router",
        )

    def test_hermes_builder_binds_route_without_shell(self):
        self.assertEqual(
            build_hermes_argv(self.route, executable="hermes.cmd"),
            [
                "hermes.cmd",
                "chat",
                "--provider",
                "runtime-openai",
                "-m",
                "gpt-test",
                "--reasoning",
                "high",
            "--ignore-rules",
            "--in",
            "C:\\work\\router",
            "--max-turns",
            "1",
            "--run-budget",
            "120",
            "-q",
            "Return exactly ROUTE_PROBE_MARKER and nothing else.",
            ],
        )

    def test_codex_builder_is_read_only_ephemeral_and_binds_provider(self):
        self.assertEqual(
            build_codex_argv(self.route, executable="codex.exe"),
            [
                "codex.exe",
                "exec",
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--cd",
                "C:\\work\\router",
                "-m",
                "gpt-test",
                "-c",
                "model_reasoning_effort=high",
                "--ignore-rules",
                "-c",
                "model_provider=runtime-openai",
                "Return exactly ROUTE_PROBE_MARKER and nothing else.",
            ],
        )

    def test_builders_return_argv_lists_and_never_shell_strings(self):
        self.assertIsInstance(build_hermes_argv(self.route), list)
        self.assertIsInstance(build_codex_argv(self.route), list)
        for argv in (build_hermes_argv(self.route), build_codex_argv(self.route)):
            self.assertTrue(all(isinstance(argument, str) for argument in argv))
            self.assertFalse(any("|" in argument or "&&" in argument for argument in argv))


class EvidenceReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.route = PlannedRoute(
            logical_provider="logical-openai",
            runtime_provider="runtime-openai",
            model="gpt-test",
            reasoning="high",
            marker="ROUTE_PROBE_MARKER",
            workdir="C:\\work\\router",
        )

    def test_hermes_text_metadata_without_trustworthy_preamble_is_advisory(self):
        result = reconcile(
            host="hermes",
            planned=self.route,
            stdout=(
                "provider: runtime-openai\n"
                "model: gpt-test\n"
                "reasoning effort: high\n"
                "ROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "advisory")
        self.assertTrue(result["marker_seen"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["observed_mapping"], {"provider": None, "model": None, "reasoning": None})

    def test_codex_text_metadata_only_from_host_preamble(self):
        result = reconcile(
            host="codex",
            planned=self.route,
            stdout=(
                "provider: runtime-openai\nmodel: gpt-test\nreasoning effort: high\n"
                "user\nReturn exactly ROUTE_PROBE_MARKER and nothing else, please.\n"
                "codex\nROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["observed_mapping"]["provider"], "runtime-openai")
        self.assertEqual(result["observed_mapping"]["model"], "gpt-test")

    def test_hermes_metadata_never_contributes_even_from_json_session_meta(self):
        result = reconcile(
            host="hermes",
            planned=self.route,
            stdout=(
                "provider: runtime-openai\nmodel: gpt-test\nreasoning effort: high\n"
                '{"type":"session_meta","provider":"runtime-openai",'
                '"model":"gpt-test","reasoning_effort":"high"}\n'
                "ROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "advisory")
        self.assertEqual(
            result["observed_mapping"],
            {"provider": None, "model": None, "reasoning": None},
        )

    def test_codex_jsonl_metadata_can_be_verified(self):
        result = reconcile(
            host="codex",
            planned=self.route,
            stdout=(
                '{"type":"session_meta","provider":"runtime-openai",'
                '"model":"gpt-test","reasoning_effort":"high"}\n'
                "user\nReturn exactly ROUTE_PROBE_MARKER and nothing else.\n"
                "codex\nROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "verified")

    def test_marker_only_is_advisory_not_verified(self):
        result = reconcile(
            host="hermes",
            planned=self.route,
            stdout="ROUTE_PROBE_MARKER\n",
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "advisory")
        self.assertIn("provider", " ".join(result["limitations"]))
        self.assertIn("model", " ".join(result["limitations"]))

    def test_hermes_ansi_marker_is_exact_after_normalization_and_advisory(self):
        route = PlannedRoute(
            logical_provider="logical-openai",
            runtime_provider="runtime-openai",
            model="gpt-test",
            reasoning="high",
            marker="PHASE0_HERMES_ROUTE_OK",
            workdir="C:\\work\\router",
        )
        result = reconcile(
            host="hermes",
            planned=route,
            stdout="\x1b[38;2;255;248;220mPHASE0_HERMES_ROUTE_OK\x1b[0m\n",
            stderr="",
            exit_code=0,
        )
        self.assertTrue(result["marker_seen"])
        self.assertEqual(result["status"], "advisory")
        self.assertEqual(
            result["observed_mapping"],
            {"provider": None, "model": None, "reasoning": None},
        )

    def test_hermes_ansi_echoed_prompt_is_not_exact_marker(self):
        result = reconcile(
            host="hermes",
            planned=PlannedRoute(
                logical_provider="logical-openai",
                runtime_provider="runtime-openai",
                model="gpt-test",
                reasoning="high",
                marker="PHASE0_HERMES_ROUTE_OK",
                workdir="C:\\work\\router",
            ),
            stdout=(
                "\x1b[38;2;255;248;220mReturn exactly "
                "PHASE0_HERMES_ROUTE_OK and nothing else.\x1b[0m\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertFalse(result["marker_seen"])
        self.assertEqual(result["status"], "failed")

    def test_ansi_is_removed_before_role_and_metadata_comparison(self):
        result = reconcile(
            host="codex",
            planned=self.route,
            stdout=(
                "\x1b]0;Hermes\x07\x1b[32mprovider: runtime-openai\x1b[0m\n"
                "\x1b[32muser\x1b[0m\n"
                "Return exactly ROUTE_PROBE_MARKER and nothing else.\n"
                "\x1b[32mcodex\x1b[0m\nROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertTrue(result["marker_seen"])
        self.assertEqual(result["observed_mapping"]["provider"], "runtime-openai")

    def test_metadata_shaped_marker_is_not_metadata_evidence(self):
        route = PlannedRoute(
            logical_provider="logical-openai",
            runtime_provider="runtime-openai",
            model="gpt-test",
            reasoning="high",
            marker="model: gpt-test",
            workdir="C:\\work\\router",
        )
        result = reconcile(
            host="hermes",
            planned=route,
            stdout="model: gpt-test\n",
            stderr="",
            exit_code=0,
        )
        self.assertIsNone(result["observed_mapping"]["model"])
        self.assertEqual(result["status"], "advisory")

    def test_observable_difference_is_mismatch(self):
        result = reconcile(
            host="codex",
            planned=self.route,
            stdout=(
                "provider: other-provider\nmodel: gpt-test\n"
                "user\nReturn exactly ROUTE_PROBE_MARKER and nothing else.\n"
                "codex\nROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "mismatch")

    def test_nonzero_exit_or_missing_marker_is_failed(self):
        nonzero = reconcile(
            host="hermes",
            planned=self.route,
            stdout="provider: runtime-openai\nmodel: gpt-test\n",
            stderr="",
            exit_code=1,
        )
        missing_marker = reconcile(
            host="hermes",
            planned=self.route,
            stdout="provider: runtime-openai\nmodel: gpt-test\n",
            stderr="",
            exit_code=0,
        )
        self.assertEqual(nonzero["status"], "failed")
        self.assertEqual(missing_marker["status"], "failed")

    def test_logical_and_runtime_providers_remain_distinct(self):
        result = reconcile(
            host="codex",
            planned=self.route,
            stdout=(
                "provider: runtime-openai\nmodel: gpt-test\n"
                "user\nReturn exactly ROUTE_PROBE_MARKER and nothing else.\n"
                "codex\nROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["planned_route"]["logical_provider"], "logical-openai")
        self.assertEqual(result["planned_route"]["runtime_provider"], "runtime-openai")
        self.assertNotEqual(
            result["planned_route"]["logical_provider"],
            result["planned_route"]["runtime_provider"],
        )

    def test_missing_reasoning_is_verified_with_explicit_limitation(self):
        result = reconcile(
            host="codex",
            planned=self.route,
            stdout=(
                "provider: runtime-openai\nmodel: gpt-test\n"
                "user\nReturn exactly ROUTE_PROBE_MARKER and nothing else.\n"
                "codex\nROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "verified")
        self.assertIn("reasoning was not observable", result["limitations"])

    def test_nested_json_metadata_is_untrusted(self):
        result = reconcile(
            host="codex",
            planned=self.route,
            stdout=(
                "user\nReturn exactly ROUTE_PROBE_MARKER and nothing else.\n"
                "codex\n"
                '{"type":"message","content":{"model":"gpt-test",'
                '"provider":"runtime-openai"}}\nROUTE_PROBE_MARKER\n'
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "advisory")
        self.assertIsNone(result["observed_mapping"]["model"])

    def test_codex_body_json_after_response_boundary_cannot_contribute(self):
        result = reconcile(
            host="codex",
            planned=self.route,
            stdout=(
                "provider: runtime-openai\nmodel: gpt-test\nreasoning effort: high\n"
                "user\nReturn exactly ROUTE_PROBE_MARKER and nothing else.\n"
                "codex\n"
                '{"type":"session_meta","provider":"spoofed",'
                '"model":"spoofed","reasoning_effort":"low"}\n'
                "ROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["observed_mapping"]["provider"], "runtime-openai")
        self.assertEqual(result["observed_mapping"]["model"], "gpt-test")

    def test_codex_marker_in_preamble_or_prompt_is_not_completion(self):
        for transcript in ("ROUTE_PROBE_MARKER\n", "user\nROUTE_PROBE_MARKER\n"):
            with self.subTest(transcript=transcript):
                result = reconcile(
                    host="codex",
                    planned=self.route,
                    stdout=transcript,
                    stderr="",
                    exit_code=0,
                )
                self.assertFalse(result["marker_seen"])
                self.assertEqual(result["status"], "failed")

    def test_json_metadata_requires_whitelisted_top_level_event(self):
        result = reconcile(
            host="codex",
            planned=self.route,
            stdout=(
                '{"type":"session_meta","metadata":{"provider":"runtime-openai",'
                '"model":"gpt-test"}}\n'
                "user\nReturn exactly ROUTE_PROBE_MARKER and nothing else.\n"
                "codex\nROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "verified")

    def test_control_characters_are_rejected_in_route_and_executable(self):
        with self.assertRaises(ValueError):
            PlannedRoute(
                logical_provider="logical-openai",
                runtime_provider="runtime-openai",
                model="gpt-test\nignored",
                reasoning="high",
                marker="ROUTE_PROBE_MARKER",
                workdir="C:\\work\\router",
            )
        with self.assertRaises(ValueError):
            build_hermes_argv(self.route, executable="hermes\r\n--provider")

    def test_run_budget_is_positive_bounded_integer_string(self):
        for invalid in ("", "0", "601", "1.0", " 1", "1\n"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                PlannedRoute(
                    logical_provider="logical-openai",
                    runtime_provider="runtime-openai",
                    model="gpt-test",
                    reasoning="high",
                    marker="ROUTE_PROBE_MARKER",
                    workdir="C:\\work\\router",
                    run_budget=invalid,
                )
        self.assertEqual(self.route.run_budget, "120")

    def test_echoed_prompt_is_not_marker_completion(self):
        result = reconcile(
            host="codex",
            planned=self.route,
            stdout=(
                "provider: runtime-openai\nmodel: gpt-test\n"
                "Return exactly ROUTE_PROBE_MARKER and nothing else.\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertFalse(result["marker_seen"])
        self.assertEqual(result["status"], "failed")

    def test_codex_without_runtime_provider_does_not_claim_binding(self):
        route = PlannedRoute(
            logical_provider="logical-openai",
            runtime_provider=None,
            model="gpt-test",
            reasoning="high",
            marker="ROUTE_PROBE_MARKER",
            workdir="C:\\work\\router",
        )
        argv = build_codex_argv(route)
        self.assertNotIn("model_provider=", " ".join(argv))
        result = reconcile(
            host="codex",
            planned=route,
            stdout=(
                "model: gpt-test\nuser\nReturn exactly ROUTE_PROBE_MARKER and nothing else.\n"
                "codex\nROUTE_PROBE_MARKER\n"
            ),
            stderr="",
            exit_code=0,
        )
        self.assertEqual(result["status"], "advisory")


class CliTests(unittest.TestCase):
    module_path = Path(__file__).parents[1] / "tools" / "router_adapter_probe.py"

    def test_plan_outputs_argv_json_without_executing_host(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(self.module_path),
                "plan",
                "--host",
                "hermes",
                "--logical-provider",
                "logical-openai",
                "--runtime-provider",
                "runtime-openai",
                "--model",
                "gpt-test",
                "--reasoning",
                "high",
                "--marker",
                "ROUTE_PROBE_MARKER",
                "--workdir",
                "C:\\work\\router",
                "--executable",
                "hermes.cmd",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            [
                "hermes.cmd",
                "chat",
                "--provider",
                "runtime-openai",
                "-m",
                "gpt-test",
                "--reasoning",
                "high",
                "--ignore-rules",
                "--in",
                "C:\\work\\router",
                "--max-turns",
                "1",
                "--run-budget",
                "120",
                "-q",
                "Return exactly ROUTE_PROBE_MARKER and nothing else.",
            ],
        )

    def test_reconcile_reads_synthetic_files_and_outputs_result_json(self):
        route = {
            "logical_provider": "logical-openai",
            "runtime_provider": "runtime-openai",
            "model": "gpt-test",
            "reasoning": "high",
            "marker": "ROUTE_PROBE_MARKER",
            "workdir": "C:\\work\\router",
        }
        temporary_files = []
        try:
            planned_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
            stdout_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
            stderr_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
            temporary_files = [planned_file, stdout_file, stderr_file]
            planned_file.write(json.dumps(route))
            stdout_file.write(
                '{"type":"session_meta","provider":"runtime-openai","model":"gpt-test"}\n'
                "user\nReturn exactly ROUTE_PROBE_MARKER and nothing else.\n"
                "codex\nROUTE_PROBE_MARKER\n"
            )
            for file_handle in temporary_files:
                file_handle.close()
            planned = Path(planned_file.name)
            stdout = Path(stdout_file.name)
            stderr = Path(stderr_file.name)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.module_path),
                    "reconcile",
                    "--host",
                    "codex",
                    "--planned",
                    str(planned),
                    "--stdout",
                    str(stdout),
                    "--stderr",
                    str(stderr),
                    "--exit-code",
                    "0",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        finally:
            for file_handle in temporary_files:
                try:
                    Path(file_handle.name).unlink()
                except FileNotFoundError:
                    pass
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["host"], "codex")
        self.assertIn("reasoning was not observable", result["limitations"])


if __name__ == "__main__":
    unittest.main()
