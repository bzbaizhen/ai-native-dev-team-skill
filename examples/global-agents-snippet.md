# Optional global trigger for Codex

Add this compact rule to `~/.codex/AGENTS.md`. Keep the complete workflow in the Skill so ordinary tasks do not carry the full governance document in context.

```md
## Default AI-native development team

- Route work first as `no-delegation`, `single-worker`, `task-cell`, or `team-required`. A single Worker is not a team.
- For a new software project, substantial cross-component work, multi-agent parallel implementation, release preparation, or high-risk engineering change, use `bootstrap-ai-native-dev-team` to design or audit the team before implementation.
- Separate complexity from risk. Map C0 batch / C1 / C2 / C3 to Economy-Low / Standard-Medium / Advanced-High / Frontier-Max; map R0-R3 to progressively stronger permission, review, approval, rollback, and recovery gates. Record a reason for Frontier escalation.
- Keep the main Agent as the high-capability information hub. Give ordinary Workers approved task contracts; do not make them reload the complete team Skill.
- Default to proposal-first: do not create agents, branches, worktrees, or project governance files until the applicable scope is approved. An explicit request to initialize authorizes only ordinary reversible writes within that scope; production, real data, credentials, publication, irreversible migration, and deletion still require explicit owner approval.
- Default to one Writer and one Validator per repository. Do not start another Writer while accepted integration is waiting at DEV_COMPLETE, QA_PENDING, or MERGE_READY without a recorded override.
- Use Lean, Controlled, or Strict governance proportionally. Let the main Agent own the shared prospective event ledger; Workers return metrics handoffs.
- Do not invoke the full team workflow for small, low-risk work that the main Agent can safely complete alone, unless the user explicitly requests the Skill.
- Project-specific `AGENTS.md`, accepted ADRs, and the user's current instructions may override this baseline. Record durable exceptions instead of silently bypassing them.
```
