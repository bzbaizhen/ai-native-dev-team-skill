import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
LOCK_NAME = "git-isolation-bootstrap.lock"
VENDOR_TOKEN = re.compile(r"\b(?:codex|openai|deepseek|anthropic)\b", re.IGNORECASE)
HELPER = (
    ROOT
    / "skills"
    / "bootstrap-ai-native-dev-team"
    / "scripts"
    / "git_isolation_bootstrap.py"
)


def remove_test_owned_root(path: Path) -> None:
    def retry_read_only(function, target, _exc_info) -> None:
        os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
        function(target)

    shutil.rmtree(path, onerror=retry_read_only)


@contextmanager
def disposable_directory():
    path = Path(tempfile.gettempdir()) / f"git-isolation-bootstrap-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        remove_test_owned_root(path)
        if path.exists():
            raise AssertionError(f"test-owned temporary root remains: {path}")
        residue = [
            candidate
            for candidate in ROOT.rglob("git-isolation-bootstrap-*")
            if candidate.is_dir()
        ]
        if residue:
            raise AssertionError(f"repo-local temporary residue remains: {residue}")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def git_common_dir(repo: Path) -> Path:
    value = Path(git(repo, "rev-parse", "--git-common-dir"))
    return value.resolve() if value.is_absolute() else (repo / value).resolve()


def local_branch_exists_for_test(repo: Path, branch: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        capture_output=True,
    ).returncode == 0


def repair_probe_environment(root: Path, target: Path, fail_repair: bool) -> tuple[dict[str, str], Path]:
    real_git = shutil.which("git")
    if real_git is None:
        raise RuntimeError("Git executable is unavailable")
    log_path = root / "git-audit.log"
    sentinel_path = root / "metadata-failed-once"
    wrapper = root / "git-wrapper.py"
    wrapper.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "import subprocess\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        "with Path(os.environ['GIT_ISOLATION_AUDIT_LOG']).open('a', encoding='utf-8') as handle:\n"
        "    handle.write(' '.join(args) + '\\n')\n"
        "if args[:4] == ['-C', os.environ['GIT_ISOLATION_REPAIR_TARGET'], 'rev-parse', '--show-toplevel'] and not Path(os.environ['GIT_ISOLATION_FAIL_ONCE']).exists():\n"
        "    Path(os.environ['GIT_ISOLATION_FAIL_ONCE']).write_text('failed', encoding='utf-8')\n"
        "    raise SystemExit(128)\n"
        "if args[:4] == ['-C', args[1] if len(args) > 1 else '', 'worktree', 'repair'] and os.environ['GIT_ISOLATION_FAIL_REPAIR'] == '1':\n"
        "    raise SystemExit(128)\n"
        "raise SystemExit(subprocess.run([os.environ['GIT_ISOLATION_REAL_GIT'], *args]).returncode)\n",
        encoding="utf-8",
    )
    return (
        {
            "GIT_ISOLATION_GIT_COMMAND_JSON": json.dumps([sys.executable, str(wrapper)]),
            "GIT_ISOLATION_REAL_GIT": real_git,
            "GIT_ISOLATION_AUDIT_LOG": str(log_path),
            "GIT_ISOLATION_REPAIR_TARGET": str(target),
            "GIT_ISOLATION_FAIL_ONCE": str(sentinel_path),
            "GIT_ISOLATION_FAIL_REPAIR": "1" if fail_repair else "0",
        },
        log_path,
    )


def make_repo(root: Path, name: str = "isolation-repo") -> tuple[Path, str]:
    repo = root / name
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Isolation Test")
    git(repo, "config", "user.email", "isolation@example.invalid")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "fixture")
    git(repo, "branch", "-M", "main")
    return repo, git(repo, "rev-parse", "HEAD")


def make_remote_only_repo(root: Path, branch: str) -> tuple[Path, str]:
    remote = root / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
    )
    seed, base_commit = make_repo(root, "seed")
    git(seed, "branch", branch, base_commit)
    bundle = root / "remote.bundle"
    git(seed, "bundle", "create", str(bundle), "--all")
    subprocess.run(
        [
            "git",
            "--git-dir",
            str(remote),
            "fetch",
            str(bundle),
            "refs/heads/main:refs/heads/main",
            f"refs/heads/{branch}:refs/heads/{branch}",
        ],
        check=True,
        capture_output=True,
    )
    repo = root / "consumer"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Isolation Test")
    git(repo, "config", "user.email", "isolation@example.invalid")
    git(repo, "fetch", str(bundle), "refs/heads/main:refs/heads/main")
    git(repo, "checkout", "--quiet", "main")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "update-ref", "refs/remotes/origin/main", base_commit)
    git(repo, "update-ref", f"refs/remotes/origin/{branch}", base_commit)
    return repo, base_commit


