# Security policy

## Supported versions

Security fixes target the latest `0.1.x` release while the project is in public beta.

## Report a vulnerability

Use GitHub's private security advisory flow for `ownasquare/context-loom`. Do not open a public
issue with credentials, private source text, exploit payloads, or identifying workspace data.
Include the affected version, configuration, reproduction, impact, and a minimal sanitized fixture.

## Security defaults

- Loopback-only HTTP, disabled CORS, no telemetry, and denied outbound access.
- No `.env*`, private-key, credential, dependency, build, binary, symlink, or outside-root indexing.
- Sanitized source objects with private filesystem permissions.
- No raw message persistence unless the operator explicitly enables it.
- Parameterized SQLite operations and atomic file promotion.
- Indexed content is reference data and cannot become executable system policy.
- Harness installers preview standalone snippets and never overwrite configuration silently.

The local single-user beta assumes an OS account and disk trusted by the operator. It is not a
multi-tenant service and does not provide application-level encryption at rest.

