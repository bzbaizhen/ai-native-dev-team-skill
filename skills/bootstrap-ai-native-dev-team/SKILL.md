---
name: bootstrap-ai-native-dev-team
description: Route, bootstrap, resize, or audit AI-native software delivery with cost-aware capability selection and proportional governance. Use when deciding whether work should stay with the main agent, go to one worker, use an implementer-validator cell, or require a multi-agent team; when planning parallel implementation, write ownership, worktrees, release gates, or recovery; and when auditing team efficiency or delivery evidence. Produce an approval-ready proposal before creating agents or changing repositories. Do not invoke the full team lifecycle for a small low-risk task unless the user explicitly asks for this skill.
---

# Bootstrap an AI-Native Development Team

Operate only from the main agent or control plane. Treat workers as task-scoped executors, not as copies of the control plane. Optimize for accepted user value per unit of time and capability cost while preserving evidence, approval, and recovery.

Reply in the user's language. Keep `Confirmed facts / Inferences / To verify` distinct, translating the labels when useful.

## Resolve authority

Apply, in order:

1. System, developer, and current explicit user instructions.
2. Active repository instructions and accepted ADRs.
3. This workflow and the selected governance profile.
4. Project defaults.

Do not bypass permissions or silently override project reality. Record durable exceptions with an owner, impact, and reversal condition.

## Route before forming a team

Assess complexity `C0-C3` and risk `R0-R3` separately, then choose one route:

| Route | Use when | Default execution |
|---|---|---|
| `no-delegation` | Read-only or tiny control-plane work; delegation overhead exceeds value | Main agent |
| `single-worker` | One isolated, easily verified slice or mechanical batch | One worker, main-agent acceptance |
| `task-cell` | Material behavior change or meaningful regression risk | One implementer plus an independent validator |
| `team-required` | Independent slices, multiple repositories, frozen cross-component contracts, specialist gates, release, migration, or R3 work | Minimum approved team |

A single worker is not a team. Do not create a charter, branch, worktree, or standing role merely because delegation is possible. See [routing-and-topologies.md](references/routing-and-topologies.md) for scoring, capability tiers, escalation, and topology rules.

If the route is `no-delegation`, complete the work in the main thread and stop the team workflow. If it is `single-worker` or `task-cell`, issue only the necessary task contract and validation gate. Enter the full lifecycle below only for `team-required` or when the user explicitly requests bootstrap, adjustment, or audit.

## Select a lifecycle mode

State the mode when entering the team lifecycle:

- `proposal`: inspect and return an approval-ready plan; make no project writes or agent changes. Default.
- `initialize`: propose first, then create only approved artifacts and team resources.
- `adjust`: resize or correct an existing team without discarding confirmed facts or accepted decisions.
- `audit`: read-only comparison of actual routing, delivery flow, evidence, and governance cost.

Initialization authorizes ordinary reversible project writes only within the approved scope. It does not authorize production, real data, credentials, paid resources, public release, irreversible migration, or deletion of material recovery copies.

## Establish the baseline once

Inspect primary evidence before asking questions:

- product goal, users, scope, stage, success criteria, and active decisions;
- repository roots, instructions, Git status, stable branch, remotes, baseline commit, branches, worktrees, and write conflicts;
- product, task, contract, status, risk, decision, and evidence sources of truth;
- native platform, build, test, deployment, and recovery requirements;
- existing agents and current integration backlog.

Run an environment preflight once per repository-host-toolchain fingerprint. Reuse it while the host, repository root, runtime, lockfiles, build/test entry points, and permissions remain unchanged. Re-run only after a relevant change or a failed assumption; do not make every worker rediscover the environment.

Report `Confirmed facts / Inferences / To verify`. Ask only about missing or conflicting inputs that materially change execution.

## Score complexity and risk separately

- Complexity `C0-C3` controls decomposition, context size, capability tier, and reasoning effort.
- Risk `R0-R3` controls permission, review independence, approval, rollback evidence, and stop conditions.

Never raise implementation capability merely because risk is high; strengthen gates instead. Never use a frontier/highest-cost tier to compensate for an oversized or unclear task. Split first.

Use capability names, not vendor model names:

| Complexity | Default executor tier | Reasoning |
|---|---|---|
| C0 control-plane micro-task | Main agent | Current |
| C0 delegated mechanical batch | Economy | Low |
| C1 | Standard | Medium |
| C2 | Advanced | High |
| C3 | Frontier, or main-agent takeover | Max |

The active global or project configuration maps these tiers to available models. Record every frontier-tier escalation reason. Never claim a model was used unless the runtime confirms it.

## Select proportional governance

Choose the lightest profile that satisfies both dimensions and the topology:

- [Lean](references/governance-lean.md): C0/C1, R0/R1, at most one writer, no release or migration.
- [Controlled](references/governance-controlled.md): C2, R2, a task cell, contract-sensitive integration, or multiple approved writers.
- [Strict](references/governance-strict.md): C3, R3, production, security/privacy, irreversible migration, or public release.

Read only the selected profile. Higher risk overrides a lower-complexity profile. Do not give the complete Skill or unrelated profiles to an ordinary implementer, validator, or worker; send the approved contract, relevant project facts, allowed paths, and required checks.

