# Optional global trigger for Codex

Add this compact rule to `~/.codex/AGENTS.md`. Keep the complete workflow in the Skill
so ordinary tasks do not carry it in every prompt.

```md
## Default AI-native development team

- Route work first as `no-delegation`, `single-worker`, `task-cell`, or `team-required`.
- For a new software project, substantial cross-component work, multi-agent parallel implementation, release preparation, or high-risk engineering change, use `bootstrap-ai-native-dev-team` to design or adjust the development team before implementation.
- Separate complexity from risk. Map C0 batch / C1 / C2 / C3 to Economy-Low / Standard-Medium / Advanced-High / Frontier-Max; map R0-R3 to stronger permission, review, approval, rollback, and recovery gates.
- Keep the main Agent as the control plane for scope, architecture decisions, contracts, permissions, integration, evidence review, stop decisions, and final acceptance. It must not duplicate a Writer's repository exploration, implementation, or test/debug loop.
- Permit direct main-Agent work only for read-only control-plane work or one tiny deterministic, low-risk, single-file C0 edit with no material behavior, interface, dependency, data, security, concurrency, production, or public effect; no debugging loop or test authoring; and exactly one deterministic verification. Missing or uncertain evidence delegates.
- Route every C0 mechanical batch and every C1+ implementation, refactor, bug fix, test-writing, or debugging task to a task-scoped Writer on the configured lower-cost execution path. Do not use a generic handoff-cost exception for implementation.
- Treat an explicit request to build, implement, fix, initialize, or adjust as one standing authorization envelope for ordinary reversible work in the stated repository/task scope. Use proposal-only when explicitly requested, scope cannot be bounded, or a real authority boundary is already present.
- The envelope excludes credentials or secrets, real or production data, paid resources, publication, push/merge/deploy/release, destructive deletion, irreversible migration, privilege escalation, and out-of-scope writes. Prefer native file tools and task-local scripts; never use broad global allowlisting as an approval shortcut.
- Default material work to one Writer and one independent Validator tied to the exact candidate. Preserve rollback/recovery evidence. Do not open another Writer while integration is waiting without a recorded reason.
- For material Controlled acceptance, load the task-level DQR protocol. It does not add a routing layer; map findings, limits, and revalidation to the exact candidate.
- On Windows, default unattended non-interactive Coding CLI exec, Writer, and Validator invocations for bounded long work to `pty=false`, `background=true`, and `notify_on_complete=true`. Reserve `pty=true` for an interactive TUI, login, or a command that genuinely requires terminal input; never apply it unconditionally to unattended exec.
- Final output text is not process-exit evidence. Accept completion only after fresh registry status is `exited` and the exit code is captured. If a legacy PTY run prints a final marker but remains alive, make one short bounded grace check, inspect fresh process status, and terminate only the exact tracked process if needed; never start a duplicate Writer or repeatedly wait/reconnect.
- Keep C3 architecture with the main Agent if needed, but send frozen implementation slices to Writers. Main-Agent implementation takeover requires an unavailable or repeatedly failing Writer path with evidence, no safe re-slice, explicit user authorization, and a recorded reason.
- Do not claim an orchestration subagent is lower-cost unless its observable runtime mapping is to a lower-cost tier.
- Keep canonical capability tiers vendor-neutral. A dated runtime profile is optional and inactive until the Owner explicitly selects it; file presence or credentials alone do not activate it.
- Only if the main Agent explicitly selects optional local prospective metrics may it write the local lifecycle ledger. Writers and Validators supply facts but do not write it; observed model/provider/reasoning/token/cost values stay null or `unknown` when unavailable.
- Treat metrics snapshots and compare output as descriptive only; they do not add a fixed threshold or acceptance authority.
- Use Core for non-material C0/C1 and R0/R1 work. Use Controlled for material behavior, C2/C3, R2/R3, boundaries, concurrency, production, release, or public action.
- Do not invoke the full workflow for strict C0 main-Agent work; this does not remove the Writer requirement for C0 batches or C1+ implementation.
- Project-specific `AGENTS.md`, accepted ADRs, and current user instructions may override this default. Record durable exceptions.
```
