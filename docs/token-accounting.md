# Token accounting

Every hydration turn can contain four different kinds of evidence. The API and workbench keep them
visually and mathematically separate.

| Symbol | Meaning | Typical confidence |
|---|---|---|
| `Bₑ` | Candidate-bundle baseline estimate | exact-local, calibrated, or rough |
| `Hₑ` | Internal compiled-prompt estimate | exact-local, calibrated, or rough |
| `Aᵢ`, `Aₒ` | Provider-observed actual input and output | provider-observed |
| `Bₐ` | Optional actual input from an opt-in shadow baseline call | provider-observed |
| `Lᵢ`, `Lₒ` | Optional local-compactor input and output | local observation/estimate |

## Metrics

`Bₑ` counts the exact message plus the deduplicated candidates returned by lexical, deterministic
vector, and direct-reference retrieval. Version 0.1.0 requests at most 40 candidates per channel by
default. It is not every byte in the workspace and is not an observed unhydrated provider request.

`Hₑ` counts Context Loom's internal compiled prompt: selected digest plus exact message. The final
adapter payload can add an untrusted-data preamble, citations, fidelity and recovery metadata, while
the destination harness can add system, tool, cache, and protocol overhead. Those additions are not
part of `Hₑ`; provider readback is the authority after a send.

- Projected input savings: `max(Bₑ - Hₑ, 0)`.
- Estimate error after send: `Aᵢ - Hₑ` when `Aᵢ` exists.
- Observed system tokens: `Aᵢ + Aₒ + Lᵢ + Lₒ`, with absent fields left unknown.
- Baseline-estimate-adjusted reduction: `Bₑ - Aᵢ`, explicitly labeled as estimate-adjusted.
- Verified counterfactual savings: `Bₐ - Aᵢ` only when both variants were actually sent.

Output-token savings are not claimed without a paired baseline. Shadow calls consume money and
tokens, so they are disabled by default and belong in opt-in evaluation, not routine operation.

Estimates store their tokenizer profile, version, method, confidence, and provider/model when
applicable. Usage observations store provider, model, method, timestamp, and optional hydration
association. Billable input/output can be recorded separately from provider-observed token fields.
Idempotency keys prevent retried usage callbacks from double-counting. Thread summaries show
actual-usage completeness rather than replacing missing observations with zero.

Use one stable thread identifier across turns and attach the hydration identifier when importing
usage. An unassociated observation still appears in lifetime totals, but it cannot establish a
measured estimate error for a specific hydration.
