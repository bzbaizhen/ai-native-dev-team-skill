# Routing, complexity, risk, and topology

Use this reference only in the main control plane. Do not send it to ordinary Workers.

## Score complexity and risk independently

| Level | Evidence | Capability and reasoning |
|---|---|---|
| C0 | Query, tiny edit, deterministic transform, or mechanical batch | Main agent/Current for micro work; Economy/Low for an optional batch Worker |
| C1 | Narrow scope, known path, and easy verification | Standard/Medium |
| C2 | Cross-file or cross-module work, meaningful design choice, or uncertain integration | Advanced/High |
| C3 | Architecture, cross-system change, unknown root cause, or difficult migration | Frontier/Max or main-agent takeover |

Split mixed objectives before escalating capability. A larger model is not a substitute
for a clear task boundary.

| Risk | Evidence | Minimum gate |
|---|---|---|
| R0 | Read-only and no side effects | Main-agent scope check |
| R1 | Ordinary reversible project change | Relevant tests and main-agent review |
| R2 | Interface, dependency, data shape, security boundary, or material regression risk | Independent exact-candidate validation and executable rollback |
| R3 | Production, credentials, compliance, public action, real data, irreversible work, deletion, or paid resource | Owner approval, relevant specialist gate, exact validation, and rollback/recovery evidence |

Risk changes gates, not implementation capability. A one-line authentication change can
be C1/R3; a difficult pure refactor can be C3/R1.

## Select Core or Controlled

```text
controlled_trigger = material behavior OR C2/C3 OR R2/R3 OR
                     interface/dependency/data/security change OR concurrency OR
                     production/deployment/release/public action

if controlled_trigger:
    layer = Controlled
else:
    layer = Core
```

Resolve missing material facts before choosing Core. Ordinary release, deployment, and
publication are Controlled/R3.

## Choose the smallest topology

1. `no-delegation` for C0/R0 micro work or when handoff costs more than the task.
2. `single-worker` for an isolated, easily verified slice or deterministic batch.
3. `task-cell` for material behavior or meaningful regression risk: one Writer and one independent Validator.
4. `team-required` only for independent contract-frozen slices, multiple repositories, or concrete specialist gates.

Core creates no mandatory governance artifact. Controlled uses only the material
contract, path lease, validation, approval, and recovery evidence the task needs.

One file has one Writer at a time. Do not open another Writer while work is at
`DEV_COMPLETE`, `QA_PENDING`, or `MERGE_READY` unless the main agent records a
reason and validation capacity is available.

## Cost-aware capability routing

| Work | Capability | Reasoning | Escalate when |
|---|---|---|---|
| C0 micro control-plane work | Main agent | Current | Do not delegate merely to lower nominal call cost |
| C0 deterministic batch | Economy | Low | Ambiguity, exceptions, or failed deterministic checks |
| C1 | Standard | Medium | Repeated failure, hidden dependency, or inadequate verification |
| C2 | Advanced | High | Architecture or root cause remains unresolved |
| C3 | Frontier | Max | Main agent takes over or stops if safe delegation is unavailable |

A project maps these vendor-neutral tiers to currently available models and one declared
fallback. Optimize for the expected total cost of an accepted result, including likely
rework and validation, not the cheapest single call. Never claim a model was used when
the runtime did not expose it.

## Delegation packet

Give a delegated agent only the task-local packet:

- objective and user value;
- confirmed facts, task baseline Commit, repository, native environment, and allowed paths;
- frozen interface or an explicit prohibition on interface changes;
- exact read/write ownership and integration order;
- selected capability/reasoning tier;
- required checks, immutable candidate identity, stop conditions, and rollback.

Workers do not decide the team design, expand scope, or reload the whole project context.
The main agent verifies their handoff, diff, tests, and path boundary.

## Evidence reuse and rerun triggers

Carry validation evidence forward only while these remain unchanged:

- candidate Commit/tree and any history-sensitive behavior;
- repository-host-toolchain environment fingerprint;
- lockfiles and test entry points;
- permissions;
- generated inputs;
- relevant external dependencies.

Rerun affected checks when any relevant input changes, merge resolution occurs,
repository policy requires it, or earlier evidence is incomplete or failed.
