import ast
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "ai-native-dev-team"
EXPECTED_LEVEL_ZERO_DESCRIPTION = "Route AI-native development with proportional controls."
MAX_LEVEL_ZERO_DESCRIPTION_CHARS = 60
MAX_LEVEL_ONE_LINES = 120
MAX_LEVEL_ONE_CHARS = 6800
CANONICAL_REFERENCE_LINKS = (
    "references/routing-and-topologies.md",
    "references/core.md",
    "references/controlled.md",
)
DQR_REFERENCE_LINK = "references/delivery-quality-review.md"
METRICS_REFERENCE_LINK = "references/metrics.md"
ASSET_TRIGGERS = {
    "assets/team-bootstrap-proposal.md":
        "only when an explicit proposal request needs an approval-ready team proposal",
    "assets/task-contract.md":
        "only when controlled work explicitly needs a durable written contract or frozen interface",
    "assets/project-team-charter.md":
        "only when an explicitly requested long-lived multi-task team is being established",
}
GIT_ISOLATION_REFERENCE = SKILL / "references" / "git-isolation-bootstrap.md"
GIT_ISOLATION_HELPER = SKILL / "scripts" / "git_isolation_bootstrap.py"
DELIVERY_QUALITY_REVIEW = SKILL / "references" / "delivery-quality-review.md"
METRICS_REFERENCE = SKILL / "references" / "metrics.md"
METRICS_SCHEMA = SKILL / "references" / "metrics-event.schema.json"
TEAM_METRICS = SKILL / "scripts" / "team_metrics.py"
EXPECTED_WINDOWS_NAMESPACE_PREFIXES = (
    "\\\\?\\",
    "\\\\.\\",
    "\\??\\",
    "\\\\??\\",
    "//?/",
    "//./",
    "/??/",
    "//??/",
)
EXPECTED_PRIMARY_UNAVAILABLE_EVIDENCE = [
    "model-not-found",
    "authenticated-provider-outage",
    "quota-exhaustion",
    "repeated-bounded-transport-failure",
]
ISOLATION_TEMPLATE_FIELDS = (
    "linear issue uuid/id",
    "linear gitbranchname",
    "canonical worktree",
    "base ref / full base commit",
    "initial/current head",
    "working-tree continuation state",
    "writer cwd / allowed root",
    "worktree ownership",
    "linear checkpoint readback",
    "exact tested head",
)

