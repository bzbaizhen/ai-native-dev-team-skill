import json
import shutil
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
import uuid


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "skills" / "ai-native-model-router"
PROFILE_DIR = ROUTER / "assets" / "profiles"
SCRIPT = ROUTER / "scripts" / "resolve_route.py"
V1_PROFILE_ID = "glm+deepseek"
V2_PROFILE_ID = "gpt5.6"
OLD_REMOVED_PROFILE_IDS = (
    "openai-glm5.3-deepseek-fallback-2026-08-28",
    "openai-gpt5.6-validator-assurance-2026-08-31",
)

sys.path.insert(0, str(ROUTER / "scripts"))

from resolve_route import load_profile, resolve_route  # noqa: E402
from router_config import validate_config, validate_config_v2  # noqa: E402


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
            "request_id": "profile-rename-v2",
            "route_slot": "validator.assurance",
            "writer_route_slot": "writer.c1",
            "profile_id": profile_id,
            "explicit_profile_selection": True,
            "explicit_high_volume_selection": False,
            "availability": {"openai/gpt-5.6-luna": "available"},
            "route_failure_evidence": {},
            "risk_level": "R1",
            "writer_identity": {
                "provider": "openai",
                "runtime_provider": "custom",
                "model": "gpt-5.6-luna",
            },
            "candidate_id": "candidate-profile-rename-v2",
        }
    return {
        "router_api_version": "route/v1",
        "request_id": "profile-rename-v1",
        "route_slot": "writer.c1",
        "writer_route_slot": None,
        "profile_id": profile_id,
        "explicit_profile_selection": True,
        "explicit_high_volume_selection": False,
        "availability": {"openai/gpt-5.6-luna": "available"},
        "primary_failure_evidence": [],
        "writer_identity": None,
        "candidate_id": "candidate-profile-rename-v1",
    }


def project_config(profile_id, router_api_version):
    return {
        "schema_version": 2 if router_api_version == "route/v2" else 1,
        "router_api_version": router_api_version,
        "config_id": "retired-profile-test",
        "active_profile": profile_id,
        "project_profile_dirs": ["profiles"],
        "updated_reason": "retired profile negative test",
    }


@contextmanager
def retired_profile_project():
    root = ROOT / "tests" / f".retired-profile-{uuid.uuid4().hex}"
    root.mkdir()
    try:
        profile_dir = root / "profiles"
        profile_dir.mkdir()
        for retired_id, bundled_id in zip(
            OLD_REMOVED_PROFILE_IDS, (V1_PROFILE_ID, V2_PROFILE_ID)
        ):
            profile = json.loads(
                (PROFILE_DIR / f"{bundled_id}.json").read_text(encoding="utf-8")
            )
            profile["profile_id"] = retired_id
            (profile_dir / f"{retired_id}.json").write_text(
                json.dumps(profile), encoding="utf-8"
            )
        yield root
    finally:
        shutil.rmtree(root)


