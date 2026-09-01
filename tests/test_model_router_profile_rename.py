import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "skills" / "ai-native-model-router"
PROFILE_DIR = ROUTER / "assets" / "profiles"
SCRIPT = ROUTER / "scripts" / "resolve_route.py"
BUNDLED_PROFILE_ID = "gpt5.6"
RETIRED_PROFILE_ID = "glm+deepseek"
OLDER_RETIRED_PROFILE_IDS = (
    "openai-glm5.3-deepseek-fallback-2026-08-28",
    "openai-gpt5.6-validator-assurance-2026-08-31",
)
RETIRED_PROFILE_IDS = (RETIRED_PROFILE_ID, *OLDER_RETIRED_PROFILE_IDS)
EVIDENCE = [
    "model-not-found",
    "authenticated-provider-outage",
    "quota-exhaustion",
    "repeated-bounded-transport-failure",
]

sys.path.insert(0, str(ROUTER / "scripts"))

from resolve_route import (  # noqa: E402
    load_profile,
    resolve_route,
    validate_profile,
    validate_profile_versioned,
    validate_route_request,
    validate_route_request_v2,
)
from router_config import (  # noqa: E402
    migrate_legacy_profile,
    validate_config,
    validate_config_v2,
)


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )


def route_request(profile_id, router_api_version):
    if router_api_version == "route/v2":
        return {
            "router_api_version": "route/v2",
            "request_id": "profile-removal-v2",
            "route_slot": "writer.c1",
            "writer_route_slot": None,
            "profile_id": profile_id,
            "explicit_profile_selection": True,
            "explicit_high_volume_selection": False,
            "availability": {"openai/gpt-5.6-luna": "available"},
            "route_failure_evidence": {},
            "risk_level": None,
            "writer_identity": None,
            "candidate_id": None,
        }
    return {
        "router_api_version": "route/v1",
        "request_id": "profile-removal-v1",
        "route_slot": "writer.c1",
        "writer_route_slot": None,
        "profile_id": profile_id,
        "explicit_profile_selection": True,
        "explicit_high_volume_selection": False,
        "availability": {"openai/gpt-5.6-luna": "available"},
        "primary_failure_evidence": [],
        "writer_identity": None,
        "candidate_id": "candidate-profile-removal-v1",
    }


def project_config(profile_id, router_api_version, project_profile_dirs=None):
    return {
        "schema_version": 2 if router_api_version == "route/v2" else 1,
        "router_api_version": router_api_version,
        "config_id": "profile-removal-test",
        "active_profile": profile_id,
        "project_profile_dirs": project_profile_dirs or [],
        "updated_reason": "profile removal negative test",
    }


def custom_v1_profile(profile_id="custom-v1"):
    """Build a bounded project-only v1 fixture from the preserved v2 slots."""

    profile = json.loads(
        (PROFILE_DIR / f"{BUNDLED_PROFILE_ID}.json").read_text(encoding="utf-8")
    )
    profile["schema_version"] = 1
    profile["profile_id"] = profile_id
    profile["evidence_date"] = "2026-08-28"
    del profile["slots"]["validator.assurance"]
    profile["slots"]["validator.independent"] = {
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
        "accepted_primary_unavailable_evidence": EVIDENCE,
        "independent_validator_source": "openai-complexity-map",
    }
    return profile


@contextmanager
def temporary_project():
    root = ROOT / "tests" / f".profile-removal-{uuid.uuid4().hex}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root)


def write_project_profile(project, profile, directory="profiles"):
    profile_dir = project / directory
    profile_dir.mkdir(parents=True, exist_ok=True)
    path = profile_dir / f"{profile['profile_id']}.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    return path


