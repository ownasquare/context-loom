# Harness integrations

Context Loom prepares context before delivery and keeps rendering separate from transport. No single
automatic pre-send hook works across every chat harness, so choose one of these three truthful methods.

## 1. Copy and paste (recommended)

Prepare a message in the workbench, review its cited sources and exact-message check, then copy the
complete payload into the destination chat. This is the quickest path, changes no harness files, and
makes no provider request from Context Loom.

Use Generic Markdown for a readable payload or Canonical JSON for a structured envelope. Provider-
shaped formats are described under [Advanced output formats](#advanced-output-formats).

## 2. MCP connection

Generate a standalone configuration snippet for the harness you use. The command prints bare TOML or
JSON with the detected absolute Context Loom executable path; it does not change harness settings.

| Harness | Preview command |
|---|---|
| Codex | `context-loom adapter preview codex` |
| Claude | `context-loom adapter preview claude` |
| Cursor | `context-loom adapter preview cursor` |
| GitHub Copilot | `context-loom adapter preview copilot` |
| Gemini | `context-loom adapter preview gemini` |
| Generic MCP client | `context-loom adapter preview generic` |

`adapter preview` accepts harness names, not renderer IDs such as `openai_responses`. Add the reviewed
snippet to the harness's MCP settings and restart the harness. It will spawn
`context-loom mcp serve --transport stdio` when it needs the connection; do not start that blocking
stdio process manually during ordinary setup. Add `--details` only when you want the snippet metadata
as JSON.

The server exposes structured tools for hydration, explanation, usage recording, thread statistics,
workspace status, and immutable resource-version recovery. Project and MCP text remains untrusted
reference data.

### Verify the connection

After registering and scanning `my-project`, ask the harness to call Context Loom's
`workspace_status` tool with `workspace_id` set to `my-project`. Then ask it to call
`hydrate_message` with this minimal input:

```json
{
  "workspace_id": "my-project",
  "message": "Where is retry behavior defined?",
  "thread_id": "mcp-smoke",
  "adapter": "generic_markdown"
}
```

Success returns a `hydration_id`, the same `message_exact`, cited local context when relevant, and a
projected token plan. No provider request is made. For transport diagnostics only, run
`context-loom mcp serve --transport stdio` in a terminal and stop it with Ctrl+C after confirming it
starts without an error.

`adapter install` can write a reviewed snippet to an explicit standalone file only when `--target`
and `--write` are supplied. It does not merge a global configuration, and it refuses an existing file
unless `--overwrite` is also given.

SSE and streamable HTTP MCP transports are available, but Context Loom adds no authentication or TLS.
Keep them on trusted loopback or behind an authenticated local gateway.

## 3. Local API

Start the workbench/API, then call the versioned loopback endpoint. This example uses the generated
demo so every identifier is known:

```bash
context-loom demo
context-loom serve
```

```bash
curl --fail-with-body --request POST http://127.0.0.1:8768/api/v1/hydrations \
  --header 'Content-Type: application/json' \
  --data '{
    "workspace_id": "demo-workspace",
    "thread_id": "local-api-demo",
    "message": "Where is retry behavior defined?",
    "adapter": "generic_markdown"
  }'
```

The response contains both the canonical envelope and rendered payload. The API is loopback-only by
default, has no CORS allowlist, and is not a hosted authenticated service.

## Advanced output formats

`context-loom adapter list` shows the formats available in the installed version. Built-ins include
OpenAI Responses, OpenAI-compatible Chat, Anthropic Messages, Gemini Contents, Generic Markdown,
Canonical JSON, and copyable Codex/Claude/Cursor/Copilot shapes.

These are renderers, not proof of an automatic harness connection. Anthropic and Gemini are renderer-
only paths. The optional OpenAI-compatible forwarder is an explicit two-step, non-streaming
hydrate-then-forward route; it remains disabled until an upstream and process-wide outbound consent
are configured. Usage is provider-observed only when the forwarder or an explicit import records it.

See [HTTP API](api.md) for endpoints and [Extending Context Loom](extending.md) for the trusted
in-process custom-adapter boundary.
