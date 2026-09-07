# Routing, complexity, risk, and topology

Use this reference only in the main control plane. Do not send it to ordinary Workers.

## Score complexity and risk independently

| Level | Evidence | Capability and reasoning |
|---|---|---|
| C0 | Query, tiny edit, deterministic transform, or mechanical batch | Main agent/Current only for strict micro work; Economy/Low Writer for a batch |
| C1 | Narrow scope, known path, and easy verification | Standard/Medium |
| C2 | Cross-file or cross-module work, meaningful design choice, or uncertain integration | Advanced/High |
| C3 | Architecture, cross-system change, unknown root cause, or difficult migration | Frontier/Max Writer for frozen implementation slices; main agent may retain architecture |

Split mixed objectives before escalating capability. A larger model is not a substitute
for a clear task boundary.

| Risk | Evidence | Minimum gate |
|---|---|---|
| R0 | Read-only and no side effects | Main-agent scope check |
| R1 | Ordinary reversible project change | Relevant tests and main-agent review |
| R2 | Interface, dependency, data shape, security boundary, or material regression risk | Independent exact-candidate validation and executable rollback |
| R3 | Production, credentials, compliance, public action, real data, irreversible work, deletion, or paid resource | Owner approval, relevant specialist gate, exact validation, and rollback/recovery evidence |

Risk changes gates, not implementation capability. A one-line authentication change can
be C1/R3; a difficult pure refactor can be C3/R1.

## Select Core or Controlled

```text
controlled_trigger = material behavior OR C2/C3 OR R2/R3 OR
                     interface/dependency/data/security change OR concurrency OR
                     production/deployment/release/public action

if controlled_trigger:
    layer = Controlled
else:
    layer = Core
```

Resolve missing material facts before choosing Core. Ordinary release, deployment, and
publication are Controlled/R3.

For a material Controlled candidate that needs acceptance, load
[delivery-quality-review.md](delivery-quality-review.md). It is a per-task protocol
after routing, not a routing layer.

## Choose the smallest topology

1. `no-delegation` only for read-only control-plane work or one tiny deterministic,
   low-risk, single-file C0 edit with no material behavior, interface, dependency, data,
   security, concurrency, production, or public effect; no debugging loop or test
   authoring; and exactly one deterministic verification. Missing or uncertain evidence
   fails closed to delegation.
2. `single-worker` for every C0 mechanical batch and every non-material C1+
   implementation, refactor, bug fix, test-writing, or debugging slice.
3. `task-cell` for material behavior or meaningful regression risk: one Writer and one independent Validator.
4. `team-required` only for independent contract-frozen slices, multiple repositories, or concrete specialist gates.

Core creates no mandatory governance artifact. Controlled uses only the material
contract, path lease, validation, approval, and recovery evidence the task needs.

One file has one Writer at a time. Do not open another Writer while work is at
`DEV_COMPLETE`, `QA_PENDING`, or `MERGE_READY` unless the main agent records a
reason and validation capacity is available.

## Windows unattended Coding CLI transport and completion

The following transport defaults apply only when the active host/operator contract does
not mandate a transport. A mandated PTY remains PTY; do not switch to pipe for convenience.
On Hermes, reuse `coding-cli-process-lifecycle` for watchdog and exact-process recovery;
on other hosts use the equivalent host lifecycle procedure. Do not introduce a second
monitor. Preserve actual natural-exit versus forced-cleanup status; cleanup is not a
successful normal exit and does not replace candidate verification.

For unattended non-interactive Coding CLI exec, Writer, or Validator invocations on
Windows that may perform bounded long work, use `pty=false`, `background=true`, and
`notify_on_complete=true` by default. `pty=true` is reserved for an interactive TUI,
login, or a command that genuinely requires terminal input; never apply it
unconditionally to unattended exec.

Treat the runtime process registry as the completion authority. Final output text, a
final-answer marker, or a tokens-used line is not process-exit evidence. Accept
completion only after a fresh status inspection reports registry status `exited` and
captures the exit code.

For a legacy PTY run that printed a final marker but remains alive, perform one short
bounded grace check, then inspect fresh process status. If it is still alive, terminate
only the exact tracked process. Never start a duplicate Writer and never repeatedly
wait/reconnect. Preserve its output and captured exit evidence with the exact-candidate
validation record.

## Cost-aware capability routing

| Work | Capability | Reasoning | Escalate when |
|---|---|---|---|
| Strict C0 micro work | Main agent | Current | Delegate if any eligibility condition is absent or uncertain |
| C0 deterministic batch | Economy | Low | Ambiguity, exceptions, or failed deterministic checks |
| C1 | Standard | Medium | Repeated failure, hidden dependency, or inadequate verification |
| C2 | Advanced | High | Architecture or root cause remains unresolved |
| C3 implementation slice | Frontier | Max | Re-slice, use a declared fallback, or stop if the Writer path fails |

A project maps these vendor-neutral tiers to currently available models and one declared
fallback. Optimize for the expected total cost of an accepted result, including likely
rework and validation, not the cheapest single call. Never claim a model was used when
the runtime did not expose it.

The main agent owns scope, architecture decisions, contracts, permissions, integration,
evidence review, stop decisions, and final acceptance; it does not duplicate the
Writer's repository exploration, implementation, or test/debug loop. C3 architecture
may stay in the control plane, but frozen implementation slices go to Writers.

Higher-cost main-agent implementation takeover requires all of: the Writer path is
unavailable or repeatedly failed with evidence; safe re-slicing is impossible; the user
explicitly authorizes the takeover; and the reason is recorded. Otherwise use a declared
fallback or stop. An orchestration subagent supports a cost-saving claim only when its
observable runtime mapping is to a lower-cost tier; never infer that mapping.

## Delegation packet

Give a delegated agent only the task-local packet:

- objective and user value;
- confirmed facts, task baseline Commit, repository, native environment, and allowed paths;
- frozen interface or an explicit prohibition on interface changes;
- exact read/write ownership and integration order;
- selected capability/reasoning tier;
- required checks, immutable candidate identity, stop conditions, and rollback.

Workers do not decide the team design, expand scope, or reload the whole project context.
The main agent verifies their handoff, diff, tests, and path boundary.

## Evidence reuse and rerun triggers

Carry validation evidence forward only while these remain unchanged:

- candidate Commit/tree and any history-sensitive behavior;
- repository-host-toolchain environment fingerprint;
- lockfiles and test entry points;
- permissions;
- generated inputs;
- relevant external dependencies.

Rerun affected checks when any relevant input changes, merge resolution occurs,
repository policy requires it, or earlier evidence is incomplete or failed.
