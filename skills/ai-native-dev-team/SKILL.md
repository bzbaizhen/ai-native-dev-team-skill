---
name: ai-native-dev-team
description: "开发任务出现边界清楚、可独立验收的子任务，且具备并行推进、合适模型承接或必要独立验证价值时，优先进行轻量委派；简单修改和强耦合工作直接执行。"
version: 3.1.0
author: bzbaizhen, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    related_skills: [ai-native-model-router]
    tags: [team-governance, proportional-controls, route-slots]
---

# AI Native Dev Team

在初步探索后或发现新的独立工作分支时，检查委派机会。子任务目标、上下文、写入边界和验收方式清楚，且具有具体的并行推进、合适模型承接或必要独立验证价值时，默认采用轻量委派。

无需事先量化或证明明显净收益，但应考虑交接、等待、整合和验证成本。默认从一个子 Agent 开始；不按文件数量、模块数量或固定比例强制分发。简单修改、强耦合工作及明显不值得交接的任务由主 Agent 执行。

如以成本优势作为理由，必须确认实际模型映射及适用的费用依据；未经验证时只陈述预期价值，不声称已节省时间或费用。

对收益仍不确定、但边界清楚且交接成本低的任务，可委派一个可独立验收的小任务试行；不存在合适子任务或主 Agent 已接近完成时直接执行。成本价值已确认时，不要求主 Agent 同时有其他工作。委派受宿主能力和更高优先级约束限制。

## Scope and responsibility

The main agent owns scope, architecture decisions, authorization, integration and final acceptance. Give each delegate a bounded objective, inputs, allowed paths and completion checks. One file has one writer at a time; avoid repeating delegated work supported by reliable evidence; necessary independent review is not wasteful duplication.

Existing authorization covers ordinary reversible work in the requested scope. Continue through the required implementation and verification. A topology change or main-agent takeover does not itself require another approval; settle write ownership first and preserve validation independence where required. External actions and actual permission boundaries still follow the user's authority.

## Select only the needed controls

识别委派机会不需要预先加载全部引用资料。决定委派后，仅加载当前任务所需的控制层和路由资料。日常委派说明保持简短，指出子任务及其价值即可。

- For simple delegated work without material behavior or boundary changes, read [core.md](references/core.md).
- For material behavior, difficult integration, data/interface/security changes or R2/R3 work, read [controlled.md](references/controlled.md). Necessary validation is not removed to manufacture a cost advantage.
- For complexity/risk scoring, topology, evidence reuse or Windows unattended CLI lifecycle, read the relevant section of [routing-and-topologies.md](references/routing-and-topologies.md).
- For material candidate acceptance, use [delivery-quality-review.md](references/delivery-quality-review.md). Bind findings to the exact candidate; a later edit invalidates affected evidence.
- For Linear-governed implementation or an explicit isolation request, read [git-isolation-bootstrap.md](references/git-isolation-bootstrap.md) before writer dispatch.
- When selecting delegate models, use the available `ai-native-model-router` with the user's configured profile and API version. A route decision is not execution; verify host support and actual invocation. Missing mapping stays unknown or host-inherited.
- Only for requested prospective measurements, read [metrics.md](references/metrics.md); missing observations remain null/unknown.

Do not create a standing team, charter or recurring monitor merely because delegation is available. Inspect current scoped facts; do not preload the whole repository or every reference. When delegation no longer offers concrete value, the main agent may finish the remaining authorized work while preserving candidate checks and avoiding simultaneous writers.

## Conditional assets

- Explicit team proposal: [team-bootstrap-proposal.md](assets/team-bootstrap-proposal.md).
- Controlled work needing a durable contract or frozen interface: [task-contract.md](assets/task-contract.md).
- Explicit long-lived team setup: [project-team-charter.md](assets/project-team-charter.md).

Report the accepted result, relevant evidence and any unresolved blocker. Pause only the affected work when scope, authority, baseline, interface or evidence conflicts cannot be resolved; keep unrelated authorized work moving.
