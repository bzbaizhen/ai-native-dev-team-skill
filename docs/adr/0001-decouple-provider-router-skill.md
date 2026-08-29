# ADR 0001: Decouple provider routing from the ai-native-dev-team Skill

Status: accepted for Phase 1 contract freeze
Date: 2026-08-28

## Decision

The dependency direction is one-way: `ai-native-dev-team` owns governance and
emits semantic `route/v1` slots; `ai-native-model-router` owns project
configuration and selection and returns a `RouteDecision`. The stable seam is
`RouteRequest -> RouteDecision`. Governance must not import provider-selection
implementation, and the router must not own governance policy.

Phase 1 freezes the machine-readable RouteRequest and RouteDecision contracts,
the v1 project configuration shape, and the configuration helper. The mutable
project file is conventionally `.ai-native/model-router.json`, outside the
installed Skill. The Skill package supplies only the schema, example, and
stdlib helper. Hermes may inject `config_path`; Codex uses explicit `--config`
or the conventional project path. The helper never reads Hermes or Codex global
configuration.

Configuration-only switching is limited to an existing Host Adapter contract.
Provider credentials, endpoints, authentication, transport, command execution,
and host integration remain outside this boundary. A selected configuration is
not evidence that a provider was available or that a route was enforced.

## Rejected alternatives

- A shared provider implementation inside `ai-native-dev-team` was rejected
  because it reverses the dependency direction and couples governance to hosts.
- An installed Skill-owned mutable configuration was rejected because it makes
  project state global or ambiguous across repositories.
- A generic expression/override DSL was rejected because it would smuggle
  credentials, endpoints, transport, or arbitrary commands into configuration.
- Implicit default activation and opaque automatic fallback were rejected;
  profile and high-volume selection remain explicit and evidence-bound.

## Migration and rename boundary

The current and previous embedded-profile shape is migrated by selecting its
`profile_id` into the v1 `active_profile`; legacy `default_active` and
`activation` are checked for explicit, non-default activation. The old embedded
selection structure is not copied into v1 configuration. Any future rename of
the existing development-team governance Skill is staged after execution proof, including
Host Adapter compatibility and independent validation. Phase 1 does not rename
or replace the existing Skill.

Historical evidence is preserved in its original dated artifacts and wording.
Migration and contract changes append new records or documents; they do not
silently rewrite prior routing observations, benchmark evidence, or acceptance
history.

## Consequences

The router can be tested as a pure project-local contract and persistence
boundary. Runtime availability, model/provider identity, fallback evidence, and
independent validation remain observable inputs/outputs of the Host Adapter and
the route decision, not hidden configuration side effects. Atomic writes provide
same-directory preimage backups and fail-closed rollback for the project file.
