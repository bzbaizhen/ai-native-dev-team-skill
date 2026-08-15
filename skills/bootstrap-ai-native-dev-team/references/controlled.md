# Controlled layer

Use Controlled when a task has material behavior or regression risk, is C2/C3 or R2/R3,
changes an interface, dependency, data shape, or security boundary, needs concurrency,
or performs a production, deployment, release, or public action. Controlled absorbs the
relevant authority, security, privacy, and recovery controls previously associated with
a stricter profile. It does not implicitly start a Release Audit.

## Minimum topology and artifacts

- Keep the main agent as fact, routing, conflict, integration, stop, and acceptance
  owner.
- Use one path-bounded Writer and one independent Validator per repository by default.
  Add a specialist only for a concrete architecture, security, privacy, data,
  operations, or owner gate.
- Freeze the smallest useful task and interface boundary. A shared file has one Writer.
- Give every Worker a task packet, never the complete team Skill. The packet identifies
  the objective, confirmed facts, baseline, exact allowed read/write paths, checks, stop
  conditions, and rollback. A Worker reports `worker_skill_loaded=false`,
  `worker_repo_wide_search_used=false`, and `worker_out_of_scope_reads=false`. Any true
  or unreviewable value fails context-isolation evidence and forbids a context or cost
  saving claim.
- Use only the governance artifacts the material task needs. A concise contract, write
  lease, and acceptance record are the default maximum for ordinary Controlled work;
  do not require a daily ledger or release-audit bundle unless explicitly selected.
- Create a Worktree or branch for a material Writer when the repository workflow
  requires isolation. Do not create one for non-material Core work merely because a
  Worker exists.

## Capability and risk overlay

Complexity selects implementation capability and reasoning:

| Complexity | Capability | Reasoning |
|---|---|---|
| C1 | Standard | Medium |
| C2 | Advanced | High |
| C3 | Frontier, or main-agent takeover | Max |

Risk strengthens gates, not implementation capability. In particular, C1/R3 remains
Standard/Medium implementation with explicit R3 approval, security, permission,
rollback, and recovery evidence. C3/R1 may use Frontier/Max or a main-agent takeover,
but remains Controlled and does not load Release Audit.

For R3, obtain the required owner approval, least-privilege and sanitized-data review,
exact candidate validation, executable rollback or recovery evidence, and stable-state
readback. Production/public action is not accepted merely because a command started or
a static check passed.

## Validation and evidence reuse

1. The Writer checks scope and runs relevant affected checks on its candidate.
2. The independent Validator checks the exact candidate Commit from a clean or
   controlled state and reports findings without modifying product code.
3. The main agent verifies path scope, immutable identity, permissions, rollback, and
   integration before acceptance.
4. Reuse prior validation evidence only when Commit/tree, environment fingerprint,
   lockfiles, test entry points, permissions, generated inputs, and relevant external
   dependencies are all unchanged.
5. Rerun the affected or full check when the integrated tree differs, history-sensitive
   behavior is involved, the fingerprint or any listed input changes, merge resolution
   occurs, repository policy requires it, or prior evidence is incomplete or failed.

Do not repeat a full suite solely because the work moved between agents when all reuse
conditions hold. Do repeat it when any rerun trigger appears.

## Ordinary release and stop conditions

Treat ordinary release, deployment, or publication as Controlled/R3 with
`release_audit=false`. Activate [Release Audit](release-audit.md) only for an explicit
stable-version qualification, formal efficiency comparison, historical-baseline
qualification, or external evidence-freeze request.

Stop when authority, baseline, interface, scope, evidence, or recovery conflicts; when
secrets or unexpected real data appear; or when a required gate cannot be tied to the
exact candidate. Reopen a frozen Writer lease explicitly for fixes and preserve failed
candidates in history.
