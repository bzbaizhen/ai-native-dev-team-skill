---
name: bootstrap-ai-native-dev-team
description: Route, bootstrap, resize, or audit AI-native delivery through a default Core path, conditional Controlled governance, and an explicit Release Audit path. Use when deciding whether work stays with the main agent, uses one worker, needs an implementer-validator cell, or requires a multi-agent team; when planning parallel implementation, ownership, recovery, or formal efficiency and stable-version evidence. Produce an approval-ready proposal before creating agents or changing repositories.
---

# Bootstrap an AI-Native Development Team

Operate from the main agent or control plane. Treat delegated workers as task-scoped
executors, not copies of this Skill. Reply in the user's language and keep
`Confirmed facts / Inferences / To verify` distinct.

## Resolve authority and facts

Apply, in order:

1. System, developer, and current explicit user instructions.
2. Active repository instructions and accepted ADRs.
3. This workflow and the selected layer.
4. Project defaults.

Inspect product scope, repository state, baseline, permissions, test entry points,
recovery requirements, and integration backlog before asking questions. Reuse one
repository-host-toolchain preflight while its fingerprint, lockfiles, test entry points,
generated inputs, permissions, and relevant external dependencies are unchanged.

## Select the layer before forming a team

Score complexity (`C0-C3`) and risk (`R0-R3`) separately. Then select the first
applicable layer:

| Layer | Select when | Default posture |
|---|---|---|
| **Core** | C0/C1, R0/R1, and no material behavior or boundary change | Main agent or one task-packet worker; no standing governance |
| **Controlled** | Material behavior, C2/C3, R2/R3, interface/dependency/data/security change, concurrency, or production/public action | One Writer plus an independent Validator by default |
| **Release Audit** | Explicit stable-version qualification, formal efficiency comparison, historical-baseline qualification, or external evidence-freeze request | Separately approved audit workflow |

Use [routing-and-topologies.md](references/routing-and-topologies.md) for the selector,
capability tiers, topology rules, and immutable-evidence reuse conditions.

Complexity selects vendor-neutral capability and reasoning. Risk changes permissions,
review independence, approval, rollback, and recovery gates; it does not by itself
raise implementation capability.

## Core default

Read [core.md](references/core.md) when the selector stays in Core. A C0/R0 micro task
stays with the main agent and creates zero agents and zero mandatory governance files.
Non-material C1/R1 work does not require a Worktree, ledger, or independent Validator.
An optional delegated Worker receives only an inline task packet and reports
`worker_skill_loaded=false`; it does not load this complete Skill.

Escalate immediately if material behavior, a boundary change, difficult verification,
R2/R3 risk, concurrency, or production/public action appears.

## Controlled selector

Read [controlled.md](references/controlled.md) when any Controlled trigger appears.
Use one path-bounded Writer and one independent Validator for material work by default;
bind checks and acceptance to the exact candidate. Apply the R3 approval, security,
privacy, production, and recovery overlay when risk requires it. Ordinary release,
deployment, or publication is Controlled/R3 with `release_audit=false` unless the user
also makes one of the explicit Release Audit requests above.

## Explicit Release Audit selector

Read [release-audit.md](references/release-audit.md) only when the user explicitly asks
for stable-version qualification, a formal efficiency comparison, historical-baseline
qualification, or an external evidence freeze. Do not infer this layer from the word
"release" alone. Keep ordinary delivery in Controlled and keep Release Audit resources
inactive until this selector is true.

Use [metrics.md](references/metrics.md) only when optional delivery measurement or the
explicit Release Audit workflow is selected. The main agent owns any shared ledger.

## Team and acceptance rules

The main agent owns facts, routing, contracts, conflicts, integration, stop decisions,
and final acceptance. Form the smallest approved topology: no delegation for tiny work,
one Worker for an isolated slice, or a Writer/independent-Validator cell for material
behavior. Add specialists only for a concrete gate. One file has one Writer at a time.

Default lifecycle mode is `proposal`: return an approval-ready plan without project or
agent writes. In approved `initialize` or `adjust` work, create only the contract, lease,
and evidence sources required by the selected layer and project policy. Freeze the write
lease at `dev_complete`; reopen it explicitly for fixes. Accept only the exact validated
change integrated into the stable branch.

Distinguish designed, written, run, verified, accepted, integrated, and released. Stop
when scope, baseline, permissions, interface, evidence, or rollback conflicts, or when
secrets, real data, production, public release, deletion, or irreversible work appears
without authority. Report `Confirmed facts / Current impact / Not executed / Risk /
Options / Required approval / Rollback`.

Lead with the recommendation, selected layer, capability and reasoning tiers, minimum
topology, evidence limits, and remaining verification.
