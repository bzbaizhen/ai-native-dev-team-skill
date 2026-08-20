# Core layer

Use Core for C0/C1, R0/R1 work when there is no material behavior, interface,
dependency, data, security, concurrency, production, release, or public-action trigger.

## Execute lightly

1. Inspect the smallest fact set needed to act.
2. Keep work with the main agent only when it is read-only control-plane work or one
   tiny deterministic, low-risk, single-file C0 edit with no material behavior,
   interface, dependency, data, security, concurrency, production, or public effect;
   no debugging loop or test authoring; and exactly one deterministic verification. If
   any condition is absent or uncertain, delegate.
3. Delegate every C0 mechanical batch and every C1+ implementation, refactor, bug fix,
   test-writing, or debugging task to one task-scoped Writer on the configured lower-cost
   execution path. There is no generic handoff-cost exception for implementation.
4. Give the Writer a task-local packet with exact inputs, allowed paths, checks, stop conditions, and rollback.
5. Run relevant checks and let the main agent review and accept the result.
6. Do not create a standing team, charter, Worktree, lease, or evidence folder solely because delegation is available.

| Work | Capability | Reasoning |
|---|---|---|
| C0 main-agent micro task | Main agent | Current |
| C0 delegated batch | Economy | Low |
| C1 | Standard | Medium |

Risk does not raise implementation capability. Move to [Controlled](controlled.md) when
R2/R3, material behavior, difficult verification, concurrency, or a boundary change
appears.

The main agent remains the control plane for scope, architecture decisions, contracts,
permissions, integration, evidence review, stop decisions, and acceptance. It does not
repeat the Writer's repository exploration, implementation, or test/debug loop. C3
architecture may remain with the main agent, but frozen implementation slices go to
Writers.

Higher-cost main-agent implementation takeover is allowed only when the Writer path is
unavailable or repeatedly fails with evidence, the task cannot be safely re-sliced, the
user explicitly authorizes the takeover, and the reason is recorded. An orchestration
subagent is not evidence of lower cost unless its observable runtime mapping is to a
lower-cost tier.

## Stop and escalate

Stop Core work and re-score when the task becomes C2/C3, material, hard to verify,
R2/R3, cross-component, concurrent, production-facing, release-related, or public.
Report `Confirmed facts / Current impact / Not executed / Risk / Options / Required
approval / Rollback`.
