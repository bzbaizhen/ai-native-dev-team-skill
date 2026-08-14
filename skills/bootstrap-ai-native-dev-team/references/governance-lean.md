# Lean governance profile

Use for C0/C1, R0/R1 work with at most one Writer and no release, migration, production, real-data, credential, or compliance boundary.

## Minimum controls

- Keep the main agent as fact owner and final accepter.
- Use `no-delegation` when handoff cost is greater than task cost.
- For delegated work, issue one concise task contract with objective, baseline, allowed paths, checks, stop conditions, and rollback.
- Preserve one Writer per file.
- Use the existing branch and project workflow when safe; do not require a Worktree or new governance document for a tiny reversible edit unless repository policy requires it.
- Run only relevant checks. Do not create CI, ADRs, risk registers, or evidence directories for their own sake.
- Require an independent Validator for a material behavior change even if implementation is C1/R1.
- Accept only the exact change integrated into the stable branch.

## Environment preflight

The main agent verifies the repository root, active instructions, Git state, native runtime, and build/test entry points once. Record or reuse the project fingerprint. Workers consume the result and do not repeat discovery unless an assumption fails.

## Handoff

The worker returns:

- completed work and changed files;
- exact Commit or immutable diff identifier;
- commands, environment, results, and limitations;
- `Confirmed facts / Inferences / To verify`;
- rollback;
- `metrics_handoff` for the main agent.

Freeze the write lease at `dev_complete`. Reopen explicitly for any fix.

## Escalate

Move to Controlled when scope becomes cross-module, an interface/dependency/data shape changes, independent slices appear, risk reaches R2, or verification is no longer easy. Move to Strict for any R3 condition.
