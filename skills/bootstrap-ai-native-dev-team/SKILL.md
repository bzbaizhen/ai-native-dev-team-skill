---
name: bootstrap-ai-native-dev-team
description: Bootstrap, resize, or audit an AI-native software development team with proportional governance. Use when starting a software project, assembling multiple coding agents, planning parallel implementation, defining developer and QA roles, introducing worktrees or write leases, preparing a release, or auditing an existing agent team. Produces an approval-ready team charter before creating agents or changing repositories. Do not trigger the full workflow for a small, low-risk task that one agent can safely complete unless the user explicitly invokes this skill.
---

# Bootstrap an AI-Native Development Team

Treat the main agent as the control plane and specialist agents as task-scoped, permission-bounded workers or independent validators. Design the smallest sufficient team first. Create agents and engineering resources only after the applicable approval gate.

Reply in the user's language. Preserve the labels `Confirmed facts`, `Inferences`, and `To verify`, translating them when helpful.

## Resolve authority

Apply instructions in this order:

1. System, developer, and the user's current explicit instructions.
2. Active repository instructions and accepted architecture decision records.
3. This workflow.
4. The detailed baseline in [team-governance-template.zh-CN.md](references/team-governance-template.zh-CN.md).

Do not use this skill to bypass permissions or repository policy. When project reality conflicts with the baseline, propose a documented exception or ADR with its owner, impact, and reversal condition.

## Select a mode

State the selected mode at the start:

- `proposal`: Inspect and produce an approval-ready plan. Do not create agents or edit project files. Use by default.
- `initialize`: Produce the plan first, then write only the approved project artifacts and create only the approved team resources.
- `audit`: Read-only assessment of an existing team, repository, and gates.
- `adjust`: Resize or correct an existing team while preserving confirmed project facts and accepted decisions.

An explicit request to initialize authorizes ordinary, reversible project-file writes within scope. It does not authorize production access, real user data, credentials, external publication, irreversible migration, or deletion of material recovery copies.

## Workflow

### 1. Establish the baseline

Read the detailed governance reference, then inspect available primary evidence before asking questions:

- repository root and active agent instructions;
- product goal, users, scope, success criteria, and current stage;
- Git state, repository boundaries, stable branch, remotes, and baseline commit;
- build, test, deployment, and native platform requirements;
- product, task, contract, decision, risk, status, and evidence sources of truth;
- existing agents, branches, worktrees, pull requests, and write conflicts.

Separate the result into:

- `Confirmed facts`: supported directly by inspected evidence.
- `Inferences`: reasoned conclusions that remain labeled as such.
- `To verify`: genuinely missing or conflicting inputs.

Do not ask the user to reconfirm facts supported by direct evidence. Do not fill missing fields by guessing.

### 2. Decide whether a team is justified

Choose the lightest sufficient topology:

| Situation | Default topology |
|---|---|
| Read-only or tiny, clear, low-risk task | Main agent only |
| Isolated implementation with easy verification | One implementer plus main-agent review |
| Behavioral change or meaningful regression risk | Implementer plus independent validator |
| Independent slices with frozen boundaries | Isolated implementers plus independent validator |
| Security, privacy, production, migration, or release risk | Specialists, independent gate, and owner approval |

Do not create permanent personas merely to appear agent-native. Team size, agent count, commits, and token use are not delivery metrics.

### 3. Score complexity and risk separately

Record both dimensions and their evidence:

- Complexity `C0-C3` controls decomposition, context preparation, model capability, and reasoning effort.
- Risk `R0-R3` controls permissions, independent review, approval, rollback evidence, and stop conditions.

Do not collapse them into one score. A one-line production authentication change can be `C1/R3`; a difficult pure refactor can be `C3/R1`.

Follow active global and project model-routing instructions. Never claim a requested model was used when the runtime did not provide it.

### 4. Compose the minimum team

Define only roles with real work:

