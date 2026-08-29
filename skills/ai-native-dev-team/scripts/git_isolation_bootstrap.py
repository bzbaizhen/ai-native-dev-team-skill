#!/usr/bin/env python3
"""Plan or safely bootstrap one Linear-governed Git worktree.

The helper intentionally owns no Linear credentials.  Callers supply the latest
Linear readback, and this program verifies that it agrees with local Git facts.
Every normal outcome is a single JSON object on stdout.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import UUID


SCHEMA_VERSION = 1
EXIT_OK = 0
EXIT_INPUT_INVALID = 2
EXIT_BLOCKED = 3
EXIT_OPERATION_FAILED = 4
ISSUE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
FULL_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
BOOTSTRAP_LOCK_NAME = "git-isolation-bootstrap.lock"


class BootstrapBlocker(Exception):
    def __init__(
        self,
        code: str,
        conflict: str,
        facts: dict[str, Any],
        evidence: list[str],
        recovery_options: list[str],
        required_decision: str,
        exit_code: int = EXIT_BLOCKED,
    ) -> None:
        super().__init__(conflict)
        self.code = code
        self.conflict = conflict
        self.facts = facts
        self.evidence = evidence
        self.recovery_options = recovery_options
        self.required_decision = required_decision
        self.exit_code = exit_code


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--mode", default="plan")
    parser.add_argument("--issue-id")
    parser.add_argument("--issue-uuid")
    parser.add_argument("--linear-status-category")
    parser.add_argument("--linear-blocker")
    parser.add_argument("--git-branch-name")
    parser.add_argument("--repo")
    parser.add_argument("--base-ref")
    parser.add_argument("--base-commit")
    parser.add_argument("--worktree-path")
    parser.add_argument("--latest-checkpoint-json")
    parser.add_argument("--remote-name", default="origin")
    try:
        namespace, unknown = parser.parse_known_args(argv)
    except (argparse.ArgumentError, SystemExit) as exc:
        raise BootstrapBlocker(
            "INVALID_ARGUMENTS",
            "command-line arguments could not be parsed",
            {"arguments": argv},
            [str(exc)],
            ["supply complete documented helper arguments"],
            "Correct the helper arguments and retry.",
            EXIT_INPUT_INVALID,
        ) from exc
    if unknown:
        raise BootstrapBlocker(
            "INVALID_ARGUMENTS",
            "unrecognized command-line arguments",
            {"unknown_arguments": unknown},
            ["parser rejected unrecognized arguments"],
            ["remove unsupported arguments and retry"],
            "Provide only the documented helper arguments.",
            EXIT_INPUT_INVALID,
        )
    if namespace.mode not in {"plan", "inspect", "apply"}:
        raise BootstrapBlocker(
            "INVALID_MODE",
            "mode must be plan, inspect, or apply",
            {"mode": namespace.mode},
            ["unsupported mode was supplied"],
            ["use plan, inspect, or apply"],
            "Choose a supported helper mode.",
            EXIT_INPUT_INVALID,
        )
    return namespace


def same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def git_executable() -> str:
    return os.environ.get("GIT_ISOLATION_GIT_EXECUTABLE", "git")


def git_command_prefix() -> list[str]:
    encoded = os.environ.get("GIT_ISOLATION_GIT_COMMAND_JSON")
    if not encoded:
        return [git_executable()]
    try:
        command = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise BootstrapBlocker(
            "INVALID_GIT_EXECUTABLE_OVERRIDE",
            "GIT_ISOLATION_GIT_COMMAND_JSON is not valid JSON",
            {},
            [str(exc)],
            ["remove the invalid local test override"],
            "Provide a valid local Git executable override.",
            EXIT_INPUT_INVALID,
        ) from exc
    if not isinstance(command, list) or not command or not all(
        isinstance(part, str) and part for part in command
    ):
        raise BootstrapBlocker(
            "INVALID_GIT_EXECUTABLE_OVERRIDE",
            "GIT_ISOLATION_GIT_COMMAND_JSON must be a non-empty string command list",
            {},
            ["the executable override shape was invalid"],
            ["remove the invalid local test override"],
            "Provide a valid local Git executable override.",
            EXIT_INPUT_INVALID,
        )
    return command


def git_result(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*git_command_prefix(), "-C", str(repo), *args],
        text=True,
        capture_output=True,
    )


def run_git(repo: Path, *args: str, check: bool = True) -> str:
    result = git_result(repo, *args)
    if check and result.returncode:
        raise BootstrapBlocker(
            "GIT_PREFLIGHT_FAILED",
            "Git could not complete a read-only preflight command",
            {"repository": str(repo), "git_arguments": list(args)},
            [result.stderr.strip() or result.stdout.strip() or "Git returned non-zero"],
            ["resolve the repository or reference error and retry"],
            "Provide a reachable Git repository and valid Git reference.",
        )
    return result.stdout.strip()


def git_path(repo: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate.resolve() if candidate.is_absolute() else (repo / candidate).resolve()


def require_text(value: str | None, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BootstrapBlocker(
            "MISSING_AUTHORITATIVE_FIELD",
            f"{name} is required",
            {"missing_field": name},
            [f"no authoritative {name} was supplied"],
            [f"read {name} from Linear governance truth and retry"],
            f"Supply {name}.",
            EXIT_INPUT_INVALID,
        )
    return value.strip()


def validate_identity(
    args: argparse.Namespace, *, allow_unauthorized: bool = False
) -> dict[str, Any]:
    issue_id = require_text(args.issue_id, "issue_id").upper()
    issue_uuid = require_text(args.issue_uuid, "issue_uuid")
    branch = require_text(args.git_branch_name, "git_branch_name")
    status = require_text(args.linear_status_category, "linear_status_category").lower()
    blocker_text = require_text(args.linear_blocker, "linear_blocker").lower()
    blocker_value: bool | str = {
        "true": True,
        "false": False,
    }.get(blocker_text, blocker_text)
    if not ISSUE_PATTERN.fullmatch(issue_id):
        raise BootstrapBlocker(
            "INVALID_ISSUE_ID",
            "issue_id is not a canonical Linear-style identifier",
            {"issue_id": issue_id},
            ["issue_id must match <TEAM>-<NUMBER>"],
            ["supply the authoritative Linear issue identifier"],
            "Correct the issue identifier.",
            EXIT_INPUT_INVALID,
        )
    try:
        UUID(issue_uuid)
    except ValueError as exc:
        raise BootstrapBlocker(
            "INVALID_ISSUE_UUID",
            "issue_uuid is not a UUID",
            {"issue_uuid": issue_uuid},
            [str(exc)],
            ["supply the authoritative Linear issue UUID"],
            "Correct the issue UUID.",
            EXIT_INPUT_INVALID,
        ) from exc
    if not allow_unauthorized and status != "started":
        raise BootstrapBlocker(
            "LINEAR_STATUS_NOT_STARTED",
            "Linear status category does not authorize Writer bootstrap",
            {"linear_status_category": status},
            ["only a started issue can receive a Writer worktree"],
            ["move the issue to a started status before Writer dispatch"],
            "Confirm a started Linear status before dispatch.",
        )
    if not allow_unauthorized and blocker_text != "false":
        raise BootstrapBlocker(
            "LINEAR_BLOCKER_PRESENT",
            "Linear reports an unresolved blocker",
            {"linear_blocker": blocker_text},
            ["the issue has an authoritative blocker"],
            ["resolve or explicitly override the Linear blocker outside this helper"],
            "Resolve the Linear blocker before dispatch.",
        )
    issue_token = issue_id.lower()
    issue_in_branch = re.search(
        rf"(?<![a-z0-9]){re.escape(issue_token)}(?![a-z0-9])", branch.lower()
    )
    if issue_in_branch is None:
        raise BootstrapBlocker(
            "ISSUE_BRANCH_MISMATCH",
            "the supplied Git branch does not contain the authoritative issue id",
            {"issue_id": issue_id, "git_branch_name": branch},
            ["the helper never derives a replacement branch"],
            ["correct Linear gitBranchName", "correct the authoritative issue identity"],
            "Decide which authoritative value is wrong, then retry.",
        )
    return {
        "id": issue_id,
        "uuid": issue_uuid,
        "linear_status_category": status,
        "linear_blocker": blocker_value,
        "git_branch_name": branch,
    }


def validate_repository(repo_text: str | None) -> tuple[Path, Path, Path]:
    supplied = Path(require_text(repo_text, "repo")).expanduser()
    if not supplied.is_absolute() or not supplied.is_dir():
        raise BootstrapBlocker(
            "WRONG_REPOSITORY_OR_GITDIR",
            "repo must be an existing native absolute Git worktree root",
            {"repo": str(supplied)},
            ["repo was not an existing absolute directory"],
            ["supply the intended repository root"],
            "Confirm the target repository root.",
        )
    repo = supplied.resolve()
    top_level = Path(run_git(repo, "rev-parse", "--show-toplevel")).resolve()
    if not same_path(repo, top_level):
        raise BootstrapBlocker(
            "WRONG_REPOSITORY_OR_GITDIR",
            "repo points inside a repository instead of at its worktree root",
            {"supplied_repo": str(repo), "git_top_level": str(top_level)},
            ["Git resolved a different top-level directory"],
            ["supply the exact worktree root"],
            "Confirm the repository root.",
        )
    git_dir = git_path(repo, run_git(repo, "rev-parse", "--git-dir"))
    common_dir = git_path(repo, run_git(repo, "rev-parse", "--git-common-dir"))
    return repo, git_dir, common_dir


def validate_git_branch_name(repo: Path, branch: str) -> None:
    result = git_result(repo, "check-ref-format", "--branch", branch)
    if result.returncode:
        raise BootstrapBlocker(
            "INVALID_GIT_BRANCH_NAME",
            "the authoritative Linear gitBranchName is not a valid Git branch name",
            {"git_branch_name": branch},
            [result.stderr.strip() or result.stdout.strip() or "git check-ref-format rejected the branch"],
            ["correct Linear gitBranchName without deriving a replacement"],
            "Correct the authoritative Linear branch before dispatch.",
            EXIT_INPUT_INVALID,
        )


def canonical_worktree_path(repo: Path, issue_id: str, override: str | None) -> Path:
    if override is not None:
        candidate = Path(require_text(override, "worktree_path")).expanduser()
        if not candidate.is_absolute():
            raise BootstrapBlocker(
                "INVALID_WORKTREE_PATH",
                "an explicit governed worktree path must be native and absolute",
                {"worktree_path": str(candidate)},
                ["relative worktree overrides are ambiguous"],
                ["supply an approved native absolute path"],
                "Provide an explicit absolute governed override.",
                EXIT_INPUT_INVALID,
            )
        return candidate.resolve()
    return (repo.parent / f"{repo.name}-worktrees" / issue_id.lower()).resolve()


def validate_checkpoint(
    text: str | None,
    identity: dict[str, Any],
    base_ref: str,
    base_commit: str,
    worktree_path: Path,
) -> dict[str, Any]:
    raw = require_text(text, "latest_checkpoint_json")
    try:
        checkpoint = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BootstrapBlocker(
            "INVALID_LINEAR_CHECKPOINT",
            "latest checkpoint is not valid JSON",
            {},
            [str(exc)],
            ["read back the latest Linear checkpoint JSON"],
            "Provide a valid latest checkpoint.",
            EXIT_INPUT_INVALID,
        ) from exc
    if not isinstance(checkpoint, dict):
        raise BootstrapBlocker(
            "INVALID_LINEAR_CHECKPOINT",
            "latest checkpoint must be a JSON object",
            {"checkpoint_type": type(checkpoint).__name__},
            ["a JSON object is required"],
            ["supply the latest Linear checkpoint object"],
            "Provide a valid latest checkpoint.",
            EXIT_INPUT_INVALID,
        )
    expected = {
        "schema_version": SCHEMA_VERSION,
        "issue_uuid": identity["uuid"],
        "issue_id": identity["id"],
        "git_branch_name": identity["git_branch_name"],
        "base_ref": base_ref,
        "base_commit": base_commit,
    }
    mismatches = {
        key: {"expected": value, "actual": checkpoint.get(key)}
        for key, value in expected.items()
        if checkpoint.get(key) != value
    }
    checkpoint_path = checkpoint.get("canonical_worktree")
    if not isinstance(checkpoint_path, str) or not same_path(
        Path(checkpoint_path), worktree_path
    ):
        mismatches["canonical_worktree"] = {
            "expected": str(worktree_path),
            "actual": checkpoint_path,
        }
    if checkpoint.get("state") not in {"READY_FOR_ISOLATION", "ISOLATION_READY"}:
        mismatches["state"] = {
            "expected": "READY_FOR_ISOLATION or ISOLATION_READY",
            "actual": checkpoint.get("state"),
        }
    if mismatches:
        raise BootstrapBlocker(
            "LINEAR_CHECKPOINT_MISMATCH",
            "latest Linear checkpoint conflicts with authoritative bootstrap inputs",
            {"mismatches": mismatches},
            ["checkpoint identity, base, branch, or path did not match"],
            ["read back Linear and reconcile the checkpoint", "use an explicit governed path override"],
            "Reconcile Linear governance truth before dispatch.",
        )
    return checkpoint


def remote_base_binding(repo: Path, base_ref: str) -> tuple[str, str] | None:
    for remote_name in run_git(repo, "remote").splitlines():
        direct_prefix = f"{remote_name}/"
        remote_prefix = f"refs/remotes/{remote_name}/"
        if base_ref.startswith(direct_prefix):
            return remote_name, f"refs/heads/{base_ref.removeprefix(direct_prefix)}"
        if base_ref.startswith(remote_prefix):
            return remote_name, f"refs/heads/{base_ref.removeprefix(remote_prefix)}"
    return None


def validate_base(repo: Path, base_ref_text: str | None, base_commit_text: str | None) -> dict[str, Any]:
    base_ref = require_text(base_ref_text, "base_ref")
    base_commit = require_text(base_commit_text, "base_commit").lower()
    if not FULL_SHA_PATTERN.fullmatch(base_commit):
        raise BootstrapBlocker(
            "INVALID_BASE_COMMIT",
            "base_commit must be a full 40-character Git commit id",
            {"base_commit": base_commit},
            ["short or malformed base commits are not accepted"],
            ["supply the accepted full base Commit"],
            "Confirm the accepted full base Commit.",
            EXIT_INPUT_INVALID,
        )
    remote_binding = remote_base_binding(repo, base_ref)
    if remote_binding is not None:
        remote_name, remote_ref = remote_binding
        remote = verified_remote_ref(repo, remote_name, remote_ref)
        if remote is None:
            raise BootstrapBlocker(
                "MISSING_INVALID_OR_STALE_BASE",
                "the current remote does not expose the accepted base ref",
                {"base_ref": base_ref, "accepted_base_commit": base_commit, "remote_name": remote_name},
                ["live remote verification found no matching base ref"],
                ["restore or select the accepted remote base ref"],
                "Resolve the base reference discrepancy.",
            )
        if remote["commit"] != base_commit:
            raise BootstrapBlocker(
                "MISSING_INVALID_OR_STALE_BASE",
                "the current remote base ref does not match the accepted full base Commit",
                {"base_ref": base_ref, "accepted_base_commit": base_commit, "remote": remote},
                ["live remote identity differed from the supplied base Commit"],
                ["refresh the accepted base or supply the correct remote ref"],
                "Resolve the base reference discrepancy.",
            )
        local_object = git_result(repo, "cat-file", "-e", f"{base_commit}^{{commit}}")
        if local_object.returncode:
            raise BootstrapBlocker(
                "MISSING_INVALID_OR_STALE_BASE",
                "the verified remote base Commit is not available in the local repository",
                {"base_ref": base_ref, "accepted_base_commit": base_commit, "remote": remote},
                [local_object.stderr.strip() or "local repository lacks the verified base object"],
                ["make the accepted base object available outside this helper"],
                "Make the verified base Commit available locally before dispatch.",
            )
        return {
            "ref": base_ref,
            "commit": base_commit,
            "ref_kind": "remote",
            "verified_current": "true",
            "remote": remote,
        }
    resolved = git_result(repo, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    if resolved.returncode:
        raise BootstrapBlocker(
            "MISSING_INVALID_OR_STALE_BASE",
            "base_ref does not currently resolve to an accepted Git commit",
            {"base_ref": base_ref, "accepted_base_commit": base_commit},
            [resolved.stderr.strip() or resolved.stdout.strip() or "Git could not resolve base_ref"],
            ["supply an existing accepted base ref", "refresh the accepted base"],
            "Resolve the base reference discrepancy.",
        )
    observed = resolved.stdout.strip().lower()
    if observed != base_commit:
        raise BootstrapBlocker(
            "MISSING_INVALID_OR_STALE_BASE",
            "base_ref does not currently resolve to the accepted full base Commit",
            {"base_ref": base_ref, "accepted_base_commit": base_commit, "observed": observed},
            ["local Git reference readback did not match the supplied base Commit"],
            ["refresh the accepted base or supply the correct repository/ref"],
            "Resolve the base reference discrepancy.",
        )
    run_git(repo, "cat-file", "-e", f"{base_commit}^{{commit}}")
    return {"ref": base_ref, "commit": base_commit, "ref_kind": "local", "verified_current": "true"}


def list_worktrees(repo: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in run_git(repo, "worktree", "list", "--porcelain").splitlines():
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = str(Path(value).resolve())
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value
        elif key in {"bare", "detached", "locked", "prunable"}:
            current[key] = value or True
    if current:
        records.append(current)
    return records


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def validate_worktree_location(
    repo: Path, target: Path, entries: list[dict[str, Any]]
) -> None:
    if path_is_within(target, repo):
        raise BootstrapBlocker(
            "WORKTREE_PATH_INSIDE_REPOSITORY",
            "the governed worktree path must be outside the main checkout",
            {"target": str(target), "repository": str(repo)},
            ["the requested target is equal to or nested inside the main checkout"],
            ["supply a governed path outside the repository root"],
            "Choose a worktree path outside the main checkout.",
        )
    for entry in entries:
        registered = Path(entry["path"]).resolve()
        if same_path(target, registered):
            continue
        if path_is_within(target, registered):
            raise BootstrapBlocker(
                "WORKTREE_PATH_INSIDE_REGISTERED_WORKTREE",
                "the governed worktree path is nested inside another registered worktree",
                {"target": str(target), "registered_worktree": str(registered)},
                ["the requested target is equal to or nested inside a sibling worktree root"],
                ["supply a governed path outside every registered worktree root"],
                "Choose a non-nested governed worktree path.",
            )


def local_branch_exists(repo: Path, branch: str) -> bool:
    return git_result(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0


def ref_commit(repo: Path, ref: str) -> str:
    return run_git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").lower()


def configured_remote_url(repo: Path, remote_name: str) -> str | None:
    result = git_result(repo, "remote", "get-url", remote_name)
    return result.stdout.strip() if result.returncode == 0 else None


def local_remote_path(repo: Path, remote_url: str) -> Path | None:
    raw_path = Path(remote_url)
    if raw_path.is_absolute():
        return raw_path.resolve() if raw_path.exists() else None
    parsed = urlparse(remote_url)
    if parsed.scheme == "file":
        path_text = unquote(parsed.path)
        if os.name == "nt" and re.fullmatch(r"/[A-Za-z]:/.*", path_text):
            path_text = path_text[1:]
        candidate = Path(path_text)
    elif parsed.scheme:
        return None
    else:
        candidate = repo / raw_path
    return candidate.resolve() if candidate.exists() else None


def remote_show_ref(remote_path: Path, ref: str) -> tuple[int, str, str]:
    normal = subprocess.run(
        [*git_command_prefix(), "-C", str(remote_path), "show-ref", "--verify", "--hash", ref],
        text=True,
        capture_output=True,
    )
    if normal.returncode == 0:
        return normal.returncode, normal.stdout.strip(), normal.stderr.strip()
    bare = subprocess.run(
        [*git_command_prefix(), "--git-dir", str(remote_path), "show-ref", "--verify", "--hash", ref],
        text=True,
        capture_output=True,
    )
    return bare.returncode, bare.stdout.strip(), bare.stderr.strip()


def verified_remote_ref(
    repo: Path, remote_name: str, ref: str
) -> dict[str, str] | None:
    remote_url = configured_remote_url(repo, remote_name)
    if remote_url is None:
        return None
    local_path = local_remote_path(repo, remote_url)
    if local_path is not None:
        return_code, output, error = remote_show_ref(local_path, ref)
        if return_code == 1:
            return None
        if return_code != 0 or not FULL_SHA_PATTERN.fullmatch(output):
            raise BootstrapBlocker(
                "REMOTE_IDENTITY_UNVERIFIABLE",
                "the configured local remote could not prove its current branch identity",
                {"remote_name": remote_name, "remote_url": remote_url, "ref": ref},
                [error or output or "local remote show-ref failed"],
                ["repair the configured remote", "use a verified remote or local branch"],
                "Resolve the remote identity before dispatch.",
            )
        return {
            "name": remote_name,
            "url": remote_url,
            "ref": ref,
            "commit": output.lower(),
            "verification": "local-remote-gitdir",
        }
    result = git_result(repo, "ls-remote", "--heads", remote_name, ref)
    if result.returncode:
        raise BootstrapBlocker(
            "REMOTE_IDENTITY_UNVERIFIABLE",
            "the configured remote could not be read live",
            {"remote_name": remote_name, "remote_url": remote_url, "ref": ref},
            [result.stderr.strip() or result.stdout.strip() or "git ls-remote failed"],
            ["restore remote reachability", "use a verified local branch"],
            "Resolve the remote identity before dispatch.",
        )
    lines = [line.split() for line in result.stdout.splitlines() if line.strip()]
    matching = [parts for parts in lines if len(parts) == 2 and parts[1] == ref]
    if not matching:
        return None
    commit = matching[0][0].lower()
    if len(matching) != 1 or not FULL_SHA_PATTERN.fullmatch(commit):
        raise BootstrapBlocker(
            "REMOTE_IDENTITY_UNVERIFIABLE",
            "the live remote returned an ambiguous branch identity",
            {"remote_name": remote_name, "remote_url": remote_url, "ref": ref},
            [result.stdout.strip()],
            ["resolve the remote reference ambiguity"],
            "Provide one current remote branch identity.",
        )
    return {
        "name": remote_name,
        "url": remote_url,
        "ref": ref,
        "commit": commit,
        "verification": "git-ls-remote",
    }


def target_entry(entries: list[dict[str, Any]], target: Path) -> dict[str, Any] | None:
    return next((entry for entry in entries if same_path(Path(entry["path"]), target)), None)


def branch_entry(entries: list[dict[str, Any]], branch: str) -> dict[str, Any] | None:
    ref = f"refs/heads/{branch}"
    return next((entry for entry in entries if entry.get("branch") == ref), None)


def dirty_state(worktree: Path) -> tuple[str, str]:
    status = run_git(worktree, "status", "--porcelain=v1", "--untracked-files=all")
    return ("dirty" if status else "clean", status)


def inspect_registered_target(
    target: Path,
    expected_common_dir: Path,
    expected_branch: str,
) -> dict[str, Any] | None:
    top_level = git_result(target, "rev-parse", "--show-toplevel")
    common_dir = git_result(target, "rev-parse", "--git-common-dir")
    branch = git_result(target, "branch", "--show-current")
    if top_level.returncode or common_dir.returncode or branch.returncode:
        return None
    resolved_top = Path(top_level.stdout.strip()).resolve()
    resolved_common = git_path(target, common_dir.stdout.strip())
    actual_branch = branch.stdout.strip()
    if not same_path(resolved_top, target) or not same_path(resolved_common, expected_common_dir):
        raise BootstrapBlocker(
            "WRONG_REPOSITORY_OR_GITDIR",
            "the registered target path does not resolve to the requested repository common Git directory",
            {
                "target": str(target),
                "target_top_level": str(resolved_top),
                "target_common_dir": str(resolved_common),
                "expected_common_dir": str(expected_common_dir),
            },
            ["target Git metadata resolves to a different repository or gitdir"],
            ["use the correct repository or governed worktree path"],
            "Resolve the repository/gitdir conflict before dispatch.",
        )
    if actual_branch != expected_branch:
        raise BootstrapBlocker(
            "WRONG_BRANCH_OR_PATH",
            "the requested worktree path is checked out on a different branch",
            {"target": str(target), "expected_branch": expected_branch, "actual_branch": actual_branch},
            ["registered target branch readback differs from Linear gitBranchName"],
            ["use the correct governed path", "reconcile Linear gitBranchName"],
            "Resolve the branch/path conflict before dispatch.",
        )
    continuation, raw_status = dirty_state(target)
    return {"continuation_state": continuation, "raw_status": raw_status}


def diagnose_existing_path(target: Path, expected_common_dir: Path) -> None:
    common_dir = git_result(target, "rev-parse", "--git-common-dir")
    if common_dir.returncode == 0:
        actual_common_dir = git_path(target, common_dir.stdout.strip())
        code = "WRONG_REPOSITORY_OR_GITDIR" if not same_path(actual_common_dir, expected_common_dir) else "NON_REPAIRABLE_METADATA"
        raise BootstrapBlocker(
            code,
            "the target path exists but is not a registered reusable worktree",
            {"target": str(target), "actual_common_dir": str(actual_common_dir), "expected_common_dir": str(expected_common_dir)},
            ["the path is already a Git worktree outside the current repository registry"],
            ["choose an explicit governed override", "repair repository metadata outside this helper"],
            "Choose a non-colliding governed worktree path.",
        )
    raise BootstrapBlocker(
        "PATH_COLLISION",
        "the target worktree path already exists and is not registered to this repository",
        {"target": str(target)},
        ["target path exists before bootstrap"],
        ["choose an explicit governed override", "move the unrelated path outside this helper"],
        "Choose a non-colliding governed worktree path.",
    )


def acquire_bootstrap_lock(common_dir: Path, identity: dict[str, Any]) -> tuple[int, Path]:
    lock_path = common_dir / BOOTSTRAP_LOCK_NAME
    payload = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "pid": os.getpid(),
            "issue_id": identity["id"],
            "issue_uuid": identity["uuid"],
            "git_branch_name": identity["git_branch_name"],
        },
        sort_keys=True,
    ).encode("utf-8")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise BootstrapBlocker(
            "CONCURRENT_BOOTSTRAP_LOCK",
            "a repository-scoped bootstrap lock already exists",
            {"lock_path": str(lock_path)},
            ["pre-existing or stale locks are intentionally never deleted by this helper"],
            ["wait for the active bootstrap", "have the lock owner inspect and remove it"],
            "Resolve the existing lock outside this helper before retrying.",
        ) from exc
    except OSError as exc:
        raise BootstrapBlocker(
            "BOOTSTRAP_LOCK_UNAVAILABLE",
            "the repository-scoped bootstrap lock could not be created atomically",
            {"lock_path": str(lock_path)},
            [f"{type(exc).__name__}: {exc}"],
            ["repair local filesystem access"],
            "Restore safe lock creation before dispatch.",
        ) from exc
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    except OSError:
        os.close(descriptor)
        raise
    return descriptor, lock_path


def release_bootstrap_lock(descriptor: int, lock_path: Path) -> None:
    os.close(descriptor)
    try:
        os.unlink(lock_path)
    except OSError as exc:
        raise BootstrapBlocker(
            "BOOTSTRAP_LOCK_RELEASE_FAILED",
            "the helper-created bootstrap lock could not be removed after normal completion",
            {"lock_path": str(lock_path)},
            [f"{type(exc).__name__}: {exc}"],
            ["have the lock owner inspect the lock"],
            "Resolve the helper-created lock before another bootstrap.",
            EXIT_OPERATION_FAILED,
        ) from exc


def run_git_mutation(repo: Path, *args: str) -> str:
    result = git_result(repo, *args)
    if result.returncode:
        raise BootstrapBlocker(
            "SAFE_APPLY_OPERATION_FAILED",
            "Git refused a bounded non-destructive bootstrap operation",
            {"repository": str(repo), "git_arguments": list(args)},
            [result.stderr.strip() or result.stdout.strip() or "Git returned non-zero"],
            ["inspect the recorded Git state", "resolve the conflict without destructive commands"],
            "Decide how to recover the partially created isolation state.",
            EXIT_OPERATION_FAILED,
        )
    return result.stdout.strip()


def ensure_worktree_parent(target: Path) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BootstrapBlocker(
            "WORKTREE_PARENT_UNAVAILABLE",
            "the canonical worktree parent could not be created",
            {"parent": str(target.parent)},
            [f"{type(exc).__name__}: {exc}"],
            ["supply a writable explicit governed override"],
            "Provide a writable governed worktree path.",
        ) from exc
    if not target.parent.is_dir():
        raise BootstrapBlocker(
            "WORKTREE_PARENT_UNAVAILABLE",
            "the canonical worktree parent is not a directory",
            {"parent": str(target.parent)},
            ["path exists but is not a directory"],
            ["supply a different governed path"],
            "Provide a directory parent for the governed worktree path.",
        )


def make_checkpoint(
    identity: dict[str, Any],
    base: dict[str, str],
    worktree_path: Path,
    initial_head: str | None = None,
    current_head: str | None = None,
    continuation_state: str = "not-started",
) -> dict[str, Any]:
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "issue_uuid": identity["uuid"],
        "issue_id": identity["id"],
        "git_branch_name": identity["git_branch_name"],
        "base_ref": base["ref"],
        "base_commit": base["commit"],
        "canonical_worktree": str(worktree_path),
        "state": "ISOLATION_READY",
        "initial_head": initial_head,
        "current_head": current_head,
        "working_tree_continuation": continuation_state,
        "writer_cwd": str(worktree_path),
        "allowed_root": str(worktree_path),
    }
    return checkpoint


def bootstrap_context(
    args: argparse.Namespace, *, allow_unauthorized: bool = False
) -> dict[str, Any]:
    identity = validate_identity(args, allow_unauthorized=allow_unauthorized)
    repo, git_dir, common_dir = validate_repository(args.repo)
    validate_git_branch_name(repo, identity["git_branch_name"])
    worktree_path = canonical_worktree_path(repo, identity["id"], args.worktree_path)
    validate_worktree_location(repo, worktree_path, list_worktrees(repo))
    base = validate_base(repo, args.base_ref, args.base_commit)
    checkpoint = validate_checkpoint(
        args.latest_checkpoint_json,
        identity,
        base["ref"],
        base["commit"],
        worktree_path,
    )
    return {
        "identity": identity,
        "repo": repo,
        "git_dir": git_dir,
        "common_dir": common_dir,
        "worktree_path": worktree_path,
        "base": base,
        "input_checkpoint": checkpoint,
        "remote_name": args.remote_name,
    }


def success_payload(
    context: dict[str, Any],
    status: str,
    worktree_state: str,
    continuation_state: str,
    head: str,
    actions: list[str],
) -> dict[str, Any]:
    identity = context["identity"]
    target = context["worktree_path"]
    checkpoint = make_checkpoint(
        identity,
        context["base"],
        target,
        initial_head=context["input_checkpoint"].get("initial_head") or head,
        current_head=head,
        continuation_state=continuation_state,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "status": status,
        "exit_code": EXIT_OK,
        "mode": "apply",
        "issue": identity,
        "repository": {
            "path": str(context["repo"]),
            "git_dir": str(context["git_dir"]),
            "common_dir": str(context["common_dir"]),
        },
        "base": context["base"],
        "worktree": {
            "path": str(target),
            "canonical_path": str(target),
            "branch": identity["git_branch_name"],
            "state": worktree_state,
            "continuation_state": continuation_state,
            "current_head": head,
        },
        "writer": {
            "cwd": str(target),
            "allowed_root": str(target),
            "write_lease": "granted",
        },
        "checkpoint": checkpoint,
        "actions": actions,
        "blocker": None,
    }


def remote_source_or_block(context: dict[str, Any]) -> dict[str, str] | None:
    repo = context["repo"]
    branch = context["identity"]["git_branch_name"]
    remote_name = context["remote_name"]
    tracking_ref = f"refs/remotes/{remote_name}/{branch}"
    tracking_exists = git_result(repo, "show-ref", "--verify", "--quiet", tracking_ref).returncode == 0
    remote_url = configured_remote_url(repo, remote_name)
    if tracking_exists and remote_url is None:
        raise BootstrapBlocker(
            "REMOTE_REF_NOT_CURRENT",
            "a cached remote-tracking branch has no configured remote to verify it",
            {"tracking_ref": tracking_ref, "remote_name": remote_name},
            ["cached refs are never accepted as current remote truth"],
            ["restore the configured remote", "use an existing local branch"],
            "Resolve the remote identity before dispatch.",
        )
    if remote_url is None:
        return None
    remote = verified_remote_ref(repo, remote_name, f"refs/heads/{branch}")
    if remote is None:
        if tracking_exists:
            raise BootstrapBlocker(
                "STALE_REMOTE_REF",
                "the cached remote-tracking branch no longer exists on the current remote",
                {"tracking_ref": tracking_ref, "remote_name": remote_name, "remote_url": remote_url},
                ["live remote verification found no matching branch"],
                ["refresh remote state outside this helper", "use an existing local branch"],
                "Reconcile the remote branch before dispatch.",
            )
        return None
    if not tracking_exists:
        raise BootstrapBlocker(
            "REMOTE_BRANCH_NOT_AVAILABLE_LOCALLY",
            "a live remote-only branch is not available in this repository without an explicit refresh",
            {"remote": remote, "tracking_ref": tracking_ref},
            ["bounded apply does not fetch or create cached remote refs"],
            ["refresh the remote reference outside this helper", "use a local branch"],
            "Make the verified remote branch available locally before dispatch.",
        )
    tracking_commit = ref_commit(repo, tracking_ref)
    if tracking_commit != remote["commit"]:
        raise BootstrapBlocker(
            "STALE_REMOTE_REF",
            "the cached remote-tracking branch does not match the current remote branch",
            {"tracking_ref": tracking_ref, "cached_commit": tracking_commit, "remote": remote},
            ["live remote identity differs from the local remote-tracking ref"],
            ["refresh remote state outside this helper"],
            "Reconcile the remote branch before dispatch.",
        )
    return remote


def repair_registered_target(
    context: dict[str, Any], entry: dict[str, Any]
) -> dict[str, Any]:
    repo = context["repo"]
    target = context["worktree_path"]
    branch = context["identity"]["git_branch_name"]
    expected_ref = f"refs/heads/{branch}"
    if entry.get("branch") != expected_ref or not target.is_dir():
        raise BootstrapBlocker(
            "NON_REPAIRABLE_METADATA",
            "registered metadata cannot prove the exact same issue branch at a usable target directory",
            {"target": str(target), "registered_branch": entry.get("branch"), "expected_branch": expected_ref},
            ["repair is allowed only for an existing directory registered to the exact issue branch"],
            ["choose a new governed worktree path", "repair the repository outside this helper"],
            "Resolve the non-repairable metadata conflict before dispatch.",
        )
    repair = git_result(repo, "worktree", "repair", str(target))
    if repair.returncode:
        raise BootstrapBlocker(
            "NON_REPAIRABLE_METADATA",
            "Git could not perform a proven non-destructive worktree metadata repair",
            {"target": str(target), "registered_branch": entry.get("branch")},
            [repair.stderr.strip() or repair.stdout.strip() or "git worktree repair failed"],
            ["repair the repository outside this helper", "choose a new governed worktree path"],
            "Resolve the non-repairable metadata conflict before dispatch.",
        )
    repaired_entry = target_entry(list_worktrees(repo), target)
    if repaired_entry is None or repaired_entry.get("branch") != expected_ref:
        raise BootstrapBlocker(
            "NON_REPAIRABLE_METADATA",
            "post-repair metadata does not register the exact requested branch/path pair",
            {"target": str(target), "entries": list_worktrees(repo)},
            ["post-repair worktree readback did not prove the requested branch/path pair"],
            ["repair the repository outside this helper", "choose a new governed worktree path"],
            "Resolve the non-repairable metadata conflict before dispatch.",
        )
    inspected = inspect_registered_target(target, context["common_dir"], branch)
    if inspected is None:
        raise BootstrapBlocker(
            "NON_REPAIRABLE_METADATA",
            "post-repair Git metadata is still unreadable",
            {"target": str(target), "registered_branch": repaired_entry.get("branch")},
            ["post-repair target Git readback failed"],
            ["repair the repository outside this helper", "choose a new governed worktree path"],
            "Resolve the non-repairable metadata conflict before dispatch.",
        )
    head = ref_commit(target, "HEAD")
    actions = [
        "re-read registered worktree state after repository lock acquisition",
        "performed proven non-destructive git worktree repair for the registered exact issue branch",
    ]
    if inspected["continuation_state"] == "dirty":
        actions.append("preserved dirty working files")
    return success_payload(
        context,
        "REUSED",
        "repaired-same-issue-reuse",
        inspected["continuation_state"],
        head,
        actions,
    )


def reusable_target_payload(context: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    target = context["worktree_path"]
    inspected = inspect_registered_target(
        target,
        context["common_dir"],
        context["identity"]["git_branch_name"],
    )
    if inspected is None:
        return repair_registered_target(context, entry)
    head = ref_commit(target, "HEAD")
    actions = [
        "re-read registered worktree state after repository lock acquisition",
        "reused the exact same issue branch and worktree without changing working files",
    ]
    if inspected["continuation_state"] == "dirty":
        actions.append("preserved dirty working files")
    return success_payload(
        context,
        "REUSED",
        "same-issue-reuse",
        inspected["continuation_state"],
        head,
        actions,
    )


def post_create_payload(
    context: dict[str, Any], worktree_state: str, actions: list[str]
) -> dict[str, Any]:
    target = context["worktree_path"]
    entries = list_worktrees(context["repo"])
    entry = target_entry(entries, target)
    if entry is None or entry.get("branch") != f"refs/heads/{context['identity']['git_branch_name']}":
        raise BootstrapBlocker(
            "SAFE_APPLY_POSTCHECK_FAILED",
            "Git did not register the requested branch and worktree exactly as requested",
            {"target": str(target), "entries": entries},
            ["post-apply worktree list did not prove the exact branch/path pair"],
            ["inspect the created state without destructive commands"],
            "Decide how to recover the partially created isolation state.",
            EXIT_OPERATION_FAILED,
        )
    inspected = inspect_registered_target(
        target,
        context["common_dir"],
        context["identity"]["git_branch_name"],
    )
    if inspected is None:
        raise BootstrapBlocker(
            "SAFE_APPLY_POSTCHECK_FAILED",
            "created worktree metadata could not be read back",
            {"target": str(target)},
            ["post-apply Git readback failed"],
            ["inspect the created state without destructive commands"],
            "Decide how to recover the partially created isolation state.",
            EXIT_OPERATION_FAILED,
        )
    head = ref_commit(target, "HEAD")
    return success_payload(
        context,
        "APPLIED",
        worktree_state,
        inspected["continuation_state"],
        head,
        actions,
    )


def apply_locked(context: dict[str, Any]) -> dict[str, Any]:
    repo = context["repo"]
    target = context["worktree_path"]
    branch = context["identity"]["git_branch_name"]
    entries = list_worktrees(repo)
    validate_worktree_location(repo, target, entries)
    existing_target = target_entry(entries, target)
    if existing_target is not None:
        return reusable_target_payload(context, existing_target)
    if target.exists():
        diagnose_existing_path(target, context["common_dir"])
    elsewhere = branch_entry(entries, branch)
    if elsewhere is not None:
        raise BootstrapBlocker(
            "BRANCH_CHECKED_OUT_ELSEWHERE",
            "the exact Linear branch is already checked out in another worktree",
            {"branch": branch, "existing_worktree": elsewhere.get("path")},
            ["Git worktree list reports the branch at a different path"],
            ["reuse that exact worktree", "choose a new authoritative Linear branch"],
            "Decide which worktree owns the issue branch.",
        )
    if local_branch_exists(repo, branch):
        ensure_worktree_parent(target)
        run_git_mutation(repo, "worktree", "add", str(target), branch)
        return post_create_payload(
            context,
            "attached-local-branch",
            [
                "re-read repository state after repository lock acquisition",
                "attached the existing local Linear branch without replacing it",
            ],
        )
    remote = remote_source_or_block(context)
    if remote is not None:
        ensure_worktree_parent(target)
        run_git_mutation(
            repo,
            "worktree",
            "add",
            "--track",
            "-b",
            branch,
            str(target),
            f"{context['remote_name']}/{branch}",
        )
        return post_create_payload(
            context,
            "tracked-remote-branch",
            [
                "re-read repository and live remote state after repository lock acquisition",
                "created a local tracking branch from the verified current remote branch",
            ],
        )
    ensure_worktree_parent(target)
    run_git_mutation(repo, "worktree", "add", "-b", branch, str(target), context["base"]["commit"])
    return post_create_payload(
        context,
        "created-from-base",
        [
            "re-read repository state after repository lock acquisition",
            "created the exact Linear branch and worktree from the accepted full base Commit",
        ],
    )


def apply(args: argparse.Namespace) -> dict[str, Any]:
    bootstrap_context(args)
    identity = validate_identity(args)
    repo, _, common_dir = validate_repository(args.repo)
    descriptor, lock_path = acquire_bootstrap_lock(common_dir, identity)
    try:
        context = bootstrap_context(args)
        payload = apply_locked(context)
    except BootstrapBlocker:
        release_bootstrap_lock(descriptor, lock_path)
        raise
    except Exception:
        os.close(descriptor)
        raise
    release_bootstrap_lock(descriptor, lock_path)
    return payload


def read_only_state_matrix(
    context: dict[str, Any],
) -> tuple[str, str, str | None, list[str]]:
    repo = context["repo"]
    target = context["worktree_path"]
    branch = context["identity"]["git_branch_name"]
    entries = list_worktrees(repo)
    validate_worktree_location(repo, target, entries)
    existing_target = target_entry(entries, target)
    if existing_target is not None:
        inspected = inspect_registered_target(target, context["common_dir"], branch)
        if inspected is None:
            raise BootstrapBlocker(
                "WORKTREE_METADATA_UNREADABLE",
                "registered target metadata could not be read without mutation",
                {"target": str(target), "registered_branch": existing_target.get("branch")},
                ["read-only Git metadata readback failed for the registered target"],
                ["inspect or repair repository metadata outside this helper", "choose a new governed path"],
                "Resolve the worktree metadata conflict before dispatch.",
            )
        head = ref_commit(target, "HEAD")
        actions = [
            "read-only repository, base, Linear identity, checkpoint, path, branch, remote, and worktree state preflight completed",
            "read-only state matrix classified exact same-issue reuse",
            "no branch, worktree, lock, or working file was changed",
        ]
        if inspected["continuation_state"] == "dirty":
            actions.append("preserved dirty working files")
        return "same-issue-reuse", inspected["continuation_state"], head, actions
    if target.exists():
        diagnose_existing_path(target, context["common_dir"])
    elsewhere = branch_entry(entries, branch)
    if elsewhere is not None:
        raise BootstrapBlocker(
            "BRANCH_CHECKED_OUT_ELSEWHERE",
            "the exact Linear branch is already checked out in another worktree",
            {"branch": branch, "existing_worktree": elsewhere.get("path")},
            ["Git worktree list reports the branch at a different path"],
            ["reuse that exact worktree", "choose a new authoritative Linear branch"],
            "Decide which worktree owns the issue branch.",
        )
    if local_branch_exists(repo, branch):
        head = ref_commit(repo, f"refs/heads/{branch}")
        return (
            "attached-local-branch",
            "not-started",
            head,
            [
                "read-only repository, base, Linear identity, checkpoint, path, branch, remote, and worktree state preflight completed",
                "read-only state matrix classified an existing local Linear branch for attach",
                "no branch, worktree, lock, or working file was changed",
            ],
        )
    remote = remote_source_or_block(context)
    if remote is not None:
        head = ref_commit(repo, f"refs/remotes/{context['remote_name']}/{branch}")
        return (
            "tracked-remote-branch",
            "not-started",
            head,
            [
                "read-only repository, base, Linear identity, checkpoint, path, branch, remote, and worktree state preflight completed",
                "read-only state matrix classified a verified remote branch for tracking",
                "no branch, worktree, lock, or working file was changed",
            ],
        )
    return (
        "created-from-base",
        "not-started",
        None,
        [
            "read-only repository, base, Linear identity, checkpoint, path, branch, remote, and worktree state preflight completed",
            "read-only state matrix classified safe creation from the accepted base",
            "no branch, worktree, lock, or working file was changed",
        ],
    )


def authorization_facts(
    context: dict[str, Any],
    worktree_state: str,
    continuation_state: str,
    current_head: str | None,
) -> dict[str, Any]:
    identity = context["identity"]
    return {
        "issue_id": identity["id"],
        "issue_uuid": identity["uuid"],
        "git_branch_name": identity["git_branch_name"],
        "linear_status_category": identity["linear_status_category"],
        "linear_blocker": identity["linear_blocker"],
        "canonical_worktree": str(context["worktree_path"]),
        "base_ref": context["base"]["ref"],
        "base_commit": context["base"]["commit"],
        "worktree_state": worktree_state,
        "continuation_state": continuation_state,
        "current_head": current_head,
    }


def enforce_writer_authorization(
    context: dict[str, Any],
    worktree_state: str,
    continuation_state: str,
    current_head: str | None,
) -> None:
    identity = context["identity"]
    facts = authorization_facts(
        context,
        worktree_state,
        continuation_state,
        current_head,
    )
    if identity["linear_status_category"] != "started":
        raise BootstrapBlocker(
            "LINEAR_STATUS_NOT_STARTED",
            "Linear status category does not authorize Writer dispatch",
            facts,
            [
                "read-only Linear identity, repository, base, checkpoint, canonical path, branch, and worktree state inspection completed",
                "Linear status category is not started",
            ],
            [
                "move the issue to a started Linear status and obtain a fresh checkpoint",
                "rerun plan or inspect after the authoritative status readback changes",
            ],
            "Confirm a started Linear status before Writer dispatch.",
        )
    if identity["linear_blocker"] is not False:
        raise BootstrapBlocker(
            "LINEAR_BLOCKER_PRESENT",
            "Linear reports an unresolved blocker",
            facts,
            [
                "read-only Linear identity, repository, base, checkpoint, canonical path, branch, and worktree state inspection completed",
                "Linear reports an unresolved blocker",
            ],
            [
                "resolve the authoritative Linear blocker and obtain a fresh checkpoint",
                "rerun plan or inspect after linear_blocker is read back as false",
            ],
            "Resolve the Linear blocker before Writer dispatch.",
        )


def plan(args: argparse.Namespace) -> dict[str, Any]:
    context = bootstrap_context(args, allow_unauthorized=True)
    identity = context["identity"]
    repo = context["repo"]
    git_dir = context["git_dir"]
    common_dir = context["common_dir"]
    worktree_path = context["worktree_path"]
    base = context["base"]
    state, continuation_state, current_head, actions = read_only_state_matrix(context)
    enforce_writer_authorization(context, state, continuation_state, current_head)
    checkpoint = make_checkpoint(
        identity,
        base,
        worktree_path,
        initial_head=current_head,
        current_head=current_head,
        continuation_state=continuation_state,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "status": "PLAN_READY",
        "exit_code": EXIT_OK,
        "mode": args.mode,
        "issue": identity,
        "repository": {
            "path": str(repo),
            "git_dir": str(git_dir),
            "common_dir": str(common_dir),
        },
        "base": base,
        "worktree": {
            "path": str(worktree_path),
            "canonical_path": str(worktree_path),
            "branch": identity["git_branch_name"],
            "state": state,
            "continuation_state": continuation_state,
            "current_head": current_head,
        },
        "writer": {
            "cwd": str(worktree_path),
            "allowed_root": str(worktree_path),
            "write_lease": "planned",
        },
        "checkpoint": checkpoint,
        "actions": actions,
        "blocker": None,
    }


def blocker_payload(error: BootstrapBlocker, mode: str | None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "status": "LOCAL_EXECUTION_BLOCKER",
        "exit_code": error.exit_code,
        "mode": mode or "unknown",
        "blocker": {
            "code": error.code,
            "confirmed_facts": error.facts,
            "conflict": error.conflict,
            "impact": "Writer dispatch and local Git isolation are blocked.",
            "actions_not_executed": [
                "no branch was created, replaced, or checked out",
                "no worktree was created, removed, moved, or overwritten",
                "no destructive Git command was executed",
            ],
            "recovery_options": error.recovery_options,
            "required_decision": error.required_decision,
            "evidence": error.evidence,
        },
    }


def main(argv: list[str]) -> int:
    args: argparse.Namespace | None = None
    try:
        args = parse_args(argv)
        payload = plan(args) if args.mode in {"plan", "inspect"} else apply(args)
        exit_code = EXIT_OK
    except BootstrapBlocker as error:
        payload = blocker_payload(error, args.mode if args else None)
        exit_code = error.exit_code
    except Exception as error:  # Fail closed while retaining the JSON stdout contract.
        payload = blocker_payload(
            BootstrapBlocker(
                "UNEXPECTED_LOCAL_ERROR",
                "an unexpected local error prevented safe bootstrap",
                {},
                [f"{type(error).__name__}: {error}"],
                ["inspect the local environment and retry in plan mode"],
                "Resolve the local error before dispatch.",
                EXIT_OPERATION_FAILED,
            ),
            args.mode if args else None,
        )
        exit_code = EXIT_OPERATION_FAILED
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
