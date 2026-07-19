# Limitations and proof boundaries

- Source-preserving fidelity does not guarantee a downstream model reaches the same answer it would
  have produced from every raw workspace byte.
- Version 0.1.0 uses deterministic hashed-term vectors, not a learned local or provider embedding
  model. Semantic matches outside lexical overlap can therefore be missed.
- The workbench can add, select, and rescan multiple local projects, but every path must be visible to
  the Context Loom process. Docker sees only paths explicitly mounted into the container. The
  workbench copies the selected renderer payload and does not send provider requests.
- Automatic pre-send interception depends on the harness. MCP is the safest portable integration;
  the bundled OpenAI-compatible forwarder is an explicit hydrate-then-forward path, while Anthropic
  and Gemini are renderers only. Cursor and Copilot usage totals may remain unavailable.
- Actual counterfactual savings are unknowable without an opt-in baseline call. Routine dashboard
  savings compare a bounded retrieved candidate bundle with an internal compiled-prompt estimate;
  they are projected and labeled accordingly.
- Raw messages are not persisted by default. A bounded current-process cache supports short-lived
  readback; exact replay after cache expiry or restart requires prior retention consent or a
  caller-held copy.
- The single-user SQLite runtime is not a distributed queue or multi-tenant hosted service.
- Custom prompt adapters are trusted in-process Python code and are available only to applications
  built with an injected registry. The default CLI, MCP server, and proxy do not discover them;
  collectors and tokenizers are not public plugin APIs in version 0.1.0.
- The checked-in CI workflow includes package/CLI smoke jobs for Linux, macOS, and Windows, while the
  full browser and container suites run on Linux. This source tree does not assert a hosted run until
  the public repository completes it successfully.
- Local Ollama success, provider calibration, real-harness behavior, hosted availability, and
  production operations require separate opt-in proof.
- Text-first ingestion does not parse arbitrary multimedia or archives in version 0.1.0.
- `compact_aggressive` currently follows the same selection and digest path as `hybrid_safe`; it is
  reserved for future behavior and should not be read as a stronger compression mode today.
- Version 0.1.0 has no hot-backup command, automatic state retention job, or state-pruning CLI;
  operators stop writers and copy the complete private state directory for backup.
