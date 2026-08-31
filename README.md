# AI Native Dev Team Suite v3.0.0

[English](README.md) | [简体中文](README.zh-CN.md)

A two-Skill control plane for giving Coding Agents bounded ownership, evidence-based validation, and recoverable delivery decisions.

For developers and technical leads using Codex, Hermes Agent, or another compatible Skill host. Current release: [v3.0.0](https://github.com/bzbaizhen/ai-native-dev-team-skill/releases/tag/v3.0.0).

One GitHub repository contains exactly two independently installable canonical Skills:

- `skills/ai-native-dev-team/` v3.0.0 — the required governance-entry Skill.
- `skills/ai-native-model-router/` v0.3.0 — the optional routing-extension Skill.

## What is in the Suite

| Skill | Version | Role | Owns |
|---|---:|---|---|
| `ai-native-dev-team` | 3.0.0 | governance-entry | C/R classification, Core/Controlled, topology, permissions, DQR, Git isolation, candidate identity, integration, and recovery. |
| `ai-native-model-router` | 0.3.0 | routing-extension | Deterministic provider/model resolution through `route/v1` and `route/v2` with `.ai-native/model-router.json`. It does not execute a host. |

The Team is complete on its own. Install the Router only when a project needs a local provider/model decision at the Host boundary.

## How the two Skills work together

```text
task
  -> Team semantic route slot
  -> optional Router RouteDecision via route/v1 or route/v2
  -> Host Adapter
```

The Team emits the semantic slot. Team works without the Router. If the Router is absent, provider/model mapping stays unknown or host-inherited; it is never inferred. The Router supports the compatible `route/v1` contract and additive `route/v2` assurance contract, returns a decision for the Host Adapter, and makes no claim that a provider was called or a route was enforced.

Throughout this README, Team, Router, Writer, Validator, RouteDecision, route slot, and Host Adapter are fixed names.

![Team route slot to optional Router decision and Host Adapter](docs/images/ai-native-dev-team-workflow.png)

## Install

Install each Skill independently. Every source install must copy the complete Skill directory, including its references, assets, agents metadata, and scripts.

| Skill | Codex | Hermes Agent | Manual source install |
|---|---|---|---|
| `ai-native-dev-team` | `$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/ai-native-dev-team` | Copy `skills/ai-native-dev-team/` to `$HERMES_HOME/skills/`. | Copy the complete [`skills/ai-native-dev-team/`](skills/ai-native-dev-team/) directory to the host's Skill directory. |
| `ai-native-model-router` | `$skill-installer install https://github.com/bzbaizhen/ai-native-dev-team-skill/tree/main/skills/ai-native-model-router` | Copy `skills/ai-native-model-router/` to `$HERMES_HOME/skills/`. | Copy the complete [`skills/ai-native-model-router/`](skills/ai-native-model-router/) directory to the host's Skill directory. |

There is one repository and one current GitHub Release for the suite; the optional Router is not a separate repository or release.

## 60-second quick start

After installing the Team Skill, start with a Team-only prompt:

```text
Use $ai-native-dev-team. Inspect this task and repository, separate confirmed facts, inferences, and items to verify, score C/R, and propose the smallest safe topology. Do not modify files yet.
```

When the project also has the Router installed:

```text
Use $ai-native-dev-team with $ai-native-model-router. Inspect the task, emit the semantic route slot, resolve it through route/v1 or route/v2 only after explicit profile, API/config version, and availability inputs are present, and keep Host execution separate. Do not modify files yet.
```

## Configure the Router

Create `.ai-native/model-router.json` with one of the matching versioned shapes below. The `active_profile` is explicit. Both the profile and the Router API/configuration version are explicit. A profile file's presence does not activate anything. No secrets belong in this file. Router v0.3.0 is a breaking Profile-ID rename: use `glm+deepseek` for the bundled v1 profile and `gpt5.6` for the bundled v2 profile. The previous IDs and profile filenames are removed, not aliases or supported discovery names; update existing project configurations before use.

```json
{
  "schema_version": 1,
  "router_api_version": "route/v1",
  "config_id": "project-router-2026-08-28",
  "active_profile": "glm+deepseek",
  "project_profile_dirs": [".ai-native/profiles"],
  "updated_reason": "Explicit project profile selection for route/v1."
}
```

For the additive v2 assurance contract, select the matching v2 profile and configuration version explicitly:

```json
{
  "schema_version": 2,
  "router_api_version": "route/v2",
  "config_id": "project-router-v2-2026-08-31",
  "active_profile": "gpt5.6",
  "project_profile_dirs": [".ai-native/profiles"],
  "updated_reason": "Explicit project profile selection for route/v2."
}
```

The assurance matrix is: R1: Luna Max -> Terra Max -> Sol High; R2: Terra Max -> Sol High; R3 requires strict Terra Max + Sol High and never degrades to one Validator. The API/config version and profile must match; merely having a profile file does not activate anything. See the [v1 configuration schema](skills/ai-native-model-router/assets/model-router-config.v1.schema.json), [v2 configuration schema](skills/ai-native-model-router/assets/model-router-config.v2.schema.json), and [v1 example](skills/ai-native-model-router/assets/model-router-config.example.json). Configuration-only switching is limited to an existing Host Adapter contract. New authentication, transport, or host injection requires Adapter code; the Router does not add any of those capabilities.

## Workflow

Complexity and risk are separate inputs:

| Input | Decides |
|---|---|
| `C0-C3` complexity | Decomposition, capability, and reasoning effort. |
| `R0-R3` risk | Permission level, independent review, approval, rollback, and recovery gates. |

The Team selects `Core` for ordinary low-risk work and `Controlled` when material behavior, higher complexity/risk, interface or dependency change, concurrency, production, release, or public effect needs stronger gates. DQR is the per-task acceptance protocol inside `Controlled`, not a third layer.

For material work, one path-bounded `Writer` writes the frozen scope and an independent `Validator` checks the exact candidate without silently fixing it. The Team owns the contract, permissions, topology, candidate identity, integration order, and recovery decision.

```text
inspect -> classify -> authorize -> isolate -> write -> independently validate exact candidate
       -> accept -> separately integrate/install/release -> rollback or recover when needed
```

Acceptance, integration, installation, and release are different states. A green check or accepted candidate does not authorize the next state.

## Safety boundaries

- Permissions are layered: the Team controls task scope and authority; `Writer` receives only its path lease; `Validator` is independent; Owner approval remains required where risk calls for it.
- The preserved v1 profile uses GLM-5.3 as the primary `Validator`, GLM-5.3 Flash as the explicitly selected high-volume `Writer`, and an evidence-gated DeepSeek fallback only with accepted primary-unavailable evidence. The v2 assurance profile uses the GPT-5.6 matrix above. Both require explicit matching profile/API selection; neither profile is a default or auto-activated. Availability remains an input; it is not inferred.
- Router output is advisory and not executed: every `RouteDecision` has `enforcement_status: not-executed`. The Host Adapter owns invocation, credentials, transport, and execution.
- Fallback evidence must be explicit and accepted by the active profile. An unspecified error, subjective quality judgment, or missing availability is not enough.
- For unattended non-interactive Coding CLI exec, Writer, or Validator invocations on Windows, use `pty=false`, `background=true`, and `notify_on_complete=true` by default. `pty=true` is reserved for an interactive TUI, login, or a command that genuinely requires terminal input; never apply it unconditionally to unattended exec. Final output text, a final-answer marker, or a tokens-used line is not process-exit evidence: accept only after registry status `exited` captures the exit code. Use one short bounded grace check, inspect fresh process status, terminate only the exact tracked process if necessary, never start a duplicate Writer, and never repeatedly wait/reconnect.
- A process-kill or power-loss crash journal is not automated by the migration tool. Recovery remains an explicit, separately reviewed operation.

## Migrate from the legacy name

The old component name `bootstrap-ai-native-dev-team` is migration input only. It is not a third Skill, installed alias, or discoverable route. Use the [migration tool](tools/migrate_suite_install.py); its bounded CLI provides `plan`, `apply`, `verify`, and `rollback`.

The actual install/removal target needs separate Owner authorization. `plan` is read-only; apply, verification, and rollback bind to explicit roots and the tool's returned integrity values. Running tests or accepting a candidate does not grant migration authorization.

## Repository layout

```text
skills/ai-native-dev-team/       # governance-entry Skill
skills/ai-native-model-router/   # optional routing-extension Skill
tools/migrate_suite_install.py   # bounded plan/apply/verify/rollback tool
tests/                           # Skill, routing, packaging, and contract checks
```

Start with the [Team Skill](skills/ai-native-dev-team/SKILL.md), [Router Skill](skills/ai-native-model-router/SKILL.md), [routing and topology reference](skills/ai-native-dev-team/references/routing-and-topologies.md), or [delivery review reference](skills/ai-native-dev-team/references/delivery-quality-review.md).

## Validation

Run the public checks from the repository root:

```text
python -X utf8 tests/validate_skill.py
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

These checks validate source structure, routing policy, complete Skill packaging, and documentation contracts. They do not prove host execution, provider availability, or a visual/runtime result that was not run.

## Release and license

The current release is [v3.0.0 on GitHub](https://github.com/bzbaizhen/ai-native-dev-team-skill/releases/tag/v3.0.0). Both canonical Skills are released from this repository; no separate component repository or release is implied.

Licensed under [MIT](LICENSE).
