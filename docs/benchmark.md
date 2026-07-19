# Benchmark methodology

The credential-free benchmark loads the versioned cases and targets from
`evals/retrieval-cases.json`, copies the bundled demo workspace, and adds 40 deterministic noise
documents. It performs one initial synchronization, then changes one fixture file before every
measured synchronization and hydrates every case twice to test replay. It reports:

- initial synchronization latency and one-file-change synchronization p50/p95 latency;
- hydration p50/p95 latency;
- Recall@10 and explicit-reference recall;
- protected-atom and citation coverage;
- median projected input-token reduction;
- deterministic replay agreement.

Every result includes Python/platform/machine/processor metadata, fixture and eval-suite identifiers,
indexed resource/chunk and noise-file counts, tokenizer identity/fingerprint, cache state, requested
mode, and local-model state. The measured one-file-change synchronization still executes the full
bounded reconciliation described in `architecture.md`; it is a workload label, not a metadata-only
incremental scanner claim. Version 0.1.0 uses the suite's smoke-regression gates rather than
universal performance claims: Recall@10 ≥95%, explicit-reference recall/protected atoms/citations/
replay 100%, and median projected input reduction ≥30% on the bundled cases.

Provider and shadow-baseline benchmarks are opt-in because they incur network transfer, cost, and
additional tokens. They are not part of the bundled command. Answer-quality equivalence, reduction
distributions, and actual counterfactual savings require separate paired evaluations.
