# V2 prospective release trials

This directory defines how the preregistered stable V2.0 gate is audited. It contains no private project paths or trial results.

## Inclusion

- Before counting, place `release-source-registry.json` in a dedicated anchor repository and fix its freeze Commit outside the trial Manifest. The registry freezes the candidate, five-task policy, approved source roster, each private project identity, Git root, stable branch, ledger path, and the byte length plus SHA-256 of its pre-trial ledger prefix.
- For every later `task_ready`, add exactly one `registrations/NNNNNN.json` receipt in its own linear Git Commit before the outcome is known. The receipt fixes the global sequence, source/task identity, request digest, C/R/topology, exact V1 stratum, comparability, and candidate Commit.
- Close the window with one final Commit that adds only `release-window-closure.json`, including the finalized trial Manifest SHA-256. Supply the freeze and closed-head SHAs to the verifier from an independently protected append-only ref, signed record, or trusted timestamp receipt; never let the trial Manifest choose them.
- The release Manifest must map every anchored receipt, including unfinished and non-comparable work. The anchor history, not the Manifest, defines the trial universe.
- Include the first five tasks by that sequence that are genuinely requested, accepted into their project stable branch, and comparable to a V1 complexity/risk/topology stratum declared at `task_ready`.
- Do not count synthetic scenarios, repository housekeeping created only to inflate sample size, tasks completed before the candidate, or tasks without immutable acceptance evidence.
- One `(candidate Commit, project evidence identity, task_id)` can appear only once. Preserve non-comparable, unfinished, failed, and inconvenient trials; a later success cannot replace an earlier comparable failure.
- Use anonymized project aliases in any public summary.

## Evidence

The private evidence set records:

- the external freeze/head Commit pair, append-only registration Commit chain, frozen source registry, anchored final Manifest digest, and each current full-ledger SHA-256;
- anchored request digests and content-addressed acceptance JSON records;
- candidate Skill Commit, registration sequence, strictly matching C/R/topology V1 stratum, task candidate Commit, and stable Commit;
- complete-ledger source-level hard-gate audit, candidate-to-stable ancestry, and stable-branch ancestry;
- critical defect escape, material quality regression, scope violation, write conflict, and recovery status;
- disposition, comparability decision, and exclusion reason when applicable.

Use `release-source-registry.schema.json`, `release-registration-receipt.schema.json`, `release-anchor-closure.schema.json`, `release-trial-evidence.schema.json`, and `release-trial-manifest.schema.json`. Run:

All relative paths in the frozen registry and Manifest resolve from the Manifest directory.

```text
python skills/bootstrap-ai-native-dev-team/scripts/v2_release_gate.py \
  --manifest <PRIVATE_MANIFEST> \
  --anchor-repo <PRIVATE_ANCHOR_REPO> \
  --anchor-freeze-commit <TRUSTED_FREEZE_SHA> \
  --anchor-head-commit <TRUSTED_CLOSED_HEAD_SHA>
```

Exit `0` means the first required comparable tasks passed source integrity, registry completeness, ordering, Git, evidence, mechanism, and quality gates. Exit `1` means the release gate is not yet met. Exit `2` means the Manifest contract is invalid.

The command rejects merge history, receipt edits/deletes, non-continuous registration, a self-rehashed replacement registry, unanchored `task_ready`, source-level hard-gate violations in the candidate window, and a candidate Commit that never reached the stable Commit. It cannot prove that a local ref was remotely protected or when it was pushed; the trusted freeze/head pair must come from an independent control. It does not prove efficiency improvement. Formal claims still require 15–20 unique comparable accepted tasks and the preregistered stratified comparison.
