# Benchmark methodology

## Measurement types

- `historical_reconstruction`: derive ranges from existing conversation event logs, Git, worktrees, task records, and evidence files. Preserve uncertainty and never manufacture missing task events.
- `prospective_event_ledger`: record a small set of task events during V2 execution, then join them with deterministic Git and evidence facts.

Historical and prospective measurements must remain labeled. They are not interchangeable datasets.

## Active-time estimate

For historical conversation logs, sort timestamped activity events per thread and sum consecutive intervals with two caps:

- lower estimate: cap each interval at 5 minutes;
- upper estimate: cap each interval at 15 minutes.

Exclude approval guardians, duplicated history mirrors, unrelated threads, and long user or overnight waits. Sum parallel worker time only as cumulative Agent active time; never present it as user wall-clock waiting time.

## Allocation

Classify task evidence by its dominant responsibility:

- product and owner decisions;
- implementation and defect repair;
- independent QA and quality verification;
- contracts, governance, environment, Git, CI, and status maintenance;
- compliance, source, or research preparation.

Ranges are used when a thread spans categories or the evidence cannot support minute-level precision.

## Comparison rules

- Compare tasks within the same complexity, risk, and topology strata.
- Define completion as accepted into the stable branch, not worker completion or Commit creation.
- Report `READY → accepted` and `dev_complete → accepted` separately.
- Do not infer token, model, or cash cost when the runtime record is missing.
- Treat material state disagreement with Git or evidence as a quality failure.
- Disclose environment changes separately. The pre-V2 PowerShell repair is excluded from V2 attribution.

## Publication boundary

Private evidence packages retain source paths, thread IDs, exact timestamps, and audit pointers. Public summaries contain only anonymous cases, aggregate ranges, method, version, and limitations.
