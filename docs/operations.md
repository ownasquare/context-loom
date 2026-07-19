# Operations

## Install paths

Source development requires Python 3.11-3.13 and `uv`. Node is required only to build or test the
React workbench; an installed wheel already contains the built frontend.

```bash
uv sync --frozen
npm --prefix frontend ci
make demo
make serve
```

For browser E2E on a fresh machine, also run
`npx --prefix frontend playwright install --with-deps chromium`. To install an already-built wheel:

```bash
uv tool install dist/context_loom-0.1.0-py3-none-any.whl
context-loom init
context-loom serve
```

The container-only path is `docker compose up --build --detach`; no host Python or Node runtime is
required.

## Configuration and registration

State defaults to the platform user-data directory with private permissions. Override it with
`CONTEXT_LOOM_HOME` for isolated development, backup, or testing. The database and object store must
move together. Settings read exported environment variables, not a repository `.env` file;
`.env.example` is a reference and is not auto-loaded.

Register only an explicit project root. A stable workspace ID makes automation and examples
repeatable:

```bash
context-loom workspace add /absolute/path/to/project --name "Project" --id project-local
context-loom workspace sync project-local
context-loom hydrate project-local "Where is retry behavior defined?" --thread-id project-chat
context-loom thread stats project-chat
```

Reuse the same thread ID to accumulate lifetime accounting. Record provider usage with the
hydration ID returned by `--envelope-json`; see `token-accounting.md`.

## Synchronization

`workspace sync` performs a full bounded reconciliation. Every run enumerates and rereads eligible
text files, applies redaction, hashes and chunks sanitized content, and lets the database reuse
unchanged versions before atomic generation publication. `workspace watch` repeats that operation on
a polling interval; it does not subscribe to filesystem events or use a metadata-only fast path. A
single-writer lock protects publication while SQLite/WAL permits concurrent readers.

The scanner applies Git-style `.gitignore` and `.contextloomignore` files from parent to child while
immutable secret, dependency, database, build, and symlink exclusions remain in force. Defaults cap
each file at 2,000,000 bytes and each workspace at 50,000 files. Only regular UTF-8 text is indexed;
binary, unsupported-encoding, oversized, and symlinked entries are reported as exclusions.

## Backup and recovery

Version 0.1.0 does not expose a hot-backup command. Stop `serve` and `workspace watch`, then copy the
entire private `CONTEXT_LOOM_HOME` directory as one unit so the SQLite database and object inventory
remain consistent. Restore that directory with owner-only permissions, run `context-loom doctor`,
and resynchronize each registered workspace before trusting freshness. Source objects are addressed
by hash; missing or mismatched objects fail readiness.

## Retention

Raw messages are not persisted by default, while sanitized resource versions, hydration metadata,
usage observations, and exports remain in the private state directory. The running process still
keeps up to 128 full envelopes for 15 minutes by default so immediate inspection and forwarding can
work. Enable `--retain-messages` only when full envelope readback after cache expiry or restart is
required. Version 0.1.0 has no automatic retention or state-pruning job. Remove an export only by its
exact path, and take a backup before manually pruning application state. `make clean` removes
repository build/test artifacts; it does not delete private Context Loom state.

## Local model

Ollama support is optional and defaults to the loopback URL with model `qwen3:4b`:

```bash
ollama pull qwen3:4b
ollama serve
context-loom --allow-outbound hydrate project-local "Explain the retry path" --thread-id project-chat --use-local-model
```

Both controls are required: process-wide outbound consent and request-level `--use-local-model` (or
`use_local_model: true` over HTTP/MCP). Keep the Ollama URL on loopback unless an external security
boundary protects it. Context Loom remains functional through deterministic extraction if the model
is disabled, unavailable, malformed, slow, or fails fidelity validation. Local-model readiness never
determines database/API liveness.

## Provider forwarder

Set `CONTEXT_LOOM_PROXY_UPSTREAM_URL`, then start the process with `--allow-outbound` (or export
`CONTEXT_LOOM_ALLOW_OUTBOUND=true`). Hydrate first and send the returned hydration ID to
`POST /api/v1/proxy`. This is an explicit two-step, non-streaming forwarder, not an automatic or
drop-in `/v1` proxy. Keep provider credentials in the request's `Authorization` header; Context Loom
forwards but does not persist them.

## Container

`docker compose up --build --detach` runs the packaged workbench as a non-root user with a read-only
root filesystem and a named writable volume. The published port is loopback-only. Keep the named
volume with the container backup, and run `make container-smoke` after changing the image, startup
command, runtime permissions, or storage layout.
