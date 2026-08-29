---
name: ai-native-model-router
description: Deterministic model routing with evidence-bound fallbacks.
version: 0.1.0
author: bzbaizhen, Hermes Agent
license: MIT
platforms:
  - linux
  - macos
  - windows
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
---

# AI Native Model Router

Use this Skill as a deterministic `route/v1` resolver. It owns project-local
selection and returns a machine-readable `RouteDecision`; it does not execute a
host, call a provider, load credentials, or claim that a route was enforced.

## Contract navigation

- Read [interface](references/interface.md) for RouteRequest and RouteDecision.
- Read [configuration](references/configuration.md) for selection precedence,
  digest checks, safe project profiles, and collision handling.
- Read [provider evidence](references/provider-evidence.md) before relying on a
  dated identity or fallback claim.
- Use [resolve_route.py](scripts/resolve_route.py) for validation and resolution.
  The Phase 1 config helper remains [router_config.py](scripts/router_config.py).
- The package contract is in [provider-catalog.json](assets/provider-catalog.json),
  the immutable [profile](assets/profiles/openai-glm5.3-deepseek-fallback-2026-08-28.json),
  and the [config](assets/model-router-config.v1.schema.json),
  [request](assets/route-request.v1.schema.json), and
  [decision](assets/route-decision.v1.schema.json) schemas.

## Operating rules

1. Require explicit profile selection on every request. Require explicit task
   selection for `writer.high-volume-deterministic`.
2. Resolve the primary only when its exact provider/model availability is
   `available`. Treat `unknown` as unknown; never infer availability.
3. Permit a fallback only when the primary is unavailable, every supplied
   failure item is in the profile's exact accepted evidence list, and the
   fallback is available. Unaccepted or missing evidence blocks the route.
4. Keep independent validation separate: validator requests must name the
   `writer_route_slot`; an actual selected validator may not equal the writer
   logical provider/model or runtime provider/model. High-volume decisions use
   the exact `openai-complexity-map` independent validator source. Return
   `enforcement_status: not-executed` always.
5. Keep provider identity, runtime capability, authentication, transport, and
   execution outside this package. No secret values belong in configuration,
   profiles, catalog data, prompts, or evidence.

## CLI

```text
python scripts/resolve_route.py list-profiles
python scripts/resolve_route.py validate-profile --profile <id>
python scripts/resolve_route.py resolve --request <json-path-or-json> [--config <path>] [--injected-config <path-or-json>]
```

CLI success is JSON on stdout. Errors are JSON-free diagnostics on stderr with a
nonzero exit code. Ordering is deterministic.