def checkpoint(
    issue_id: str,
    issue_uuid: str,
    branch: str,
    base_ref: str,
    base_commit: str,
    path: Path,
) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "issue_uuid": issue_uuid,
            "issue_id": issue_id,
            "git_branch_name": branch,
            "base_ref": base_ref,
            "base_commit": base_commit,
            "canonical_worktree": str(path),
            "state": "READY_FOR_ISOLATION",
        }
    )


def invoke(
    repo: Path,
    base_commit: str,
    issue_id: str,
    issue_uuid: str,
    branch: str,
    path: Path,
    mode: str = "plan",
    base_ref: str = "main",
    worktree_path: Path | None = None,
    extra_args: tuple[str, ...] = (),
    environment: dict[str, str] | None = None,
    linear_status_category: str = "started",
    linear_blocker: str = "false",
) -> tuple[subprocess.CompletedProcess[str], dict]:
    command = [
        sys.executable,
        "-B",
        str(HELPER),
        "--mode",
        mode,
        "--issue-id",
        issue_id,
        "--issue-uuid",
        issue_uuid,
        "--linear-status-category",
        linear_status_category,
        "--linear-blocker",
        linear_blocker,
        "--git-branch-name",
        branch,
        "--repo",
        str(repo),
        "--base-ref",
        base_ref,
        "--base-commit",
        base_commit,
        "--latest-checkpoint-json",
        checkpoint(issue_id, issue_uuid, branch, base_ref, base_commit, path),
    ]
    if worktree_path is not None:
        command.extend(("--worktree-path", str(worktree_path)))
    command.extend(extra_args)
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        env={**os.environ, **(environment or {})},
    )
    return result, json.loads(result.stdout) if result.stdout else {}


class GitIsolationBootstrapContractTests(unittest.TestCase):
    def test_public_isolation_files_are_vendor_neutral_and_use_skill_local_helper(self) -> None:
        reference = (
            ROOT
            / "skills"
            / "bootstrap-ai-native-dev-team"
            / "references"
            / "git-isolation-bootstrap.md"
        )
        for path in (reference, HELPER):
            self.assertIsNone(VENDOR_TOKEN.search(path.read_text(encoding="utf-8")), path)
            self.assertNotIn("codex-git-isolation-bootstrap.lock", path.read_text(encoding="utf-8"))
        reference_text = reference.read_text(encoding="utf-8")
        self.assertIn(
            "skills/bootstrap-ai-native-dev-team/scripts/git_isolation_bootstrap.py",
            reference_text,
        )
        self.assertNotIn("python -B scripts/git_isolation_bootstrap.py", reference_text)
        self.assertIn(LOCK_NAME, reference_text)
        reference_lower = reference_text.casefold()
        for phrase in (
            "plan-only review is a rich, non-mutating evidence preflight",
            "a non-started or blocked issue returns",
            "it is not permission to dispatch",
        ):
            self.assertIn(phrase, reference_lower)


