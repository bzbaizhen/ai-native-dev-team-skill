# V2 preregistered success criteria

These criteria are fixed before V2 implementation. Passing a script or producing more Agent output is not sufficient.

## Release stages

- `v2.0.0-rc.1`: routing, progressive governance loading, metrics script, schema, templates, and scenario tests are implemented and verified.
- `v2.0.0`: the first five unique comparable real tasks in the frozen continuous registry satisfy every source, evidence, Git, mechanism, and quality gate.
- Formal efficiency claim: only after 15–20 unique comparable accepted tasks from that registry, stratified by complexity, risk, and topology.

## Must improve

At the formal audit, compared with the applicable V1 historical stratum:

- median `READY → accepted` cycle time improves by at least 20%;
- median `dev_complete → accepted` integration wait improves by at least 30%;
- accepted tasks per cumulative active Agent hour improves by at least 20%;
- implementation-phase governance and repeated-precheck share is no more than 15% and at least 25% lower in relative terms;
- at least 80% of eligible C0/C1 delegated work uses the configured economy or standard capability tier;
- every highest-tier escalation records a reason.

Do not publish a percentage for a metric whose V1 denominator cannot be reconstructed.

## Hard mechanism gates

- ordinary Implementers, Validators, and Workers fully loading the team Skill: `0`;
- simultaneous Writers for the same file: `0`;
- unapproved new Writers: `0`;
- new Writer started while `DEV_COMPLETE`, `QA_PENDING`, or `MERGE_READY` backlog exists: `0` by default;
- important acceptance not bound to an exact Commit: `0`;
- highest-cost tier for C0 batch work without an escalation record: `0`;
- material task status disagreement with Git or acceptance evidence: `0`;
- high-risk action that bypasses approval or lacks executable rollback: `0`.

## Quality guardrails

- no critical defect escapes an accepted task;
- independent validation remains separate from developer self-check for material behavior changes;
- scope violations and write conflicts do not increase;
- rollback and recovery remain executable;
- the main agent retains task graph, fact boundaries, integration decisions, and final acceptance context;
- lower-cost routing is reversed or escalated when evidence shows insufficient capability.

Historical V1 first-pass QA and cash-cost data are incomplete. V2 records these prospectively, but no before/after improvement claim is allowed until a comparable denominator exists.

## Attribution exclusion

The PowerShell/Windows host repair predates V2. First-shell-start improvements may be reported as environment evidence, but they do not count toward any V2 success threshold.
