import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "ai-native-model-router"
ASSET_DIR = SKILL_DIR / "assets"
PROFILE_ID = "openai-glm5.3-deepseek-fallback-2026-08-28"
EVIDENCE = [
    "model-not-found",
    "authenticated-provider-outage",
    "quota-exhaustion",
    "repeated-bounded-transport-failure",
]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from resolve_route import (  # noqa: E402
    load_catalog,
    load_profile,
    resolve_route,
    validate_profile,
    validate_route_request,
)
from router_config import config_digest, validate_config  # noqa: E402
sys.path.insert(0, str(ROOT / "tests"))
from validate_skill import validate_model_router_bundle  # noqa: E402


@contextmanager
def temporary_project():
    path = ROOT / "tests" / ".model-router-tmp"
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()
    try:
        yield path
    finally:
        if path.exists():
            shutil.rmtree(path)


def route_request(**overrides):
    request = {
        "router_api_version": "route/v1",
        "request_id": "test-request",
        "route_slot": "writer.c1",
        "writer_route_slot": None,
        "profile_id": PROFILE_ID,
        "explicit_profile_selection": True,
        "explicit_high_volume_selection": False,
        "availability": {"openai/gpt-5.6-luna": "available"},
        "primary_failure_evidence": [],
        "writer_identity": None,
        "candidate_id": "candidate-1",
    }
    request.update(overrides)
    return request


def valid_config(**overrides):
    config = {
        "schema_version": 1,
        "router_api_version": "route/v1",
        "config_id": "test-config",
        "active_profile": PROFILE_ID,
        "project_profile_dirs": [".ai-native/profiles"],
        "updated_reason": "test fixture",
    }
    config.update(overrides)
    return config


