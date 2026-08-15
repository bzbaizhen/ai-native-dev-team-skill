# Prospective delivery metrics

Use metrics only when the main agent explicitly selects delivery measurement or the
Release Audit layer. Metrics compare delivery flow, not activity, and never become a
mandatory artifact for ordinary Core or Controlled work. Historical reconstruction and
prospective ledgers are different datasets.

## Ownership and location

When measurement is selected, the main agent is the only writer to
`.ai-team/metrics/events.jsonl`. Workers return `metrics_handoff`; the main agent
validates and records it. Keep one JSON object per line, UTF-8, ordered per task by
timestamp.

The schema is [metrics-event.schema.json](metrics-event.schema.json). The standard-library CLI is `scripts/team_metrics.py`.

## Optional delivery measurement

For a selected prospective measurement run, record the material-task lifecycle:

1. `task_ready`
2. `worker_started` when delegated
3. `dev_complete`
4. `qa_complete` when independent validation applies
5. `accepted` only after the exact change is in the stable branch

Record `blocked`, `reopened`, and `cancelled` when they occur. A worker Commit, `dev_complete`, or `qa_complete` is not acceptance.

## Fields that make the gates auditable

At `task_ready` record complexity, risk, route/topology, governance profile, and whether the task is a material behavior change.

Release-trial fields such as `release_trial_registration_sequence`, `skill_candidate_commit`,
`release_trial_comparable`, the frozen `v1_baseline_id`, and its exact
`v1_baseline_stratum` belong to the explicit [Release Audit](release-audit.md) layer,
not ordinary delivery.

At `worker_started` record the approved Writer, declared owned paths, capability and reasoning tiers, whether the Writer loaded this team Skill, and any integration-backlog override reason.

At `qa_complete` record the candidate Commit, result, and whether validation was independent.

At `accepted` record the candidate Commit, stable-branch Commit, status/evidence agreement, executable rollback, and owner approval status.

Every event may add:

- `active_minutes`: Agent working time attributable since the previous event;
- `governance_minutes`: the subset spent on contracts, repeated preflight, coordination, Git/CI administration, or status/evidence maintenance;
- `metadata`: project-specific non-secret facts.

`governance_minutes` must not exceed `active_minutes`. Do not estimate missing token, model, or cash cost.

## Optional commands

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

`audit` exits nonzero when it finds a hard-gate violation. `compare` emits `unavailable`
rather than inventing a percentage when either denominator is missing or zero.

Do not run the formal Release Audit gate from this ordinary measurement reference. For
stable qualification, formal efficiency comparison, historical-baseline qualification,
or external evidence freeze, load [release-audit.md](release-audit.md), obtain the
required approval, and follow its freeze, registration, schema, verifier, and
integration-proof rules.

## Primary measures when selected

- median `task_ready → accepted` cycle hours;
- median `dev_complete → accepted` integration-wait hours;
- accepted tasks per cumulative active Agent hour;
- governance share of cumulative active time;
- eligible delegated C0/C1 work routed to Economy or Standard;
- first-pass independent QA rate;
- reopened task rate;
- hard-gate violations.

Compare only like complexity, risk, and topology strata. Separate environment changes
from Skill effects, and do not publish an efficiency percentage without a comparable
denominator.

## Measurement hard gates

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
