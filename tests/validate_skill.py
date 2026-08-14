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
    SKILL / "references" / "release-anchor-closure.schema.json",
    SKILL / "references" / "release-registration-receipt.schema.json",
    SKILL / "references" / "release-source-registry.schema.json",
    SKILL / "references" / "release-trial-evidence.schema.json",
    SKILL / "references" / "release-trial-manifest.schema.json",
    SKILL / "references" / "team-governance-template.zh-CN.md",
    SKILL / "assets" / "team-bootstrap-proposal.md",
    SKILL / "assets" / "project-team-charter.md",
    SKILL / "assets" / "task-contract.md",
    SKILL / "assets" / "evidence-manifest.yaml",
    SKILL / "assets" / "metrics-handoff.yaml",
    SKILL / "scripts" / "team_metrics.py",
    SKILL / "scripts" / "v2_release_gate.py",
    ROOT / "benchmarks" / "v2-prospective" / "README.md",
    ROOT / "benchmarks" / "v2-prospective" / "anchor-closure.example.json",
    ROOT / "benchmarks" / "v2-prospective" / "registration-000001.example.json",
    ROOT / "benchmarks" / "v2-prospective" / "source-registry.example.json",
    ROOT / "benchmarks" / "v2-prospective" / "trial-manifest.example.json",
    ROOT / "tests" / "routing-scenarios.json",
    ROOT / "tests" / "test_team_metrics.py",
    ROOT / "tests" / "test_v2_release_gate.py",
    ROOT / "releases" / "v2.0.0-rc.1.md",
    ROOT / "releases" / "v2.0.0-rc.2.md",
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
    "references/release-anchor-closure.schema.json",
    "references/release-registration-receipt.schema.json",
    "references/release-source-registry.schema.json",
    "references/release-trial-evidence.schema.json",
    "references/release-trial-manifest.schema.json",
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

release_schema_path = SKILL / "references" / "release-trial-manifest.schema.json"
try:
    release_schema = json.loads(release_schema_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    fail(f"release trial JSON Schema is invalid JSON: {exc}")
if release_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
    fail("release trial schema must declare JSON Schema 2020-12")
if (
    release_schema.get("properties", {})
    .get("required_comparable_tasks", {})
    .get("minimum")
    != 5
):
    fail("release trial schema must require at least five comparable tasks")

for name in (
    "release-anchor-closure.schema.json",
    "release-registration-receipt.schema.json",
    "release-source-registry.schema.json",
    "release-trial-evidence.schema.json",
):
    schema_path = SKILL / "references" / name
    try:
        extra_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{name} is invalid JSON: {exc}")
    if extra_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        fail(f"{name} must declare JSON Schema 2020-12")

script_path = SKILL / "scripts" / "team_metrics.py"
try:
    compile(script_path.read_text(encoding="utf-8"), str(script_path), "exec")
except SyntaxError as exc:
    fail(f"team_metrics.py has a syntax error: {exc}")

release_gate_path = SKILL / "scripts" / "v2_release_gate.py"
try:
    compile(release_gate_path.read_text(encoding="utf-8"), str(release_gate_path), "exec")
except SyntaxError as exc:
    fail(f"v2_release_gate.py has a syntax error: {exc}")

try:
    example_manifest = json.loads(
        (ROOT / "benchmarks" / "v2-prospective" / "trial-manifest.example.json")
        .read_text(encoding="utf-8")
    )
except json.JSONDecodeError as exc:
    fail(f"release trial example is invalid JSON: {exc}")
if example_manifest.get("required_comparable_tasks") != 5:
    fail("release trial example must preserve the preregistered five-task gate")

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
