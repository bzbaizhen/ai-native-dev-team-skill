---
name: bootstrap-ai-native-dev-team
description: Route, bootstrap, or adjust an AI-native software development team with proportional controls. Use when starting a software project, deciding whether to delegate, planning parallel implementation, assigning file ownership, selecting cost-aware model capability and reasoning, defining independent validation, or correcting an existing team. Produce an approval-ready proposal before creating agents or changing repositories.
---

# Bootstrap an AI-Native Development Team

Operate from the main agent as the control plane. Treat delegated agents as
task-scoped executors or independent validators. Reply in the user's language and keep
`Confirmed facts / Inferences / To verify` distinct.

## Resolve authority and facts

Apply, in order:

1. System, developer, and current explicit user instructions.
2. Active repository instructions and accepted ADRs.
3. This workflow and the selected development layer.
4. Project defaults.

Inspect product scope, repository state, task baseline, permissions, test entry points,
integration backlog, rollback, and recovery requirements before asking questions. Reuse
a repository-host-toolchain preflight only while its relevant inputs remain unchanged.

## Select one development layer

Score complexity (`C0-C3`) and risk (`R0-R3`) separately, then choose:

| Layer | Select when | Default posture |
|---|---|---|
| **Core** | C0/C1, R0/R1, and no material behavior or boundary change | Main agent or one isolated Worker |
| **Controlled** | Material behavior, C2/C3, R2/R3, interface/dependency/data/security change, concurrency, or production/public action | One path-bounded Writer plus an independent Validator by default |

Read [routing-and-topologies.md](references/routing-and-topologies.md) for capability,
reasoning, topology, and evidence-reuse rules. Complexity selects implementation
capability and reasoning. Risk selects permissions, review independence, approval,
rollback, and recovery; risk alone does not raise model capability.

## Core

Read [core.md](references/core.md) when no Controlled trigger exists. Keep C0/R0 micro
work with the main agent. Delegate a deterministic batch or isolated C1 slice only when
handoff has net value. Core creates no standing team or mandatory governance files.

## Controlled

Read [controlled.md](references/controlled.md) when any Controlled trigger appears.
Use the smallest task contract and one Writer/independent-Validator cell for material
work. Bind validation and acceptance to the exact candidate. Apply the R3 owner,
security, privacy, production, public-action, rollback, and recovery overlay when risk
requires it.

## Modes

- `proposal`: inspect and return an approval-ready plan; do not create agents or edit project files.
- `initialize`: after approval, create only the approved team artifacts and resources.
- `adjust`: correct an existing team or task topology while preserving confirmed facts.

An initialization or adjustment request authorizes only ordinary, reversible writes
inside the approved scope. Production, real data, credentials, paid resources, public
publication, irreversible migration, and deletion still require explicit Owner
approval.

## Team and acceptance rules

The main agent owns fact boundaries, routing, task graph, contracts, conflicts,
integration, stop decisions, and final acceptance. Form the smallest sufficient
topology: no delegation, one Worker, a Writer/Validator cell, or a larger team only for
independent contract-frozen slices or concrete specialist gates.

One file has one Writer at a time. Give every delegated agent a task-local packet with
the objective, confirmed facts, task baseline, exact allowed paths, frozen interface,
checks, stop conditions, and rollback. Do not delegate unresolved product direction or
the final merge decision.

Freeze the write lease at `dev_complete`; reopen it explicitly for fixes. Distinguish
designed, written, run, verified, accepted, integrated, and released. Accept only the
exact validated change integrated into the stable branch.

Stop when scope, task baseline, permissions, interface, evidence, or rollback conflicts,
or when secrets, real data, production, public action, deletion, or irreversible work
appears without authority. Report `Confirmed facts / Current impact / Not executed /
Risk / Options / Required approval / Rollback`.

Lead with the recommendation, layer, capability and reasoning tiers, minimum topology,
evidence limits, and remaining verification.
