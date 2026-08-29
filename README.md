# AI Native Dev Team Suite

[English](README.md) | [简体中文](README.zh-CN.md)

**A control-plane Skill for developers who want Coding Agents to change a repository with explicit ownership, independent evidence, and recoverable delivery.**

It is for developers and technical leads using Codex, Hermes Agent, or a manually installed compatible agent. Generic multi-agent orchestration starts with a roster; this Skill starts with the task: inspect the facts, choose the smallest topology, and bind work and evidence to an allowed path and an exact candidate.

The suite has a governance Core/Entry Skill and an optional Routing Extension. The Core
remains useful without the Router; the Extension supplies a separate project-local route
contract when a host mapping is needed.

Released: [v2.1.0](https://github.com/bzbaizhen/ai-native-dev-team-skill/releases/tag/v2.1.0)

## In brief

| Concern | Rule |
|---|---|
| Control plane | The main agent owns facts, scope, contracts, routing, permissions, integration, evidence review, stop decisions, and final acceptance. |
| Implementation and validation | A task- and path-bounded Writer edits the frozen scope. An independent Validator reads the exact candidate without silently fixing it. Delivery Quality Review (DQR) is the per-task acceptance protocol inside Controlled. |
| Active layers | Core and Controlled are the only layers. DQR is not a third layer. |
| Routing | Complexity `C0-C3` selects decomposition, capability, and reasoning. Risk `R0-R3` selects authority, review, approval, rollback, and recovery gates. |
| Linear isolation | A Linear-governed issue uses its exact issue branch, accepted base, and canonical Git worktree before Writer dispatch; shared roots are not a substitute. |
| Recovery | Checks and acceptance name an immutable candidate. Rollback and recovery stay executable for that candidate. |
| Measurements | Local prospective metrics are optional, main-agent-only, and descriptive. Missing observations remain `null` or `unknown`; metrics do not decide acceptance. |

![More agents do not automatically make a team](docs/images/ai-native-dev-team-hero.png)

[Install](#install) · [60-second Quick Start](#60-second-quick-start) · [Workflow](#workflow) · [Boundaries](#boundaries-and-evidence)

## Why it exists

This Skill grew out of a real multi-agent project where every automated check was green:

```text
Backend: 39/39
Frontend: 8/8
TypeScript: 0 diagnostics
Target WeChat runtime: blank screen, 9 errors
```

The project had frontend, backend, and QA agents, but its delivery system was underspecified: the authoritative contract, writable paths, tested Commit, and stop rule for insufficient evidence were unclear. The useful correction was to make those boundaries explicit and add an independent acceptance path.

## Install

| Component | Host | Install | Notes |
|---|---|---|---|
| Core/Entry — `ai-native-dev-team` | Codex | `$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/ai-native-dev-team` | Governance and delivery controls. |
| Routing Extension — `ai-native-model-router` | Codex | `$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/ai-native-model-router` | Optional project-local route contract. |
| Core/Entry — `ai-native-dev-team` | Hermes Agent | Copy the complete `skills/ai-native-dev-team/` directory into `$HERMES_HOME/skills/`. | Keep references, assets, and scripts together. |
| Routing Extension — `ai-native-model-router` | Hermes Agent | Copy the complete `skills/ai-native-model-router/` directory into `$HERMES_HOME/skills/`. | Install separately when routing is needed. |
| Core/Entry — `ai-native-dev-team` | Manual compatible agent | Copy the complete [`skills/ai-native-dev-team/`](skills/ai-native-dev-team/) directory into the supported Skill location. | Copying only `SKILL.md` is incomplete. |
| Routing Extension — `ai-native-model-router` | Manual compatible agent | Copy the complete [`skills/ai-native-model-router/`](skills/ai-native-model-router/) directory into the supported Skill location. | The Extension is independently optional. |

## 60-second Quick Start

Install the Skill, then use one of these short prompts:

```text
Use $ai-native-dev-team. Inspect this repository and task, separate confirmed facts, inferences, and items to verify, and propose the smallest safe topology. Do not modify files yet.
```

```text
Implement the accepted task. Freeze the contract and file ownership first; give each Writer only its allowed path, use an independent Validator for material work, and bind every check to the exact candidate.
```

```text
Prepare this project for release. Re-score complexity and risk, verify the exact candidate, rollback and recovery, and Owner approval. Release actions remain separately authorized.
```

## Core concepts

### Main agent as the control plane

The main agent keeps the project context and makes the control-plane decisions. It does not repeat a Writer's repository exploration, implementation, or test/debug loop. A strict C0 micro edit may stay with the main agent only when it is tiny, deterministic, low-risk, single-file, and needs one deterministic verification; uncertainty sends the work to a task-scoped Writer.

### One Writer, one path, independent validation

Material work uses one Writer with an exact path lease and one independent Validator. The Validator reads the candidate in a clean or controlled state, records findings against the contract and candidate identity, and does not silently fix product code. If a fix changes the candidate, affected evidence is invalidated and the checks run again.

For a material Controlled candidate, DQR records the frozen contract, lease, exact candidate, independent findings, revalidation, limitations, acceptance, and rollback or recovery. It remains inside Controlled.

### Complexity and risk are separate axes

| Axis | Selects |
|---|---|
| Complexity `C0-C3` | Task decomposition, context preparation, model capability, and reasoning. |
| Risk `R0-R3` | Permissions, independent review, approval, rollback, and recovery. |

Risk changes the gates, not the implementation capability. A difficult refactor can need stronger reasoning without gaining production authority; a small production permission change can need Owner approval and strong rollback evidence.

The active layers are deliberately limited:

| Layer | Default use |
|---|---|
| **Core** | Non-material C0/C1 and R0/R1 work. |
| **Controlled** | Material behavior, C2/C3, R2/R3, interface or dependency changes, concurrency, production, release, or public action. |

Controlled adds only the contract, ownership, validation, approval, and recovery evidence that the task needs. Release, deployment, and publication are Controlled/R3 and remain Owner-gated.

### Linear Git isolation

For a Linear-governed issue, read back the issue identity, status, blocker, exact `gitBranchName`, accepted base ref and Commit, and canonical worktree before dispatch. Run the Skill's isolation helper from the repository environment. A mismatch in issue, branch, base, repository, worktree, or checkpoint is a stop condition; do not make an ambiguous state fit by resetting, replacing, or reusing a shared root.

### Rollback and recovery

Git history, a remote copy, rollback, recovery, integration, installation, and release are separate states. Acceptance means that the main agent accepted evidence for the exact verified candidate; it does not authorize integration, installation, push, merge, deployment, or publication. Keep an executable rollback or recovery method with the candidate and preserve known limitations.

### Optional measurements

The main agent may explicitly select a local prospective ledger for a task set. It records observed lifecycle facts only. Writers and Validators provide handoff facts; they do not append the ledger. The resulting audit and comparison are descriptive and cannot replace independent validation, DQR, acceptance authority, or a project decision.

## Workflow

![Inspect, classify, propose, approve, execute, and verify the exact candidate](docs/images/ai-native-dev-team-workflow.png)

1. Inspect the repository, task baseline, contracts, permissions, test entry points, integration backlog, rollback, and recovery.
2. Separate confirmed facts, inferences, and items to verify. Score complexity and risk independently.
3. Select Core or Controlled, then choose no delegation, one Writer, a Writer-Validator cell, or a larger team only when the work requires it.
4. Freeze the smallest useful contract, allowed paths, interface, candidate identity, checks, authority limits, and rollback. For Linear issues, establish the isolated branch and worktree before Writer dispatch.
5. Execute within the standing authorization envelope for ordinary reversible work. If the user asked only for a plan, scope is unbounded, or a real authority boundary exists, stop at proposal-only.
6. Validate the exact candidate independently, review limitations and recovery, and accept only with the required authority. Integration, installation, release, and publication each need their own authorization and readback.

## When not to use

- A read-only question or a strict, deterministic, low-risk, single-file C0 edit can stay with the main agent.
- A task with no repository change does not need a team topology or file lease.
- If the repository root, task baseline, authoritative contract, allowed path, or authority boundary cannot be confirmed, stay in proposal-only or stop until it is resolved.
- Do not expect this Skill to grant credentials or permission for production, destructive, irreversible, release, or public actions. Those actions remain separately authorized.

## Boundaries and evidence

This Skill is a workflow, not the source of truth for a product, task, contract, or release. Keep `Confirmed facts / Inferences / To verify` distinct, and report missing evidence instead of filling it in.

Designed, written, run, verified, accepted, integrated, installed, and released are separate states. A command start, green static check, or Push is not acceptance. Runtime, external, platform, visual, and recovery checks that were not run remain limitations.

The backend/frontend/TypeScript checks in the origin story do not prove the target runtime. Exact-candidate validation and recovery remain part of the active workflow. Public, release, destructive, credential, real-data, and production actions remain separately authorized; optional metrics never become a go/no-go threshold.

## Global rule and Skill

| Layer | Responsibility |
|---|---|
| Global `AGENTS.md` | Decide when this Skill should trigger and retain a few hard boundaries. |
| `ai-native-dev-team` | Inspect, classify, propose, initialize, and adjust. |
| Project sources of truth | Store the actual product, task, contract, decision, risk, and version evidence. |

The compact global trigger is available in [examples/global-agents-snippet.md](examples/global-agents-snippet.md).

## Deeper references

- [Team Skill entrypoint](skills/ai-native-dev-team/SKILL.md): authority, selection, and execution lifecycle. On Windows, unattended Writers default to `pty=false`, `background=true`, and `notify_on_complete=true`; reserve `pty=true` for interactive input, and accept completion only when the process registry reports `exited`, without duplicate Writers or repeated `wait/reconnect`.
- [Team routing and topologies](skills/ai-native-dev-team/references/routing-and-topologies.md): full complexity/risk gates, topology, capability routing, and evidence reuse.
- [Core layer](skills/ai-native-dev-team/references/core.md) and [Controlled layer](skills/ai-native-dev-team/references/controlled.md): layer-specific rules.
- [Linear Git isolation](skills/ai-native-dev-team/references/git-isolation-bootstrap.md): identity, base, branch, worktree, checkpoint, and blocker gates.
- [Delivery Quality Review](skills/ai-native-dev-team/references/delivery-quality-review.md): the per-task acceptance protocol inside Controlled.
- [Model Router entrypoint](skills/ai-native-model-router/SKILL.md): optional project-local route resolution with evidence-bound fallbacks.
- [Optional metrics guide](skills/ai-native-dev-team/references/metrics.md) and [metrics event schema](skills/ai-native-dev-team/references/metrics-event.schema.json): the local ledger and its fields.
- [Release and migration history](releases/): prior release records and historical boundaries.

## Repository map

```text
skills/ai-native-dev-team/
├── SKILL.md              # entrypoint
├── references/           # routing, layers, isolation, DQR, metrics, and governance
├── scripts/              # Git isolation and optional metrics helpers
└── assets/               # proposal, contract, and team templates
```

## Validation

```bash
python tests/validate_skill.py
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

The repository includes a GitHub Actions workflow for the Python checks.

## V2 migration boundary

### Release

This landing page describes the active `v2.1.0` line. The [GitHub release](https://github.com/bzbaizhen/ai-native-dev-team-skill/releases/tag/v2.1.0) is the release record.

### Migration history

Historical migration and release notes live in [release history](releases/). Repository-external channels and any publication decision remain separate Owner decisions.

## References and acknowledgements

This project learned from useful patterns in:

- [obra/superpowers](https://github.com/obra/superpowers)
- [wshobson/agents](https://github.com/wshobson/agents)
- [github/awesome-copilot](https://github.com/github/awesome-copilot)

The workflow is independently authored, with additional emphasis on bounded execution authority, proposal-only conditions, C/R separation, complexity-aware, cost-conscious routing, path ownership, exact-version evidence, native environments, rollback, and recovery.

The English launch post and development visuals are available on [X](https://x.com/Bzbaizhen/status/2087828830627205527).

## License

[MIT](LICENSE)
