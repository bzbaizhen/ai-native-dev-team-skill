import ast
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
PROFILE_ID = "custom-v1"
NEW_PROFILE_ID = "gpt6"
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
    resolve_route as _resolve_route,
    validate_profile,
    validate_profile_v2,
    validate_profile_versioned,
    validate_route_request,
    validate_route_request_v2,
)
from router_config import config_digest, validate_config  # noqa: E402
sys.path.insert(0, str(ROOT / "tests"))


def custom_v1_profile(profile_id="custom-v1"):
    """Independent project-only v1 fixture; never derives old semantics from v2."""
    profile = json.loads((ROOT / "tests/fixtures/custom-v1.json").read_text(encoding="utf-8"))
    profile["profile_id"] = profile_id
    return profile


_DEFAULT_V1_CONTEXT = None


def resolve_route(request, **kwargs):
    """Use the class-scoped temporary v1 fixture for legacy route tests."""

    if (
        _DEFAULT_V1_CONTEXT is not None
        and request.get("router_api_version") == "route/v1"
        and request.get("profile_id") == PROFILE_ID
        and not kwargs
    ):
        return _resolve_route(
            request,
            cwd=_DEFAULT_V1_CONTEXT["project"],
            config_path=_DEFAULT_V1_CONTEXT["config"],
        )
    return _resolve_route(request, **kwargs)


