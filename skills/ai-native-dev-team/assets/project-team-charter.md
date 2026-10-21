# AI-Native Project Team Charter

## Project

- Name:
- One-sentence goal:
- Target users:
- Stage: `DISCOVERY / MVP / BETA / PRODUCTION`
- Business owner:
- Main agent:
- Effective date:
- Development workflow version:

## Scope and success

- In scope:
- Out of scope:
- Product success criteria:
- Completion means: the exact accepted change is present in the stable branch

## Sources of truth

| Type | Path or URL | Owner |
|---|---|---|
| Product | | |
| Tasks and status | | |
| Code and stable branch | | |
| Contracts | | |
| Decisions and risks | | |
| Validation evidence | | |

## Repositories and environments

| Component | Unique editable source | Native platform | Stable branch | Task baseline | Build / test | Preflight fingerprint |
|---|---|---|---|---|---|---|
| | | | | | | |

## Routing and model mapping

- Active routing profile: `none / <explicitly-selected-profile-id>`
- Profile selection authority/evidence:
- Runtime mapping observation method: `unknown / <method>`

| Complexity | Capability | Reasoning | Current model mapping | Fallback |
|---|---|---|---|---|
| Simple, tightly coupled, or nearly completed work | main-agent | current | | check SKILL.md delegation conditions |
| C0 batch | economy | low | | |
| C1 | standard | medium | | |
| C2 | advanced | high | | |
| C3 implementation slice | frontier | max | | task-scoped Writer or stop |

- Risk `R0-R3` controls gates, not capability.
- Never claim a model was used when the runtime did not expose it.
- Prefer lightweight delegation under the SKILL.md conditions: clear boundaries and acceptance, concrete parallel work, confirmed suitable model routing, or necessary independent validation, with manageable overhead. Start with one delegate; no quantified net-gain proof is required. Record actual runtime mapping and applicable pricing evidence before claiming lower cost.
- The main agent may take over within existing scope after settling write ownership; preserve required validation and actual authority boundaries.
- Actual task runtime model/provider, only if observable: `unknown / task-local value`
- Actual task reasoning effort, only if observable: `unknown / task-local value`
- Input tokens, only if observable: `unknown / task-local count`
- Output tokens, only if observable: `unknown / task-local count`
- Steps, only if observable: `unknown / task-local count`
- First-pass result: `unknown / accepted / reopened / failed`
- Reopens: `unknown / task-local count`
- Escalation reason: `none / unknown / task-local reason`
- Optional prospective metrics: `not-selected / selected`; when selected, the main
  agent is the sole local ledger writer and absent values remain unknown.

## Team and authority

| Role | Activation | Responsibility | Prohibited actions | Handoff |
|---|---|---|---|---|
| Business owner | always | | | |
| Main agent | always | scope, architecture decisions, contracts, permissions, integration, evidence review, stop, acceptance | wasteful repetition of Writer work supported by reliable evidence; necessary independent review remains required | |
| Writer | per approved task | | scope expansion | |
| Independent validator | material behavior or risk | | silent product fix | |
| Specialist | by domain/risk | | replacing Owner approval | |

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
- DQR protocol for material acceptance:
- DQR findings, limitations, and revalidation:
- Candidate/stable Commit evidence:
- Release approval:
- Rollback:
- Remote copy:
- Independent archive/recovery drill:

## Confirmed facts

-

## Inferences

-

## To verify

-

## Accepted exceptions

-