MODEL_ROUTER = ROOT / "skills" / "ai-native-model-router"
MODEL_ROUTER_REQUIRED_PATHS = {
    "SKILL.md",
    "agents/openai.yaml",
    "assets/model-router-config.example.json",
    "assets/model-router-config.v1.schema.json",
    "assets/profiles/openai-glm5.3-deepseek-fallback-2026-08-28.json",
    "assets/provider-catalog.json",
    "assets/route-decision.v1.schema.json",
    "assets/route-request.v1.schema.json",
    "references/configuration.md",
    "references/interface.md",
    "references/provider-evidence.md",
    "scripts/resolve_route.py",
    "scripts/router_config.py",
}
MODEL_ROUTER_PROFILE_ID = "openai-glm5.3-deepseek-fallback-2026-08-28"
MODEL_ROUTER_CONFIG_ID = "project-router-2026-08-28"
MODEL_ROUTER_FORBIDDEN_TOKENS = re.compile(
    r"\b(?:core|controlled|dqr|linear|governance)\b", re.IGNORECASE
)
OLD_COMPONENT_NAME = "bootstrap" + "-ai-native-dev-team"
LEGACY_REFERENCE_ALLOWLIST = {
    "suite-manifest.json": (1, '"migration_only": true'),
    "README.md": (1, "migration input only"),
    "README.zh-CN.md": (1, "仅作为迁移输入"),
    "tools/migrate_suite_install.py": (1, "OLD_COMPONENT_NAME"),
    "tests/test_suite_packaging.py": (3, "migration_only"),
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def normalize_policy(text: str) -> str:
    return " ".join(text.casefold().split())


def contains_removed_term(text: str, term: str) -> bool:
    normalized_term = term.strip()
    return re.search(
        rf"(?<!\w){re.escape(normalized_term)}(?!\w)",
        text,
        re.IGNORECASE,
    ) is not None


def local_link_targets(text: str) -> set[str]:
    return {
        target.split("#", 1)[0]
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
        if not target.startswith(("http://", "https://", "#"))
    }


def validate_model_router_bundle(skill_dir: Path) -> None:
    """Validate the complete provider-router surface without executing it."""
    actual_paths = {
        path.relative_to(skill_dir).as_posix()
        for path in skill_dir.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    assert actual_paths == MODEL_ROUTER_REQUIRED_PATHS, (
        f"Router paths drifted: extra={sorted(actual_paths - MODEL_ROUTER_REQUIRED_PATHS)}, "
        f"missing={sorted(MODEL_ROUTER_REQUIRED_PATHS - actual_paths)}"
    )

    skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    frontmatter_match = re.match(r"\A---\s*\n(.*?)\n---", skill_text, re.DOTALL)
    assert frontmatter_match, "Router frontmatter is malformed"
    expected_frontmatter = """name: ai-native-model-router
description: Deterministic model routing with evidence-bound fallbacks.
version: 0.1.0
author: bzbaizhen, Hermes Agent
license: MIT
platforms:
  - linux
  - macos
  - windows
metadata:
  hermes:
    related_skills:
      - ai-native-dev-team
    tags:
      - model-routing
      - provider-selection
      - deterministic
    config:
      - key: ai_native_model_router.config_path
        description: Path to the project-local model router configuration.
        default: .ai-native/model-router.json
        prompt: Enter the project-local model router configuration path."""
    assert frontmatter_match.group(1) == expected_frontmatter

    metadata_text = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert "allow_implicit_invocation: false" in metadata_text
    assert "allow_implicit_invocation: true" not in metadata_text
    assert re.search(r"^\s*default_prompt:\s*.*\$ai-native-model-router", metadata_text, re.MULTILINE)
    assert "display_name: \"AI Native Model Router\"" in metadata_text
    assert "short_description: \"Deterministic provider routing with evidence gates\"" in metadata_text

    links = local_link_targets(skill_text)
    expected_links = MODEL_ROUTER_REQUIRED_PATHS - {
        "SKILL.md",
        "agents/openai.yaml",
        "assets/model-router-config.example.json",
    }
    assert links == expected_links
    for target in links:
        assert (skill_dir / target).is_file(), target

    for path in skill_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".py", ".json", ".yaml"}:
            assert not MODEL_ROUTER_FORBIDDEN_TOKENS.search(path.read_text(encoding="utf-8")), path

    json_payloads = {}
    for path in skill_dir.rglob("*.json"):
        try:
            json_payloads[path.relative_to(skill_dir).as_posix()] = json.loads(
                path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise AssertionError(f"invalid Router JSON: {path}: {exc}") from exc
    for path in skill_dir.rglob("*.py"):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise AssertionError(f"invalid Router Python: {path}: {exc}") from exc

    profile = json_payloads["assets/profiles/" + MODEL_ROUTER_PROFILE_ID + ".json"]
    assert profile["schema_version"] == 1
    assert profile["profile_id"] == MODEL_ROUTER_PROFILE_ID
    assert profile["default_active"] is False
    assert profile["activation"] == "explicit-owner-selection"
    assert profile["evidence_date"] == "2026-08-28"
    config = json_payloads["assets/model-router-config.example.json"]
    assert config == {
        "schema_version": 1,
        "router_api_version": "route/v1",
        "config_id": MODEL_ROUTER_CONFIG_ID,
        "active_profile": MODEL_ROUTER_PROFILE_ID,
        "project_profile_dirs": [".ai-native/profiles"],
        "updated_reason": "Explicit project profile selection for route/v1.",
    }
    catalog = json_payloads["assets/provider-catalog.json"]
    assert catalog["schema_version"] == 1
    assert catalog["catalog_id"] == "provider-catalog-2026-08-28"
    assert json_payloads["assets/model-router-config.v1.schema.json"]["$id"] == "model-router-config.v1.schema.json"
    assert json_payloads["assets/route-request.v1.schema.json"]["$id"] == "route-request.v1.schema.json"
    assert json_payloads["assets/route-decision.v1.schema.json"]["$id"] == "route-decision.v1.schema.json"


validate_model_router_bundle(MODEL_ROUTER)


def validate_progressive_disclosure(skill_text: str, skill_dir: Path) -> None:
    frontmatter = re.match(r"\A---\s*\n(.*?)\n---", skill_text, re.DOTALL)
    assert frontmatter, "frontmatter is malformed"
    descriptions = [
        line.split(":", 1)[1].strip()
        for line in frontmatter.group(1).splitlines()
        if line.lstrip().startswith("description:")
    ]
    assert len(descriptions) == 1, "description must occur exactly once"
    description = descriptions[0]
    assert description == EXPECTED_LEVEL_ZERO_DESCRIPTION
    assert len(description) <= MAX_LEVEL_ZERO_DESCRIPTION_CHARS
    assert re.fullmatch(r"[A-Z][A-Za-z0-9-]*(?: [A-Za-z0-9-]+){2,}[.!?]", description)
    assert len(skill_text.splitlines()) <= MAX_LEVEL_ONE_LINES
    assert len(skill_text) <= MAX_LEVEL_ONE_CHARS

    links = local_link_targets(skill_text)
    assert set(CANONICAL_REFERENCE_LINKS) <= links
    assert DQR_REFERENCE_LINK in links
    assert METRICS_REFERENCE_LINK in links
    compact = normalize_policy(skill_text)
    assert "load level-2 assets only on demand" in compact
    assert "do not preload assets; load only the asset whose matching trigger applies" in compact
    assert "dqr is a per-task acceptance protocol, not a routing layer" in compact
    assert "main agent explicitly selects local prospective measurement" in compact
    for target, trigger in ASSET_TRIGGERS.items():
        assert target in links
        line = next(
            (normalize_policy(line) for line in skill_text.splitlines()
             if f"]({target})" in line),
            None,
        )
        assert line is not None
        assert trigger in line
    for target in links:
        assert (skill_dir / target).is_file(), target


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
    DELIVERY_QUALITY_REVIEW,
    METRICS_REFERENCE,
    METRICS_SCHEMA,
    GIT_ISOLATION_REFERENCE,
    SKILL / "references" / "governance-lean.md",
    SKILL / "references" / "governance-controlled.md",
    SKILL / "references" / "governance-strict.md",
    SKILL / "references" / "team-governance-template.zh-CN.md",
    SKILL / "assets" / "team-bootstrap-proposal.md",
    SKILL / "assets" / "project-team-charter.md",
    SKILL / "assets" / "task-contract.md",
    GIT_ISOLATION_HELPER,
    TEAM_METRICS,
    ROOT / "tests" / "routing-scenarios.json",
    ROOT / "tests" / "cost-routing-policy-cases.json",
    ROOT / "tests" / "test_routing_policy.py",
    ROOT / "tests" / "test_git_isolation_bootstrap.py",
    ROOT / "tests" / "test_team_metrics.py",
]
for path in required:
    if not path.is_file():
        fail(f"missing required file: {path.relative_to(ROOT)}")

removed_paths = [
    ROOT / "benchmarks",
    ROOT / "docs" / "images" / "verification-evidence.svg",
    SKILL / "assets" / "evidence-manifest.yaml",
    SKILL / "assets" / "metrics-handoff.yaml",
    SKILL / "references" / "release-audit.md",
    SKILL / "references" / "model-routing-openai-deepseek.md",
    ROOT / "tests" / "fixtures" / "p2",
    ROOT / "tests" / "fixtures" / "p3-public",
    ROOT / "tests" / "test_v2_release_gate.py",
    ROOT / "tests" / "test_p2_pregate.py",
    ROOT / "tests" / "test_p3_sigstore_github_adapter.py",
]
for path in removed_paths:
    if path.exists():
        fail(f"removed product surface still exists: {path.relative_to(ROOT)}")

for manifest in ("requirements.txt", "pyproject.toml", "package.json", "Pipfile"):
    if (ROOT / manifest).exists():
        fail(f"unexpected dependency manifest exists: {manifest}")

for path in (SKILL / "references").iterdir():
    lowered = path.name.casefold()
    if lowered.startswith(("release-", "p2-", "p3-", "zhe125-")):
        fail(f"removed protocol file still exists: {path.relative_to(ROOT)}")

tracked_files = subprocess.check_output(
    ["git", "ls-files", "-z"], cwd=ROOT, text=False
).decode("utf-8").split("\0")
manifest_path = ROOT / "suite-manifest.json"
try:
    suite_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"suite manifest is unreadable: {exc}")
