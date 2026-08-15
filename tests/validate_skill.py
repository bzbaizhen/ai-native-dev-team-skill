from pathlib import Path, PurePosixPath
import hashlib
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
    SKILL / "references" / "core.md",
    SKILL / "references" / "controlled.md",
    SKILL / "references" / "release-audit.md",
    SKILL / "references" / "governance-lean.md",
    SKILL / "references" / "governance-controlled.md",
    SKILL / "references" / "governance-strict.md",
    SKILL / "references" / "metrics.md",
    SKILL / "references" / "metrics-event.schema.json",
    SKILL / "references" / "release-anchor-closure.schema.json",
    SKILL / "references" / "release-registration-receipt.schema.json",
    SKILL / "references" / "release-source-registry.schema.json",
    SKILL / "references" / "release-trial-evidence.schema.json",
    SKILL / "references" / "release-v1-baseline-evidence.schema.json",
    SKILL / "references" / "release-trial-manifest.schema.json",
    SKILL / "references" / "p2-private-binding.schema.json",
    SKILL / "references" / "p2-opaque-envelope.schema.json",
    SKILL / "references" / "p2-external-proof-package.schema.json",
    SKILL / "references" / "team-governance-template.zh-CN.md",
    SKILL / "assets" / "team-bootstrap-proposal.md",
    SKILL / "assets" / "project-team-charter.md",
    SKILL / "assets" / "task-contract.md",
    SKILL / "assets" / "evidence-manifest.yaml",
    SKILL / "assets" / "metrics-handoff.yaml",
    SKILL / "scripts" / "team_metrics.py",
    SKILL / "scripts" / "v2_release_gate.py",
    SKILL / "scripts" / "p2_pregate.py",
    ROOT / "benchmarks" / "v2-prospective" / "README.md",
    ROOT / "benchmarks" / "v2-prospective" / "anchor-closure.example.json",
    ROOT / "benchmarks" / "v2-prospective" / "registration-000001.example.json",
    ROOT / "benchmarks" / "v2-prospective" / "source-registry.example.json",
    ROOT / "benchmarks" / "v2-prospective" / "trial-manifest.example.json",
    ROOT / "benchmarks" / "v2-prospective" / "v1-baseline.example.json",
    ROOT / "benchmarks" / "v2-prospective" / "v1-task-contract.example.md",
    ROOT / "benchmarks" / "v2-prospective" / "v1-qa-report.example.md",
    ROOT / "tests" / "routing-scenarios.json",
    ROOT / "tests" / "test_routing_policy.py",
    ROOT / "tests" / "test_team_metrics.py",
    ROOT / "tests" / "test_v2_release_gate.py",
    ROOT / "tests" / "test_p2_pregate.py",
    ROOT / "tests" / "fixtures" / "p2" / "private-binding-vector.json",
    ROOT / "tests" / "fixtures" / "p2" / "duplicate-key.json",
    ROOT / "tests" / "fixtures" / "p2" / "public-leak.json",
    ROOT / "releases" / "v2.0.0-rc.1.md",
    ROOT / "releases" / "v2.0.0-rc.2.md",
    ROOT / "releases" / "v2.0.0-rc.3.md",
    ROOT / "releases" / "v2.0.0-rc.4.md",
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
if len(text.splitlines()) > 120:
    fail("SKILL.md did not shrink to the Core and selector entry path")

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
    "references/core.md",
    "references/controlled.md",
    "references/release-audit.md",
    "references/metrics.md",
}
if not direct_references.issubset(set(local_links)):
    fail("SKILL.md does not directly link every canonical progressive reference")

default_protocol_details = (
    "release-anchor-closure.schema.json",
    "release-registration-receipt.schema.json",
    "release-trial-manifest.schema.json",
    "release-source-registry.schema.json",
    "release-v1-baseline-evidence.schema.json",
    "release-trial-evidence.schema.json",
    "Anchor history",
)
for detail in default_protocol_details:
    if detail in text:
        fail(f"default SKILL.md exposes Release Audit protocol detail: {detail}")

for canonical, pointer in (
    ("core.md", "governance-lean.md"),
    ("controlled.md", "governance-controlled.md"),
    ("controlled.md", "governance-strict.md"),
):
    pointer_text = (SKILL / "references" / pointer).read_text(encoding="utf-8")
    if canonical not in pointer_text:
        fail(f"compatibility pointer {pointer} does not point to {canonical}")

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
    "release-v1-baseline-evidence.schema.json",
):
    schema_path = SKILL / "references" / name
    try:
        extra_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{name} is invalid JSON: {exc}")
    if extra_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        fail(f"{name} must declare JSON Schema 2020-12")

p2_schema_fields = {
    "p2-private-binding.schema.json": {
        "schema_version",
        "window_id",
        "sequence",
        "record_kind",
        "private_anchor_commit",
        "private_object_sha256",
        "candidate_commit",
        "previous_private_binding_sha256",
        "created_at",
    },
    "p2-opaque-envelope.schema.json": {
        "schema_version",
        "receipt_type",
        "opaque_window_id",
        "sequence",
        "commitment_sha256",
        "previous_envelope_sha256",
    },
    "p2-external-proof-package.schema.json": {
        "schema_version",
        "proof_type",
        "provider",
        "protocol_version",
        "submitted_digest_sha256",
        "retained_files",
        "verification_policy",
        "acquired_at",
    },
}
for name, expected_fields in p2_schema_fields.items():
    schema_path = SKILL / "references" / name
    try:
        p2_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{name} is invalid JSON: {exc}")
    if p2_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        fail(f"{name} must declare JSON Schema 2020-12")
    if p2_schema.get("additionalProperties") is not False:
        fail(f"{name} must reject unknown fields")
    if set(p2_schema.get("required", [])) != expected_fields:
        fail(f"{name} required fields do not match the frozen P2 contract")
    if set(p2_schema.get("properties", {})) != expected_fields:
        fail(f"{name} properties do not match the frozen P2 contract")

