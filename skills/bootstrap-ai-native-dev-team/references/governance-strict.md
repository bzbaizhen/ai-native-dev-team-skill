# Strict governance profile

Use for C3, R3, production, security/privacy/compliance, public release, credentials, real data, paid resources, irreversible migration, deletion, or material recovery operations.

Strict means stronger evidence and authority, not more agents by default.

## Authority and isolation

- Business Owner explicitly approves production, real data, credentials, paid resources, public release, irreversible actions, and deletion of material recovery copies.
- Main agent retains task graph, fact boundaries, integration, stop decisions, and final acceptance.
- Activate security, privacy/compliance, data, architecture, DevOps, or release specialists only for a concrete gate.
- Separate implementation from independent validation and from owner approval.
- Use isolated branches/Worktrees and one path-bounded lease per Writer.
- Use least privilege, native environments, approved credential mechanisms, and sanitized test data.

## Required evidence

Record:

- exact baseline and candidate Commits;
- scope, interfaces, dependencies, data changes, permissions, and approvers;
- threat, privacy, compliance, or provenance review as applicable;
- automated, integration, migration, security, and target-environment results;
- rollback command or procedure, recovery point, owner, and stop threshold;
- stable-branch acceptance evidence and known residual risk.

A successful Push, deployment command start, static check, or backup creation is not proof of acceptance, production health, or recovery.

## Change and release gates

1. Freeze the task and interface contract.
2. Prepare backup or recovery point before destructive or migratory work.
3. Rehearse rollback or recovery in a safe environment when feasible.
4. Obtain the required specialist and owner approvals.
5. Execute only the approved scope.
6. Validate the exact candidate in the required environment.
7. Integrate and verify the stable version.
8. Observe the defined health window.
9. Close only after recovery evidence and status sources agree.

Emergency work may narrow scope and tests but may not remove exact-version evidence, an independent gate, approval, or rollback.

## Stop immediately when

- authority, credential provenance, data classification, environment, or baseline is uncertain;
- a secret or unexpected real dataset appears;
- the actual change exceeds the contract or modifies an unfrozen interface;
- evidence cannot be tied to the candidate;
- recovery cannot be demonstrated;
- a security boundary blocks access;
- an irreversible action lacks explicit owner approval.

Report `Confirmed facts / Current impact / Not executed / Risk / Options / Required approval / Rollback`. Do not work around the blocker.

## Recovery standard

Distinguish:

- working directory;
- local Git history;
- remote repository copy;
- independent archive or database snapshot;
- tested recovery path.

Delete branches, Worktrees, snapshots, or recovery copies only after merge, retention, and recoverability are confirmed and the required authority approves.
