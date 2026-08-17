import ast
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bootstrap-ai-native-dev-team"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


required = [
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "examples" / "global-agents-snippet.md",
    ROOT / "examples" / "sample-proposal.md",
    SKILL / "SKILL.md",
    SKILL / "agents" / "openai.yaml",
    SKILL / "references" / "routing-and-topologies.md",
    SKILL / "references" / "core.md",
    SKILL / "references" / "controlled.md",
    SKILL / "references" / "governance-lean.md",
    SKILL / "references" / "governance-controlled.md",
    SKILL / "references" / "governance-strict.md",
    SKILL / "references" / "team-governance-template.zh-CN.md",
    SKILL / "assets" / "team-bootstrap-proposal.md",
    SKILL / "assets" / "project-team-charter.md",
    SKILL / "assets" / "task-contract.md",
    SKILL / "assets" / "evidence-manifest.yaml",
    ROOT / "tests" / "routing-scenarios.json",
    ROOT / "tests" / "test_routing_policy.py",
]
for path in required:
    if not path.is_file():
        fail(f"missing required file: {path.relative_to(ROOT)}")

removed_paths = [
    ROOT / "benchmarks",
    ROOT / "docs" / "images" / "verification-evidence.svg",
    SKILL / "assets" / "metrics-handoff.yaml",
    SKILL / "references" / "metrics.md",
    SKILL / "references" / "metrics-event.schema.json",
    SKILL / "references" / "release-audit.md",
    SKILL / "scripts",
    ROOT / "tests" / "fixtures" / "p2",
    ROOT / "tests" / "fixtures" / "p3-public",
    ROOT / "tests" / "test_team_metrics.py",
    ROOT / "tests" / "test_v2_release_gate.py",
    ROOT / "tests" / "test_p2_pregate.py",
    ROOT / "tests" / "test_p3_sigstore_github_adapter.py",
]
for path in removed_paths:
    if path.exists():
        fail(f"removed product surface still exists: {path.relative_to(ROOT)}")

for path in (SKILL / "references").iterdir():
    lowered = path.name.casefold()
    if lowered.startswith(("release-", "p2-", "p3-", "zhe125-")):
        fail(f"removed protocol file still exists: {path.relative_to(ROOT)}")

skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
parts = skill_text.split("---", 2)
if len(parts) != 3 or parts[0] != "":
    fail("SKILL.md frontmatter is malformed")
frontmatter_keys = {
    line.split(":", 1)[0].strip()
    for line in parts[1].splitlines()
    if ":" in line
}
if frontmatter_keys != {"name", "description"}:
    fail("SKILL.md frontmatter must contain only name and description")
if "name: bootstrap-ai-native-dev-team" not in parts[1]:
    fail("SKILL.md name is incorrect")
if len(skill_text.splitlines()) > 500:
    fail("SKILL.md exceeds 500 lines")

for target in (
    "references/routing-and-topologies.md",
    "references/core.md",
    "references/controlled.md",
):
    if f"]({target})" not in skill_text:
        fail(f"SKILL.md does not link canonical reference: {target}")

lower_skill = skill_text.casefold()
for removed in (
    "release audit",
    "release-audit",
    "metrics.md",
    "mode: audit",
    "formal efficiency",
    "historical-baseline",
    "registration receipt",
    "p2 ",
    "p3 ",
):
    if removed in lower_skill:
        fail(f"SKILL.md still exposes removed surface: {removed}")

for mode in ("proposal", "initialize", "adjust"):
    if mode not in lower_skill:
        fail(f"SKILL.md is missing mode: {mode}")

for canonical, pointer in (
    ("core.md", "governance-lean.md"),
    ("controlled.md", "governance-controlled.md"),
    ("controlled.md", "governance-strict.md"),
    ("core.md", "team-governance-template.zh-CN.md"),
):
    pointer_text = (SKILL / "references" / pointer).read_text(encoding="utf-8")
    if canonical not in pointer_text:
        fail(f"compatibility pointer {pointer} does not point to {canonical}")
    if len(pointer_text.splitlines()) > 20:
        fail(f"compatibility pointer {pointer} is too large")

for template in (
    "team-bootstrap-proposal.md",
    "project-team-charter.md",
    "task-contract.md",
):
    text = (SKILL / "assets" / template).read_text(encoding="utf-8").casefold()
    for removed in (
        "metrics ledger",
        "metrics handoff",
        "release audit",
        "proposal / initialize / audit",
    ):
        if removed in text:
            fail(f"{template} still exposes removed surface: {removed}")

test_path = ROOT / "tests" / "test_routing_policy.py"
try:
    ast.parse(test_path.read_text(encoding="utf-8"))
except SyntaxError as exc:
    fail(f"routing policy test has a syntax error: {exc}")

try:
    scenarios = json.loads(
        (ROOT / "tests" / "routing-scenarios.json").read_text(encoding="utf-8")
    )
except json.JSONDecodeError as exc:
    fail(f"routing scenarios are invalid JSON: {exc}")
if not isinstance(scenarios, list) or len(scenarios) < 10:
    fail("routing scenario matrix is too small")
if {case.get("layer") for case in scenarios} != {"core", "controlled"}:
    fail("routing scenarios must use exactly Core and Controlled")
if any("audit" in json.dumps(case, sort_keys=True).casefold() for case in scenarios):
    fail("routing scenarios contain a removed field or value")
if not any(
    case.get("complexity") == "C1" and case.get("risk") == "R3"
    for case in scenarios
):
    fail("routing scenarios must cover C1/R3")
if not any(
    case.get("complexity") == "C0" and case.get("capability") == "economy"
    for case in scenarios
):
    fail("routing scenarios must cover Economy C0 delegation")

openai_yaml = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
if "$bootstrap-ai-native-dev-team" not in openai_yaml:
    fail("default prompt does not explicitly invoke the Skill")
if "Release Audit" in openai_yaml or "audit work" in openai_yaml.casefold():
    fail("openai.yaml advertises removed work")
short_match = re.search(
    r'^\s*short_description:\s*"([^"]+)"',
    openai_yaml,
    re.MULTILINE,
)
if not short_match or not 25 <= len(short_match.group(1)) <= 64:
    fail("short_description must contain 25-64 characters")

markdown_files = [
    SKILL / "SKILL.md",
    *SKILL.rglob("*.md"),
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
    ROOT / "CONTRIBUTING.md",
    *list((ROOT / "examples").glob("*.md")),
]
for markdown in dict.fromkeys(markdown_files):
    text = markdown.read_text(encoding="utf-8")
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "#")):
            continue
        clean_target = target.split("#", 1)[0]
        target_path = (markdown.parent / clean_target).resolve()
        if not target_path.exists():
            fail(f"broken local link in {markdown.relative_to(ROOT)}: {target}")

sensitive = re.compile(r"(?:[A-Za-z]:\\Users\\|/Users/|/home/)")
for path in SKILL.rglob("*"):
    if path.is_file() and path.suffix.lower() in {".md", ".yaml", ".yml", ".json", ".py"}:
        if sensitive.search(path.read_text(encoding="utf-8")):
            fail(f"local user path leaked into {path.relative_to(ROOT)}")

print("PASS: V2 development-only Skill structure and routing are valid")