class GitIsolationBootstrapPlanTests(unittest.TestCase):
    def test_plan_and_inspect_return_rich_blockers_for_unauthorized_linear_states(self) -> None:
        fixtures = (
            (
                "ZHE-171",
                "17111111-1111-4111-8111-111111111111",
                "linear/zhe-171-plan-review",
                "backlog",
                "false",
                "LINEAR_STATUS_NOT_STARTED",
            ),
            (
                "ZHE-173",
                "17333333-3333-4333-8333-333333333333",
                "linear/zhe-173-plan-review",
                "completed",
                "false",
                "LINEAR_STATUS_NOT_STARTED",
            ),
            (
                "ZHE-175",
                "17555555-5555-4555-8555-555555555555",
                "linear/zhe-175-plan-review",
                "started",
                "true",
                "LINEAR_BLOCKER_PRESENT",
            ),
        )
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            for issue_id, issue_uuid, branch, status, blocker, code in fixtures:
                with self.subTest(issue_id=issue_id, status=status, blocker=blocker):
                    path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
                    for mode in ("plan", "inspect"):
                        with self.subTest(mode=mode):
                            result, payload = invoke(
                                repo,
                                base_commit,
                                issue_id,
                                issue_uuid,
                                branch,
                                path,
                                mode=mode,
                                linear_status_category=status,
                                linear_blocker=blocker,
                            )
                            self.assertEqual(
                                result.returncode,
                                3,
                                f"{result.stderr}\n{payload}",
                            )
                            self.assertEqual(payload["status"], "LOCAL_EXECUTION_BLOCKER")
                            self.assertEqual(payload["exit_code"], 3)
                            self.assertEqual(payload["blocker"]["code"], code)
                            facts = payload["blocker"]["confirmed_facts"]
                            self.assertEqual(facts["issue_id"], issue_id)
                            self.assertEqual(facts["issue_uuid"], issue_uuid)
                            self.assertEqual(facts["git_branch_name"], branch)
                            self.assertEqual(facts["linear_status_category"], status)
                            self.assertEqual(facts["linear_blocker"], blocker == "true")
                            self.assertEqual(facts["canonical_worktree"], str(path))
                            self.assertEqual(facts["base_ref"], "main")
                            self.assertEqual(facts["base_commit"], base_commit)
                            self.assertEqual(facts["worktree_state"], "created-from-base")
                            self.assertEqual(facts["continuation_state"], "not-started")
                            self.assertIsNone(facts["current_head"])
                            self.assertEqual(payload["mode"], mode)
                            self.assertIn(
                                "no branch was created, replaced, or checked out",
                                payload["blocker"]["actions_not_executed"],
                            )
                            self.assertFalse(
                                any(
                                    "plan-only review" in option
                                    for option in payload["blocker"]["recovery_options"]
                                )
                            )
                            self.assertFalse(path.exists())
                    apply_result, apply_payload = invoke(
                        repo,
                        base_commit,
                        issue_id,
                        issue_uuid,
                        branch,
                        path,
                        mode="apply",
                        linear_status_category=status,
                        linear_blocker=blocker,
                    )
                    self.assertEqual(
                        apply_result.returncode,
                        3,
                        f"{apply_result.stderr}\n{apply_payload}",
                    )
                    self.assertEqual(apply_payload["status"], "LOCAL_EXECUTION_BLOCKER")
                    self.assertEqual(apply_payload["blocker"]["code"], code)
                    self.assertFalse(path.exists())
                    self.assertFalse(local_branch_exists_for_test(repo, branch))

    def test_plan_mode_keeps_three_linear_issue_pairs_non_mutating(self) -> None:
        fixtures = (
            (
                "ZHE-171",
                "11111111-1111-4111-8111-111111111111",
                "linear/zhe-171-isolation",
            ),
            (
                "ZHE-173",
                "33333333-3333-4333-8333-333333333333",
                "linear/zhe-173-isolation",
            ),
            (
                "ZHE-175",
                "55555555-5555-4555-8555-555555555555",
                "linear/zhe-175-isolation",
            ),
        )
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            for issue_id, issue_uuid, branch in fixtures:
                with self.subTest(issue_id=issue_id):
                    path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
                    result, payload = invoke(
                        repo, base_commit, issue_id, issue_uuid, branch, path
                    )
                    self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
                    self.assertEqual(payload["status"], "PLAN_READY")
                    self.assertEqual(payload["issue"]["git_branch_name"], branch)
                    self.assertEqual(payload["worktree"]["path"], str(path))
                    self.assertFalse(path.exists())

    def test_inspect_mode_is_a_non_mutating_plan_alias(self) -> None:
        issue_id = "ZHE-176"
        issue_uuid = "17666666-6666-4666-8666-666666666666"
        branch = "linear/zhe-176-inspect"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="inspect"
            )
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["status"], "PLAN_READY")
            self.assertEqual(payload["mode"], "inspect")
            self.assertFalse(path.exists())

    def test_plan_blocks_an_invalid_exact_linear_branch_name(self) -> None:
        issue_id = "ZHE-177"
        issue_uuid = "17777777-7777-4777-8777-777777777777"
        branch = "linear/zhe-177 invalid"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path
            )
            self.assertEqual(result.returncode, 2, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["status"], "LOCAL_EXECUTION_BLOCKER")
            self.assertEqual(payload["blocker"]["code"], "INVALID_GIT_BRANCH_NAME")

    def test_plan_classifies_safe_create_from_accepted_base(self) -> None:
        issue_id = "ZHE-199"
        issue_uuid = "19999999-9999-4999-8999-999999999999"
        branch = "linear/zhe-199-plan-create"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(repo, base_commit, issue_id, issue_uuid, branch, path)
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["worktree"]["state"], "created-from-base")
            self.assertEqual(payload["worktree"]["continuation_state"], "not-started")
            self.assertIsNone(payload["worktree"]["current_head"])
            self.assertFalse(path.exists())

    def test_plan_classifies_existing_local_branch_as_attach(self) -> None:
        issue_id = "ZHE-200"
        issue_uuid = "20000000-0000-4000-8000-000000000000"
        branch = "linear/zhe-200-plan-local"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            git(repo, "branch", branch, base_commit)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(repo, base_commit, issue_id, issue_uuid, branch, path)
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["worktree"]["state"], "attached-local-branch")
            self.assertEqual(payload["worktree"]["continuation_state"], "not-started")
            self.assertEqual(payload["worktree"]["current_head"], base_commit)
            self.assertFalse(path.exists())

    def test_plan_classifies_verified_remote_branch(self) -> None:
        issue_id = "ZHE-201"
        issue_uuid = "20111111-1111-4111-8111-111111111111"
        branch = "linear/zhe-201-plan-remote"
        with disposable_directory() as temporary:
            repo, base_commit = make_remote_only_repo(temporary, branch)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(repo, base_commit, issue_id, issue_uuid, branch, path)
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["worktree"]["state"], "tracked-remote-branch")
            self.assertEqual(payload["worktree"]["continuation_state"], "not-started")
            self.assertEqual(payload["worktree"]["current_head"], base_commit)
            self.assertFalse(path.exists())

    def test_plan_classifies_exact_clean_and_dirty_reuse(self) -> None:
        issue_id = "ZHE-202"
        issue_uuid = "20222222-2222-4222-8222-222222222222"
        branch = "linear/zhe-202-plan-reuse"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            git(repo, "worktree", "add", "-b", branch, str(path), base_commit)
            clean, clean_payload = invoke(repo, base_commit, issue_id, issue_uuid, branch, path)
            self.assertEqual(clean.returncode, 0, f"{clean.stderr}\n{clean_payload}")
            self.assertEqual(clean_payload["worktree"]["state"], "same-issue-reuse")
            self.assertEqual(clean_payload["worktree"]["continuation_state"], "clean")
            self.assertEqual(clean_payload["worktree"]["current_head"], base_commit)
            (path / "README.md").write_text("dirty continuation\n", encoding="utf-8")
            dirty, dirty_payload = invoke(repo, base_commit, issue_id, issue_uuid, branch, path)
            self.assertEqual(dirty.returncode, 0, f"{dirty.stderr}\n{dirty_payload}")
            self.assertEqual(dirty_payload["worktree"]["state"], "same-issue-reuse")
            self.assertEqual(dirty_payload["worktree"]["continuation_state"], "dirty")
            self.assertIn("preserved dirty working files", dirty_payload["actions"])


