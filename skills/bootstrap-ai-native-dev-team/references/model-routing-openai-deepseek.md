# Optional OpenAI + DeepSeek runtime routing profile

This is an optional, dated runtime mapping for an Owner who has a ChatGPT
subscription and separately managed DeepSeek credentials. It does not change the
vendor-neutral Core/Controlled policy, and it is inactive unless the Owner explicitly
selects `openai-deepseek-2026-08-20` in the proposal, charter, or task contract.

The evidence snapshot date is **2026-08-20**. Availability, authentication, runtime
model identifiers, pricing, quotas, and benchmark results can drift after that date.

## Machine-checked routing contract

The tests treat this JSON block as the exact opt-in contract. It is documentation, not
an executable configuration file.

```json routing-profile
{
  "profile_id": "openai-deepseek-2026-08-20",
  "default_active": false,
  "activation": "explicit-owner-selection",
  "evidence_date": "2026-08-20",
  "control_plane": {"model": "gpt-5.6-sol", "reasoning": "high"},
  "writers": {
    "C0_batch": {"model": "gpt-5.6-luna", "reasoning": "max"},
    "C1": {"model": "gpt-5.6-luna", "reasoning": "max"},
    "C2": {"model": "gpt-5.6-terra", "reasoning": "max"},
    "C3": {"model": "gpt-5.6-sol", "reasoning": "high"}
  },
  "validators": {
    "R2_R3_when_writer_is_openai": {"model": "deepseek-v4-pro", "reasoning": "max"},
    "when_writer_is_deepseek_fallback": {"model_source": "openai-writer-map-for-complexity", "reasoning_source": "openai-writer-map-for-complexity"}
  },
  "high_volume_deterministic_fallback": {"model": "deepseek-v4-flash", "reasoning": "max", "default": false, "requires_explicit_task_selection": true},
  "forbidden_defaults": ["gpt-5.6-sol:xhigh", "gpt-5.6-sol:max", "gpt-5.6-sol:ultra", "gpt-5.6-luna:low", "gpt-5.6-luna:medium", "gpt-5.6-luna:high", "gpt-5.6-luna:xhigh", "gpt-5.6-terra:low", "gpt-5.6-terra:medium", "gpt-5.6-terra:high", "gpt-5.6-terra:xhigh", "gpt-5.5:*", "gpt-5.4:*"]
}
```

`C3` includes an unsplittable implementation after the control plane has recorded why
safe slicing is unavailable. Strict C0 main-agent work continues to use the control
plane; `C0_batch` means delegated mechanical batch work. Risk still controls gates, not
Writer capability. For an R2/R3 task whose Writer is an OpenAI model, the independent
Validator is `deepseek-v4-pro` at `max`. If an explicitly selected DeepSeek fallback is
the Writer, the Validator returns to the OpenAI Writer model and effort assigned by the
task's complexity tier. This snapshot does not choose the DeepSeek fallback Writer
model; record that per-task choice explicitly or stop.

`deepseek-v4-flash` at `max` is only an explicitly selected, high-volume deterministic
fallback. It is not the default Validator and does not automatically replace an
unavailable Pro route. The forbidden entries above are guardrails against silently
turning unsupported effort/model choices into defaults; they are not fallback options.

## Availability and authentication gate

Before activating or dispatching through this profile, fail closed unless all relevant
facts are true and recorded without exposing secrets:

1. The Owner explicitly selected the profile for this project or task. Mere file
   presence, a ChatGPT subscription, or available credentials is not activation.
2. The intended runtime exposes the requested model, provider, and reasoning effort,
   and authentication succeeds through user-managed environment or credential storage.
3. The chosen route can expose the actual model/effort mapping or the task records it as
   `unknown`. An unobservable mapping forbids model-specific cost or savings claims.
4. R2/R3 validation remains independent of the Writer and is tied to the exact
   candidate. If the specified Validator is unavailable, stop; do not silently
   substitute the Writer or Flash.
5. No API key, token, credential value, or copied user configuration is written into
   the repository, task artifacts, prompts, or evidence.

