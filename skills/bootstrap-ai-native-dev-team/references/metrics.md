# Prospective delivery metrics

Use metrics to compare delivery flow, not to reward activity. Historical reconstruction and prospective ledgers are different datasets.

## Ownership and location

The main agent is the only writer to `.ai-team/metrics/events.jsonl`. Workers return `metrics_handoff`; the main agent validates and records it. Keep one JSON object per line, UTF-8, ordered per task by timestamp.

The schema is [metrics-event.schema.json](metrics-event.schema.json). The standard-library CLI is `scripts/team_metrics.py`.

## Required lifecycle

For every material task record:

1. `task_ready`
2. `worker_started` when delegated
3. `dev_complete`
4. `qa_complete` when independent validation applies
5. `accepted` only after the exact change is in the stable branch

Record `blocked`, `reopened`, and `cancelled` when they occur. A worker Commit, `dev_complete`, or `qa_complete` is not acceptance.

## Fields that make the gates auditable

At `task_ready` record complexity, risk, route/topology, governance profile, and whether the task is a material behavior change.

For a prospective release trial, also record `release_trial_registration_sequence`, `skill_candidate_commit`, `release_trial_comparable`, the frozen `v1_baseline_id`, and its exact `v1_baseline_stratum`. The sequence is global across the frozen source roster, starts at `1`, never repeats, and is assigned before outcome is known.

At `worker_started` record the approved Writer, declared owned paths, capability and reasoning tiers, whether the Writer loaded this team Skill, and any integration-backlog override reason.

At `qa_complete` record the candidate Commit, result, and whether validation was independent.

At `accepted` record the candidate Commit, stable-branch Commit, status/evidence agreement, executable rollback, and owner approval status.

Every event may add:

- `active_minutes`: Agent working time attributable since the previous event;
- `governance_minutes`: the subset spent on contracts, repeated preflight, coordination, Git/CI administration, or status/evidence maintenance;
- `metadata`: project-specific non-secret facts.

`governance_minutes` must not exceed `active_minutes`. Do not estimate missing token, model, or cash cost.

## Commands

Record an event:

```powershell
python scripts/team_metrics.py record --ledger .ai-team/metrics/events.jsonl --task TASK-001 --event task_ready --complexity C1 --risk R1 --topology single-worker --governance-profile lean --material-behavior-change false
```

Create a snapshot:

```powershell
python scripts/team_metrics.py snapshot --ledger .ai-team/metrics/events.jsonl --output .ai-team/metrics/snapshot.json
```

Audit hard gates:

```powershell
python scripts/team_metrics.py audit --ledger .ai-team/metrics/events.jsonl
```

Compare two compatible snapshots:

```powershell
python scripts/team_metrics.py compare --baseline baseline.json --current current.json
```

`audit` exits nonzero when it finds a hard-gate violation. `compare` emits `unavailable` rather than inventing a percentage when either denominator is missing or zero.

Audit the first-five-task stable-release gate:

```powershell
python scripts/v2_release_gate.py --manifest <PRIVATE_TRIAL_MANIFEST> --anchor-repo <PRIVATE_ANCHOR_REPO> --anchor-freeze-commit <TRUSTED_FREEZE_SHA> --anchor-head-commit <TRUSTED_CLOSED_HEAD_SHA>
```

At the external freeze Commit, record the candidate, five-task policy, source roster, project identity, stable branch, ledger path, byte length, and SHA-256 of each pre-trial ledger prefix using [release-source-registry.schema.json](release-source-registry.schema.json). Freeze every allowed V1 baseline identity, exact stratum, eligibility flags, and the SHA-256 of an evidence object that follows [release-v1-baseline-evidence.schema.json](release-v1-baseline-evidence.schema.json). Each baseline object must enumerate source blobs from that same freeze Commit with unique IDs, source revisions, normalized relative POSIX paths, SHA-256 digests, evidence kinds, and supported claims. The set must cover task identity, stratum, and acceptance; formal-efficiency eligibility additionally requires an `efficiency_denominator` claim supported by a `metrics_record`. Before each task outcome, add one linear Git Commit containing only a receipt that follows [release-registration-receipt.schema.json](release-registration-receipt.schema.json). At the cutoff, hash the full ledgers, finalize [release-trial-manifest.schema.json](release-trial-manifest.schema.json), then end with a Commit that adds only [release-anchor-closure.schema.json](release-anchor-closure.schema.json) and anchors that Manifest digest. The verifier must receive the immutable freeze and closed-head SHAs outside the Manifest. Request and acceptance records follow [release-trial-evidence.schema.json](release-trial-evidence.schema.json).

The anchor history enumerates the task universe; the Manifest only maps outcomes. The gate requires the ledger and Manifest to cover every anchored receipt, rejects unanchored `task_ready`, treats every source-level audit violation triggered inside the candidate window as blocking, verifies stable-branch reachability plus the accepted trial's strict `integration_proof`, and re-hashes every declared V1 source blob from the exact freeze Commit. `same_commit` requires candidate/stable SHA equality. `same_tree` requires a retained full candidate ref and verifier-recomputed equal Git tree IDs; it carries evidence by exact tree identity and does not claim QA was rerun on the stable Commit. `same_tree` is ineligible for history-sensitive, LFS/filter, submodule-content, generated, or external dependencies. Comparable receipt, ledger, and Manifest records must name the same frozen V1 baseline identity and exact C/R/topology stratum. Only baselines with reconstructable denominators may contribute to the later formal-efficiency sample. Content-addressing proves what was frozen and whether it changed; it does not prove that the source material was truthful or qualified, so retain human source review. Preserve excluded, unfinished, and failed trials; do not cherry-pick later successes. Local Git cannot prove remote ref protection or push time, so use a protected append-only ref, signed record, or trusted timestamp receipt as the independent control.

## Primary measures

- median `task_ready → accepted` cycle hours;
- median `dev_complete → accepted` integration-wait hours;
- accepted tasks per cumulative active Agent hour;
- governance share of cumulative active time;
- eligible delegated C0/C1 work routed to Economy or Standard;
- first-pass independent QA rate;
- reopened task rate;
- hard-gate violations.

Compare only like complexity, risk, and topology strata. Separate environment changes from Skill effects.

## Hard gates

The audit checks for:

- a Worker loading the complete team Skill;
- an unapproved Writer;
- overlapping declared path ownership;
- a new Writer opened while integration backlog exists without a reason;
- C0 delegated work using Frontier without an escalation reason;
- material acceptance without passed independent validation on the same Commit;
- acceptance without a full stable Commit, status/evidence agreement, or executable rollback;
- R3 acceptance without explicit Owner approval.

The ledger makes violations visible; it does not replace repository permissions, CI, or human authority.
