# Optional OpenAI + GLM5.3 runtime routing profile with DeepSeek fallback

This is an optional, dated runtime mapping for an Owner who has a ChatGPT
subscription and separately managed credentials for the verified `zai` and
`deepseek` providers. It does not change the vendor-neutral Core/Controlled
policy, and it is inactive unless the Owner explicitly selects
`openai-glm5.3-deepseek-fallback-2026-08-28` in the proposal, charter, or task
contract.

The evidence snapshot date is **2026-08-28**. Availability, authentication, runtime
model identifiers, pricing, quotas, and benchmark results can drift after that date.

## Machine-checked routing contract

The tests treat this JSON block as the exact opt-in contract. It is documentation, not
an executable configuration file.

```json routing-profile
{
  "profile_id": "openai-glm5.3-deepseek-fallback-2026-08-28",
  "default_active": false,
  "activation": "explicit-owner-selection",
  "evidence_date": "2026-08-28",
  "control_plane": {"model": "gpt-5.6-sol", "reasoning": "high"},
  "writers": {
    "C0_batch": {"model": "gpt-5.6-luna", "reasoning": "max"},
    "C1": {"model": "gpt-5.6-luna", "reasoning": "max"},
    "C2": {"model": "gpt-5.6-terra", "reasoning": "max"},
    "C3": {"model": "gpt-5.6-sol", "reasoning": "high"}
  },
  "validators": {
    "R2_R3_when_writer_is_openai": {
      "primary": {
        "provider": "zai",
        "model": "glm-5.3",
        "reasoning": "max",
        "reasoning_delivery": "provider-default"
      },
      "fallback": {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "reasoning": "max",
        "requires_primary_unavailable_evidence": true,
        "accepted_primary_unavailable_evidence": [
          "model-not-found",
          "authenticated-provider-outage",
          "quota-exhaustion",
          "repeated-bounded-transport-failure"
        ]
      }
    },
    "when_writer_is_glm_or_deepseek_fallback": {
      "model_source": "openai-writer-map-for-complexity",
      "reasoning_source": "openai-writer-map-for-complexity"
    }
  },
  "high_volume_deterministic_fallback": {
    "primary": {
      "provider": "zai",
      "model": "glm-5.3-flash",
      "reasoning": "max",
      "reasoning_delivery": "provider-default"
    },
    "fallback": {
      "provider": "deepseek",
      "model": "deepseek-v4-flash",
      "reasoning": "max",
      "requires_primary_unavailable_evidence": true,
      "accepted_primary_unavailable_evidence": [
        "model-not-found",
        "authenticated-provider-outage",
        "quota-exhaustion",
        "repeated-bounded-transport-failure"
      ]
    },
    "default": false,
    "requires_explicit_task_selection": true
  },
  "forbidden_defaults": [
    "gpt-5.6-sol:xhigh",
    "gpt-5.6-sol:max",
    "gpt-5.6-sol:ultra",
    "gpt-5.6-luna:low",
    "gpt-5.6-luna:medium",
    "gpt-5.6-luna:high",
    "gpt-5.6-luna:xhigh",
    "gpt-5.6-terra:low",
    "gpt-5.6-terra:medium",
    "gpt-5.6-terra:high",
    "gpt-5.6-terra:xhigh",
    "gpt-5.5:*",
    "gpt-5.4:*"
  ]
}
```

`C3` includes an unsplittable implementation after the control plane has recorded why
safe slicing is unavailable. Strict C0 main-agent work continues to use the control
plane; `C0_batch` means delegated mechanical batch work. Risk still controls gates, not
Writer capability. The control plane and OpenAI Writer map above are unchanged from the
baseline.

For an R2/R3 task whose Writer is an OpenAI model, the independent Validator is the
primary `zai/glm-5.3` route at desired reasoning `max`. Only after the main Agent records
concrete primary-unavailable evidence and the actual mapping may validation use
`deepseek/deepseek-v4-pro:max`. If GLM Flash or DeepSeek Flash is the Writer,
validation returns to the OpenAI Writer model and reasoning assigned by
the complexity map. Neither fallback Writer can validate its own candidate.

`zai/glm-5.3-flash` at desired reasoning `max` is the primary high-volume deterministic
Writer route. `deepseek/deepseek-v4-flash:max` is available only after recorded GLM Flash
unavailability and explicit task selection. This route is never the default and does not
silently replace the primary or the Pro Validator.

Accepted primary-unavailability evidence is limited to model-not-found, an authenticated
provider outage, quota exhaustion, or repeated bounded transport failure. Subjective
quality or cost preference, credential presence alone, and opaque automatic fallback do
not qualify. The selected profile pre-authorizes only the documented DeepSeek fallback
after that evidence gate; otherwise stop and record the deviation rather than switching
silently.

## Availability and authentication gate

Before activating or dispatching through this profile, fail closed unless all relevant
facts are true and recorded without exposing secrets:

1. The Owner explicitly selected the profile for this project or task. Mere file
   presence, a ChatGPT subscription, or available credentials is not activation.
2. The intended runtime exposes the requested provider, exact API model identifier, and
   reasoning support, and authentication succeeds through user-managed environment or
   credential storage.
3. The chosen route can expose the actual model/effort mapping or the task records it as
   `unknown`. An unobservable mapping forbids model-specific cost, quality, or savings
   claims.
