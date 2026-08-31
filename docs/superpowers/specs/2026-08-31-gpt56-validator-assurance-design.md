# GPT-5.6 Validator Assurance Design

## Status

Owner-approved design for implementation. The existing bundled profile remains immutable and selectable. A new explicitly selected profile and `route/v2` contract add ChatGPT GPT-5.6 assurance routing without changing `route/v1` behavior.

## Goals

- Preserve `openai-glm5.3-deepseek-fallback-2026-08-28` byte-for-byte.
- Add `openai-gpt5.6-validator-assurance-2026-08-31` as a second bundled profile.
- Remove GLM and DeepSeek from the new profile's Validator routes.
- Route Validator assurance by risk:
  - R1: `gpt-5.6-luna:max`, escalating through Terra then Sol only for accepted execution-unavailability evidence.
  - R2: `gpt-5.6-terra:max`, escalating to Sol only for accepted execution-unavailability evidence.
  - R3: require both `gpt-5.6-terra:max` and `gpt-5.6-sol:high`; no single-Validator degradation.
- Permit a selected Validator route to equal the Writer model, but report that fact explicitly.
- Keep every decision selection-only with `enforcement_status: not-executed`.

## Non-goals

- Do not execute providers, inspect credentials, or claim runtime enforcement.
- Do not treat a valid Validator rejection as model failure or seek a more permissive verdict.
- Do not change Writer, control-plane, or high-volume mappings copied from the preserved profile.
- Do not remove DeepSeek from the existing profile or from the new profile's high-volume Writer fallback.
- Do not activate either profile by file presence.

## Compatibility strategy

`route/v1`, its three schemas, its profile ID, resolver behavior, and tests remain supported. `route/v2` is additive and has separate config, request, and decision schemas. The resolver dispatches by the request/config/profile version and rejects mixed versions.

The old bundled profile remains protected by exact-byte collision checks. Both bundled IDs appear in `list-profiles` and can be selected explicitly. A project copy colliding with either bundled ID is accepted only when its bytes are identical.

## New profile

Profile ID: `openai-gpt5.6-validator-assurance-2026-08-31`.

The control-plane, Writer C0–C3, forbidden defaults, and high-volume Writer slot match the preserved profile. The Validator slot is renamed from `validator.independent` to `validator.assurance` and contains:

- `allow_same_model_as_writer: true`;
- exact accepted evidence, in order: `model-not-found`, `authenticated-provider-outage`, `quota-exhaustion`, `repeated-bounded-transport-failure`;
- R1 ordered chain: Luna Max, Terra Max, Sol High;
- R2 ordered chain: Terra Max, Sol High;
- R3 required dual set: Terra Max and Sol High;
- exhaustion action: `blocked-owner`.

## RouteRequest v2

The v2 request keeps common v1 identity and availability fields, replaces `primary_failure_evidence` with `route_failure_evidence`, and adds `risk_level`.

- `router_api_version` is `route/v2`.
- `route_slot` supports all common slots plus `validator.assurance` and excludes `validator.independent`.
- `risk_level` is `R1`, `R2`, or `R3` for `validator.assurance`, and null otherwise.
- `writer_route_slot`, `writer_identity`, and non-null `candidate_id` are required for `validator.assurance` and forbidden/null otherwise as in v1.
- `route_failure_evidence` maps an exact logical route key such as `openai/gpt-5.6-luna` to a unique array of evidence strings.
- Profile and high-volume selection remain explicit.

## RouteDecision v2

Every decision contains:

- `selected_routes`: zero, one, or two expanded logical/runtime routes;
- `validation_mode`: `not-applicable`, `single`, or `dual`;
- `risk_level`;
- `escalation_used`;
- `escalation_evidence`, keyed by exact logical route;
- `same_model_as_writer`, true when any selected route equals the Writer logical or runtime provider/model;
- `validator_source`: `router-selected` or `not-applicable`;
- deterministic config digest and limitations;
- `enforcement_status: not-executed` always.

## Resolution rules

For R1 and R2, evaluate the ordered chain from the first route:

1. `available`: select it.
2. `unknown`: return `unknown`; do not skip it.
3. `unavailable`: require non-empty evidence for that exact route and require every item to be accepted. If valid, continue to the next route; otherwise return `blocked`.
4. Exhausted chain: return `blocked` with the Owner boundary in limitations.

For R3:

1. Both required routes must be `available` to return `selected` with `validation_mode: dual`.
2. Any `unknown` route returns `unknown` unless another required route already has invalid/unaccepted unavailable evidence, which returns `blocked`.
3. Any `unavailable` route requires accepted evidence but still returns `blocked`; R3 never degrades to one route.

A Validator's substantive rejection is outside router resolution. The Writer must create a new candidate ID before revalidation.

## Security and evidence

No auth, credential, endpoint, command, price, token, transport, or secret values enter catalog/profile/request evidence. Availability and failures are caller-supplied facts and may be unknown. Output never claims the selected host was executed.

## Packaging and installation

The suite manifest inventories all new v2 schemas and the new profile. The model-router component version increments. Installation uses the repository's plan/apply/verify transaction, preserving byte-exact backups and receipts for the existing Hermes and Codex install roots. No push, PR, merge, release, or deployment is authorized.

## Verification

- Focused tests prove v1 behavior and old-profile bytes remain unchanged.
- New tests cover R1/R2 escalation, unknown handling, unaccepted evidence, R3 dual selection, R3 no-degradation, same-model reporting, schema surfaces, profile listing, and version mismatch rejection.
- Full repository tests pass.
- CLI validates both profiles and resolves representative v1/v2 requests.
- Installation receipts prove both install roots match repository source.
