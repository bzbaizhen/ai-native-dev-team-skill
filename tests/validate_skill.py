from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bootstrap-ai-native-dev-team"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


required = [
    SKILL / "SKILL.md",
    SKILL / "agents" / "openai.yaml",
    SKILL / "references" / "routing-and-topologies.md",
    SKILL / "references" / "governance-lean.md",
    SKILL / "references" / "governance-controlled.md",
    SKILL / "references" / "governance-strict.md",
    SKILL / "references" / "metrics.md",
    SKILL / "references" / "metrics-event.schema.json",
    SKILL / "references" / "team-governance-template.zh-CN.md",
    SKILL / "assets" / "team-bootstrap-proposal.md",
    SKILL / "assets" / "project-team-charter.md",
    SKILL / "assets" / "task-contract.md",
    SKILL / "assets" / "evidence-manifest.yaml",
    SKILL / "assets" / "metrics-handoff.yaml",
    SKILL / "scripts" / "team_metrics.py",
    ROOT / "tests" / "routing-scenarios.json",
    ROOT / "tests" / "test_team_metrics.py",
    ROOT / "releases" / "v2.0.0-rc.1.md",
]

for path in required:
    if not path.is_file():
        fail(f"missing {path.relative_to(ROOT)}")

text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
if not match:
    fail("SKILL.md frontmatter is missing")
frontmatter = match.group(1)
keys = [
    line.split(":", 1)[0].strip()
    for line in frontmatter.splitlines()
    if line.strip() and ":" in line
]
if keys != ["name", "description"]:
    fail(f"SKILL.md frontmatter keys must be name and description only: {keys}")
if "name: bootstrap-ai-native-dev-team" not in frontmatter:
    fail("skill name is invalid")
if "description:" not in frontmatter:
    fail("skill description is missing")
if "TODO" in text or "[TODO" in text:
    fail("SKILL.md still contains TODO placeholders")
if len(text.splitlines()) > 500:
    fail("SKILL.md exceeds 500 lines")

local_links = []
for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
    if target.startswith(("http://", "https://", "#")):
        continue
    local_links.append(target)
    resolved = (SKILL / target).resolve()
    if not resolved.exists():
        fail(f"broken local link in SKILL.md: {target}")

direct_references = {
    "references/routing-and-topologies.md",
    "references/governance-lean.md",
    "references/governance-controlled.md",
    "references/governance-strict.md",
    "references/metrics.md",
    "references/metrics-event.schema.json",
}
if not direct_references.issubset(set(local_links)):
    fail("SKILL.md does not directly link every progressive reference")

legacy = SKILL / "references" / "team-governance-template.zh-CN.md"
if len(legacy.read_text(encoding="utf-8").splitlines()) > 40:
    fail("V1 compatibility pointer became a second monolithic governance source")

schema_path = SKILL / "references" / "metrics-event.schema.json"
try:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    fail(f"metrics JSON Schema is invalid JSON: {exc}")
if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
    fail("metrics schema must declare JSON Schema 2020-12")
if schema.get("properties", {}).get("schema_version", {}).get("const") != "2.0":
    fail("metrics schema version is not 2.0")

script_path = SKILL / "scripts" / "team_metrics.py"
try:
    compile(script_path.read_text(encoding="utf-8"), str(script_path), "exec")
except SyntaxError as exc:
    fail(f"team_metrics.py has a syntax error: {exc}")

try:
    scenarios = json.loads(
        (ROOT / "tests" / "routing-scenarios.json").read_text(encoding="utf-8")
    )
except json.JSONDecodeError as exc:
    fail(f"routing scenarios are invalid JSON: {exc}")
if not isinstance(scenarios, list) or len(scenarios) < 8:
    fail("routing scenario matrix is too small")
if not any(case.get("risk") == "R3" and case.get("complexity") == "C1" for case in scenarios):
    fail("routing scenarios must prove that high risk does not force high capability")
if not any(
    case.get("complexity") == "C0" and case.get("capability") == "economy"
    for case in scenarios
):
    fail("routing scenarios must cover economical C0 delegation")

openai_yaml = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
if "$bootstrap-ai-native-dev-team" not in openai_yaml:
    fail("default prompt does not explicitly invoke the skill")
short_match = re.search(r'^\s*short_description:\s*"([^"]+)"', openai_yaml, re.MULTILINE)
if not short_match or not 25 <= len(short_match.group(1)) <= 64:
    fail("short_description must contain 25-64 characters")

sensitive = re.compile(r"(?:[A-Za-z]:\\\\Users\\\\|/Users/|/home/)")
for path in SKILL.rglob("*"):
    if path.is_file() and path.suffix.lower() in {".md", ".yaml", ".yml", ".json", ".py"}:
        if sensitive.search(path.read_text(encoding="utf-8")):
            fail(f"local user path leaked into {path.relative_to(ROOT)}")

print("PASS: V2 skill structure, progressive references, schema, script, and scenarios are valid")
