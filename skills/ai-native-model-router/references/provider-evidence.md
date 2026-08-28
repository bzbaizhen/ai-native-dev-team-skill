# Provider identity evidence

The catalog is a dated, machine-checked identity snapshot. It records provider
names, runtime provider labels, exact model IDs, reasoning capabilities, and
delivery semantics only. It contains no authentication material, endpoints,
prices, or transport instructions.

The preserved profile maps the control plane to `openai/gpt-5.6-sol:high`, C0
batch and C1 Writers to `openai/gpt-5.6-luna:max`, C2 to
`openai/gpt-5.6-terra:max`, and C3 to `openai/gpt-5.6-sol:high`.
Independent validation uses `zai/glm-5.3:max` when the Writer is OpenAI, with
`deepseek/deepseek-v4-pro:max` as an evidence-gated fallback. High-volume
deterministic writing uses `zai/glm-5.3-flash:max`, with
`deepseek/deepseek-v4-flash:max` under the same gate.

The exact accepted evidence is, in order:

1. `model-not-found`
2. `authenticated-provider-outage`
3. `quota-exhaustion`
4. `repeated-bounded-transport-failure`

These strings are routing evidence supplied by the caller, not facts that this
package discovers. Subjective quality, cost preference, credential presence, and
an unspecified error do not qualify. Availability and runtime behavior remain
caller-observed inputs and may be `unknown`.
