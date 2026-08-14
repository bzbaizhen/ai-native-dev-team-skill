# Controlled governance profile

Use for C2, R2, task-cell delivery, contract-sensitive integration, or more than one approved Writer.

## Required controls

- Maintain an evidence-backed task graph and identify the stable branch and baseline Commit.
- Define Writer, independent Validator, file Owner, allowed paths, dependency order, and acceptance authority.
- Use one task, branch, Worktree, pull request, and write lease per material Writer when the repository supports them.
- Freeze the minimum interface before cross-component work. Keep its schema, fixtures, compatibility rule, and source Commit in one source of truth.
- Give each worker a task contract, not the full team Skill.
- Bind self-check, automated checks, independent review, and acceptance to exact Commits.
- Preserve executable rollback. Changes to interfaces, dependencies, data shapes, CI, or security policy require main-agent approval.
- Accept only after the validated candidate is integrated into the stable branch and status agrees with Git and evidence.

## Parallelism and integration

Start with one Writer and one Validator per repository. Add a Writer only when paths are independent or a shared interface is frozen.

Before starting any Writer:

1. Check existing compatible agents and leases.
2. Check for `DEV_COMPLETE`, `QA_PENDING`, or `MERGE_READY` backlog.
3. Prefer clearing integration backlog over opening new work.
4. Verify that validation capacity is available.
5. Record an override reason when concurrency is still justified.

A shared file has one Owner. Other workers request changes from that Owner.

## Validation sequence

1. Implementer reviews scope and diff.
2. Relevant automated checks run on the candidate.
3. Independent Validator checks the same Commit from a clean or controlled state.
4. Failures return to an explicitly reopened Writer lease.
5. Validator rechecks the affected scope.
6. Main agent decides acceptance and verifies the stable-branch Commit.

Separate static checks, simulation, target-platform execution, and real-environment evidence.

## Sources of truth

Create only what the project needs:

- product/scope and task status;
- contracts and fixtures when interfaces exist;
- ADR for durable exceptions or architectural decisions;
- evidence manifest for material acceptance;
- minimal metrics ledger owned by the main agent.

## Escalate

Move to Strict for C3, R3, production, security/privacy/compliance, public release, irreversible migration, deletion, credentials, real data, or an unproven recovery path.
