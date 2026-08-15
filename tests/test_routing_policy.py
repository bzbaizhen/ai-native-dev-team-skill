import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "bootstrap-ai-native-dev-team"
SCENARIOS_PATH = ROOT / "tests" / "routing-scenarios.json"


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


class RoutingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
        cls.by_name = {case["name"]: case for case in cls.scenarios}

    def test_matrix_has_complete_shape_and_expected_layers(self) -> None:
        self.assertGreaterEqual(len(self.scenarios), 14)
        required = {
            "name",
            "complexity",
            "risk",
            "shape",
            "material_behavior_change",
            "interface_change",
            "dependency_change",
            "data_change",
            "security_change",
            "concurrency",
            "production_action",
            "public_action",
            "request",
            "route",
            "layer",
            "profile",
            "capability",
            "reasoning",
            "delegated",
            "worker_skill_loaded",
            "independent_validator",
            "owner_approval",
            "worktree_required",
            "ledger_required",
            "release_audit",
            "explicit_release_audit",
            "evidence_reuse_allowed",
            "rerun_trigger",
        }
        for case in self.scenarios:
            self.assertTrue(required.issubset(case), case["name"])
            self.assertIn(case["complexity"], {"C0", "C1", "C2", "C3"})
            self.assertIn(case["risk"], {"R0", "R1", "R2", "R3"})
            self.assertEqual(case["layer"], expected_layer(case), case["name"])
            # `profile` keeps the V1 `strict` spelling as a compatibility alias for
            # Controlled R3/C3 cases; `layer` is the canonical V2 selector.
            self.assertIn(case["profile"], {case["layer"], "strict"}, case["name"])
            if case["profile"] == "strict":
                self.assertIn(case["layer"], {"controlled", "release-audit"})
            self.assertEqual(
                (case["capability"], case["reasoning"]),
                expected_capability(case),
                case["name"],
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
