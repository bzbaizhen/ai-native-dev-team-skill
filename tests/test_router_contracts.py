import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
import uuid


ROOT = Path(__file__).parents[1]
SCRIPT_DIR = ROOT / "skills" / "ai-native-model-router" / "scripts"
ASSET_DIR = ROOT / "skills" / "ai-native-model-router" / "assets"
sys.path.insert(0, str(SCRIPT_DIR))

from router_config import (  # noqa: E402
    atomic_write_config,
    config_digest,
    migrate_legacy_profile,
    resolve_config_path,
    rollback_config,
    validate_config,
    validate_config_for_version,
    validate_config_v2,
    validate_config_versioned,
)


ROUTE_SLOTS = [
    "control-plane",
    "writer.c0-batch",
    "writer.c1",
    "writer.c2",
    "writer.c3",
    "validator.independent",
    "writer.high-volume-deterministic",
]
V2_ROUTE_SLOTS = [
    "control-plane",
    "writer.c0-batch",
    "writer.c1",
    "writer.c2",
    "writer.c3",
    "validator.assurance",
    "writer.high-volume-deterministic",
]
OLD_PROFILE_PATH = ASSET_DIR / "profiles" / "openai-glm5.3-deepseek-fallback-2026-08-28.json"
OLD_PROFILE_GIT_BLOB = "3da4191c501cc8ce403c8a5a39aabe6a6d59e2ca"
OLD_PROFILE_SHA256 = "cc6beae0df7434baca3d782eaecc8696c31b6abdc28c63157d599af1cd95ccaa"


def valid_config(**overrides):
    payload = {
        "schema_version": 1,
        "router_api_version": "route/v1",
        "config_id": "test-config",
        "active_profile": "openai-glm5.3-deepseek-fallback-2026-08-28",
        "project_profile_dirs": [".ai-native/profiles"],
        "updated_reason": "test fixture",
    }
    payload.update(overrides)
    return payload


def valid_config_v2(**overrides):
    payload = {
        "schema_version": 2,
        "router_api_version": "route/v2",
        "config_id": "test-config-v2",
        "active_profile": "openai-gpt5.6-validator-assurance-2026-08-31",
        "project_profile_dirs": [".ai-native/profiles"],
        "updated_reason": "test fixture",
    }
    payload.update(overrides)
    return payload


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


@contextmanager
def temporary_contract_project():
    path = ROOT / "tests" / f".router-contracts-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


