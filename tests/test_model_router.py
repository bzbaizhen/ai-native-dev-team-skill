import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unittest
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
import uuid
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "ai-native-model-router"
ASSET_DIR = SKILL_DIR / "assets"
PROFILE_ID = "openai-glm5.3-deepseek-fallback-2026-08-28"
NEW_PROFILE_ID = "openai-gpt5.6-validator-assurance-2026-08-31"
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
    validate_profile_v2,
    validate_profile_versioned,
    validate_route_request,
    validate_route_request_v2,
)
from router_config import config_digest, validate_config  # noqa: E402
sys.path.insert(0, str(ROOT / "tests"))


_validate_skill_import_failure = None
try:
    with redirect_stdout(StringIO()) as _validate_skill_output:
        from validate_skill import validate_model_router_bundle  # noqa: E402
except SystemExit as exc:
    _validate_skill_import_failure = _validate_skill_output.getvalue().strip()
    if exc.code != 1 or _validate_skill_import_failure != (
        "FAIL: suite manifest inventory drifted: ai-native-model-router"
    ):
        raise
    validate_model_router_bundle = None


@contextmanager
def temporary_project():
    path = ROOT / "tests" / f".model-router-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
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


def route_v2_request(**overrides):
    request = {
        "router_api_version": "route/v2",
        "request_id": "test-v2-request",
        "route_slot": "validator.assurance",
        "writer_route_slot": "writer.c1",
        "profile_id": NEW_PROFILE_ID,
        "explicit_profile_selection": True,
        "explicit_high_volume_selection": False,
        "availability": {},
        "route_failure_evidence": {},
        "risk_level": "R1",
        "writer_identity": {
            "provider": "openai",
            "runtime_provider": "custom",
            "model": "gpt-5.6-luna",
        },
        "candidate_id": "candidate-v2-1",
    }
    request.update(overrides)
    return request


