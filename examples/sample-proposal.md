# Example: Personal MVP team proposal

- Status: `proposed`
- Mode: `proposal`
- Project: Local-first desktop prototype

## Recommendation

Approve a `task-cell`: main agent, one Writer, and one independent Validator activated when the behavior-changing candidate is ready. Do not form a broader team.

## Confirmed facts

- The product is an MVP and has no production users.
- One repository contains the current editable source.
- The requested milestone changes one UI module and one local service contract.

## Inferences

- Parallel frontend and service implementation could save time after the contract is frozen.

## To verify

- Exact build and test commands.
- Whether the local service contract already has fixtures.

## Routing decision

- Complexity: `C2` because the milestone crosses a UI/service boundary.
- Risk: `R1` because it changes only reversible prototype code and no real data.
- Route: `task-cell`.
- Governance profile: `controlled`.
- Capability/reasoning tier: `advanced / high`.
- Model mapping: use the active project configuration; do not infer the runtime model.

## Minimum team

| Role | Enabled | Reason |
|---|---:|---|
| Business owner | yes | Approves scope |
| Main agent | yes | Freezes contract and accepts work |
| Implementer | yes | Builds one approved slice |
| Independent validator | yes, deferred until candidate | Reviews the exact behavior-changing Commit |
| Security specialist | no | No credentials, production, or sensitive data in scope |

## Explicitly not executed

- No agents, branches, or worktrees have been created.
- No project files have been modified.
- No production or external action is authorized.