class SchemaContractTests(unittest.TestCase):
    def load(self, name):
        with (ASSET_DIR / name).open(encoding="utf-8") as handle:
            return json.load(handle)

    def test_all_versioned_schemas_are_machine_readable(self):
        for name in (
            "route-request.v1.schema.json",
            "route-decision.v1.schema.json",
            "model-router-config.v1.schema.json",
            "route-request.v2.schema.json",
            "route-decision.v2.schema.json",
            "model-router-config.v2.schema.json",
        ):
            with self.subTest(name=name):
                schema = self.load(name)
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertEqual(schema["type"], "object")
                self.assertFalse(schema["additionalProperties"])

    def test_route_request_v2_contract_has_assurance_surface(self):
        schema = self.load("route-request.v2.schema.json")
        expected = {
            "router_api_version",
            "request_id",
            "route_slot",
            "writer_route_slot",
            "profile_id",
            "explicit_profile_selection",
            "explicit_high_volume_selection",
            "availability",
            "route_failure_evidence",
            "risk_level",
            "writer_identity",
            "candidate_id",
        }
        self.assertEqual(set(schema["required"]), expected)
        self.assertEqual(set(schema["properties"]), expected)
        self.assertEqual(schema["properties"]["router_api_version"]["const"], "route/v2")
        self.assertEqual(schema["properties"]["route_slot"]["enum"], V2_ROUTE_SLOTS)
        self.assertNotIn("validator.independent", schema["properties"]["route_slot"]["enum"])
        self.assertEqual(
            schema["properties"]["writer_route_slot"],
            {
                "type": ["string", "null"],
                "enum": ["writer.c0-batch", "writer.c1", "writer.c2", "writer.c3", None],
            },
        )
        self.assertEqual(schema["properties"]["risk_level"]["enum"], ["R1", "R2", "R3", None])
        evidence = schema["properties"]["route_failure_evidence"]
        self.assertNotIn("primary_failure_evidence", schema["properties"])
        self.assertTrue(evidence["additionalProperties"]["uniqueItems"])
        self.assertEqual(evidence["additionalProperties"]["items"]["type"], "string")
        self.assertEqual(schema["properties"]["candidate_id"]["type"], ["string", "null"])

    def test_route_decision_v2_contract_has_assurance_surface(self):
        schema = self.load("route-decision.v2.schema.json")
        expected = {
            "router_api_version",
            "request_id",
            "profile_id",
            "route_slot",
            "decision_status",
            "enforcement_status",
            "selected_routes",
            "validation_mode",
            "risk_level",
            "escalation_used",
            "escalation_evidence",
            "same_model_as_writer",
            "validator_source",
            "config_digest",
            "limitations",
        }
        self.assertEqual(set(schema["required"]), expected)
        self.assertEqual(set(schema["properties"]), expected)
        self.assertEqual(schema["properties"]["router_api_version"]["const"], "route/v2")
        self.assertEqual(schema["properties"]["route_slot"]["enum"], V2_ROUTE_SLOTS)
        self.assertEqual(schema["properties"]["decision_status"]["enum"], ["selected", "blocked", "unknown"])
        self.assertEqual(schema["properties"]["enforcement_status"]["enum"], ["not-executed"])
        self.assertEqual(
            schema["properties"]["validation_mode"]["enum"],
            ["not-applicable", "single", "dual"],
        )
        self.assertEqual(schema["properties"]["risk_level"]["enum"], ["R1", "R2", "R3", None])
        self.assertEqual(schema["properties"]["validator_source"]["enum"], ["router-selected", "not-applicable"])
        selected_routes = schema["properties"]["selected_routes"]
        self.assertEqual(selected_routes["type"], "array")
        self.assertEqual(selected_routes["minItems"], 0)
        self.assertEqual(selected_routes["maxItems"], 2)
        self.assertEqual(selected_routes["items"]["type"], "object")
        self.assertFalse(selected_routes["items"]["additionalProperties"])
        self.assertEqual(
            set(selected_routes["items"]["required"]),
            {"provider", "runtime_provider", "model", "reasoning", "reasoning_delivery"},
        )
        escalation = schema["properties"]["escalation_evidence"]
        self.assertTrue(escalation["additionalProperties"]["uniqueItems"])
        self.assertEqual(escalation["additionalProperties"]["items"]["type"], "string")
        self.assertEqual(schema["properties"]["config_digest"]["pattern"], r"^[0-9a-f]{64}$")

    def test_config_v2_contract_is_strict_and_versioned(self):
        schema = self.load("model-router-config.v2.schema.json")
        expected = {
            "schema_version",
            "router_api_version",
            "config_id",
            "active_profile",
            "project_profile_dirs",
            "updated_reason",
        }
        self.assertEqual(set(schema["required"]), expected)
        self.assertEqual(set(schema["properties"]), expected)
        self.assertEqual(schema["properties"]["schema_version"]["const"], 2)
        self.assertEqual(schema["properties"]["router_api_version"]["const"], "route/v2")

    def test_preserved_profile_matches_frozen_git_blob_and_sha256(self):
        profile_bytes = OLD_PROFILE_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(profile_bytes).hexdigest(), OLD_PROFILE_SHA256)
        self.assertEqual(
            subprocess.check_output(
                ["git", "cat-file", "blob", OLD_PROFILE_GIT_BLOB],
                cwd=ROOT,
            ),
            profile_bytes,
        )
        self.assertEqual(
            subprocess.check_output(
                ["git", "hash-object", "--", str(OLD_PROFILE_PATH)],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
            ).strip(),
            OLD_PROFILE_GIT_BLOB,
        )

    def test_route_request_contract_has_exact_required_surface(self):
        schema = self.load("route-request.v1.schema.json")
        expected = {
            "router_api_version",
            "request_id",
            "route_slot",
            "writer_route_slot",
            "profile_id",
            "explicit_profile_selection",
            "explicit_high_volume_selection",
            "availability",
            "primary_failure_evidence",
            "writer_identity",
            "candidate_id",
        }
        self.assertEqual(set(schema["required"]), expected)
        self.assertEqual(set(schema["properties"]), expected)
        self.assertEqual(schema["properties"]["router_api_version"]["const"], "route/v1")
        self.assertEqual(schema["properties"]["route_slot"]["enum"], ROUTE_SLOTS)
        self.assertEqual(
            schema["properties"]["writer_route_slot"],
            {
                "type": ["string", "null"],
                "enum": ["writer.c0-batch", "writer.c1", "writer.c2", "writer.c3", None],
            },
        )
        self.assertEqual(
            schema["properties"]["availability"]["additionalProperties"]["enum"]
            ,
            ["available", "unavailable", "unknown"],
        )
        evidence = schema["properties"]["primary_failure_evidence"]
        self.assertTrue(evidence["uniqueItems"])
        self.assertEqual(evidence["items"]["type"], "string")
        writer_identity = schema["properties"]["writer_identity"]
        self.assertEqual(writer_identity["type"], ["object", "null"])
        self.assertEqual(set(writer_identity["required"]), {"provider", "runtime_provider", "model"})
        self.assertEqual(set(writer_identity["properties"]), {"provider", "runtime_provider", "model"})
        self.assertTrue(all(item["type"] == "string" for item in writer_identity["properties"].values()))
        self.assertFalse(writer_identity["additionalProperties"])
        self.assertEqual(schema["properties"]["candidate_id"]["type"], ["string", "null"])

    def test_route_decision_contract_has_exact_required_surface(self):
        schema = self.load("route-decision.v1.schema.json")
        expected = {
            "router_api_version",
            "request_id",
            "profile_id",
            "route_slot",
            "decision_status",
            "enforcement_status",
            "selected_route",
            "fallback_used",
            "fallback_evidence",
            "independent_validator_source",
            "config_digest",
            "limitations",
        }
        self.assertEqual(set(schema["required"]), expected)
        self.assertEqual(set(schema["properties"]), expected)
        self.assertEqual(schema["properties"]["decision_status"]["enum"], ["selected", "blocked", "unknown"])
        self.assertEqual(schema["properties"]["enforcement_status"]["enum"], ["verified", "advisory", "not-executed"])
        self.assertEqual(
            schema["properties"]["independent_validator_source"]["enum"],
            ["router-selected", "openai-complexity-map", "caller-required", "not-applicable"],
        )
        self.assertEqual(schema["properties"]["config_digest"]["pattern"], r"^[0-9a-f]{64}$")
        self.assertEqual(schema["properties"]["selected_route"]["type"], ["object", "null"])
        self.assertEqual(
            set(schema["properties"]["selected_route"]["required"]),
            {"provider", "runtime_provider", "model", "reasoning", "reasoning_delivery"},
        )
        self.assertFalse(schema["properties"]["selected_route"]["additionalProperties"])

    def test_config_contract_and_example_are_exact_and_secret_free(self):
        schema = self.load("model-router-config.v1.schema.json")
        expected = {
            "schema_version",
            "router_api_version",
            "config_id",
            "active_profile",
            "project_profile_dirs",
            "updated_reason",
        }
        self.assertEqual(set(schema["required"]), expected)
        self.assertEqual(set(schema["properties"]), expected)
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(schema["properties"]["router_api_version"]["const"], "route/v1")
        active_profile = schema["properties"]["active_profile"]
        self.assertEqual(active_profile["type"], "string")
        self.assertEqual(active_profile["minLength"], 1)
        self.assertEqual(active_profile["pattern"], r"^(?!.*[\u0000-\u001f\u007f])\S(?:.*\S)?$")
        self.assertNotIn("const", active_profile)
        dirs = schema["properties"]["project_profile_dirs"]["items"]
        self.assertEqual(
            dirs["pattern"],
            r'^[^\\/:*?"<>|\u0000-\u001f\u007f]+(?:[/\\][^\\/:*?"<>|\u0000-\u001f\u007f]+)*$',
        )
        self.assertEqual(
            dirs["not"]["pattern"],
            r"(^|[/\\])(?:\.|\.\.)(?=$|[/\\])",
        )
        example = self.load("model-router-config.example.json")
        self.assertEqual(example["active_profile"], "openai-glm5.3-deepseek-fallback-2026-08-28")
        self.assertEqual(example["project_profile_dirs"], [".ai-native/profiles"])
        self.assertNotRegex(json.dumps(example).casefold(), r"credential|secret|token|endpoint|command|script")

    def test_config_string_schema_patterns_match_control_and_space_boundary_samples(self):
        schema = self.load("model-router-config.v1.schema.json")
        for field in ("config_id", "active_profile", "updated_reason"):
            pattern = re.compile(schema["properties"][field]["pattern"])
            for value in ("internal\t tab", "internal\nnewline", "internal\x7fdel"):
                with self.subTest(field=field, value=repr(value)):
                    self.assertIsNone(pattern.fullmatch(value))
            with self.subTest(field=field, value="internal spaces"):
                self.assertIsNotNone(pattern.fullmatch("internal spaces"))