Try the same model/effort through another already authorized per-task route before
changing the mapping. If that still fails, re-slice safely or ask the Owner to amend the
selected profile. A route that does not match this contract is a profile deviation, not
a successful fallback. Record the deviation and escalation reason; never infer a cost
advantage from a model name alone.

## Hermes runtime mechanics

Hermes `delegate_task` model, provider, and reasoning overrides are global delegation
defaults, not per-task overrides. Blank override values inherit the parent. After
explicit Owner opt-in and the availability/authentication gate, generic
`delegate_task` work may be pinned globally to `gpt-5.6-luna` at `max` for this profile.
Do not make that user-level change as part of Skill installation or repository setup.

The C2 Terra route, C3 Sol route, and DeepSeek Validator route require a mechanism that
can select model/provider/effort per task: a task-specific Codex CLI invocation, a
Hermes one-shot run, or a Hermes Kanban route. Confirm the actual mapping when the
runtime exposes it. Do not claim that a generic `delegate_task` call used a per-task
override merely because the task contract requested one.

Reference: [Hermes delegation documentation](https://hermes-agent.nousresearch.com/docs/zh-Hans/user-guide/features/delegation).

## Evidence snapshot and limits

These benchmarks use different task sets, harnesses, scoring, and run shapes. Their
percentages and resource observations are retained as separate evidence; they are not
directly mergeable into a composite ranking, cost claim, or expected project outcome.

| Evidence source | Luna Max | Terra Max | Sol High | Preserved comparison |
|---|---:|---:|---:|---|
| DeepSWE v1.1 | 67% +/- 4% | 70% +/- 3% | 69% +/- 1% | Luna xhigh to max +10pp; Terra xhigh to max +10pp; Sol medium to high +8pp |
| CursorBench 3.2 | 61.1%; $0.39; 87,973 tokens; 61 steps | 64.9%; $2.31; 32,969 tokens; 47 steps | 63.5%; $2.79; 13,867 tokens; 32 steps | Luna xhigh to max +3.4pp; Terra xhigh to max +5.7pp; Sol medium to high +3.5pp |
| Terminal-Bench 2.1, official same Codex harness | 75.7% +/- 1.3% | 78.4% +/- 1.3% | unknown | No official same-row Sol High or DeepSeek Pro result |

Sources:

- [DeepSWE](https://deepswe.datacurve.ai/) and [DeepSWE v1.1 notes](https://deepswe.datacurve.ai/blog/deepswe-v1-1)
- [CursorBench](https://cursor.com/cn/cursorbench) and [CursorBench methodology](https://cursor.com/blog/cursorbench)
- [Terminal-Bench 2.1](https://www.tbench.ai/leaderboard/terminal-bench/2.1)
- [DeepSeek reasoning update](https://api-docs.deepseek.com/news/news260813/) and [chat-completion API](https://api-docs.deepseek.com/api/create-chat-completion)

The snapshot supplies no official same-row Terminal-Bench result for Sol High or
DeepSeek Pro, no project-specific acceptance rate, and no normalized price/performance
comparison. Keep each missing value `unknown` rather than extrapolating it.

## Lightweight observation and recalibration

Task contracts may record the selected profile, actual model/effort, input/output
tokens, steps, first-pass result, reopen count, and escalation reason. Record a value
only when the runtime or review exposes it; otherwise use `unknown`. These task-local
fields do not create a mandatory ledger, release gate, historical baseline, or
performance subsystem.

Review a routed tier after 10 accepted tasks in that tier, or review the whole profile
after 20 accepted tasks total with coverage of every active routed tier. Compare results
within the same complexity and risk strata, and keep task type and acceptance criteria
visible. Recalibrate earlier when model availability, pricing, or relevant benchmark
evidence changes; repeated first-pass failure or reopen appears; quota pressure affects
the route; or observed runtime mapping drifts from the contract. Recalibration proposes
a new dated profile or explicit exception; it never silently mutates this snapshot.
