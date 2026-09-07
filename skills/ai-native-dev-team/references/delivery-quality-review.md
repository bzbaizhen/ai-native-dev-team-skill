# Delivery quality review (DQR)

DQR is the Controlled per-task acceptance protocol for material work. It is not a routing layer: select Core or Controlled first, then load DQR only for a material
Controlled candidate that needs acceptance.

## Freeze the delivery contract

Before writing, record the smallest frozen contract: objective, acceptance criteria,
task baseline, frozen interfaces and dependencies, allowed and forbidden paths, exact
Writer/Validator roles, required checks, authority limits, separately authorized
integration or installation targets when applicable, and rollback or recovery method.
The main agent owns changes to this contract. A changed contract reopens the review and
invalidates affected evidence.

## Lease, self-check, and candidate identity

- Grant one Writer an exact path lease and allowed root. Do not overlap ownership; freeze
  the lease at dev_complete and reopen it only for an in-scope correction.
- Require the Writer to check path scope and run the assigned checks. Record failures and
  limitations. A Writer self-check is not independent validation.
- Identify the candidate with an immutable Commit, tree, digest, or equivalent stable
  identity. Every check, finding, and acceptance decision names that exact candidate.

## Independent validation and findings

### Assign test authority once

Name the canonical command and execution owner before the run. Reuse a Writer or Main
test run only when Main reads its original stdout/stderr and inner runner exit code,
confirms test discovery/counts and relevant assertions, and verifies the full candidate
digest before and after execution. Include tracked and untracked candidate inputs;
HEAD alone cannot identify a dirty candidate. Bind cwd, command/arguments, toolchain,
lockfiles, generated inputs, permissions, and relevant external dependencies as well.
Writer summaries, copied counts, a wrapper exit 0, or a missing log are not sufficient.

If that evidence is complete and unchanged, do not rerun the same suite merely because
Main or a Validator is a different actor. The Validator independently assesses semantics
and authenticates reused evidence, labeling who executed it; reuse never turns Writer
self-check into independent semantic validation. An explicitly required independent
execution remains mandatory. Missing evidence calls for the missing check, not another
Writer or a replay of all completed stages. A new full-candidate digest invalidates old
acceptance: rerun affected checks and bind the new review to the replacement candidate.

### Bounded failure investigation

Preserve the first failure and freeze candidate bytes. For a suspected transient failure,
inspect the original traceback and runtime evidence before changing code. By default,
allow one exact targeted rerun; if it passes, run the unchanged canonical regression
once. Both must pass to classify the failure as transient, with the initial failure
retained. If either fails, stop this retry path and report a reproducible defect or an
unresolved environment blocker; do not keep rerunning until green.

Additional diagnostics require a concrete new hypothesis, a stated command/time budget,
and an expected discriminating result, not another review for reassurance. Separate
product defects from environmental blockers and invalid transport runs. Instrumented
or alternate-runner success is diagnostic evidence, not a substitute for a failing
required standard command. Changing that acceptance requirement needs an explicit
contract decision; failed standard evidence is never overwritten.

For material work, use an independent, read-only Validator from a clean or controlled
state. The Validator does not silently fix product code. Map each finding to a contract
requirement, candidate identity, evidence, severity, and required disposition.

If a fix changes the candidate, reopen the lease, invalidate candidate-bound evidence,
and rerun every affected check. Reuse evidence only when the candidate and all relevant
inputs remain unchanged. A revalidation must name the replacement candidate; it cannot
silently inherit a prior pass.

## Acceptance, limitations, and recovery

The main agent accepts only after confirming the frozen contract, exact verified candidate,
Writer handoff, independent result, permissions, authority evidence, required Owner
approval, limitations, and executable rollback or recovery. Acceptance is a
candidate-and-evidence decision. Acceptance does not require prior integration or
installation and does not authorize either action. Record known limits rather than treating an unrun
visual, external, platform, or recovery check as passed. For R3, also require explicit
Owner approval and stable-state readback where applicable.

Keep rollback executable for the exact accepted candidate and preserve the recovery
instructions and any required readback. Stop and report when identity, authority,
scope, evidence, or recovery conflicts.

## Separate lifecycle actions

Acceptance, integration, and installation are separate states and actions. Integration
requires a separately authorized integration target and identity readback confirming the
exact verified candidate. Installation requires a separately authorized installation
target, a rollback backup, and byte/readback verification confirming the exact verified
candidate. Acceptance implies neither integration nor installation; integration and
installation do not imply each other.

Release, public, and production actions remain separately gated Controlled/R3 actions
with their required Owner authority; no acceptance, integration, or installation state
grants that authority.

## State words

| Word | Precise meaning |
|---|---|
| designed | The contract and route are decided; no candidate is implied. |
| written | The Writer saved a candidate; no check result is implied. |
| run | A named check or runtime action executed and its result was captured; success is not implied. |
| verified | Required checks and independent validation support the exact candidate. |
| accepted | The main agent made the evidence-bound acceptance decision for the exact verified candidate with authority evidence; acceptance does not imply integrated or installed. |
| integrated | The exact verified candidate is present in a separately authorized integration target and identity readback confirms it; integration does not imply installed. |
| installed | The exact verified candidate is available at a separately authorized installation target with a rollback backup and byte/readback verification; installation does not imply integrated. |
| released | A separately authorized release, public, or production action passed its applicable Controlled/R3 gates; no earlier state grants this state. |
