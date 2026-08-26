# Example: Personal MVP team proposal

- Status: `proposed`
- Mode: `proposal`
- Project: Local-first desktop prototype

## Recommendation

Approve a `task-cell`: main agent, one Writer, and one independent Validator activated
when the behavior-changing candidate is ready. Do not form a broader team.

## Confirmed facts

- The product is an MVP with no production users.
- One repository contains the current editable source.
- The milestone changes one UI module and one local service contract.

## Inferences

- Parallel UI and service implementation may help after the contract is frozen.

## To verify

- Exact build and test commands.
- Whether the local service contract already has fixtures.

## Routing decision

- Complexity: `C2` because the milestone crosses a UI/service boundary.
- Risk: `R1` because it changes only reversible prototype code and no real data.
- Layer: `controlled`.
- Route: `task-cell`.
- Capability/reasoning: `advanced / high`.
- Model mapping: use the active project configuration; do not infer the runtime model.
- DQR: required before material acceptance; it will bind findings and limits to the exact candidate.

## Minimum team

| Role | Enabled | Reason |
|---|---:|---|
| Business owner | yes | Approves scope |
| Main agent | yes | Freezes contract and accepts work |
| Writer | yes | Builds one approved slice |
| Independent validator | yes, when candidate is ready | Reviews the exact behavior-changing Commit |
| Security specialist | no | No credentials, production, or sensitive data in scope |

## Explicitly not executed

- No agents, branches, or Worktrees have been created.
- No project files have been modified.
- No production or external action is authorized.