- **Business owner**: retains final approval for business scope, real data, production authority, public release, and irreversible operations.
- **Main agent / producer**: owns intake, fact boundaries, task graph, contracts, leases, conflict decisions, and final acceptance.
- **Implementer**: changes only the paths and behavior in an approved task contract.
- **Independent validator**: tests the exact version under review and does not silently fix the product code it is accepting.
- **Optional specialist**: architecture, AI, data provenance, DevOps, security, privacy/compliance, or user research, activated only by domain need or risk.

The main agent must not delegate unresolved product direction, fact boundaries, or the final merge decision. Developer self-review and independent validation are different evidence.

### 5. Design safe parallelism

Recommend parallel writers only when all conditions hold:

- tasks are independent or a minimum contract is frozen;
- paths do not overlap, or every shared file has exactly one owner;
- other agents request shared-file changes from that owner instead of editing it;
- dependency graph, integration order, baseline commit, and rollback are explicit;
- validation capacity can absorb the development concurrency.

For material parallel changes in one repository, default to one task, branch, worktree, pull request, and write lease per writer. Inspect and reuse compatible existing agents before creating new ones.

### 6. Produce the approval gate

Fill [team-bootstrap-proposal.md](assets/team-bootstrap-proposal.md) or return an equivalent structure. Include:

- fact boundary and blockers;
- stage and `C/R` scores with evidence;
- selected topology and intentionally omitted roles;
- task dependencies, contracts, and file ownership;
- permissions, approvals, stop conditions, and rollback;
- Git/worktree/PR, QA, and evidence plan;
- exact files and resources proposed for creation;
- recommendation: `approve`, `approve with changes`, or `do not form a team yet`.

Stop here in `proposal` mode. Never describe proposed agents, files, checks, or releases as already created or completed.

### 7. Initialize approved artifacts

In `initialize` mode, execute only the approved scope:

1. Add a project-level charter under `product/`, `governance/`, or the project's equivalent using [project-team-charter.md](assets/project-team-charter.md).
2. Establish only the stage-appropriate product, task, contract, decision, risk, status, and evidence sources of truth.
3. Use [task-contract.md](assets/task-contract.md) for each material task.
4. Issue one path-bounded write lease per writer.
5. Create or reuse agents, branches, and worktrees only after task boundaries and leases are ready.
6. Record what was created, what was intentionally deferred, and how to recover.

Do not impose production-scale automation on an early MVP. Start with the minimum controls justified by current stage and risk.

### 8. Execute and validate

Use this evidence sequence for each material task:

1. Implementer self-check.
2. Relevant automated checks.
3. Independent task-scoped review of the exact diff and commit.
4. Fix and scoped re-review when needed.
5. Main-agent acceptance.
6. Whole-branch review for substantial integrated changes.

Bind validation to an exact commit or equivalent immutable version. Distinguish static checks, simulation, target-platform execution, and real-environment evidence. Record commands, results, environment, limitations, validator, and rollback using [evidence-manifest.yaml](assets/evidence-manifest.yaml) or the project's equivalent.

### 9. Close and recover

Update project status, task, decision, and risk sources. Reclaim agents that no longer have work. Remove branches or worktrees only after merge and recoverability are confirmed.

Distinguish local Git history, a private remote copy, an independent archive, and a tested recovery path. A successful push is not proof that recovery works.

## Stop conditions

Stop the affected expansion or high-risk action and report back when:

- project facts, the task contract, or baseline commit conflict;
- required work exceeds the lease or changes an interface, architecture, or data structure;
- real data, secrets, privileged access, compliance, production, or irreversible actions appear;
- test evidence cannot be tied to the reviewed version;
- rollback cannot be demonstrated;
- required authority is missing or a security boundary blocks the action.

Report: `Confirmed facts / Current impact / Not executed / Risk / Options / Required approval / Rollback`.

## Output standard

- Lead with the recommendation.
- Clearly distinguish designed, written, created, run, and verified states.
- Default to the smallest sufficient team and explain omitted roles.
- Optimize for accepted user value, traceable evidence, and recoverability.

