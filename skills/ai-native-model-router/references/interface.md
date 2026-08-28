# Route interface

The stable seam is `RouteRequest -> RouteDecision`. Both documents are JSON
objects with no undeclared fields. Validate them against the bundled schemas and
the extra explicit-selection rules in `resolve_route.py`.

## RouteRequest

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

## RouteDecision

Every result contains the request identity, selected profile and slot,
`decision_status` (`selected`, `blocked`, or `unknown`), an optional
`selected_route`, `fallback_used`, `fallback_evidence`, the validator source,
the canonical config SHA-256 digest, and limitations.

`selected_route` contains the logical `provider` and its catalog-resolved
`runtime_provider`. `enforcement_status` is always `not-executed`: this
interface reports a selection, not a provider invocation or host assertion.
