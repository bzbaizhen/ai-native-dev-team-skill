# Contributing

Contributions are welcome when they make the development-team workflow safer, lighter, or easier to verify.

## Principles

- Keep the Skill focused on team bootstrap and bounded adjustment.
- Prefer proportional controls over mandatory ceremony.
- Preserve bounded continuous-execution authorization, explicit proposal-only conditions, and authority boundaries.
- Separate implementation self-checks from independent validation.
- Keep DQR as the material-Controlled acceptance protocol, not a third routing layer.
- Delegate bounded work when its goal, context, write ownership, and acceptance
  are clear and it has concrete parallel, model-routing, or independent-review value.
  Keep simple and tightly coupled work with the main agent; preserve required validation
  when implementation ownership changes. Cost claims require observed mapping and prices.
- Keep the canonical Skill, Core/Controlled policy, templates, agent metadata, and global
  trigger vendor-neutral. Vendor-specific mappings belong only in isolated, dated,
  explicitly selected optional profile references with fail-closed tests.
- Optional prospective metrics require explicit main-agent selection and main-agent-only
  ledger writes. Keep absent observations null or `unknown`, and keep audit/compare
  output descriptive rather than threshold-based.
- Prefer native file tools and task-local scripts; never recommend broad global allowlisting as an approval shortcut.
- Do not add claims without inspectable evidence.

## Development

1. Change the Skill or a directly used resource.
2. Run `python tests/validate_skill.py`.
3. Run `python -m unittest discover -s tests -p "test_*.py" -v`.
4. Include a realistic triggering or non-triggering example when behavior changes.
5. Add or update fail-closed structural tests for routing-policy changes.
6. Explain the safety and context-cost impact in the pull request.
