import copy
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "bootstrap-ai-native-dev-team"
SCENARIOS_PATH = ROOT / "tests" / "routing-scenarios.json"

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


def validate_case(case: dict) -> None:
    assert set(case) == REQUIRED_FIELDS, f"field set mismatch: {case.get('name')}"
    for field in STRING_FIELDS:
        assert type(case[field]) is str and case[field].strip(), field
    for field in BOOL_FIELDS:
        assert type(case[field]) is bool, field

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
        assert not case["independent_validator"]
        assert not case["worktree_required"]
    else:
        assert case["route"] in {"task-cell", "team-required"}
        assert case["independent_validator"]
        assert case["worktree_required"]

    assert case["delegated"] == (case["route"] != "no-delegation")
    assert case["owner_approval"] == (case["risk"] == "R3")
    assert not (case["evidence_reuse_allowed"] and case["rerun_trigger"])


class RoutingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
        cls.by_name = {case["name"]: case for case in cls.scenarios}

    def test_matrix_shape_and_policy(self) -> None:
        self.assertGreaterEqual(len(self.scenarios), 10)
        self.assertEqual(len(self.by_name), len(self.scenarios))
        for case in self.scenarios:
            validate_case(case)

    def assert_rejected(self, case: dict, mutate, label: str) -> None:
        candidate = copy.deepcopy(case)
        mutate(candidate)
        with self.assertRaises(AssertionError, msg=label):
            validate_case(candidate)

    def test_negative_mutations_fail_closed(self) -> None:
        core = self.by_name["C1/R1 non-material isolated work"]
        material = self.by_name["material C1/R1 behavior change"]
        public = self.by_name["ordinary public deployment"]
        c1_r3 = self.by_name["C1/R3 security-boundary change"]

        self.assert_rejected(core, lambda c: c.pop("layer"), "missing layer")
        self.assert_rejected(core, lambda c: c.update(delegated="false"), "string bool")
        self.assert_rejected(material, lambda c: c.update(layer="core"), "wrong layer")
        self.assert_rejected(public, lambda c: c.update(layer="release-audit"), "removed layer")
        self.assert_rejected(
            c1_r3,
            lambda c: c.update(capability="frontier", reasoning="max"),
            "risk raised capability",
        )
        self.assert_rejected(
            c1_r3,
            lambda c: c.update(owner_approval=False),
            "missing owner approval",
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
