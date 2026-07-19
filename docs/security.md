# Security and threat model

## Assets

The protected assets are workspace source, chat intent, resource history, prompt envelopes, usage
metadata, provider credentials, harness configuration, and local availability.

## Threats and controls

| Threat | Control |
|---|---|
| Secret or key ingestion | hard path denies, content redaction, key-name-only env inventory |
| Symlink/path escape | resolved allowlisted roots, no symlink following, descriptor checks |
| File changes during scan | before/after stat validation and bounded retry |
| Repository prompt injection | all repository instructions and content are quoted untrusted evidence, never system policy |
| Malicious MCP/tool metadata | schemas are data; ingestion never invokes tools |
| SQL injection | parameterized statements and strict boundary models |
| Oversized/binary denial of service | file/count/token/time limits and binary detection |
| Network exfiltration | outbound denied by default; process opt-in plus an explicit local-model or proxy invocation |
| Harness config loss | preview-first snippets, explicit target, atomic non-overwrite default |
| Usage inflation | immutable idempotent observations and confidence-separated aggregates |
| Stale or deleted evidence | active generations, tombstones, current-version citation checks |

## Trust assumptions

Version 0.1.0 is a local single-user process. The OS user, filesystem, and loopback peers are trusted.
Application authentication, TLS, tenant isolation, hosted object storage, and distributed writers are
outside this release. Binding beyond loopback requires explicit acknowledgment and an external
security boundary. The MCP SSE and streamable-HTTP transports also add no Context Loom authentication
or TLS, so prefer stdio or keep those transports behind a trusted local boundary.

## Privacy

Telemetry is absent. Raw messages are not persisted by default, but the running process holds recent
full envelopes in a bounded time/size cache so they can be inspected or forwarded. Exact message and
envelope persistence is a separate opt-in. Sanitized resource text is stored locally because cited
replay and retrieval require it. Operators should use encrypted disks and avoid registering
workspaces whose content they are not authorized to process.

Hard path exclusions and content redaction reduce accidental secret ingestion; they cannot prove
arbitrary text is harmless. Use `.contextloomignore` as the primary workspace-specific boundary,
review the resource list and exclusion counts after synchronization, and do not register a root that
contains data the operator is not allowed to index.
