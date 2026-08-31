# GPT-5.6 Validator Assurance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an additive `route/v2` GPT-5.6 Validator assurance profile while preserving the existing `route/v1` profile and behavior byte-for-byte.

**Architecture:** Keep v1 and v2 as explicit versioned contracts in one resolver, dispatching validation and resolution by API/profile schema version. Model R1/R2 as ordered single-route escalation chains and R3 as a strict dual-route set; never execute a provider. Package both profiles and synchronize installations only after repository tests and exact-candidate validation.

**Tech Stack:** Python 3.13 standard library, JSON Schema assets, `unittest`, Git, repository migration/install CLI.

**Spec:** `docs/superpowers/specs/2026-08-31-gpt56-validator-assurance-design.md`

## Global Constraints

- Preserve `skills/ai-native-model-router/assets/profiles/openai-glm5.3-deepseek-fallback-2026-08-28.json` byte-for-byte.
- Preserve all `route/v1` behavior and schemas.
- New Validator routes use only `gpt-5.6-luna:max`, `gpt-5.6-terra:max`, and `gpt-5.6-sol:high`.
- R3 requires Terra and Sol together and never degrades to one Validator.
- Valid Validator rejection is not routing failure.
- File presence never activates a profile; every request selects a profile explicitly.
- `enforcement_status` remains `not-executed`.
- No secrets, credentials, endpoints, prices, commands, or transport instructions enter contracts.
- Do not push, merge, release, deploy, or delete the preserved profile.

---

### Task 1: Freeze v1 and define v2 schemas/profile

**Files:**
- Create: `skills/ai-native-model-router/assets/model-router-config.v2.schema.json`
- Create: `skills/ai-native-model-router/assets/route-request.v2.schema.json`
- Create: `skills/ai-native-model-router/assets/route-decision.v2.schema.json`
- Create: `skills/ai-native-model-router/assets/profiles/openai-gpt5.6-validator-assurance-2026-08-31.json`
- Modify: `tests/test_router_contracts.py`
- Modify: `tests/test_model_router.py`

**Interfaces:**
- Consumes: v1 route/profile conventions and provider catalog identities.
- Produces: machine-readable v2 config/request/decision surfaces and a bundled schema-v2 profile.

- [ ] **Step 1: Write failing contract tests**

