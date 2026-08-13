# Example: Personal MVP team proposal

- Status: `proposed`
- Mode: `proposal`
- Project: Local-first desktop prototype

## Recommendation

Approve a two-role execution topology: main agent plus one implementation agent. Add an independent validator only when the first behavior-changing diff is ready.

## Confirmed facts

- The product is an MVP and has no production users.
- One repository contains the current editable source.
- The requested milestone changes one UI module and one local service contract.

## Inferences

- Parallel frontend and service implementation could save time after the contract is frozen.

## To verify

- Exact build and test commands.
- Whether the local service contract already has fixtures.

## Classification

- Complexity: `C2` because the milestone crosses a UI/service boundary.
- Risk: `R1` because it changes only reversible prototype code and no real data.

## Minimum team

| Role | Enabled | Reason |
|---|---:|---|
| Business owner | yes | Approves scope |
| Main agent | yes | Freezes contract and accepts work |
| Implementer | yes | Builds one approved slice |
| Independent validator | later | Reviews the exact behavior-changing commit |
| Security specialist | no | No credentials, production, or sensitive data in scope |

## Explicitly not executed

- No agents, branches, or worktrees have been created.
- No project files have been modified.
- No production or external action is authorized.

