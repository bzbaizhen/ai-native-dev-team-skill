import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "migrate_suite_install.py"
MANIFEST_PATH = ROOT / "suite-manifest.json"
MODEL_ROUTER = ROOT / "skills" / "ai-native-model-router"
MODEL_ROUTER_PROFILE_IDS = {
    "gpt5.6",
}
MODEL_ROUTER_INVENTORY = [
    "SKILL.md",
    "agents/openai.yaml",
    "assets/model-router-config.example.json",
    "assets/model-router-config.v1.schema.json",
    "assets/model-router-config.v2.schema.json",
    "assets/profiles/gpt5.6.json",
    "assets/provider-catalog.json",
    "assets/route-decision.v1.schema.json",
    "assets/route-decision.v2.schema.json",
    "assets/route-request.v1.schema.json",
    "assets/route-request.v2.schema.json",
    "references/configuration.md",
    "references/interface.md",
    "references/provider-evidence.md",
    "scripts/resolve_route.py",
    "scripts/router_config.py",
]
MODEL_ROUTER_SCHEMAS = {
    "assets/model-router-config.v1.schema.json",
    "assets/model-router-config.v2.schema.json",
    "assets/route-request.v1.schema.json",
    "assets/route-request.v2.schema.json",
    "assets/route-decision.v1.schema.json",
    "assets/route-decision.v2.schema.json",
}
ROUTE_FAILURE_EVIDENCE = (
    "model-not-found",
    "authenticated-provider-outage",
    "quota-exhaustion",
    "repeated-bounded-transport-failure",
)


