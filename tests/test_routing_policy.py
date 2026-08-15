import copy
import importlib.util
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "bootstrap-ai-native-dev-team"
SCENARIOS_PATH = ROOT / "tests" / "routing-scenarios.json"
METRICS_SCHEMA_PATH = (
    SKILL_DIR / "references" / "metrics-event.schema.json"
)
METRICS_SCRIPT_PATH = SKILL_DIR / "scripts" / "team_metrics.py"

TEAM_METRICS_SPEC = importlib.util.spec_from_file_location(
    "routing_policy_team_metrics", METRICS_SCRIPT_PATH
)
if TEAM_METRICS_SPEC is None or TEAM_METRICS_SPEC.loader is None:
    raise RuntimeError("cannot load team_metrics.py for read-only profile inspection")
TEAM_METRICS = importlib.util.module_from_spec(TEAM_METRICS_SPEC)
TEAM_METRICS_SPEC.loader.exec_module(TEAM_METRICS)


CONTROLLED_SHAPES = {
    "material_behavior_change",
    "interface_change",
    "dependency_change",
    "data_change",
    "security_change",
    "concurrency",
    "production_action",
    "public_action",
}
AUDIT_REQUESTS = {
    "qualify this stable version": "stable-qualification",
    "formally compare efficiency": "formal-efficiency",
    "qualify the historical baseline": "historical-baseline",
    "freeze external evidence": "evidence-freeze",
}
CANONICAL_LAYERS = {"core", "controlled", "release-audit"}
ROUTES = {"no-delegation", "single-worker", "task-cell", "team-required"}
CAPABILITIES = {"main-agent", "economy", "standard", "advanced", "frontier"}
REASONING = {"current", "low", "medium", "high", "max"}
STRING_FIELDS = {
    "name",
    "complexity",
    "risk",
    "shape",
    "request",
    "route",
    "layer",
    "profile",
    "capability",
    "reasoning",
}
BOOL_FIELDS = {
    "material_behavior_change",
    "interface_change",
    "dependency_change",
    "data_change",
    "security_change",
    "concurrency",
    "production_action",
    "public_action",
    "delegated",
    "independent_validator",
    "owner_approval",
    "worktree_required",
    "ledger_required",
    "release_audit",
    "explicit_release_audit",
    "evidence_reuse_allowed",
    "rerun_trigger",
}
REQUIRED_FIELDS = STRING_FIELDS | BOOL_FIELDS | {"worker_skill_loaded"}


def controlled_trigger(case: dict) -> bool:
    return (
        case["material_behavior_change"]
        or case["complexity"] in {"C2", "C3"}
        or case["risk"] in {"R2", "R3"}
        or any(case[key] for key in CONTROLLED_SHAPES - {"material_behavior_change"})
    )


def explicit_release_audit(case: dict) -> bool:
    return case["explicit_release_audit"] and case["request"] in AUDIT_REQUESTS


def expected_layer(case: dict) -> str:
    if explicit_release_audit(case):
        return "release-audit"
    if controlled_trigger(case):
        return "controlled"
    return "core"


def expected_capability(case: dict) -> tuple[str, str]:
    if case["complexity"] == "C0":
        return ("economy", "low") if case["delegated"] else ("main-agent", "current")
    return {
        "C1": ("standard", "medium"),
        "C2": ("advanced", "high"),
        "C3": ("frontier", "max"),
    }[case["complexity"]]


def expected_profile(case: dict) -> str:
    layer = expected_layer(case)
    if layer == "core":
        return "lean"
    if layer == "release-audit" or case["complexity"] == "C3" or case["risk"] == "R3":
        return "strict"
    return "controlled"


