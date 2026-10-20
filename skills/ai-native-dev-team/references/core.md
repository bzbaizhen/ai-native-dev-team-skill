# Core layer

Use Core for C0/C1, R0/R1 work when there is no material behavior, interface,
dependency, data, security, concurrency, production, release, or public-action trigger.

## Execute lightly

1. Inspect the smallest fact set needed to act.
2. 当子任务边界和验收清楚、交接成本可控，并具有具体的并行推进或已确认的模型承接价值时，默认轻量委派；无需先证明明显净收益。简单修改、强耦合工作和明显不值得交接的任务直接执行。复杂度标签、文件数量和模块数量本身不构成委派理由。
3. 默认从一个子 Agent 开始，有更多独立工作时再增加。使用已配置且宿主可用的路由；共享决策和紧密耦合的修改保持在一起。
4. 简单委派使用简短任务说明，包含目标、必要上下文、允许修改的路径和完成检查；停止条件及恢复方式仅在相关时补充。
5. Run relevant checks and let the main agent review and accept the result. Inspect trustworthy candidate-bound command/log/exit evidence instead of duplicating an unchanged successful run; missing evidence requires only the missing check. Do not introduce DQR or a separate audit for a non-material documentation edit.
6. Do not create a standing team, charter, Worktree, lease, or evidence folder solely because delegation is available. Existing project isolation requirements still apply.

| Work | Capability | Reasoning |
|---|---|---|
| C0 main-agent micro task | Main agent | Current |
| C0 delegated batch | Economy | Low |
| C1 | Standard | Medium |

Risk does not raise implementation capability. Move to [Controlled](controlled.md) when
R2/R3, material behavior, difficult verification, concurrency, or a boundary change
appears.

Core does not load a DQR acceptance packet. When a material candidate needs acceptance,
move to Controlled and use its [DQR protocol](delivery-quality-review.md).

The main agent remains the control plane for scope, architecture decisions, contracts,
permissions, integration, evidence review, stop decisions, and acceptance. It avoids
repeating the Writer's work supported by reliable evidence; necessary independent review is preserved. C3
architecture may remain with the main agent, and delegates frozen implementation slices when the delegation conditions in SKILL.md hold.

Main-agent takeover within existing scope is allowed when it is the better remaining path. End the prior write lease first; preserve required checks and avoid duplicate work. A cost-saving claim needs an observable lower-cost runtime mapping, not just an agent label.

Necessary validation must not be reduced to manufacture delegation value.

## Stop and escalate

Stop Core work and re-score when the task becomes C2/C3, material, hard to verify,
R2/R3, cross-component, concurrent, production-facing, release-related, or public.
Report `Confirmed facts / Current impact / Not executed / Risk / Options / Required
approval / Rollback`.
