import copy
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "ai-native-dev-team"
SCENARIOS_PATH = ROOT / "tests" / "routing-scenarios.json"
COST_POLICY_CASES_PATH = ROOT / "tests" / "cost-routing-policy-cases.json"
PROFILE_PATH = ROOT / "skills" / "ai-native-model-router" / "assets" / "profiles" / "gpt5.6.json"
PROFILE_EVIDENCE_PATH = ROOT / "skills" / "ai-native-model-router" / "references" / "provider-evidence.md"
LEGACY_PROFILE_PATH = SKILL_DIR / "references" / "model-routing-openai-deepseek.md"
GIT_ISOLATION_REFERENCE = SKILL_DIR / "references" / "git-isolation-bootstrap.md"
GIT_ISOLATION_HELPER = SKILL_DIR / "scripts" / "git_isolation_bootstrap.py"

EXPECTED_LEVEL_ZERO_DESCRIPTION = "Route AI-native development with proportional controls."
MAX_LEVEL_ZERO_DESCRIPTION_CHARS = 60
MAX_LEVEL_ONE_LINES = 120
MAX_LEVEL_ONE_CHARS = 6800
CANONICAL_REFERENCE_LINKS = (
    "references/routing-and-topologies.md",
    "references/core.md",
    "references/controlled.md",
)
DQR_REFERENCE_LINK = "references/delivery-quality-review.md"
METRICS_REFERENCE_LINK = "references/metrics.md"
DQR_PATH = SKILL_DIR / "references" / "delivery-quality-review.md"
METRICS_PATH = SKILL_DIR / "references" / "metrics.md"
ASSET_TRIGGERS = {
    "assets/team-bootstrap-proposal.md":
        "only when an explicit proposal request needs an approval-ready team proposal",
    "assets/task-contract.md":
        "only when controlled work explicitly needs a durable written contract or frozen interface",
    "assets/project-team-charter.md":
        "only when an explicitly requested long-lived multi-task team is being established",
}


def validate_progressive_disclosure(skill_text: str, skill_dir: Path) -> None:
    frontmatter = re.match(r"\A---\s*\n(.*?)\n---", skill_text, re.DOTALL)
    assert frontmatter, "frontmatter is malformed"
    descriptions = [
        line.split(":", 1)[1].strip()
        for line in frontmatter.group(1).splitlines()
        if line.lstrip().startswith("description:")
    ]
    assert len(descriptions) == 1, "description must occur exactly once"
    description = descriptions[0]
    assert description == EXPECTED_LEVEL_ZERO_DESCRIPTION
    assert len(description) <= MAX_LEVEL_ZERO_DESCRIPTION_CHARS
    assert re.fullmatch(r"[A-Z][A-Za-z0-9-]*(?: [A-Za-z0-9-]+){2,}[.!?]", description)
    assert len(skill_text.splitlines()) <= MAX_LEVEL_ONE_LINES
    assert len(skill_text) <= MAX_LEVEL_ONE_CHARS

    links = {
        target.split("#", 1)[0]
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", skill_text)
        if not target.startswith(("http://", "https://", "#"))
    }
    assert set(CANONICAL_REFERENCE_LINKS) <= links
    assert DQR_REFERENCE_LINK in links
    assert METRICS_REFERENCE_LINK in links
    compact = " ".join(skill_text.casefold().split())
    assert "load level-2 assets only on demand" in compact
    assert "do not preload assets; load only the asset whose matching trigger applies" in compact
    assert "dqr is a per-task acceptance protocol, not a routing layer" in compact
    assert "main agent explicitly selects local prospective measurement" in compact
    for target, trigger in ASSET_TRIGGERS.items():
        assert target in links
        line = next(
            (" ".join(line.casefold().split()) for line in skill_text.splitlines()
             if f"]({target})" in line),
            None,
        )
        assert line is not None
        assert trigger in line
    for target in links:
        assert (skill_dir / target).is_file(), target
