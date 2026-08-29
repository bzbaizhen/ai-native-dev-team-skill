# AI Native Dev Team Suite

[English](README.md) | [简体中文](README.zh-CN.md)

**给希望让 Coding Agent 安全修改仓库的开发者使用：明确文件所有权，保留独立证据，并让交付可回退、可恢复。**

它适合使用 Codex、Hermes Agent 或手动安装的兼容 Agent 的开发者与技术负责人。普通的多 Agent 编排往往先列角色；这个 Skill 先检查任务事实，再选择最小拓扑，并把工作和证据绑定到允许路径与准确候选版本。

这个套件由治理 Core/Entry Skill 和可选的 Routing Extension 组成。没有 Router 时
Core 仍可独立工作；需要宿主映射时，再单独安装 Extension。

当前版本：[v2.1.0](https://github.com/bzbaizhen/ai-native-dev-team-skill/releases/tag/v2.1.0)

## 先看这里

| 关注点 | 规则 |
|---|---|
| 控制面 | 主 Agent 负责事实、范围、任务合同、路由、权限、集成、证据复核、停止判断和最终验收。 |
| 实现与验证 | 按任务和路径授权的 Writer（写入者）只修改已冻结范围。独立 Validator（验证者）读取准确候选版本，不顺手修产品代码。Delivery Quality Review（交付质量复核，DQR）是 Controlled 内按任务执行的验收协议。 |
| 活动层 | 只有 Core 和 Controlled 两层。DQR 不是第三层。 |
| 路由 | 复杂度 `C0-C3` 决定拆分、能力和推理强度；风险 `R0-R3` 决定权限、复核、审批、回退和恢复门禁。 |
| Linear 隔离 | Linear 管理的任务在派发 Writer 前使用对应任务分支、已接受的基线和规范 Git Worktree；共享根目录不能替代隔离。 |
| 恢复 | 检查和验收都指向不可变的候选版本；针对该候选版本保留可执行的回退和恢复路径。 |
| 度量 | 本地前瞻指标可选，只由主 Agent 写入，结果仅作描述。缺失观测保留为 `null` 或 `unknown`，指标不负责验收。 |

![多个 Agent 不自动等于一支团队](docs/images/ai-native-dev-team-hero.png)

[安装](#安装) · [60 秒快速开始](#60-秒快速开始) · [工作流](#工作流) · [边界](#边界与证据)

## 为什么做这个 Skill

它来自一个真实的多 Agent 项目。当时所有自动检查都是绿色的：

```text
后端：39/39
前端：8/8
TypeScript：0 diagnostics
微信目标运行时：白屏，9 errors
```

项目里有前端、后端和 QA Agent，但交付边界没有说清楚：哪份任务合同是真源，谁能写哪个路径，测试针对哪个 Commit，证据不足时谁负责停下来。改进的重点是把这些边界写清楚，并增加独立验收路径。

## 安装

| 组件 | 宿主 | 安装方式 | 说明 |
|---|---|---|---|
| Core/Entry — `ai-native-dev-team` | Codex | `$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/ai-native-dev-team` | 治理和交付控制。 |
| Routing Extension — `ai-native-model-router` | Codex | `$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/ai-native-model-router` | 可选的项目级路由合同。 |
| Core/Entry — `ai-native-dev-team` | Hermes Agent | 将完整的 `skills/ai-native-dev-team/` 目录复制到 `$HERMES_HOME/skills/`。 | 保持 references、assets 和 scripts 完整。 |
| Routing Extension — `ai-native-model-router` | Hermes Agent | 将完整的 `skills/ai-native-model-router/` 目录复制到 `$HERMES_HOME/skills/`。 | 需要路由时单独安装。 |
| Core/Entry — `ai-native-dev-team` | 手动安装的兼容 Agent | 将完整的 [`skills/ai-native-dev-team/`](skills/ai-native-dev-team/) 目录复制到 Agent 支持的 Skill 目录。 | 只复制 `SKILL.md` 不完整。 |
| Routing Extension — `ai-native-model-router` | 手动安装的兼容 Agent | 将完整的 [`skills/ai-native-model-router/`](skills/ai-native-model-router/) 目录复制到 Agent 支持的 Skill 目录。 | Extension 可独立选择。 |

## 60 秒快速开始

安装 Skill 后，可以直接使用下面的短提示词：

```text
使用 $ai-native-dev-team。先检查这个仓库和任务，区分已确认事实、推断和待核验项，提出最小安全拓扑。现在不要修改文件。
```

```text
执行已批准的任务。先冻结任务合同和文件所有权；每个 Writer 只写自己的允许路径，实质工作使用独立 Validator，所有检查都绑定到准确候选版本。
```

```text
为这个项目准备发布。重新评估复杂度与风险，核对准确候选、回退与恢复，以及 Owner 批准。发布动作仍需单独授权。
```

## 核心概念

### 主 Agent 是控制面

主 Agent 保留项目上下文，并负责控制面决策。它不重复 Writer 的仓库探索、实现或测试/调试循环。主 Agent 直接处理严格 C0 微编辑时，任务必须微小、确定、低风险、限于单文件，并且只需一次确定性验证；存在不确定性就交给任务级 Writer。

### 一个 Writer 一条路径，验证独立进行

实质工作使用一个拥有准确路径租约的 Writer 和一个独立 Validator。Validator 在干净或受控状态下读取候选版本，把发现项对应到任务合同和候选身份，不顺手修产品代码。修复改变候选版本后，受影响的证据失效，相关检查必须重新运行。

对于需要验收的实质 Controlled 候选，DQR 记录冻结的任务合同、租约、准确候选、独立发现项、重新验证、限制、验收以及回退/恢复。它仍属于 Controlled。

### 复杂度与风险是两条轴

| 轴 | 决定什么 |
|---|---|
| 复杂度 `C0-C3` | 任务拆分、上下文准备、模型能力和推理强度。 |
| 风险 `R0-R3` | 权限、独立复核、审批、回退和恢复。 |

风险会增加门禁，不会自动提高实现能力。一项困难的重构可能需要更强推理能力，但不会因此取得生产权限；一项很小的生产权限修改仍可能需要 Owner 批准和可靠的回退证据。

活动层保持两层：

| 层 | 默认适用范围 |
|---|---|
| **Core** | 非实质性 C0/C1、R0/R1 工作。 |
| **Controlled** | 实质行为、C2/C3、R2/R3、接口或依赖变化、并发、生产、发布或公开动作。 |

Controlled 只增加当前任务需要的任务合同、所有权、验证、审批和恢复证据。发布、部署和公开动作属于 Controlled/R3，仍需 Owner 明确授权。

### Linear Git 隔离

Linear 管理的任务在派发前要回读任务身份、状态、阻断状态、准确 `gitBranchName`、已接受的基线引用与 Commit，以及规范 Worktree。隔离 helper 必须在仓库环境中运行。任务、分支、基线、仓库、Worktree 或 checkpoint 有任何不一致，都应停止；不能用 reset、替换或共享根目录把含糊状态强行变成可执行。

### 回退与恢复

Git 历史、远程副本、回退、恢复、集成、安装和发布是不同状态。验收只表示主 Agent 已基于证据接受准确候选版本，不代表已经授权集成、安装、推送、合并、部署或公开发布。要把可执行的回退/恢复方法和候选版本放在一起，并保留已知限制。

### 可选度量

主 Agent 可以为一组任务明确选择本地前瞻台账。它只记录已经发生且可观察的生命周期事实；Writer 和 Validator 提供交接事实，不写入该记录。audit 和 compare 结果仅作描述，不能替代独立验证、DQR、验收权限或项目决策。

## 工作流

![检查、分级、提案、批准、执行并验证准确候选版本](docs/images/ai-native-dev-team-workflow.png)

1. 检查仓库、任务基线、任务合同、权限、测试入口、集成积压、回退和恢复。
2. 分开记录已确认事实、推断和待核验项，分别评估复杂度与风险。
3. 选择 Core 或 Controlled，再决定不委派、一个 Writer、Writer-Validator 小组，或只有在确有需要时组建更大团队。
4. 冻结最小必要的任务合同、允许路径、接口、候选身份、检查、权限边界和回退方式。Linear 任务要在派发 Writer 前建立隔离分支和 Worktree。
5. 在一次持续授权包络内执行普通、可回退工作。用户只要求方案、范围无法界定或遇到真实权限边界时，停在 proposal-only。
6. 对准确候选版本做独立验证，复核限制和恢复方式，满足所需权限后再验收。集成、安装、发布和公开发布各自需要单独授权与回读。

## 什么时候不必用

- 只读问题，或严格确定、低风险、单文件的 C0 微编辑，可以由主 Agent 直接处理。
- 没有仓库变更的任务不需要团队拓扑或文件租约。
- 如果仓库根目录、任务基线、权威任务合同、允许路径或权限边界无法确认，应停在 proposal-only，直到事实补齐。
- 不要把这个 Skill 当成获取凭证或取得生产、破坏性、不可逆、发布、公开动作权限的捷径；这些动作仍需单独授权。

## 边界与证据

这个 Skill 是工作流，不是产品、任务合同或发布的真源。请把“已确认事实 / 推断 / 待核验”分开；缺少证据就报告缺口，不要补猜。

设计、写入、运行、验证、验收、集成、安装和发布是不同状态。命令已启动、静态检查通过或已经 Push，都不等于验收。未运行的运行时、外部、平台、视觉和恢复检查，应保留为限制。

起始故事里的后端、前端和 TypeScript 检查不能证明目标运行时。准确候选验证、回退和恢复仍是活动工作流的一部分。公开、发布、破坏性、凭证、真实数据和生产动作仍需单独授权；可选指标不是验收门槛。

## 全局规则与 Skill

| 层级 | 负责什么 |
|---|---|
| 全局 `AGENTS.md` | 决定何时触发这个 Skill，并保留少数硬边界。 |
| `ai-native-dev-team` | 检查、分级、提案、初始化和调整。 |
| 项目真源 | 保存实际产品、任务合同、决策、风险和版本证据。 |

精简的全局触发规则见 [examples/global-agents-snippet.md](examples/global-agents-snippet.md)。

## 深入参考

- [Team Skill 入口](skills/ai-native-dev-team/SKILL.md)：权限、选择和执行生命周期。Windows 无人值守 Writer 默认使用 `pty=false`、`background=true` 和 `notify_on_complete=true`；仅将 `pty=true` 保留给交互式输入，并且只有进程 registry 报告 `exited` 时才接受完成，不得创建重复 Writer 或反复 `wait/reconnect`。
- [Team 路由与拓扑](skills/ai-native-dev-team/references/routing-and-topologies.md)：完整的复杂度/风险门禁、拓扑、能力路由和证据复用规则。
- [Core 层](skills/ai-native-dev-team/references/core.md)与 [Controlled 层](skills/ai-native-dev-team/references/controlled.md)：各层的具体规则。
- [Linear Git 隔离](skills/ai-native-dev-team/references/git-isolation-bootstrap.md)：身份、基线、分支、Worktree、checkpoint 和阻断状态门禁。
- [Delivery Quality Review](skills/ai-native-dev-team/references/delivery-quality-review.md)：Controlled 内的按任务验收协议。
- [Model Router 入口](skills/ai-native-model-router/SKILL.md)：可选的项目级路由解析和证据门控回退。
- [可选指标指南](skills/ai-native-dev-team/references/metrics.md)与 [指标事件格式定义](skills/ai-native-dev-team/references/metrics-event.schema.json)：本地台账及其字段。
- [发布与迁移历史](releases/)：既有发布记录和历史边界。

## 仓库结构

```text
skills/ai-native-dev-team/
├── SKILL.md              # 入口
├── references/           # 路由、开发层、隔离、DQR、指标和治理
├── scripts/              # Git 隔离与可选指标工具
└── assets/               # 方案、任务合同和团队模板
```

## 验证

```bash
python tests/validate_skill.py
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

仓库包含对 Python 检查执行相同命令的 GitHub Actions 工作流。

## 迁移与发布边界

### 发布

这个落地页描述当前的 `v2.1.0`。[GitHub Release](https://github.com/bzbaizhen/ai-native-dev-team-skill/releases/tag/v2.1.0) 是发布记录。

### 迁移历史

历史迁移和发布说明见 [发布历史](releases/)。仓库外渠道及任何公开发布决策仍由 Owner 单独授权。

当前源只包含以下两个规范 Skill：`ai-native-dev-team` 和 `ai-native-model-router`。旧名称 `bootstrap-ai-native-dev-team` 仅作为迁移输入，不是已安装的别名，也不可被发现。

标准库迁移工具采用 fail-closed 策略，只操作命令中明确给出的根目录。`plan` 只读，不创建回执或备份任务。对实际安装目标执行破坏性改名和移除旧目录，需要 Owner 对该安装/移除目标另行授权；运行测试或验收候选版本都不等于取得这项授权。

`source-root` 必须是清洁且与 manifest 完全一致的物化结果：所有声明文件都必须存在，不能包含 `__pycache__`、生成缓存或任意额外文件；这些情况按设计会阻止 `plan`。迁移应使用干净的 Commit 或全新物化结果，不要使用有未提交改动的开发 Worktree。实际安装仍保留已声明的进程被杀和断电限制；本工具不会扩展崩溃日志机制。

```text
python tools/migrate_suite_install.py plan --source-root <ABSOLUTE_SOURCE_ROOT> --install-root <ABSOLUTE_INSTALL_ROOT_A> --install-root <ABSOLUTE_INSTALL_ROOT_B> --backup-root <ABSOLUTE_BACKUP_ROOT>
python tools/migrate_suite_install.py apply --source-root <ABSOLUTE_SOURCE_ROOT> --install-root <ABSOLUTE_INSTALL_ROOT_A> --install-root <ABSOLUTE_INSTALL_ROOT_B> --backup-root <ABSOLUTE_BACKUP_ROOT> --receipt <ABSOLUTE_APPLIED_RECEIPT> --plan-digest <PLAN_DIGEST> --confirm-breaking-rename
python tools/migrate_suite_install.py verify --source-root <ABSOLUTE_SOURCE_ROOT> --install-root <ABSOLUTE_INSTALL_ROOT_A> --install-root <ABSOLUTE_INSTALL_ROOT_B> --backup-root <ABSOLUTE_BACKUP_ROOT> --receipt <ABSOLUTE_APPLIED_RECEIPT>
python tools/migrate_suite_install.py rollback --install-root <ABSOLUTE_INSTALL_ROOT_A> --install-root <ABSOLUTE_INSTALL_ROOT_B> --receipt <ABSOLUTE_APPLIED_RECEIPT> --rollback-receipt <ABSOLUTE_ROLLBACK_RECEIPT> --receipt-hash <RECEIPT_HASH> --confirm-rollback
```

请使用 `plan` 输出的计划摘要和 `apply` 输出的回执哈希；不要替换成新生成的值或隐含路径。`rollback` 会写入独立回执，不改写已应用回执。

## 参考与致谢

这个项目参考了以下项目中有价值的做法：

- [obra/superpowers](https://github.com/obra/superpowers)
- [wshobson/agents](https://github.com/wshobson/agents)
- [github/awesome-copilot](https://github.com/github/awesome-copilot)

本仓库的工作流为独立编写，重点补充范围内持续执行授权、proposal-only 条件、C/R 双轴、按复杂度分档、兼顾成本的路由、路径所有权、准确版本证据、原生环境、回退和恢复。

英文发布短文与开发过程图见 [X](https://x.com/Bzbaizhen/status/2087828830627205527)。

## 许可证

[MIT](LICENSE)
