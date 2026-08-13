# AI 原生软件开发团队默认模板

> 适用场景：由一名业务 Owner 管理主线程，并通过多个职责明确的 AI 开发线程完成产品、开发、测试、安全与交付工作。
>
> 模板性质：本文件是团队治理与工程交付的默认基线。新项目创建时应复制本文件，并填写“项目配置区”。如项目现实与默认规则冲突，应通过明确的项目决策记录（ADR）修改，而不是口头绕过。

---

## 目录

- [0. 文档信息](#0-文档信息)
- [1. 项目配置区](#1-项目配置区)
- [2. 核心原则](#2-核心原则)
- [3. 组织架构与权力边界](#3-组织架构与权力边界)
- [4. 单一真源与开发环境](#4-单一真源与开发环境)
- [5. 项目事实真源](#5-项目事实真源)
- [6. 任务状态机与在制品限制](#6-任务状态机与在制品限制)
- [7. 复杂度、风险与模型调度](#7-复杂度风险与模型调度)
- [8. 任务合同与写入租约](#8-任务合同与写入租约)
- [9. Git、Worktree 与 GitHub 工作流](#9-gitworktree-与-github-工作流)
- [10. Contract-first 与跨组件协作](#10-contract-first-与跨组件协作)
- [11. 证据与质量门禁](#11-证据与质量门禁)
- [12. QA、集成与审查](#12-qa集成与审查)
- [13. CI/CD 与自动化门禁](#13-cicd-与自动化门禁)
- [14. 版本与发布](#14-版本与发布)
- [15. 备份与恢复机制](#15-备份与恢复机制)
- [16. 安全、隐私与停止机制](#16-安全隐私与停止机制)
- [17. 状态、决策与风险记录](#17-状态决策与风险记录)
- [18. 指标与自我优化](#18-指标与自我优化)
- [19. 分阶段落地策略](#19-分阶段落地策略)
- [20. 新项目团队初始化清单](#20-新项目团队初始化清单)
- [21. 主线程每次派发任务的操作清单](#21-主线程每次派发任务的操作清单)
- [22. 最终默认原则](#22-最终默认原则)

---

## 0. 文档信息

| 字段 | 内容 |
|---|---|
| 模板版本 | `1.0.0` |
| 项目名称 | `<PROJECT_NAME>` |
| 业务 Owner | `<OWNER>` |
| 主线程 | `<MAIN_THREAD>` |
| 生效日期 | `<YYYY-MM-DD>` |
| 当前阶段 | `<DISCOVERY / MVP / BETA / PRODUCTION>` |
| 最高风险等级 | `<R0-R3>` |
| 文档维护者 | `<MAINTAINER>` |

### 0.1 使用方法

新项目开始时：

1. 复制本文件到项目的治理或产品目录；
2. 填写第 1 节“项目配置区”；
3. 建立第 5 节规定的项目事实真源；
4. 按第 20 节执行初始化检查；
5. 主线程确认门禁和权限后，才开始派发写入任务；
6. 所有偏离本模板的长期决定写入 ADR；
7. 不为了形式启用全部角色，只启用当前任务需要的能力。

---

## 1. 项目配置区

本节必须由主线程在项目启动时填写。未确定的内容标记为 `待核验`，不得猜测。

### 1.1 产品配置

```yaml
project:
  name: <PROJECT_NAME>
  goal: <ONE_SENTENCE_GOAL>
  target_users: <TARGET_USERS>
  current_stage: <DISCOVERY|MVP|BETA|PRODUCTION>
  in_scope:
    - <ITEM>
  out_of_scope:
    - <ITEM>
  success_metrics:
    - <MEASURABLE_RESULT>
```

### 1.2 仓库与环境配置

```yaml
repositories:
  - component: <COMPONENT_NAME>
    repository: <PRIVATE_REPOSITORY_NAME>
    source_of_truth_path: <ABSOLUTE_PATH>
    platform: <WINDOWS|WSL_EXT4|MACOS|LINUX>
    stable_branch: main
    remote_visibility: private
    build_command: <COMMAND>
    test_command: <COMMAND>

integration:
  contract_source: <REPOSITORY_AND_PATH>
  export_target: <PATH_OR_ARTIFACT_REGISTRY>
  direction: <ONE_WAY_DIRECTION>
```

### 1.3 模型路由配置

模型名称不永久写死在通用规则中。每个项目根据当时可用模型填写映射：

```yaml
model_routing:
  main_thread:
    model: <HIGHEST_RELIABLE_MODEL>
    reasoning: <HIGH_OR_MAX>
  C0:
    executor: main_thread
  C1:
    preferred_model: <ECONOMICAL_MODEL>
    preferred_reasoning: <LOW_OR_MEDIUM>
    fallback_model: <FALLBACK_MODEL>
    fallback_reasoning: <LOW_OR_MEDIUM>
  C2:
    preferred_model: <CAPABLE_MODEL>
    preferred_reasoning: <HIGH>
    fallback_model: <FALLBACK_MODEL>
    fallback_reasoning: <MEDIUM_OR_HIGH>
  C3:
    preferred_model: <HIGHEST_RELIABLE_SUBAGENT_MODEL>
    preferred_reasoning: <MAX>
    fallback_model: <FALLBACK_MODEL_OR_MAIN_THREAD>
    fallback_reasoning: <HIGH_OR_MAX>
```

模型不可用时只允许按已声明的回退路径降级一次。高风险或无法安全降级的任务由主线程接管或暂停，不得用低能力结果冒充可靠结论。

### 1.4 审批配置

```yaml
approvals:
  owner_required:
    - production_deployment
    - real_user_data
    - production_credentials
    - external_publication
    - irreversible_migration
    - deletion_of_material_recovery_copy
  main_thread_required:
    - contract_breaking_change
    - new_dependency
    - ci_or_security_policy_change
    - database_migration
    - merge_to_main
    - version_tag_or_release
```

---

## 2. 核心原则

本团队默认遵循：

> 决策集中，事实外置；专业执行，职责隔离；任务驱动，最小授权；单一真源，环境原生；接口先行，受控并行；证据绑定版本，质量分层门禁；Git 管历史，私有远程保异机副本，独立归档与恢复演练保证可恢复。

十二条不可省略的基线：

1. 主线程是唯一任务入口、信息枢纽和合并决策者；
2. 项目事实必须写入可读取的文件或 GitHub，不依赖聊天记忆；
3. 每项任务必须有编号、边界、基线、验收标准和回退方法；
4. 复杂度决定执行能力，风险决定权限和审核门禁；
5. 每个组件只能有一个唯一代码真源；
6. 平台专属工作留在原生环境，其余工作使用项目指定的主要开发环境；
7. 所有写入任务都必须有明确写入租约；
8. 同仓库并行时必须使用独立分支、Worktree 和 PR；
9. `main` 只保存经过验证、可运行、可回退的稳定版本；
10. 测试结论必须绑定确定的 Commit SHA；
11. 本地 Git 不等于异机备份，上传成功也不等于可恢复；
12. 任何 Agent 不得自行扩大范围、合并、发布或执行未获授权的高风险操作。

---

## 3. 组织架构与权力边界

### 3.1 组织结构

```text
业务 Owner／最终批准者
          │
主线程：产品负责人＋技术总控＋控制平面
          │
   ┌──────┼──────────┐
规划与决策池      专业执行池       独立验证池
   │                  │                │
产品拆解            前端开发          QA
架构与接口          后端开发          集成验收
优先级              AI开发            安全审核
风险裁决            DevOps            合规审核
任务调度            数据／来源         AI质量评测
   │                  │                │
   └────────── GitHub与证据真源 ────────┘
```

### 3.2 业务 Owner

业务 Owner 保留：

- 业务目标和资源投入的最终决定权；
- 真实数据、真实来源、生产凭证和对外发布的批准权；
- 不可逆迁移和重要回退副本删除的批准权；
- 正式发布、收费及重大合规边界的最终批准权。

### 3.3 主线程

主线程同时承担产品经理、技术总控和控制平面职责：

- 接收需求并确认目标；
- 拆解任务和维护依赖图；
- 判断是否需要 Subagent；
- 评估复杂度与风险；
- 选择或复用适当角色、模型和推理强度；
- 签发写入租约；
- 冻结接口和验收标准；
- 汇总跨角色意见并裁决冲突；
- 审核交付证据；
- 决定退回、合并、标记版本或升级审批；
- 回收任务和更新项目事实真源。

主线程是决策中心，但不得成为唯一记忆载体。重要事实必须外置。

### 3.4 专业角色池

| 角色 | 主要职责 | 默认是否写代码 |
|---|---|---:|
| 前端开发 | UI、交互、客户端数据层、平台运行 | 是 |
| 后端开发 | API、业务逻辑、持久化、任务管线 | 是 |
| AI开发 | 模型调用、提示与评测管线、AI质量约束 | 是 |
| QA与集成验收 | 独立复现、边界测试、证据审查 | 默认否 |
| 数据／来源运营 | 来源维护、事实链、数据质量 | 视任务而定 |
| AI质量评测 | 保真度、稳定性、偏差与回归评测 | 测试代码可写 |
| DevOps与安全 | CI/CD、环境、安全扫描、运行可靠性 | 视授权而定 |
| 合规与隐私 | 合规边界、个人信息、授权与留存规则 | 否 |
| 用户研究与商业验证 | 用户需求、付费意愿、商业假设验证 | 否 |

角色是能力池，不是常驻编制。只有存在清晰任务时才启用。

### 3.5 独立性规则

- 开发负责实现，QA 负责独立验证；
- QA 不得在正在验收的开发分支上直接修复产品代码；
- QA 可以在独立分支提交测试用例或测试基础设施修复；
- 安全、合规和质量评测提出门禁，不自行替代业务 Owner 批准；
- 执行线程不得自行宣布项目阶段完成；
- 所有进入 `main` 的决定由主线程作出。

---

## 4. 单一真源与开发环境

### 4.1 单一真源原则

每个组件必须满足：

```text
一个组件
→ 一个唯一开发环境
→ 一个唯一源代码目录
→ 一个唯一Git仓库
→ 一个稳定分支真源
```

禁止：

- 在 Windows 与 WSL 同时维护同一组件的可编辑源码；
- 双向同步源码；
- 将导出副本、构建目录或成果目录作为源码真源；
- 多个目录分别修改同一组件；
- 将运行中的 WSL 虚拟磁盘放入同步盘；
- 依赖聊天中的代码片段代替仓库内容。

### 4.2 平台原生优先

- 依赖 Windows GUI、微信开发者工具或 Windows 专属能力的任务在 Windows 完成；
- iOS/macOS 原生项目在 macOS 完成；
- 后端、AI、数据、自动化、Git、Node、Python 和 Linux 服务优先在 Linux 或 WSL Ext4 完成；
- 同一任务跨平台时，按步骤分别执行，不把平台专属命令强行包进另一平台。

### 4.3 跨环境交接

跨环境只允许通过以下方式交接：

- 版本化 API Contract；
- 受控生成物；
- 带清单和校验值的单向导出；
- 私有制品库或明确的集成输入目录。

交接物至少记录：

```text
来源仓库
来源Commit SHA
Contract版本
生成时间
文件SHA-256
兼容性说明
Breaking Change说明
```

---

## 5. 项目事实真源

每个项目至少维护以下六类事实真源：

| 真源 | 推荐位置 | 内容 |
|---|---|---|
| 产品真源 | `product/PRODUCT.md` | 目标、用户、范围、成功标准 |
| 任务真源 | GitHub Issues／`product/TASKS.md` | 状态、依赖、负责人、分支 |
| 代码真源 | Git仓库受保护分支 | 已验证源代码 |
| 接口真源 | `contracts/` | OpenAPI、Schema、Fixture |
| 决策真源 | `decisions/ADR-*.md` | 重要产品与技术决定 |
| 证据真源 | CI、PR、`evidence/` | 绑定Commit的测试和验收 |

建议补充：

```text
PROJECT_STATUS.md   当前版本、门禁、阻塞项
RISKS.md            活跃风险、责任人、缓解措施
CHANGELOG.md        面向使用者的版本变化
RUNBOOKS/           构建、恢复、发布和故障处置
```

以下事项不得只保存在聊天里：

- 产品范围变化；
- 接口字段和兼容性决定；
- 任务是否完成；
- 已知缺陷；
- 测试和真实运行结论；
- 发布、回退与恢复方法；
- 安全或合规门禁。

---

## 6. 任务状态机与在制品限制

### 6.1 标准状态机

```text
DRAFT
→ READY
→ IN_PROGRESS
→ DEV_COMPLETE
→ CI_PENDING
→ CI_PASSED
→ QA_PENDING
→ QA_PASSED
→ MERGE_READY
→ MERGED
→ RELEASED
```

异常状态：

```text
BLOCKED
CI_FAILED
QA_FAILED
CANCELLED
```

任何状态变化必须附带证据或原因。`DEV_COMPLETE` 不等于完成，`QA_PASSED` 也不自动等于允许发布。

### 6.2 Definition of Ready

任务只有同时满足以下条件才能进入 `READY`：

- 目标明确；
- 包含范围和排除范围明确；
- 输入、依赖和基线可用；
- 允许与禁止修改范围明确；
- 接口已冻结，或已明确不涉及接口；
- 验收标准可以执行；
- 风险等级和审批边界已确定；
- 回退方式已说明；
- 不与当前写入租约冲突。

### 6.3 Definition of Done

任务只有同时满足以下条件才能标记完成：

- 实现与任务合同一致；
- 没有越界或无关修改；
- 必要测试通过；
- QA 验证了准确 Commit；
- 文档、契约和迁移说明已同步；
- 安全、隐私和依赖影响已披露；
- PR 可审核且回退方法可执行；
- 状态与证据真源已更新；
- 获得对应风险等级要求的批准。

### 6.4 在制品限制（WIP Limit）

默认限制：

- 每个执行线程同时只承担一个主要任务；
- 每个核心模块同时只允许一个写入租约；
- 每个仓库默认一个写入任务；
- 确有并行收益且目录、接口和依赖可隔离时，可增加独立 Worktree；
- 开发并发不得长期高于 QA 可验收能力；
- 阻塞任务优先解除，不通过创建更多任务掩盖阻塞。

团队衡量“完成并通过验收的任务”，不衡量“同时运行的 Agent 数量”。

---

## 7. 复杂度、风险与模型调度

### 7.1 二维分级

#### 复杂度 C0-C3

| 等级 | 定义 | 典型任务 |
|---|---|---|
| C0 | 查询、整理、机械性操作 | 状态汇总、明确的文字修改 |
| C1 | 范围小、实现路径清晰、易验证 | 小功能、明确缺陷、补充测试 |
| C2 | 跨文件或模块、存在方案选择 | 新业务模块、接口调整、复杂缺陷 |
| C3 | 架构级、跨系统、根因未知 | 核心重构、复杂迁移、系统性诊断 |

复杂度决定：模型能力、推理强度、是否拆分、上下文准备程度。

#### 风险 R0-R3

| 等级 | 定义 | 默认门禁 |
|---|---|---|
| R0 | 只读、无副作用 | 主线程确认范围 |
| R1 | 可轻易回退的普通代码修改 | 测试＋PR审核 |
| R2 | 接口、依赖、数据结构或安全边界变化 | CI＋独立QA＋主线程批准 |
| R3 | 生产、真实数据、密钥、迁移、删除、合规或发布 | 专业审核＋Owner明确批准＋演练或回退证据 |

风险决定：权限、审核角色、测试深度、批准人和停止条件。

### 7.2 不得混淆复杂度与风险

示例：

```text
修改一行生产认证配置：C1 / R3
重构一个无副作用的复杂算法：C3 / R1
修改API返回字段：C1或C2 / R2
只读检查磁盘空间：C0 / R0
```

### 7.3 自动模型调度

主线程派发任务前必须记录：

```text
复杂度
风险
专业领域
上下文规模
不确定性
可验证性
历史一次通过率
成本与时延要求
```

默认决策：

- C0：主线程直接完成；
- C1：使用满足任务的经济型模型和较低推理；
- C2：使用高能力模型和高推理；
- C3：使用最高可靠能力和最高推理，必要时主线程接管；
- R2/R3：不一定提高实现复杂度，但必须提高审核和批准等级；
- 任务过大时优先拆分，不用更高推理掩盖不清晰的任务边界。

### 7.4 动态升级与停止

执行中发现以下情况时必须暂停扩展操作并交回主线程：

- 实际修改范围超过合同；
- 出现新的跨模块依赖；
- 需要改变接口、架构或数据结构；
- 原因无法定位；
- 涉及密钥、真实数据、合规或不可逆操作；
- 原验收标准不足；
- 基线 Commit 已发生变化。

主线程可以拆分任务、提高模型或推理强度、增加审核、重签租约或收回任务。

### 7.5 Agent 复用

主线程创建新 Agent 前应：

1. 检查现有 Agent 状态；
2. 优先复用职责和上下文匹配的 Agent；
3. 运行中的同范围任务追加信息，不重复创建；
4. 空闲且合适的 Agent 继续分配；
5. 只有确有独立任务或并行收益时才创建新 Agent；
6. 任务结束后回收不再需要的 Agent。

---

## 8. 任务合同与写入租约

每个实质性任务必须建立任务合同；每个写入任务必须附带写入租约。

### 8.1 任务合同模板

```markdown
# <TASK-ID> <TASK-TITLE>

## 任务元数据

- 状态：`DRAFT`
- 业务目标：
- 用户价值：
- 负责角色：
- 最终审核者：主线程
- 复杂度：`C0/C1/C2/C3`
- 风险：`R0/R1/R2/R3`
- 复杂度依据：
- 风险依据：
- 选用模型：
- 推理强度：
- 是否降级：否／是，原因：

## 范围

- 包含：
- 不包含：
- 仓库：
- 环境：
- 基线 Commit SHA：
- 允许修改目录：
- 禁止修改目录：
- 分支：
- Worktree：
- 依赖任务：
- 接口／Contract版本：

## 权限

- 可自动执行：
- 需主线程批准：
- 需业务 Owner批准：

## 验证

- 必须运行的测试：
- 人工验收：
- 完成定义：
- 回退方法：

## 交付物

- 代码：
- 测试：
- 文档：
- Evidence Manifest：
```

### 8.2 写入租约模板

```yaml
write_lease:
  task: <TASK-ID>
  repository: <REPOSITORY>
  baseline_sha: <FULL_SHA>
  branch: <BRANCH>
  worktree: <ABSOLUTE_PATH>
  writer: <AGENT_OR_THREAD>
  allowed_paths:
    - <PATH>
  forbidden_paths:
    - <PATH>
  status: active
  start_time: <ISO-8601>
  termination_condition: <DEV_COMPLETE_OR_REVOKED>
```

租约规则：

- 租约只服务一个任务；
- 开发交付后租约冻结；
- QA 期间不得继续修改被验收 Commit；
- 追加修改需要重新打开任务或建立修复任务；
- Agent 不得访问或修改其他任务 Worktree；
- 路径越界应由人工审核或 CI 自动阻断。

---

## 9. Git、Worktree 与 GitHub 工作流

### 9.1 默认映射

所有实质性代码任务采用：

> 一个任务 = 一个 Issue = 一个分支 = 一个 Worktree = 一个 PR

如果项目尚未启用 GitHub，至少保留本地任务编号、分支、Commit 和验证证据，远程启用后补齐。

### 9.2 分支命名

```text
main
├── feat/<TASK-ID>-<name>
├── fix/<TASK-ID>-<name>
├── test/<TASK-ID>-<name>
├── docs/<TASK-ID>-<name>
└── chore/<TASK-ID>-<name>
```

禁止直接在 `main` 开发。

### 9.3 主仓库与 Worktree

主仓库工作目录只用于：

- 查看稳定 `main`；
- 拉取合并后的版本；
- 集成检查；
- 创建 Tag 或 Release。

开发任务在独立 Worktree 完成。不同平台的 Worktree 留在对应原生文件系统。

### 9.4 Commit 原则

每个 Commit 必须：

- 只完成一件明确的事；
- 不混入无关修改；
- 包含必要测试；
- 提交后仍可运行；
- 可以单独理解和安全回退。

提交信息：

```text
feat: add capability
fix: correct defect
test: add or adjust tests
refactor: restructure without behavior change
docs: update documentation
chore: maintain tooling or project
```

### 9.5 标准交付路径

```text
同步main
→ 建立Issue
→ 创建任务分支和Worktree
→ 开发
→ 自检diff
→ 本地测试
→ Commit
→ Push任务分支
→ 创建PR
→ CI
→ 独立QA
→ 主线程审核
→ Squash Merge
→ 更新main
→ 清理已合并分支和Worktree
→ 更新状态与证据
```

### 9.6 禁止的 Git 操作

未经明确授权，禁止：

```text
git reset --hard
git clean -fd
git push --force
覆盖或删除main
删除未确认已合并的分支或Worktree
重写共享历史
```

共享历史中的错误优先使用 `git revert`。

### 9.7 GitHub 保护规则

私有仓库默认启用：

- 禁止直接 Push 到 `main`；
- 禁止强制推送和删除 `main`；
- 必须通过 PR；
- 指定 CI 必须通过；
- 阻断性 Review 必须解决；
- 合并后自动删除任务分支；
- MVP 默认使用 Squash Merge；
- Secret scanning 和依赖安全提醒在可用时启用。

AI OPC 场景可以不强制第二位真人审批，但不得取消主线程审核和自动门禁。

---

## 10. Contract-first 与跨组件协作

前后端或跨组件并行前，必须先冻结最小接口契约：

```text
OpenAPI／JSON Schema
→ Contract测试
→ Synthetic Fixture
→ 上下游并行实现
→ 兼容性测试
→ 集成验收
```

Contract 的唯一真源必须明确。接口修改必须记录：

- 新增、删除或重命名的字段；
- 类型、枚举和必填性变化；
- 是否向后兼容；
- 受影响组件；
- 迁移步骤；
- 兼容版本；
- Breaking Change；
- 来源 Commit SHA。

不同仓库通过 Contract 和版本化制品协作，不通过互相复制源码协作。

---

## 11. 证据与质量门禁

### 11.1 Evidence Manifest

每次验收必须生成或记录等价信息：

```yaml
evidence:
  task: <TASK-ID>
  repository: <REPOSITORY>
  branch: <BRANCH>
  commit: <FULL_COMMIT_SHA>
  environment: <OS_AND_RUNTIME>
  contract_version: <VERSION_OR_NA>
  tests:
    - command: <EXACT_COMMAND>
      result: <RESULT>
      evidence_path: <PATH_OR_URL>
  manual_validation:
    type: <NONE|SIMULATOR|TARGET_PLATFORM|REAL_ENVIRONMENT>
    result: <RESULT>
  qa:
    reviewer: <THREAD_OR_AGENT>
    result: <PASSED|FAILED|BLOCKED>
  known_limits:
    - <LIMIT>
  timestamp: <ISO-8601>
```

规则：

- 测试绑定完整 Commit SHA；
- Commit 变化后，原测试证据失效；
- QA 必须验证同一 Commit；
- 合并内容必须与被验收代码一致；
- 静态检查、单元测试、Synthetic、模拟器、目标平台和真实环境验证必须分别标记；
- “命令已启动”不得写成“测试通过”。

### 11.2 四级门禁

#### Gate 1：开发自检

- 修改范围符合租约；
- 已审核 Diff；
- 本地测试通过；
- 没有密钥、临时文件或无关文件；
- 文档和 Contract 已同步。

#### Gate 2：CI 自动门禁

- 格式和静态检查；
- 单元测试；
- Contract 测试；
- 构建测试；
- Secret 扫描；
- 依赖和锁文件检查；
- 路径越界检查；
- Evidence Manifest 格式检查。

#### Gate 3：独立 QA

- 从干净 Worktree 或干净检出验证；
- 确认准确 Commit SHA；
- 验证关键用户路径、边界和异常状态；
- 区分静态、模拟、集成和真实运行证据；
- 输出 `已确认事实／推断／待核验`。

#### Gate 4：主线程审核

- 业务目标是否达成；
- 是否超出任务边界；
- 风险和残余限制是否可接受；
- 回退是否可执行；
- 是否允许进入 `main`；
- 是否需要 Owner 进一步批准。

任何一级失败，任务退回或阻塞，不得靠文字解释绕过门禁。

---

## 12. PR、QA 与交接模板

### 12.1 Pull Request 模板

```markdown
## 关联任务

- Issue／Task：
- 基线 Commit：
- 当前 Commit：

## 完成内容

- 

## 修改范围

- 修改文件／目录：
- 明确未修改：

## 接口与数据影响

- Contract变化：无／有
- Breaking Change：无／有
- 安全与隐私影响：

## 验证

- 测试命令：
- 测试结果：
- 人工验收：
- Evidence：

## 限制与回退

- 已知限制：
- 回退方法：
- 依赖版本：
```

### 12.2 QA 报告模板

```markdown
# QA Report - <TASK-ID>

- Repository：
- Branch：
- Commit SHA：
- Environment：
- Contract Version：

## 已确认事实

- 

## 测试记录

| 类型 | 命令／步骤 | 结果 | 证据 |
|---|---|---|---|
| | | | |

## 推断

- 

## 待核验

- 

## 缺陷与严重程度

- 

## 结论

- `PASSED / FAILED / BLOCKED`
```

### 12.3 Agent 结构化交接模板

```markdown
# Handoff - <TASK-ID>

## 已完成事项

- 

## 修改的文件

- 

## Git信息

- Repository：
- Branch：
- Commit：
- PR：

## 验证结果

- 

## 接口变化

- 

## 已确认事实

- 

## 推断

- 

## 待核验

- 

## 未解决事项与风险

- 

## 回退方法

- 

## 建议后续行动

- 
```

交付后开发线程停止修改，等待 QA 和主线程决定；需要追加修改时重新授权。

---

## 13. 权限与批准矩阵

### 13.1 Agent 可在任务租约内执行

- 阅读授权项目资料；
- 编辑允许路径；
- 创建任务分支和 Worktree；
- 运行本地测试和静态检查；
- 提交任务分支；
- Push 任务分支；
- 创建草稿 PR；
- 生成验证和交接报告。

### 13.2 必须由主线程批准

- 改变任务范围；
- 修改接口契约或产生 Breaking Change；
- 新增或升级依赖；
- 修改 CI、安全策略或权限；
- 数据库 Schema 迁移；
- 合并到 `main`；
- 创建正式 Tag 或 Release；
- 删除已确认可清理的分支或 Worktree。

### 13.3 必须由业务 Owner 批准

- 接入真实来源或真实用户数据；
- 使用生产密钥、真实账号或付费资源；
- 对外部署、上传、预览、发布或收费；
- 不可逆迁移；
- 删除重要回退副本或生产数据；
- 改变重大合规、隐私或商业边界。

权限与任务绑定，不因某个 Agent 经验较高而永久开放。

---

## 14. 版本、发布与紧急修复

### 14.1 版本规则

采用语义化版本：

```text
0.1.0：首个可验收版本
0.2.0：新增一批向后兼容能力
0.2.1：兼容性缺陷修复
1.0.0：达到正式发布标准
```

多个仓库可以独立编号，但必须记录兼容关系：

```yaml
release:
  frontend: <VERSION>
  backend: <VERSION>
  contract: <VERSION>
```

普通 Commit 不随意打 Tag。只有通过阶段验收的版本才建立 Tag；只有通过发布门禁的版本才建立正式 Release。

### 14.2 标准发布通道

```text
READY
→ IN_PROGRESS
→ DEV_COMPLETE
→ CI_PASSED
→ QA_PASSED
→ MERGE_READY
→ MERGED
→ RELEASE_CANDIDATE
→ OWNER_APPROVED（如需要）
→ RELEASED
```

### 14.3 紧急修复通道

仅阻断性生产问题使用：

```text
Incident
→ 最小修复任务
→ 独立修复分支／Worktree
→ 针对性测试
→ 主线程批准
→ 合并与发布
→ 事后补齐完整测试和复盘
```

紧急通道缩小修改和验证范围，但不允许完全跳过测试、证据或回退准备。

---

## 15. 备份与恢复机制

### 15.1 三类能力必须区分

| 层级 | 作用 | 是否属于完整备份 |
|---|---|---:|
| 工作目录 | 当前编辑状态 | 否 |
| 本地Git | 本地版本历史和回退 | 否 |
| 私有远程仓库 | 异机版本副本 | 部分 |
| 独立归档＋恢复演练 | 灾备与恢复证明 | 是 |

### 15.2 推荐备份结构

重要项目尽量满足接近 `3-2-1`：

```text
第一份：本地工作副本＋本地Git
第二份：GitHub私有远程仓库
第三份：另一位置的加密只读归档
```

分别管理：

- 源代码：Git 和私有远程；
- 大型成果：独立制品或成果归档；
- 数据库：快照、事务日志和数据库恢复方案；
- 密钥：密码或密钥管理器；
- 配置：仓库只保存无密钥模板；
- 开发环境：保存可重建脚本和锁文件，不备份运行中的虚拟磁盘文件。

### 15.3 禁止进入 Git 的内容

```text
.env及真实环境变量
API Key、Token、密码
私钥和证书
真实用户数据
真实来源凭证
依赖目录和虚拟环境
缓存、日志和运行数据库
个人开发配置
无必要的大型二进制文件
```

### 15.4 远程备份完成标准

只有同时满足以下条件，才能标记为远程备份完成：

- 本地 Commit 已生成；
- 成功 Push 到私有远程；
- 远程 `main`、必要分支和 Tag 可读取；
- 仓库可见性确认为 Private；
- 没有上传密钥和敏感数据；
- 从新目录 Clone 的基础验证成功。

### 15.5 恢复演练

每季度或每个重要版本至少执行一次：

1. 从空目录 Clone；
2. 检出指定 Tag；
3. 安装锁定依赖；
4. 根据模板重建配置；
5. 构建；
6. 运行核心测试；
7. 验证 Contract 和必要制品；
8. 记录恢复耗时、缺失项和修复行动。

“上传成功”不等于“恢复成功”。

### 15.6 恢复演练报告模板

```markdown
# Recovery Drill - <DATE>

- Repository：
- Target Tag／Commit：
- Clean Environment：
- Start／End：

## 恢复步骤与结果

| 步骤 | 结果 | 证据 |
|---|---|---|
| Clone | | |
| Checkout | | |
| Install | | |
| Build | | |
| Test | | |
| Contract | | |

## 缺失项

- 

## 恢复结论

- `PASSED / FAILED / PARTIAL`
```

---

## 16. 安全、隐私与停止机制

任何线程发现以下情况必须立即停止相关写入或高风险动作：

- 任务描述与项目事实冲突；
- 实际范围超出任务合同；
- 基线 Commit 变化；
- 接口与冻结 Contract 不一致；
- 测试证据无法对应代码；
- 发现密钥、真实敏感数据或不明凭证；
- 需要删除、覆盖、迁移或执行不可逆操作；
- 出现来源不明的代码、包或二进制；
- 无法证明回退可行；
- 需要真实外部发布或生产权限；
- 原有权限不足或受到明确安全阻止。

停止后必须报告：

```text
已确认事实
当前影响
尚未执行的动作
风险
可选方案
所需批准
恢复或回退方式
```

不得通过绕过权限、安全校验或隐瞒真实状态继续执行。

---

## 17. 状态、决策与风险记录

### 17.1 项目状态模板

```markdown
# Project Status - <DATE>

## 当前阶段与版本

- Stage：
- Stable Commit／Tag：
- Frontend／Backend／Contract compatibility：

## 当前门禁

- 

## 活动任务

| Task | Status | Writer | Branch | Commit | Blocker |
|---|---|---|---|---|---|
| | | | | | |

## 已确认事实

- 

## 推断

- 

## 待核验

- 

## 下一步

- 
```

### 17.2 ADR 模板

```markdown
# ADR-<NUMBER>: <DECISION_TITLE>

- 状态：`PROPOSED / ACCEPTED / SUPERSEDED / REJECTED`
- 日期：
- 决策者：

## 背景

## 已确认事实

## 约束

## 候选方案

## 决定

## 理由

## 影响与代价

## 回退或替代条件
```

### 17.3 风险记录

```markdown
| Risk ID | 描述 | 等级 | 可能性 | 影响 | Owner | 缓解措施 | 触发条件 | 状态 |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |
```

---

## 18. 指标与自我优化

每个阶段版本后复盘：

- 哪类任务返工最多；
- 哪个门禁发现了最多有效问题；
- 哪些检查可以自动化；
- 哪些规则没有产生价值；
- 哪种模型在哪类任务上首次通过率和成本更合理；
- 是否存在主线程、QA 或某仓库的吞吐瓶颈；
- 备份能否真正恢复。

优先指标：

```text
需求到验收通过的周期
首次QA通过率
返工率
逃逸缺陷率
CI稳定性
Agent越界率
每个通过任务的成本
平均恢复时间
恢复演练成功率
```

不得把以下内容直接当作生产力：

```text
Commit数量
代码行数
Agent运行时长
Thread数量
Token消耗量本身
```

连续两个阶段无法证明价值的流程，应简化、自动化或删除。

---

## 19. 分阶段落地策略

不要在小型 MVP 第一天一次性实现所有自动化。

### 阶段 A：项目启动时必须具备

- 主线程和业务 Owner 权限边界；
- 产品、任务、代码、Contract、决策、证据真源；
- 任务合同、Ready／Done 和状态机；
- 单一真源和环境边界；
- 每仓库单写入者；
- Git 本地版本管理；
- 测试证据绑定 Commit。

### 阶段 B：GitHub 就绪后

- 私有远程仓库；
- Issue、分支、Worktree、PR 映射；
- `main` 保护；
- 最小 CI；
- Secret 和依赖扫描；
- Tag、兼容性和远程恢复验证。

### 阶段 C：准备真实用户或上线时

- R2/R3 权限门禁；
- 安全、隐私与合规审核；
- 部署环境隔离；
- 数据库独立备份；
- 日志、监控与告警；
- 发布与回滚演练；
- 第二位置加密只读归档；
- 正式恢复演练。

复杂流程应由真实风险或规模触发，不为“看起来专业”而引入。

---

## 20. 新项目团队初始化清单

### 20.1 产品与治理

- [ ] 已填写项目目标、用户和排除范围；
- [ ] 已确认业务 Owner 与主线程；
- [ ] 已定义哪些操作需要 Owner 批准；
- [ ] 已建立产品、任务、决策、风险和状态真源；
- [ ] 已区分已确认事实、推断与待核验。

### 20.2 环境与真源

- [ ] 每个组件只有一个代码真源；
- [ ] 已记录绝对路径、平台和仓库；
- [ ] 平台专属工具留在原生环境；
- [ ] 没有双向源码同步；
- [ ] 跨组件交接方向与 Contract 真源已明确。

### 20.3 Git 与 GitHub

- [ ] 仓库边界合理；
- [ ] `.gitignore` 已审核；
- [ ] 没有密钥、真实数据和不必要大文件；
- [ ] 初始基线 Commit 已验证；
- [ ] 私有远程已配置并验证；
- [ ] `main` 保护和 PR 规则已配置；
- [ ] 回退与恢复方法已记录。

### 20.4 团队与调度

- [ ] 只启用了有明确任务的角色；
- [ ] 模型路由映射已填写；
- [ ] 复杂度与风险分级已启用；
- [ ] Agent 复用和回收规则已启用；
- [ ] WIP 限制已声明；
- [ ] 同仓库并行任务使用独立 Worktree。

### 20.5 质量与交付

- [ ] Definition of Ready 和 Done 已启用；
- [ ] 最小 CI 与测试命令已确认；
- [ ] QA 使用干净代码状态；
- [ ] Evidence Manifest 绑定 Commit；
- [ ] 静态、模拟、平台和真实运行证据被严格区分；
- [ ] 发布、回退和紧急修复通道已定义。

### 20.6 备份与恢复

- [ ] 本地 Git 历史可用；
- [ ] 私有远程可从新目录 Clone；
- [ ] 大型成果、数据库和密钥有独立方案；
- [ ] 第二位置归档计划已定义；
- [ ] 恢复演练时间和责任人已确定。

---

## 21. 主线程每次派发任务的操作清单

```text
1. 读取最新项目状态与相关决策
2. 确认任务是否达到Ready
3. 检查依赖图和现有写入租约
4. 判断是否需要Subagent及是否有并行收益
5. 检查并优先复用合适Agent
6. 评估复杂度C0-C3和风险R0-R3
7. 根据项目映射选择模型与推理强度
8. 明确仓库、环境、基线SHA和路径边界
9. 创建Issue、分支、Worktree和写入租约
10. 下发任务合同与验收标准
11. 开发交付后冻结写入
12. 运行CI并安排独立QA
13. 审核证据是否绑定准确Commit
14. 决定退回、合并、升级审批或阻塞
15. 更新项目状态、决策和风险
16. 回收Agent及已完成任务资源
17. 阶段通过后再建立Tag、Release和备份验证
```

---

## 22. 最终默认原则

本模板的最终目标不是建立最多的角色、文档或审批，而是构建一个可以持续交付的系统：

> 主线程作为控制平面统一决策；专业 Agent 作为受限执行单元按任务启用；项目事实保存在外部真源；复杂度决定执行能力，风险决定权限与门禁；每项修改被隔离在明确的 Issue、分支、Worktree 和写入租约中；Contract 先于跨组件并行；所有测试和验收绑定准确 Commit；只有通过自检、CI、独立 QA 和主线程审核的代码才能进入稳定分支；Git 记录历史，私有远程保存异机副本，独立归档与恢复演练证明项目可以真正恢复。

判断团队是否高效，只看三件事：

1. 是否更快地产出通过验收的用户价值；
2. 是否能准确知道每个结论对应哪份代码和证据；
3. 发生错误、人员或环境中断时，是否能够安全回退并恢复。
