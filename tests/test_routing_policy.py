import copy
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "bootstrap-ai-native-dev-team"
SCENARIOS_PATH = ROOT / "tests" / "routing-scenarios.json"
COST_POLICY_CASES_PATH = ROOT / "tests" / "cost-routing-policy-cases.json"

CONTROLLED_SHAPES = {
    "material_behavior",
    "cross_file",
    "architecture",
    "interface_change",
    "security_change",
    "public_action",
    "multi_repository",
}
LAYERS = {"core", "controlled"}
ROUTES = {"no-delegation", "single-worker", "task-cell", "team-required"}
CAPABILITIES = {"main-agent", "economy", "standard", "advanced", "frontier"}
REASONING = {"current", "low", "medium", "high", "max"}
STRING_FIELDS = {
    "name", "complexity", "risk", "shape", "route", "layer",
    "capability", "reasoning",
}
BOOL_FIELDS = {
    "delegated", "independent_validator", "owner_approval",
    "worktree_required", "evidence_reuse_allowed", "rerun_trigger",
}
REQUIRED_FIELDS = STRING_FIELDS | BOOL_FIELDS
DIRECT_STRING_FIELDS = {"direct_work_type"}
DIRECT_BOOL_FIELDS = {
    "deterministic",
    "low_risk",
    "single_file_scope",
    "material_effect",
    "interface_effect",
    "dependency_effect",
    "data_effect",
    "security_effect",
    "concurrency_effect",
    "production_effect",
    "public_effect",
    "debugging_loop",
    "test_authoring",
}
DIRECT_INT_FIELDS = {"deterministic_verification_count"}
DIRECT_EXECUTION_FIELDS = DIRECT_STRING_FIELDS | DIRECT_BOOL_FIELDS | DIRECT_INT_FIELDS
COST_POLICY_FIELDS = {
    "name",
    "main_agent_takeover",
    "writer_path_status",
    "writer_failure_evidence",
    "safe_reslice_possible",
    "explicit_high_cost_takeover_authorization",
    "takeover_reason",
    "runtime_mapping_observed",
    "mapped_to_lower_cost_tier",
    "cost_saving_claim",
}


def controlled_trigger(case: dict) -> bool:
    return (
        case["complexity"] in {"C2", "C3"}
        or case["risk"] in {"R2", "R3"}
        or case["shape"] in CONTROLLED_SHAPES
    )


def expected_layer(case: dict) -> str:
    return "controlled" if controlled_trigger(case) else "core"


def expected_capability(case: dict) -> tuple[str, str]:
    if case["complexity"] == "C0":
        return ("economy", "low") if case["delegated"] else ("main-agent", "current")
    return {
        "C1": ("standard", "medium"),
        "C2": ("advanced", "high"),
        "C3": ("frontier", "max"),
    }[case["complexity"]]


def has_no_disqualifying_effect(case: dict) -> bool:
    return not any(
        case[field]
        for field in {
            "material_effect",
            "interface_effect",
            "dependency_effect",
            "data_effect",
            "security_effect",
            "concurrency_effect",
            "production_effect",
            "public_effect",
        }
    )


def is_strict_read_only_direct(case: dict) -> bool:
    return (
        case["direct_work_type"] == "read-only-control-plane"
        and case["complexity"] == "C0"
        and case["risk"] == "R0"
        and case["shape"] == "micro"
        and case["low_risk"] is True
        and case["single_file_scope"] is False
        and case["debugging_loop"] is False
        and case["test_authoring"] is False
        and case["deterministic_verification_count"] == 0
        and has_no_disqualifying_effect(case)
        and not controlled_trigger(case)
    )


def is_strict_tiny_edit_direct(case: dict) -> bool:
    return (
        case["direct_work_type"] == "tiny-edit"
        and case["complexity"] == "C0"
        and case["risk"] == "R1"
        and case["shape"] == "strict_tiny_edit"
        and case["deterministic"] is True
        and case["low_risk"] is True
        and case["single_file_scope"] is True
        and case["debugging_loop"] is False
        and case["test_authoring"] is False
        and case["deterministic_verification_count"] == 1
        and has_no_disqualifying_effect(case)
        and not controlled_trigger(case)
    )