if suite_manifest.get("schema_version") != 1:
    fail("suite manifest schema_version drifted")
for component in suite_manifest.get("components", []):
    component_id = component.get("id")
    tracked_component_files = sorted(
        relative.split("/", 2)[2]
        for relative in tracked_files
        if relative.startswith(f"skills/{component_id}/")
    )
    if component.get("files") != tracked_component_files:
        fail(f"suite manifest inventory drifted: {component_id}")

legacy_scan_paths = {
    item for item in tracked_files if item and not item.startswith("releases/")
}
legacy_scan_paths.update(LEGACY_REFERENCE_ALLOWLIST)
for relative in sorted(legacy_scan_paths):
    path = ROOT / relative
    if not path.is_file() or path.suffix.lower() not in {
        ".md", ".markdown", ".txt", ".json", ".jsonl", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".conf", ".py", ".js", ".ts", ".tsx",
        ".jsx", ".css", ".html", ".xml", ".svg", ".sh", ".ps1", ".bat",
    }:
        continue
    text = path.read_text(encoding="utf-8")
    if relative in LEGACY_REFERENCE_ALLOWLIST:
        expected_count, context = LEGACY_REFERENCE_ALLOWLIST[relative]
        if text.count(OLD_COMPONENT_NAME) != expected_count or context not in text:
            fail(f"legacy reference is outside its bounded exception: {relative}")
    elif OLD_COMPONENT_NAME in text or "skills/" + OLD_COMPONENT_NAME in text:
        fail(f"active file contains legacy component reference: {relative}")