class GitIsolationBootstrapApplyTests(unittest.TestCase):
    def test_apply_creates_first_issue_worktree_from_accepted_base(self) -> None:
        issue_id = "ZHE-181"
        issue_uuid = "18111111-1111-4111-8111-111111111111"
        branch = "linear/zhe-181-first-create"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["status"], "APPLIED")
            self.assertTrue(path.is_dir())
            self.assertEqual(git(path, "branch", "--show-current"), branch)
            self.assertEqual(git(path, "rev-parse", "HEAD"), base_commit)

    def test_apply_is_idempotent_for_an_exact_same_issue_worktree(self) -> None:
        issue_id = "ZHE-182"
        issue_uuid = "18222222-2222-4222-8222-222222222222"
        branch = "linear/zhe-182-idempotent"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            first, first_payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(first.returncode, 0, f"{first.stderr}\n{first_payload}")
            head_before = git(path, "rev-parse", "HEAD")
            second, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(second.returncode, 0, f"{second.stderr}\n{payload}")
            self.assertEqual(payload["status"], "REUSED")
            self.assertEqual(git(path, "rev-parse", "HEAD"), head_before)

    def test_apply_attaches_an_existing_local_issue_branch(self) -> None:
        issue_id = "ZHE-183"
        issue_uuid = "18333333-3333-4333-8333-333333333333"
        branch = "linear/zhe-183-local-branch"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            git(repo, "branch", branch, base_commit)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["status"], "APPLIED")
            self.assertEqual(payload["worktree"]["state"], "attached-local-branch")
            self.assertEqual(git(path, "branch", "--show-current"), branch)

    def test_apply_tracks_a_verified_remote_only_issue_branch(self) -> None:
        issue_id = "ZHE-184"
        issue_uuid = "18444444-4444-4444-8444-444444444444"
        branch = "linear/zhe-184-remote-only"
        with disposable_directory() as temporary:
            repo, base_commit = make_remote_only_repo(temporary, branch)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["status"], "APPLIED")
            self.assertEqual(payload["worktree"]["state"], "tracked-remote-branch")
            self.assertEqual(git(path, "branch", "--show-current"), branch)

    def test_apply_reuses_a_preexisting_same_issue_worktree(self) -> None:
        issue_id = "ZHE-185"
        issue_uuid = "18555555-5555-4555-8555-555555555555"
        branch = "linear/zhe-185-preexisting"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            path.parent.mkdir()
            git(repo, "worktree", "add", "-b", branch, str(path), base_commit)
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["status"], "REUSED")
            self.assertEqual(payload["worktree"]["state"], "same-issue-reuse")
            self.assertEqual(git(path, "branch", "--show-current"), branch)