with redirect_stdout(StringIO()):
    from validate_skill import validate_model_router_bundle  # noqa: E402


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
        testcase.assertEqual(decision["validation_mode"], "single")


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
        metadata = (SKILL_DIR / "agents/openai.yaml").read_text(encoding="utf-8")
        for term in ("name: ai-native-model-router", "version: 0.5.1", "author: bzbaizhen, Hermes Agent", "license: MIT", "ai_native_model_router.config_path", "default: .ai-native/model-router.json"):
            self.assertIn(term, skill)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$ai-native-model-router", metadata)

    def test_progressive_disclosure_links_every_required_resource(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        links = set(re.findall(r"\]\(([^)#]+)", skill))
        self.assertEqual(links, {"references/interface.md", "references/configuration.md", "references/provider-evidence.md", "references/operating-rules.md"})
        for target in links:
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
            mutated = original.replace("version: 0.5.1", "version: 99.0.0")
            self.assertNotEqual(mutated, original)
            skill_path.write_text(mutated, encoding="utf-8")
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
            config_path.write_text(config.replace("project-router-v2-2026-09-23", "wrong-config"), encoding="utf-8")
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
            {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-6-astra", "gpt-6-luna", "gpt-6.1-sol"},
        )
        for model, reasoning in {
            "gpt-5.6-luna": ["max"], "gpt-5.6-terra": ["max"],
            "gpt-6-astra": ["medium"], "gpt-6-luna": ["max"],
            "gpt-6.1-sol": ["low", "medium", "high"],
        }.items():
            self.assertEqual(catalog["providers"]["openai"]["models"][model]["reasoning"], reasoning)
            self.assertEqual(catalog["providers"]["openai"]["models"][model]["reasoning_delivery"], "explicit")
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

    def test_bundled_profile_has_current_routes_and_no_external_high_volume(self):
        profile = load_profile(NEW_PROFILE_ID)
        self.assertEqual(set(profile["slots"]), {"control-plane", "writer.c0-batch", "writer.c1", "writer.c2", "writer.c3", "validator.assurance"})
        self.assertFalse(profile["default_active"])
        self.assertEqual(profile["activation"], "explicit-owner-selection")
        self.assertEqual(profile["evidence_date"], "2026-10-02")
        for risk, effort in (("R1", "low"), ("R2", "medium"), ("R3", "high")):
            self.assertEqual(profile["slots"]["validator.assurance"]["routes_by_risk"][risk], [{"provider": "openai", "model": "gpt-6.1-sol", "reasoning": effort, "reasoning_delivery": "explicit"}])
        self.assertEqual(profile["slots"]["validator.assurance"]["accepted_route_failure_evidence"], EVIDENCE)
        self.assertEqual(profile["slots"]["validator.assurance"]["exhaustion_action"], "blocked-owner")

    def test_profile_mutations_and_catalog_drift_fail_closed(self):
        profile = load_profile(NEW_PROFILE_ID)
        for mutation in (
            lambda p: p["slots"]["writer.c1"]["primary"].update(model="unknown-model"),
            lambda p: p["slots"]["writer.c1"].update(extra=True),
            lambda p: p["slots"]["writer.c1"].update(default=True),
            lambda p: p["slots"]["writer.c1"].update(
                independent_validator_source="other-source"
            ),
        ):
            candidate = copy.deepcopy(profile)
            mutation(candidate)
            with self.assertRaises(ValueError):
                validate_profile_v2(candidate, load_catalog())

    def test_new_profile_asset_has_exact_assurance_routes(self):
        profile = load_profile(NEW_PROFILE_ID)
        self.assertEqual(set(profile["slots"]), {"control-plane", "writer.c0-batch", "writer.c1", "writer.c2", "writer.c3", "validator.assurance"})
        self.assertFalse(profile["default_active"])
        self.assertEqual(profile["activation"], "explicit-owner-selection")
        self.assertEqual(profile["evidence_date"], "2026-10-02")
        for risk, effort in (("R1", "low"), ("R2", "medium"), ("R3", "high")):
            self.assertEqual(profile["slots"]["validator.assurance"]["routes_by_risk"][risk], [{"provider": "openai", "model": "gpt-6.1-sol", "reasoning": effort, "reasoning_delivery": "explicit"}])
        self.assertEqual(profile["slots"]["validator.assurance"]["accepted_route_failure_evidence"], EVIDENCE)
        self.assertEqual(profile["slots"]["validator.assurance"]["exhaustion_action"], "blocked-owner")

    def test_new_profile_is_loadable_as_a_bundled_profile(self):
        self.assertEqual(load_profile(NEW_PROFILE_ID)["profile_id"], NEW_PROFILE_ID)
        profile = load_profile(NEW_PROFILE_ID)
        with self.assertRaises(ValueError):
            validate_profile(profile, load_catalog())
        self.assertEqual(validate_profile_v2(profile, load_catalog()), profile)
        self.assertEqual(validate_profile_versioned(profile, load_catalog()), profile)


class ResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _DEFAULT_V1_CONTEXT
        project = ROOT / "tests" / f".model-router-v1-{uuid.uuid4().hex}"
        project.mkdir()
        profile_dir = project / "profiles"
        profile_dir.mkdir()
        (profile_dir / f"{PROFILE_ID}.json").write_text(
            json.dumps(custom_v1_profile()), encoding="utf-8"
        )
        config = {
            "schema_version": 1,
            "router_api_version": "route/v1",
            "config_id": "default-v1-test-config",
            "active_profile": PROFILE_ID,
            "project_profile_dirs": ["profiles"],
            "updated_reason": "bounded route/v1 test fixture",
        }
        config_path = project / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        _DEFAULT_V1_CONTEXT = {"project": project, "config": config_path}

    @classmethod
    def tearDownClass(cls):
        global _DEFAULT_V1_CONTEXT
        if _DEFAULT_V1_CONTEXT is not None:
            shutil.rmtree(_DEFAULT_V1_CONTEXT["project"])
            _DEFAULT_V1_CONTEXT = None

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


    def test_v2_request_and_config_profile_versions_cannot_be_mixed(self):
        with self.assertRaises(ValueError):
            resolve_route(route_v2_request(profile_id=PROFILE_ID))
        with self.assertRaises(ValueError):
            resolve_route(route_request(profile_id=NEW_PROFILE_ID))


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
                    slot: {"primary": {"provider": "openai", "model": "gpt-6.1-sol", "reasoning": "high", "reasoning_delivery": "explicit"}}
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
                    availability={"openai/gpt-6.1-sol": "available"},
                ), cwd=project, config_path=config_path
            )
            self.assertEqual(decision["selected_route"]["model"], "gpt-6.1-sol")
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
        profile = custom_v1_profile()
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
            bundled = SKILL_DIR / "assets" / "profiles" / f"{NEW_PROFILE_ID}.json"
            changed = json.loads(bundled.read_text(encoding="utf-8"))
            changed["evidence_date"] = "2099-01-01"
            candidate = profile_dir / f"{NEW_PROFILE_ID}.json"
            candidate.write_text(json.dumps(changed), encoding="utf-8")

            class SameDigest:
                def hexdigest(self):
                    return "0" * 64

            with patch("hashlib.sha256", return_value=SameDigest()):
                with self.assertRaises(ValueError):
                    load_profile(NEW_PROFILE_ID, project_root=project, project_profile_dirs=[".ai-native/profiles"])

    def test_collision_blocks_changed_bundled_profile(self):
        with temporary_project() as project:
            profile_dir = project / ".ai-native" / "profiles"
            profile_dir.mkdir(parents=True)
            bundled = SKILL_DIR / "assets" / "profiles" / f"{NEW_PROFILE_ID}.json"
            changed = json.loads(bundled.read_text(encoding="utf-8"))
            changed["evidence_date"] = "2099-01-01"
            (profile_dir / f"{NEW_PROFILE_ID}.json").write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_profile(NEW_PROFILE_ID, project_root=project, project_profile_dirs=[".ai-native/profiles"])

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

    def test_help_and_module_docstring_describe_versioned_nonexecuting_resolution_contracts(self):
        module_path = SKILL_DIR / "scripts" / "resolve_route.py"
        source = module_path.read_text(encoding="utf-8")
        module_docstring = ast.get_docstring(ast.parse(source))
        self.assertIsNotNone(module_docstring)
        for version in ("route/v1", "route/v2"):
            with self.subTest(surface="module", version=version):
                self.assertIn(version, module_docstring)
        self.assertRegex(module_docstring.casefold(), r"does\s+not\s+(?s:.*?)host")
        self.assertIn("provider", module_docstring.casefold())

        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for version in ("route/v1", "route/v2"):
            with self.subTest(surface="help", version=version):
                self.assertIn(version, result.stdout)
        self.assertRegex(result.stdout.casefold(), r"without executing")
        self.assertIn("host", result.stdout.casefold())
        self.assertIn("provider", result.stdout.casefold())

    def test_list_validate_and_resolve_commands_emit_json(self):
        listed = self.run_cli("list-profiles")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(json.loads(listed.stdout)["profiles"], [NEW_PROFILE_ID])
        validated = self.run_cli("validate-profile", "--profile", NEW_PROFILE_ID)
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertEqual(json.loads(validated.stdout)["profile_id"], NEW_PROFILE_ID)
        with temporary_project() as project:
            request_path = project / "request.json"
            request_path.write_text(
                json.dumps(
                    route_v2_request(
                        route_slot="writer.c1",
                        writer_route_slot=None,
                        risk_level=None,
                        writer_identity=None,
                        candidate_id=None,
                        availability={"openai/gpt-6.1-sol": "available"},
                    )
                ),
                encoding="utf-8",
            )
            resolved = self.run_cli("resolve", "--request", str(request_path))
            self.assertEqual(resolved.returncode, 0, resolved.stderr)
            self.assertEqual(json.loads(resolved.stdout)["decision_status"], "selected")


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