WINDOWS_LIFECYCLE_POLICY_PATHS = {
    "SKILL.md": SKILL_DIR / "SKILL.md",
    "routing-and-topologies.md": SKILL_DIR / "references" / "routing-and-topologies.md",
    "README.md": ROOT / "README.md",
    "README.zh-CN.md": ROOT / "README.zh-CN.md",
    "global-agents-snippet.md": ROOT / "examples" / "global-agents-snippet.md",
}

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
EXPECTED_PRIMARY_UNAVAILABLE_EVIDENCE = [
    "model-not-found",
    "authenticated-provider-outage",
    "quota-exhaustion",
    "repeated-bounded-transport-failure",
]


def custom_v1_profile_source(profile_id="custom-v1") -> dict:
    """Build the bounded project-only v1 fixture used by policy tests."""

    source = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    source["schema_version"] = 1
    source["profile_id"] = profile_id
    source["evidence_date"] = "2026-08-28"
    del source["slots"]["validator.assurance"]
    source["slots"]["validator.independent"] = {
        "primary": {
            "provider": "zai",
            "model": "glm-5.3",
            "reasoning": "max",
            "reasoning_delivery": "provider-default",
        },
        "fallback": {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "reasoning": "max",
            "reasoning_delivery": "explicit",
        },
        "accepted_primary_unavailable_evidence": EXPECTED_PRIMARY_UNAVAILABLE_EVIDENCE,
        "independent_validator_source": "openai-complexity-map",
    }
    return source


def controlled_trigger(case: dict) -> bool:
    return (
        case["complexity"] in {"C2", "C3"}
        or case["risk"] in {"R2", "R3"}
        or case["shape"] in CONTROLLED_SHAPES
    )


def load_profile_contract() -> dict:
    source = custom_v1_profile_source()
    slots = source["slots"]
    writer_names = {
        "writer.c0-batch": "C0_batch",
        "writer.c1": "C1",
        "writer.c2": "C2",
        "writer.c3": "C3",
    }
    writers = {
        writer_names[name]:
        {key: slot["primary"][key] for key in ("model", "reasoning")}
        for name, slot in slots.items()
        if name.startswith("writer.c")
    }
    return {
        "profile_id": source["profile_id"],
        "default_active": source["default_active"],
        "activation": source["activation"],
        "evidence_date": source["evidence_date"],
        "control_plane": {
            key: slots["control-plane"]["primary"][key]
            for key in ("model", "reasoning")
        },
        "writers": writers,
        "validators": {
            "R2_R3_when_writer_is_openai": {
                "primary": {
                    key: slots["validator.independent"]["primary"][key]
                    for key in ("provider", "model", "reasoning", "reasoning_delivery")
                },
                "fallback": {
                    key: slots["validator.independent"]["fallback"][key]
                    for key in ("provider", "model", "reasoning")
                }
                | {
                    "requires_primary_unavailable_evidence": True,
                    "accepted_primary_unavailable_evidence": slots["validator.independent"]["accepted_primary_unavailable_evidence"],
                },
            },
            "when_writer_is_glm_or_deepseek_fallback": {
                "model_source": "openai-writer-map-for-complexity",
                "reasoning_source": "openai-writer-map-for-complexity",
            },
        },
        "high_volume_deterministic_fallback": {
            "primary": {
                key: slots["writer.high-volume-deterministic"]["primary"][key]
                for key in ("provider", "model", "reasoning", "reasoning_delivery")
            },
            "fallback": {
                key: slots["writer.high-volume-deterministic"]["fallback"][key]
                for key in ("provider", "model", "reasoning")
            }
            | {
                "requires_primary_unavailable_evidence": True,
                "accepted_primary_unavailable_evidence": slots["writer.high-volume-deterministic"]["accepted_primary_unavailable_evidence"],
            },
            "default": slots["writer.high-volume-deterministic"]["default"],
            "requires_explicit_task_selection": slots["writer.high-volume-deterministic"]["requires_explicit_task_selection"],
        },
        "forbidden_defaults": source["forbidden_defaults"],
    }