class GitIsolationBootstrapSafetyTests(unittest.TestCase):
    def assert_blocker(
        self, result: subprocess.CompletedProcess[str], payload: dict, code: str
    ) -> None:
        self.assertEqual(result.returncode, 3, f"{result.stderr}\n{payload}")
        self.assertEqual(payload["status"], "LOCAL_EXECUTION_BLOCKER")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocker"]["code"], code)
        self.assertEqual(
            set(payload["blocker"]),
            {
                "code",
                "confirmed_facts",
                "conflict",
                "impact",
                "actions_not_executed",
                "recovery_options",
                "required_decision",
                "evidence",
            },
        )

    def test_apply_preserves_a_dirty_same_issue_continuation(self) -> None:
        issue_id = "ZHE-186"
        issue_uuid = "18666666-6666-4666-8666-666666666666"
        branch = "linear/zhe-186-dirty-continuation"
        patch = (
            "diff --git a/README.md b/README.md\n"
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -1 +1,2 @@\n"
            " fixture\n"
            "+dirty continuation\n"
        )
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            created, created_payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(created.returncode, 0, f"{created.stderr}\n{created_payload}")
            apply_result = subprocess.run(
                ["git", "-C", str(path), "apply", "-"],
                input=patch,
                text=True,
                capture_output=True,
            )
            self.assertEqual(
                apply_result.returncode,
                0,
                apply_result.stderr or apply_result.stdout,
            )
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["status"], "REUSED")
            self.assertEqual(payload["worktree"]["continuation_state"], "dirty")
            self.assertIn("preserved dirty working files", payload["actions"])
            self.assertIn("dirty continuation", git(path, "diff", "--", "README.md"))

    def test_apply_blocks_a_non_git_target_path_collision(self) -> None:
        issue_id = "ZHE-187"
        issue_uuid = "18777777-7777-4777-8777-777777777777"
        branch = "linear/zhe-187-path-collision"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            path.mkdir(parents=True)
            (path / "foreign.txt").write_text("foreign", encoding="utf-8")
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assert_blocker(result, payload, "PATH_COLLISION")

    def test_plan_and_inspect_block_an_absent_nested_path_inside_main_checkout(self) -> None:
        issue_id = "ZHE-203"
        issue_uuid = "20333333-3333-4333-8333-333333333333"
        branch = "linear/zhe-203-nested-repo-path"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo / "forbidden" / issue_id.lower()
            for mode in ("plan", "inspect", "apply"):
                with self.subTest(mode=mode):
                    result, payload = invoke(
                        repo,
                        base_commit,
                        issue_id,
                        issue_uuid,
                        branch,
                        path,
                        mode=mode,
                        worktree_path=path,
                    )
                    self.assert_blocker(result, payload, "WORKTREE_PATH_INSIDE_REPOSITORY")
                    self.assertFalse(path.exists())
                    self.assertFalse(path.parent.exists())
            self.assertFalse(local_branch_exists_for_test(repo, branch))

    def test_plan_and_apply_block_an_absent_nested_path_inside_registered_sibling(self) -> None:
        issue_id = "ZHE-204"
        issue_uuid = "20444444-4444-4444-8444-444444444444"
        branch = "linear/zhe-204-nested-sibling-path"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            sibling = temporary / "registered-sibling"
            git(repo, "worktree", "add", "-b", "linear/zhe-204-sibling", str(sibling), base_commit)
            path = sibling / "forbidden" / issue_id.lower()
            for mode in ("plan", "apply"):
                with self.subTest(mode=mode):
                    result, payload = invoke(
                        repo,
                        base_commit,
                        issue_id,
                        issue_uuid,
                        branch,
                        path,
                        mode=mode,
                        worktree_path=path,
                    )
                    self.assert_blocker(
                        result, payload, "WORKTREE_PATH_INSIDE_REGISTERED_WORKTREE"
                    )
                    self.assertFalse(path.exists())
            self.assertFalse(local_branch_exists_for_test(repo, branch))

    def test_plan_and_inspect_block_an_existing_unregistered_path_collision(self) -> None:
        issue_id = "ZHE-205"
        issue_uuid = "20555555-5555-4555-8555-555555555555"
        branch = "linear/zhe-205-plan-collision"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            path.mkdir(parents=True)
            (path / "foreign.txt").write_text("foreign", encoding="utf-8")
            for mode in ("plan", "inspect"):
                with self.subTest(mode=mode):
                    result, payload = invoke(
                        repo,
                        base_commit,
                        issue_id,
                        issue_uuid,
                        branch,
                        path,
                        mode=mode,
                    )
                    self.assert_blocker(result, payload, "PATH_COLLISION")
                    self.assertTrue((path / "foreign.txt").is_file())

    def test_plan_and_inspect_block_wrong_branch_at_registered_target(self) -> None:
        issue_id = "ZHE-206"
        issue_uuid = "20666666-6666-4666-8666-666666666666"
        expected_branch = "linear/zhe-206-authoritative"
        other_branch = "linear/zhe-206-other"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            path.parent.mkdir()
            git(repo, "worktree", "add", "-b", other_branch, str(path), base_commit)
            for mode in ("plan", "inspect"):
                with self.subTest(mode=mode):
                    result, payload = invoke(
                        repo,
                        base_commit,
                        issue_id,
                        issue_uuid,
                        expected_branch,
                        path,
                        mode=mode,
                    )
                    self.assert_blocker(result, payload, "WRONG_BRANCH_OR_PATH")
                    self.assertEqual(git(path, "branch", "--show-current"), other_branch)

    def test_plan_and_inspect_block_a_branch_checked_out_elsewhere(self) -> None:
        issue_id = "ZHE-207"
        issue_uuid = "20777777-7777-4777-8777-777777777777"
        branch = "linear/zhe-207-elsewhere"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            elsewhere = temporary / "elsewhere"
            git(repo, "worktree", "add", "-b", branch, str(elsewhere), base_commit)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            for mode in ("plan", "inspect"):
                with self.subTest(mode=mode):
                    result, payload = invoke(
                        repo,
                        base_commit,
                        issue_id,
                        issue_uuid,
                        branch,
                        path,
                        mode=mode,
                    )
                    self.assert_blocker(result, payload, "BRANCH_CHECKED_OUT_ELSEWHERE")
                    self.assertFalse(path.exists())

    def test_plan_and_inspect_block_an_unverified_remote_before_mutation(self) -> None:
        issue_id = "ZHE-208"
        issue_uuid = "20888888-8888-4888-8888-888888888888"
        branch = "linear/zhe-208-unverified-remote"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            git(repo, "remote", "add", "origin", str(temporary / "missing-origin.git"))
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            for mode in ("plan", "inspect"):
                with self.subTest(mode=mode):
                    result, payload = invoke(
                        repo,
                        base_commit,
                        issue_id,
                        issue_uuid,
                        branch,
                        path,
                        mode=mode,
                    )
                    self.assert_blocker(result, payload, "REMOTE_IDENTITY_UNVERIFIABLE")
                    self.assertFalse(path.exists())
                    self.assertFalse(path.parent.exists())

    def test_plan_blocks_stale_remote_tracking_state_before_mutation(self) -> None:
        issue_id = "ZHE-209"
        issue_uuid = "20999999-9999-4999-8999-999999999999"
        branch = "linear/zhe-209-stale-remote"
        with disposable_directory() as temporary:
            repo, base_commit = make_remote_only_repo(temporary, branch)
            (repo / "README.md").write_text("remote update\n", encoding="utf-8")
            git(repo, "add", "README.md")
            git(repo, "commit", "-m", "remote update")
            new_commit = git(repo, "rev-parse", "HEAD")
            source_objects = repo / ".git" / "objects"
            remote_objects = temporary / "origin.git" / "objects"
            for source in source_objects.rglob("*"):
                if source.is_file():
                    destination = remote_objects / source.relative_to(source_objects)
                    if destination.exists():
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
            subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(temporary / "origin.git"),
                    "update-ref",
                    f"refs/heads/{branch}",
                    new_commit,
                ],
                check=True,
                capture_output=True,
            )
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(
                repo,
                base_commit,
                issue_id,
                issue_uuid,
                branch,
                path,
                base_ref="origin/main",
            )
            self.assert_blocker(result, payload, "STALE_REMOTE_REF")
            self.assertFalse(path.exists())

    def test_plan_and_inspect_block_unreadable_registered_metadata(self) -> None:
        issue_id = "ZHE-210"
        issue_uuid = "21000000-0000-4000-8000-000000000000"
        branch = "linear/zhe-210-metadata"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            git(repo, "worktree", "add", "-b", branch, str(path), base_commit)
            for mode in ("plan", "inspect"):
                probe_root = temporary / f"probe-{mode}"
                probe_root.mkdir()
                environment, audit_log = repair_probe_environment(probe_root, path, False)
                result, payload = invoke(
                    repo,
                    base_commit,
                    issue_id,
                    issue_uuid,
                    branch,
                    path,
                    mode=mode,
                    environment=environment,
                )
                self.assert_blocker(result, payload, "WORKTREE_METADATA_UNREADABLE")
                self.assertNotIn("worktree repair", audit_log.read_text(encoding="utf-8"))

    def test_apply_blocks_branch_checked_out_elsewhere(self) -> None:
        issue_id = "ZHE-188"
        issue_uuid = "18888888-8888-4888-8888-888888888888"
        branch = "linear/zhe-188-elsewhere"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            elsewhere = temporary / "elsewhere"
            git(repo, "worktree", "add", "-b", branch, str(elsewhere), base_commit)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assert_blocker(result, payload, "BRANCH_CHECKED_OUT_ELSEWHERE")

    def test_apply_blocks_a_registered_target_on_the_wrong_branch(self) -> None:
        issue_id = "ZHE-189"
        issue_uuid = "18999999-9999-4999-8999-999999999999"
        expected_branch = "linear/zhe-189-authoritative"
        other_branch = "linear/zhe-189-other"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            path.parent.mkdir()
            git(repo, "worktree", "add", "-b", other_branch, str(path), base_commit)
            result, payload = invoke(
                repo,
                base_commit,
                issue_id,
                issue_uuid,
                expected_branch,
                path,
                mode="apply",
            )
            self.assert_blocker(result, payload, "WRONG_BRANCH_OR_PATH")

    def test_apply_blocks_target_from_a_different_repository_gitdir(self) -> None:
        issue_id = "ZHE-190"
        issue_uuid = "19000000-0000-4000-8000-000000000000"
        branch = "linear/zhe-190-wrong-repository"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            other_repo, other_base = make_repo(temporary, "other-repository")
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            path.parent.mkdir()
            git(other_repo, "worktree", "add", "-b", "linear/zhe-190-other", str(path), other_base)
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assert_blocker(result, payload, "WRONG_REPOSITORY_OR_GITDIR")

    def test_apply_blocks_missing_invalid_and_stale_base(self) -> None:
        issue_id = "ZHE-191"
        issue_uuid = "19111111-1111-4111-8111-111111111111"
        branch = "linear/zhe-191-base-gate"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            stale, stale_payload = invoke(
                repo, "0" * 40, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assert_blocker(stale, stale_payload, "MISSING_INVALID_OR_STALE_BASE")
            missing, missing_payload = invoke(
                repo,
                base_commit,
                issue_id,
                issue_uuid,
                branch,
                path,
                mode="apply",
                base_ref="does-not-exist",
            )
            self.assert_blocker(missing, missing_payload, "MISSING_INVALID_OR_STALE_BASE")
            invalid, invalid_payload = invoke(
                repo, "not-a-full-sha", issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(invalid.returncode, 2, f"{invalid.stderr}\n{invalid_payload}")
            self.assertEqual(invalid_payload["blocker"]["code"], "INVALID_BASE_COMMIT")

    def test_apply_blocks_issue_branch_mismatch(self) -> None:
        issue_id = "ZHE-192"
        issue_uuid = "19222222-2222-4222-8222-222222222222"
        branch = "linear/zhe-999-mismatch"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assert_blocker(result, payload, "ISSUE_BRANCH_MISMATCH")

    def test_apply_treats_a_preexisting_bootstrap_lock_as_a_collision(self) -> None:
        issue_id = "ZHE-193"
        issue_uuid = "19333333-3333-4333-8333-333333333333"
        branch = "linear/zhe-193-lock-collision"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            lock_path = git_common_dir(repo) / LOCK_NAME
            subprocess.run(
                ["git", "config", "--file", str(lock_path), "issue.id", issue_id],
                check=True,
                capture_output=True,
            )
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assert_blocker(result, payload, "CONCURRENT_BOOTSTRAP_LOCK")
            self.assertTrue(lock_path.exists())

    def test_apply_does_not_create_a_parent_for_a_blocked_remote_state(self) -> None:
        issue_id = "ZHE-198"
        issue_uuid = "19888888-8888-4888-8888-888888888888"
        branch = "linear/zhe-198-stale-remote"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            remote = temporary / "empty-origin.git"
            subprocess.run(
                ["git", "init", "--bare", str(remote)],
                check=True,
                capture_output=True,
            )
            git(repo, "remote", "add", "origin", str(remote))
            git(repo, "update-ref", f"refs/remotes/origin/{branch}", base_commit)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            self.assertFalse(path.parent.exists())
            result, payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assert_blocker(result, payload, "REMOTE_IDENTITY_UNVERIFIABLE")
            self.assertFalse(path.parent.exists())


class GitIsolationBootstrapRepairTests(unittest.TestCase):
    def test_apply_repairs_only_a_proven_registered_same_issue_metadata_case(self) -> None:
        issue_id = "ZHE-194"
        issue_uuid = "19444444-4444-4444-8444-444444444444"
        branch = "linear/zhe-194-repairable"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            created, created_payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(created.returncode, 0, f"{created.stderr}\n{created_payload}")
            environment, audit_log = repair_probe_environment(temporary, path, False)
            result, payload = invoke(
                repo,
                base_commit,
                issue_id,
                issue_uuid,
                branch,
                path,
                mode="apply",
                environment=environment,
            )
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["status"], "REUSED")
            self.assertEqual(payload["worktree"]["state"], "repaired-same-issue-reuse")
            self.assertIn("worktree repair", audit_log.read_text(encoding="utf-8"))

    def test_apply_blocks_non_repairable_registered_metadata(self) -> None:
        issue_id = "ZHE-195"
        issue_uuid = "19555555-5555-4555-8555-555555555555"
        branch = "linear/zhe-195-nonrepairable"
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            created, created_payload = invoke(
                repo, base_commit, issue_id, issue_uuid, branch, path, mode="apply"
            )
            self.assertEqual(created.returncode, 0, f"{created.stderr}\n{created_payload}")
            environment, audit_log = repair_probe_environment(temporary, path, True)
            result, payload = invoke(
                repo,
                base_commit,
                issue_id,
                issue_uuid,
                branch,
                path,
                mode="apply",
                environment=environment,
            )
            self.assertEqual(result.returncode, 3, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["status"], "LOCAL_EXECUTION_BLOCKER")
            self.assertEqual(payload["blocker"]["code"], "NON_REPAIRABLE_METADATA")
            self.assertIn("worktree repair", audit_log.read_text(encoding="utf-8"))


class GitIsolationBootstrapRemoteBaseTests(unittest.TestCase):
    def test_plan_mode_validates_a_remote_base_live_not_from_cached_ref(self) -> None:
        issue_id = "ZHE-196"
        issue_uuid = "19666666-6666-4666-8666-666666666666"
        branch = "linear/zhe-196-remote-base"
        with disposable_directory() as temporary:
            repo, base_commit = make_remote_only_repo(temporary, branch)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            result, payload = invoke(
                repo,
                base_commit,
                issue_id,
                issue_uuid,
                branch,
                path,
                base_ref="origin/main",
            )
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            self.assertEqual(payload["base"]["ref_kind"], "remote")
            self.assertEqual(payload["base"]["remote"]["name"], "origin")
            self.assertEqual(payload["base"]["remote"]["verification"], "local-remote-gitdir")


class GitIsolationBootstrapDestructiveCommandTests(unittest.TestCase):
    def test_apply_executes_no_forbidden_destructive_git_command(self) -> None:
        issue_id = "ZHE-197"
        issue_uuid = "19777777-7777-4777-8777-777777777777"
        branch = "linear/zhe-197-command-audit"
        forbidden = (
            " reset ",
            " clean ",
            " stash ",
            " rebase ",
            " checkout ",
            " switch ",
            " restore ",
            " branch -D",
            " worktree remove",
            " worktree prune",
            " worktree move",
        )
        with disposable_directory() as temporary:
            repo, base_commit = make_repo(temporary)
            path = repo.parent / f"{repo.name}-worktrees" / issue_id.lower()
            environment, audit_log = repair_probe_environment(
                temporary, temporary / "unrelated-target", False
            )
            result, payload = invoke(
                repo,
                base_commit,
                issue_id,
                issue_uuid,
                branch,
                path,
                mode="apply",
                environment=environment,
            )
            self.assertEqual(result.returncode, 0, f"{result.stderr}\n{payload}")
            commands = f" {audit_log.read_text(encoding='utf-8').casefold()} "
            self.assertIn(" worktree add", commands)
            for token in forbidden:
                with self.subTest(command=token):
                    self.assertNotIn(token.casefold(), commands)


if __name__ == "__main__":
    unittest.main()