def load_tool():
    spec = importlib.util.spec_from_file_location("migrate_suite_install", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SuitePackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = ROOT / ".tmp-suite-packaging" / uuid.uuid4().hex
        self.temp.mkdir(parents=True)
        self.work = self.temp
        self.source = self.work / "source"
        self.source_skills = self.source / "skills"
        self.install_a = self.work / "install-a"
        self.install_b = self.work / "install-b"
        self.backup = self.work / "backups"
        self.receipt = self.work / "applied.json"
        self.rollback_receipt = self.work / "rollback.json"
        self.source_skills.mkdir(parents=True)
        self.install_a.mkdir()
        self.install_b.mkdir()
        self.backup.mkdir()
        self._write_source()

    def tearDown(self):
        shutil.rmtree(self.temp)
        try:
            self.temp.parent.rmdir()
        except OSError:
            pass

    def _write_source(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        for component in manifest["components"]:
            for relative in component["files"]:
                path = self.source_skills / component["id"] / relative
                content = f"fixture:{component['id']}:{relative}\n"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

    def _args(self, command, *extra):
        args = [
            sys.executable,
            str(TOOL_PATH),
            command,
            "--source-root",
            str(self.source),
            "--install-root",
            str(self.install_a),
            "--install-root",
            str(self.install_b),
            "--backup-root",
            str(self.backup),
        ]
        if command in {"apply", "verify", "rollback"}:
            args.extend(["--receipt", str(self.receipt)])
        if command == "rollback":
            args.extend(["--rollback-receipt", str(self.rollback_receipt)])
        args.extend(extra)
        if command == "rollback":
            source_index = args.index("--source-root")
            del args[source_index:source_index + 2]
            backup_index = args.index("--backup-root")
            del args[backup_index:backup_index + 2]
        return args

    def _run(self, command, *extra, check=False):
        result = subprocess.run(
            self._args(command, *extra),
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if check and result.returncode:
            self.fail(f"{result.stderr}\nstdout={result.stdout}")
        return result

    def _plan(self):
        result = self._run("plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_manifest_is_exact_suite_contract(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["suite"],
            {"id": "ai-native-dev-team-suite", "name": "AI Native Dev Team Suite"},
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            manifest["components"],
            [
                {
                    "id": "ai-native-dev-team",
                    "version": "3.0.1",
                    "role": "governance-entry",
                    "files": [
                        "SKILL.md",
                        "agents/openai.yaml",
                        "assets/project-team-charter.md",
                        "assets/task-contract.md",
                        "assets/team-bootstrap-proposal.md",
                        "references/controlled.md",
                        "references/core.md",
                        "references/delivery-quality-review.md",
                        "references/git-isolation-bootstrap.md",
                        "references/governance-controlled.md",
                        "references/governance-lean.md",
                        "references/governance-strict.md",
                        "references/metrics-event.schema.json",
                        "references/metrics.md",
                        "references/routing-and-topologies.md",
                        "references/team-governance-template.zh-CN.md",
                        "scripts/git_isolation_bootstrap.py",
                        "scripts/team_metrics.py",
                    ],
                },
                {
                    "id": "ai-native-model-router",
                    "version": "0.4.0",
                    "role": "routing-extension",
                    "files": [
                        "SKILL.md",
                        "agents/openai.yaml",
                        "assets/model-router-config.example.json",
                        "assets/model-router-config.v1.schema.json",
                        "assets/model-router-config.v2.schema.json",
                        "assets/profiles/gpt5.6.json",
                        "assets/provider-catalog.json",
                        "assets/route-decision.v1.schema.json",
                        "assets/route-decision.v2.schema.json",
                        "assets/route-request.v1.schema.json",
                        "assets/route-request.v2.schema.json",
                        "references/configuration.md",
                        "references/interface.md",
                        "references/provider-evidence.md",
                        "scripts/resolve_route.py",
                        "scripts/router_config.py",
                    ],
                },
            ],
        )
        self.assertEqual(manifest["route_interface"], {"name": "route/v1", "compatible": True})
        self.assertTrue(manifest["router"]["optional"])
        self.assertEqual(
            manifest["legacy"],
            {
                "id": "bootstrap-ai-native-dev-team",
                "migration_only": True,
                "discoverable": False,
            },
        )
        self.assertEqual(
            manifest["install_inventory"],
            {"policy": "tracked-source-files-only", "exclude": ["__pycache__", "*.pyc", "secrets"]},
        )
        self.assertIn("compatibility_matrix", manifest)
        self.assertEqual(manifest["compatibility_matrix"]["route/v1"], ["ai-native-dev-team", "ai-native-model-router"])
        self.assertEqual(manifest["compatibility_matrix"]["route/v2"], ["ai-native-model-router"])
        self.assertNotIn("route/v2", manifest["compatibility_matrix"]["components"]["ai-native-dev-team"])
        self.assertTrue(manifest["compatibility_matrix"]["components"]["ai-native-model-router"]["route/v2"])

    def test_model_router_version_and_inventory_are_exact_and_sorted(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        component = next(item for item in manifest["components"] if item["id"] == "ai-native-model-router")
        self.assertEqual(component["version"], "0.4.0")
        skill = (MODEL_ROUTER / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(re.search(r"^version:\s*(.+)$", skill, re.MULTILINE).group(1), "0.4.0")
        self.assertEqual(component["files"], MODEL_ROUTER_INVENTORY)
        self.assertEqual(component["files"], sorted(component["files"]))
        self.assertEqual(
            set(component["files"]) - {
                "SKILL.md",
                "agents/openai.yaml",
                "assets/model-router-config.example.json",
                "assets/model-router-config.v1.schema.json",
                "assets/provider-catalog.json",
                "assets/route-decision.v1.schema.json",
                "assets/route-request.v1.schema.json",
                "references/configuration.md",
                "references/interface.md",
                "references/provider-evidence.md",
                "scripts/resolve_route.py",
                "scripts/router_config.py",
            },
            {
                "assets/model-router-config.v2.schema.json",
                "assets/profiles/gpt5.6.json",
                "assets/route-decision.v2.schema.json",
                "assets/route-request.v2.schema.json",
            },
        )

    def test_model_router_progressive_disclosure_links_both_profiles_and_all_schemas(self):
        skill = (MODEL_ROUTER / "SKILL.md").read_text(encoding="utf-8")
        links = set(re.findall(r"\[[^\]]+\]\(([^)#]+)", skill))
        expected = {
            "references/interface.md",
            "references/configuration.md",
            "references/provider-evidence.md",
            "assets/provider-catalog.json",
            *{f"assets/profiles/{profile_id}.json" for profile_id in MODEL_ROUTER_PROFILE_IDS},
            *MODEL_ROUTER_SCHEMAS,
            "scripts/router_config.py",
            "scripts/resolve_route.py",
        }
        self.assertEqual(links, expected)
        for target in expected:
            self.assertTrue((MODEL_ROUTER / target).is_file(), target)

    def test_model_router_docs_define_v1_v2_assurance_and_safety_boundaries(self):
        docs = "\n".join(
            (MODEL_ROUTER / relative).read_text(encoding="utf-8")
            for relative in (
                "SKILL.md",
                "references/interface.md",
                "references/configuration.md",
                "references/provider-evidence.md",
            )
        )
        normalized_docs = " ".join(docs.casefold().split())
        for phrase in (
            "route/v1",
            "route/v2",
            "validator.independent",
            "validator.assurance",
            "independent validation",
            "same-model review is allowed",
            "same_model_as_writer",
            "not independent validation",
            "gpt-5.6-luna:max -> gpt-5.6-terra:max -> gpt-5.6-sol:high",
            "gpt-5.6-terra:max -> gpt-5.6-sol:high",
            "gpt-5.6-terra:max + gpt-5.6-sol:high",
            "never degrade to one Validator",
            "route-bound evidence",
            "unknown remains unknown",
            "missing or unaccepted route-bound evidence for any unavailable required route => `decision_status: blocked`, even when the other required route is `unknown`",
            "otherwise, any required route with `unknown` availability => `decision_status: unknown`",
            "otherwise, accepted unavailability => `decision_status: blocked`",
            "r3 never selects or degrades to one route",
            "create a new candidate id before revalidation",
            "substantive Validator rejection does not trigger escalation",
            "every request explicitly selects a profile",
            "file presence never activates a profile",
            "enforcement_status: not-executed",
            "not an execution receipt",
            "provider execution, authentication, and transport remain outside this package",
        ):
            self.assertIn(phrase.casefold(), normalized_docs)
        for evidence in ROUTE_FAILURE_EVIDENCE:
            self.assertIn(f"`{evidence}`", normalized_docs)
        structured = "\n".join(
            (MODEL_ROUTER / relative).read_text(encoding="utf-8")
            for relative in MODEL_ROUTER_SCHEMAS
            | {"assets/profiles/gpt5.6.json"}
        )
        self.assertEqual(
            set(re.findall(r"https?://[^\"\s]+", structured, re.IGNORECASE)),
            {"https://json-schema.org/draft/2020-12/schema"},
        )
        self.assertIsNone(re.search(r"-----BEGIN|sk-[A-Za-z0-9]|Bearer\s+", structured, re.IGNORECASE))
        self.assertIsNone(re.search(r"\b(?:endpoint|credential|secret|token|price|command)\s*[:=]", structured, re.IGNORECASE))

    def test_plan_is_read_only_and_has_exact_inventories(self):
        before = self._snapshot(self.work)
        plan = self._plan()
        self.assertEqual(before, self._snapshot(self.work))
        self.assertEqual(plan["state"], "plan")
        self.assertEqual(plan["blockers"], [])
        self.assertEqual(plan["source"]["components"][0]["id"], "ai-native-dev-team")
        self.assertEqual(plan["source"]["components"][1]["id"], "ai-native-model-router")
        self.assertEqual(len(plan["roots"]), 2)
        self.assertTrue(plan["plan_digest"])
        self.assertEqual(plan["plan_digest"], self._digest_without(plan, "plan_digest"))

    def test_apply_verify_two_roots_and_receipt(self):
        plan = self._plan()
        result = self._run("apply", "--plan-digest", plan["plan_digest"], "--confirm-breaking-rename")
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(receipt["schema_version"], 1)
        self.assertEqual(receipt["state"], "applied")
        self.assertIn("before", receipt)
        self.assertIn("after", receipt)
        self.assertIn("backup_paths", receipt)
        self.assertIn("operations", receipt)
        self.assertEqual(receipt["receipt_hash"], self._digest_without(receipt, "receipt_hash"))
        for install in (self.install_a, self.install_b):
            self.assertTrue((install / "ai-native-dev-team/SKILL.md").is_file())
            self.assertTrue((install / "ai-native-model-router/SKILL.md").is_file())
            self.assertFalse((install / ("bootstrap" + "-ai-native-dev-team")).exists())
        verify = self._run("verify")
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertEqual(json.loads(verify.stdout)["receipt_hash"], receipt["receipt_hash"])

    def test_rollback_restores_old_and_new_bytes_exactly(self):
        old = self.install_a / "bootstrap-ai-native-dev-team/SKILL.md"
        old.parent.mkdir()
        old.write_bytes(b"old-byte-exact\x00")
        existing = self.install_a / "ai-native-dev-team/SKILL.md"
        existing.parent.mkdir()
        existing.write_bytes(b"new-collision-byte-exact\x01")
        plan = self._plan()
        self.assertEqual(
            self._run("apply", "--plan-digest", plan["plan_digest"], "--confirm-breaking-rename").returncode,
            0,
        )
        result = self._run(
            "rollback",
            "--receipt-hash",
            json.loads(self.receipt.read_text(encoding="utf-8"))["receipt_hash"],
            "--confirm-rollback",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(old.read_bytes(), b"old-byte-exact\x00")
        self.assertEqual(existing.read_bytes(), b"new-collision-byte-exact\x01")
        self.assertFalse((self.install_a / "ai-native-model-router").exists())
        self.assertFalse((self.install_b / "ai-native-dev-team").exists())
        self.assertEqual(json.loads(self.receipt.read_text(encoding="utf-8"))["state"], "applied")
        self.assertEqual(json.loads(self.rollback_receipt.read_text(encoding="utf-8"))["state"], "rolled_back")

    def test_second_root_failure_rolls_back_first_root(self):
        module = load_tool()
        plan = module.build_plan(self.source, [self.install_a, self.install_b], self.backup)
        original = module._apply_one_root
        calls = []

        def fail_second(*args, **kwargs):
            calls.append(args[1])
            if len(calls) == 2:
                raise module.MigrationError("injected second-root failure")
            return original(*args, **kwargs)

        with mock.patch.object(module, "_apply_one_root", side_effect=fail_second):
            with self.assertRaises(module.MigrationError):
                module.apply_plan(
                    plan,
                    self.backup,
                    self.receipt,
                    confirm_breaking_rename=True,
                    plan_digest=plan["plan_digest"],
                )
        self.assertFalse((self.install_a / "ai-native-dev-team").exists())
        self.assertFalse((self.install_a / "ai-native-model-router").exists())
        self.assertFalse(self.receipt.exists())

    def test_apply_rejects_stale_plan_and_existing_receipt(self):
        plan = self._plan()
        (self.source_skills / "ai-native-dev-team/SKILL.md").write_text("drift\n", encoding="utf-8")
        stale = self._run("apply", "--plan-digest", plan["plan_digest"], "--confirm-breaking-rename")
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("stale", stale.stderr.lower())
        self._write_source()
        plan = self._plan()
        self.receipt.write_text("already", encoding="utf-8")
        existing = self._run("apply", "--plan-digest", plan["plan_digest"], "--confirm-breaking-rename")
        self.assertNotEqual(existing.returncode, 0)
        self.assertIn("receipt", existing.stderr.lower())

    def test_verify_rejects_extra_and_missing_files(self):
        plan = self._plan()
        self.assertEqual(
            self._run("apply", "--plan-digest", plan["plan_digest"], "--confirm-breaking-rename").returncode,
            0,
        )
        extra = self.install_a / "ai-native-dev-team/extra.txt"
        extra.write_text("extra", encoding="utf-8")
        result = self._run("verify")
        self.assertNotEqual(result.returncode, 0)
        extra.unlink()
        (self.install_a / "ai-native-dev-team/SKILL.md").unlink()
        result = self._run("verify")
        self.assertNotEqual(result.returncode, 0)

    def test_source_inventory_must_match_manifest_files_exactly(self):
        extra = self.source_skills / "ai-native-dev-team" / "arbitrary.txt"
        extra.write_text("extra", encoding="utf-8")
        result = self._run("plan")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manifest", result.stdout.lower())
        extra.unlink()
        missing = self.source_skills / "ai-native-model-router" / "SKILL.md"
        missing.unlink()
        result = self._run("plan")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manifest", result.stdout.lower())

    def test_apply_preflight_has_no_mutation_on_receipt_parent_or_plan_failure(self):
        module = load_tool()
        plan = module.build_plan(self.source, [self.install_a, self.install_b], self.backup)
        missing_parent_receipt = self.work / "missing" / "applied.json"
        with mock.patch.object(module, "_apply_one_root") as apply_one:
            with self.assertRaises(module.MigrationError):
                module.apply_plan(
                    plan,
                    self.backup,
                    missing_parent_receipt,
                    confirm_breaking_rename=True,
                    plan_digest=plan["plan_digest"],
                )
        apply_one.assert_not_called()
        self.assertFalse(any(self.install_a.iterdir()))
        self.assertFalse(any(self.install_b.iterdir()))
        invalid = dict(plan)
        invalid["plan_digest"] = "0" * 64
        with mock.patch.object(module, "_apply_one_root") as apply_one:
            with self.assertRaises(module.MigrationError):
                module.apply_plan(
                    invalid,
                    self.backup,
                    self.receipt,
                    confirm_breaking_rename=True,
                    plan_digest=invalid["plan_digest"],
                )
        apply_one.assert_not_called()

    def test_receipt_write_failure_rolls_back_all_roots_and_removes_backup_task(self):
        module = load_tool()
        plan = module.build_plan(self.source, [self.install_a, self.install_b], self.backup)
        with mock.patch.object(module, "_atomic_write_json", side_effect=module.MigrationError("receipt write failed")):
            with self.assertRaisesRegex(module.MigrationError, "receipt write failed"):
                module.apply_plan(
                    plan,
                    self.backup,
                    self.receipt,
                    confirm_breaking_rename=True,
                    plan_digest=plan["plan_digest"],
                )
        for install in (self.install_a, self.install_b):
            self.assertFalse((install / "ai-native-dev-team").exists())
            self.assertFalse((install / "ai-native-model-router").exists())
            self.assertFalse((install / ("bootstrap" + "-ai-native-dev-team")).exists())
        self.assertFalse(self.receipt.exists())
        self.assertEqual(list(self.backup.iterdir()), [])

    def test_after_state_capture_failure_rolls_back_all_roots(self):
        module = load_tool()
        plan = module.build_plan(self.source, [self.install_a, self.install_b], self.backup)
        with mock.patch.object(
            module, "_current_states", side_effect=module.MigrationError("after-state capture failed")
        ):
            with self.assertRaisesRegex(module.MigrationError, "after-state capture failed"):
                module.apply_plan(
                    plan,
                    self.backup,
                    self.receipt,
                    confirm_breaking_rename=True,
                    plan_digest=plan["plan_digest"],
                )
        for install in (self.install_a, self.install_b):
            self.assertFalse((install / "ai-native-dev-team").exists())
            self.assertFalse((install / "ai-native-model-router").exists())
            self.assertFalse((install / "bootstrap-ai-native-dev-team").exists())
        self.assertFalse(self.receipt.exists())
        self.assertEqual(list(self.backup.iterdir()), [])

    def test_manual_rollback_second_root_restore_failure_recovers_all_roots_to_applied(self):
        module = load_tool()
        plan = self._plan()
        applied = module.apply_plan(
            plan,
            self.backup,
            self.receipt,
            confirm_breaking_rename=True,
            plan_digest=plan["plan_digest"],
        )
        applied_bytes = self.receipt.read_bytes()
        original_restore = module._restore_root
        calls = 0

        def fail_second_restore(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise module.MigrationError("injected second-root restore failure")
            return original_restore(*args, **kwargs)

        with mock.patch.object(module, "_restore_root", side_effect=fail_second_restore):
            with self.assertRaisesRegex(module.MigrationError, "second-root restore failure"):
                module.rollback_receipt(
                    self.receipt,
                    self.rollback_receipt,
                    [self.install_a, self.install_b],
                    receipt_hash=applied["receipt_hash"],
                    confirm_rollback=True,
                )
        self.assertEqual(self.receipt.read_bytes(), applied_bytes)
        self.assertFalse(self.rollback_receipt.exists())
        self.assertTrue((self.install_a / "ai-native-dev-team/SKILL.md").is_file())
        self.assertTrue((self.install_b / "ai-native-dev-team/SKILL.md").is_file())
        self.assertEqual([item.name for item in self.backup.iterdir()], [Path(applied["backup_task"]).name])

    def test_manual_rollback_receipt_failure_recovers_all_roots_to_applied(self):
        module = load_tool()
        plan = self._plan()
        applied = module.apply_plan(
            plan,
            self.backup,
            self.receipt,
            confirm_breaking_rename=True,
            plan_digest=plan["plan_digest"],
        )
        applied_bytes = self.receipt.read_bytes()
        with mock.patch.object(
            module, "_atomic_write_json", side_effect=module.MigrationError("rollback receipt write failed")
        ):
            with self.assertRaisesRegex(module.MigrationError, "rollback receipt write failed"):
                module.rollback_receipt(
                    self.receipt,
                    self.rollback_receipt,
                    [self.install_a, self.install_b],
                    receipt_hash=applied["receipt_hash"],
                    confirm_rollback=True,
                )
        self.assertEqual(self.receipt.read_bytes(), applied_bytes)
        self.assertFalse(self.rollback_receipt.exists())
        for install in (self.install_a, self.install_b):
            self.assertTrue((install / "ai-native-dev-team/SKILL.md").is_file())
            self.assertTrue((install / "ai-native-model-router/SKILL.md").is_file())
        self.assertEqual([item.name for item in self.backup.iterdir()], [Path(applied["backup_task"]).name])

    def test_plan_cli_rejects_duplicate_normalized_install_roots(self):
        result = self._run("plan", "--install-root", str(self.install_a / "."))
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(any("duplicate" in blocker.lower() for blocker in payload["blockers"]))

    def test_manual_rollback_validates_all_backups_before_first_write(self):
        old_second = self.install_b / "ai-native-dev-team/SKILL.md"
        old_second.parent.mkdir(parents=True)
        old_second.write_bytes(b"second-root-before\x00")
        plan = self._plan()
        self.assertEqual(
            self._run("apply", "--plan-digest", plan["plan_digest"], "--confirm-breaking-rename").returncode,
            0,
        )
        applied = json.loads(self.receipt.read_text(encoding="utf-8"))
        second_backup = next(
            item["targets"]["ai-native-dev-team"]
            for item in applied["backup_paths"]
            if item["install_root"] == str(self.install_b)
        )
        self.assertIsNotNone(second_backup)
        shutil.rmtree(second_backup)
        result = self._run(
            "rollback",
            "--receipt-hash", applied["receipt_hash"],
            "--confirm-rollback",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.install_a / "ai-native-dev-team/SKILL.md").is_file())
        self.assertTrue((self.install_b / "ai-native-dev-team/SKILL.md").is_file())
        self.assertFalse(self.rollback_receipt.exists())

    def test_verify_rejects_tampered_receipt_and_parser_has_only_command_args(self):
        plan = self._plan()
        self.assertEqual(
            self._run("apply", "--plan-digest", plan["plan_digest"], "--confirm-breaking-rename").returncode,
            0,
        )
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        receipt["suite_id"] = "tampered"
        self.receipt.write_text(json.dumps(receipt), encoding="utf-8")
        result = self._run("verify")
        self.assertNotEqual(result.returncode, 0)
        module = load_tool()
        parser = module._parser()
        self.assertNotIn("receipt", {action.dest for action in parser._subparsers._group_actions[0].choices["plan"]._actions})
        self.assertNotIn("source_root", {action.dest for action in parser._subparsers._group_actions[0].choices["rollback"]._actions})
        self.assertNotIn("backup_root", {action.dest for action in parser._subparsers._group_actions[0].choices["rollback"]._actions})

    def test_path_safety_rejects_symlink_ancestor(self):
        real_parent = self.work / "real-parent"
        real_parent.mkdir()
        alias = self.work / "alias"
        try:
            alias.symlink_to(real_parent, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest("directory symlinks unavailable")
        aliased_source = alias / "source"
        shutil.copytree(self.source, aliased_source)
        result = subprocess.run(
            [sys.executable, str(TOOL_PATH), "plan", "--source-root", str(aliased_source),
             "--install-root", str(self.install_a), "--install-root", str(self.install_b),
             "--backup-root", str(self.backup)],
            cwd=ROOT, text=True, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stdout.lower())

    def test_plan_rejects_existing_component_symlink_without_mutation(self):
        sentinel = self.work / "component-sentinel"
        sentinel.mkdir()
        sentinel_file = sentinel / "sentinel.txt"
        sentinel_file.write_bytes(b"must remain unchanged")
        component = self.install_a / "ai-native-dev-team"
        try:
            component.symlink_to(sentinel, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest("directory symlinks unavailable")

        try:
            result = self._run("plan")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", result.stdout.lower())
            self.assertEqual(sentinel_file.read_bytes(), b"must remain unchanged")
            self.assertEqual(list(self.install_b.iterdir()), [])
            self.assertEqual(list(self.backup.iterdir()), [])
            self.assertFalse(self.receipt.exists())
        finally:
            component.unlink(missing_ok=True)

    def test_plan_rejects_existing_component_junction_without_mutation(self):
        if os.name != "nt":
            self.skipTest("Windows junctions are unavailable")
        sentinel = self.work / "junction-sentinel"
        sentinel.mkdir()
        sentinel_file = sentinel / "sentinel.txt"
        sentinel_file.write_bytes(b"junction target remains unchanged")
        component = self.install_a / "ai-native-dev-team"
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(component), str(sentinel)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if created.returncode:
            self.skipTest("junction creation is unavailable")

        try:
            result = subprocess.run(
                self._args("plan"),
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stdout.lower()
            self.assertRegex(output, b"reparse|junction")
            self.assertEqual(sentinel_file.read_bytes(), b"junction target remains unchanged")
            self.assertEqual(list(self.install_b.iterdir()), [])
            self.assertEqual(list(self.backup.iterdir()), [])
            self.assertFalse(self.receipt.exists())
        finally:
            component.unlink(missing_ok=True)

    def test_path_safety_rejects_junction_ancestor_when_supported(self):
        if os.name != "nt":
            self.skipTest("Windows junctions are unavailable")
        real_parent = self.work / "junction-target"
        real_parent.mkdir()
        junction = self.work / "junction"
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(real_parent)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if created.returncode:
            self.skipTest("junction creation is unavailable")
        aliased_source = junction / "source"
        shutil.copytree(self.source, aliased_source)
        result = subprocess.run(
            [sys.executable, str(TOOL_PATH), "plan", "--source-root", str(aliased_source),
             "--install-root", str(self.install_a), "--install-root", str(self.install_b),
             "--backup-root", str(self.backup)],
            cwd=ROOT, text=True, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stdout.lower(), "reparse|junction")

    def test_readmes_have_one_migration_release_boundary(self):
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        self.assertEqual(english.count("## Migrate from the legacy name"), 1)
        self.assertNotIn("## V2 migration boundary", english)
        self.assertEqual(chinese.count("## 从旧名称迁移"), 1)
        self.assertNotIn("## V2 迁移边界", chinese)

    def test_plan_refuses_pycaches_secrets_symlinks_and_nested_roots(self):
        pycache = self.source_skills / "ai-native-dev-team/__pycache__"
        pycache.mkdir()
        (pycache / "x.pyc").write_bytes(b"not-source")
        result = self._run("plan")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pycache", result.stdout.lower())
        shutil.rmtree(pycache)
        secret = self.source_skills / "ai-native-dev-team/token.secret"
        secret.write_text("not a real secret", encoding="utf-8")
        result = self._run("plan")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("secret", result.stdout.lower())
        secret.unlink()
        try:
            (self.source_skills / "ai-native-dev-team/link").symlink_to(
                self.source_skills / "ai-native-dev-team/SKILL.md"
            )
        except (NotImplementedError, OSError):
            pass
        else:
            result = self._run("plan")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", result.stdout.lower())
            (self.source_skills / "ai-native-dev-team/link").unlink()
        result = subprocess.run(
            self._args("plan").copy(),
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0)
        nested = self.work / "nested"
        nested.mkdir()
        nested_args = self._args("plan")
        nested_args[nested_args.index("--install-root") + 1] = str(nested)
        nested_args.insert(nested_args.index("--install-root") + 2, "--install-root")
        nested_args.insert(nested_args.index("--install-root") + 3, str(nested / "child"))
        result = subprocess.run(nested_args, cwd=ROOT, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nested", result.stdout.lower())

    def test_apply_requires_confirmation_and_backup_root_existing(self):
        plan = self._plan()
        result = self._run("apply", "--plan-digest", plan["plan_digest"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("confirm", result.stderr.lower())
        shutil.rmtree(self.backup)
        result = self._run("apply", "--plan-digest", plan["plan_digest"], "--confirm-breaking-rename")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backup", result.stderr.lower())

    @staticmethod
    def _snapshot(root):
        return sorted(
            (
                str(path.relative_to(root)),
                path.read_bytes() if path.is_file() else None,
            )
            for path in root.rglob("*")
            if path.is_file()
        )

    @staticmethod
    def _digest_without(value, key):
        payload = dict(value)
        payload.pop(key, None)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    unittest.main()
