---
name: bootstrap-ai-native-dev-team
description: Route, bootstrap, or adjust an AI-native software development team with proportional controls. Use when starting a software project, deciding whether to delegate, planning implementation, assigning file ownership, selecting cost-aware capability and reasoning, defining independent validation, or correcting an existing team.
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

## Resolve the execution mode

An explicit request to build, implement, fix, initialize, or adjust creates one standing
authorization envelope for ordinary reversible work inside the stated repository and
task scope. It covers bounded delegation, workspace edits, local build/test/lint,
read-only Git inspection, handoffs, and reversible corrections. Continue through those
phases without asking for redundant approvals.

Use proposal-only mode when the user explicitly requests a plan, the scope cannot be
bounded, or a real authority boundary is already present. For an explicit implementation
request, proposal and initialization may be combined before execution.

The envelope excludes credentials or secrets, real or production data, paid resources,
publication, push/merge/deploy/release, destructive deletion, irreversible migration,
privilege escalation, and out-of-scope writes. Stop at those boundaries and request the
required authority. Prefer native file tools and task-local scripts; never use broad
global allowlisting as an approval shortcut.

## Select one development layer

Score complexity (`C0-C3`) and risk (`R0-R3`) separately, then choose:

| Layer | Select when | Default posture |
|---|---|---|
| **Core** | C0/C1, R0/R1, and no material behavior or boundary change | Strict C0 main-agent work or one task-scoped Writer |
| **Controlled** | Material behavior, C2/C3, R2/R3, interface/dependency/data/security change, concurrency, or production/public action | One path-bounded Writer plus an independent Validator |

Read [routing-and-topologies.md](references/routing-and-topologies.md) for capability,
reasoning, topology, and evidence-reuse rules. Complexity selects implementation
capability and reasoning. Risk selects permissions, review independence, approval,
rollback, and recovery; risk alone does not raise model capability.

## Core

Read [core.md](references/core.md) when no Controlled trigger exists. Main-agent direct
implementation is limited to one tiny deterministic, low-risk, single-file C0 edit with
no material, interface, dependency, data, security, concurrency, production, or public
effect; no debugging loop or test authoring; and exactly one deterministic verification.
Read-only control-plane work is also eligible. If any condition is absent or uncertain,
delegate. Every C0 mechanical batch and every C1+ implementation, refactor, bug fix,
test-writing, or debugging task requires a task-scoped Writer on the configured
lower-cost execution path. There is no generic handoff-cost exception.

## Controlled

Read [controlled.md](references/controlled.md) when any Controlled trigger appears.
Use the smallest task contract, one Writer on the configured lower-cost execution path,
and one independent Validator for material work. Bind validation and acceptance to the
exact candidate. Apply the R3 owner, security, privacy, production, public-action,
rollback, and recovery overlay when risk requires it.

## Modes

- `proposal`: when proposal-only conditions apply, inspect and return an approval-ready plan without project writes.
- `initialize`: create only the task artifacts and resources inside the standing authorization envelope.
- `adjust`: correct an existing team or task topology while preserving confirmed facts.

These modes do not expand the execution envelope or cross an Owner boundary.

## Team and acceptance rules

The main agent owns fact boundaries, scope, architecture decisions, routing, task graph,
contracts, permissions, conflicts, integration, evidence review, stop decisions, and
final acceptance. It does not duplicate a Writer's repository exploration,
implementation, or test/debug loop. Form the smallest sufficient topology: strict C0
main-agent work, one task-scoped Writer, a Writer/Validator cell, or a larger team only
for independent contract-frozen slices or concrete specialist gates. C3 architecture
may stay with the main agent, but frozen implementation slices go to Writers.

Higher-cost main-agent implementation takeover requires all of the following: the
Writer path is unavailable or has repeatedly failed with evidence, the task cannot be
safely re-sliced, the user explicitly authorizes the takeover, and the reason is
recorded. An orchestration subagent supports a cost-saving claim only when its observable
runtime mapping is to a lower-cost tier; never infer that mapping.

One file has one Writer at a time. Give every delegated agent a task-local packet with
the objective, confirmed facts, task baseline, exact allowed paths, frozen interface,
checks, stop conditions, and rollback. Do not delegate unresolved product direction or
the final merge decision.

Freeze the write lease at `dev_complete`; the main agent may reopen it for in-envelope
fixes while invalidating affected evidence. Distinguish
designed, written, run, verified, accepted, integrated, and released. Accept only the
exact validated change integrated into the stable branch.

Stop when scope, task baseline, permissions, interface, evidence, or rollback conflicts,
or when secrets, real data, production, public action, deletion, or irreversible work
appears without authority. Report `Confirmed facts / Current impact / Not executed /
Risk / Options / Required approval / Rollback`.

Lead with the recommendation, layer, capability and reasoning tiers, minimum topology,
evidence limits, and remaining verification.
