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
