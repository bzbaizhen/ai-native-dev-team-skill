# AI-Native Dev Team Skill

**Bootstrap the smallest AI software team that can ship safely — with explicit ownership, independent validation, version-bound evidence, and recovery built in.**

![More agents does not equal a team: approval-gated AI-native delivery](docs/images/ai-native-dev-team-hero.png)

[中文说明](#中文说明) · [Install](#install) · [How it works](#how-it-works) · [Why this is different](#why-this-is-different)

## The problem

Most multi-agent demos optimize for the number of agents running at once. Real software delivery fails elsewhere:

- nobody owns the final decision;
- two agents edit the same file;
- QA validates a different commit;
- a prototype inherits production-scale ceremony;
- a push is mistaken for a recoverable backup;
- planned work is reported as completed work.

This Skill treats the main agent as a control plane and specialist agents as temporary, permission-bounded execution units. It asks one question first: **what is the smallest team and process justified by this project's complexity and risk?**

## What it provides

- proposal-first team initialization;
- separate `C0-C3` complexity and `R0-R3` risk classification;
- business owner, producer/main agent, implementer, validator, and optional specialist boundaries;
- one-owner-per-file and task-scoped write leases;
- contract-first parallelism with branch/worktree/PR isolation;
- independent task review and exact-commit evidence;
- explicit stop, approval, rollback, backup, and recovery rules;
- reusable project charter, task contract, and evidence manifest templates;
- audit and team-resizing modes for existing projects.

## Install

Ask Codex to install the Skill from this repository:

```text
$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/bootstrap-ai-native-dev-team
```

Or copy `skills/bootstrap-ai-native-dev-team` into a supported user or repository Skill directory.

For consistent automatic use across projects, add the compact rule in [`examples/global-agents-snippet.md`](examples/global-agents-snippet.md) to your global `AGENTS.md`. The global rule triggers the workflow; the Skill holds the detailed procedure so ordinary tasks stay lightweight.

## Use

Explicit invocation:

```text
Use $bootstrap-ai-native-dev-team to propose the smallest safe AI-native development team for this repository. Do not modify files yet.
```

Other examples:

- “Initialize this MVP with the minimum useful AI development team.”
- “Can the frontend and backend agents work in parallel safely?”
- “Audit our current agent team, worktrees, QA gates, and recovery plan.”
- “Resize the team now that this project is preparing for production.”

The default mode is `proposal`: no agents, branches, worktrees, or governance files are created until the applicable scope is approved.

## How it works

![Inspect, classify, propose, approve, execute, and verify the exact commit](docs/images/bootstrap-workflow.png)

```text
inspect primary evidence
        ↓
confirmed facts / inferences / to verify
        ↓
complexity C0-C3 + risk R0-R3
        ↓
smallest sufficient team topology
        ↓
ownership + contracts + approvals + rollback
        ↓
approval-ready proposal
        ↓ approved scope only
initialize → implement → independent validation → acceptance → recovery record
```

See [`examples/sample-proposal.md`](examples/sample-proposal.md) for a compact output.

## Why this is different

This project combines useful patterns found in mature agent-development projects, then adds a governance layer for traceability and recovery:

- [obra/superpowers](https://github.com/obra/superpowers): task-scoped subagent development, worktrees, review loops, and verification before completion.
- [wshobson/agents](https://github.com/wshobson/agents): team-composition patterns, task coordination, file ownership, and parallel feature development.
- [github/awesome-copilot](https://github.com/github/awesome-copilot): producer, developer, and optional QA role separation.

The workflow in this repository is independently authored. Its additional focus includes proposal-first authorization, separate complexity/risk routing, business-owner authority, write leases, immutable evidence, native-environment boundaries, backup semantics, and recovery drills.

It deliberately does **not** create a fixed eight-agent pipeline. Roles are capabilities activated by real work, not permanent headcount.

## Repository layout

```text
skills/bootstrap-ai-native-dev-team/
├── SKILL.md
├── agents/openai.yaml
├── references/team-governance-template.zh-CN.md
└── assets/
    ├── team-bootstrap-proposal.md
    ├── project-team-charter.md
    ├── task-contract.md
    └── evidence-manifest.yaml
```

`docs/images/social-preview.png` is the candidate asset for this repository's GitHub Social Preview; committing it does not change the repository setting.

## Validation

![Version 0.1.0 verification evidence](docs/images/verification-evidence.svg)

```bash
python tests/validate_skill.py
```

The repository includes a GitHub Actions workflow for the same structural checks.

## 中文说明

这个 Skill 用于为软件项目组建、调整或审核一支 **按任务启用、权限受限、证据可追溯** 的 AI Native 开发团队。

它不是简单地“多开几个 Agent”，而是先检查项目事实，分别评估复杂度和风险，再决定是否需要主线程单独完成、单开发者、独立 QA，或多个隔离执行者。默认先生成待审核方案，得到授权后才创建 Agent、分支、Worktree 或项目治理文件。

核心目标只有三个：

1. 更快地产出通过验收的用户价值；
2. 准确知道每个结论对应哪份代码和证据；
3. 出错或环境中断时能够安全回退并恢复。

## Status

Version `0.1.0` is the first public baseline. Real-project feedback and focused pull requests are welcome.

## License

[MIT](LICENSE)
