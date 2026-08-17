# Optional global trigger for Codex

Add this compact rule to `~/.codex/AGENTS.md`. Keep the complete workflow in the Skill
so ordinary tasks do not carry it in every prompt.

```md
## Default AI-native development team

- Route work first as `no-delegation`, `single-worker`, `task-cell`, or `team-required`.
- For a new software project, substantial cross-component work, multi-agent parallel implementation, release preparation, or high-risk engineering change, use `bootstrap-ai-native-dev-team` to design or adjust the development team before implementation.
- Separate complexity from risk. Map C0 batch / C1 / C2 / C3 to Economy-Low / Standard-Medium / Advanced-High / Frontier-Max; map R0-R3 to stronger permission, review, approval, rollback, and recovery gates.
- Keep the main Agent as the high-capability information hub. Give Workers task-local packets; do not make them reload the complete Skill.
- Default to proposal-first. Do not create agents, branches, Worktrees, or governance files before the applicable scope is approved.
- Default to one Writer and one independent Validator for material work. Do not open another Writer while integration is waiting without a recorded reason.
- Use Core for non-material C0/C1 and R0/R1 work. Use Controlled for material behavior, C2/C3, R2/R3, boundaries, concurrency, production, release, or public action.
- Keep audit, baseline construction, efficiency measurement, and development telemetry outside this Skill.
- Do not invoke the full workflow for small, low-risk work the main Agent can safely complete alone unless the user explicitly requests it.
- Project-specific `AGENTS.md`, accepted ADRs, and current user instructions may override this default. Record durable exceptions.
```
