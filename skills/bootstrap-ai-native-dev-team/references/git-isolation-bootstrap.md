# Linear-driven Git branch and worktree isolation

Use this reference only before dispatching a Writer for a Linear-governed implementation
issue, or when an Owner explicitly requests issue isolation. It does not add a routing
layer: non-Linear work continues through Core or Controlled exactly as selected. A
plan-only review is a rich, non-mutating evidence preflight; it never grants permission
to dispatch a Writer.

## Required gate

Complete the **Linear identity/status/blocker/gitBranchName/latest-checkpoint gate** from
a fresh Linear readback. Supply the authoritative issue UUID and display ID, a `started`
status category, `linear_blocker=false`, and the exact `gitBranchName`; do not derive or
rename that branch. The latest checkpoint must match all identity values, branch, base
ref/full Commit, and canonical worktree. Any terminal/non-started status, blocker, absent
checkpoint, or mismatch stops local execution. For `plan` and `inspect`, a non-started or
blocked issue reaches that stop only after safe read-only repository, base, checkpoint,
canonical path, branch, and worktree-state inspection, so the blocker retains the
distinct issue/branch/path evidence.

Then prove the local repository root and the accepted base ref/full Commit. A local base
must resolve exactly. A remote base or remote-only issue branch must be checked against the
current configured remote identity; cached tracking refs are never current truth. The base
Commit must also exist locally. Do not fetch, reset, clean, stash, checkout, switch,
rebase, move, remove, prune, replace, or delete to make an ambiguous state fit.

Unless Linear carries an explicit governed override, the canonical native absolute path is
`<repo-parent>/<repo-name>-worktrees/<issue-id-lowercase>`. The Writer's cwd and only
writable root are that accepted worktree; bind one Writer/ownership lease to it before
dispatch and do not dispatch into a repository root or sibling worktree. Both calculated
targets and explicit governed overrides must be outside the main checkout and outside
every other registered worktree root; an absent nested target is a blocker before apply.

## Helper contract

Run the stdlib helper from the selected repository environment before Writer dispatch,
resolving it through the Skill directory from the repository root:

```text
python -B skills/bootstrap-ai-native-dev-team/scripts/git_isolation_bootstrap.py --mode plan|inspect|apply \
  --issue-id <LINEAR-ID> --issue-uuid <UUID> \
  --linear-status-category started --linear-blocker false \
  --git-branch-name <EXACT-LINEAR-gitBranchName> \
  --repo <NATIVE-ABSOLUTE-REPOSITORY-ROOT> \
  --base-ref <ACCEPTED-REF> --base-commit <FULL-40-CHAR-COMMIT> \
  --latest-checkpoint-json <FRESH-LINEAR-CHECKPOINT> \
  [--worktree-path <EXPLICIT-GOVERNED-ABSOLUTE-OVERRIDE>]
```

`plan` and `inspect` are read-only and return a JSON-only stdout contract. A started,
unblocked issue may return `PLAN_READY`; a non-started or blocked issue returns
`LOCAL_EXECUTION_BLOCKER` only after the safe read-only preflight, with confirmed issue
id/UUID, exact branch, status/blocker, canonical path, accepted base ref/full Commit,
and classified worktree state/current HEAD when available. `apply` repeats preflight
before acquiring its lock, then may only create/attach/reuse the exact issue
branch/worktree, or perform a proven non-destructive `git worktree repair`. It emits
JSON-only stdout and stable exits: `0` for ready/applied/reused, `2` for invalid
supplied authority data, `3` for a local or governance blocker, and `4` for a bounded
operation or unexpected local failure. A plan-only review is evidence gathering, not
Writer dispatch or authorization to mutate.

The helper atomically creates a **repository-scoped short bootstrap lock** named
`git-isolation-bootstrap.lock` in the Git common directory. It re-reads state after lock
acquisition, and removes only the lock it created on normal completion. A pre-existing or
stale lock is always a blocker and is never removed by the helper.

## State matrix

| Confirmed state after the lock | Safe result | Not executed |
| --- | --- | --- |
| Branch and target absent; accepted base exact | Create branch/worktree from base | No fetch or replacement |
| Local exact issue branch, not checked out | Attach it at canonical path | No branch recreation |
| Live remote-only branch and matching local tracking ref | Create tracking branch/worktree | No cached-ref assumption or fetch |
| Exact issue branch at exact registered target | Reuse; retain clean or dirty files | No working-file change |
| Target exists but is unrelated, wrong branch, wrong repo/gitdir | `LOCAL_EXECUTION_BLOCKER` | No overwrite, move, or delete |
| Branch is checked out elsewhere | `LOCAL_EXECUTION_BLOCKER` | No second checkout/worktree |
| Missing, invalid, stale, or remote-unverified base | `LOCAL_EXECUTION_BLOCKER` | No branch/worktree creation |
| Exact registered target has unreadable metadata but still proves exact path/branch | Re-read after `git worktree repair` | No destructive Git command |
| Any other metadata conflict or failed repair | `LOCAL_EXECUTION_BLOCKER` | No repair retry or destructive recovery |

Path identity, common Git directory, branch, and post-apply HEAD must be read back before
granting the Writer lease. Dirty same-issue continuations remain dirty and are reported as
preserved; a helper must never reset or overwrite them. `plan` and `inspect` perform this
state matrix read-only and classify safe creation, local attach, verified remote tracking,
exact reuse, and dirty continuation; collisions, wrong repository/branch, branch elsewhere,
stale or unverified remote state, invalid base, and metadata conflicts are blockers without
mutation.

## Linear checkpoint schema

Use this minimum JSON object for the latest Linear checkpoint. `READY_FOR_ISOLATION` is
valid before first bootstrap; the helper returns `ISOLATION_READY` after a safe plan or
apply readback.

```json
{
  "schema_version": 1,
  "issue_uuid": "<UUID>",
  "issue_id": "<LINEAR-ID>",
  "git_branch_name": "<EXACT-LINEAR-gitBranchName>",
  "base_ref": "<ACCEPTED-REF>",
  "base_commit": "<FULL-40-CHAR-COMMIT>",
  "canonical_worktree": "<NATIVE-ABSOLUTE-PATH>",
  "state": "READY_FOR_ISOLATION"
}
```

Record the helper readback back in Linear before Writer dispatch: canonical path, base
ref/full Commit, initial/current HEAD, clean/dirty continuation state, Writer cwd/allowed
root, ownership lease, and exact tested HEAD. Linear remains governance truth; Git remains
repository/ref/worktree truth.

## Blocker report contract

Every ambiguous or unsafe local outcome is `LOCAL_EXECUTION_BLOCKER`, with these fields:

```json
{
  "status": "LOCAL_EXECUTION_BLOCKER",
  "blocker": {
    "confirmed_facts": {},
    "conflict": "<what disagrees>",
    "impact": "<why Writer dispatch is blocked>",
    "actions_not_executed": ["<safe omissions>"],
    "recovery_options": ["<non-destructive options>"],
    "required_decision": "<Owner or Linear decision>",
    "evidence": ["<Git/Linear readback>"]
  }
}
```

Report the exact command result and path/ref evidence; do not silently choose a replacement
branch, path, base, lock disposition, or repair. A plan, helper exit, or branch creation is
not Writer dispatch, validation, integration, or release. When plan-only review encounters
a non-started or blocked issue, its rich `LOCAL_EXECUTION_BLOCKER` is the review result;
it is not permission to dispatch.
