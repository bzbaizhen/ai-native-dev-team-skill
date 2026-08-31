import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README_PATHS = (ROOT / "README.md", ROOT / "README.zh-CN.md")
RELEASE_URL = "https://github.com/bzbaizhen/ai-native-dev-team-skill/releases/tag/v3.0.0"
LEGACY_NAME = "bootstrap" + "-ai-native-dev-team"
ROUTER_PROFILE_IDS = (
    "openai-glm5.3-deepseek-fallback-2026-08-28",
    "openai-gpt5.6-validator-assurance-2026-08-31",
)


def headings(text: str) -> list[tuple[int, str]]:
    return [
        (len(match.group(1)), match.group(2).strip())
        for line in text.splitlines()
        if (match := re.match(r"^(#{2,3})\s+(.+?)\s*$", line))
    ]


def local_targets(text: str) -> list[str]:
    return [
        target.split("#", 1)[0].strip().strip("<>")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
        if not target.startswith(("http://", "https://", "mailto:", "#"))
        and target.split("#", 1)[0].strip()
    ]


class ReadmeV3ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.texts = [path.read_text(encoding="utf-8") for path in README_PATHS]

    def test_bilingual_heading_structure_is_identical_and_in_order(self) -> None:
        expected_levels = [2] * 11
        for text in self.texts:
            self.assertEqual([level for level, _ in headings(text)], expected_levels)
        self.assertEqual(
            [title for _, title in headings(self.texts[0])],
            [
                "What is in the Suite",
                "How the two Skills work together",
                "Install",
                "60-second quick start",
                "Configure the Router",
                "Workflow",
                "Safety boundaries",
                "Migrate from the legacy name",
                "Repository layout",
                "Validation",
                "Release and license",
            ],
        )

    def test_first_screen_and_release_identify_v3_two_skills_one_repository(self) -> None:
        english, chinese = self.texts
        for text in self.texts:
            self.assertIn("v3.0.0", text)
            self.assertIn("`skills/ai-native-model-router/` v0.2.0", text)
            self.assertNotIn("v0.1.0", text)
            self.assertIn(RELEASE_URL, text)
            self.assertIn("ai-native-dev-team", text)
            self.assertIn("ai-native-model-router", text)
            self.assertNotIn("v2.1.0", text)
        self.assertIn("One GitHub repository", english)
        self.assertIn("一个 GitHub 仓库", chinese)

    def test_required_sections_and_contract_facts_are_present(self) -> None:
        english = self.texts[0]
        chinese = self.texts[1]
        for phrase in ("Team", "Router", "route/v1", "route/v2", ".ai-native/model-router.json", "Host Adapter",
                       "C0-C3", "R0-R3", "Core", "Controlled", "DQR", "Writer", "Validator",
                       "candidate", "recovery", "permissions", "Git isolation", "not-executed", "plan", "apply",
                       "verify", "rollback", "complete Skill directory"):
            self.assertIn(phrase, english)
        for phrase in ("Team", "Router", "route/v1", "route/v2", ".ai-native/model-router.json", "Host Adapter",
                       "C0-C3", "R0-R3", "Core", "Controlled", "DQR", "Writer", "Validator",
                       "候选版本", "恢复", "权限", "Git 隔离", "not-executed", "plan", "apply", "verify",
                       "rollback", "完整 Skill 目录"):
            self.assertIn(phrase, chinese)
        self.assertIn("Team works without the Router", english)
        self.assertIn("Team, Router, Writer, Validator, RouteDecision, route slot, and Host Adapter are fixed names", english)
        self.assertIn("Configuration-only switching", english)
        self.assertIn("New authentication", english)
        self.assertIn("transport", english)
        self.assertIn("host injection", english)
        self.assertIn("GLM-5.3", english)
        self.assertIn("GLM-5.3 Flash", english)
        self.assertIn("evidence-gated", english)
        self.assertIn("not automated", english)
        self.assertIn("R1: Luna Max -> Terra Max -> Sol High", english)
        self.assertIn("R2: Terra Max -> Sol High", english)
        self.assertIn("R3 requires strict Terra Max + Sol High", english)
        self.assertIn("never degrades to one Validator", english)
        self.assertIn("The preserved v1 profile uses GLM-5.3", english)
        self.assertIn("neither profile is a default or auto-activated", english)
        self.assertNotIn("The default validation profile", english)
        self.assertIn("Team 本身可以独立工作", chinese)
        self.assertIn("Team、Router、Writer、Validator、RouteDecision、route slot 和 Host Adapter 作为固定名称", chinese)
        self.assertIn("仅改配置", chinese)
        self.assertIn("新增认证", chinese)
        self.assertIn("R1：Luna Max -> Terra Max -> Sol High", chinese)
        self.assertIn("R2：Terra Max -> Sol High", chinese)
        self.assertIn("R3：严格使用 Terra Max + Sol High", chinese)
        self.assertIn("不会降级为一个 Validator", chinese)
        self.assertIn("保留的 v1 profile 用 GLM-5.3", chinese)
        self.assertIn("均不是默认项，也不会自动启用", chinese)
        self.assertNotIn("默认路由配置", chinese)

    def test_router_example_is_exact_and_no_secrets_are_advertised(self) -> None:
        expected = (
            '"schema_version": 1',
            '"router_api_version": "route/v1"',
            '"config_id": "project-router-2026-08-28"',
            '"active_profile": "openai-glm5.3-deepseek-fallback-2026-08-28"',
            '"project_profile_dirs": [".ai-native/profiles"]',
            '"updated_reason": "Explicit project profile selection for route/v1."',
        )
        v2_expected = (
            '"schema_version": 2',
            '"router_api_version": "route/v2"',
            '"config_id": "project-router-v2-2026-08-31"',
            '"active_profile": "openai-gpt5.6-validator-assurance-2026-08-31"',
            '"project_profile_dirs": [".ai-native/profiles"]',
            '"updated_reason": "Explicit project profile selection for route/v2."',
        )
        for text in self.texts:
            for field in expected:
                self.assertIn(field, text)
            for field in v2_expected:
                self.assertIn(field, text)
            for profile_id in ROUTER_PROFILE_IDS:
                self.assertIn(profile_id, text)
        self.assertIn("No secrets belong in this file.", self.texts[0])
        self.assertIn("配置中不放密钥或其他敏感信息", self.texts[1])
        self.assertIn("active_profile` is explicit", self.texts[0])
        self.assertIn("active_profile` 必须显式选择", self.texts[1])
        self.assertIn("Both the profile and the Router API/configuration version are explicit", self.texts[0])
        self.assertIn("必须分别显式选择 profile 和 Router API/配置版本", self.texts[1])
        self.assertIn("A profile file's presence does not activate anything", self.texts[0])
        self.assertIn("仅有 profile 文件不会启用任何路由", self.texts[1])
        self.assertIn("remains a reusable explicit option", self.texts[0])
        self.assertIn("仍可作为可复用的显式选项", self.texts[1])

    def test_install_tables_and_commands_are_bilingual_contracts(self) -> None:
        english, chinese = self.texts
        install_commands = (
            "$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/ai-native-dev-team",
            "$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/ai-native-model-router",
        )
        for command in install_commands:
            self.assertIn(command, english)
            self.assertIn(command, chinese)
        for phrase in ("Codex", "Hermes Agent", "Manual source install", "one current GitHub Release",
                       "not a separate repository or release"):
            self.assertIn(phrase, english)
        for phrase in ("Codex", "Hermes Agent", "手动从源码安装", "一个当前 GitHub 发布",
                       "没有单独的仓库或 Release"):
            self.assertIn(phrase, chinese)

    def test_safety_lifecycle_contract_is_complete_in_each_language(self) -> None:
        english, chinese = self.texts
        for token in ("pty=false", "background=true", "notify_on_complete=true", "pty=true",
                      "interactive TUI", "login", "unattended exec", "final-answer marker",
                      "tokens-used", "registry status", "exited", "exit code",
                      "one short bounded grace check", "fresh process status", "exact tracked process",
                      "duplicate Writer", "wait/reconnect"):
            self.assertIn(token, english)
        for token in ("pty=false", "background=true", "notify_on_complete=true", "pty=true",
                      "interactive TUI", "login", "unattended exec", "final-answer marker",
                      "tokens-used", "registry status", "exited", "exit code",
                      "one short bounded grace check", "fresh process status", "exact tracked process",
                      "duplicate Writer", "wait/reconnect"):
            self.assertIn(token, chinese)
        for phrase in ("无人值守、非交互式", "进程退出证据", "取得 exit code", "不启动 duplicate Writer"):
            self.assertIn(phrase, chinese)
        self.assertIn("process-kill or power-loss crash journal is not automated", english)
        self.assertIn("process-kill 或断电中断不会自动建立 crash journal", chinese)

    def test_links_and_images_are_relative_and_resolve(self) -> None:
        for path, text in zip(README_PATHS, self.texts):
            for target in local_targets(text):
                self.assertFalse(target.startswith(("/", "\\", "C:", "D:")), target)
                self.assertTrue((path.parent / target).is_file() or (path.parent / target).is_dir(), f"{path.name}: {target}")

    def test_public_readmes_have_no_internal_or_unverified_registry_claims(self) -> None:
        forbidden = (
            r"[CD]:\\",
            r"(?:/Users/|/home/|\\Users\\)",
            r"\bZHE-\d+\b",
            r"\b[0-9a-f]{40}\b",
            r"\b(?:Phase|阶段)\s*\d+\b",
            r"\b(?:official|published|available|listed)\s+(?:in|on)\s+the\s+registry\b",
            r"\b(?:local|本地)\s*(?:receipt|回执)\b",
        )
        for text in self.texts:
            for pattern in forbidden:
                self.assertIsNone(re.search(pattern, text, re.IGNORECASE), pattern)

    def test_legacy_name_is_bounded_to_one_migration_statement(self) -> None:
        for text in self.texts:
            self.assertEqual(text.count(LEGACY_NAME), 1)
        self.assertIn("migration input only", self.texts[0])
        self.assertIn("仅作为迁移输入", self.texts[1])


if __name__ == "__main__":
    unittest.main()