release_count = sum(
    (ROOT / relative).read_text(encoding="utf-8").count(OLD_COMPONENT_NAME)
    for relative in tracked_files
    if relative.startswith("releases/") and (ROOT / relative).is_file()
)
if release_count != 8:
    fail(f"release history legacy occurrence count drifted: {release_count}")

skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
parts = skill_text.split("---", 2)
if len(parts) != 3 or parts[0] != "":
    fail("SKILL.md frontmatter is malformed")
frontmatter_keys = {
    line.split(":", 1)[0].strip()
    for line in parts[1].splitlines()
    if ":" in line
}
if frontmatter_keys != {
    "name", "description", "version", "author", "license", "platforms",
    "metadata", "hermes", "related_skills", "tags",
}:
    fail("SKILL.md frontmatter keys drifted")
if "name: ai-native-dev-team" not in parts[1]:
    fail("SKILL.md name is incorrect")
try:
    validate_progressive_disclosure(skill_text, SKILL)
except AssertionError as exc:
    fail(f"SKILL.md progressive-disclosure contract failed: {exc}")

if "](references/git-isolation-bootstrap.md)" not in skill_text:
    fail("SKILL.md does not link the Linear Git-isolation reference")
for required_isolation_boundary in (
    "linear-governed implementation issue",
    "explicit isolation request",
    "before writer dispatch",
    "non-linear core/controlled routing",
):
    if required_isolation_boundary not in normalize_policy(skill_text):
        fail(f"SKILL.md is missing Linear-isolation activation boundary: {required_isolation_boundary}")

reference_text = GIT_ISOLATION_REFERENCE.read_text(encoding="utf-8")
for required_reference_term in (
    "Linear identity/status/blocker/gitBranchName/latest-checkpoint gate",
    "<repo-parent>/<repo-name>-worktrees/<issue-id-lowercase>",
    "repository-scoped short bootstrap lock",
    "LOCAL_EXECUTION_BLOCKER",
    "git worktree repair",
    "no destructive Git command",
    "plan-only review is a rich, non-mutating evidence preflight",
    "a non-started or blocked issue returns",
    "it is not permission to dispatch",
):
    if required_reference_term.casefold() not in reference_text.casefold():
        fail(f"git isolation reference is missing: {required_reference_term}")
try:
    ast.parse(GIT_ISOLATION_HELPER.read_text(encoding="utf-8"))
except SyntaxError as exc:
    fail(f"git isolation helper has a syntax error: {exc}")

if "optional runtime profiles belong to `ai-native-model-router`" not in skill_text.casefold():
    fail("SKILL.md does not assign optional profiles to the Router")
if "file presence never activates a profile" not in skill_text.casefold():
    fail("SKILL.md does not keep optional profiles inactive by default")

lower_skill = skill_text.casefold()
compact_skill = normalize_policy(skill_text)

for removed in (
    "release audit",
    "release-audit",
    "mode: audit",
    "formal efficiency",
    "historical-baseline",
    "registration receipt",
    "evidence-manifest",
    "p2 ",
    "p3 ",
):
    if contains_removed_term(lower_skill, removed):
        fail(f"SKILL.md still exposes removed surface: {removed}")

for mode in ("proposal", "initialize", "adjust"):
    if mode not in lower_skill:
        fail(f"SKILL.md is missing mode: {mode}")

for required_policy in (
    "standing authorization envelope",
    "strict c0",
    "every c0 mechanical batch",
    "every c1+ implementation",
    "independent validator",
    "repeatedly failed with evidence",
    "cannot be safely re-sliced",
    "explicitly authorizes the takeover",
    "observable runtime mapping",
):
    if required_policy not in compact_skill:
        fail(f"SKILL.md is missing delegated-routing policy: {required_policy}")