class CurrentAssuranceTests(unittest.TestCase):
    def test_v2_rejects_invalid_availability_and_route_evidence(self):
        for availability in ({"openai/gpt-6.1-sol": "broken"}, {"openai/gpt-6.1-sol": True}, {"openai/gpt-6.1-sol": None}):
            with self.assertRaises(ValueError):
                validate_route_request_v2(route_v2_request(availability=availability))
        for evidence in ({"openai:gpt-6.1-sol": EVIDENCE}, {"openai/gpt-6.1-sol": "model-not-found"}, {"openai/gpt-6.1-sol": [1]}):
            with self.assertRaises(ValueError):
                validate_route_request_v2(route_v2_request(route_failure_evidence=evidence))

    def test_current_risk_availability_and_evidence_matrix(self):
        for risk, effort in (("R1", "low"), ("R2", "medium"), ("R3", "high")):
            for state, expected in (("available", "selected"), ("unknown", "unknown"), ("unavailable", "blocked")):
                for evidence in ([], EVIDENCE[:1], ["subjective-quality"], ["cost-preference"], ["validator-rejection"]):
                    with self.subTest(risk=risk, state=state, evidence=evidence):
                        request = route_v2_request(risk_level=risk, availability={"openai/gpt-6.1-sol": state}, route_failure_evidence={"openai/gpt-6.1-sol": evidence})
                        decision = _resolve_route(request)
                        assert_v2_decision_matches_schema(self, decision)
                        self.assertEqual(decision["decision_status"], expected)
                        self.assertEqual(decision["validation_mode"], "single")
                        self.assertEqual(decision["escalation_used"], state == "unavailable" and evidence == EVIDENCE[:1])
                        self.assertEqual(len(decision["selected_routes"]), 1 if expected == "selected" else 0)
                        if expected == "selected":
                            route = decision["selected_routes"][0]
                            self.assertEqual((route["model"], route["reasoning"]), ("gpt-6.1-sol", effort))

    def test_other_models_or_wrong_evidence_keys_cannot_substitute(self):
        for risk in ("R1", "R2", "R3"):
            request = route_v2_request(risk_level=risk, availability={"openai/gpt-5.6-luna":"available", "zai/glm-5.3":"available", "deepseek/deepseek-v4-pro":"available"}, route_failure_evidence={"openai/gpt-5.6-luna": EVIDENCE[:1]})
            decision = _resolve_route(request)
            self.assertEqual(decision["decision_status"], "unknown")
            self.assertEqual(decision["selected_routes"], [])

    def test_same_model_identity_is_reported_and_not_independence(self):
        for provider in ("openai", "custom"):
            request = route_v2_request(availability={"openai/gpt-6.1-sol":"available"}, writer_identity={"provider":provider, "runtime_provider":"custom", "model":"gpt-6.1-sol"})
            decision = _resolve_route(request)
            self.assertTrue(decision["same_model_as_writer"])
            self.assertEqual(decision["enforcement_status"], "not-executed")

    def test_cli_risk_state_matrix_is_nonexecuting(self):
        for risk in ("R1", "R2", "R3"):
            for state, expected in (("available", "selected"), ("unknown", "unknown"), ("unavailable", "blocked")):
                request = route_v2_request(risk_level=risk, availability={"openai/gpt-6.1-sol":state})
                result = subprocess.run([sys.executable, str(SKILL_DIR / "scripts/resolve_route.py"), "resolve", "--request", json.dumps(request)], cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                decision = json.loads(result.stdout)
                self.assertEqual(decision["decision_status"], expected)
                assert_v2_decision_matches_schema(self, decision)
