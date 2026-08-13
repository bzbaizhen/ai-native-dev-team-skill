from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bootstrap-ai-native-dev-team"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


required = [
    SKILL / "SKILL.md",
    SKILL / "agents" / "openai.yaml",
    SKILL / "references" / "team-governance-template.zh-CN.md",
    SKILL / "assets" / "team-bootstrap-proposal.md",
    SKILL / "assets" / "project-team-charter.md",
    SKILL / "assets" / "task-contract.md",
    SKILL / "assets" / "evidence-manifest.yaml",
]

for path in required:
    if not path.is_file():
        fail(f"missing {path.relative_to(ROOT)}")

text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
if not match:
    fail("SKILL.md frontmatter is missing")

frontmatter = match.group(1)
if "name: bootstrap-ai-native-dev-team" not in frontmatter:
    fail("skill name is invalid")
if "description:" not in frontmatter:
    fail("skill description is missing")
if "TODO" in text or "[TODO" in text:
    fail("SKILL.md still contains TODO placeholders")
if len(text.splitlines()) > 500:
    fail("SKILL.md exceeds 500 lines")

for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
    if target.startswith(("http://", "https://", "#")):
        continue
    resolved = (SKILL / target).resolve()
    if not resolved.exists():
        fail(f"broken local link in SKILL.md: {target}")

openai_yaml = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
if "$bootstrap-ai-native-dev-team" not in openai_yaml:
    fail("default prompt does not explicitly invoke the skill")

print("PASS: skill structure and required resources are valid")
