# Routing, complexity, risk, and topology

Use this reference only in the main control plane. Do not send it to ordinary workers.

## Complexity

| Level | Evidence | Default capability |
|---|---|---|
| C0 | Query, tiny edit, deterministic transform, or mechanical batch | Main agent for micro work; Economy/Low for delegated batches |
| C1 | Narrow scope, known implementation path, easy verification | Standard/Medium |
| C2 | Cross-file or cross-module work, meaningful design choice, or uncertain integration | Advanced/High |
| C3 | Architecture, cross-system change, unknown root cause, or difficult migration | Frontier/Max or main-agent takeover |

Split tasks that mix multiple objectives. Capability escalation is not a substitute for a clear boundary.

## Risk

| Level | Evidence | Minimum gate |
|---|---|---|
| R0 | Read-only, no side effects | Main-agent scope check |
| R1 | Ordinary reversible project change | Relevant tests and main-agent review |
| R2 | Interface, dependency, data shape, security boundary, or material regression risk | Independent validation, exact Commit, executable rollback |
| R3 | Production, real data, credentials, compliance, public release, irreversible migration, deletion, or paid resource | Specialist gate when relevant, explicit owner approval, rollback or recovery evidence |

Risk changes gates, not implementation capability. A one-line authentication change can be C1/R3; a difficult pure refactor can be C3/R1.

## Route decision

Choose the first route that safely fits:

1. `no-delegation` when work is read-only or tiny and the main agent can finish it with less coordination than a handoff.
2. `single-worker` when one isolated writer can complete an easily verified slice or a mechanical batch.
3. `task-cell` when implementation needs independent validation because behavior or regression risk is material.
4. `team-required` when work has independently valuable slices, multiple repositories, frozen interfaces, multiple specialists, release/migration gates, or R3 coordination.

Do not call one worker a team. Do not create a permanent role without a current task.

## Cost-aware capability routing

The public Skill emits capability and reasoning tiers. A global or project rule maps them to current models.

| Work | Capability | Reasoning | Escalate when |
|---|---|---|---|
| C0 micro control-plane work | Main agent | Current | Never delegate merely to lower nominal model cost |
| C0 batch | Economy | Low | Ambiguity, exceptions, or failed deterministic checks |
| C1 | Standard | Medium | Repeated failure, hidden cross-module dependency, or inadequate verification |
| C2 | Advanced | High | Architecture or root cause remains unresolved |
| C3 | Frontier | Max | Main agent takes over or pauses if frontier delegation is unavailable or unsafe |

Record the actual runtime-provided model when observable. Record a reason for every Frontier selection. If the requested capability is unavailable, use the declared fallback once, take over in the main agent, or stop; never silently pretend.

## Topology and WIP

- Default per repository: one Writer and one Validator.
- Add a Writer only for an independent path or a frozen interface.
- One file has one Writer at a time.
- Do not start a new Writer while any task is at `DEV_COMPLETE`, `QA_PENDING`, or `MERGE_READY` unless an override reason is recorded.
- Validation capacity must be able to absorb development concurrency.
- Acceptance occurs only when the exact validated change enters the stable branch.

## Delegation packet

Give a worker only:

- objective and user value;
- confirmed project facts needed for the task;
- baseline Commit, repository, native environment, and allowed/forbidden paths;
- frozen interface or explicit statement that no interface changes are allowed;
- required checks, immutable evidence, stop conditions, and handoff format;
- selected capability/reasoning tier from the active model mapping.

Do not instruct the worker to reload this Skill or decide the team design.
