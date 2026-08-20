import copy
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "bootstrap-ai-native-dev-team"
SCENARIOS_PATH = ROOT / "tests" / "routing-scenarios.json"
COST_POLICY_CASES_PATH = ROOT / "tests" / "cost-routing-policy-cases.json"
PROFILE_PATH = SKILL_DIR / "references" / "model-routing-openai-deepseek.md"

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
EXPECTED_PROFILE_KEYS = {
    "profile_id",
    "default_active",
    "activation",
    "evidence_date",
    "control_plane",
    "writers",
    "validators",
    "high_volume_deterministic_fallback",
    "forbidden_defaults",
}
EXPECTED_WRITERS = {
    "C0_batch": {"model": "gpt-5.6-luna", "reasoning": "max"},
    "C1": {"model": "gpt-5.6-luna", "reasoning": "max"},
    "C2": {"model": "gpt-5.6-terra", "reasoning": "max"},
    "C3": {"model": "gpt-5.6-sol", "reasoning": "high"},
}
EXPECTED_FORBIDDEN_DEFAULTS = {
    "gpt-5.6-sol:xhigh",
    "gpt-5.6-sol:max",
    "gpt-5.6-sol:ultra",
    "gpt-5.6-luna:low",
    "gpt-5.6-luna:medium",
    "gpt-5.6-luna:high",
    "gpt-5.6-luna:xhigh",
    "gpt-5.6-terra:low",
    "gpt-5.6-terra:medium",
    "gpt-5.6-terra:high",
    "gpt-5.6-terra:xhigh",
    "gpt-5.5:*",
    "gpt-5.4:*",
}
TASK_ROUTING_OBSERVATION_FIELDS = {
    "actual_runtime_mapping_observed",
    "actual_model",
    "actual_effort",
    "input_tokens",
    "output_tokens",
    "steps",
    "first_pass_result",
    "reopens",
    "escalation_reason",
    "cost_claim",
}
EXPECTED_EVIDENCE_DATE = "The evidence snapshot date is **2026-08-20**."
EXPECTED_CURSORBENCH_ROW = (
    "| CursorBench 3.2 | 61.1%; $0.39; 87,973 tokens; 61 steps | "
    "64.9%; $2.31; 32,969 tokens; 47 steps | 63.5%; $2.79; 13,867 tokens; "
    "32 steps | Luna xhigh to max +3.4pp; Terra xhigh to max +5.7pp; "
    "Sol medium to high +3.5pp |"
)


def controlled_trigger(case: dict) -> bool:
    return (
        case["complexity"] in {"C2", "C3"}
        or case["risk"] in {"R2", "R3"}
        or case["shape"] in CONTROLLED_SHAPES
    )


def load_profile_contract() -> dict:
    text = PROFILE_PATH.read_text(encoding="utf-8")
    match = re.search(r"```json routing-profile\s*(\{.*?\})\s*```", text, re.DOTALL)
    assert match, "routing profile JSON block missing"
    return json.loads(match.group(1))


def validate_profile_contract(profile: dict) -> None:
    assert set(profile) == EXPECTED_PROFILE_KEYS
    assert profile["profile_id"] == "openai-deepseek-2026-08-20"
    assert profile["default_active"] is False
    assert profile["activation"] == "explicit-owner-selection"
    assert profile["evidence_date"] == "2026-08-20"
    assert profile["control_plane"] == {
        "model": "gpt-5.6-sol", "reasoning": "high",
    }
    assert profile["writers"] == EXPECTED_WRITERS
    assert profile["validators"] == {
        "R2_R3_when_writer_is_openai": {
            "model": "deepseek-v4-pro", "reasoning": "max",
        },
        "when_writer_is_deepseek_fallback": {
            "model_source": "openai-writer-map-for-complexity",
            "reasoning_source": "openai-writer-map-for-complexity",
        },
    }
    assert profile["high_volume_deterministic_fallback"] == {
        "model": "deepseek-v4-flash",
        "reasoning": "max",
        "default": False,
        "requires_explicit_task_selection": True,
    }
    assert set(profile["forbidden_defaults"]) == EXPECTED_FORBIDDEN_DEFAULTS
    assert len(profile["forbidden_defaults"]) == len(EXPECTED_FORBIDDEN_DEFAULTS)


def validate_profile_activation(
    profile: dict,
    selected_profile: str | None,
    availability_ok: bool,
    authentication_ok: bool,
) -> None:
    validate_profile_contract(profile)
    assert selected_profile == profile["profile_id"]
    assert availability_ok is True
    assert authentication_ok is True


def validate_task_routing_observation(record: dict) -> None:
    assert set(record) == TASK_ROUTING_OBSERVATION_FIELDS
    assert type(record["actual_runtime_mapping_observed"]) is bool
    for field in {"actual_model", "actual_effort", "escalation_reason", "cost_claim"}:
        assert type(record[field]) is str and record[field].strip(), field
    for field in {"input_tokens", "output_tokens", "steps", "reopens"}:
        value = record[field]
        assert value == "unknown" or (type(value) is int and value >= 0), field
    assert record["first_pass_result"] in {"unknown", "accepted", "reopened", "failed"}
    if record["actual_runtime_mapping_observed"]:
        assert record["actual_model"] != "unknown"
        assert record["actual_effort"] != "unknown"
    else:
        assert record["actual_model"] == "unknown"
        assert record["actual_effort"] == "unknown"
        assert record["cost_claim"] in {"none", "blocked-unobservable-mapping"}
    if record["cost_claim"] not in {"none", "blocked-unobservable-mapping"}:
        assert record["actual_runtime_mapping_observed"] is True


