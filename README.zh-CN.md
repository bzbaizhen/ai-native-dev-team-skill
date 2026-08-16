# AI Native 开发团队 Skill

[English](README.md) | [简体中文](README.zh-CN.md)

**先判断这次工作是否需要组队，再创建能够安全交付的最小团队。**

这个 Skill 为 Coding Agent 补上文件所有权、具有性价比的模型路由、独立验证、
准确版本证据、审批边界、回退和恢复，同时避免让每个小任务背上完整治理流程。

![多个 Agent 不自动等于一支团队](docs/images/ai-native-dev-team-hero.png)

[安装](#安装) · [使用](#使用) · [模型路由](#按复杂度选择模型而不是按风险抬高模型) · [开发层](#两层开发控制) · [全局规则与-skill](#为什么全局规则和-skill-都要有)

## 为什么做这个 Skill

它来自一次真实的多 Agent 项目失败。当时所有自动检查都是绿色：

```text
后端：39/39
前端：8/8
TypeScript：0 diagnostics
微信目标运行时：白屏，9 errors
```

前端、后端和 QA 都有了，但团队仍没有形成交付系统：接口以什么为准，谁能修改
哪个路径，QA 验收的是哪个 Commit，证据不足时谁负责让所有人停下来，都没有说清楚。

解决方式不是继续增加 Agent，而是缩小团队、冻结边界，并建立独立验收路径。

## 它解决什么

| 常见问题 | 默认处理 |
|---|---|
| 任务尚未看清就创建完整角色池 | 先检查，只启用有真实任务的角色 |
| 每个微任务都加载整套治理手册 | 小型 C0/C1 工作留在 Core |
| 接口未冻结，前后端同时开工 | Contract 先于跨组件并行 |
| 两个 Agent 修改同一文件 | 同一时段每个路径只有一个 Writer |
| QA 顺手修改自己正在验收的代码 | 实现与独立验证分离 |
| “测试通过”但版本说不清 | 证据绑定准确候选 Commit |
| 高风险的一行改动与复杂重构混为一谈 | 复杂度和风险分别评估 |
| 所有任务都调用最贵模型 | 按复杂度选择能力与推理强度 |
| Push 被当成已经可恢复 | 区分 Git 历史、远程副本、回退和恢复 |

## 核心原则

1. **最小充分团队**：角色是按任务启用的能力，不是固定编制。
2. **Proposal first**：批准前不创建 Agent、分支、Worktree 或治理文件。
3. **复杂度与风险分开**：复杂度决定模型与推理；风险决定权限与门禁。
4. **一个路径，一个 Writer**：共享文件在同一时段只有一个写入 Owner。
5. **Contract 先于并行**：接口、依赖、集成顺序和验收标准冻结后再并行。
6. **验证准确版本**：开发自检、自动检查、独立 QA 和 Owner 批准是不同证据。
7. **能够安全停止**：范围、权限、任务基线、证据或回退不一致时停止并报告。

## 安装

让 Codex 从本仓库安装：

```text
$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/bootstrap-ai-native-dev-team
```

也可以把 `skills/bootstrap-ai-native-dev-team` 复制到 Codex 支持的用户级或
项目级 Skill 目录。

明确调用：

```text
使用 $bootstrap-ai-native-dev-team，为这个仓库提出最小且安全的开发团队方案。现在不要修改文件。
```

## 使用

```text
用最小充分团队初始化这个 MVP，先给我审核方案。
```

```text
前端和后端适合并行吗？创建 Agent 前先检查接口真源和文件所有权。
```

```text
调整当前团队：集成正在等待，而且两个 Writer 的路径发生重叠。
```

```text
项目准备发布，重新评估风险、独立验证、Owner 审批、回退和恢复。
```

## 三种模式

| 模式 | 用途 | 默认写入行为 |
|---|---|---|
| `proposal` | 设计最小团队和门禁 | 只读检查，返回待审核方案 |
| `initialize` | 创建已经批准的团队结构 | 只写批准范围内、可回退的项目文件 |
| `adjust` | 修正现有团队或任务拓扑 | 保留已确认事实，只执行批准的调整 |

任何模式都不会自动授权生产、真实数据、凭证、付费资源、公开发布、不可逆迁移或删除。

## 工作方式

![检查、分级、提案、批准、执行并验证准确 Commit](docs/images/bootstrap-workflow.png)

```text
检查项目事实
      ↓
已确认事实 / 推断 / 待核验
      ↓
复杂度 C0-C3 + 风险 R0-R3
      ↓
Core 或 Controlled
      ↓
不委派 / 单 Worker / Writer-Validator 小组 / 团队
      ↓
能力档 + 推理强度
      ↓
文件 Owner + Contract + 审批 + 回退
      ↓
待审核方案
      ↓ 仅限已批准范围
执行 → 独立验证 → 验收 → 恢复记录
```

## 按复杂度选择模型，而不是按风险抬高模型

| 判断 | 决定什么 |
|---|---|
| 复杂度 `C0-C3` | 任务拆分、上下文准备、模型能力和推理强度 |
| 风险 `R0-R3` | 权限、独立复核、审批、回退和恢复 |
| 运行时可用性 | 当前模型映射、一次声明的回退、主 Agent 接管或停止 |
| 验证难度 | 是否继续拆分、提高能力或增加独立门禁 |

优化目标不是单次调用最便宜，而是通过验收结果的最低预期总成本：

```text
通过验收的结果成本 = 首次执行 + 预计重试与返工 + 验证 + 协调
```

一项 `C1/R3` 的生产权限修改可以使用 Standard/Medium 实现，同时要求 Owner
批准和强回退证据。一项 `C3/R1` 的纯重构可能需要 Frontier/Max，却不因此取得
生产权限。

主 Agent 继续作为高上下文的信息枢纽。C0/R0 微任务留在主线程；只有在交接具有
净收益时，才把确定性的 C0 批次交给 Economy/Low Worker。

## 两层开发控制

| 开发层 | 默认适用范围 |
|---|---|
| **Core** | 非实质性 C0/C1、R0/R1 工作 |
| **Controlled** | 实质行为、C2/C3、R2/R3、边界变化、并发、生产、发布或公开动作 |

Controlled 不是“流程拉满”，而是只增加当前任务确实需要的 Contract、路径所有权、
独立验证、审批与恢复证据。release、deploy、publish 统一属于 Controlled/R3，并
继续要求 Owner 明确授权。

## 最小团队如何选择

| 任务情况 | 默认拓扑 |
|---|---|
| 很小、明确、低风险 | 主 Agent 单独完成 |
| 隔离且容易验证 | 一个 Worker + 主 Agent 复核 |
| 实质行为变化或回归风险 | 一个 Writer + 一个独立 Validator |
| 多个独立切片且 Contract 已冻结 | 路径隔离的 Writers + 独立验证 |
| 安全、隐私、生产、迁移或发布风险 | 相关专家 + 独立门禁 + Owner 批准 |

Agent 数、Commit 数、代码行数和 Token 数都不是交付结果。

## 这个 Skill 明确不再包含什么

团队绩效回审、历史基线建立、交付遥测、效率比较、任务样本、registration receipt
和外部时间证明，全部由独立系统负责。V2 不在开发过程中采集这些数据，也不为已删除
的接口保留兼容别名。

Skill 仍保留**任务基线 Commit**、准确候选验证、回退和恢复。这些用于保护代码变更，
不是绩效度量功能。

## 为什么全局规则和 Skill 都要有

| 层级 | 负责什么 |
|---|---|
| 全局 `AGENTS.md` | 决定何时触发，保留少数不可绕过的边界 |
| `bootstrap-ai-native-dev-team` | 检查、分级、提案、初始化和调整 |
| 项目真源 | 保存产品、任务、Contract、决策、风险和版本证据 |

精简全局触发规则见
[examples/global-agents-snippet.md](examples/global-agents-snippet.md)。

## 仓库结构

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

## 验证

```bash
python tests/validate_skill.py
python -m unittest discover -s tests -p "test_*.py" -v
```

仓库包含执行相同检查的 GitHub Actions。

## V2 迁移边界

之前的开发线包含 Release Audit、前瞻 metrics、历史基线比较、P2/P3 proof adapter、
公开 receipt 合同和 benchmark fixture。V2 已将这些内容从当前 Skill 树移除。较早的
Git 历史与 release notes 继续作为历史事实保留；不会静默删除或改写外部仓库。

当前分支是尚未打 Tag 的 V2 开发候选，不是正式发布。Push、Tag、GitHub Release、
安装和公开发布仍是相互独立的 Owner 决策。

## 参考与致谢

这个项目参考了以下项目中有价值的做法：

- [obra/superpowers](https://github.com/obra/superpowers)
- [wshobson/agents](https://github.com/wshobson/agents)
- [github/awesome-copilot](https://github.com/github/awesome-copilot)

本仓库的工作流为独立编写，重点补充 proposal-first、C/R 双轴、模型性价比路由、
路径所有权、准确版本证据、原生环境、回退与恢复。

英文发布短文与开发过程图见
[X](https://x.com/Bzbaizhen/status/2087828830627205527)。

## License

[MIT](LICENSE)
