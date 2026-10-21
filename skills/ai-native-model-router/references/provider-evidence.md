# Provider identity evidence

The catalog is a dated, machine-checked identity snapshot. It records provider
names, runtime provider labels, exact model IDs, reasoning capabilities, and
delivery semantics only. It contains no authentication material, endpoints,
prices, or transport instructions.

The bundled `gpt6` profile was originally specified by the owner on 2026-09-23.
On 2026-10-02 the owner replaced every Sol route with `gpt-6.1-sol`,
keeping each reasoning level and the same profile ID; the previous profile is not retained.
The current Codex host tool metadata lists the requested model/reasoning pairs:
control-plane `gpt-6-astra:medium`, C0 `gpt-6-luna:max`, C1
`gpt-6.1-sol:low`, C2 `gpt-6.1-sol:medium`, and C3 `gpt-6.1-sol:high`.
R1/R2/R3 use one `gpt-6.1-sol` review at low/medium/high respectively.
The owner explicitly selected single-review R3. No live provider calls were made.
The catalog's runtime_provider label remains the existing `custom` adapter label;
it does not prove host adapter availability or successful execution.
Other legacy model identities remain in the catalog for route/v1 project compatibility;
`gpt-5.6-sol` and `gpt-6-sol` are removed from selectable catalog identities;
the old bundled `gpt5.6` profile itself is removed and rejected.

The owner removed the GLM/DeepSeek high-volume writer from gpt6 on
2026-09-23. No gpt6 route or fallback selects either provider. Legacy catalog
identities remain for route/v1 compatibility only.

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
