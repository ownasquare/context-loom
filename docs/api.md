# HTTP API

The local API is versioned under `/api/v1`. It binds to loopback by default, exposes no CORS
allowlist, and serves interactive OpenAPI documentation at `/api/docs`.

Start a credential-free demo and the service, then prepare a message through the API:

```bash
context-loom demo
context-loom serve
```

```bash
curl --fail-with-body --request POST http://127.0.0.1:8768/api/v1/hydrations \
  --header 'Content-Type: application/json' \
  --data '{
    "workspace_id": "demo-workspace",
    "thread_id": "api-demo",
    "message": "Where is retry behavior defined?",
    "adapter": "generic_markdown"
  }'
```

The request stays local and returns the canonical envelope plus the selected rendered payload. It does
not call a model provider.

## System

- `GET /healthz` — process liveness and version.
- `GET /readyz` — database/migration readiness and local-model status.
- `GET /api/v1/adapters` — renderer and integration capabilities.

Applications built with an injected adapter registry include those custom adapter capabilities here.
The default installed service exposes built-ins only; see [Extending Context Loom](extending.md).

## Workspaces and resources

- `POST /api/v1/workspaces` — register an allowlisted root.
- `GET /api/v1/workspaces` — list registered workspaces.
- `GET /api/v1/workspaces/{id}/status` — active generation and index health.
- `POST /api/v1/workspaces/{id}/sync` — transactionally reconcile resources.
- `GET /api/v1/workspaces/{id}/resources` — current, non-deleted resource metadata only. Read the
  workspace status for exclusion and stale counts.
- `GET /api/v1/resources?workspace_id={id}` — workbench-compatible resource-list alias.
- `GET /api/v1/resources/{resource_id}/versions/{version_id}` — resolve one immutable sanitized
  version referenced by an omission recovery URI. This can return a historical version.

## Hydration and accounting

- `POST /api/v1/hydrations` — compile a canonical envelope and return both the envelope and selected
  rendered payload.
- `GET /api/v1/hydrations/{id}` — read the full envelope while it remains in the bounded current-
  process cache, or after restart only when message retention was enabled when it was created.
- `GET /api/v1/hydrations/{id}/explanation` — selection and omission scores under the same content
  availability rule. Without retained content, expired/restarted hydrations return `410`.
- `POST /api/v1/threads/{id}/usage` — idempotently record normalized usage.
- `GET /api/v1/threads/{id}/stats` — confidence-separated lifetime metrics.
- `GET /api/v1/threads?workspace_id={id}` — list all or workspace-filtered thread summaries.
- `POST /api/v1/exports` — create a sanitized JSONL or Parquet analytics export.

## Provider forwarding

- `POST /api/v1/proxy` — hydrate-first forwarding to the configured OpenAI-compatible upstream.
  The request names a retained/cached `hydration_id`, an idempotency key, `chat/completions` or
  `responses`, and a provider payload. It rejects streaming and remains disabled until both an
  upstream and process-wide outbound consent are configured.

Handled application failures, request-validation failures, and internal failures use
`{error: {code, message, request_id, details}}`. Framework-level unmatched routes can use FastAPI's
default error response. Raw prompts, source bodies, and credentials are omitted from application
logs.

## Local-only boundary

The API has no application authentication or TLS. Keep it on loopback, or place it behind an
authenticated local gateway you operate. It is not a hosted multi-user API, and browser JavaScript
from other origins cannot use it through CORS by default.
