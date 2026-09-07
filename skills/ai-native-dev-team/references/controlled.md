# Controlled layer

Use Controlled for material behavior or regression risk, C2/C3, R2/R3, interface,
dependency, data-shape or security-boundary changes, concurrency, production,
deployment, release, or public action.

For a material candidate that needs acceptance, read
[delivery-quality-review.md](delivery-quality-review.md). DQR records the per-task
delivery review; it is not a routing layer.

## Minimum topology and artifacts

- Keep the main agent as fact, scope, architecture-decision, routing, contract,
  permission, conflict, integration, evidence-review, stop, and acceptance owner. It
  does not duplicate the Writer's repository exploration, implementation, or test/debug loop.
- Use one path-bounded Writer on the configured lower-cost execution path and one
  independent Validator for material work.
- Add a specialist only for a concrete architecture, security, privacy, data, operations, or Owner gate.
- Freeze a bounded, independently acceptable user behavior and its interface boundary. Keep closely coupled changes to one state machine in one slice; split only for distinct authority, interface, ownership, or acceptance boundaries, not per file or UI micro-step. One file has one Writer.
- Give each Worker a task-local packet with the objective, confirmed facts, task baseline, exact allowed paths, checks, stop conditions, and rollback.
- Use only the concise contract, write lease, validation, approval, and recovery evidence the task needs.
- Use a branch or Worktree when the repository workflow or parallel ownership requires isolation.

## Capability and risk

| Complexity | Capability | Reasoning |
|---|---|---|
| C1 | Standard | Medium |
| C2 | Advanced | High |
| C3 | Frontier Writer for frozen implementation slices | Max |

Risk strengthens gates, not implementation capability. C1/R3 remains Standard/Medium
implementation with R3 authority, security, rollback, and recovery controls. C3
architecture may remain with the main agent, but frozen implementation slices go to
Writers; C3/R1 does not automatically gain production authority.

Higher-cost main-agent implementation takeover is exceptional. Allow it only when the
Writer path is unavailable or repeatedly fails with evidence, the task cannot be safely
re-sliced, the user explicitly authorizes the takeover, and the reason is recorded. An
orchestration subagent supports a cost-saving claim only when its observable runtime
mapping is to a lower-cost tier; never infer that mapping.

For R3, obtain explicit Owner approval, least-privilege and sanitized-data review, exact
candidate validation, executable rollback or recovery evidence, and stable-state
readback. A command start or static check is not acceptance.

## Validation and acceptance

### Continuous execution within the existing authorization

1. Prepare scope, interfaces, baseline, acceptance, check ownership, and rollback once.
   Refresh only changed inputs; do not repeat a proposal, audit, or contract per micro-step.
2. For behavior changes and regression fixes, use a tests-only Writer to establish RED.
   Main confirms the expected semantic failure from authentic candidate-bound evidence
   before opening the production lease. Collection, import, setup, and transport failures
   do not establish RED. If the Writer cannot run the canonical command, Main runs it.
3. Proceed directly to GREEN and the declared proportionate checks. A separate independent
   RED-fixture review is not a default gate; use it only for a concrete test contradiction,
   complex simulation, evidence gap, or explicit task requirement. Pure documentation and
   other changes exempt from behavior tests do not acquire artificial RED/GREEN gates.
4. Freeze the complete candidate for one independent final Validator and Main acceptance.
   Do not add review seats or one audit per dimension without a concrete unresolved need
   and Owner authorization. An explicit stricter task/host contract still takes precedence.
   Do not automatically invoke `/abrain` multi-seat panels. A current explicit Owner
   reduction supersedes historical seat-count requirements for that scope, without
   weakening tests, exact-candidate binding, or independence. Record that decision in
   governance, not by editing frozen product code or runtime routing profiles.
5. Reconcile completion notifications and start the next already-authorized stage in the
   same control-plane turn. A status reply is not a handoff to the user. Stop for a real
   blocker, user pause, terminal goal, or approved round limit (at most 50); never reset it to
   continue automatically. Delayed duplicate notifications do not reopen accepted work.

One five-minute watchdog owner covers active Writers/Validators; reuse it across the
batch, inspect process/CPU/output/artifact progress, and cancel on exit or authorization
pause. Do not add a heartbeat or another monitor. Completion notification and watchdog
inspection have different purposes; neither is evidence of candidate acceptance.

When Linear governs the task, maintain one clear Current Frontier (candidate, stage,
remaining blocker, next authorized action). Update it at meaningful stage transitions,
and retain milestone/decision/failure receipts as history. Routine watchdog observations
belong in brief user receipts, not repetitive Linear comments. Explicit machine gates
requiring a RED checkpoint and readback still apply; compact existing records rather
than removing an authority gate. An Obsidian summary is not a second live task ledger.

Follow DQR for a material acceptance: the Writer self-checks the scoped candidate, the
independent Validator reads the exact candidate without silently fixing it, and the main
agent accepts only after reviewing identity, permissions, findings, limitations,
rollback, and integration. Reuse evidence only while Commit/tree, environment
fingerprint, lockfiles, test entry points, permissions, generated inputs, and relevant
external dependencies remain unchanged. Rerun affected checks after a relevant change,
merge resolution, or incomplete prior evidence.

Treat release, deployment, and publication as Controlled/R3. They require explicit
Owner authority and do not become accepted merely because local development is complete.

Stop when authority, task baseline, interface, scope, evidence, or recovery conflicts;
when secrets or unexpected real data appear; or when a gate cannot be tied to the exact
candidate. Reopen a frozen Writer lease explicitly for fixes and preserve failed
candidates in Git history.