class ModelRouterProfileRenameTests(unittest.TestCase):
    def test_bundled_profile_filenames_and_internal_ids_are_exact(self):
        self.assertEqual(
            sorted(path.name for path in PROFILE_DIR.glob("*.json")),
            ["glm+deepseek.json", "gpt5.6.json"],
        )
        for profile_id, schema_version in ((V1_PROFILE_ID, 1), (V2_PROFILE_ID, 2)):
            profile = json.loads((PROFILE_DIR / f"{profile_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["profile_id"], profile_id)
            self.assertEqual(profile["schema_version"], schema_version)

    def test_list_profiles_returns_only_new_ids_in_deterministic_order(self):
        result = run_cli("list-profiles")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"profiles": [V1_PROFILE_ID, V2_PROFILE_ID]})

    def test_new_ids_validate_and_resolve_for_matching_route_versions(self):
        for profile_id, router_api_version in (
            (V1_PROFILE_ID, "route/v1"),
            (V2_PROFILE_ID, "route/v2"),
        ):
            with self.subTest(profile_id=profile_id):
                validated = run_cli("validate-profile", "--profile", profile_id)
                self.assertEqual(validated.returncode, 0, validated.stderr)
                self.assertEqual(json.loads(validated.stdout)["profile_id"], profile_id)

                resolved = run_cli(
                    "resolve",
                    "--request",
                    json.dumps(route_request(profile_id, router_api_version)),
                )
                self.assertEqual(resolved.returncode, 0, resolved.stderr)
                decision = json.loads(resolved.stdout)
                self.assertEqual(decision["profile_id"], profile_id)
                self.assertEqual(decision["router_api_version"], router_api_version)
                self.assertEqual(decision["enforcement_status"], "not-executed")

    def test_removed_ids_fail_closed_for_validation_and_resolution(self):
        for profile_id in OLD_REMOVED_PROFILE_IDS:
            with self.subTest(operation="validate", profile_id=profile_id):
                validated = run_cli("validate-profile", "--profile", profile_id)
                self.assertNotEqual(validated.returncode, 0)
                self.assertEqual(validated.stdout, "")
                self.assertIn("ERROR:", validated.stderr)
            for router_api_version in ("route/v1", "route/v2"):
                with self.subTest(operation="resolve", profile_id=profile_id, router_api_version=router_api_version):
                    resolved = run_cli(
                        "resolve",
                        "--request",
                        json.dumps(route_request(profile_id, router_api_version)),
                    )
                    self.assertNotEqual(resolved.returncode, 0)
                    self.assertEqual(resolved.stdout, "")
                    self.assertIn("ERROR:", resolved.stderr)

    def test_matching_retired_ids_are_rejected_by_v1_and_v2_config_validation(self):
        for router_api_version, validator in (
            ("route/v1", validate_config),
            ("route/v2", validate_config_v2),
        ):
            for profile_id in OLD_REMOVED_PROFILE_IDS:
                with self.subTest(router_api_version=router_api_version, profile_id=profile_id):
                    with self.assertRaisesRegex(ValueError, "retired"):
                        validator(project_config(profile_id, router_api_version))

    def test_matching_retired_project_profiles_are_rejected_by_load_and_validate_profile(self):
        with retired_profile_project() as project:
            for profile_id in OLD_REMOVED_PROFILE_IDS:
                with self.subTest(operation="load", profile_id=profile_id):
                    with self.assertRaisesRegex(ValueError, "retired"):
                        load_profile(
                            profile_id,
                            project_root=project,
                            project_profile_dirs=["profiles"],
                        )

                router_api_version = (
                    "route/v2" if profile_id == OLD_REMOVED_PROFILE_IDS[1] else "route/v1"
                )
                config_path = project / f"config-{profile_id}.json"
                config_path.write_text(
                    json.dumps(project_config(profile_id, router_api_version)),
                    encoding="utf-8",
                )
                validated = run_cli(
                    "validate-profile",
                    "--profile",
                    profile_id,
                    "--config",
                    str(config_path),
                    "--project-root",
                    str(project),
                )
                with self.subTest(operation="validate-profile", profile_id=profile_id):
                    self.assertNotEqual(validated.returncode, 0)
                    self.assertEqual(validated.stdout, "")
                    self.assertIn("retired", validated.stderr)

    def test_matching_retired_project_profiles_are_rejected_during_discovery(self):
        with retired_profile_project() as project:
            config_path = project / "discovery-config.json"
            config_path.write_text(
                json.dumps(project_config(V1_PROFILE_ID, "route/v1")),
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

    def test_matching_retired_project_profiles_are_rejected_for_explicit_injected_and_conventional_config(self):
        for profile_id in OLD_REMOVED_PROFILE_IDS:
            router_api_version = (
                "route/v2" if profile_id == OLD_REMOVED_PROFILE_IDS[1] else "route/v1"
            )
            request = route_request(profile_id, router_api_version)
            config = project_config(profile_id, router_api_version)
            with retired_profile_project() as project:
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
                    with self.subTest(profile_id=profile_id, source=source):
                        with self.assertRaisesRegex(ValueError, "retired"):
                            resolve_route(request, cwd=project, **kwargs)


if __name__ == "__main__":
    unittest.main()
