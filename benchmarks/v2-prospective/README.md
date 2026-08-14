# V2 prospective release trials

This directory defines how the preregistered stable V2.0 gate is audited. It contains no private project paths or trial results.

## Inclusion

- Before counting, freeze the candidate Commit and the complete approved source roster. Record each private project identity, Git root, stable branch, ledger path, and the byte length plus SHA-256 of its pre-trial ledger prefix in a content-addressed source registry.
- For every later `task_ready`, assign one global continuous `registration_sequence` before the outcome is known. The release Manifest must cover every `task_ready` from candidate freeze through its declared audit cutoff, including unfinished and non-comparable work.
- Include the first five tasks by that sequence that are genuinely requested, accepted into their project stable branch, and comparable to a V1 complexity/risk/topology stratum declared at `task_ready`.
- Do not count synthetic scenarios, repository housekeeping created only to inflate sample size, tasks completed before the candidate, or tasks without immutable acceptance evidence.
- One `(candidate Commit, project evidence identity, task_id)` can appear only once. Preserve non-comparable, unfinished, failed, and inconvenient trials; a later success cannot replace an earlier comparable failure.
- Use anonymized project aliases in any public summary.

## Evidence

The private evidence set records:

- the hashed frozen source registry and each current full-ledger SHA-256;
- content-addressed request and acceptance JSON records;
- candidate Skill Commit, registration sequence, declared V1 stratum, task candidate Commit, and stable Commit;
- complete-ledger cross-task hard-gate audit and stable-branch ancestry;
- critical defect escape, material quality regression, scope violation, write conflict, and recovery status;
- disposition, comparability decision, and exclusion reason when applicable.

Use `release-source-registry.schema.json`, `release-trial-evidence.schema.json`, and `release-trial-manifest.schema.json`. Run:

All relative paths in the frozen registry and Manifest resolve from the Manifest directory.

```text
python skills/bootstrap-ai-native-dev-team/scripts/v2_release_gate.py --manifest <PRIVATE_MANIFEST>
```

Exit `0` means the first required comparable tasks passed source integrity, registry completeness, ordering, Git, evidence, mechanism, and quality gates. Exit `1` means the release gate is not yet met. Exit `2` means the Manifest contract is invalid.

This command cannot prove an external task that was never recorded or authenticity beyond the supplied private evidence. It does not prove efficiency improvement. Formal claims still require 15–20 unique comparable accepted tasks and the preregistered stratified comparison.
