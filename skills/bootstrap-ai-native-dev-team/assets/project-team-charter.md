# AI-Native Project Team Charter

## Project

- Name:
- One-sentence goal:
- Target users:
- Stage: `DISCOVERY / MVP / BETA / PRODUCTION`
- Business owner:
- Main agent:
- Effective date:
- Governance baseline version:

## Scope and success

- In scope:
- Out of scope:
- Success metrics:
- Completion means: exact accepted change is present in the stable branch

## Sources of truth

| Type | Path or URL | Owner |
|---|---|---|
| Product | | |
| Tasks and status | | |
| Code and stable branch | | |
| Contracts | | |
| Decisions and risks | | |
| Evidence | | |
| Metrics | `.ai-team/metrics/events.jsonl` or project equivalent | Main agent |

## Repositories and environment fingerprints

| Component | Unique editable source | Native platform | Stable branch | Baseline | Build / test | Preflight fingerprint |
|---|---|---|---|---|---|---|
| | | | | | | |

Re-run preflight only after host, root, runtime, lockfile, entry point, permission, or an assumption changes.

## Routing and capability mapping

| Complexity | Capability tier | Reasoning tier | Current model mapping | Fallback |
|---|---|---|---|---|
| C0 micro | main-agent | current | | |
| C0 batch | economy | low | | |
| C1 | standard | medium | | |
| C2 | advanced | high | | |
| C3 | frontier | max | | main agent or stop |

- Risk scale: `R0-R3` controls gates, not capability.
- Every frontier escalation requires a reason.
- Runtime model must be recorded when observable; never infer it.

## Team and authority

| Role | Activation | Responsibility | Prohibited actions | Handoff |
|---|---|---|---|---|
| Business owner | always | | | |
| Main agent | always | facts, task graph, routing, integration, acceptance | | |
| Writer | per approved task | | scope expansion | |
| Independent validator | material behavior or risk | | silent product fix | |
| Specialist | by domain/risk | | replacing Owner approval | |

Workers receive task contracts and the selected governance constraints, not the complete team Skill.

## Parallelism and integration

- Default topology:
- WIP limit:
- Integration-backlog gate:
- Single-file ownership:
- Branch/worktree/PR policy:
- Contract freeze/change policy:
- Write-lease location:

## Quality, release, and recovery

- Definition of Ready:
- Definition of Done:
- CI:
- Independent validation:
- Candidate/stable Commit evidence:
- Release approval:
- Rollback:
- Remote copy:
- Independent archive/recovery drill:

## Metrics and audit

- Main-agent ledger writer:
- Handoff format:
- Snapshot cadence:
- Comparison strata:
- Environment attribution exclusions:

## Confirmed facts

-

## Inferences

-

## To verify

-

## Accepted exceptions

Link each durable exception to an ADR with owner, impact, and reversal condition.

-
