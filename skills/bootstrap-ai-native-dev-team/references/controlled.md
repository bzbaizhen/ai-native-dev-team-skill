# Controlled layer

Use Controlled for material behavior or regression risk, C2/C3, R2/R3, interface,
dependency, data-shape or security-boundary changes, concurrency, production,
deployment, release, or public action.

## Minimum topology and artifacts

- Keep the main agent as fact, routing, conflict, integration, stop, and acceptance owner.
- Use one path-bounded Writer and one independent Validator per repository by default.
- Add a specialist only for a concrete architecture, security, privacy, data, operations, or Owner gate.
- Freeze the smallest useful task and interface boundary. One file has one Writer.
- Give each Worker a task-local packet with the objective, confirmed facts, task baseline, exact allowed paths, checks, stop conditions, and rollback.
- Use only the concise contract, write lease, validation, approval, and recovery evidence the task needs.
- Use a branch or Worktree when the repository workflow or parallel ownership requires isolation.

## Capability and risk

| Complexity | Capability | Reasoning |
|---|---|---|
| C1 | Standard | Medium |
| C2 | Advanced | High |
| C3 | Frontier, or main-agent takeover | Max |

Risk strengthens gates, not implementation capability. C1/R3 remains Standard/Medium
implementation with R3 authority, security, rollback, and recovery controls. C3/R1 may
use Frontier/Max but does not automatically gain production authority.

For R3, obtain explicit Owner approval, least-privilege and sanitized-data review, exact
candidate validation, executable rollback or recovery evidence, and stable-state
readback. A command start or static check is not acceptance.

## Validation and acceptance

1. The Writer checks scope and runs relevant checks on the candidate.
2. The independent Validator checks the exact candidate from a clean or controlled state and does not silently fix product code.
3. The main agent verifies path scope, immutable identity, permissions, rollback, and integration before acceptance.
4. Reuse evidence only while Commit/tree, environment fingerprint, lockfiles, test entry points, permissions, generated inputs, and relevant external dependencies remain unchanged.
5. Rerun affected checks when any relevant input changes, merge resolution occurs, policy requires it, or prior evidence is incomplete.

Treat release, deployment, and publication as Controlled/R3. They require explicit
Owner authority and do not become accepted merely because local development is complete.

Stop when authority, task baseline, interface, scope, evidence, or recovery conflicts;
when secrets or unexpected real data appear; or when a gate cannot be tied to the exact
candidate. Reopen a frozen Writer lease explicitly for fixes and preserve failed
candidates in Git history.