## Compose the minimum team

Activate only roles with real work:

- Business owner: approves business scope, production, real data, public release, paid resources, and irreversible actions.
- Main agent: owns intake, facts, task graph, routing, contracts, conflicts, integration, and final acceptance.
- Implementer: writes only within an approved contract and path lease.
- Independent validator: tests the exact candidate version and does not silently fix product code under review.
- Specialist: architecture, AI, data provenance, DevOps, security, privacy/compliance, or research only when domain or risk requires it.

The main agent retains unresolved product direction, fact boundaries, routing exceptions, and the final merge decision.

## Control flow and parallelism

Default to one writer and one validator per repository. Add writers only when interfaces are frozen, paths are independent, each shared file has one owner, integration order is explicit, and validation capacity can absorb the work.

Do not start a new writer while any task is waiting at `DEV_COMPLETE`, `QA_PENDING`, or `MERGE_READY` unless the main agent records a concrete override reason. Entering the stable branch is completion; worker delivery, a Commit, or `QA_PASSED` alone is not.

Before creating an agent, inspect and reuse compatible existing agents as required by the active environment. After handoff, freeze the writer lease. Reopen explicitly for fixes.

## Produce the approval gate

Use [team-bootstrap-proposal.md](assets/team-bootstrap-proposal.md) or an equivalent. Include:

- evidence-backed facts, inferences, blockers, stage, `C/R` scores, route, capability tier, and governance profile;
- minimum topology, omitted roles, dependencies, contracts, Writer/Validator, file ownership, and integration order;
- exact proposed agents, files, branches, worktrees, and other writes;
- approvals, stop conditions, rollback, recovery, tests, and immutable acceptance evidence;
- recommendation: `approve`, `approve with changes`, or `do not form a team yet`.

Stop in `proposal` mode. Never describe proposed resources or checks as created, run, verified, merged, or released.

## Initialize and execute approved work

In `initialize` or an approved `adjust`:

1. Create only stage-appropriate sources of truth and the approved [project-team-charter.md](assets/project-team-charter.md).
2. Create a [task-contract.md](assets/task-contract.md) for each material write task.
3. Issue one path-bounded lease per writer; one file has one writer at a time.
4. Create or reuse only approved agents, branches, and worktrees.
5. Have the implementer self-check, then run relevant automated checks.
6. Have an independent validator review the exact candidate Commit for material behavior changes.
7. Let the main agent accept only the exact version integrated into the stable branch.
8. Record evidence with [evidence-manifest.yaml](assets/evidence-manifest.yaml), update status, freeze leases, and reclaim idle resources.

Distinguish designed, written, created, run, verified, accepted, merged, and released states.

## Measure delivery, not activity

For prospective V2 tasks, the main agent owns `.ai-team/metrics/events.jsonl`. Workers never write the shared ledger; they return [metrics-handoff.yaml](assets/metrics-handoff.yaml).

Record `task_ready`, `worker_started` when delegated, `dev_complete`, `qa_complete` when applicable, and `accepted`. Record `blocked`, `reopened`, and `cancelled` when they occur. Follow [metrics.md](references/metrics.md) and [metrics-event.schema.json](references/metrics-event.schema.json); use `scripts/team_metrics.py` for `record`, `snapshot`, `audit`, and `compare`.

For a stable V2 release decision, fix the candidate, source roster, and eligible V1 baseline identities at an externally trusted Git freeze Commit. Hash each frozen baseline object that follows [release-v1-baseline-evidence.schema.json](references/release-v1-baseline-evidence.schema.json); do not treat an invented or unevidenced C/R/topology string as comparable. Before each outcome, append exactly one linear task-ready Commit using [release-registration-receipt.schema.json](references/release-registration-receipt.schema.json); close with [release-anchor-closure.schema.json](references/release-anchor-closure.schema.json), including the final Manifest digest. Supply the trusted freeze/head SHAs outside the Manifest so it can map but cannot define the task universe or rewrite the closed evidence snapshot. Follow [release-source-registry.schema.json](references/release-source-registry.schema.json), [release-trial-manifest.schema.json](references/release-trial-manifest.schema.json), and [release-trial-evidence.schema.json](references/release-trial-evidence.schema.json), then run `scripts/v2_release_gate.py`. Never omit failed, unfinished, or non-comparable trials, and never count synthetic work or one task more than once.

Treat Commit count, line count, Agent count, thread count, or token volume alone as non-productivity metrics. Do not claim percentage improvement without a comparable baseline denominator.

## Stop conditions

Stop the affected expansion or high-risk action when facts, baseline, contract, permissions, interface, evidence, or rollback conflict; when secrets, real data, production, compliance, public release, deletion, or irreversible work appears without authority; or when validation cannot be tied to the reviewed version.

Report: `Confirmed facts / Current impact / Not executed / Risk / Options / Required approval / Rollback`.

## Output standard

Lead with the recommendation. Prefer the smallest topology and lowest sufficient capability tier. Explain exceptions, omitted roles, evidence limits, and remaining verification. Optimize for fast accepted value, cost-aware routing, traceable proof, and recoverability.
