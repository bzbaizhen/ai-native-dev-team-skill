# Project configuration

The mutable project document is `.ai-native/model-router.json`. Its exact v1 and
v2 fields are defined by their bundled config schemas. The profile and
`router_api_version` must use the same version; mixed versions fail closed. Every
request explicitly selects a profile; file presence alone never activates a
profile. Both bundled profiles are inactive by default and require
`explicit-owner-selection`.

## Selection precedence

For the resolver, use explicit `--config` first, an injected configuration
second, and the conventional project path third. A missing conventional file
may use a bundled profile only when the request itself explicitly selects that
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

Project profiles use the matching strict versioned schema, catalog identities,
dated route-bound fallback evidence, and explicit-selection rules as the bundled
profile. A profile file being present or listed never activates it.

Provider execution, authentication, and transport remain outside this package.
Configuration contains no secret, endpoint, credential, transport command, or
price values.