def validate_profile_evidence(text: str) -> None:
    assert text.count(EXPECTED_EVIDENCE_DATE) == 1
    cursorbench_rows = [
        line for line in text.splitlines() if line.startswith("| CursorBench 3.2 |")
    ]
    assert cursorbench_rows == [EXPECTED_CURSORBENCH_ROW]
    for amount in ("$0.39", "$2.31", "$2.79"):
        assert cursorbench_rows[0].count(amount) == 1


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
        cls.profile = load_profile_contract()

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

    def test_optional_profile_exact_mapping_and_effort_ceiling(self) -> None:
        validate_profile_contract(self.profile)
        mutations = [
            ("Sol xhigh", lambda p: p["control_plane"].update(reasoning="xhigh")),
            ("Sol max", lambda p: p["writers"]["C3"].update(reasoning="max")),
            ("Sol ultra", lambda p: p["writers"]["C3"].update(reasoning="ultra")),
            ("Luna low", lambda p: p["writers"]["C1"].update(reasoning="low")),
            ("Luna medium", lambda p: p["writers"]["C1"].update(reasoning="medium")),
            ("Luna high", lambda p: p["writers"]["C1"].update(reasoning="high")),
            ("Luna xhigh", lambda p: p["writers"]["C1"].update(reasoning="xhigh")),
            ("Terra low", lambda p: p["writers"]["C2"].update(reasoning="low")),
            ("Terra medium", lambda p: p["writers"]["C2"].update(reasoning="medium")),
            ("Terra high", lambda p: p["writers"]["C2"].update(reasoning="high")),
            ("Terra xhigh", lambda p: p["writers"]["C2"].update(reasoning="xhigh")),
            ("GPT-5.5", lambda p: p["writers"]["C3"].update(model="gpt-5.5")),
            ("GPT-5.4", lambda p: p["writers"]["C3"].update(model="gpt-5.4")),
            (
                "Flash as default Validator",
                lambda p: p["validators"]["R2_R3_when_writer_is_openai"].update(
                    model="deepseek-v4-flash"
                ),
            ),
        ]
        for label, mutate in mutations:
            candidate = copy.deepcopy(self.profile)
            mutate(candidate)
            with self.assertRaises(AssertionError, msg=label):
                validate_profile_contract(candidate)

    def test_optional_profile_activation_fails_closed(self) -> None:
        for selected, available, authenticated in (
            (None, True, True),
            ("different-profile", True, True),
            (self.profile["profile_id"], False, True),
            (self.profile["profile_id"], True, False),
        ):
            with self.assertRaises(AssertionError):
                validate_profile_activation(
                    self.profile, selected, available, authenticated
                )
        validate_profile_activation(
            self.profile, self.profile["profile_id"], True, True
        )

    def test_optional_profile_dated_cursorbench_evidence_fails_closed(self) -> None:
        text = PROFILE_PATH.read_text(encoding="utf-8")
        validate_profile_evidence(text)
        for amount, corrupted in (
            ("$0.39", "/usr/bin/bash.39"),
            ("$2.31", ".31"),
            ("$2.79", ".79"),
        ):
            with self.subTest(amount=amount):
                with self.assertRaises(AssertionError):
                    validate_profile_evidence(text.replace(amount, corrupted, 1))

    def test_missing_routing_telemetry_stays_unknown(self) -> None:
        unknown = {
            "actual_runtime_mapping_observed": False,
            "actual_model": "unknown",
            "actual_effort": "unknown",
            "input_tokens": "unknown",
            "output_tokens": "unknown",
            "steps": "unknown",
            "first_pass_result": "unknown",
            "reopens": "unknown",
            "escalation_reason": "unknown",
            "cost_claim": "blocked-unobservable-mapping",
        }
        validate_task_routing_observation(unknown)
        invented = copy.deepcopy(unknown)
        invented["input_tokens"] = None
        with self.assertRaises(AssertionError):
            validate_task_routing_observation(invented)

        unsupported_claim = copy.deepcopy(unknown)
        unsupported_claim["cost_claim"] = "lower-cost"
        with self.assertRaises(AssertionError):
            validate_task_routing_observation(unsupported_claim)

    def test_canonical_policy_corpus_is_vendor_neutral(self) -> None:
        canonical = [
            SKILL_DIR / "SKILL.md",
            SKILL_DIR / "references" / "routing-and-topologies.md",
            SKILL_DIR / "references" / "core.md",
            SKILL_DIR / "references" / "controlled.md",
            SKILL_DIR / "assets" / "team-bootstrap-proposal.md",
            SKILL_DIR / "assets" / "project-team-charter.md",
            SKILL_DIR / "assets" / "task-contract.md",
            SKILL_DIR / "agents" / "openai.yaml",
            ROOT / "examples" / "global-agents-snippet.md",
        ]
        vendor_name = re.compile(r"(?:gpt-5(?:\.|-)|deepseek|openai)", re.IGNORECASE)
        for path in canonical:
            self.assertIsNone(
                vendor_name.search(path.read_text(encoding="utf-8")), path
            )
        self.assertIsNotNone(vendor_name.search(PROFILE_PATH.read_text(encoding="utf-8")))

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
