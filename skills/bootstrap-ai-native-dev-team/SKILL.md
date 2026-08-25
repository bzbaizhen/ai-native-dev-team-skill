---
name: bootstrap-ai-native-dev-team
description: Route AI-native development with proportional controls.
---

# Bootstrap an AI-Native Development Team

Operate from the main agent as the control plane. Delegated agents are task-scoped
Writers or independent Validators; keep `Confirmed facts / Inferences / To verify`
distinct and reply in the user's language.

## Authority and authorization

Apply authority in order: (1) system, developer, and explicit user
instructions; (2) active repository instructions and accepted ADRs; (3) this workflow
and its selected layer; (4) project defaults. Inspect scope, repository state, task
baseline, permissions, test entry points, integration backlog, rollback, and recovery
before asking questions; reuse a preflight only while its inputs remain unchanged.

An explicit build, implement, fix, initialize, or adjust request creates a standing
authorization envelope for ordinary reversible work in the stated repository and task
scope: bounded delegation, workspace edits, local build/test/lint, read-only Git
inspection, handoffs, and reversible corrections. Continue without redundant approval.
Use proposal-only mode when the user explicitly requests a plan, scope cannot be
bounded, or a real authority boundary already exists. An explicit implementation request
may combine proposal and initialization before execution. `proposal`, `initialize`, and
`adjust` do not expand the envelope.
The envelope excludes credentials or secrets, real or production data, paid resources,
publication, push/merge/deploy/release, destructive deletion, irreversible migration,
privilege escalation, and out-of-scope writes. Never use broad global allowlisting as an
approval shortcut. Stop at each boundary and request the required authority; prefer
native file tools and task-local scripts.

## Select and route

Score complexity (`C0-C3`) and risk (`R0-R3`) independently. Select **Controlled** for
material behavior, C2/C3, R2/R3, interface/dependency/data/security change, concurrency,
or production/deployment/release/public action; otherwise select **Core**. Resolve
missing material facts before Core. Read [routing-and-topologies.md](references/routing-and-topologies.md)
for thresholds, capability/reasoning tiers, topology, evidence reuse, and recovery.
Optional profiles in `references/model-routing-*.md` require explicit Owner
selection; file presence never activates a profile. They map vendor-neutral tiers to a
dated runtime, never a canonical layer.
For a Linear-governed implementation issue or explicit isolation request, read
[Git isolation](references/git-isolation-bootstrap.md); run the helper before Writer dispatch; preserve non-Linear Core/Controlled routing.

### Core

Read [core.md](references/core.md) when no Controlled trigger exists. Strict C0 direct
implementation is limited to one tiny deterministic, low-risk, single-file edit with
no material, interface, dependency, data, security, concurrency, production, or public
effect; no debugging loop or test authoring; and exactly one deterministic verification.
Read-only control-plane work is separately eligible. If any condition is absent or
uncertain, fail closed to a Writer.
Every C0 mechanical batch and every C1+ implementation, refactor, bug fix, test-writing,
or debugging task requires a task-scoped Writer on the configured lower-cost
path. There is no generic handoff-cost exception.

### Controlled

Read [controlled.md](references/controlled.md) whenever a Controlled trigger appears.
Use one path-bounded Writer and, for material work, one independent Validator; bind
validation and acceptance to the exact candidate. Apply the R3 authority, security,
privacy, production, public-action, rollback, and recovery gates when risk requires.

## Windows unattended Coding CLI

For unattended non-interactive Coding CLI exec, Writer, or Validator work on Windows,
default to `pty=false`, `background=true`, and `notify_on_complete=true`; reserve
`pty=true` for an interactive TUI, login, or genuine terminal input. Final output is not
process-exit evidence: accept completion only after fresh registry status is `exited` and
the exit code is captured. Use the routing reference's one short bounded grace check,
inspect fresh status, and, if needed, terminate only the exact tracked process; never
start a duplicate Writer or repeatedly wait/reconnect.

## Control, lease, and cost guards

The main agent owns facts, scope, architecture decisions, routing, contracts,
permissions, integration, evidence review, stop decisions, and final acceptance; it does
not duplicate a Writer's exploration, implementation, or test/debug loop. One file has
one Writer at a time. Freeze the write lease at `dev_complete`; reopen it only for
in-envelope fixes and invalidate affected evidence.
Distinguish designed, written, run, verified, accepted, integrated, and released; accept
only the exact validated change integrated into the stable branch.
Higher-cost main-agent implementation takeover requires a Writer path that is unavailable
or repeatedly failed with evidence, a task that cannot be safely re-sliced, a user who
explicitly authorizes the takeover, and a recorded reason. An orchestration subagent
supports a cost-saving claim only with an observable runtime mapping to a lower-cost tier;
never infer that mapping.

## Load Level-2 assets only on demand

Do not preload assets; load only the asset whose matching trigger applies:

- [team-bootstrap-proposal.md](assets/team-bootstrap-proposal.md) only when an explicit proposal request needs an approval-ready team proposal.
- [task-contract.md](assets/task-contract.md) only when Controlled work explicitly needs a durable written contract or frozen interface.
- [project-team-charter.md](assets/project-team-charter.md) only when an explicitly requested long-lived multi-task team is being established.
- [evidence-manifest.yaml](assets/evidence-manifest.yaml) only when a machine-readable evidence package is explicitly required for independent exact-candidate validation and acceptance; it is not needed for every validation.

## Stop and report

Stop when scope, task baseline, permissions, interface, evidence, or rollback conflicts,
or when an excluded authority boundary appears. Report `Confirmed facts / Current impact /
Not executed / Risk / Options / Required approval / Rollback`. Lead with the
recommendation, layer, capability/reasoning tiers, minimum topology, evidence limits, and
remaining verification.
