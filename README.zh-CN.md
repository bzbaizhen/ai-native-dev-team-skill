# AI Native Dev Team Suite v3.1.1

[English](README.md) | [简体中文](README.zh-CN.md)

这是一个由两个 Skill 组成的控制面：为 Coding Agent 划定可写范围，用有证据的验证支撑交付判断，并保留可回退、可恢复的路径。

适合使用 Codex、Hermes Agent 或其他兼容 Skill 宿主的开发者与技术负责人。当前版本是 [v3.1.1](https://github.com/bzbaizhen/ai-native-dev-team-skill/releases/tag/v3.1.1)。

一个 GitHub 仓库正好包含两个可独立安装的规范 Skill：

- `skills/ai-native-dev-team/` v3.0.1：必需的治理入口（governance-entry）。
- `skills/ai-native-model-router/` v0.4.0：可选的路由扩展（routing-extension）。

## 套件包含什么

| Skill | 版本 | 角色 | 负责内容 |
|---|---:|---|---|
| `ai-native-dev-team` | 3.0.1 | governance-entry | C/R 分类、Core/Controlled、拓扑、权限、DQR、Git 隔离、候选版本身份、集成和恢复。 |
| `ai-native-model-router` | 0.4.0 | routing-extension | 通过 `route/v1`、`route/v2` 和 `.ai-native/model-router.json` 确定具体供应商和模型（provider/model）。它不执行宿主。 |

Team 本身可以独立工作。只有项目需要在宿主边界确定具体供应商和模型时，才安装 Router。

## 两个 Skill 如何协作

```text
任务
  -> Team 的语义 route slot
  -> 可选的 Router：通过 route/v1 或 route/v2 返回 RouteDecision
  -> Host Adapter
```

Team 先给出语义路由槽位（`route slot`），即使没有 Router 也能继续工作。没有 Router 时，供应商和模型的映射保持 `unknown` 或由宿主继承，不能靠推测补齐。Router 支持兼容的 `route/v1` 合同和新增的 `route/v2` assurance 合同，只为宿主适配器（Host Adapter）返回决策，不声称已经调用供应商或强制执行了路由。

本文将 Team、Router、Writer、Validator、RouteDecision、route slot 和 Host Adapter 作为固定名称，后文不再另译。

![Team route slot、可选 Router 决策与 Host Adapter](docs/images/ai-native-dev-team-workflow.png)

## 安装

两个 Skill 分开安装。从源码安装时必须复制完整 Skill 目录，包括 `references`、`assets`、`agents` 元数据和 `scripts`。

| Skill | Codex | Hermes Agent | 手动从源码安装 |
|---|---|---|---|
| `ai-native-dev-team` | `$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/ai-native-dev-team` | 将 `skills/ai-native-dev-team/` 复制到 `$HERMES_HOME/skills/`。 | 将完整的 [`skills/ai-native-dev-team/`](skills/ai-native-dev-team/) 目录复制到宿主支持的 Skill 目录。 |
| `ai-native-model-router` | `$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/ai-native-model-router` | 将 `skills/ai-native-model-router/` 复制到 `$HERMES_HOME/skills/`。 | 将完整的 [`skills/ai-native-model-router/`](skills/ai-native-model-router/) 目录复制到宿主支持的 Skill 目录。 |

套件只有一个仓库和一个当前 GitHub 发布；可选 Router 没有单独的仓库或 Release。

## 60 秒快速开始

安装 Team Skill 后，先发送这条只使用 Team 的提示词：

```text
使用 $ai-native-dev-team。先检查任务和仓库，区分已确认事实、推断和待核验项，评估 C/R，并提出最小安全拓扑。现在不要修改文件。
```

如果项目同时安装了 Router：

```text
使用 $ai-native-dev-team 和 $ai-native-model-router。先检查任务，生成语义 route slot；只有在收到明确的配置档（profile）、API/配置版本和可用性（availability）输入后才通过 route/v1 或 route/v2 解析，并把宿主执行保持在独立边界。现在不要修改文件。
```

## 配置 Router

在项目中创建 `.ai-native/model-router.json`，内容使用下面匹配版本的完整结构。其中 `active_profile` 必须显式选择。必须分别显式选择 Profile 和 Router API/配置版本；仅有 Profile 文件不会启用任何路由。配置中不放密钥或其他敏感信息。Router v0.4.0 移除了 bundled route/v1 Profile：唯一的 bundled 示例是使用 route/v2 的 `gpt5.6`。通用 route/v1 schema 和 API 仍可用于安全的项目 Profile；退休的 Profile ID 会被拒绝，不是别名，也不支持发现。

```json
{
  "schema_version": 2,
  "router_api_version": "route/v2",
  "config_id": "project-router-v2-2026-08-31",
  "active_profile": "gpt5.6",
  "project_profile_dirs": [".ai-native/profiles"],
  "updated_reason": "Explicit project profile selection for route/v2."
}
```

Assurance 矩阵是：R1：Luna Max -> Terra Max -> Sol High；R2：Terra Max -> Sol High；R3：严格使用 Terra Max + Sol High，不会降级为一个 Validator。API/配置版本和 Profile 必须匹配；仅有 Profile 文件不会启用任何路由。参见 [v1 配置 Schema](skills/ai-native-model-router/assets/model-router-config.v1.schema.json)、[v2 配置 Schema](skills/ai-native-model-router/assets/model-router-config.v2.schema.json) 和 [bundled v2 示例](skills/ai-native-model-router/assets/model-router-config.example.json)。仅改配置只适用于已有的宿主适配器合同。新增认证方式、传输机制或宿主注入方式时，仍需修改适配器代码；Router 不会凭配置增加这些能力。

## 工作流

复杂度和风险是两项独立输入：

| 输入 | 决定什么 |
|---|---|
| `C0-C3` 复杂度 | 拆分方式、能力和推理强度。 |
| `R0-R3` 风险 | 权限级别、独立复核、审批、回退和恢复门禁。 |

Team 对普通低风险工作选择 `Core`；出现实质行为变化、更高复杂度/风险、接口或依赖变化、并发、生产、发布或公开影响时，选择 `Controlled`。DQR 是 `Controlled` 内按任务执行的验收协议，不是第三层。

实质工作由只拥有路径租约的 `Writer` 写入冻结范围，再由独立 `Validator` 检查准确候选版本；Validator 不顺手修复。Team 负责任务合同、权限、拓扑、候选版本身份、集成顺序和恢复决策。

```text
检查 -> 分类 -> 授权 -> 隔离 -> 写入 -> 独立验证准确候选版本
     -> 验收 -> 分开执行集成/安装/发布 -> 必要时回退或恢复
```

验收、集成、安装和发布是不同状态。检查通过或接受候选版本，都不会自动授权下一个状态。

## 安全边界

- 权限分层：Team 控制任务范围和授权边界；`Writer` 只获得自己的路径租约；`Validator` 保持独立；风险要求 Owner 审批时不能省略。
- bundled `gpt5.6` Profile 使用上面的 GPT-5.6 assurance 矩阵。它明确选择的高吞吐 `Writer` 仍使用 GLM-5.3 Flash，并在证据满足门禁时回退到 DeepSeek V4 Flash。通用 route/v1 合同仍可用于安全的项目 Profile。Profile/API 始终必须显式选择；bundled Profile 不是默认项，也不会自动启用。可用性必须由调用方提供，不能推断。
- Router 只给出建议，不执行调用。每个 `RouteDecision` 都带有 `enforcement_status: not-executed`；宿主适配器负责凭证、传输和实际执行。
- 回退必须有明确、被配置档接受的“主模型不可用”证据。未说明的错误、主观质量判断或缺少可用性信息都不够。
- Windows 上运行无人值守、非交互式 Coding CLI（Writer 或 Validator）时，默认使用 `pty=false`、`background=true` 和 `notify_on_complete=true`。只有 interactive TUI、login 或确实需要终端输入时才使用 `pty=true`，不能把它无条件用于 unattended exec。最终输出、final-answer marker 或 tokens-used 行都不是进程退出证据；必须等 registry status 为 `exited` 并取得 exit code。只做 one short bounded grace check，再读取 fresh process status；必要时只 terminate exact tracked process，不启动 duplicate Writer，也不反复 wait/reconnect。
- process-kill 或断电中断不会自动建立 crash journal；恢复仍需明确发起并单独复核。

## 从旧名称迁移

旧组件 `bootstrap-ai-native-dev-team` 仅作为迁移输入（migration input only）。它不是第三个 Skill、安装别名或可发现路由。使用[迁移工具](tools/migrate_suite_install.py)；它提供边界明确的 `plan`、`apply`、`verify` 和 `rollback`。

实际安装/移除目标需要 Owner 另行授权。`plan` 只读；`apply`、`verify` 和 `rollback` 会绑定明确的根目录及工具返回的完整性值。运行测试或接受候选版本不等于取得迁移授权。

## 仓库结构

```text
skills/ai-native-dev-team/       # governance-entry Skill
skills/ai-native-model-router/   # optional routing-extension Skill
tools/migrate_suite_install.py   # plan/apply/verify/rollback 工具
tests/                           # Skill、路由、打包和文档合同检查
```

可以从 [Team Skill](skills/ai-native-dev-team/SKILL.md)、[Router Skill](skills/ai-native-model-router/SKILL.md)、[路由与拓扑参考](skills/ai-native-dev-team/references/routing-and-topologies.md) 或 [交付复核参考](skills/ai-native-dev-team/references/delivery-quality-review.md) 开始。

## 验证

在仓库根目录运行公开检查：

```text
python -X utf8 tests/validate_skill.py
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

这些检查覆盖源码结构、路由策略、完整 Skill 打包和文档合同；它们不能证明未实际运行的宿主调用、模型可用性或视觉/运行时结果。

## 发布与许可证

当前发布版本是 [GitHub 上的 v3.1.1](https://github.com/bzbaizhen/ai-native-dev-team-skill/releases/tag/v3.1.1)。两个规范 Skill 都从本仓库发布；这不代表存在单独的组件仓库或发布版本。

许可证为 [MIT](LICENSE)。
