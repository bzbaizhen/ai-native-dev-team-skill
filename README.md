# AI-Native Development Team Skill

[English](README.md) | [简体中文](README.zh-CN.md)

**Decide whether the work needs a team, then bootstrap the smallest team that can ship it safely.**

This Skill gives coding agents explicit file ownership, cost-aware model routing,
independent validation, exact-version evidence, approval boundaries, rollback, and
recovery—without turning every small task into a ceremony.

![More agents do not automatically make a team](docs/images/ai-native-dev-team-hero.png)

[Install](#install) · [Use](#use) · [Model routing](#route-models-by-complexity-not-risk) · [Development layers](#two-development-layers) · [Global rule + Skill](#why-use-both-a-global-rule-and-a-skill)

## Why I built it

This Skill grew out of a multi-agent project where every automated check was green:

```text
Backend: 39/39
Frontend: 8/8
TypeScript: 0 diagnostics
Target WeChat runtime: blank screen, 9 errors
```

We had frontend, backend, and QA agents. What we did not have was a delivery system:
which contract was authoritative, who could edit which path, which Commit QA had
actually tested, and who would stop the work when the evidence was insufficient.

The fix was not “more agents.” It was a smaller team with explicit boundaries and an
independent acceptance path.

## What it solves

| Failure mode | Default response |
|---|---|
| A full role roster is created before the task is understood | Inspect first; enable only roles with real work |
| Every micro task carries the whole governance manual | Keep small C0/C1 work in Core |
| Frontend and backend start before the interface is stable | Freeze the minimum contract before parallel work |
| Two agents edit the same file | Give each path one Writer at a time |
| QA fixes the code it is accepting | Separate implementation from independent validation |
| “Tests passed” but the tested version is unclear | Bind evidence to the exact candidate Commit |
| A risky one-line change gets the same process as a hard refactor | Score complexity and risk independently |
| Every task uses the most expensive model | Route capability and reasoning by complexity |
| A Push is mistaken for recoverability | Separate Git history, remote copy, rollback, and recovery |

## Core principles

1. **Smallest sufficient team** — roles are task-scoped capabilities, not a permanent roster.
2. **Proposal first** — inspect and propose before creating agents, branches, Worktrees, or governance files.
3. **Complexity and risk are separate** — complexity selects model capability and reasoning; risk selects authority and gates.
4. **One path, one Writer** — shared files have one write owner at a time.
5. **Contract before concurrency** — freeze interfaces, dependencies, integration order, and acceptance criteria before parallel implementation.
6. **Validate the exact version** — developer checks, automated checks, independent QA, and Owner approval are different evidence.
7. **Stop safely** — pause when scope, permissions, task baseline, evidence, or rollback no longer matches the contract.

## Install

Ask Codex to install the Skill from this repository:

```text
$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/bootstrap-ai-native-dev-team
```

Or copy `skills/bootstrap-ai-native-dev-team` into a supported user or project Skill
directory.

Explicit invocation:

```text
Use $bootstrap-ai-native-dev-team. Propose the smallest safe development team for this repository. Do not modify files yet.
```

## Use

```text
Initialize the smallest sufficient team for this MVP. Give me the proposal first.
```

```text
The frontend and backend may work in parallel. Check the contract source and file ownership before creating agents.
```

```text
Adjust the current team: integration is waiting and two Writers overlap.
```

```text
Prepare this project for release. Re-score risk, validation, Owner approval, rollback, and recovery.
```

## Three modes

| Mode | Purpose | Default write behavior |
|---|---|---|
| `proposal` | Design the minimum team and gates | Read-only inspection; return a proposal |
| `initialize` | Create an approved team structure | Write only approved, reversible project artifacts |
| `adjust` | Correct an existing team or task topology | Preserve confirmed facts; apply only the approved adjustment |

None of these modes grants production, credentials, real data, paid resources, public
publication, irreversible migration, or deletion authority.

## Workflow

![Inspect, classify, propose, approve, execute, and verify the exact Commit](docs/images/bootstrap-workflow.png)

```text
Inspect project facts
        ↓
Confirmed facts / Inferences / To verify
        ↓
Complexity C0-C3 + Risk R0-R3
        ↓
Core or Controlled
        ↓
No delegation / one Worker / Writer-Validator cell / team
        ↓
Capability + reasoning tier
        ↓
File owner + contract + approval + rollback
        ↓
Proposal
        ↓ approved scope only
Execute → independent validation → acceptance → recovery record
```

## Route models by complexity, not risk

| Signal | Controls |
|---|---|
| Complexity `C0-C3` | Task decomposition, context preparation, model capability, and reasoning |
| Risk `R0-R3` | Permissions, independent review, approval, rollback, and recovery |
| Runtime availability | Current model mapping, one declared fallback, main-agent takeover, or stop |
| Verification difficulty | Whether to split further, escalate capability, or add an independent gate |

The goal is not the cheapest call. It is the lowest expected total cost of an accepted
result:

```text
accepted-result cost = first execution + likely retries/rework + validation + coordination
```

A `C1/R3` production permission change may use Standard/Medium implementation while
requiring Owner approval and strong rollback evidence. A `C3/R1` pure refactor may
need Frontier/Max reasoning without production authority.

The main agent remains the high-context information hub. Keep C0/R0 micro work there.
Delegate a deterministic C0 batch only when handoff has net value.

## Two development layers

| Layer | Default use |
|---|---|
| **Core** | Non-material C0/C1 and R0/R1 work |
| **Controlled** | Material behavior, C2/C3, R2/R3, boundaries, concurrency, production, release, or public action |

Controlled does not mean “maximum process.” It means adding only the contract,
ownership, independent validation, approvals, and recovery evidence justified by the
task. Release, deployment, and publication are Controlled/R3 and remain Owner-gated.

## Minimum team selection

| Situation | Default topology |
|---|---|
| Tiny, clear, low-risk work | Main agent only |
| Isolated, easy-to-verify slice | One Worker plus main-agent review |
| Material behavior or regression risk | One Writer plus one independent Validator |
| Independent slices with a frozen contract | Path-isolated Writers plus independent validation |
| Security, privacy, production, migration, or release risk | Relevant specialist, independent gate, and Owner approval |

Agent count, Commit count, lines of code, and token count are not delivery outcomes.

## What this Skill deliberately excludes

Team-performance review, historical baseline construction, delivery telemetry,
efficiency comparison, task sampling, registration receipts, and external timestamp
proof are separate systems. V2 does not collect them during development and does not
ship compatibility aliases for the removed interfaces.

The Skill still keeps a **task baseline Commit**, exact-candidate validation, rollback,
and recovery. Those protect code changes; they are not performance-measurement features.

## Why use both a global rule and a Skill

| Layer | Responsibility |
|---|---|
| Global `AGENTS.md` | Decide when this Skill should trigger and retain a few hard boundaries |
| `bootstrap-ai-native-dev-team` | Inspect, classify, propose, initialize, and adjust |
| Project sources of truth | Store the actual product, tasks, contracts, decisions, risks, and version evidence |

A compact global trigger is available in
[examples/global-agents-snippet.md](examples/global-agents-snippet.md).

## Repository layout

```text
skills/bootstrap-ai-native-dev-team/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── routing-and-topologies.md
│   ├── core.md
│   ├── controlled.md
│   └── governance-*.md
└── assets/
    ├── team-bootstrap-proposal.md
    ├── project-team-charter.md
    ├── task-contract.md
    └── evidence-manifest.yaml
```

## Validation

```bash
python tests/validate_skill.py
python -m unittest discover -s tests -p "test_*.py" -v
```

The repository includes a GitHub Actions workflow for the same checks.

## V2 migration boundary

The prior development line contained Release Audit, prospective metrics, historical
baseline comparison, P2/P3 proof adapters, public-receipt contracts, and benchmark
fixtures. V2 removes those from the active Skill tree. Their earlier Git history and
release notes remain available as historical evidence; no external repository is
silently deleted or rewritten.

This line is V2.0.0. The `v2.0.0` tag and GitHub Release identify the published
repository version. Installation and external channels beyond this repository remain
separate Owner decisions.

## References and acknowledgements

This project learned from useful patterns in:

- [obra/superpowers](https://github.com/obra/superpowers)
- [wshobson/agents](https://github.com/wshobson/agents)
- [github/awesome-copilot](https://github.com/github/awesome-copilot)

The workflow here is independently authored, with additional emphasis on proposal-first
authority, C/R separation, cost-aware routing, path ownership, exact-version evidence,
native environments, rollback, and recovery.

The English launch post and development visuals are available on
[X](https://x.com/Bzbaizhen/status/2087828830627205527).

## License

[MIT](LICENSE)
