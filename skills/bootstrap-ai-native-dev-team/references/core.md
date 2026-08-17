# Core layer

Use Core for C0/C1, R0/R1 work when there is no material behavior, interface,
dependency, data, security, concurrency, production, release, or public-action trigger.

## Execute lightly

1. Inspect the smallest fact set needed to act.
2. Keep C0/R0 micro work with the main agent.
3. Delegate at most one deterministic batch or isolated C1 slice when handoff has net value.
4. Give the Worker a task-local packet with exact inputs, allowed paths, checks, stop conditions, and rollback.
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

## Stop and escalate

Stop Core work and re-score when the task becomes C2/C3, material, hard to verify,
R2/R3, cross-component, concurrent, production-facing, release-related, or public.
Report `Confirmed facts / Current impact / Not executed / Risk / Options / Required
approval / Rollback`.
