# Extending Context Loom

Context Loom has one deliberately small public extension seam: an embedder may add prompt-rendering
adapters to an application it constructs. It does not auto-discover plugins.

## Trust boundary

Adapters are ordinary Python objects loaded into the Context Loom process. They are trusted code with
the same filesystem and network permissions as that process; installing an adapter is equivalent to
installing and running a Python package. Review its source and dependencies first.

The extension API does not sandbox adapters, grant limited capabilities, or make untrusted code safe.

## Adapter contract

Import the supported types from `context_loom.extensions`. An adapter supplies:

- one unique `AdapterCapability.id`;
- a `render(PromptEnvelope) -> RenderedPrompt` method;
- the exact original message in `RenderedPrompt.exact_message`; and
- a payload that actually contains that exact message in the destination's user-message position.

The registry rejects duplicate or mismatched IDs, a returned `exact_message` that differs
byte-for-byte from the canonical envelope, and payloads that do not contain that exact string. The
adapter author remains responsible for putting it in the destination's real user-message position,
for the rest of the payload semantics, for avoiding hidden transport side effects, and for testing
the destination format.

```python
from context_loom.extensions import (
    AdapterCapability,
    AdapterRegistry,
    PromptEnvelope,
    RenderedPrompt,
    Settings,
    create_application,
)


class PlainTextAdapter:
    capability = AdapterCapability(
        id="plain_text",
        display_name="Plain text",
        injection="manual",
        usage_visibility="manual",
        formats=["text"],
        install_supported=False,
    )

    def render(self, envelope: PromptEnvelope) -> RenderedPrompt:
        return RenderedPrompt(
            adapter=self.capability.id,
            media_type="text/plain",
            payload=f"Request:\n{envelope.message_exact}",
            exact_message=envelope.message_exact,
        )


registry = AdapterRegistry(extra_adapters=[PlainTextAdapter()])
application = create_application(Settings(), adapter_registry=registry)
```

The complete credential-free example creates a temporary project, calls the application in-process,
and renders one hydration:

```bash
uv run python examples/extensions/custom_adapter.py
```

CI executes this example so documentation and the public adapter surface cannot drift silently.

## Run the custom application

The companion factory starts the normal loopback API and workbench with `ChecklistAdapter` injected:

```bash
uv run uvicorn --factory examples.extensions.custom_server:create_custom_app \
  --host 127.0.0.1 --port 8769
```

It uses the same private Context Loom state and registered projects as the standard service. Confirm
the extension at `http://127.0.0.1:8769/api/v1/adapters`, then select `checklist` in a
`POST /api/v1/hydrations` request. Copy this factory into your own trusted package when the adapter
must persist across restarts.

## Where custom adapters appear

An injected registry is used by the FastAPI application returned from `create_application`. Its
capabilities appear in `GET /api/v1/adapters`, and its IDs can be selected in
`POST /api/v1/hydrations`.

The installed `context-loom` CLI, default `context-loom serve`, MCP server, and OpenAI-compatible
forwarder construct built-in behavior and do not discover custom adapters. Run an explicit factory
like the example above, embed your application, or contribute a built-in adapter when those entry
points need the format.

## Internal extension points

Collectors, tokenizers, retrieval services, storage repositories, and local-model compactors are not
public plugin APIs in version 0.1.0. Some internal classes are importable for tests and project
development, but compatibility is not promised. Changes to those surfaces should be proposed as a
source contribution with security, fidelity, provenance, and deterministic regression coverage.

In particular, an in-process collector could execute arbitrary code. A future collector plugin system
would need an explicit trusted-code policy plus centralized path, redaction, size, count, and
non-execution boundaries before it could be described as safe.
