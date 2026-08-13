# Optional global trigger for Codex

Add this compact rule to `~/.codex/AGENTS.md`. Keep the complete workflow in the Skill so ordinary tasks do not carry the full governance document in context.

```md
## Default AI-native development team

- For a new software project, substantial cross-component work, multi-agent parallel implementation, release preparation, or high-risk engineering change, use `bootstrap-ai-native-dev-team` to design or audit the team before implementation.
- The Skill must propose the smallest sufficient team, separate complexity from risk, establish task and path ownership, and define approval, independent validation, version evidence, rollback, and recovery requirements.
- Default to proposal-first: do not create agents, branches, worktrees, or project governance files until the applicable scope is approved. An explicit request to initialize authorizes only ordinary reversible writes within that scope; production, real data, credentials, publication, irreversible migration, and deletion still require explicit owner approval.
- Do not invoke the full team workflow for small, low-risk work that the main agent can safely complete alone, unless the user explicitly requests the Skill.
- Project-specific `AGENTS.md`, accepted ADRs, and the user's current instructions may override this baseline. Record durable exceptions instead of silently bypassing them.
```

