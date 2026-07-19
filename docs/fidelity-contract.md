# Source-preserving fidelity contract

Context Loom never describes lossy summarization as guaranteed semantic equivalence. Its contract is
defined by checks the program can prove.

## Guaranteed by a passing report

- The user message bytes in the canonical envelope equal the submitted message bytes.
- Every emitted excerpt points to a current resource version, SHA-256 digest, and valid line range.
- Every optional local-model claim cites at least one selected current resource version.
- Explicit safe path and symbol references are selected or named in a security/fallback reason.
- Protected atoms survive: paths, symbols, commands, URLs, numbers, percentages, durations,
  thresholds, negative guards, and configured policy labels.
- A deterministic envelope can be replayed from the same generation, settings, and tokenizer
  fingerprint to the same replay hash.
- Omitted candidates remain named through local recovery URIs without sending their bodies. Resolve
  one with `GET /api/v1/resources/{resource_id}/versions/{version_id}`, the MCP
  `resolve_resource_version(resource_id, version_id)` tool, or pass the emitted URI directly to
  `context-loom resource resolve 'context-loom://resources/RESOURCE/versions/VERSION'`.

## Security override

Secrets are never preserved merely to satisfy fidelity. Hard-denied files are excluded and detected
credential values are redacted before canonical storage. The fidelity report records the override
and, when it affects an explicit reference, falls back rather than hiding the omission.

## Mode ladder

1. `hybrid_safe`: exact selected extracts rendered deterministically by default; when the local model
   is explicitly requested, a cited structured digest may replace the deterministic digest.
2. `strict_extractive`: exact selected extracts without generated claims.
3. `passthrough`: exact user request with no compacted workspace claims.

`compact_aggressive` is a reserved opt-in label in version 0.1.0 and currently follows the same
selection and digest path as `hybrid_safe`. It never bypasses citation or protected-atom checks. A
failed gate moves down the ladder and records the reason.

## Not guaranteed

Retrieval can miss an unmentioned dependency, a downstream model can ignore context, and omitted
text can affect an answer. Paired task evaluations measure those risks; they do not turn them into an
absolute semantic guarantee.