class SkillSurfaceTests(unittest.TestCase):
    def test_skill_and_openai_metadata_are_complete(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\s*\n(.*?)\n---", skill, re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = match.group(1)
        self.assertIn("name: ai-native-model-router", frontmatter)
        description = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE).group(1)
        self.assertLessEqual(len(description), 60)
        self.assertTrue(description.endswith("."))
        for required in (
            "version: 0.1.0",
            "author: bzbaizhen, Hermes Agent",
            "license: MIT",
            "platforms:",
            "hermes:",
        ):
            self.assertIn(required, frontmatter)
        config_lines = [
            line for line in frontmatter.splitlines()
            if line.startswith("    config:")
            or line.startswith("      - key:")
            or line.startswith("        description:")
            or line.startswith("        default:")
            or line.startswith("        prompt:")
        ]
        self.assertEqual(
            config_lines,
            [
                "    config:",
                "      - key: ai_native_model_router.config_path",
                "        description: Path to the project-local model router configuration.",
                "        default: .ai-native/model-router.json",
                "        prompt: Enter the project-local model router configuration path.",
            ],
        )
        metadata = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "AI Native Model Router"', metadata)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("default_prompt:", metadata)

    def test_progressive_disclosure_links_every_required_resource(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        expected = {
            "references/interface.md",
            "references/configuration.md",
            "references/provider-evidence.md",
            "assets/provider-catalog.json",
            f"assets/profiles/{PROFILE_ID}.json",
            "assets/model-router-config.v1.schema.json",
            "assets/route-request.v1.schema.json",
            "assets/route-decision.v1.schema.json",
            "scripts/router_config.py",
            "scripts/resolve_route.py",
        }
        links = set(re.findall(r"\]\(([^)#]+)", skill))
        self.assertTrue(expected <= links)
        for target in expected:
            self.assertTrue((SKILL_DIR / target).is_file(), target)

    def test_bundle_validator_rejects_path_frontmatter_and_governance_mutations(self):
        with temporary_project() as project:
            candidate = project / "router"
            shutil.copytree(SKILL_DIR, candidate)

            (candidate / "extra.md").write_text("unexpected", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_model_router_bundle(candidate)
            (candidate / "extra.md").unlink()

            skill_path = candidate / "SKILL.md"
            original = skill_path.read_text(encoding="utf-8")
            skill_path.write_text(original.replace("version: 0.1.0", "version: 0.1.1"), encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_model_router_bundle(candidate)
            skill_path.write_text(original.replace("provider-selection", "governance"), encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_model_router_bundle(candidate)

            skill_path.write_text(original, encoding="utf-8")
            metadata_path = candidate / "agents" / "openai.yaml"
            metadata = metadata_path.read_text(encoding="utf-8")
            metadata_path.write_text(metadata.replace("allow_implicit_invocation: false", "allow_implicit_invocation: true"), encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_model_router_bundle(candidate)

            metadata_path.write_text(metadata, encoding="utf-8")
            config_path = candidate / "assets" / "model-router-config.example.json"
            config = config_path.read_text(encoding="utf-8")
            config_path.write_text(config.replace("project-router-2026-08-28", "wrong-config"), encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_model_router_bundle(candidate)

            config_path.write_text(config, encoding="utf-8")
            link_path = candidate / "SKILL.md"
            link_path.write_text(original.replace("references/interface.md", "references/missing.md"), encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_model_router_bundle(candidate)

            link_path.write_text(original, encoding="utf-8")
            py_path = candidate / "scripts" / "resolve_route.py"
            py_path.write_text(py_path.read_text(encoding="utf-8") + "\ndef (\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_model_router_bundle(candidate)


class CatalogAndProfileTests(unittest.TestCase):
    def test_catalog_has_exact_current_identities_without_secrets(self):
        catalog = load_catalog()
        self.assertEqual(
            set(catalog["providers"]), {"openai", "zai", "deepseek"}
        )
        self.assertEqual(catalog["providers"]["openai"]["runtime_provider"], "custom")
        self.assertEqual(
            set(catalog["providers"]["openai"]["models"]),
            {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"},
        )
        for model, reasoning in {
            "gpt-5.6-luna": "max",
            "gpt-5.6-terra": "max",
            "gpt-5.6-sol": "high",
        }.items():
            self.assertEqual(catalog["providers"]["openai"]["models"][model]["reasoning"], [reasoning])
            self.assertEqual(
                catalog["providers"]["openai"]["models"][model]["reasoning_delivery"],
                "explicit",
            )
        for provider, models in {
            "zai": {"glm-5.3", "glm-5.3-flash"},
            "deepseek": {"deepseek-v4-pro", "deepseek-v4-flash"},
        }.items():
            self.assertEqual(set(catalog["providers"][provider]["models"]), models)
        for model in catalog["providers"]["zai"]["models"].values():
            self.assertEqual(model["reasoning"], ["low", "high", "max"])
            self.assertEqual(model["reasoning_delivery"], "provider-default")
        for model in catalog["providers"]["deepseek"]["models"].values():
            self.assertEqual(model["reasoning"], ["max"])
            self.assertEqual(model["reasoning_delivery"], "explicit")
        self.assertNotRegex(
            json.dumps(catalog).casefold(),
            r"credential|secret|token|endpoint|price|command|transport",
        )

    def test_profile_preserves_mappings_and_exact_fallback_evidence(self):
        profile = load_profile(PROFILE_ID)
        self.assertEqual(profile["profile_id"], PROFILE_ID)
        self.assertFalse(profile["default_active"])
        self.assertEqual(
            set(profile["slots"]),
            {
                "control-plane",
                "writer.c0-batch",
                "writer.c1",
                "writer.c2",
                "writer.c3",
                "validator.independent",
                "writer.high-volume-deterministic",
            },
        )
        expected = {
            "control-plane": ("openai", "gpt-5.6-sol", "high"),
            "writer.c0-batch": ("openai", "gpt-5.6-luna", "max"),
            "writer.c1": ("openai", "gpt-5.6-luna", "max"),
            "writer.c2": ("openai", "gpt-5.6-terra", "max"),
            "writer.c3": ("openai", "gpt-5.6-sol", "high"),
        }
        for slot, identity in expected.items():
            route = profile["slots"][slot]["primary"]
            self.assertEqual((route["provider"], route["model"], route["reasoning"]), identity)
        for slot, fallback_model in (
            ("validator.independent", "deepseek-v4-pro"),
            ("writer.high-volume-deterministic", "deepseek-v4-flash"),
        ):
            slot_data = profile["slots"][slot]
            self.assertEqual(slot_data["fallback"]["model"], fallback_model)
            self.assertEqual(slot_data["accepted_primary_unavailable_evidence"], EVIDENCE)
        self.assertTrue(profile["slots"]["writer.high-volume-deterministic"]["requires_explicit_task_selection"])
        self.assertEqual(
            set(profile["slots"]["validator.independent"]),
            {"primary", "fallback", "accepted_primary_unavailable_evidence", "independent_validator_source"},
        )
        self.assertEqual(
            profile["slots"]["writer.high-volume-deterministic"]["independent_validator_source"],
            "openai-complexity-map",
        )

    def test_profile_mutations_and_catalog_drift_fail_closed(self):
        profile = load_profile(PROFILE_ID)
        for mutation in (
            lambda p: p["slots"]["writer.c1"]["primary"].update(model="unknown-model"),
            lambda p: p["slots"]["writer.c1"].update(extra=True),
            lambda p: p["slots"]["writer.high-volume-deterministic"].update(default=True),
            lambda p: p["slots"]["validator.independent"].update(
                independent_validator_source="other-source"
            ),
            lambda p: p["slots"]["writer.high-volume-deterministic"].update(
                independent_validator_source="other-source"
            ),
        ):
            candidate = copy.deepcopy(profile)
            mutation(candidate)
            with self.assertRaises(ValueError):
                validate_profile(candidate, load_catalog())


class ResolutionTests(unittest.TestCase):
    def test_config_precedence_digest_and_alternate_project_profile(self):
        with temporary_project() as project:
            profile_dir = project / ".ai-native" / "profiles"
            profile_dir.mkdir(parents=True)
            config_path = project / "explicit-config.json"
            config = valid_config(active_profile="alternate")
            config_path.write_text(json.dumps(config), encoding="utf-8")
            alternate = {
                "schema_version": 1,
                "profile_id": "alternate",
                "default_active": False,
                "activation": "explicit-owner-selection",
                "evidence_date": "2026-08-28",
                "forbidden_defaults": [
                    "gpt-5.6-sol:xhigh", "gpt-5.6-sol:max", "gpt-5.6-sol:ultra",
                    "gpt-5.6-luna:low", "gpt-5.6-luna:medium", "gpt-5.6-luna:high", "gpt-5.6-luna:xhigh",
                    "gpt-5.6-terra:low", "gpt-5.6-terra:medium", "gpt-5.6-terra:high", "gpt-5.6-terra:xhigh",
                    "gpt-5.5:*", "gpt-5.4:*",
                ],
                "slots": {
                    slot: {"primary": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high", "reasoning_delivery": "explicit"}}
                    for slot in (
                        "control-plane", "writer.c0-batch", "writer.c1", "writer.c2", "writer.c3"
                    )
                },
            }
            alternate["slots"]["validator.independent"] = {
                "primary": {"provider": "zai", "model": "glm-5.3", "reasoning": "max", "reasoning_delivery": "provider-default"},
                "fallback": {"provider": "deepseek", "model": "deepseek-v4-pro", "reasoning": "max", "reasoning_delivery": "explicit"},
                "accepted_primary_unavailable_evidence": EVIDENCE,
                "independent_validator_source": "openai-complexity-map",
            }
            alternate["slots"]["writer.high-volume-deterministic"] = {
                "primary": {"provider": "zai", "model": "glm-5.3-flash", "reasoning": "max", "reasoning_delivery": "provider-default"},
                "fallback": {"provider": "deepseek", "model": "deepseek-v4-flash", "reasoning": "max", "reasoning_delivery": "explicit"},
                "accepted_primary_unavailable_evidence": EVIDENCE,
                "independent_validator_source": "openai-complexity-map",
                "default": False,
                "requires_explicit_task_selection": True,
            }
            (profile_dir / "alternate.json").write_text(json.dumps(alternate), encoding="utf-8")
            decision = resolve_route(
                route_request(
                    profile_id="alternate",
                    route_slot="validator.independent",
                    writer_route_slot="writer.c1",
                    writer_identity={"provider": "zai", "runtime_provider": "zai", "model": "glm-5.3"},
                    availability={"openai/gpt-5.6-sol": "available"},
                ), cwd=project, config_path=config_path
            )
            self.assertEqual(decision["selected_route"]["model"], "gpt-5.6-sol")
            self.assertEqual(decision["selected_route"]["runtime_provider"], "custom")
            self.assertEqual(decision["config_digest"], config_digest(validate_config(config)))

    def test_primary_fallback_unknown_and_unaccepted_evidence(self):
        base = route_request(
            route_slot="validator.independent",
            writer_route_slot="writer.c1",
            writer_identity={"provider": "openai", "runtime_provider": "custom", "model": "gpt-5.6-luna"},
            availability={"zai/glm-5.3": "available"},
        )
        self.assertEqual(resolve_route(base)["decision_status"], "selected")
        fallback = dict(base, availability={"zai/glm-5.3": "unavailable", "deepseek/deepseek-v4-pro": "available"}, primary_failure_evidence=EVIDENCE[:1])
        selected = resolve_route(fallback)
        self.assertEqual(selected["selected_route"]["model"], "deepseek-v4-pro")
        self.assertEqual(selected["fallback_evidence"], EVIDENCE[:1])
        unknown = dict(base, availability={"zai/glm-5.3": "unknown"})
        unknown_decision = resolve_route(unknown)
        self.assertEqual(unknown_decision["decision_status"], "unknown")
        self.assertEqual(unknown_decision["independent_validator_source"], "router-selected")
        blocked = dict(fallback, primary_failure_evidence=["cost-preference"])
        blocked_decision = resolve_route(blocked)
        self.assertEqual(blocked_decision["decision_status"], "blocked")
        self.assertEqual(blocked_decision["independent_validator_source"], "router-selected")
        self.assertFalse(resolve_route(blocked)["fallback_used"])

    def test_high_volume_requires_explicit_selection_and_validator_is_independent(self):
        request = route_request(
            route_slot="writer.high-volume-deterministic",
            explicit_high_volume_selection=True,
            availability={"zai/glm-5.3-flash": "available"},
        )
        decision = resolve_route(request)
        self.assertEqual(decision["decision_status"], "selected")
        self.assertEqual(decision["selected_route"]["model"], "glm-5.3-flash")
        self.assertEqual(decision["enforcement_status"], "not-executed")
        self.assertEqual(decision["independent_validator_source"], "openai-complexity-map")
        fallback = resolve_route(dict(
            request,
            availability={"zai/glm-5.3-flash": "unavailable", "deepseek/deepseek-v4-flash": "available"},
            primary_failure_evidence=EVIDENCE[:1],
        ))
        self.assertEqual(fallback["decision_status"], "selected")
        self.assertTrue(fallback["fallback_used"])
        self.assertEqual(fallback["independent_validator_source"], "openai-complexity-map")
        unknown = resolve_route(dict(request, availability={"zai/glm-5.3-flash": "unknown"}))
        self.assertEqual(unknown["decision_status"], "unknown")
        self.assertEqual(unknown["independent_validator_source"], "openai-complexity-map")
        blocked = resolve_route(dict(
            request,
            availability={"zai/glm-5.3-flash": "unavailable"},
            primary_failure_evidence=["unaccepted-evidence"],
        ))
        self.assertEqual(blocked["decision_status"], "blocked")
        self.assertEqual(blocked["independent_validator_source"], "openai-complexity-map")
        with self.assertRaises(ValueError):
            validate_route_request(dict(request, explicit_high_volume_selection=False))
        self_validation = route_request(
            route_slot="validator.independent",
            writer_route_slot="writer.c1",
            writer_identity={"provider": "zai", "runtime_provider": "zai", "model": "glm-5.3"},
            availability={"zai/glm-5.3": "available"},
        )
        self.assertEqual(resolve_route(self_validation)["decision_status"], "unknown")

    def test_runtime_provider_is_expanded_for_openai_and_zai_routes(self):
        openai = resolve_route(route_request())
        self.assertEqual(
            openai["selected_route"],
            {
                "provider": "openai",
                "runtime_provider": "custom",
                "model": "gpt-5.6-luna",
                "reasoning": "max",
                "reasoning_delivery": "explicit",
            },
        )
        zai = resolve_route(
            route_request(
                route_slot="writer.high-volume-deterministic",
                explicit_high_volume_selection=True,
                availability={"zai/glm-5.3-flash": "available"},
            )
        )
        self.assertEqual(zai["selected_route"]["provider"], "zai")
        self.assertEqual(zai["selected_route"]["runtime_provider"], "zai")

    def test_writer_route_slot_invariant_is_fail_closed(self):
        self.assertIsNone(validate_route_request(route_request())["writer_route_slot"])
        self.assertEqual(
            validate_route_request(
                route_request(route_slot="validator.independent", writer_route_slot="writer.c1")
            )["writer_route_slot"],
            "writer.c1",
        )
        for invalid in (
            route_request(route_slot="validator.independent", writer_route_slot=None),
            route_request(route_slot="writer.c1", writer_route_slot="writer.c1"),
            route_request(writer_route_slot="validator.independent"),
        ):
            with self.assertRaises(ValueError):
                validate_route_request(invalid)

    def test_non_openai_writer_uses_selected_writer_primary_without_validator_fallback(self):
        not_fallback_collision = route_request(
            route_slot="validator.independent",
            writer_route_slot="writer.c1",
            writer_identity={"provider": "deepseek", "runtime_provider": "deepseek", "model": "deepseek-v4-pro"},
            availability={
                "openai/gpt-5.6-luna": "available",
                "deepseek/deepseek-v4-pro": "available",
            },
        )
        selected = resolve_route(not_fallback_collision)
        self.assertEqual(selected["decision_status"], "selected")
        self.assertEqual(selected["selected_route"]["model"], "gpt-5.6-luna")
        self.assertFalse(selected["fallback_used"])

        unavailable = dict(
            not_fallback_collision,
            availability={
                "openai/gpt-5.6-luna": "unavailable",
                "deepseek/deepseek-v4-pro": "available",
            },
            primary_failure_evidence=EVIDENCE[:1],
        )
        blocked = resolve_route(unavailable)
        self.assertEqual(blocked["decision_status"], "blocked")
        self.assertIsNone(blocked["selected_route"])
        self.assertFalse(blocked["fallback_used"])

    def test_self_validation_compares_only_actual_selected_candidate(self):
        request = route_request(
            route_slot="validator.independent",
            writer_route_slot="writer.c1",
            writer_identity={"provider": "deepseek", "runtime_provider": "deepseek", "model": "deepseek-v4-pro"},
            availability={"openai/gpt-5.6-luna": "available"},
        )
        decision = resolve_route(request)
        self.assertEqual(decision["decision_status"], "selected")
        self.assertNotEqual(decision["selected_route"]["model"], request["writer_identity"]["model"])

    def test_self_validation_blocks_logical_or_runtime_identity_matches(self):
        profile = load_profile(PROFILE_ID)
        profile["slots"]["validator.independent"]["primary"] = {
            "provider": "openai", "model": "gpt-5.6-luna", "reasoning": "max", "reasoning_delivery": "explicit"
        }
        for identity in (
            {"provider": "openai", "runtime_provider": "other-host", "model": "gpt-5.6-luna"},
            {"provider": "other-family", "runtime_provider": "custom", "model": "gpt-5.6-luna"},
        ):
            with self.subTest(identity=identity):
                with patch("resolve_route.load_profile", return_value=profile):
                    decision = resolve_route(route_request(
                        route_slot="validator.independent",
                        writer_route_slot="writer.c1",
                        writer_identity=identity,
                        availability={"openai/gpt-5.6-luna": "available"},
                    ))
                self.assertEqual(decision["decision_status"], "blocked")
                self.assertIsNone(decision["selected_route"])

    def test_changed_bundled_profile_blocks_even_when_hashes_are_equal(self):
        with temporary_project() as project:
            profile_dir = project / ".ai-native" / "profiles"
            profile_dir.mkdir(parents=True)
            bundled = SKILL_DIR / "assets" / "profiles" / f"{PROFILE_ID}.json"
            changed = json.loads(bundled.read_text(encoding="utf-8"))
            changed["evidence_date"] = "2099-01-01"
            candidate = profile_dir / f"{PROFILE_ID}.json"
            candidate.write_text(json.dumps(changed), encoding="utf-8")

            class SameDigest:
                def hexdigest(self):
                    return "0" * 64

            with patch("hashlib.sha256", return_value=SameDigest()):
                with self.assertRaises(ValueError):
                    load_profile(PROFILE_ID, project_root=project, project_profile_dirs=[".ai-native/profiles"])

    def test_collision_blocks_changed_bundled_profile(self):
        with temporary_project() as project:
            profile_dir = project / ".ai-native" / "profiles"
            profile_dir.mkdir(parents=True)
            bundled = SKILL_DIR / "assets" / "profiles" / f"{PROFILE_ID}.json"
            changed = json.loads(bundled.read_text(encoding="utf-8"))
            changed["evidence_date"] = "2099-01-01"
            (profile_dir / f"{PROFILE_ID}.json").write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_profile(PROFILE_ID, project_root=project, project_profile_dirs=[".ai-native/profiles"])

    def test_request_schema_and_forbidden_profile_paths_fail_closed(self):
        with self.assertRaises(ValueError):
            validate_route_request(dict(route_request(), extra=True))
        with self.assertRaises(ValueError):
            validate_route_request(dict(route_request(), explicit_profile_selection=False))
        with temporary_project() as project:
            with self.assertRaises(ValueError):
                load_profile(PROFILE_ID, project_root=project, project_profile_dirs=["../outside"])

    def test_all_decisions_have_digest_and_no_execution_claim(self):
        for request in (
            route_request(),
            route_request(availability={"openai/gpt-5.6-luna": "unknown"}),
        ):
            decision = resolve_route(request)
            self.assertRegex(decision["config_digest"], r"^[0-9a-f]{64}$")
            self.assertEqual(decision["enforcement_status"], "not-executed")
            self.assertIn("execute", " ".join(decision["limitations"]).casefold())


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SKILL_DIR / "scripts" / "resolve_route.py"), *args],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )

    def test_list_validate_and_resolve_commands_emit_json(self):
        listed = self.run_cli("list-profiles")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn(PROFILE_ID, json.loads(listed.stdout)["profiles"])
        validated = self.run_cli("validate-profile", "--profile", PROFILE_ID)
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertEqual(json.loads(validated.stdout)["profile_id"], PROFILE_ID)
        with temporary_project() as project:
            request_path = project / "request.json"
            request_path.write_text(json.dumps(route_request()), encoding="utf-8")
            resolved = self.run_cli("resolve", "--request", str(request_path))
            self.assertEqual(resolved.returncode, 0, resolved.stderr)
            self.assertEqual(json.loads(resolved.stdout)["decision_status"], "selected")

    def test_cli_errors_are_stderr_and_nonzero(self):
        result = self.run_cli("validate-profile", "--profile", "missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("ERROR:", result.stderr)


class StructureTests(unittest.TestCase):
    def test_router_directory_has_no_governance_logic(self):
        forbidden = re.compile(r"\b(?:Core|Controlled|DQR|Linear)\b")
        for path in SKILL_DIR.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".md", ".py", ".json", ".yaml"}:
                self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")), path)


if __name__ == "__main__":
    unittest.main()