for excluded_authority in (
    "credentials or secrets",
    "real or production data",
    "paid resources",
    "publication",
    "push/merge/deploy/release",
    "destructive deletion",
    "irreversible migration",
    "privilege escalation",
    "out-of-scope writes",
    "broad global allowlisting",
):
    if excluded_authority not in compact_skill:
        fail(f"SKILL.md is missing authority exclusion: {excluded_authority}")

windows_lifecycle_docs = {
    "SKILL.md": SKILL / "SKILL.md",
    "routing-and-topologies.md": SKILL / "references" / "routing-and-topologies.md",
    "README.md": ROOT / "README.md",
    "README.zh-CN.md": ROOT / "README.zh-CN.md",
    "global-agents-snippet.md": ROOT / "examples" / "global-agents-snippet.md",
}
for label, path in windows_lifecycle_docs.items():
    compact = " ".join(path.read_text(encoding="utf-8").casefold().split())
    for required_lifecycle_term in (
        "`pty=false`",
        "`background=true`",
        "`notify_on_complete=true`",
        "`pty=true`",
        "registry",
        "`exited`",
        "writer",
        "wait/reconnect",
    ):
        if required_lifecycle_term not in compact:
            fail(f"{label} is missing Windows lifecycle policy: {required_lifecycle_term}")

routing_text = windows_lifecycle_docs["routing-and-topologies.md"].read_text(
    encoding="utf-8"
)
compact_routing = " ".join(routing_text.casefold().split())
for required_lifecycle_policy in (
    "unattended non-interactive coding cli exec, writer, or validator invocations on windows",
    "use `pty=false`, `background=true`, and `notify_on_complete=true` by default",
    "`pty=true` is reserved for an interactive tui, login, or a command that genuinely requires terminal input",
    "never apply it unconditionally to unattended exec",
    "final output text, a final-answer marker, or a tokens-used line is not process-exit evidence",
    "registry status `exited`",
    "captures the exit code",
    "one short bounded grace check",
    "inspect fresh process status",
    "terminate only the exact tracked process",
    "never start a duplicate writer",
    "never repeatedly wait/reconnect",
):
    if required_lifecycle_policy not in compact_routing:
        fail(
            "routing-and-topologies.md is missing fail-closed Windows lifecycle policy: "
            f"{required_lifecycle_policy}"
        )

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
        "metrics handoff",
        "release audit",
        "proposal / initialize / audit",
    ):
        if contains_removed_term(text, removed):
            fail(f"{template} still exposes removed surface: {removed}")

for template in (
    "team-bootstrap-proposal.md",
    "project-team-charter.md",
    "task-contract.md",
):
    text = (SKILL / "assets" / template).read_text(encoding="utf-8").casefold()
    for field in (
        "active routing profile",
        "input tokens",
        "output tokens",
        "steps",
        "first-pass result",
        "reopens",
        "escalation reason",
        "unknown",
    ):
        if field not in text:
            fail(f"{template} is missing lightweight routing field: {field}")

for template in ("task-contract.md",):
    text = (SKILL / "assets" / template).read_text(encoding="utf-8").casefold()
    for field in ISOLATION_TEMPLATE_FIELDS:
        if field not in text:
            fail(f"{template} is missing Linear-isolation field: {field}")

for template in (
    "team-bootstrap-proposal.md",
    "project-team-charter.md",
    "task-contract.md",
):
    text = (SKILL / "assets" / template).read_text(encoding="utf-8").casefold()
    for required_dqr_field in ("dqr", "metrics"):
        if required_dqr_field not in text:
            fail(f"{template} is missing DQR or optional-metrics boundary: {required_dqr_field}")

dqr_text = DELIVERY_QUALITY_REVIEW.read_text(encoding="utf-8")
compact_dqr = normalize_policy(dqr_text)
for required_dqr_term in (
    "not a routing layer",
    "frozen contract",
    "exact path lease",
    "writer self-check",
    "immutable commit, tree, digest",
    "independent, read-only validator",
    "map each finding to a contract requirement",
    "invalidate candidate-bound evidence",
    "main agent accepts only after",
    "known limits",
    "executable rollback",
    "designed",
    "written",
    "run",
    "verified",
    "accepted",
    "integrated",
    "installed",
    "released",
    "exact verified candidate",
    "authority evidence",
    "acceptance does not require prior integration or installation",
    "does not authorize either action",
    "separately authorized integration target",
    "identity readback",
    "separately authorized installation target",
    "rollback backup",
    "byte/readback verification",
    "acceptance implies neither integration nor installation",
    "integration and installation do not imply each other",
    "release, public, and production actions remain separately gated",
):
    if required_dqr_term not in compact_dqr:
        fail(f"delivery-quality-review.md is missing: {required_dqr_term}")

