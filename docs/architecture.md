# Architecture

Context Loom is a local context compiler, not a remote retrieval service. One application layer is
exposed through HTTP, CLI, MCP, proxy, and the React workbench.

```mermaid
flowchart LR
  S["Allowlisted workspace"] --> C["Safe collectors"]
  C --> R["Redaction and classification"]
  R --> V["Versioned sanitized object store"]
  V --> DB[("SQLite WAL and FTS5")]
  DB --> I["Intent and risk packet"]
  I --> H["Hybrid retrieval and budget"]
  H --> D["Extracts and optional local digest"]
  D --> F["Fidelity gate"]
  F --> E["Canonical prompt envelope"]
  E --> A["Harness adapters, MCP, API, CLI"]
  A --> U["Usage event ledger"]
  U --> W["Thread savings workbench"]
```

## Canonical and derived state

The sanitized content-addressed object store and SQLite resource/version/chunk records are
authoritative. FTS rows, the built-in deterministic hashed lexical vectors, Parquet exports, and the
frontend build are derived. Resource versions record parser and chunker fingerprints, and
hydrations record tokenizer metadata. Version 0.1.0 does not call a learned embedding model.

## Index generations

A synchronizer performs a full bounded reconciliation: it enumerates and reads every eligible text
file, applies redaction, hashes and chunks the sanitized text, and then lets the database classify
added, modified, renamed, unchanged, and deleted resources. Unchanged versions and content-addressed
objects are reused before one generation is published transactionally. Queries pin the active
generation and deletions become tombstones. `workspace watch` is a polling loop over that same full
reconciliation; version 0.1.0 has no filesystem-event debounce or metadata-first scan shortcut.

## Retrieval

Explicit safe paths and symbols are forced candidates. The remaining rank combines FTS/BM25,
deterministic hashed-term similarity, resource-kind authority, and a stale penalty. MMR reduces
duplicate evidence. Recency and thread-affinity fields exist in the score schema but use fixed
defaults in version 0.1.0, so they do not distinguish candidates. Component scores and
selection/omission reasons are retained as hydration metadata.

## Trust boundaries

Repository instructions, source, documentation, tool catalogs, and MCP catalogs are all quoted as
untrusted evidence. Instruction resources can be mandatory retrieval candidates, but they do not
become Context Loom system policy. Collectors inspect metadata and text but never execute source,
project scripts, hooks, tools, or MCP calls.
