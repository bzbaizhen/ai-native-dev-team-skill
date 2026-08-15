# Routing, complexity, risk, and topology

Use this reference only in the main control plane. Do not send it to ordinary Workers.

## Contents

- [Score complexity and risk independently](#score-complexity-and-risk-independently)
- [Layer selector](#layer-selector)
- [Legacy profile encoding](#legacy-profile-encoding)
- [Route and topology](#route-and-topology)
- [Cost-aware capability routing](#cost-aware-capability-routing)
- [Delegation packet](#delegation-packet)
- [Evidence reuse and rerun triggers](#evidence-reuse-and-rerun-triggers)

## Score complexity and risk independently

| Level | Evidence | Capability and reasoning |
|---|---|---|
| C0 | Query, tiny edit, deterministic transform, or mechanical batch | Main agent/Current for micro work; Economy/Low for an optional batch Worker |
| C1 | Narrow scope, known path, and easy verification | Standard/Medium |
| C2 | Cross-file or cross-module work, meaningful design choice, or uncertain integration | Advanced/High |
| C3 | Architecture, cross-system change, unknown root cause, or difficult migration | Frontier/Max or main-agent takeover |

Split tasks that mix multiple objectives. Capability escalation is not a substitute for a clear boundary.

## Risk

| Level | Evidence | Minimum gate |
|---|---|---|
| R0 | Read-only, no side effects | Main-agent scope check |
| R1 | Ordinary reversible project change | Relevant tests and main-agent review |
| R2 | Interface, dependency, data shape, security boundary, or material regression risk | Independent exact-candidate validation and executable rollback |
| R3 | Production, credentials, compliance, public action, real data, irreversible work, deletion, or paid resource | Owner approval, relevant specialist gate, exact validation, and rollback/recovery evidence |

Risk changes gates, not implementation capability. A one-line authentication change can
be C1/R3; a difficult pure refactor can be C3/R1.

## Layer selector

Evaluate these predicates before choosing a topology:

```text
explicit_release_audit = an explicit request for stable qualification,
                         formal efficiency comparison, historical-baseline
                         qualification, or external evidence freeze
controlled_trigger = material behavior OR C2/C3 OR R2/R3 OR
                     interface/dependency/data/security change OR concurrency OR
                     production/deployment/release/public action

if explicit_release_audit:
    layer = Release Audit
else if controlled_trigger:
    layer = Controlled
else:
    layer = Core
```

The selector is fail-closed around ambiguity: ask the main agent to resolve a missing
fact rather than silently assuming Core. Ordinary release/deployment/publication is
Controlled/R3 with `release_audit=false`; the word “release” is not an explicit audit
request.

## Legacy profile encoding

The canonical product selector is `layer=core|controlled|release-audit`. The persisted
scenario/metrics field `profile` and the unchanged CLI field `governance_profile` retain
the first-phase legacy enum `lean|controlled|strict`:

| Canonical layer and condition | Legacy `profile` / `governance_profile` |
|---|---|
| Core | `lean` |
| Ordinary Controlled | `controlled` |
| Controlled with a C3 or R3 overlay | `strict` |
| Release Audit | `strict` |

This is a compatibility encoding only. It does not make Lean or Strict separate V2
product layers, and it does not change the unchanged CLI or metrics schema.

## Route and topology

Choose the smallest route that safely fits the selected layer:

1. `no-delegation` for C0/R0 micro work or when handoff costs more than the task.
2. `single-worker` for an isolated, easily verified slice or deterministic batch.
3. `task-cell` for material behavior or meaningful regression risk: one Writer and one
   independent Validator by default.
4. `team-required` only for independent contract-frozen slices, multiple repositories,
   multiple real specialists, or an explicitly approved audit topology.

Core creates no mandatory governance artifact. Controlled uses the smallest material
contract, lease, and acceptance evidence required by the repository; it does not require
a daily ledger by default. Release Audit activates its separately approved evidence and
measurement workflow.

One file has one Writer at a time. Do not open another Writer while work is at
`DEV_COMPLETE`, `QA_PENDING`, or `MERGE_READY` unless the main agent records an override
reason and validation capacity is available. Acceptance occurs only after the exact
validated candidate enters the stable branch.

## Cost-aware capability routing

The public Skill emits capability and reasoning tiers. A global or project rule maps
these tiers to current models.

| Work | Capability | Reasoning | Escalate when |
|---|---|---|---|
| C0 micro control-plane work | Main agent | Current | Never delegate merely to lower nominal model cost |
| C0 batch | Economy | Low | Ambiguity, exceptions, or failed deterministic checks |
| C1 | Standard | Medium | Repeated failure, hidden cross-module dependency, or inadequate verification |
| C2 | Advanced | High | Architecture or root cause remains unresolved |
| C3 | Frontier | Max | Main agent takes over or pauses if frontier delegation is unavailable or unsafe |

Record the actual runtime-provided model when observable and the reason for every
Frontier selection. If a required tier is unavailable, use the declared fallback once,
take over, or stop; never silently pretend.

## Delegation packet

Give a Worker only the task-local packet:

- objective and user value;
- confirmed facts, baseline Commit, repository, native environment, and allowed paths;
- frozen interface or an explicit statement that no interface change is allowed;
- selected capability/reasoning tier;
- required checks, immutable evidence, stop conditions, and rollback.

Workers report `worker_skill_loaded=false` and never decide the team design or reload the
complete Skill. One file has one Writer at a time. Do not open another Writer while work
is at `DEV_COMPLETE`, `QA_PENDING`, or `MERGE_READY` unless the main agent records an
override reason and validation capacity is available. Acceptance occurs only after the
exact validated candidate enters the stable branch.

## Evidence reuse and rerun triggers

Carry validation evidence forward only when all of these remain unchanged:

- candidate Commit/tree and any history-sensitive behavior;
- repository-host-toolchain environment fingerprint;
- lockfiles and test entry points;
- permissions;
- generated inputs; and
- relevant external dependencies.

Rerun the affected or full check when the integrated tree differs, a history-sensitive
condition exists, any listed input changes, merge resolution occurs, repository policy
requires it, or earlier evidence is incomplete or failed. A second full suite is not
justified merely by moving an unchanged candidate between agents.
