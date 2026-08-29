# Optional local prospective metrics

Use this reference only when the main agent explicitly selects local prospective
measurement for a task set. Metrics are optional for both Core and Controlled and do
not add a routing layer, acceptance authority, or go/no-go threshold.

The main agent is the sole ledger writer. Record an event only after it actually occurs,
using the schema in [metrics-event.schema.json](metrics-event.schema.json). Keep the
ledger local to the selected project unless the Owner separately authorizes another
location. Writers and Validators supply handoff facts; they do not append the ledger.

## Lifecycle and observations

Use only these lifecycle events: task_ready, worker_started, dev_complete, qa_complete,
accepted, blocked, reopened, and cancelled. Start with task_ready before prospective
work. Record the selected Core/Controlled route and C/R tier at task_ready.

Record model, provider, reasoning, token, and cost fields only when the runtime or a
reviewed source exposes them. Store absent values as null (display them as unknown if a
consumer needs text). Do not estimate, backfill, or turn a missing observation into a
cost claim.

When `writer` is present, it records the required boolean worker context fields
`skill_loaded`, `repo_wide_search_used`, and `out_of_scope_reads`. A true
`skill_loaded` or `out_of_scope_reads` value is a hard-gate finding. Snapshots expose
the worker context per task, and audits expose it under `context.worker_context`.
`repo_wide_search_used` is not a delivery failure; when true, it makes that task's
`context_saving_claim` false, so no context-saving claim is available for that task.

## Commands

All commands use only the Python standard library. Selecting a ledger is explicit:

~~~text
python scripts/team_metrics.py record --ledger <events.jsonl> --event-file <event.json>
python scripts/team_metrics.py snapshot --ledger <events.jsonl> --output <snapshot.json>
python scripts/team_metrics.py audit --ledger <events.jsonl> --output <audit.json>
python scripts/team_metrics.py compare --left <snapshot-a.json> --right <snapshot-b.json> --output <compare.json>
~~~

Record appends one validated event. Snapshot reports task_ready-to-accepted cycle time,
dev_complete-to-accepted integration wait, observed wall-clock active/governance
minutes, first-pass independent-validation status, reopen visibility, routing tier, and
only actually observed runtime values. Incomplete tasks retain null duration values;
the tool never uses the current time as an invented endpoint.

Audit checks ledger integrity and the following hard gates:

- a Writer started without approval;
- a Writer loaded the full team Skill (`WRITER_LOADED_FULL_TEAM_SKILL`);
- a Writer read out-of-scope content (`WRITER_OUT_OF_SCOPE_READS`);
- a Writer supplied an invalid path (`INVALID_WRITER_PATH`), such as an above-root
  traversal, a component emptied by trailing-space/dot trimming, NTFS
  alternate-data-stream syntax, or a Windows device/NT namespace prefix;
- overlapping active path ownership;
- a new Writer while another task has integration backlog and no recorded reason;
- material acceptance without independent same-candidate validation;
- acceptance without exact candidate and stable identity or executable rollback;
- R3 acceptance without Owner approval;
- reused validation evidence after a reopen or candidate change.

Compare is descriptive: it shows observed snapshot deltas without a fixed threshold or
qualification decision. DQR remains the delivery-acceptance protocol; a metrics result
cannot replace its candidate, validation, authority, limitation, rollback, or recovery
evidence.

Path safety is checked before ordinary drive, UNC, or root parsing. The canonicalizer
rejects Windows namespace prefixes in both backslash and slash-normalized spellings:
extended drive and UNC forms (`\\?\`, `//?/`), device and pipe forms (`\\.\`,
`//./`), and NT namespace forms (`\??\`, `/??/`; the equivalent `\\??\` and
`//??/` forms are rejected too). A rejected path uses the existing controlled path
error, emits the hard-gate `INVALID_WRITER_PATH` during replay, and causes that whole
`worker_started` event to acquire no active path lease. Ordinary `C:/` drives,
`//server/share` UNC paths, POSIX-rooted paths, and relative paths remain supported.