if "accept only the exact validated change integrated into the stable branch" in normalize_policy(skill_text):
    fail("SKILL.md still requires stable-branch integration before acceptance")

state_rows = {
    state: re.search(
        rf"\| {state} \| ([^|]+) \|",
        dqr_text.casefold(),
    )
    for state in ("accepted", "integrated", "installed", "released")
}
if any(match is None for match in state_rows.values()):
    fail("delivery-quality-review.md is missing a lifecycle state row")
if len({match.group(1).strip() for match in state_rows.values()}) != len(state_rows):
    fail("delivery-quality-review.md lifecycle state rows collapsed")

try:
    metrics_schema = json.loads(METRICS_SCHEMA.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    fail(f"metrics event schema is invalid JSON: {exc}")
if metrics_schema.get("properties", {}).get("event", {}).get("enum") != [
    "task_ready",
    "worker_started",
    "dev_complete",
    "qa_complete",
    "accepted",
    "blocked",
    "reopened",
    "cancelled",
]:
    fail("metrics event schema lifecycle drifted")
if metrics_schema.get("properties", {}).get("ledger_writer", {}).get("const") != "main-agent":
    fail("metrics event schema must reserve ledger writes to the main agent")
writer_schema = metrics_schema.get("properties", {}).get("writer", {})
expected_writer_fields = [
    "id",
    "approved",
    "paths",
    "skill_loaded",
    "repo_wide_search_used",
    "out_of_scope_reads",
]
if writer_schema.get("required") != expected_writer_fields:
    fail("metrics event schema writer context fields are not required")
for writer_context_field in expected_writer_fields[3:]:
    if writer_schema.get("properties", {}).get(writer_context_field, {}).get("type") != "boolean":
        fail(f"metrics event schema writer field is not boolean: {writer_context_field}")

metrics_text = normalize_policy(METRICS_REFERENCE.read_text(encoding="utf-8"))
for required_metrics_term in (
    "optional for both core and controlled",
    "sole ledger writer",
    "record",
    "snapshot",
    "audit",
    "compare",
    "hard gates",
    "invalid_writer_path",
    "descriptive",
    "skill_loaded",
    "repo_wide_search_used",
    "out_of_scope_reads",
    "context-saving claim",
    "windows namespace prefixes",
    "extended drive and unc forms",
    "device and pipe forms",
    "nt namespace forms",
    "no active path lease",
    "ordinary `c:/` drives",
    "posix-rooted paths",
    "relative paths remain supported",
):
    if required_metrics_term not in metrics_text:
        fail(f"metrics.md is missing: {required_metrics_term}")

try:
    team_metrics_source = TEAM_METRICS.read_text(encoding="utf-8")
    metrics_tree = ast.parse(team_metrics_source)
except SyntaxError as exc:
    fail(f"team_metrics.py has a syntax error: {exc}")
stdlib_roots = {
    "__future__",
    "argparse",
    "datetime",
    "json",
    "math",
    "os",
    "pathlib",
    "statistics",
    "sys",
    "typing",
}
for node in ast.walk(metrics_tree):
    if isinstance(node, ast.Import):
        roots = [alias.name.split(".", 1)[0] for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        roots = [node.module.split(".", 1)[0]] if node.module else []
    else:
        continue
    if any(root not in stdlib_roots for root in roots):
        fail(f"team_metrics.py imports a non-stdlib module: {roots}")
for hard_gate in (
    "UNAPPROVED_WRITER",
    "WRITER_LOADED_FULL_TEAM_SKILL",
    "WRITER_OUT_OF_SCOPE_READS",
    "INVALID_WRITER_PATH",
    "OVERLAPPING_PATH_OWNERSHIP",
    "NEW_WRITER_WITH_INTEGRATION_BACKLOG",
    "MATERIAL_ACCEPTANCE_WITHOUT_SAME_CANDIDATE_INDEPENDENT_VALIDATION",
    "ACCEPTANCE_WITHOUT_EXACT_IDENTITY_OR_EXECUTABLE_ROLLBACK",
    "R3_WITHOUT_OWNER_APPROVAL",
    "EVIDENCE_REUSE_AFTER_REOPEN_OR_CANDIDATE_CHANGE",
):
    if hard_gate not in team_metrics_source:
        fail(f"team_metrics.py is missing hard gate: {hard_gate}")

namespace_assignments = [
    node
    for node in metrics_tree.body
    if isinstance(node, ast.Assign)
    and any(
        isinstance(target, ast.Name)
        and target.id == "WINDOWS_NAMESPACE_PREFIXES"
        for target in node.targets
    )
]
if len(namespace_assignments) != 1:
    fail("team_metrics.py must declare one Windows namespace prefix contract")
try:
    actual_namespace_prefixes = ast.literal_eval(namespace_assignments[0].value)
except (ValueError, TypeError, SyntaxError) as exc:
    fail(f"Windows namespace prefix contract is not a literal tuple: {exc}")
if actual_namespace_prefixes != EXPECTED_WINDOWS_NAMESPACE_PREFIXES:
    fail("Windows namespace prefix contract drifted")
canonicalizer_start = team_metrics_source.index("def _canonical_path_identity")
namespace_guard_start = team_metrics_source.index(
    "WINDOWS_NAMESPACE_PREFIXES",
    canonicalizer_start,
)
ordinary_parser_start = team_metrics_source.index(
    "if (\n        len(unified)",
    canonicalizer_start,
)
if namespace_guard_start >= ordinary_parser_start:
    fail("Windows namespace rejection must precede ordinary path parsing")
for namespace_contract_term in (
    "writer path uses a Windows device or NT namespace prefix",
    "leased_paths = set() if invalid_writer_path else canonical_paths",
):
    if namespace_contract_term not in team_metrics_source:
        fail(f"team_metrics.py is missing namespace safety behavior: {namespace_contract_term}")

profile_path = MODEL_ROUTER / "assets" / "profiles" / "openai-glm5.3-deepseek-fallback-2026-08-28.json"
try:
    profile_contract = json.loads(profile_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    fail(f"optional routing profile contract is invalid JSON: {exc}")
if profile_contract.get("default_active") is not False:
    fail("optional routing profile must be inactive by default")
if profile_contract.get("activation") != "explicit-owner-selection":
    fail("optional routing profile requires explicit Owner selection")
if profile_contract.get("evidence_date") != "2026-08-28":
    fail("optional routing profile evidence date drifted")

validator_fallback = profile_contract.get("slots", {}).get("validator.independent", {})
if not isinstance(validator_fallback, dict):
    fail("validator fallback object is missing")
if validator_fallback.get("accepted_primary_unavailable_evidence") != EXPECTED_PRIMARY_UNAVAILABLE_EVIDENCE:
    fail("validator fallback evidence list is not the exact accepted array")

high_volume_writer_fallback = profile_contract.get("slots", {}).get("writer.high-volume-deterministic", {})
if not isinstance(high_volume_writer_fallback, dict):
    fail("high-volume Writer fallback object is missing")
if high_volume_writer_fallback.get("accepted_primary_unavailable_evidence") != EXPECTED_PRIMARY_UNAVAILABLE_EVIDENCE:
    fail("high-volume Writer fallback evidence list is not the exact accepted array")

canonical_policy_files = [
    SKILL / "SKILL.md",
    SKILL / "references" / "routing-and-topologies.md",
    SKILL / "references" / "core.md",
    SKILL / "references" / "controlled.md",
    DELIVERY_QUALITY_REVIEW,
    METRICS_REFERENCE,
    SKILL / "assets" / "team-bootstrap-proposal.md",
    SKILL / "assets" / "project-team-charter.md",
    SKILL / "assets" / "task-contract.md",
    SKILL / "agents" / "openai.yaml",
    ROOT / "examples" / "global-agents-snippet.md",
    GIT_ISOLATION_REFERENCE,
    GIT_ISOLATION_HELPER,
    TEAM_METRICS,
]
vendor_names = re.compile(
    r"(?:gpt-5(?:\.|-)|deepseek|openai|anthropic|"
    r"(?<!\w)glm-5\.3(?:-flash)?(?!\w)|\bzai\b)",
    re.IGNORECASE,
)
for path in canonical_policy_files:
    if vendor_names.search(path.read_text(encoding="utf-8")):
        fail(f"canonical policy corpus is not vendor-neutral: {path.relative_to(ROOT)}")
isolation_vendor_names = re.compile(
    r"\b(?:codex|openai|deepseek|anthropic)\b|"
    r"(?<!\w)glm-5\.3(?:-flash)?(?!\w)|\bzai\b",
    re.IGNORECASE,
)
for path in (GIT_ISOLATION_REFERENCE, GIT_ISOLATION_HELPER):
    if isolation_vendor_names.search(path.read_text(encoding="utf-8")):
        fail(f"Git-isolation public files are not vendor-neutral: {path.relative_to(ROOT)}")

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
if not isinstance(scenarios, list) or len(scenarios) < 13:
    fail("routing scenario matrix is too small")
if {case.get("layer") for case in scenarios} != {"core", "controlled"}:
    fail("routing scenarios must use exactly Core and Controlled")
if any(
    contains_removed_term(json.dumps(case, sort_keys=True), "audit")
    for case in scenarios
):
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
if not any(
    case.get("name") == "C0/R1 strict main-agent tiny edit"
    and case.get("route") == "no-delegation"
    and case.get("deterministic_verification_count") == 1
    for case in scenarios
):
    fail("routing scenarios must cover strict C0 tiny-edit eligibility")
if any(
    case.get("complexity") == "C0"
    and case.get("shape") == "deterministic_batch"
    and not case.get("delegated")
    for case in scenarios
):
    fail("C0 mechanical batches must delegate")
if any(case.get("complexity") == "C1" and not case.get("delegated") for case in scenarios):
    fail("C1 implementation scenarios must delegate")

try:
    cost_policy_cases = json.loads(
        (ROOT / "tests" / "cost-routing-policy-cases.json").read_text(encoding="utf-8")
    )
except json.JSONDecodeError as exc:
    fail(f"cost-routing policy cases are invalid JSON: {exc}")
if not isinstance(cost_policy_cases, list) or len(cost_policy_cases) < 3:
    fail("cost-routing policy case matrix is too small")
if not any(
    case.get("main_agent_takeover")
    and case.get("writer_path_status") == "unavailable"
    and case.get("safe_reslice_possible") is False
    and case.get("explicit_high_cost_takeover_authorization") is True
    and case.get("takeover_reason")
    for case in cost_policy_cases
):
    fail("cost-routing cases must cover the full unavailable-Writer takeover conjunction")
if not any(
    case.get("cost_saving_claim")
    and case.get("runtime_mapping_observed")
    and case.get("mapped_to_lower_cost_tier")
    for case in cost_policy_cases
):
    fail("cost-routing cases must bind cost claims to an observed lower-cost mapping")

openai_yaml = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
if "$ai-native-dev-team" not in openai_yaml:
    fail("default prompt does not explicitly invoke the Skill")
if contains_removed_term(openai_yaml, "release audit") or contains_removed_term(
    openai_yaml, "audit work"
):
    fail("openai.yaml advertises removed work")
short_match = re.search(
    r'^\s*short_description:\s*"([^"]+)"',
    openai_yaml,
    re.MULTILINE,
)
if not short_match or not 25 <= len(short_match.group(1)) <= 64:
    fail("short_description must contain 25-64 characters")

active_terminology_files = [
    SKILL / "SKILL.md",
    SKILL / "references" / "routing-and-topologies.md",
    SKILL / "references" / "core.md",
    SKILL / "references" / "controlled.md",
    DELIVERY_QUALITY_REVIEW,
    METRICS_REFERENCE,
    SKILL / "assets" / "team-bootstrap-proposal.md",
    SKILL / "assets" / "project-team-charter.md",
    SKILL / "assets" / "task-contract.md",
    SKILL / "agents" / "openai.yaml",
    ROOT / "CONTRIBUTING.md",
    ROOT / "examples" / "global-agents-snippet.md",
    ROOT / "examples" / "sample-proposal.md",
]
for path in active_terminology_files:
    text = path.read_text(encoding="utf-8").casefold()
    for removed in (
        "release audit",
        "first-five",
        "first five",
        "anchor",
        "receipt",
        "manifest",
        "closure",
        "p2 ",
        "p3 ",
        "historical baseline",
        "benchmark",
        "formal efficiency",
    ):
        if contains_removed_term(text, removed):
            fail(f"active policy exposes removed terminology: {path.relative_to(ROOT)}: {removed}")

for readme, heading in (
    (ROOT / "README.md", "## migrate from the legacy name"),
    (ROOT / "README.zh-CN.md", "## 从旧名称迁移"),
):
    text = readme.read_text(encoding="utf-8")
    active_text, marker, _ = text.casefold().partition(heading)
    if not marker:
        fail(f"migration boundary is missing from {readme.name}")
    for removed in (
        "release audit",
        "anchor",
        "receipt",
        "manifest",
        "closure",
        "p2 ",
        "p3 ",
        "historical baseline",
        "benchmark",
        "formal efficiency",
    ):
        if contains_removed_term(active_text, removed):
            fail(f"active README text exposes historical terminology: {readme.name}: {removed}")

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

print("PASS: AI Native Dev Team Suite structure and routing are valid")