Add tests that assert the old profile SHA-256/blob bytes match the frozen fixture, all six schemas are strict JSON Schema objects, the v2 request has `risk_level` and `route_failure_evidence`, the v2 decision has `selected_routes`, `validation_mode`, `escalation_used`, `escalation_evidence`, `same_model_as_writer`, and `validator_source`, and the new profile encodes exact R1/R2/R3 routes with no GLM/DeepSeek Validator route.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m unittest tests.test_router_contracts tests.test_model_router -v`

Expected: FAIL because v2 assets/profile are absent and profile loading/listing does not support them.

- [ ] **Step 3: Add minimal strict v2 assets**

Create strict schemas with `additionalProperties: false`, exact enums, and the fields specified by the design. Create the new profile by copying existing non-Validator slots exactly and adding `validator.assurance` with R1 Luna→Terra→Sol, R2 Terra→Sol, and R3 Terra+Sol.

- [ ] **Step 4: Run schema/profile tests and verify partial GREEN**

Run: `python -m unittest tests.test_router_contracts.SchemaContractTests tests.test_model_router.CatalogAndProfileTests -v`

Expected: schema tests pass; loader-dependent tests may still fail only because resolver code has not learned v2.

### Task 2: Implement versioned profile loading and assurance resolution

**Files:**
- Modify: `skills/ai-native-model-router/scripts/resolve_route.py`
- Modify: `skills/ai-native-model-router/scripts/router_config.py`
- Modify: `tests/test_model_router.py`
- Modify: `tests/test_router_contracts.py`

**Interfaces:**
- Consumes: v2 assets/profile from Task 1.
- Produces: `validate_route_request_v2`, version-dispatched profile/config validation, and deterministic v2 `RouteDecision` objects.

- [ ] **Step 1: Write failing R1/R2 tracer tests**

Add one test for R1 selecting Luna and reporting same-model identity, then one test for Luna unavailable with accepted route-bound evidence escalating to Terra. Add R2 Terra selection and Terra→Sol escalation tests.

- [ ] **Step 2: Run the tracer tests and verify RED**

Run the exact new test methods with `python -m unittest -v`.

Expected: FAIL because v2 request/profile dispatch and assurance chain resolution are missing.

- [ ] **Step 3: Implement minimal v2 single-route resolution**

Add version dispatch without changing v1 functions. Validate exact route-bound evidence, stop on unknown availability, select the first available route, expand runtime provider, and return explicit same-model/escalation fields.

- [ ] **Step 4: Run R1/R2 tests and verify GREEN**

Run the exact new methods, then `python -m unittest tests.test_model_router.ResolutionTests -v`.

Expected: all new R1/R2 tests and existing v1 resolution tests pass.

- [ ] **Step 5: Write failing R3 dual-route tests**

Add tests proving Terra+Sol are both selected only when both are available; either unknown produces unknown; unavailable with accepted evidence blocks; unaccepted evidence blocks; selected same-model status is reported without blocking.

- [ ] **Step 6: Run R3 tests and verify RED**

Expected: FAIL because strict dual assurance resolution is missing.

- [ ] **Step 7: Implement minimal R3 dual resolution**

Require both routes, never degrade to one, preserve deterministic route ordering, return `validation_mode: dual`, and include Owner-boundary limitations when blocked.

- [ ] **Step 8: Run all router tests and verify GREEN**

Run: `python -m unittest tests.test_router_contracts tests.test_model_router -v`

Expected: PASS with no v1 regressions.

### Task 3: Update skill docs and package inventory

**Files:**
- Modify: `skills/ai-native-model-router/SKILL.md`
- Modify: `skills/ai-native-model-router/references/interface.md`
- Modify: `skills/ai-native-model-router/references/configuration.md`
- Modify: `skills/ai-native-model-router/references/provider-evidence.md`
- Modify: `skills/ai-native-model-router/agents/openai.yaml` only if its prompt names v1 exclusively
- Modify: `suite-manifest.json`
- Modify: `tests/validate_skill.py`
- Modify: `tests/test_suite_packaging.py`
- Modify: `tests/test_readme_v3.py` only when it asserts the former single-profile surface

**Interfaces:**
- Consumes: implemented v1/v2 resolver and exact profile IDs.
- Produces: a complete tracked-source inventory and user-facing contract navigation for both versions.

- [ ] **Step 1: Write failing packaging/documentation tests**

Require both bundled profile links, all v2 schema links, updated component version, exact sorted manifest inventory, and language that distinguishes independent v1 validation from same-family v2 assurance.

- [ ] **Step 2: Run packaging tests and verify RED**

Run: `python -m unittest tests.test_suite_packaging tests.test_readme_v3 -v`

Expected: FAIL because manifest/docs do not include v2.

- [ ] **Step 3: Update docs, version, validator inventory, and manifest**

Keep the SKILL description within 60 characters and preserve explicit selection. Explain that v2 permits same-model review and that `not-executed` is not an execution receipt. Add every new file to the sorted component inventory.

- [ ] **Step 4: Run packaging tests and verify GREEN**

Run the focused packaging tests, then `python tests/validate_skill.py` if that is the repository validator entry point.

Expected: PASS with exact inventory and no generated residue.

### Task 4: Full verification, exact-candidate review, and local integration

**Files:**
- Verify all changed files from Tasks 1–3.
- Create installation plan/receipt files outside the repository under a bounded backup directory.

**Interfaces:**
- Consumes: stable working-tree candidate.
- Produces: passing full-suite evidence, Validator reports bound to the candidate hash, a local commit, and verified install receipts.

- [ ] **Step 1: Run full tests**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS.

- [ ] **Step 2: Run CLI probes**

Run `list-profiles`, validate both profile IDs, resolve a v1 Writer request, resolve v2 R1/R2 escalation requests, and resolve v2 R3 dual selection and blocked-degradation requests.

Expected: deterministic JSON on stdout, nonzero JSON-free diagnostics on invalid input, and `enforcement_status: not-executed` in every decision.

- [ ] **Step 3: Freeze candidate identity and perform two read-only reviews**

Record status, diff, candidate patch hash, and two bounded file hashes. Run one Terra-Max and one Sol-High read-only Validator against the same candidate and current Owner decisions. Discard reports if bytes change.

- [ ] **Step 4: Correct in-scope findings and re-run affected verification**

For each accepted finding, reopen the Writer lease, add a failing regression test, implement the minimal fix, rerun focused/full tests, and invalidate earlier Validator evidence.

- [ ] **Step 5: Commit exact approved paths locally**

Stage the mathematically exact changed-path set, run `git diff --cached --check`, verify the staged diff, commit on `feat/gpt56-validator-assurance`, and prove the commit tree equals the validated candidate. Do not push.

- [ ] **Step 6: Plan, apply, and verify installation transaction**

Use `tools/migrate_suite_install.py` to plan against the current Hermes default skill root and the current Codex skill root. Preserve backups, apply only with the exact plan digest, verify both roots, and read back old/new profile bytes and CLI behavior from the installed Hermes copy.

- [ ] **Step 7: Report exact state**

Report branch/commit, tests, Validator identities, install receipt and backup paths, both selectable profile IDs, and explicit non-effects: not pushed, not merged, not released, and no profile automatically activated.
