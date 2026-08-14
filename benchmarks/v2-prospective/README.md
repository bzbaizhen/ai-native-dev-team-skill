# V2 prospective release trials

This directory defines how the preregistered stable V2.0 gate is audited. It contains no private project paths or trial results.

## Inclusion

- Start prospective counting only after the candidate Skill Commit is fixed.
- Include the first five tasks that are genuinely requested, accepted into their project stable branch, and comparable to a declared V1 stratum.
- Do not count synthetic scenarios, repository housekeeping created only to inflate sample size, tasks completed before the candidate, or tasks without immutable acceptance evidence.
- Preserve non-comparable tasks in the private manifest with an exclusion reason. Do not silently omit failed or inconvenient trials.
- Use anonymized project aliases in any public summary.

## Evidence

Each trial points to a private main-agent-owned JSONL ledger and records:

- candidate Skill Commit;
- task candidate and stable Commits;
- hard-gate audit;
- critical defect escape, material quality regression, scope violation, write conflict, and recovery status;
- comparability decision and exclusion reason when applicable.

The private manifest follows `release-trial-manifest.schema.json`. Run:

```text
python skills/bootstrap-ai-native-dev-team/scripts/v2_release_gate.py --manifest <PRIVATE_MANIFEST>
```

Exit `0` means the first required comparable tasks passed the recorded mechanism and quality gates. Exit `1` means the release gate is not yet met. Exit `2` means the manifest itself is invalid.

This command does not prove efficiency improvement. Formal claims still require 15–20 comparable accepted tasks and the preregistered stratified comparison.