def validate_cost_policy_case(case: dict) -> None:
    assert set(case) == COST_POLICY_FIELDS, f"cost-policy field set mismatch: {case.get('name')}"
    assert type(case["name"]) is str and case["name"].strip()
    assert case["writer_path_status"] in {"available", "unavailable", "repeated-failure"}
    for field in {
        "main_agent_takeover",
        "safe_reslice_possible",
        "explicit_high_cost_takeover_authorization",
        "runtime_mapping_observed",
        "mapped_to_lower_cost_tier",
        "cost_saving_claim",
    }:
        assert type(case[field]) is bool, field
    for field in {"writer_failure_evidence", "takeover_reason"}:
        value = case[field]
        assert value is None or (type(value) is str and value.strip()), field

    repeated_failure_with_evidence = (
        case["writer_path_status"] == "repeated-failure"
        and case["writer_failure_evidence"] is not None
    )
    if case["writer_path_status"] == "repeated-failure":
        assert repeated_failure_with_evidence
    if case["main_agent_takeover"]:
        assert case["writer_path_status"] == "unavailable" or repeated_failure_with_evidence
        assert case["safe_reslice_possible"] is False
        assert case["explicit_high_cost_takeover_authorization"] is True
        assert case["takeover_reason"] is not None
    if case["mapped_to_lower_cost_tier"]:
        assert case["runtime_mapping_observed"] is True
    if case["cost_saving_claim"]:
        assert case["runtime_mapping_observed"] is True
        assert case["mapped_to_lower_cost_tier"] is True


def validate_case(case: dict) -> None:
    expected_fields = REQUIRED_FIELDS | (
        DIRECT_EXECUTION_FIELDS if not case.get("delegated") else set()
    )
    assert set(case) == expected_fields, f"field set mismatch: {case.get('name')}"
    for field in STRING_FIELDS:
        assert type(case[field]) is str and case[field].strip(), field
    for field in BOOL_FIELDS:
        assert type(case[field]) is bool, field
    if not case["delegated"]:
        for field in DIRECT_STRING_FIELDS:
            assert type(case[field]) is str and case[field].strip(), field
        for field in DIRECT_BOOL_FIELDS:
            assert type(case[field]) is bool, field
        for field in DIRECT_INT_FIELDS:
            assert type(case[field]) is int and case[field] >= 0, field

    assert case["complexity"] in {"C0", "C1", "C2", "C3"}
    assert case["risk"] in {"R0", "R1", "R2", "R3"}
    assert case["layer"] in LAYERS
    assert case["route"] in ROUTES
    assert case["capability"] in CAPABILITIES
    assert case["reasoning"] in REASONING
    assert case["layer"] == expected_layer(case)
    assert (case["capability"], case["reasoning"]) == expected_capability(case)

    if case["layer"] == "core":
        assert case["route"] in {"no-delegation", "single-worker"}
        assert case["route"] == ("single-worker" if case["delegated"] else "no-delegation")
        assert not case["independent_validator"]
        assert not case["worktree_required"]
    else:
        assert case["route"] in {"task-cell", "team-required"}
        assert case["delegated"]
        assert case["independent_validator"]
        assert case["worktree_required"]

    if not case["delegated"]:
        assert is_strict_read_only_direct(case) or is_strict_tiny_edit_direct(case)
    assert case["owner_approval"] == (case["risk"] == "R3")
    assert not (case["evidence_reuse_allowed"] and case["rerun_trigger"])


class RoutingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
        cls.by_name = {case["name"]: case for case in cls.scenarios}
        cls.cost_policy_cases = json.loads(COST_POLICY_CASES_PATH.read_text(encoding="utf-8"))
        cls.cost_by_name = {case["name"]: case for case in cls.cost_policy_cases}

    def test_matrix_shape_and_policy(self) -> None:
        self.assertGreaterEqual(len(self.scenarios), 13)
        self.assertEqual(len(self.by_name), len(self.scenarios))
        for case in self.scenarios:
            validate_case(case)

    def assert_rejected(self, case: dict, mutate, label: str) -> None:
        candidate = copy.deepcopy(case)
        mutate(candidate)
        with self.assertRaises(AssertionError, msg=label):
            validate_case(candidate)

    def assert_cost_policy_rejected(self, case: dict, mutate, label: str) -> None:
        candidate = copy.deepcopy(case)
        mutate(candidate)
        with self.assertRaises(AssertionError, msg=label):
            validate_cost_policy_case(candidate)

    def test_direct_tiny_edit_eligibility_mutations_fail_closed(self) -> None:
        tiny_edit = self.by_name["C0/R1 strict main-agent tiny edit"]
        eligibility = {
            "direct_work_type": "tiny-edit",
            "complexity": "C0",
            "risk": "R1",
            "shape": "strict_tiny_edit",
            "deterministic": True,
            "low_risk": True,
            "single_file_scope": True,
            "material_effect": False,
            "interface_effect": False,
            "dependency_effect": False,
            "data_effect": False,
            "security_effect": False,
            "concurrency_effect": False,
            "production_effect": False,
            "public_effect": False,
            "debugging_loop": False,
            "test_authoring": False,
            "deterministic_verification_count": 1,
        }
        for field, expected in eligibility.items():
            self.assertEqual(tiny_edit[field], expected, field)
            if type(expected) is bool:
                replacement = not expected
            elif type(expected) is int:
                replacement = expected + 1
            else:
                replacement = f"not-{expected}"
            self.assert_rejected(
                tiny_edit,
                lambda case, field=field, replacement=replacement: case.update(
                    {field: replacement}
                ),
                f"strict tiny-edit eligibility mutation: {field}",
            )

    def test_read_only_control_plane_lane_is_separate(self) -> None:
        read_only = self.by_name["C0/R0 main-agent micro work"]
        self.assertTrue(is_strict_read_only_direct(read_only))
        self.assertFalse(is_strict_tiny_edit_direct(read_only))
        self.assert_rejected(
            read_only,
            lambda case: case.update(direct_work_type="tiny-edit"),
            "read-only control-plane work cannot pose as a tiny edit",
        )

    def test_takeover_and_cost_claim_policy_fixtures(self) -> None:
        self.assertEqual(len(self.cost_policy_cases), 3)
        for case in self.cost_policy_cases:
            validate_cost_policy_case(case)

    def test_takeover_condition_mutations_fail_closed(self) -> None:
        unavailable = self.cost_by_name["authorized takeover when Writer path is unavailable"]
        repeated = self.cost_by_name["authorized takeover after evidenced repeated Writer failure"]
        self.assert_cost_policy_rejected(
            unavailable, lambda case: case.update(writer_path_status="available"),
            "Writer path still available",
        )
        self.assert_cost_policy_rejected(
            repeated, lambda case: case.update(writer_failure_evidence=None),
            "repeated failure lacks evidence",
        )
        self.assert_cost_policy_rejected(
            unavailable, lambda case: case.update(safe_reslice_possible=True),
            "safe re-slice exists",
        )
        self.assert_cost_policy_rejected(
            unavailable,
            lambda case: case.update(explicit_high_cost_takeover_authorization=False),
            "takeover lacks explicit higher-cost authorization",
        )
        self.assert_cost_policy_rejected(
            unavailable, lambda case: case.update(takeover_reason=None),
            "takeover reason is not recorded",
        )

    def test_cost_claim_condition_mutations_fail_closed(self) -> None:
        claim = self.cost_by_name["observed lower-cost execution mapping"]
        self.assert_cost_policy_rejected(
            claim, lambda case: case.update(runtime_mapping_observed=False),
            "runtime mapping was not observed",
        )
        self.assert_cost_policy_rejected(
            claim, lambda case: case.update(mapped_to_lower_cost_tier=False),
            "observed mapping is not to a lower-cost tier",
        )

    def test_negative_mutations_fail_closed(self) -> None:
        core = self.by_name["C1/R1 non-material isolated work"]
        batch = self.by_name["C0/R1 deterministic batch"]
        material = self.by_name["material C1/R1 behavior change"]
        public = self.by_name["ordinary public deployment"]
        c1_r3 = self.by_name["C1/R3 security-boundary change"]
        tiny_edit = self.by_name["C0/R1 strict main-agent tiny edit"]
        direct_fields = {
            field: tiny_edit[field] for field in DIRECT_EXECUTION_FIELDS
        }

        self.assert_rejected(core, lambda c: c.pop("layer"), "missing layer")
        self.assert_rejected(core, lambda c: c.update(delegated="false"), "string bool")
        self.assert_rejected(material, lambda c: c.update(layer="core"), "wrong layer")
        self.assert_rejected(
            material,
            lambda c: c.update(independent_validator=False),
            "material work lost independent validation",
        )
        self.assert_rejected(public, lambda c: c.update(layer="release-audit"), "removed layer")
        self.assert_rejected(
            c1_r3,
            lambda c: c.update(capability="frontier", reasoning="max"),
            "risk raised capability",
        )
        self.assert_rejected(
            c1_r3, lambda c: c.update(owner_approval=False), "missing owner approval",
        )
        self.assert_rejected(
            core,
            lambda c: c.update(
                direct_fields,
                route="no-delegation", delegated=False,
            ),
            "C1 implementation moved to the main agent",
        )
        self.assert_rejected(
            batch,
            lambda c: c.update(
                direct_fields,
                route="no-delegation", delegated=False,
                capability="main-agent", reasoning="current",
            ),
            "C0 mechanical batch moved to the main agent",
        )

    def test_complexity_and_risk_stay_independent(self) -> None:
        c1_r3 = self.by_name["C1/R3 security-boundary change"]
        self.assertEqual((c1_r3["capability"], c1_r3["reasoning"]), ("standard", "medium"))
        self.assertTrue(c1_r3["owner_approval"])

        c3_r1 = self.by_name["C3/R1 architecture refactor"]
        self.assertEqual((c3_r1["capability"], c3_r1["reasoning"]), ("frontier", "max"))
        self.assertFalse(c3_r1["owner_approval"])

    def test_release_and_public_actions_are_controlled_r3(self) -> None:
        case = self.by_name["ordinary public deployment"]
        self.assertEqual(case["layer"], "controlled")
        self.assertEqual(case["risk"], "R3")
        self.assertTrue(case["owner_approval"])
        self.assertTrue(case["independent_validator"])

    def test_evidence_reuse_is_fail_closed(self) -> None:
        reusable = self.by_name["unchanged evidence carry-forward"]
        rerun = self.by_name["changed generated input rerun"]
        self.assertTrue(reusable["evidence_reuse_allowed"])
        self.assertFalse(reusable["rerun_trigger"])
        self.assertFalse(rerun["evidence_reuse_allowed"])
        self.assertTrue(rerun["rerun_trigger"])

    def test_skill_links_only_two_canonical_layers(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for target in (
            "references/routing-and-topologies.md",
            "references/core.md",
            "references/controlled.md",
        ):
            self.assertIn(f"]({target})", skill)
        lowered = skill.casefold()
        for removed in ("release-audit.md", "metrics.md", "mode: audit"):
            self.assertNotIn(removed, lowered)

    def test_legacy_paths_are_small_pointers(self) -> None:
        pointers = {
            "governance-lean.md": "core.md",
            "governance-controlled.md": "controlled.md",
            "governance-strict.md": "controlled.md",
            "team-governance-template.zh-CN.md": "core.md",
        }
        for legacy, canonical in pointers.items():
            text = (SKILL_DIR / "references" / legacy).read_text(encoding="utf-8")
            self.assertIn(canonical, text, legacy)
            self.assertLessEqual(len(text.splitlines()), 20, legacy)

    def test_default_skill_local_links_resolve(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", skill):
            if target.startswith(("http://", "https://", "#")):
                continue
            self.assertTrue((SKILL_DIR / target).exists(), target)


if __name__ == "__main__":
    unittest.main()