def validate_case(
    case: dict,
    schema_profiles: set[str],
    runtime_profiles: set[str],
) -> None:
    """Validate one scenario against the canonical policy and live legacy enums."""
    assert set(case) == REQUIRED_FIELDS, f"field set mismatch: {case.get('name')}"
    for field in STRING_FIELDS:
        value = case[field]
        assert type(value) is str and value.strip(), f"{field} must be a non-empty string"
    for field in BOOL_FIELDS:
        assert type(case[field]) is bool, f"{field} must be a bool"
    if case["delegated"]:
        assert type(case["worker_skill_loaded"]) is bool, (
            "delegated Worker context must report a bool"
        )
    else:
        assert case["worker_skill_loaded"] is None, (
            "non-Worker scenario must not claim Worker Skill state"
        )

    assert case["complexity"] in {"C0", "C1", "C2", "C3"}
    assert case["risk"] in {"R0", "R1", "R2", "R3"}
    assert case["layer"] in CANONICAL_LAYERS
    assert case["route"] in ROUTES
    assert case["capability"] in CAPABILITIES
    assert case["reasoning"] in REASONING
    assert case["profile"] in schema_profiles
    assert case["profile"] in runtime_profiles

    assert case["layer"] == expected_layer(case), "layer contradicts policy predicates"
    assert case["profile"] == expected_profile(case), "legacy profile encoding is wrong"
    assert (case["release_audit"] is True) == (case["layer"] == "release-audit")
    assert (case["explicit_release_audit"] is True) == explicit_release_audit(case)
    assert (case["capability"], case["reasoning"]) == expected_capability(case)

    if case["layer"] == "core":
        assert case["route"] in {"no-delegation", "single-worker"}
        assert case["route"] == ("single-worker" if case["delegated"] else "no-delegation")
        assert case["independent_validator"] is False
        assert case["worktree_required"] is False
        assert case["ledger_required"] is False
    elif case["layer"] == "controlled":
        assert case["route"] in {"task-cell", "team-required"}
        assert case["independent_validator"] is True
        assert case["release_audit"] is False
    else:
        assert case["route"] == "team-required"
        assert case["independent_validator"] is True
        assert case["ledger_required"] is True

    if case["route"] == "task-cell":
        assert case["independent_validator"] is True
    if case["risk"] == "R3" or case["layer"] == "release-audit":
        assert case["owner_approval"] is True
    if case["delegated"]:
        assert case["worker_skill_loaded"] is False
    if case["rerun_trigger"]:
        assert case["evidence_reuse_allowed"] is False
    if case["evidence_reuse_allowed"]:
        assert case["rerun_trigger"] is False


class RoutingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
        cls.by_name = {case["name"]: case for case in cls.scenarios}
        schema = json.loads(METRICS_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.schema_profiles = set(
            schema["properties"]["governance_profile"]["enum"]
        )
        cls.runtime_profiles = set(TEAM_METRICS.PROFILES)

    def test_matrix_has_complete_shape_and_expected_layers(self) -> None:
        self.assertGreaterEqual(len(self.scenarios), 14)
        self.assertEqual(self.schema_profiles, {"lean", "controlled", "strict"})
        self.assertEqual(self.runtime_profiles, self.schema_profiles)
        for case in self.scenarios:
            validate_case(case, self.schema_profiles, self.runtime_profiles)

    def assert_rejected(self, case: dict, mutate, label: str) -> None:
        candidate = copy.deepcopy(case)
        mutate(candidate)
        with self.assertRaises(AssertionError, msg=label):
            validate_case(candidate, self.schema_profiles, self.runtime_profiles)

    def test_legacy_profile_contract_is_live_not_self_described(self) -> None:
        self.assertEqual(self.schema_profiles, set(TEAM_METRICS.PROFILES))
        for case in self.scenarios:
            self.assertIn(case["profile"], self.schema_profiles)
            self.assertEqual(case["profile"], expected_profile(case), case["name"])

    def test_negative_mutation_probes_fail_closed(self) -> None:
        core = self.by_name["C1/R1 non-material isolated work"]
        material = self.by_name["material C1/R1 behavior change"]
        public = self.by_name["ordinary public deployment"]
        worker = self.by_name["C0/R1 deterministic batch"]
        c1_r3 = self.by_name["C1/R3 security-boundary change"]

        self.assert_rejected(core, lambda case: case.pop("layer"), "missing layer")
        self.assert_rejected(
            core,
            lambda case: case.update(delegated="false"),
            "string bool",
        )
        self.assert_rejected(
            core,
            lambda case: case.update(independent_validator=0),
            "integer bool",
        )
        self.assert_rejected(
            material,
            lambda case: case.update(layer="core", profile="lean"),
            "self-consistent but wrong layer/profile",
        )
        self.assert_rejected(
            public,
            lambda case: case.update(
                layer="release-audit",
                profile="strict",
                release_audit=True,
                explicit_release_audit=True,
            ),
            "ordinary publication spoofed as Release Audit",
        )
        self.assert_rejected(
            public,
            lambda case: case.update(
                request="audit this release",
                layer="release-audit",
                profile="strict",
                release_audit=True,
                explicit_release_audit=True,
            ),
            "non-whitelist audit wording",
        )
        self.assert_rejected(
            worker,
            lambda case: case.update(worker_skill_loaded=True),
            "Worker loaded complete Skill",
        )
        self.assert_rejected(
            c1_r3,
            lambda case: case.update(capability="frontier", reasoning="max"),
            "risk raised implementation capability",
        )

    def test_core_minimums_and_worker_context(self) -> None:
        micro = self.by_name["C0/R0 main-agent micro work"]
        self.assertEqual(micro["route"], "no-delegation")
        self.assertFalse(micro["delegated"])
        self.assertFalse(micro["independent_validator"])
        self.assertFalse(micro["worktree_required"])
        self.assertFalse(micro["ledger_required"])

        non_material = self.by_name["C1/R1 non-material isolated work"]
        self.assertEqual(non_material["layer"], "core")
        self.assertFalse(non_material["worktree_required"])
        self.assertFalse(non_material["ledger_required"])
        self.assertFalse(non_material["independent_validator"])

        for case in self.scenarios:
            if case["delegated"]:
                self.assertFalse(
                    case["worker_skill_loaded"],
                    f"delegated Worker loaded complete Skill: {case['name']}",
                )

    def test_material_and_risk_gates(self) -> None:
        material = self.by_name["material C1/R1 behavior change"]
        self.assertEqual(material["layer"], "controlled")
        self.assertEqual(material["route"], "task-cell")
        self.assertTrue(material["independent_validator"])

        c1_r3 = self.by_name["C1/R3 security-boundary change"]
        self.assertEqual((c1_r3["capability"], c1_r3["reasoning"]), ("standard", "medium"))
        self.assertTrue(c1_r3["owner_approval"])
        self.assertTrue(c1_r3["independent_validator"])

        c3_r1 = self.by_name["C3/R1 architecture refactor"]
        self.assertEqual(c3_r1["layer"], "controlled")
        self.assertEqual((c3_r1["capability"], c3_r1["reasoning"]), ("frontier", "max"))
        self.assertFalse(c3_r1["release_audit"])
        self.assertTrue(c3_r1["independent_validator"])

    def test_ordinary_public_actions_do_not_activate_release_audit(self) -> None:
        for name in ("ordinary public deployment", "ordinary publication without audit"):
            case = self.by_name[name]
            self.assertEqual(case["layer"], "controlled")
            self.assertEqual(case["risk"], "R3")
            self.assertFalse(case["release_audit"])
            self.assertFalse(case["explicit_release_audit"])
            self.assertTrue(case["owner_approval"])
            self.assertTrue(case["independent_validator"])
            self.assertFalse(case["ledger_required"])

    def test_only_explicit_release_audit_requests_activate_audit(self) -> None:
        explicit = [case for case in self.scenarios if case["release_audit"]]
        self.assertEqual(
            {AUDIT_REQUESTS[case["request"]] for case in explicit},
            set(AUDIT_REQUESTS.values()),
        )
        for case in explicit:
            self.assertTrue(explicit_release_audit(case), case["name"])
            self.assertEqual(case["layer"], "release-audit")
            self.assertTrue(case["ledger_required"])
            self.assertTrue(case["owner_approval"])
            self.assertTrue(case["independent_validator"])

    def test_metrics_are_opt_in_and_evidence_reuse_is_fail_closed(self) -> None:
        ordinary = [case for case in self.scenarios if not case["release_audit"]]
        self.assertTrue(ordinary)
        self.assertTrue(all(not case["ledger_required"] for case in ordinary))

        reusable = self.by_name["unchanged evidence carry-forward"]
        self.assertTrue(reusable["evidence_reuse_allowed"])
        self.assertFalse(reusable["rerun_trigger"])

        rerun = self.by_name["changed generated input rerun"]
        self.assertFalse(rerun["evidence_reuse_allowed"])
        self.assertTrue(rerun["rerun_trigger"])

    def test_default_skill_selects_canonical_references_without_release_protocol(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for target in (
            "references/routing-and-topologies.md",
            "references/core.md",
            "references/controlled.md",
            "references/release-audit.md",
            "references/metrics.md",
        ):
            self.assertIn(f"]({target})", skill)

        body = skill.split("---", 2)[2]
        for detail in (
            "release-anchor-closure.schema.json",
            "release-registration-receipt.schema.json",
            "release-trial-manifest.schema.json",
            "release-source-registry.schema.json",
            "release-v1-baseline-evidence.schema.json",
        ):
            self.assertNotIn(detail, body)
        self.assertNotIn("Anchor history", body)

    def test_legacy_paths_are_compatibility_pointers(self) -> None:
        pointers = {
            "governance-lean.md": "core.md",
            "governance-controlled.md": "controlled.md",
            "governance-strict.md": "controlled.md",
            "team-governance-template.zh-CN.md": "core.md",
        }
        for legacy, canonical in pointers.items():
            text = (SKILL_DIR / "references" / legacy).read_text(encoding="utf-8")
            self.assertIn(canonical, text, legacy)
            self.assertLessEqual(len(text.splitlines()), 40, legacy)

    def test_default_skill_local_links_resolve(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", skill):
            if target.startswith(("http://", "https://", "#")):
                continue
            self.assertTrue((SKILL_DIR / target).exists(), target)


if __name__ == "__main__":
    unittest.main()
