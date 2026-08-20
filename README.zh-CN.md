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
| 每个微任务都加载整套治理手册 | 严格 C0 直做与任务级 Writer 留在 Core |
| 接口未冻结，前后端同时开工 | Contract 先于跨组件并行 |
| 两个 Agent 修改同一文件 | 同一时段每个路径只有一个 Writer |
| QA 顺手修改自己正在验收的代码 | 实现与独立验证分离 |
| “测试通过”但版本说不清 | 证据绑定准确候选 Commit |
| 高风险的一行改动与复杂重构混为一谈 | 复杂度和风险分别评估 |
| 所有任务都调用最贵模型 | 按复杂度选择能力与推理强度 |
| Push 被当成已经可恢复 | 区分 Git 历史、远程副本、回退和恢复 |

## 核心原则

1. **最小充分团队**：角色是按任务启用的能力，不是固定编制。
2. **范围内持续执行**：明确的实现请求一次授权范围内普通、可回退工作，不在阶段之间重复索要批准。
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
| `proposal` | 明确只要方案、范围无法界定或已有权限边界 | 只读检查，返回待审核方案 |
| `initialize` | 创建范围明确的团队结构；明确实现请求可直接衔接提案 | 只写授权包络内、可回退的项目文件 |
| `adjust` | 修正现有团队或任务拓扑 | 保留已确认事实，只执行授权包络内的调整 |

明确要求构建、实现、修复、初始化或调整时，该请求对所述仓库与任务范围内普通、可回退
工作形成一次持续授权包络，包括受限委派、工作区编辑、本地构建/测试/lint、只读 Git
检查、交接和可回退纠错。只有明确要求方案、范围无法界定或已遇到真实权限边界时，才
进入 proposal-only。

授权包络不包含凭证或密钥、真实或生产数据、付费资源、公开发布、push/merge/deploy/
release、破坏性删除、不可逆迁移、权限提升或范围外写入。优先使用原生文件工具和任务内
脚本，不得以宽泛的全局白名单绕过审批。

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
文件 Owner + Contract + 权限边界 + 回退
      ↓
明确只要方案 / 范围无法界定 / 已遇到权限边界 → proposal-only
      ↘ 其他情况在持续授权包络内继续
执行 → 独立验证 → 验收 → 恢复记录
```

## 按复杂度选择模型，而不是按风险抬高模型

| 判断 | 决定什么 |
|---|---|
| 复杂度 `C0-C3` | 任务拆分、上下文准备、模型能力和推理强度 |
| 风险 `R0-R3` | 权限、独立复核、审批、回退和恢复 |
| 运行时可用性 | 可观察的运行时映射、一次声明的回退、例外授权接管或停止 |
| 验证难度 | 是否继续拆分、提高能力或增加独立门禁 |

优化目标不是单次调用最便宜，而是通过验收结果的最低预期总成本：

```text
通过验收的结果成本 = 首次执行 + 预计重试与返工 + 验证 + 协调
```

一项 `C1/R3` 的生产权限修改可以使用 Standard/Medium 实现，同时要求 Owner
批准和强回退证据。一项 `C3/R1` 的纯重构可能需要 Frontier/Max，却不因此取得
生产权限。

主 Agent 是高上下文控制面，只能直接做只读控制面工作，或一个同时满足以下条件的
严格 C0 编辑：微小、确定、低风险、单文件；无实质行为、接口、依赖、数据、安全、
并发、生产或公开影响；不进入调试循环、不编写测试；且只需一次确定性验证。任一条件
缺失或不确定都必须委派。

所有 C0 机械批次，以及每个 C1+ 实现、重构、Bug 修复、测试编写或调试任务，都交给
配置好的低成本执行路径上的任务级 Writer，不存在通用的“交接成本更高”实现例外。
主 Agent 保留范围、架构决策、任务合同、权限、集成、证据复核、停止判断和最终验收，
不重复 Writer 的仓库探索、实现或测试/调试循环。

实质工作采用 Writer + 独立 Validator，并绑定准确候选版本。C3 架构可以留在控制面，
冻结后的实现切片交给 Writer。主 Agent 高成本实现接管要求 Writer 路径不可用或已有
重复失败证据、无法安全重切、用户明确授权，并记录原因。只有编排层 Subagent 的可观察
运行时映射确属较低成本档时，才能声称节省成本。

Canonical 映射继续保持供应商中立。项目可以明确选择隔离、带日期的运行时 profile；
profile 文件存在不会改变公开默认。一个示例是证据快照日期为 2026-08-20 的可选
[OpenAI + DeepSeek profile](skills/bootstrap-ai-native-dev-team/references/model-routing-openai-deepseek.md)，
其中记录准确路由、Hermes 运行时限制、认证/可用性门禁、证据缺口和重新校准触发条件。

### Windows 无人值守 Coding CLI 生命周期

在 Windows 上，对可能执行有界长任务的无人值守、非交互 Coding CLI `exec`、Writer 和
Validator 工作，默认使用 `pty=false`、`background=true` 和
`notify_on_complete=true`。`pty=true` 仅用于交互式 TUI、登录或确实需要终端输入的命令，
不能无条件套用于无人值守 exec。

最终输出文本、final-answer 标记或 tokens-used 行不是进程退出证据。只有重新检查进程
registry，确认状态为 `exited` 并取得退出码（exit code），才能接受完成状态。如果 legacy
PTY 在打印最终标记后仍存活，只做一次短时有界宽限检查，再重新检查进程状态；必要时只终止
被准确跟踪的那个进程。不得启动重复 Writer，也不得反复 wait/reconnect；将输出和退出
证据与准确候选验证放在一起保存。

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
| 只读控制面，或满足全部严格条件的单文件 C0 微编辑 | 主 Agent 单独完成 |
| C0 机械批次或非实质 C1+ 实现 | 一个任务级 Writer + 主 Agent 复核 |
| 实质行为变化或回归风险 | 一个 Writer + 一个独立 Validator |
| 多个独立切片且 Contract 已冻结 | 路径隔离的 Writers + 独立验证 |
| 安全、隐私、生产、迁移或发布风险 | 相关专家 + 独立门禁 + Owner 批准 |

Agent 数、Commit 数、代码行数和 Token 数都不是交付结果。

## 这个 Skill 明确不再包含什么

团队绩效回审、历史基线建立、强制交付遥测、效率比较、registration receipt 和外部
时间证明，全部由独立系统负责。V2 不运行 metrics ledger，也不为已删除接口保留兼容
别名。明确选择的路由 profile 可以增加轻量、任务局部的观察字段；不可观察值保持
`unknown`，这些字段不会形成 ledger、baseline、benchmark 或 release gate。

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
│   ├── model-routing-openai-deepseek.md  # 可选，默认不启用
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

当前版本为 V2.0.0，`v2.0.0` Tag 与 GitHub Release 用于标识这一已发布版本。
安装以及仓库之外的其他外部渠道仍是相互独立的 Owner 决策。

## 参考与致谢

这个项目参考了以下项目中有价值的做法：

- [obra/superpowers](https://github.com/obra/superpowers)
- [wshobson/agents](https://github.com/wshobson/agents)
- [github/awesome-copilot](https://github.com/github/awesome-copilot)

本仓库的工作流为独立编写，重点补充范围内持续执行授权、显式 proposal-only 条件、
C/R 双轴、模型性价比路由、
路径所有权、准确版本证据、原生环境、回退与恢复。

英文发布短文与开发过程图见
[X](https://x.com/Bzbaizhen/status/2087828830627205527)。

## License

[MIT](LICENSE)