def create_directory_link(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            raise
    result = subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not link.is_dir():
        raise OSError("directory symlink and junction are unsupported")


def remove_directory_link(link):
    if link.is_symlink():
        link.unlink()
    elif sys.platform == "win32" and os.path.lexists(link):
        subprocess.run(
            ["cmd.exe", "/c", "rmdir", str(link)],
            capture_output=True,
            check=True,
        )
    elif os.path.lexists(link):
        link.unlink()


class ModelRouterProfileRemovalTests(unittest.TestCase):
    def test_bundled_profile_filenames_and_internal_ids_are_exact(self):
        self.assertEqual(
            sorted(path.name for path in PROFILE_DIR.glob("*.json")),
            ["gpt5.6.json"],
        )
        profile = json.loads(
            (PROFILE_DIR / f"{BUNDLED_PROFILE_ID}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(profile["profile_id"], BUNDLED_PROFILE_ID)
        self.assertEqual(profile["schema_version"], 2)

    def test_list_profiles_returns_only_the_bundled_v2_id(self):
        result = run_cli("list-profiles")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"profiles": [BUNDLED_PROFILE_ID]})

    def test_gpt56_validates_and_resolves_through_route_v2(self):
        validated = run_cli("validate-profile", "--profile", BUNDLED_PROFILE_ID)
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertEqual(json.loads(validated.stdout)["profile_id"], BUNDLED_PROFILE_ID)

        resolved = run_cli(
            "resolve",
            "--request",
            json.dumps(route_request(BUNDLED_PROFILE_ID, "route/v2")),
        )
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        decision = json.loads(resolved.stdout)
        self.assertEqual(decision["profile_id"], BUNDLED_PROFILE_ID)
        self.assertEqual(decision["router_api_version"], "route/v2")
        self.assertEqual(decision["enforcement_status"], "not-executed")

    def test_gpt56_preserves_explicit_high_volume_writer_routes(self):
        profile = json.loads(
            (PROFILE_DIR / f"{BUNDLED_PROFILE_ID}.json").read_text(encoding="utf-8")
        )
        high_volume = profile["slots"]["writer.high-volume-deterministic"]
        self.assertEqual(
            high_volume["primary"],
            {
                "provider": "zai",
                "model": "glm-5.3-flash",
                "reasoning": "max",
                "reasoning_delivery": "provider-default",
            },
        )
        self.assertEqual(
            high_volume["fallback"],
            {
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "reasoning": "max",
                "reasoning_delivery": "explicit",
            },
        )
        self.assertTrue(high_volume["requires_explicit_task_selection"])

    def test_retired_ids_are_rejected_by_valid_requests_before_resolution(self):
        for profile_id in RETIRED_PROFILE_IDS:
            for version, validator in (
                ("route/v1", validate_route_request),
                ("route/v2", validate_route_request_v2),
            ):
                with self.subTest(operation="request", profile_id=profile_id, version=version):
                    with self.assertRaisesRegex(ValueError, "retired"):
                        validator(route_request(profile_id, version))
                with self.subTest(operation="resolve", profile_id=profile_id, version=version):
                    with self.assertRaisesRegex(ValueError, "retired"):
                        resolve_route(route_request(profile_id, version))

    def test_retired_request_does_not_read_config_or_profile(self):
        request = route_request(RETIRED_PROFILE_ID, "route/v1")
        with patch("resolve_route.load_config", side_effect=AssertionError("config was read")):
            with self.assertRaisesRegex(ValueError, "retired"):
                resolve_route(request)

    def test_retired_ids_are_rejected_by_matching_config_validation(self):
        for profile_id in RETIRED_PROFILE_IDS:
            for version, validator in (
                ("route/v1", validate_config),
                ("route/v2", validate_config_v2),
            ):
                with self.subTest(profile_id=profile_id, version=version):
                    with self.assertRaisesRegex(ValueError, "retired"):
                        validator(project_config(profile_id, version))

    def test_retired_ids_are_rejected_from_explicit_injected_and_conventional_configs(self):
        for profile_id in RETIRED_PROFILE_IDS:
            for version in ("route/v1", "route/v2"):
                safe_request_profile_id = (
                    BUNDLED_PROFILE_ID if version == "route/v2" else "safe-config-request-v1"
                )
                request = route_request(safe_request_profile_id, version)
                config = project_config(profile_id, version)
                with temporary_project() as project:
                    explicit_path = project / "explicit-config.json"
                    explicit_path.write_text(json.dumps(config), encoding="utf-8")
                    conventional_path = project / ".ai-native" / "model-router.json"
                    conventional_path.parent.mkdir()
                    conventional_path.write_text(json.dumps(config), encoding="utf-8")
                    sources = (
                        ("explicit", {"config_path": explicit_path}),
                        ("injected", {"injected_config": config}),
                        ("conventional", {}),
                    )
                    for source, kwargs in sources:
                        with self.subTest(profile_id=profile_id, version=version, source=source):
                            with self.assertRaisesRegex(ValueError, "active_profile is retired"):
                                resolve_route(request, cwd=project, **kwargs)

    def test_retired_project_profiles_are_rejected_during_discovery(self):
        for profile_id in RETIRED_PROFILE_IDS:
            with temporary_project() as project:
                write_project_profile(project, custom_v1_profile(profile_id))
                config_path = project / "discovery-config.json"
                config_path.write_text(
                    json.dumps(project_config("safe-project-profile", "route/v1", ["profiles"])),
                    encoding="utf-8",
                )
                discovered = run_cli(
                    "list-profiles",
                    "--config",
                    str(config_path),
                    "--project-root",
                    str(project),
                )
                self.assertNotEqual(discovered.returncode, 0)
                self.assertEqual(discovered.stdout, "")
                self.assertIn("retired", discovered.stderr)

    def test_retired_ids_are_rejected_by_direct_profile_load_and_validation(self):
        for profile_id in RETIRED_PROFILE_IDS:
            with self.subTest(operation="load", profile_id=profile_id):
                with self.assertRaisesRegex(ValueError, "retired"):
                    load_profile(profile_id)
            payload = custom_v1_profile(profile_id)
            with self.subTest(operation="validate", profile_id=profile_id):
                with self.assertRaisesRegex(ValueError, "retired"):
                    validate_profile(payload)
            with self.subTest(operation="validate-versioned", profile_id=profile_id):
                with self.assertRaisesRegex(ValueError, "retired"):
                    validate_profile_versioned(payload)

    def test_migration_helpers_reject_retired_ids_without_mapping(self):
        for profile_id in RETIRED_PROFILE_IDS:
            legacy = {
                "profile_id": profile_id,
                "default_active": False,
                "activation": "explicit-owner-selection",
                "evidence_date": "2026-08-28",
                "control_plane": {"model": "gpt-5.6-sol", "reasoning": "high"},
                "writers": {"C0_batch": {"model": "gpt-5.6-luna", "reasoning": "max"}},
                "validators": {},
                "high_volume_deterministic_fallback": {},
            }
            with self.subTest(profile_id=profile_id):
                with self.assertRaisesRegex(ValueError, "retired"):
                    migrate_legacy_profile(legacy)

    def test_custom_safe_route_v1_profile_lists_validates_and_resolves(self):
        with temporary_project() as project:
            profile = custom_v1_profile()
            write_project_profile(project, profile)
            config = project_config(profile["profile_id"], "route/v1", ["profiles"])
            config_path = project / "config-v1.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            listed = run_cli(
                "list-profiles",
                "--config",
                str(config_path),
                "--project-root",
                str(project),
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(
                json.loads(listed.stdout),
                {"profiles": ["custom-v1", BUNDLED_PROFILE_ID]},
            )

            validated = run_cli(
                "validate-profile",
                "--profile",
                profile["profile_id"],
                "--config",
                str(config_path),
                "--project-root",
                str(project),
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertEqual(json.loads(validated.stdout)["schema_version"], 1)

            decision = resolve_route(
                route_request(profile["profile_id"], "route/v1"),
                cwd=project,
                config_path=config_path,
            )
            self.assertEqual(decision["profile_id"], profile["profile_id"])
            self.assertEqual(decision["router_api_version"], "route/v1")
            self.assertEqual(decision["selected_route"]["model"], "gpt-5.6-luna")

    def test_list_profiles_rejects_external_profile_directory_link(self):
        external = ROOT / "tests" / f".profile-removal-external-{uuid.uuid4().hex}"
        external.mkdir()
        try:
            with temporary_project() as project:
                profile = custom_v1_profile("external-custom-v1")
                (external / f"{profile['profile_id']}.json").write_text(
                    json.dumps(profile), encoding="utf-8"
                )
                link = project / "linked-profiles"
                try:
                    try:
                        create_directory_link(link, external)
                    except (OSError, NotImplementedError):
                        self.skipTest("directory symlinks and junctions are unsupported")

                    config_path = project / "config-v1.json"
                    config_path.write_text(
                        json.dumps(
                            project_config(
                                profile["profile_id"], "route/v1", ["linked-profiles"]
                            )
                        ),
                        encoding="utf-8",
                    )
                    result = run_cli(
                        "list-profiles",
                        "--config",
                        str(config_path),
                        "--project-root",
                        str(project),
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(
                        result.stderr.strip(),
                        "ERROR: project profile directory resolves outside project root",
                    )
                    self.assertNotIn(profile["profile_id"], result.stdout)
                finally:
                    remove_directory_link(link)
        finally:
            shutil.rmtree(external)

    def test_mixed_v1_and_v2_profile_versions_fail_closed(self):
        with temporary_project() as project:
            profile = custom_v1_profile()
            write_project_profile(project, profile)
            v2_config_path = project / "config-v2.json"
            v2_config_path.write_text(
                json.dumps(project_config(profile["profile_id"], "route/v2", ["profiles"])),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                resolve_route(
                    route_request(profile["profile_id"], "route/v2"),
                    cwd=project,
                    config_path=v2_config_path,
                )
        with self.assertRaises(ValueError):
            resolve_route(route_request(BUNDLED_PROFILE_ID, "route/v1"))

    def test_profile_file_presence_never_auto_activates_a_project_profile(self):
        with temporary_project() as project:
            write_project_profile(project, custom_v1_profile())
            listed = run_cli("list-profiles", "--project-root", str(project))
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(json.loads(listed.stdout), {"profiles": [BUNDLED_PROFILE_ID]})
            with self.assertRaises(ValueError):
                resolve_route(
                    route_request("custom-v1", "route/v1"),
                    cwd=project,
                )

    def test_config_example_is_only_the_v2_gpt56_selection(self):
        example = json.loads(
            (ROUTER / "assets" / "model-router-config.example.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            example,
            {
                "schema_version": 2,
                "router_api_version": "route/v2",
                "config_id": "project-router-v2-2026-08-31",
                "active_profile": BUNDLED_PROFILE_ID,
                "project_profile_dirs": [".ai-native/profiles"],
                "updated_reason": "Explicit project profile selection for route/v2.",
            },
        )

    def test_active_docs_do_not_advertise_the_retired_profile(self):
        active_docs = (
            ROOT / "README.md",
            ROOT / "README.zh-CN.md",
            ROUTER / "SKILL.md",
            ROUTER / "references" / "configuration.md",
            ROUTER / "references" / "interface.md",
            ROUTER / "references" / "provider-evidence.md",
        )
        for path in active_docs:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertNotIn(RETIRED_PROFILE_ID, text)
                self.assertNotIn("assets/profiles/glm+deepseek.json", text)


if __name__ == "__main__":
    unittest.main()