class AdrContractTests(unittest.TestCase):
    def test_adr_names_governance_skill_and_rejects_provider_router_skill(self):
        adr = (ROOT / "docs" / "adr" / "0001-decouple-provider-router-skill.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("existing development-team governance Skill", adr)
        self.assertNotIn("existing provider-router Skill", adr)


class ConfigValidationTests(unittest.TestCase):
    def test_v2_config_validation_and_version_dispatch_are_explicit(self):
        payload = valid_config_v2()
        self.assertEqual(validate_config_v2(payload), payload)
        with self.assertRaises(ValueError):
            validate_config(payload)
        self.assertEqual(validate_config_versioned(payload), payload)
        self.assertEqual(validate_config_for_version(payload, "route/v2"), payload)
        self.assertRegex(config_digest(payload), r"^[0-9a-f]{64}$")

    def test_mixed_config_versions_fail_closed(self):
        for payload in (
            valid_config_v2(router_api_version="route/v1"),
            valid_config(schema_version=2),
            valid_config(router_api_version="route/v2"),
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_config_versioned(payload)
        with self.assertRaises(ValueError):
            validate_config_for_version(valid_config(), "route/v2")
        with self.assertRaises(ValueError):
            validate_config_for_version(valid_config_v2(), "route/v1")

    def test_generic_validation_accepts_alternate_active_profile(self):
        payload = valid_config(active_profile="team-fast")
        self.assertEqual(validate_config(payload), payload)

    def test_config_string_fields_reject_whitespace_boundaries(self):
        for field in ("config_id", "active_profile", "updated_reason"):
            for value in ("", "   ", " leading", "trailing ", "\tvalue", "value\n"):
                with self.subTest(field=field, value=repr(value)), self.assertRaises(ValueError):
                    validate_config({**valid_config(), field: value})

    def test_config_string_helper_rejects_internal_controls_and_accepts_internal_spaces(self):
        for field in ("config_id", "active_profile", "updated_reason"):
            for value in ("internal\t tab", "internal\nnewline", "internal\x7fdel"):
                with self.subTest(field=field, value=repr(value)), self.assertRaises(ValueError):
                    validate_config({**valid_config(), field: value})
            with self.subTest(field=field):
                self.assertEqual(
                    validate_config({**valid_config(), field: "internal spaces"})[field],
                    "internal spaces",
                )

    def test_valid_config_is_normalized_without_mutating_input(self):
        payload = valid_config()
        normalized = validate_config(payload)
        self.assertEqual(normalized, payload)
        self.assertIsNot(normalized, payload)

    def test_config_requires_exact_keys_and_versions(self):
        for bad in (
            {**valid_config(), "extra": True},
            {key: value for key, value in valid_config().items() if key != "config_id"},
            {**valid_config(), "schema_version": "1"},
            {**valid_config(), "schema_version": 2},
            {**valid_config(), "router_api_version": "route/v2"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_config(bad)

    def test_forbidden_keys_are_rejected_recursively_case_insensitively(self):
        for key in ("credentials", "secret", "tokens", "endpoint", "command", "script", "overrides"):
            with self.subTest(key=key), self.assertRaises(ValueError) as caught:
                validate_config({**valid_config(), "updated_reason": {"nested": {key: "x"}}})
            self.assertIn("forbidden key", str(caught.exception))

    def test_project_profile_dirs_reject_unsafe_relative_paths(self):
        unsafe = [
            "",
            "/absolute",
            "C:/drive",
            "C:\\drive",
            "\\\\server\\share",
            "../parent",
            "a/../b",
            "a//b",
            "a/./b",
            "a\tb",
            "a\nb",
            "a\x7fb",
            "a:b",
        ]
        for path in unsafe:
            with self.subTest(path=repr(path)), self.assertRaises(ValueError):
                validate_config({**valid_config(), "project_profile_dirs": [path]})

    def test_project_profile_dirs_schema_samples_match_helper_boundary_rule(self):
        schema = json.loads((ASSET_DIR / "model-router-config.v1.schema.json").read_text(encoding="utf-8"))
        safe_path = re.compile(schema["properties"]["project_profile_dirs"]["items"]["pattern"])
        forbidden_segments = re.compile(schema["properties"]["project_profile_dirs"]["items"]["not"]["pattern"])
        samples = {
            ".": False,
            "..": False,
            "a/.": False,
            "a\\.": False,
            "a/../b": False,
            "a\\..\\b": False,
            "a/b": True,
            ".ai-native/profiles": True,
            "a b": True,
            "a\x7fb": False,
        }
        for path, accepted in samples.items():
            with self.subTest(path=repr(path)):
                self.assertEqual(
                    safe_path.fullmatch(path) is not None and forbidden_segments.search(path) is None,
                    accepted,
                )
                self.assertEqual((self._validate_path(path)), accepted)

    def _validate_path(self, path):
        try:
            validate_config({**valid_config(), "project_profile_dirs": [path]})
        except ValueError:
            return False
        return True

    def test_config_digest_is_canonical_and_deterministic(self):
        first = valid_config()
        second = {
            "updated_reason": "test fixture",
            "project_profile_dirs": [".ai-native/profiles"],
            "active_profile": "openai-glm5.3-deepseek-fallback-2026-08-28",
            "config_id": "test-config",
            "router_api_version": "route/v1",
            "schema_version": 1,
        }
        self.assertEqual(config_digest(first), config_digest(second))

    def test_resolution_precedence_and_conventional_missing_path(self):
        with temporary_contract_project() as temp:
            cwd = Path(temp)
            injected = cwd / "injected.json"
            explicit = cwd / "explicit.json"
            self.assertIsNone(resolve_config_path(None, None, cwd))
            self.assertEqual(resolve_config_path(None, injected, cwd), injected)
            self.assertEqual(resolve_config_path(explicit, injected, cwd), explicit)
            self.assertEqual(resolve_config_path(None, None, cwd), None)
            conventional = cwd / ".ai-native" / "model-router.json"
            conventional.parent.mkdir()
            conventional.write_text("{}", encoding="utf-8")
            self.assertEqual(resolve_config_path(None, None, cwd), conventional)

    def test_explicit_and_injected_paths_must_be_path_values(self):
        with temporary_contract_project() as temp:
            cwd = Path(temp)
            for bad in ("", 3, object()):
                with self.subTest(bad=repr(bad)), self.assertRaises(ValueError):
                    resolve_config_path(bad, None, cwd)
            with self.assertRaises(ValueError):
                resolve_config_path(None, "", cwd)


class LegacyMigrationTests(unittest.TestCase):
    def legacy(self, **overrides):
        payload = {
            "profile_id": "openai-glm5.3-deepseek-fallback-2026-08-28",
            "default_active": False,
            "activation": "explicit-owner-selection",
            "evidence_date": "2026-08-28",
            "control_plane": {"model": "gpt-5.6-sol", "reasoning": "high"},
            "writers": {"C0_batch": {"model": "gpt-5.6-luna", "reasoning": "max"}},
            "validators": {},
            "high_volume_deterministic_fallback": {},
        }
        payload.update(overrides)
        return payload

    def test_migration_selects_profile_only_and_validates_v1(self):
        migrated = migrate_legacy_profile(self.legacy())
        self.assertEqual(
            migrated,
            {
                "schema_version": 1,
                "router_api_version": "route/v1",
                "config_id": "migrated-openai-glm5.3-deepseek-fallback-2026-08-28",
                "active_profile": "openai-glm5.3-deepseek-fallback-2026-08-28",
                "project_profile_dirs": [],
                "updated_reason": "Migrated from legacy embedded profile; explicit profile selection remains required.",
            },
        )
        self.assertEqual(validate_config(migrated), migrated)

    def test_migration_rejects_active_by_default_or_ambiguous_legacy_profile(self):
        for bad in (
            self.legacy(default_active=True),
            self.legacy(activation="automatic"),
            self.legacy(default_active="false"),
            self.legacy(profile_id=""),
            {key: value for key, value in self.legacy().items() if key != "default_active"},
            {key: value for key, value in self.legacy().items() if key != "activation"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                migrate_legacy_profile(bad)

    def test_migration_rejects_unverified_profile_id_and_boundary_whitespace(self):
        for profile_id in (
            "openai-zai-deepseek-2026-08-28",
            " openai-glm5.3-deepseek-fallback-2026-08-28",
            "openai-glm5.3-deepseek-fallback-2026-08-28 ",
            "   ",
        ):
            with self.subTest(profile_id=repr(profile_id)), self.assertRaises(ValueError):
                migrate_legacy_profile(self.legacy(profile_id=profile_id))


class AtomicConfigTests(unittest.TestCase):
    def test_atomic_write_backup_stale_refusal_and_rollback(self):
        with temporary_contract_project() as temp:
            directory = Path(temp)
            path = directory / "model-router.json"
            original = json.dumps(valid_config(updated_reason="old"), indent=2).encode() + b"\n"
            path.write_bytes(original)
            original_hash = sha256_bytes(original)
            receipt = atomic_write_config(
                path,
                valid_config(updated_reason="new"),
                expected_preimage_sha256=original_hash,
            )
            self.assertEqual(receipt["preimage_sha256"], original_hash)
            backup = Path(receipt["backup_path"])
            self.assertTrue(backup.exists())
            self.assertEqual(
                backup.name,
                f".{path.name}.backup-{sha256_bytes(backup.read_bytes())}",
            )
            self.assertEqual(receipt["backup_sha256"], sha256_bytes(backup.read_bytes()))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["updated_reason"], "new")
            with self.assertRaises(ValueError):
                atomic_write_config(path, valid_config(updated_reason="bad"), expected_preimage_sha256=original_hash)
            rollback_receipt = rollback_config(
                path,
                backup,
                expected_current_sha256=sha256_bytes(path.read_bytes()),
                expected_backup_sha256=original_hash,
            )
            self.assertEqual(rollback_receipt["restored_sha256"], original_hash)
            self.assertEqual(path.read_bytes(), original)

    def test_atomic_write_requires_existing_parent_and_leaves_no_temp_residue(self):
        with temporary_contract_project() as temp:
            directory = Path(temp)
            missing_parent = directory / "missing" / "config.json"
            with self.assertRaises(ValueError):
                atomic_write_config(missing_parent, valid_config())
            path = directory / "config.json"
            atomic_write_config(path, valid_config())
            self.assertEqual(list(directory.glob("*.tmp-*")), [])
            self.assertEqual(list(directory.glob(".*.tmp-*")), [])

    def test_rollback_fails_closed_on_current_hash_mismatch_and_foreign_backup(self):
        with temporary_contract_project() as temp:
            directory = Path(temp)
            path = directory / "config.json"
            atomic_write_config(path, valid_config())
            foreign = directory / "foreign.json"
            foreign.write_bytes(path.read_bytes())
            with self.assertRaises(ValueError):
                rollback_config(
                    path,
                    foreign,
                    expected_current_sha256=sha256_bytes(path.read_bytes()),
                    expected_backup_sha256=sha256_bytes(foreign.read_bytes()),
                )

    def test_rollback_rejects_malformed_or_uppercase_backup_suffix_and_foreign_valid_config(self):
        with temporary_contract_project() as temp:
            directory = Path(temp)
            path = directory / "config.json"
            atomic_write_config(path, valid_config())
            current_hash = sha256_bytes(path.read_bytes())
            backup_data = path.read_bytes()
            backup_hash = sha256_bytes(backup_data)
            candidates = (
                directory / f".{path.name}.backup-{backup_hash.upper()}",
                directory / f".{path.name}.backup-not-a-sha",
                directory / f".{path.name}.backup-{'0' * 64}",
            )
            for candidate in candidates:
                candidate.write_bytes(backup_data)
                with self.subTest(candidate=candidate.name), self.assertRaises(ValueError):
                    rollback_config(
                        path,
                        candidate,
                        expected_current_sha256=current_hash,
                        expected_backup_sha256=backup_hash,
                    )
                candidate.unlink()

            foreign_data = json.dumps(valid_config(config_id="foreign")).encode("utf-8")
            foreign_hash = sha256_bytes(foreign_data)
            foreign = directory / f".{path.name}.backup-{foreign_hash}"
            foreign.write_bytes(foreign_data)
            with self.assertRaises(ValueError):
                rollback_config(
                    path,
                    foreign,
                    expected_current_sha256=current_hash,
                    expected_backup_sha256=backup_hash,
                )


class CliTests(unittest.TestCase):
    module_path = ROOT / "skills" / "ai-native-model-router" / "scripts" / "router_config.py"

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(self.module_path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_validate_and_digest_cli_emit_json(self):
        with temporary_contract_project() as temp:
            config = Path(temp) / "config.json"
            config.write_text(json.dumps(valid_config()), encoding="utf-8")
            validated = self.run_cli("validate", "--config", str(config))
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertEqual(json.loads(validated.stdout), valid_config())
            digested = self.run_cli("digest", "--config", str(config))
            self.assertEqual(digested.returncode, 0, digested.stderr)
            self.assertEqual(json.loads(digested.stdout)["config_digest"], config_digest(valid_config()))

    def test_migrate_write_and_rollback_cli_paths(self):
        with temporary_contract_project() as temp:
            directory = Path(temp)
            legacy = directory / "legacy.json"
            migrated = directory / "migrated.json"
            config = directory / "config.json"
            payload = LegacyMigrationTests().legacy()
            legacy.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_cli("migrate-legacy", "--input", str(legacy), "--output", str(migrated))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["active_profile"], payload["profile_id"])
            config.write_text(json.dumps(valid_config(updated_reason="old")), encoding="utf-8")
            write_payload = directory / "payload.json"
            write_payload.write_text(json.dumps(valid_config(updated_reason="new")), encoding="utf-8")
            before = sha256_bytes(config.read_bytes())
            written = self.run_cli("write", "--config", str(config), "--payload", str(write_payload), "--expected-preimage-sha256", before)
            self.assertEqual(written.returncode, 0, written.stderr)
            receipt = json.loads(written.stdout)
            rolled = self.run_cli("rollback", "--config", str(config), "--backup", receipt["backup_path"], "--expected-current-sha256", sha256_bytes(config.read_bytes()), "--expected-backup-sha256", receipt["backup_sha256"])
            self.assertEqual(rolled.returncode, 0, rolled.stderr)
            self.assertEqual(sha256_bytes(config.read_bytes()), before)

            migrated.write_bytes(b"preserve-me")
            refused = self.run_cli("migrate-legacy", "--input", str(legacy), "--output", str(migrated))
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(migrated.read_bytes(), b"preserve-me")

    def test_cli_failure_is_nonzero_with_diagnostics_on_stderr(self):
        result = self.run_cli("validate", "--config", "missing-config.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
