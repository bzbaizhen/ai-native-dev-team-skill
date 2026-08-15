# Core layer

Use Core for C0/C1, R0/R1 work when there is no material behavior change, interface
change, dependency change, data or security boundary change, concurrency requirement,
or production/public action. Core is the default; it is not a weaker substitute for a
required Controlled gate.

## Route and execute

1. Inspect the smallest set of facts needed to act and reuse the current
   repository-host-toolchain fingerprint when it is unchanged.
2. Keep C0/R0 micro work with the main agent. Create zero agents and zero mandatory
   governance files.
3. For a deterministic C0 batch, delegate at most one Worker when handoff has net value.
   Give the Worker only a task packet with the objective, inputs, allowed paths, checks,
   stop conditions, and rollback. The Worker reports `worker_skill_loaded=false`.
4. For non-material C1/R1 work, use the main agent or one isolated Worker according to
   verification cost. Do not require a Worktree, daily ledger, or independent Validator
   unless repository policy or a newly discovered trigger requires one.
5. Run relevant deterministic or affected checks and let the main agent review and
   accept the result. Do not create a standing team, charter, lease, or evidence folder
   merely because delegation is available.

## Capability and reasoning

Use vendor-neutral tiers selected by complexity:

| Work | Capability | Reasoning |
|---|---|---|
| C0 main-agent micro task | Main agent | Current |
| C0 delegated mechanical batch | Economy | Low |
| C1 | Standard | Medium |

Risk does not raise these implementation tiers. If R2/R3 appears, or if the change is
material or difficult to verify, move to [Controlled](controlled.md) and add its gates.

## Stop and escalate

Stop Core execution and re-score when any of these appears:

- material behavior or regression risk;
- C2/C3 complexity or verification that is no longer easy;
- R2/R3 risk, including security, privacy, recovery, or permission changes;
- interface, dependency, data-shape, or security-boundary change;
- concurrent Writers, multiple components, or a frozen cross-component contract;
- production, deployment, release, or public publication.

Report `Confirmed facts / Current impact / Not executed / Risk / Options / Required
approval / Rollback` when stopping. Preserve the main agent's fact boundary and do not
silently create Controlled artifacts before the re-score.
