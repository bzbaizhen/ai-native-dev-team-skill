# Release Audit layer

Load this reference only after an explicit request for one of these scopes:

- stable-version qualification;
- a formal efficiency comparison;
- historical-baseline qualification; or
- an external evidence freeze.

The word “release”, “deploy”, or “publish” alone is not enough. Ordinary delivery stays
in [Controlled](controlled.md) with `release_audit=false`. Obtain Owner approval for the
audit scope and any external write before activating this layer.

## Freeze the audit inputs

At the approved audit boundary, freeze the candidate, source roster, eligible V1
baseline identities, and trusted Git freeze/head identities. Hash every frozen baseline
object using [release-v1-baseline-evidence.schema.json](release-v1-baseline-evidence.schema.json)
and enumerate content-addressed source blobs from the same freeze Commit that support
task identity, stratum, and acceptance. Require a metrics source supporting the
denominator before marking a baseline formally efficiency-comparable. Frozen-content
integrity is evidence about the snapshot, not automatic proof that historical claims are
true; retain human qualification.

Use [release-source-registry.schema.json](release-source-registry.schema.json) for the
source roster and [release-trial-manifest.schema.json](release-trial-manifest.schema.json)
for the candidate trial universe. Keep the trusted freeze/head SHAs outside the Manifest
so they identify the snapshot without defining the task universe or rewriting it.

## Register and close each outcome

Before each outcome, append exactly one new linear task-ready Commit using
[release-registration-receipt.schema.json](release-registration-receipt.schema.json).
Register the task universe before outcomes are known. Close with
[release-anchor-closure.schema.json](release-anchor-closure.schema.json), including the
final Manifest digest. Preserve failed, unfinished, and non-comparable trials; do not
omit them or count synthetic work or one task more than once.

Use [release-trial-evidence.schema.json](release-trial-evidence.schema.json) for each
acceptance result. Accepted trials must carry the same strict `integration_proof` in the
Manifest and acceptance evidence:

- `same_commit` requires candidate/stable SHA equality.
- `same_tree` requires a retained full `refs/heads/*` or `refs/tags/*` candidate ref,
  verifier-recomputed equal Git tree IDs, and an empty non-tree dependency scope.
- `same_tree` carries evidence by exact tree identity. It does not claim QA was rerun on
  the stable Commit and cannot cover history-sensitive, LFS/filter, submodule-content,
  generated, or external dependencies.

Run `scripts/v2_release_gate.py` after the required files and evidence are frozen. The
gate remains fail-closed: missing identities, unsupported integration proof, stale
digests, missing denominators, omitted outcomes, or any other schema/runtime violation
must fail rather than be inferred or repaired by the audit.

The closed anchor history enumerates the task universe; the Manifest maps outcomes but
does not redefine that universe. The gate must cover every anchored receipt, reject an
unanchored `task_ready`, block source-level audit violations in the candidate window,
verify stable-branch reachability, and re-hash every declared V1 source blob from the
exact freeze Commit. Comparable receipt, ledger, and Manifest records must name the same
frozen V1 identity and exact C/R/topology stratum. Only baselines with reconstructable
denominators contribute to a formal-efficiency sample. Content-addressing proves what
was frozen and whether it changed; it does not prove that source material was truthful
or qualified, so retain human source review. Preserve excluded, unfinished, and failed
trials; do not cherry-pick later successes. Local Git cannot prove remote ref protection
or push time, so use the approved protected append-only ref, signed record, or trusted
timestamp receipt as the independent control.

For a command-line gate invocation, use the approved frozen paths and identities:

```powershell
python scripts/v2_release_gate.py --manifest <PRIVATE_TRIAL_MANIFEST> --anchor-repo <PRIVATE_ANCHOR_REPO> --anchor-freeze-commit <TRUSTED_FREEZE_SHA> --anchor-head-commit <TRUSTED_CLOSED_HEAD_SHA>
```

## Evidence reuse boundary

Validation evidence may be carried forward only when Commit/tree, environment
fingerprint, lockfiles, test entry points, permissions, generated inputs, and relevant
external dependencies are unchanged. Any changed input is a rerun trigger. Release
qualification does not relax exact-candidate validation, stable-branch acceptance,
Owner approval, or executable rollback.

For prospective delivery measurement, read [metrics.md](metrics.md). Ordinary optional
metrics and formal Release Audit qualification are separate: a daily task does not gain
an audit ledger merely because it is released or deployed.
