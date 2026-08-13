# Contributing

Contributions are welcome when they make the workflow safer, lighter, or easier to verify.

## Principles

- Keep the Skill focused on team bootstrap, adjustment, and audit.
- Prefer proportional governance over mandatory ceremony.
- Preserve proposal-first behavior and explicit approval boundaries.
- Separate implementation self-checks from independent validation.
- Do not add vendor-specific model names to the reusable baseline.
- Do not add claims without inspectable evidence.

## Development

1. Change the Skill or its directly used resources.
2. Run `python tests/validate_skill.py`.
3. Include a realistic triggering or non-triggering example when behavior changes.
4. Explain the safety and context-cost impact in the pull request.

