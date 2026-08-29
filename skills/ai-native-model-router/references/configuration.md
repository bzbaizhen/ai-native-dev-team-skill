# Project configuration

The mutable project document is `.ai-native/model-router.json`. Its exact v1
fields are defined by the bundled config schema. The active profile is selected
explicitly; file presence alone never activates a profile.

## Selection precedence

For the resolver, use explicit `--config` first, an injected configuration
second, and the conventional project path third. A missing conventional file
may use the bundled profile only when the request itself explicitly selects that
profile. The helper does not read global application settings.

The resolver validates the full config and computes a canonical SHA-256 digest.
That digest is copied into every decision. It is not a secret or an execution
receipt.

## Project profiles

`project_profile_dirs` contains safe relative directories under the project root.
Profiles are JSON files whose `profile_id` matches the requested ID. Directory
traversal, absolute paths, symlink escape, malformed profiles, and ambiguity are
rejected. The bundled profile is immutable: a project copy with the same ID is
accepted only when its bytes and digest are identical; a changed collision is
blocked.

Project profiles use the same strict schema, catalog identities, dated fallback
evidence, and explicit-selection rules as the bundled profile.
