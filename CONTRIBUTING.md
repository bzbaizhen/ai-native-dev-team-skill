# Contributing

Contributions are welcome when they make the development-team workflow safer, lighter, or easier to verify.

## Principles

- Keep the Skill focused on team bootstrap and approved adjustment.
- Keep audit, baseline construction, delivery telemetry, and efficiency comparison outside this Skill.
- Prefer proportional controls over mandatory ceremony.
- Preserve proposal-first behavior and explicit approval boundaries.
- Separate implementation self-checks from independent validation.
- Do not add vendor-specific model names to the reusable workflow.
- Do not add claims without inspectable evidence.

## Development

1. Change the Skill or a directly used resource.
2. Run `python tests/validate_skill.py`.
3. Run `python -m unittest discover -s tests -p "test_*.py" -v`.
4. Include a realistic triggering or non-triggering example when behavior changes.
5. Explain the safety and context-cost impact in the pull request.