def assert_v2_decision_matches_schema(testcase, decision):
    schema = json.loads(
        (ASSET_DIR / "route-decision.v2.schema.json").read_text(encoding="utf-8")
    )
    required = set(schema["required"])
    testcase.assertEqual(set(decision), required)
    properties = schema["properties"]

    for field in (
        "router_api_version",
        "request_id",
        "profile_id",
        "route_slot",
        "decision_status",
        "enforcement_status",
        "validation_mode",
        "config_digest",
    ):
        testcase.assertIsInstance(decision[field], str)
        testcase.assertTrue(decision[field])
        if "enum" in properties[field]:
            testcase.assertIn(decision[field], properties[field]["enum"])
        if "const" in properties[field]:
            testcase.assertEqual(decision[field], properties[field]["const"])

    testcase.assertEqual(decision["router_api_version"], "route/v2")
    testcase.assertRegex(decision["config_digest"], r"^[0-9a-f]{64}$")
    testcase.assertIsInstance(decision["risk_level"], (str, type(None)))
    if decision["risk_level"] is not None:
        testcase.assertIn(decision["risk_level"], properties["risk_level"]["enum"])

    testcase.assertIsInstance(decision["selected_routes"], list)
    testcase.assertLessEqual(
        len(decision["selected_routes"]), schema["properties"]["selected_routes"]["maxItems"]
    )
    route_keys = set(schema["properties"]["selected_routes"]["items"]["required"])
    seen_routes = set()
    for route in decision["selected_routes"]:
        testcase.assertEqual(set(route), route_keys)
        testcase.assertNotIn(json.dumps(route, sort_keys=True), seen_routes)
        seen_routes.add(json.dumps(route, sort_keys=True))
        for value in route.values():
            testcase.assertIsInstance(value, str)
            testcase.assertTrue(value)

    testcase.assertIn(decision["validation_mode"], properties["validation_mode"]["enum"])
    testcase.assertIn(decision["decision_status"], properties["decision_status"]["enum"])
    testcase.assertIn(decision["enforcement_status"], properties["enforcement_status"]["enum"])
    testcase.assertIs(type(decision["escalation_used"]), bool)
    testcase.assertIs(type(decision["same_model_as_writer"]), bool)
    testcase.assertIn(decision["validator_source"], properties["validator_source"]["enum"])

    testcase.assertIsInstance(decision["escalation_evidence"], dict)
    evidence_pattern = schema["properties"]["escalation_evidence"]["propertyNames"]["pattern"]
    for route_key, evidence in decision["escalation_evidence"].items():
        testcase.assertRegex(route_key, evidence_pattern)
        testcase.assertIsInstance(evidence, list)
        testcase.assertEqual(len(evidence), len(set(evidence)))
        for item in evidence:
            testcase.assertIsInstance(item, str)
            testcase.assertTrue(item)

    testcase.assertIsInstance(decision["limitations"], list)
    for limitation in decision["limitations"]:
        testcase.assertIsInstance(limitation, str)
        testcase.assertTrue(limitation)

    if decision["route_slot"] == "validator.assurance":
        testcase.assertIn(decision["risk_level"], {"R1", "R2", "R3"})
        testcase.assertEqual(decision["validator_source"], "router-selected")
    else:
        testcase.assertIsNone(decision["risk_level"])
        testcase.assertEqual(decision["validation_mode"], "not-applicable")
        testcase.assertFalse(decision["same_model_as_writer"])
        testcase.assertEqual(decision["validator_source"], "not-applicable")
    if decision["risk_level"] == "R3":
        testcase.assertEqual(decision["validation_mode"], "dual")


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
        if validate_model_router_bundle is None:
            self.skipTest(
                "validate_skill.py import reached independent Task 3 gate: "
                + _validate_skill_import_failure
            )
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

    def test_new_profile_asset_preserves_non_validator_slots_and_exact_assurance_routes(self):
        old_profile = json.loads(
            (ASSET_DIR / "profiles" / f"{PROFILE_ID}.json").read_text(encoding="utf-8")
        )
        new_profile = json.loads(
            (ASSET_DIR / "profiles" / f"{NEW_PROFILE_ID}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(new_profile["schema_version"], 2)
        self.assertEqual(new_profile["profile_id"], NEW_PROFILE_ID)
        self.assertFalse(new_profile["default_active"])
        self.assertEqual(new_profile["activation"], "explicit-owner-selection")
        self.assertEqual(new_profile["evidence_date"], "2026-08-31")
        self.assertEqual(
            set(new_profile["slots"]),
            {
                "control-plane",
                "writer.c0-batch",
                "writer.c1",
                "writer.c2",
                "writer.c3",
                "validator.assurance",
                "writer.high-volume-deterministic",
            },
        )
        for slot in (
            "control-plane",
            "writer.c0-batch",
            "writer.c1",
            "writer.c2",
            "writer.c3",
            "writer.high-volume-deterministic",
        ):
            with self.subTest(slot=slot):
                self.assertEqual(new_profile["slots"][slot], old_profile["slots"][slot])
        self.assertEqual(new_profile["forbidden_defaults"], old_profile["forbidden_defaults"])

        assurance = new_profile["slots"]["validator.assurance"]
        self.assertEqual(
            set(assurance),
            {
                "allow_same_model_as_writer",
                "accepted_route_failure_evidence",
                "routes_by_risk",
                "exhaustion_action",
            },
        )
        self.assertTrue(assurance["allow_same_model_as_writer"])
        self.assertEqual(assurance["accepted_route_failure_evidence"], EVIDENCE)
        self.assertEqual(assurance["exhaustion_action"], "blocked-owner")

        def route_identity(route):
            return (route["provider"], route["model"], route["reasoning"], route["reasoning_delivery"])

        expected_routes = {
            "R1": [
                ("openai", "gpt-5.6-luna", "max", "explicit"),
                ("openai", "gpt-5.6-terra", "max", "explicit"),
                ("openai", "gpt-5.6-sol", "high", "explicit"),
            ],
            "R2": [
                ("openai", "gpt-5.6-terra", "max", "explicit"),
                ("openai", "gpt-5.6-sol", "high", "explicit"),
            ],
            "R3": [
                ("openai", "gpt-5.6-terra", "max", "explicit"),
                ("openai", "gpt-5.6-sol", "high", "explicit"),
            ],
        }
        self.assertEqual(set(assurance["routes_by_risk"]), set(expected_routes))
        for risk, routes in expected_routes.items():
            with self.subTest(risk=risk):
                actual = [route_identity(route) for route in assurance["routes_by_risk"][risk]]
                self.assertEqual(actual, routes)
                self.assertTrue(all(route["provider"] == "openai" for route in assurance["routes_by_risk"][risk]))
                self.assertNotRegex(json.dumps(assurance["routes_by_risk"][risk]).casefold(), r"glm|deepseek")

    def test_new_profile_is_loadable_as_a_bundled_profile(self):
        self.assertEqual(load_profile(NEW_PROFILE_ID)["profile_id"], NEW_PROFILE_ID)
        profile = load_profile(NEW_PROFILE_ID)
        with self.assertRaises(ValueError):
            validate_profile(profile, load_catalog())
        self.assertEqual(validate_profile_v2(profile, load_catalog()), profile)
        self.assertEqual(validate_profile_versioned(profile, load_catalog()), profile)


class ResolutionTests(unittest.TestCase):
    def test_v2_request_validation_rejects_mixed_versions_and_invalid_evidence_keys(self):
        self.assertEqual(validate_route_request_v2(route_v2_request()), route_v2_request())
        with self.assertRaises(ValueError):
            validate_route_request(route_v2_request())
        with self.assertRaises(ValueError):
            validate_route_request_v2(route_request())
        with self.assertRaises(ValueError):
            validate_route_request_v2(
                route_v2_request(route_failure_evidence={"openai:gpt-5.6-luna": EVIDENCE[:1]})
            )
        with self.assertRaises(ValueError):
            validate_route_request_v2(route_v2_request(candidate_id=None))

    def test_v2_requires_exact_availability_and_route_bound_evidence(self):
        alias_only = resolve_route(
            route_v2_request(availability={"gpt-5.6-luna": "available"})
        )
        self.assertEqual(alias_only["decision_status"], "unknown")
        self.assertEqual(alias_only["selected_routes"], [])
        wrong_evidence_key = resolve_route(
            route_v2_request(
                availability={
                    "openai/gpt-5.6-luna": "unavailable",
                    "openai/gpt-5.6-terra": "available",
                },
                route_failure_evidence={"openai/gpt-5.6-sol": EVIDENCE[:1]},
            )
        )
        self.assertEqual(wrong_evidence_key["decision_status"], "blocked")
        self.assertEqual(wrong_evidence_key["selected_routes"], [])
        self.assertEqual(
            wrong_evidence_key["escalation_evidence"],
            {"openai/gpt-5.6-luna": []},
        )

    def test_v2_request_and_config_profile_versions_cannot_be_mixed(self):
        with self.assertRaises(ValueError):
            resolve_route(route_v2_request(profile_id=PROFILE_ID))
        with self.assertRaises(ValueError):
            resolve_route(route_request(profile_id=NEW_PROFILE_ID))

    def test_v2_r1_initial_luna_selection_and_same_model_identity(self):
        decision = resolve_route(
            route_v2_request(
                availability={"openai/gpt-5.6-luna": "available"},
            )
        )
        self.assertEqual(decision["decision_status"], "selected")
        self.assertEqual(decision["validation_mode"], "single")
        self.assertEqual(len(decision["selected_routes"]), 1)
        self.assertEqual(decision["selected_routes"][0]["model"], "gpt-5.6-luna")
        self.assertEqual(decision["selected_routes"][0]["runtime_provider"], "custom")
        self.assertFalse(decision["escalation_used"])
        self.assertEqual(decision["escalation_evidence"], {})
        self.assertTrue(decision["same_model_as_writer"])
        self.assertEqual(decision["validator_source"], "router-selected")
        self.assertEqual(decision["enforcement_status"], "not-executed")

    def test_v2_r1_luna_unavailable_with_accepted_evidence_escalates_to_terra(self):
        decision = resolve_route(
            route_v2_request(
                availability={
                    "openai/gpt-5.6-luna": "unavailable",
                    "openai/gpt-5.6-terra": "available",
                },
                route_failure_evidence={
                    "openai/gpt-5.6-luna": EVIDENCE[:1],
                },
            )
        )
        self.assertEqual(decision["decision_status"], "selected")
        self.assertEqual(decision["selected_routes"][0]["model"], "gpt-5.6-terra")
        self.assertTrue(decision["escalation_used"])
        self.assertEqual(
            decision["escalation_evidence"],
            {"openai/gpt-5.6-luna": EVIDENCE[:1]},
        )
        self.assertFalse(decision["same_model_as_writer"])

    def test_v2_r2_initial_terra_selection(self):
        decision = resolve_route(
            route_v2_request(
                risk_level="R2",
                writer_route_slot="writer.c2",
                availability={"openai/gpt-5.6-terra": "available"},
            )
        )
        self.assertEqual(decision["decision_status"], "selected")
        self.assertEqual(decision["validation_mode"], "single")
        self.assertEqual(
            [route["model"] for route in decision["selected_routes"]],
            ["gpt-5.6-terra"],
        )
        self.assertFalse(decision["escalation_used"])

    def test_v2_r2_terra_unavailable_with_accepted_evidence_escalates_to_sol(self):
        decision = resolve_route(
            route_v2_request(
                risk_level="R2",
                writer_route_slot="writer.c2",
                availability={
                    "openai/gpt-5.6-terra": "unavailable",
                    "openai/gpt-5.6-sol": "available",
                },
                route_failure_evidence={
                    "openai/gpt-5.6-terra": EVIDENCE[:1],
                },
            )
        )
        self.assertEqual(decision["decision_status"], "selected")
        self.assertEqual(decision["selected_routes"][0]["model"], "gpt-5.6-sol")
        self.assertTrue(decision["escalation_used"])
        self.assertEqual(
            decision["escalation_evidence"],
            {"openai/gpt-5.6-terra": EVIDENCE[:1]},
        )

    def test_v2_r1_full_chain_escalates_from_luna_through_terra_to_sol(self):
        decision = resolve_route(
            route_v2_request(
                availability={
                    "openai/gpt-5.6-luna": "unavailable",
                    "openai/gpt-5.6-terra": "unavailable",
                    "openai/gpt-5.6-sol": "available",
                },
                route_failure_evidence={
                    "openai/gpt-5.6-luna": EVIDENCE[:1],
                    "openai/gpt-5.6-terra": EVIDENCE[1:2],
                },
            )
        )
        self.assertEqual(decision["decision_status"], "selected")
        self.assertEqual(decision["selected_routes"][0]["model"], "gpt-5.6-sol")
        self.assertTrue(decision["escalation_used"])
        self.assertEqual(
            decision["escalation_evidence"],
            {
                "openai/gpt-5.6-luna": EVIDENCE[:1],
                "openai/gpt-5.6-terra": EVIDENCE[1:2],
            },
        )

    def test_v2_r1_and_r2_chain_exhaustion_blocks(self):
        cases = (
            (
                "R1",
                "writer.c1",
                {
                    "openai/gpt-5.6-luna": "unavailable",
                    "openai/gpt-5.6-terra": "unavailable",
                    "openai/gpt-5.6-sol": "unavailable",
                },
                {
                    "openai/gpt-5.6-luna": EVIDENCE[:1],
                    "openai/gpt-5.6-terra": EVIDENCE[1:2],
                    "openai/gpt-5.6-sol": EVIDENCE[2:3],
                },
            ),
            (
                "R2",
                "writer.c2",
                {
                    "openai/gpt-5.6-terra": "unavailable",
                    "openai/gpt-5.6-sol": "unavailable",
                },
                {
                    "openai/gpt-5.6-terra": EVIDENCE[:1],
                    "openai/gpt-5.6-sol": EVIDENCE[1:2],
                },
            ),
        )
        for risk_level, writer_route_slot, availability, evidence in cases:
            with self.subTest(risk_level=risk_level):
                decision = resolve_route(
                    route_v2_request(
                        risk_level=risk_level,
                        writer_route_slot=writer_route_slot,
                        availability=availability,
                        route_failure_evidence=evidence,
                    )
                )
                self.assertEqual(decision["decision_status"], "blocked")
                self.assertEqual(decision["selected_routes"], [])
                self.assertTrue(decision["escalation_used"])
                self.assertEqual(decision["escalation_evidence"], evidence)
                self.assertTrue(any("Owner" in item for item in decision["limitations"]))

    def test_v2_r1_and_r2_post_escalation_unknown_returns_unknown(self):
        cases = (
            (
                "R1",
                "writer.c1",
                {
                    "openai/gpt-5.6-luna": "unavailable",
                    "openai/gpt-5.6-terra": "unknown",
                    "openai/gpt-5.6-sol": "available",
                },
                {"openai/gpt-5.6-luna": EVIDENCE[:1]},
            ),
            (
                "R2",
                "writer.c2",
                {
                    "openai/gpt-5.6-terra": "unavailable",
                    "openai/gpt-5.6-sol": "unknown",
                },
                {"openai/gpt-5.6-terra": EVIDENCE[:1]},
            ),
        )
        for risk_level, writer_route_slot, availability, evidence in cases:
            with self.subTest(risk_level=risk_level):
                decision = resolve_route(
                    route_v2_request(
                        risk_level=risk_level,
                        writer_route_slot=writer_route_slot,
                        availability=availability,
                        route_failure_evidence=evidence,
                    )
                )
                self.assertEqual(decision["decision_status"], "unknown")
                self.assertEqual(decision["selected_routes"], [])
                self.assertTrue(decision["escalation_used"])
                self.assertEqual(decision["escalation_evidence"], evidence)

    def test_v2_r1_and_r2_unaccepted_route_evidence_blocks(self):
        cases = (
            (
                "R1",
                "writer.c1",
                {"openai/gpt-5.6-luna": "unavailable"},
                {"openai/gpt-5.6-luna": ["valid-validator-rejection"]},
            ),
            (
                "R1",
                "writer.c1",
                {
                    "openai/gpt-5.6-luna": "unavailable",
                    "openai/gpt-5.6-terra": "unavailable",
                },
                {
                    "openai/gpt-5.6-luna": EVIDENCE[:1],
                    "openai/gpt-5.6-terra": ["valid-validator-rejection"],
                },
            ),
            (
                "R2",
                "writer.c2",
                {"openai/gpt-5.6-terra": "unavailable"},
                {"openai/gpt-5.6-terra": ["valid-validator-rejection"]},
            ),
            (
                "R2",
                "writer.c2",
                {
                    "openai/gpt-5.6-terra": "unavailable",
                    "openai/gpt-5.6-sol": "unavailable",
                },
                {
                    "openai/gpt-5.6-terra": EVIDENCE[:1],
                    "openai/gpt-5.6-sol": ["valid-validator-rejection"],
                },
            ),
        )
        for risk_level, writer_route_slot, availability, evidence in cases:
            with self.subTest(risk_level=risk_level, evidence=evidence):
                decision = resolve_route(
                    route_v2_request(
                        risk_level=risk_level,
                        writer_route_slot=writer_route_slot,
                        availability=availability,
                        route_failure_evidence=evidence,
                    )
                )
                self.assertEqual(decision["decision_status"], "blocked")
                self.assertEqual(decision["selected_routes"], [])
                self.assertEqual(decision["escalation_evidence"], evidence)

    def test_v2_r3_both_available_selects_both_in_deterministic_order(self):
        decision = resolve_route(
            route_v2_request(
                risk_level="R3",
                writer_route_slot="writer.c2",
                availability={
                    "openai/gpt-5.6-terra": "available",
                    "openai/gpt-5.6-sol": "available",
                },
            )
        )
        self.assertEqual(decision["decision_status"], "selected")
        self.assertEqual(decision["validation_mode"], "dual")
        self.assertEqual(
            [route["model"] for route in decision["selected_routes"]],
            ["gpt-5.6-terra", "gpt-5.6-sol"],
        )
        self.assertFalse(decision["escalation_used"])
        self.assertEqual(decision["escalation_evidence"], {})

    def test_v2_r3_unknown_required_route_returns_unknown_without_degradation(self):
        for unknown_key in ("openai/gpt-5.6-terra", "openai/gpt-5.6-sol"):
            with self.subTest(unknown_key=unknown_key):
                availability = {
                    "openai/gpt-5.6-terra": "available",
                    "openai/gpt-5.6-sol": "available",
                }
                availability[unknown_key] = "unknown"
                decision = resolve_route(
                    route_v2_request(
                        risk_level="R3",
                        writer_route_slot="writer.c2",
                        availability=availability,
                    )
                )
                self.assertEqual(decision["decision_status"], "unknown")
                self.assertEqual(decision["validation_mode"], "dual")
                self.assertEqual(decision["selected_routes"], [])
                self.assertFalse(decision["escalation_used"])
                self.assertTrue(any("Owner" in item for item in decision["limitations"]))

    def test_v2_r3_unavailable_with_accepted_evidence_blocks_without_degradation(self):
        decision = resolve_route(
            route_v2_request(
                risk_level="R3",
                writer_route_slot="writer.c2",
                availability={
                    "openai/gpt-5.6-terra": "unavailable",
                    "openai/gpt-5.6-sol": "available",
                },
                route_failure_evidence={
                    "openai/gpt-5.6-terra": EVIDENCE[:1],
                },
            )
        )
        self.assertEqual(decision["decision_status"], "blocked")
        self.assertEqual(decision["validation_mode"], "dual")
        self.assertEqual(decision["selected_routes"], [])
        self.assertFalse(decision["escalation_used"])
        self.assertEqual(
            decision["escalation_evidence"],
            {"openai/gpt-5.6-terra": EVIDENCE[:1]},
        )
        self.assertTrue(any("Owner" in item for item in decision["limitations"]))

    def test_v2_r3_unaccepted_evidence_blocks_without_degradation(self):
        decision = resolve_route(
            route_v2_request(
                risk_level="R3",
                writer_route_slot="writer.c2",
                availability={
                    "openai/gpt-5.6-terra": "unavailable",
                    "openai/gpt-5.6-sol": "available",
                },
                route_failure_evidence={
                    "openai/gpt-5.6-terra": ["valid-validator-rejection"],
                },
            )
        )
        self.assertEqual(decision["decision_status"], "blocked")
        self.assertEqual(decision["selected_routes"], [])
        self.assertEqual(
            decision["escalation_evidence"],
            {"openai/gpt-5.6-terra": ["valid-validator-rejection"]},
        )
        self.assertTrue(any("Owner" in item for item in decision["limitations"]))

    def test_v2_r3_same_model_status_is_reported_without_blocking(self):
        decision = resolve_route(
            route_v2_request(
                risk_level="R3",
                writer_route_slot="writer.c2",
                writer_identity={
                    "provider": "openai",
                    "runtime_provider": "custom",
                    "model": "gpt-5.6-terra",
                },
                availability={
                    "openai/gpt-5.6-terra": "available",
                    "openai/gpt-5.6-sol": "available",
                },
            )
        )
        self.assertEqual(decision["decision_status"], "selected")
        self.assertEqual(len(decision["selected_routes"]), 2)
        self.assertTrue(decision["same_model_as_writer"])

    def test_v2_selected_unknown_and_blocked_decisions_match_committed_schema(self):
        cases = (
            (
                "selected",
                route_v2_request(
                    availability={"openai/gpt-5.6-luna": "available"},
                ),
            ),
            (
                "unknown",
                route_v2_request(
                    risk_level="R2",
                    writer_route_slot="writer.c2",
                    availability={},
                ),
            ),
            (
                "blocked",
                route_v2_request(
                    risk_level="R3",
                    writer_route_slot="writer.c2",
                    availability={
                        "openai/gpt-5.6-terra": "unavailable",
                        "openai/gpt-5.6-sol": "available",
                    },
                    route_failure_evidence={
                        "openai/gpt-5.6-terra": EVIDENCE[:1],
                    },
                ),
            ),
        )
        for expected_status, request in cases:
            with self.subTest(expected_status=expected_status):
                decision = resolve_route(request)
                self.assertEqual(decision["decision_status"], expected_status)
                assert_v2_decision_matches_schema(self, decision)

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

    def test_collision_blocks_changed_new_bundled_profile(self):
        with temporary_project() as project:
            profile_dir = project / ".ai-native" / "profiles"
            profile_dir.mkdir(parents=True)
            bundled = SKILL_DIR / "assets" / "profiles" / f"{NEW_PROFILE_ID}.json"
            changed = json.loads(bundled.read_text(encoding="utf-8"))
            changed["evidence_date"] = "2099-01-01"
            (profile_dir / f"{NEW_PROFILE_ID}.json").write_text(
                json.dumps(changed), encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                load_profile(
                    NEW_PROFILE_ID,
                    project_root=project,
                    project_profile_dirs=[".ai-native/profiles"],
                )

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
        self.assertIn(NEW_PROFILE_ID, json.loads(listed.stdout)["profiles"])
        validated = self.run_cli("validate-profile", "--profile", PROFILE_ID)
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertEqual(json.loads(validated.stdout)["profile_id"], PROFILE_ID)
        validated_new = self.run_cli("validate-profile", "--profile", NEW_PROFILE_ID)
        self.assertEqual(validated_new.returncode, 0, validated_new.stderr)
        self.assertEqual(json.loads(validated_new.stdout)["profile_id"], NEW_PROFILE_ID)
        with temporary_project() as project:
            request_path = project / "request.json"
            request_path.write_text(json.dumps(route_request()), encoding="utf-8")
            resolved = self.run_cli("resolve", "--request", str(request_path))
            self.assertEqual(resolved.returncode, 0, resolved.stderr)
            self.assertEqual(json.loads(resolved.stdout)["decision_status"], "selected")

    def test_cli_resolves_v2_r1_r2_r3_selected_unknown_and_blocked(self):
        cases = (
            (
                "r1-selected",
                route_v2_request(
                    availability={"openai/gpt-5.6-luna": "available"},
                ),
                "selected",
            ),
            (
                "r1-unknown",
                route_v2_request(availability={}),
                "unknown",
            ),
            (
                "r1-blocked",
                route_v2_request(
                    availability={"openai/gpt-5.6-luna": "unavailable"},
                    route_failure_evidence={
                        "openai/gpt-5.6-luna": ["valid-validator-rejection"],
                    },
                ),
                "blocked",
            ),
            (
                "r2-selected",
                route_v2_request(
                    risk_level="R2",
                    writer_route_slot="writer.c2",
                    availability={"openai/gpt-5.6-terra": "available"},
                ),
                "selected",
            ),
            (
                "r2-unknown",
                route_v2_request(
                    risk_level="R2",
                    writer_route_slot="writer.c2",
                    availability={},
                ),
                "unknown",
            ),
            (
                "r2-blocked",
                route_v2_request(
                    risk_level="R2",
                    writer_route_slot="writer.c2",
                    availability={"openai/gpt-5.6-terra": "unavailable"},
                    route_failure_evidence={
                        "openai/gpt-5.6-terra": ["valid-validator-rejection"],
                    },
                ),
                "blocked",
            ),
            (
                "r3-selected",
                route_v2_request(
                    risk_level="R3",
                    writer_route_slot="writer.c2",
                    availability={
                        "openai/gpt-5.6-terra": "available",
                        "openai/gpt-5.6-sol": "available",
                    },
                ),
                "selected",
            ),
            (
                "r3-unknown",
                route_v2_request(
                    risk_level="R3",
                    writer_route_slot="writer.c2",
                    availability={
                        "openai/gpt-5.6-terra": "unknown",
                        "openai/gpt-5.6-sol": "available",
                    },
                ),
                "unknown",
            ),
            (
                "r3-blocked",
                route_v2_request(
                    risk_level="R3",
                    writer_route_slot="writer.c2",
                    availability={
                        "openai/gpt-5.6-terra": "unavailable",
                        "openai/gpt-5.6-sol": "available",
                    },
                    route_failure_evidence={
                        "openai/gpt-5.6-terra": EVIDENCE[:1],
                    },
                ),
                "blocked",
            ),
        )
        with temporary_project() as project:
            for label, request, expected_status in cases:
                with self.subTest(label=label):
                    request_path = project / f"{label}.json"
                    request_path.write_text(json.dumps(request), encoding="utf-8")
                    result = self.run_cli("resolve", "--request", str(request_path))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    decision = json.loads(result.stdout)
                    self.assertEqual(decision["decision_status"], expected_status)
                    assert_v2_decision_matches_schema(self, decision)

    def test_cli_rejects_v2_request_with_mismatched_profile_version(self):
        with temporary_project() as project:
            request_path = project / "version-mismatch.json"
            request_path.write_text(
                json.dumps(route_v2_request(profile_id=PROFILE_ID)),
                encoding="utf-8",
            )
            result = self.run_cli("resolve", "--request", str(request_path))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("ERROR:", result.stderr)
            with self.assertRaises(json.JSONDecodeError):
                json.loads(result.stderr)

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
