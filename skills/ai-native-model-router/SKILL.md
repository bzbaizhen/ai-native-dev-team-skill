---
name: ai-native-model-router
description: Deterministic model routing with evidence-bound fallbacks.
version: 0.3.0
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

Use this Skill as a deterministic `route/v1` resolver with additive `route/v2`
assurance routing. It owns project-local selection and returns a machine-readable
`RouteDecision`; it does not execute a host, call a provider, load credentials,
or claim that a route was enforced.

Version 0.3.0 is a breaking Profile-ID rename: the bundled v1 Profile ID is
`glm+deepseek` and the bundled v2 Profile ID is `gpt5.6`. The previous IDs and
profile filenames are removed; they are not aliases or supported discovery names.

## Contract navigation

- Read [interface](references/interface.md) for the v1 and v2 RouteRequest and
  RouteDecision contracts.
- Read [configuration](references/configuration.md) for selection precedence,
  version pairing, digest checks, safe project profiles, and collision handling.
- Read [provider evidence](references/provider-evidence.md) before relying on a
  dated identity or fallback claim.
- Use [resolve_route.py](scripts/resolve_route.py) for validation and resolution.
  The Phase 1 config helper remains [router_config.py](scripts/router_config.py).
- The package contract is in [provider-catalog.json](assets/provider-catalog.json),
  the immutable [v1 profile](assets/profiles/glm+deepseek.json),
  the immutable [v2 profile](assets/profiles/gpt5.6.json),
  and the [v1 config](assets/model-router-config.v1.schema.json),
  [v1 request](assets/route-request.v1.schema.json),
  [v1 decision](assets/route-decision.v1.schema.json),
  [v2 config](assets/model-router-config.v2.schema.json),
  [v2 request](assets/route-request.v2.schema.json), and
  [v2 decision](assets/route-decision.v2.schema.json) schemas.

## Operating rules

1. Every request explicitly selects a profile. Both bundled profiles are
   `default_active: false` with `explicit-owner-selection`; file presence never
   activates a profile. Require explicit task selection for
   `writer.high-volume-deterministic`.
2. Preserve `route/v1` and its `validator.independent` independent-validation
   semantics. Mixed v1/v2 request, config, and profile versions fail closed.
3. `route/v2` uses `validator.assurance`: same-model review is allowed and is
   reported through `same_model_as_writer`; it is not independent validation.
   R1 is `gpt-5.6-luna:max -> gpt-5.6-terra:max -> gpt-5.6-sol:high`.
   R2 is `gpt-5.6-terra:max -> gpt-5.6-sol:high`. R3 requires
   `gpt-5.6-terra:max + gpt-5.6-sol:high` and must never degrade to one Validator.
   For R3, apply this precedence: missing or unaccepted route-bound evidence for
   any unavailable required route => `decision_status: blocked`, even when the
   other required route is `unknown`; otherwise, any required route with
   `unknown` availability => `decision_status: unknown`; otherwise, accepted
   unavailability => `decision_status: blocked`. R3 never selects or degrades to
   one route.
4. route-bound evidence may be only `model-not-found`,
   `authenticated-provider-outage`, `quota-exhaustion`, or
   `repeated-bounded-transport-failure`, keyed to the unavailable route.
   Treat `unknown` as unknown; unknown remains unknown after the R3 precedence
   above; never infer availability. A valid Validator rejection is not a route
   failure. A substantive Validator rejection does not trigger escalation; create
   a new candidate ID before revalidation.
5. Resolve a fallback only for an unavailable route with complete accepted
   evidence and an available next route. Return `enforcement_status:
   not-executed` always; this is not an execution receipt.
6. Keep provider execution, authentication, and transport outside this package.
   No secret, endpoint, credential, transport command, or price value belongs in
   configuration, profiles, catalog data, prompts, or evidence.

## CLI

```text
python scripts/resolve_route.py list-profiles
python scripts/resolve_route.py validate-profile --profile <id>
python scripts/resolve_route.py resolve --request <json-path-or-json> [--config <path>] [--injected-config <path-or-json>]
```

CLI success is JSON on stdout. Errors are JSON-free diagnostics on stderr with a
nonzero exit code. Ordering is deterministic.
