# AI Native 开发团队 Skill

[English](README.md) | [简体中文](README.zh-CN.md)

**先判断这次任务是否真的需要组队，再组建能够安全交付的最小 AI 软件团队。**

它不追求同时运行更多 Agent，而是为 Coding Agent 补上文件所有权、独立验证、版本证据、审批门禁、回退与恢复边界。

![多个 Agent 不等于一支团队：经过审批门禁的 AI Native 交付流程](docs/images/ai-native-dev-team-hero.png)

[安装](#安装) · [使用](#使用) · [工作方式](#工作方式) · [为什么全局规则和-skill-都要有](#为什么全局规则和-skill-都要有)

## 为什么做这个 Skill

这个 Skill 不是先写好一套方法论，再去寻找适用场景。它来自我在一个多 Agent 项目里踩过的坑，下面的项目细节已经匿名化：

```text
后端：39/39
前端：8/8
TypeScript：0 diagnostics
微信目标平台：白屏，9 errors
```

所有自动检查都通过了，但它们没有证明目标平台真的能运行。

当时已经有前端、后端和 QA，任务也在并行。我把“已经分工”误当成“已经形成交付系统”。真正没有说清楚的是：接口以什么为准，谁能修改哪个路径，QA 验收的是哪个 Commit，以及证据不足时谁负责让团队停下来。

这次失败最后变成了这个 Skill 的起点：先减少无法解释的并行，再决定要不要增加 Agent。

## 它解决什么

| 常见问题 | 这个 Skill 的处理方式 |
|---|---|
| 一开始就创建完整角色池 | 先检查任务，只启用最小充分团队；简单任务可由主 Agent 单独完成 |
| 接口未冻结，前后端同时开工 | Contract 先于跨组件并行，边界不清时先停止拆分 |
| 两个 Agent 修改同一文件 | 每个路径只有一个 Owner，写入权限随任务租约发放 |
| QA 顺手修改自己正在验收的代码 | 实现与独立验证分离，QA 默认只读产品代码 |
| “测试通过”却说不清验证了哪个版本 | 结论绑定完整 Commit SHA、命令、环境、结果和限制 |
| Push 被当成“备份完成” | 区分 Git 历史、远程副本、独立归档和真实恢复演练 |
| 原型背上生产级流程 | 复杂度和风险分别判断，治理强度随任务调整 |
| Agent 缺少信息却继续编造 | 缺少接口真源、构建命令或验收方法时，可以明确选择“不组队” |

## 核心原则

1. **最小充分团队**：角色是按任务启用的能力，不是固定编制。
2. **Proposal first**：默认先给出待审核方案；批准前不创建 Agent、分支、Worktree 或治理文件。
3. **复杂度与风险分开**：`C0-C3` 决定如何拆分和执行，`R0-R3` 决定权限、复核与恢复要求。
4. **一个路径，一个 Owner**：共享文件由唯一所有者修改，其他 Agent 提交变更请求。
5. **Contract 先于并行**：接口、依赖、集成顺序和验收标准冻结后，再并行实现。
6. **验证准确版本**：开发自检、自动检查、独立 QA 和业务批准是不同层级的证据。
7. **能够安全停止**：权限不足、基线冲突、证据无法绑定版本或缺少回退路径时，停止扩张并报告。

## 安装

让 Codex 从本仓库安装：

```text
$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/bootstrap-ai-native-dev-team
```

也可以把 `skills/bootstrap-ai-native-dev-team` 复制到 Codex 支持的用户级或项目级 Skill 目录。

安装后可以明确调用：

```text
使用 $bootstrap-ai-native-dev-team，先为这个仓库提出最小且安全的 AI Native 开发团队方案。现在不要修改文件。
```

## 使用

可以这样提出任务：

```text
用最小充分团队初始化这个 MVP，先给我审核方案。
```

```text
审核当前多 Agent 项目的 Agent、分支、Worktree、文件所有权、QA 门禁和恢复方案。
```

```text
前端和后端现在适合并行吗？请先核对接口真源和路径冲突。
```

```text
项目准备发布了，重新评估复杂度、风险、独立验证和回退要求。
```

Skill 默认使用 `proposal` 模式。除非相应范围得到批准，否则它只输出方案，不执行建队或写入。

## 四种模式

| 模式 | 用途 | 默认写入行为 |
|---|---|---|
| `proposal` | 为新任务设计最小团队和门禁 | 只读检查，输出待审核方案 |
| `initialize` | 初始化已经批准的团队结构 | 只写批准范围内的项目文件和资源 |
| `audit` | 审核已有团队、仓库和交付证据 | 只读 |
| `adjust` | 缩编、扩编或纠正已有团队 | 保留已确认事实，只执行批准的调整 |

即使使用 `initialize`，也不会自动授权生产环境、真实用户数据、凭证、公开发布、不可逆迁移或删除。这些动作仍需要业务 Owner 明确批准。

## 工作方式

![检查、分级、提案、批准、执行并验证准确 Commit](docs/images/bootstrap-workflow.png)

```text
检查项目真源
      ↓
已确认事实 / 推断 / 待核验
      ↓
复杂度 C0-C3 + 风险 R0-R3
      ↓
选择最小充分团队
      ↓
文件 Owner + Contract + 审批 + 回退
      ↓
提交待审核方案
      ↓ 仅限已批准范围
初始化 → 实现 → 独立验证 → 验收 → 恢复记录
```

一份紧凑的输出示例见 [`examples/sample-proposal.md`](examples/sample-proposal.md)。

## 复杂度和风险为什么要分开

复杂不等于危险，简单也不等于低风险。

- 一行生产认证权限改动可能是 `C1/R3`：实现不难，但权限和回退要求很高。
- 一个跨多个模块、只使用合成数据的原型可能是 `C3/R1`：理解和拆分困难，但不会触碰生产数据。

把两者压成一个分数，容易给前者过少的门禁，又给后者加上过重的流程。

## 最小团队如何选择

| 任务情况 | 默认团队拓扑 |
|---|---|
| 只读、很小、明确且低风险 | 主 Agent 单独完成 |
| 隔离实现，容易验证 | 一个实现者 + 主 Agent 复核 |
| 行为变化或回归风险明显 | 实现者 + 独立验证者 |
| 多个独立切片，Contract 已冻结 | 路径隔离的实现者 + 独立验证者 |
| 安全、隐私、生产、迁移或发布风险 | 按需专家 + 独立门禁 + Owner 批准 |

它不会为了显得“更 Agentic”而固定创建八个 Agent。Agent 数量、Commit 数量和 Token 消耗都不是交付指标，通过验收的用户价值才是。

## 为什么全局规则和 Skill 都要有

只有全局规则，配置文件很快会变成一本执行手册，每个小任务都携带整套治理上下文。

只有 Skill，新项目又可能根本不会触发它。

建议采用三层结构：

| 层级 | 负责什么 |
|---|---|
| 全局 `AGENTS.md` | 决定何时触发，保留少数不可绕过的边界 |
| `bootstrap-ai-native-dev-team` Skill | 检查、分级、提案、初始化、调整与审核 |
| 项目真源 | 保存本项目的合同、ADR、任务、风险、状态与版本证据 |

可以把 [`examples/global-agents-snippet.md`](examples/global-agents-snippet.md) 中的精简规则加入全局 `AGENTS.md`。这样重要项目会自动触发，普通低风险任务仍保持轻量。

## 适合使用

- 新软件项目或重要新阶段；
- 跨前端、后端、AI、数据或原生平台的开发；
- 多 Agent 并行实现；
- 引入分支、Worktree、PR 或写入租约；
- 发布准备、高风险工程变更；
- 已经出现基线漂移、重复 Writer、QA 证据不清的项目；
- 需要缩编、扩编或重新划分团队权限。

## 不必使用完整团队流程

- 一次只读查询；
- 一个文件内的明确小修改；
- 主 Agent 可以安全完成且验证成本很低的任务。

如果用户明确调用这个 Skill，它仍会响应，但可能给出的正确结论就是：**由主 Agent 单独完成，不组建额外团队。**

## 仓库结构

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

- `SKILL.md`：工作流入口与决策规则；
- `team-governance-template.zh-CN.md`：完整治理基线；
- `team-bootstrap-proposal.md`：建队提案模板；
- `project-team-charter.md`：项目团队章程模板；
- `task-contract.md`：任务、路径、权限与验收合同；
- `evidence-manifest.yaml`：绑定准确版本的验证证据。

## 验证边界

![0.1.0 的验证证据与未声称范围](docs/images/verification-evidence.svg)

本地运行：

```bash
python tests/validate_skill.py
```

仓库包含执行相同结构检查的 GitHub Actions。

`0.1.0` 已验证仓库结构、必需资源、本地链接、Agent 配置和公开安装路径。它是首个公开基线，不代表已经达到生产成熟度，也不表示适用于所有团队和项目。

## 参考与致谢

这个项目参考了几个公开项目中已经验证过的做法：

- [obra/superpowers](https://github.com/obra/superpowers)：任务级 Subagent、Worktree、复核循环与完成前验证；
- [wshobson/agents](https://github.com/wshobson/agents)：团队组合、任务协调、文件所有权与并行开发；
- [github/awesome-copilot](https://github.com/github/awesome-copilot)：Producer、Developer 与可选 QA 的职责分离。

本仓库的工作流为独立编写，重点补充 proposal-first 授权、复杂度/风险双轴、业务 Owner 权限、写入租约、不可变版本证据、原生环境边界、备份语义和恢复演练。

## 反馈与贡献

如果你把它用于真实项目，最有价值的反馈不是“启动了多少 Agent”，而是：

- 哪个任务触发了组队，最后选择了什么团队拓扑；
- 哪条 Contract、权限或验证规则避免了返工；
- 哪个流程过重、遗漏了真实风险，或者应该直接由主 Agent 完成；
- 对应的 Skill 版本、验证方式和可公开的失败证据。

欢迎提交聚焦问题的 [Issue](https://github.com/bzbaizhen/ai-native-dev-team-skill/issues) 或小范围 Pull Request。请先删除凭证、用户数据和私有仓库信息。

## 状态

当前版本：`0.1.0`，是首个公开基线。英文发布短文与四张开发过程图见 [X](https://x.com/Bzbaizhen/status/2087828830627205527)。

## License

[MIT](LICENSE)