4. R2/R3 validation remains independent of the Writer and is tied to the exact
   candidate. If the specified primary is unavailable, use the documented fallback only
   after the evidence gate; do not silently substitute the Writer or Flash.
5. No API key, token, credential value, or copied user configuration is written into
   the repository, task artifacts, prompts, or evidence.

## Hermes runtime mechanics

Hermes `delegate_task` model, provider, and reasoning overrides are global delegation
defaults, not per-task overrides. Blank override values inherit the parent. After
explicit Owner opt-in and the availability/authentication gate, generic
`delegate_task` work may be pinned globally to `gpt-5.6-luna` at `max` for the OpenAI
Writer map. Do not make that user-level change as part of Skill installation or
repository setup.

The C2 Terra route, C3 Sol route, and GLM/DeepSeek Validator or Writer routes require a
mechanism that can select model/provider/effort per task: a task-specific Codex CLI
invocation, a Hermes one-shot run, or a Hermes Kanban route. Confirm the actual mapping
when the runtime exposes it. Do not claim that a generic `delegate_task` call used a
per-task override merely because the task contract requested one.

Hermes v0.20.4 enables thinking for GLM-5.3, but does not explicitly forward native
`reasoning_effort` for GLM-5.3. The JSON therefore records desired reasoning `max` with
`reasoning_delivery` set to `provider-default`; it does not claim explicit GLM reasoning
forwarding. The exact API model identifiers in this profile are `glm-5.3` and
`glm-5.3-flash`.

Reference: [Hermes delegation documentation](https://hermes-agent.nousresearch.com/docs/zh-Hans/user-guide/features/delegation).

## Evidence snapshot and limits

The following benchmark rows are preserved evidence for the existing OpenAI Writer map.
They use different task sets, harnesses, scoring, and run shapes; their percentages and
resource observations are retained separately and are not directly mergeable into a
composite ranking, cost claim, or expected project outcome. They are not evidence for
the optional provider routes.

| Evidence source | Luna Max | Terra Max | Sol High | Preserved comparison |
|---|---:|---:|---:|---|
| DeepSWE v1.1 | 67% +/- 4% | 70% +/- 3% | 69% +/- 1% | Luna xhigh to max +10pp; Terra xhigh to max +10pp; Sol medium to high +8pp |
| CursorBench 3.2 | 61.1%; $0.39; 87,973 tokens; 61 steps | 64.9%; $2.31; 32,969 tokens; 47 steps | 63.5%; $2.79; 13,867 tokens; 32 steps | Luna xhigh to max +3.4pp; Terra xhigh to max +5.7pp; Sol medium to high +3.5pp |
| Terminal-Bench 2.1, official same Codex harness | 75.7% +/- 1.3% | 78.4% +/- 1.3% | unknown | No official same-row Sol High result; fallback routes are not benchmarked here |

Sources for the preserved OpenAI Writer-map rows:

- [DeepSWE](https://deepswe.datacurve.ai/) and [DeepSWE v1.1 notes](https://deepswe.datacurve.ai/blog/deepswe-v1-1)
- [CursorBench](https://cursor.com/cn/cursorbench) and [CursorBench methodology](https://cursor.com/blog/cursorbench)
- [Terminal-Bench 2.1](https://www.tbench.ai/leaderboard/terminal-bench/2.1)

Official GLM sources for model identifiers and reasoning semantics:

- [Z.AI chat completion](https://docs.z.ai/api-reference/llm/chat-completion)
- [GLM-5.3 guide](https://docs.z.ai/guides/llm/glm-5.3.md)
- [GLM-5.3-Flash guide](https://docs.z.ai/guides/vlm/glm-5.3-flash)
- [Z.AI parameter concepts](https://docs.z.ai/guides/overview/concept-param)

The official Z.AI documentation states that these models require thinking and support
`low`, `high`, and `max`, with `max` as the provider default. This documents the desired
route and provider-default delivery, not a same-harness performance result.

Fallback evidence only (DeepSeek Pro versus DeepSeek Flash):

- [DeepSeek reasoning update](https://api-docs.deepseek.com/news/news260813/)
- [DeepSeek chat-completion API](https://api-docs.deepseek.com/api/create-chat-completion)

The snapshot supplies no verified same-harness result for `glm-5.3`,
`glm-5.3-flash`, `deepseek-v4-pro`, or `deepseek-v4-flash` in these rows, no
project-specific acceptance rate, and no normalized price/performance comparison. Keep
each missing value `unknown`; make no cost, quality, or savings claim from these sources.

## Lightweight observation and recalibration

Task contracts may record the selected profile, actual model/effort, input/output tokens,
steps, first-pass result, reopen count, and escalation reason. Record a value only when
the runtime or review exposes it; otherwise use `unknown`. These task-local fields do not
create a mandatory ledger, release gate, historical baseline, or performance subsystem.

Review a routed tier after 10 accepted tasks in that tier, or review the whole profile
after 20 accepted tasks total with coverage of every active routed tier. Compare results
within the same complexity and risk strata, and keep task type and acceptance criteria
visible. Recalibrate earlier when model availability, pricing, or relevant benchmark
evidence changes; repeated first-pass failure or reopen appears; quota pressure affects
the route; or observed runtime mapping drifts from the contract. Recalibration proposes
a new dated profile or explicit exception; it never silently mutates this snapshot.
