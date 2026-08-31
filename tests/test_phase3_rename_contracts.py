import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
TEAM = SKILLS / "ai-native-dev-team"
ROUTER = SKILLS / "ai-native-model-router"
OLD_NAME = "bootstrap" + "-ai-native-dev-team"
OLD_DIR = SKILLS / OLD_NAME
LEGACY_REFERENCE_ALLOWLIST = {
    "suite-manifest.json": (1, '"migration_only": true'),
    "README.md": (1, "migration input only"),
    "README.zh-CN.md": (1, "仅作为迁移输入"),
    "tools/migrate_suite_install.py": (1, "OLD_COMPONENT_NAME"),
    "tests/test_suite_packaging.py": (3, "migration_only"),
}

EXPECTED_TEAM_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "assets/project-team-charter.md",
    "assets/task-contract.md",
    "assets/team-bootstrap-proposal.md",
    "references/controlled.md",
    "references/core.md",
    "references/delivery-quality-review.md",
    "references/git-isolation-bootstrap.md",
    "references/governance-controlled.md",
    "references/governance-lean.md",
    "references/governance-strict.md",
    "references/metrics-event.schema.json",
    "references/metrics.md",
    "references/routing-and-topologies.md",
    "references/team-governance-template.zh-CN.md",
    "scripts/git_isolation_bootstrap.py",
    "scripts/team_metrics.py",
}
VENDOR_TOKENS = ("openai", "zai", "deepseek", "gpt", "glm")
TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".py", ".js", ".ts", ".tsx",
    ".jsx", ".css", ".html", ".xml", ".svg", ".sh", ".ps1", ".bat",
}


def frontmatter(text: str) -> str:
    match = re.match(r"\A---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        raise AssertionError("missing frontmatter")
    return match.group(1)


def frontmatter_list(metadata: str, key: str) -> list[str]:
    """Read a simple YAML-like list in either inline or block form."""
    lines = metadata.splitlines()
    for index, line in enumerate(lines):
        match = re.match(rf"^\s*{re.escape(key)}:\s*(.*)$", line)
        if not match:
            continue
        value = match.group(1).strip()
        if value.startswith("[") and value.endswith("]"):
            return [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
        values = []
        for child in lines[index + 1:]:
            item = re.match(r"^\s+-\s+(.+?)\s*$", child)
            if not item:
                break
            values.append(item.group(1).strip("'\""))
        return values
    raise AssertionError(f"missing frontmatter list: {key}")


def known_text_files(root: Path):
    return (
        path
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix.lower() in TEXT_EXTENSIONS
    )


class Phase3RenameContractTests(unittest.TestCase):
    def test_skill_directories_are_exactly_team_and_router(self):
        actual = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertEqual(actual, {"ai-native-dev-team", "ai-native-model-router"})
        self.assertFalse(OLD_DIR.exists())

    def test_team_directory_is_complete_and_provider_profile_is_router_only(self):
        actual = {
            path.relative_to(TEAM).as_posix()
            for path in TEAM.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        }
        self.assertEqual(actual, EXPECTED_TEAM_FILES)
        router_profiles = sorted(
            path.relative_to(ROUTER / "assets" / "profiles").as_posix()
            for path in (ROUTER / "assets" / "profiles").glob("*")
            if path.is_file()
        )
        self.assertEqual(
            router_profiles,
            [
                "openai-glm5.3-deepseek-fallback-2026-08-28.json",
                "openai-gpt5.6-validator-assurance-2026-08-31.json",
            ],
        )
        self.assertFalse(
            any("model-routing-" in path.name for path in (TEAM / "references").glob("*"))
        )

    def test_team_frontmatter_and_metadata_are_canonical(self):
        skill_text = (TEAM / "SKILL.md").read_text(encoding="utf-8")
        metadata = frontmatter(skill_text)
        self.assertIn("name: ai-native-dev-team", metadata)
        self.assertIn("version: 3.0.0", metadata)
        self.assertIn("author: bzbaizhen, Hermes Agent", metadata)
        self.assertEqual(frontmatter_list(metadata, "platforms"), ["linux", "macos", "windows"])
        self.assertEqual(frontmatter_list(metadata, "related_skills"), ["ai-native-model-router"])
        self.assertEqual(
            frontmatter_list(metadata, "tags"),
            ["team-governance", "proportional-controls", "route-slots"],
        )
        description = re.search(r"^description:\s*(.+)$", metadata, re.MULTILINE).group(1)
        self.assertLessEqual(len(description), 60)

        openai_yaml = (TEAM / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "AI Native Dev Team"', openai_yaml)
        self.assertIn("$ai-native-dev-team", openai_yaml)
        self.assertNotIn("$" + OLD_NAME, openai_yaml)

        router_metadata = frontmatter((ROUTER / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("related_skills:", router_metadata)
        self.assertIn("- ai-native-dev-team", router_metadata)

    def test_team_is_governance_only_and_router_integration_is_fail_closed(self):
        text = (TEAM / "SKILL.md").read_text(encoding="utf-8").casefold()
        self.assertIn("generic route slot", text)
        normalized = " ".join(text.split())
        self.assertIn("optionally load", normalized)
        self.assertIn("unknown", text)
        self.assertIn("host-inherited", text)
        self.assertIn("never infers a provider or model", normalized)
        self.assertIn("independent validation", normalized)
        self.assertIn("dqr", normalized)
        self.assertIn("routing does not weaken dqr or independent validation", normalized)

        for path in known_text_files(TEAM):
            lowered = path.read_text(encoding="utf-8").casefold()
            for token in VENDOR_TOKENS:
                self.assertNotIn(token, lowered, path.as_posix())

    def test_active_tracked_files_have_no_legacy_name_or_legacy_paths(self):
        tracked = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT, text=False
        ).decode("utf-8").split("\0")
        legacy_image = "docs/images/" + "bootstrap" + "-workflow.png"
        paths_to_scan = {
            item for item in tracked if item and not item.startswith("releases/")
        }
        paths_to_scan.update(LEGACY_REFERENCE_ALLOWLIST)
        for relative in sorted(paths_to_scan):
            path = ROOT / relative
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            text = path.read_text(encoding="utf-8")
            if relative in LEGACY_REFERENCE_ALLOWLIST:
                expected_count, context = LEGACY_REFERENCE_ALLOWLIST[relative]
                self.assertEqual(text.count(OLD_NAME), expected_count, relative)
                self.assertIn(context, text, relative)
            else:
                self.assertNotIn(OLD_NAME, text, relative)
            self.assertNotIn("skills/" + OLD_NAME, text, relative)
            self.assertNotIn(legacy_image, text, relative)

        release_count = sum(
            (ROOT / relative).read_text(encoding="utf-8").count(OLD_NAME)
            for relative in tracked
            if relative.startswith("releases/") and (ROOT / relative).is_file()
        )
        self.assertEqual(release_count, 8)

    def test_image_and_active_links_use_canonical_name(self):
        image = ROOT / "docs" / "images" / "ai-native-dev-team-workflow.png"
        self.assertTrue(image.is_file())
        legacy_image = ROOT / "docs" / "images" / ("bootstrap" + "-workflow.png")
        self.assertFalse(legacy_image.exists())
        active_markdown = [
            path
            for path in ROOT.rglob("*.md")
            if "releases" not in path.parts
        ]
        for path in active_markdown:
            self.assertNotIn("bootstrap" + "-workflow.png", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
