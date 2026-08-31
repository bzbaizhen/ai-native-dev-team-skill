# Provider identity evidence

The catalog is a dated, machine-checked identity snapshot. It records provider
names, runtime provider labels, exact model IDs, reasoning capabilities, and
delivery semantics only. It contains no authentication material, endpoints,
prices, or transport instructions.

The bundled `gpt5.6` Profile maps the control plane to
`openai/gpt-5.6-sol:high`, C0 batch and C1 Writers to
`openai/gpt-5.6-luna:max`, C2 to `openai/gpt-5.6-terra:max`, and C3 to
`openai/gpt-5.6-sol:high`. Its explicitly selected high-volume deterministic
Writer uses `zai/glm-5.3-flash:max`, with
`deepseek/deepseek-v4-flash:max` under the same evidence gate. The route/v1
contract remains available for safe project-local Profiles; its independent
validation slots use the catalog identities selected by that project Profile.

The bundled Profile is `default_active: false` and explicitly selected. Its
`validator.assurance` routes are exact: R1 is
`gpt-5.6-luna:max -> gpt-5.6-terra:max -> gpt-5.6-sol:high`; R2 is
`gpt-5.6-terra:max -> gpt-5.6-sol:high`; and R3 requires
`gpt-5.6-terra:max + gpt-5.6-sol:high`, never degrading to one Validator.
Same-model review is allowed in v2 and is reported through
`same_model_as_writer`; it is not independent validation.

The exact accepted evidence is, in order:

1. `model-not-found`
2. `authenticated-provider-outage`
3. `quota-exhaustion`
4. `repeated-bounded-transport-failure`

These strings are route-bound routing evidence supplied by the caller, not facts
that this package discovers. Subjective quality, cost preference, credential
presence, and an unspecified error do not qualify. Availability and runtime
behavior remain caller-observed inputs and may be `unknown`; unknown remains
unknown. A valid Validator rejection is not a route failure and does not trigger
escalation.

No auth, credential, endpoint, command, price, token, transport, or secret values
enter catalog, profile, request, or evidence data. Provider execution remains
outside this package, and `enforcement_status: not-executed` is not an execution
receipt.
