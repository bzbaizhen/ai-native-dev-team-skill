---
name: ai-native-model-router
description: 为已决定委派的任务解析模型路由与回退，或校验 Router 配置；不执行模型调用。
license: MIT
metadata:
  hermes:
    related_skills:
    - ai-native-dev-team
    tags:
    - model-routing
    - provider-selection
    - deterministic
    config:
    - key: ai_native_model_router.config_path
      description: Path to the project-local model router configuration.
      default: .ai-native/model-router.json
      prompt: Enter the project-local model router configuration path.
  version: 0.5.1
  author: bzbaizhen, Hermes Agent
  platforms:
  - linux
  - macos
  - windows
---

# AI Native Model Router

Resolve a project-local model selection into a machine-readable `RouteDecision`. This package does not call a provider, load credentials or prove execution. Use it when choosing models for already-justified delegation or when the user asks to configure or validate routing.

Use the owner's current selection and configured precedence; a profile file's presence alone is not authorization. The bundled profile is `gpt6` on `route/v2`. Preserve existing explicit-only invocation policy and task-specific role requirements.

## Resolve and validate

- Read [configuration.md](references/configuration.md) when choosing or updating configuration: precedence, version pairing, profile digests and collisions.
- Read [interface.md](references/interface.md) for request/decision fields, and [operating-rules.md](references/operating-rules.md) before resolving a request. Preserve route/v1 independence and route/v2 assurance semantics; mixed versions fail closed. The gpt6 profile uses one assurance validator at every risk level, including R3, as explicitly selected by the owner.
- Read [provider-evidence.md](references/provider-evidence.md) only when relying on provider identity, availability or fallback evidence. Unknown availability stays unknown; a valid review rejection is not a transport failure.
- Use `scripts/resolve_route.py` for deterministic validation/resolution and `scripts/router_config.py` for configuration. Keep execution, credentials and transport outside this package; return `enforcement_status: not-executed` until the host supplies its own separate receipt.

```text
python scripts/resolve_route.py list-profiles
python scripts/resolve_route.py validate-profile --profile <id>
python scripts/resolve_route.py resolve --request <json-path-or-json> [--config <path>] [--injected-config <path-or-json>]
```

Success is JSON on stdout; errors are diagnostics on stderr with nonzero exit. Use the existing `assets/` schemas and profile through the resolver rather than loading every schema into context.
