# Route interface

The stable seam is `RouteRequest -> RouteDecision`. Both documents are JSON
objects with no undeclared fields. Validate them against the bundled schemas and
the extra explicit-selection rules in `resolve_route.py`.

## RouteRequest v1

Required fields are `router_api_version`, `request_id`, `route_slot`,
`writer_route_slot`, `profile_id`, `explicit_profile_selection`,
`explicit_high_volume_selection`, `availability`, `primary_failure_evidence`,
`writer_identity`, and `candidate_id`.

`writer_route_slot` is null for every route other than `validator.independent`.
For an independent validator request it is required and must be one of
`writer.c0-batch`, `writer.c1`, `writer.c2`, or `writer.c3`.

`availability` maps a provider/model key such as `zai/glm-5.3` to
`available`, `unavailable`, or `unknown`. Missing keys are `unknown`.
`primary_failure_evidence` is unique. `writer_identity` is either null or an
object containing exactly `provider`, `runtime_provider`, and `model`.
`provider` is the logical provider family; `runtime_provider` is the Host
Adapter identity.

## RouteDecision v1

Every result contains the request identity, selected profile and slot,
`decision_status` (`selected`, `blocked`, or `unknown`), an optional
`selected_route`, `fallback_used`, `fallback_evidence`, the validator source,
the canonical config SHA-256 digest, and limitations.

`selected_route` contains the logical `provider` and its catalog-resolved
`runtime_provider`. `enforcement_status` is always `not-executed`: this
interface reports a selection, not a provider invocation or host assertion.

## RouteRequest v2

The additive v2 request keeps the v1 identity and availability fields, replaces
`primary_failure_evidence` with `route_failure_evidence`, and adds `risk_level`.
Its `router_api_version` is `route/v2`; `validator.assurance` is the Validator
slot and `validator.independent` is not a v2 slot. `risk_level` is `R1`, `R2`,
or `R3` for assurance requests and null otherwise. Assurance requests require
`writer_route_slot`, `writer_identity`, and a non-null `candidate_id`; every
request explicitly selects a profile.

`route_failure_evidence` maps an exact logical route such as
`openai/gpt-5.6-luna` to unique evidence strings. Only route-bound accepted
failures permit escalation; `unknown` remains unknown. For R3, apply this
precedence: missing or unaccepted route-bound evidence for any unavailable
required route => `decision_status: blocked`, even when the other required route
is `unknown`; otherwise, any required route with `unknown` availability =>
`decision_status: unknown`; otherwise, accepted unavailability =>
`decision_status: blocked`. R3 never selects or degrades to one route. A
substantive Validator rejection is outside route resolution and is not
independent validation.

## RouteDecision v2

Every v2 result contains `selected_routes` (zero, one, or two expanded
logical/runtime routes), `validation_mode` (`not-applicable`, `single`, or
`dual`), `risk_level`, `escalation_used`, `escalation_evidence`,
`same_model_as_writer`, `validator_source`, the deterministic config digest,
and limitations. Same-model review is allowed for v2 and is reported through
`same_model_as_writer`; it is not independent validation. R3 selects Terra and
Sol together or blocks, never degrading to one Validator.

`enforcement_status: not-executed` is always returned. It records selection
only and is not an execution receipt.