def validate_profile_contract(profile: dict) -> None:
    assert set(profile) == EXPECTED_PROFILE_KEYS
    assert profile["profile_id"] == "custom-v1"
    assert profile["default_active"] is False
    assert profile["activation"] == "explicit-owner-selection"
    assert profile["evidence_date"] == "2026-08-28"
    assert profile["control_plane"] == {
        "model": "gpt-5.6-sol", "reasoning": "high",
    }
    assert profile["writers"] == EXPECTED_WRITERS
    assert profile["validators"] == {
        "R2_R3_when_writer_is_openai": {
            "primary": {
                "provider": "zai",
                "model": "glm-5.3",
                "reasoning": "max",
                "reasoning_delivery": "provider-default",
            },
            "fallback": {
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "reasoning": "max",
                "requires_primary_unavailable_evidence": True,
                "accepted_primary_unavailable_evidence": EXPECTED_PRIMARY_UNAVAILABLE_EVIDENCE,
            },
        },
        "when_writer_is_glm_or_deepseek_fallback": {
            "model_source": "openai-writer-map-for-complexity",
            "reasoning_source": "openai-writer-map-for-complexity",
        },
    }
    assert profile["high_volume_deterministic_fallback"] == {
        "primary": {
            "provider": "zai",
            "model": "glm-5.3-flash",
            "reasoning": "max",
            "reasoning_delivery": "provider-default",
        },
        "fallback": {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "reasoning": "max",
            "requires_primary_unavailable_evidence": True,
            "accepted_primary_unavailable_evidence": EXPECTED_PRIMARY_UNAVAILABLE_EVIDENCE,
        },
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


def validate_profile_evidence(profile: dict) -> None:
    assert profile["evidence_date"] == "2026-08-28"
    for slot_name in ("validator.independent", "writer.high-volume-deterministic"):
        assert profile["slots"][slot_name]["accepted_primary_unavailable_evidence"] == EXPECTED_PRIMARY_UNAVAILABLE_EVIDENCE


def validate_windows_lifecycle_policy(text: str) -> None:
    compact = " ".join(text.casefold().split())
    required = (
        "unattended non-interactive coding cli exec, writer, or validator invocations on windows",
        "use `pty=false`, `background=true`, and `notify_on_complete=true` by default",
        "`pty=true` is reserved for an interactive tui, login, or a command that genuinely requires terminal input",
        "never apply it unconditionally to unattended exec",
        "final output text, a final-answer marker, or a tokens-used line is not process-exit evidence",
        "registry status `exited`",
        "captures the exit code",
        "one short bounded grace check",
        "inspect fresh process status",
        "terminate only the exact tracked process",
        "never start a duplicate writer",
        "never repeatedly wait/reconnect",
    )
    for phrase in required:
        assert phrase in compact, phrase


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

    def test_progressive_disclosure_contract_and_mutations_fail_closed(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        validate_progressive_disclosure(skill, SKILL_DIR)

        def reject(label: str, candidate: str) -> None:
            self.assertNotEqual(candidate, skill, label)
            with self.subTest(mutation=label):
                with self.assertRaises(AssertionError):
                    validate_progressive_disclosure(candidate, SKILL_DIR)

        description_prefix = f"description: {EXPECTED_LEVEL_ZERO_DESCRIPTION}"
        for invalid in (
            EXPECTED_LEVEL_ZERO_DESCRIPTION.removesuffix("."),
            EXPECTED_LEVEL_ZERO_DESCRIPTION.replace("Route", "route", 1),
            EXPECTED_LEVEL_ZERO_DESCRIPTION + " and more detail.",
        ):
            reject("description", skill.replace(description_prefix, f"description: {invalid}", 1))
        for label, candidate in (
            ("line limit", skill + "\nextra" * MAX_LEVEL_ONE_LINES),
            ("character limit", skill + "x" * (MAX_LEVEL_ONE_CHARS - len(skill) + 1)),
            ("canonical reference", skill.replace("](references/core.md)", "](references/missing.md)", 1)),
            (
                "unresolved local link",
                skill.replace(
                    "references/delivery-quality-review.md",
                    "references/missing.md",
                    1,
                ),
            ),
        ):
            reject(label, candidate)
        for target, trigger in ASSET_TRIGGERS.items():
            reject(
                f"asset trigger: {target}",
                re.sub(re.escape(trigger), "when needed", skill, count=1, flags=re.IGNORECASE),
            )

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

    def test_windows_lifecycle_policy_is_consistent_across_docs(self) -> None:
        for label, path in WINDOWS_LIFECYCLE_POLICY_PATHS.items():
            compact = " ".join(path.read_text(encoding="utf-8").casefold().split())
            for term in (
                "`pty=false`",
                "`background=true`",
                "`notify_on_complete=true`",
                "`pty=true`",
                "registry",
                "`exited`",
                "writer",
                "wait/reconnect",
            ):
                self.assertIn(term, compact, f"{label}: {term}")

    def test_windows_unattended_cli_policy_mutations_fail_closed(self) -> None:
        policy = " ".join(
            WINDOWS_LIFECYCLE_POLICY_PATHS[
                "routing-and-topologies.md"
            ].read_text(encoding="utf-8").split()
        )
        validate_windows_lifecycle_policy(policy)
        mutations = {
            "unconditional PTY": ("use `pty=false`", "use `pty=true`"),
            "foreground execution": ("`background=true`", "`background=false`"),
            "completion notification disabled": (
                "`notify_on_complete=true`",
                "`notify_on_complete=false`",
            ),
            "terminal reservation removed": (
                "`pty=true` is reserved",
                "`pty=true` is preferred",
            ),
            "output treated as exit evidence": (
                "is not process-exit evidence",
                "is process-exit evidence",
            ),
            "registry exit missing": ("registry status `exited`", "output status complete"),
            "exit code missing": ("captures the exit code", "captures the final output"),
            "unbounded grace wait": (
                "one short bounded grace check",
                "an unbounded grace wait",
            ),
            "broad process termination": (
                "terminate only the exact tracked process",
                "terminate all matching processes",
            ),
            "duplicate Writer allowed": (
                "Never start a duplicate Writer",
                "Start a duplicate Writer",
            ),
            "repeated reconnect allowed": (
                "never repeatedly wait/reconnect",
                "repeatedly wait/reconnect",
            ),
        }
        for label, (old, new) in mutations.items():
            self.assertIn(old, policy, label)
            mutated = policy.replace(old, new, 1)
            with self.assertRaises(AssertionError, msg=label):
                validate_windows_lifecycle_policy(mutated)

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
                "DeepSeek Pro becomes primary Validator",
                lambda p: p["validators"]["R2_R3_when_writer_is_openai"]["primary"].update(
                    provider="deepseek", model="deepseek-v4-pro"
                ),
            ),
            (
                "Validator fallback loses primary-unavailable evidence gate",
                lambda p: p["validators"]["R2_R3_when_writer_is_openai"]["fallback"].update(
                    requires_primary_unavailable_evidence=False
                ),
            ),
            (
                "DeepSeek Flash becomes primary high-volume Writer",
                lambda p: p["high_volume_deterministic_fallback"]["primary"].update(
                    provider="deepseek", model="deepseek-v4-flash"
                ),
            ),
            (
                "high-volume fallback becomes default",
                lambda p: p["high_volume_deterministic_fallback"].update(default=True),
            ),
            (
                "high-volume fallback loses explicit selection",
                lambda p: p["high_volume_deterministic_fallback"].update(
                    requires_explicit_task_selection=False
                ),
            ),
            (
                "Writer fallback loses primary-unavailable evidence gate",
                lambda p: p["high_volume_deterministic_fallback"]["fallback"].update(
                    requires_primary_unavailable_evidence=False
                ),
            ),
        ]
        for label, mutate in mutations:
            candidate = copy.deepcopy(self.profile)
            mutate(candidate)
            with self.assertRaises(AssertionError, msg=label):
                validate_profile_contract(candidate)

        fallback_getters = (
            (
                "Validator fallback",
                lambda p: p["validators"]["R2_R3_when_writer_is_openai"]["fallback"],
            ),
            (
                "high-volume Writer fallback",
                lambda p: p["high_volume_deterministic_fallback"]["fallback"],
            ),
        )
        evidence_mutations = (
            ("removes evidence field", lambda fallback: fallback.pop(
                "accepted_primary_unavailable_evidence"
            )),
            ("reorders evidence list", lambda fallback: fallback.update(
                accepted_primary_unavailable_evidence=list(
                    reversed(EXPECTED_PRIMARY_UNAVAILABLE_EVIDENCE)
                )
            )),
            ("replaces evidence list", lambda fallback: fallback.update(
                accepted_primary_unavailable_evidence=["model-not-found"]
            )),
            ("accepts subjective quality", lambda fallback: fallback.update(
                accepted_primary_unavailable_evidence=["subjective-quality"]
            )),
            ("accepts cost preference", lambda fallback: fallback.update(
                accepted_primary_unavailable_evidence=["cost-preference"]
            )),
        )
        for fallback_label, get_fallback in fallback_getters:
            for mutation_label, mutate in evidence_mutations:
                with self.subTest(fallback=fallback_label, mutation=mutation_label):
                    candidate = copy.deepcopy(self.profile)
                    mutate(get_fallback(candidate))
                    with self.assertRaises(AssertionError):
                        validate_profile_contract(candidate)

    def test_optional_profile_keeps_deepseek_fallback_only(self) -> None:
        profile = load_profile_contract()
        validator_routes = profile["validators"]["R2_R3_when_writer_is_openai"]
        high_volume_routes = profile["high_volume_deterministic_fallback"]
        self.assertEqual(validator_routes["primary"]["provider"], "zai")
        self.assertEqual(validator_routes["fallback"]["provider"], "deepseek")
        self.assertEqual(high_volume_routes["primary"]["provider"], "zai")
        self.assertEqual(high_volume_routes["fallback"]["provider"], "deepseek")
        self.assertNotIn("deepseek", json.dumps(validator_routes["primary"]).casefold())
        self.assertNotIn("deepseek", json.dumps(high_volume_routes["primary"]).casefold())
        self.assertFalse(profile["default_active"])
        self.assertFalse(high_volume_routes["default"])
        self.assertFalse(LEGACY_PROFILE_PATH.exists())
        profile_evidence = " ".join(
            PROFILE_EVIDENCE_PATH.read_text(encoding="utf-8").split()
        )
        self.assertIn("The exact accepted evidence is, in order", profile_evidence)
        self.assertIn("Availability and runtime behavior remain caller-observed", profile_evidence)

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

    def test_optional_profile_evidence_date_and_gate_fail_closed(self) -> None:
        source = custom_v1_profile_source()
        validate_profile_evidence(source)
        for mutation in (
            lambda candidate: candidate.update(evidence_date="unknown"),
            lambda candidate: candidate["slots"]["validator.independent"].update(
                accepted_primary_unavailable_evidence=[]
            ),
        ):
            candidate = json.loads(json.dumps(source))
            mutation(candidate)
            with self.assertRaises(AssertionError):
                validate_profile_evidence(candidate)

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
            DQR_PATH,
            METRICS_PATH,
            SKILL_DIR / "assets" / "team-bootstrap-proposal.md",
            SKILL_DIR / "assets" / "project-team-charter.md",
            SKILL_DIR / "assets" / "task-contract.md",
            SKILL_DIR / "agents" / "openai.yaml",
            ROOT / "examples" / "global-agents-snippet.md",
            GIT_ISOLATION_REFERENCE,
            GIT_ISOLATION_HELPER,
        ]
        vendor_name = re.compile(
            r"(?:gpt-5(?:\.|-)|deepseek|openai|anthropic|"
            r"(?<!\w)glm-5\.3(?:-flash)?(?!\w)|\bzai\b)",
            re.IGNORECASE,
        )
        for path in canonical:
            self.assertIsNone(
                vendor_name.search(path.read_text(encoding="utf-8")), path
            )
        isolation_vendor_name = re.compile(
            r"\b(?:codex|openai|deepseek|anthropic)\b|"
            r"(?<!\w)glm-5\.3(?:-flash)?(?!\w)|\bzai\b",
            re.IGNORECASE,
        )
        for path in (GIT_ISOLATION_REFERENCE, GIT_ISOLATION_HELPER):
            self.assertIsNone(isolation_vendor_name.search(path.read_text(encoding="utf-8")), path)
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
        self.assertIn(f"]({DQR_REFERENCE_LINK})", skill)
        self.assertIn(f"]({METRICS_REFERENCE_LINK})", skill)
        lowered = skill.casefold()
        for removed in ("release-audit.md", "evidence-manifest", "mode: audit"):
            self.assertNotIn(removed, lowered)

    def test_controlled_dqr_and_optional_metrics_boundaries(self) -> None:
        controlled = (SKILL_DIR / "references" / "controlled.md").read_text(
            encoding="utf-8"
        ).casefold()
        core = (SKILL_DIR / "references" / "core.md").read_text(encoding="utf-8").casefold()
        routing = (SKILL_DIR / "references" / "routing-and-topologies.md").read_text(
            encoding="utf-8"
        ).casefold()
        dqr = " ".join(DQR_PATH.read_text(encoding="utf-8").casefold().split())
        metrics = " ".join(METRICS_PATH.read_text(encoding="utf-8").casefold().split())
        for text in (controlled, routing):
            self.assertIn("delivery-quality-review.md", text)
            self.assertIn("not a routing layer", text)
        self.assertIn("core does not load a dqr acceptance packet", core)
        for term in (
            "frozen contract",
            "exact path lease",
            "writer self-check",
            "independent, read-only validator",
            "invalidate candidate-bound evidence",
            "executable rollback",
            "designed",
            "written",
            "run",
            "verified",
            "accepted",
            "integrated",
            "installed",
        ):
            self.assertIn(term, dqr)
        for term in (
            "optional for both core and controlled",
            "sole ledger writer",
            "record",
            "snapshot",
            "audit",
            "compare",
            "descriptive",
        ):
            self.assertIn(term, metrics)

    def test_dqr_lifecycle_states_do_not_collapse(self) -> None:
        skill = " ".join((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").casefold().split())
        dqr_raw = DQR_PATH.read_text(encoding="utf-8")
        dqr = " ".join(dqr_raw.casefold().split())

        self.assertNotIn(
            "accept only the exact validated change integrated into the stable branch",
            skill,
        )
        for text in (skill, dqr):
            self.assertIn("exact verified candidate", text)
            self.assertIn("authority evidence", text)
        for term in (
            "acceptance does not require prior integration or installation",
            "does not authorize either action",
            "separately authorized integration target",
            "identity readback",
            "separately authorized installation target",
            "rollback backup",
            "byte/readback verification",
            "acceptance implies neither integration nor installation",
            "integration and installation do not imply each other",
            "release, public, and production actions remain separately gated",
        ):
            self.assertIn(term, dqr)

        states = {
            state: re.search(
                rf"\| {state} \| ([^|]+) \|",
                dqr_raw.casefold(),
            )
            for state in ("accepted", "integrated", "installed", "released")
        }
        self.assertTrue(all(states.values()))
        self.assertEqual(len({match.group(1).strip() for match in states.values()}), 4)

    def test_linear_issue_isolation_activates_before_writer_dispatch(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        compact_skill = " ".join(skill.casefold().split())
        self.assertIn(
            "](references/git-isolation-bootstrap.md)", skill,
        )
        self.assertIn("linear-governed implementation issue", compact_skill)
        self.assertIn("explicit isolation request", compact_skill)
        self.assertIn("before writer dispatch", compact_skill)
        self.assertIn("non-linear core/controlled routing", compact_skill)
        self.assertTrue(GIT_ISOLATION_REFERENCE.is_file())
        self.assertTrue(GIT_ISOLATION_HELPER.is_file())
        reference = GIT_ISOLATION_REFERENCE.read_text(encoding="utf-8").casefold()
        for requirement in (
            "linear identity/status/blocker/gitbranchname/latest-checkpoint gate",
            "<repo-parent>/<repo-name>-worktrees/<issue-id-lowercase>",
            "repository-scoped short bootstrap lock",
            "local_execution_blocker",
            "git worktree repair",
            "no destructive git command",
            "plan-only review is a rich, non-mutating evidence preflight",
            "a non-started or blocked issue returns",
            "it is not permission to dispatch",
        ):
            self.assertIn(requirement, reference)
        self.assertIn(
            "skills/ai-native-dev-team/scripts/git_isolation_bootstrap.py",
            reference,
        )
        self.assertNotIn("codex-git-isolation-bootstrap.lock", reference)

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