release_audit_text = (SKILL / "references" / "release-audit.md").read_text(encoding="utf-8")
for pointer in (
    "../scripts/p2_pregate.py",
    "p2-private-binding.schema.json",
    "p2-opaque-envelope.schema.json",
    "p2-external-proof-package.schema.json",
    "trusted_time_missing",
):
    if pointer not in release_audit_text:
        fail(f"release-audit.md is missing P2 progressive-disclosure pointer: {pointer}")

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

p2_script_path = SKILL / "scripts" / "p2_pregate.py"
try:
    p2_script_text = p2_script_path.read_text(encoding="utf-8")
    compile(p2_script_text, str(p2_script_path), "exec")
except SyntaxError as exc:
    fail(f"p2_pregate.py has a syntax error: {exc}")
if re.search(r"(?:import|from)\s+v2_release_gate|subprocess\.[^\n]*v2_release_gate", p2_script_text):
    fail("p2_pregate.py must not import or invoke v2_release_gate.py")
if "trusted_time_missing" not in p2_script_text:
    fail("p2_pregate.py must emit trusted_time_missing")

try:
    example_manifest = json.loads(
        (ROOT / "benchmarks" / "v2-prospective" / "trial-manifest.example.json")
        .read_text(encoding="utf-8")
    )
except json.JSONDecodeError as exc:
    fail(f"release trial example is invalid JSON: {exc}")
if example_manifest.get("required_comparable_tasks") != 5:
    fail("release trial example must preserve the preregistered five-task gate")
if example_manifest.get("candidate_version") != "v2.0.0-rc.5":
    fail("release trial example must name the current RC.5 candidate")
example_trials = example_manifest.get("trials")
if not isinstance(example_trials, list) or not example_trials:
    fail("release trial example must contain an accepted trial")
example_proof = example_trials[0].get("integration_proof")
if not isinstance(example_proof, dict) or example_proof.get("mode") != "same_tree":
    fail("release trial example must demonstrate same_tree integration proof")
if example_proof.get("tree_scope") != {
    "history_sensitive": False,
    "non_tree_dependencies": [],
}:
    fail("same_tree example tree_scope must be explicitly empty and history-insensitive")

example_dir = ROOT / "benchmarks" / "v2-prospective"


def example_child(relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        fail(f"{label} must be a relative POSIX path")
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or not pure.parts
        or pure.as_posix() != relative
        or ".." in pure.parts
    ):
        fail(f"{label} must be a normalized relative POSIX path")
    path = example_dir.joinpath(*pure.parts)
    if not path.is_file():
        fail(f"missing example digest source: {relative}")
    return path


registry_path = example_child(
    example_manifest.get("source_registry"), "example source_registry"
)
registry_digest = hashlib.sha256(registry_path.read_bytes()).hexdigest()
if registry_digest != example_manifest.get("source_registry_sha256"):
    fail("example Manifest source-registry SHA-256 is stale")
try:
    example_registry = json.loads(registry_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    fail(f"source-registry example is invalid JSON: {exc}")
baseline_entries = example_registry.get("v1_baselines")
if not isinstance(baseline_entries, list) or len(baseline_entries) != 1:
    fail("source-registry example must contain exactly one V1 baseline")
baseline_entry = baseline_entries[0]
baseline_path = example_child(
    baseline_entry.get("evidence_path"), "example baseline evidence_path"
)
baseline_digest = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
if baseline_digest != baseline_entry.get("evidence_sha256"):
    fail("example source-registry baseline SHA-256 is stale")
try:
    example_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    fail(f"V1 baseline example is invalid JSON: {exc}")
if example_baseline.get("baseline_id") != baseline_entry.get("baseline_id"):
    fail("example V1 baseline identity differs from the source registry")
if example_baseline.get("stratum_id") != baseline_entry.get("stratum_id"):
    fail("example V1 baseline stratum differs from the source registry")
if example_baseline.get("efficiency_denominators_available") != baseline_entry.get(
    "formal_efficiency_comparable"
):
    fail("example V1 baseline efficiency eligibility differs from the source registry")
sources = example_baseline.get("source_evidence")
if not isinstance(sources, list) or not sources:
    fail("V1 baseline example must contain source evidence")
covered_claims = set()
for source in sources:
    source_path = example_child(
        source.get("evidence_path"), "example baseline source evidence_path"
    )
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if source_digest != source.get("evidence_sha256"):
        fail(f"example baseline source SHA-256 is stale: {source_path.name}")
    supports = source.get("supports")
    if not isinstance(supports, list):
        fail(f"example baseline source supports is invalid: {source_path.name}")
    covered_claims.update(supports)
required_claims = {"task_identity", "stratum", "acceptance"}
if baseline_entry.get("formal_efficiency_comparable"):
    required_claims.add("efficiency_denominator")
if not required_claims.issubset(covered_claims):
    fail("example V1 baseline source claim coverage is incomplete")

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
