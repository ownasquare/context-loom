# Contributing

Context Loom welcomes focused issues and pull requests that preserve its local-first, source-first
contract.

## Repository layout

- `src/context_loom/` — Python runtime, API, CLI, storage, retrieval, and packaged workbench assets.
- `frontend/` — React workbench source and frontend tests.
- `tests/` — Python unit, integration, contract, and Playwright tests.
- `examples/` — credential-free sample projects and extension examples.
- `docs/` — user guides, architecture, security, fidelity, accounting, and operational references.
- `scripts/` — validation, packaging, benchmark, and container checks.

## Set up

Python contributors need Python 3.11-3.13 and `uv`:

```bash
uv sync --frozen
uv run pytest -q
```

Node is not needed to use the installed package or to change Python-only code and documentation. Use
Node 22, the checked-in CI baseline, when changing or validating the workbench:

```bash
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend run test:component
npm --prefix frontend run build
npx --prefix frontend playwright install chromium
npm --prefix frontend run test:e2e
```

## Focused validation loops

- Python behavior: `uv run pytest tests/path/to/test_file.py -q`
- Adapter extension surface: `uv run pytest tests/contract/test_renderers.py tests/contract/test_api.py tests/contract/test_container.py -q`
- Runnable extension example: `uv run python examples/extensions/custom_adapter.py`
- React component behavior: `npm --prefix frontend run test:component`
- End-to-end workbench behavior: `npm --prefix frontend run test:e2e`
- Public documentation and packaging boundary: `uv run python scripts/check_public_repo.py`
- Distribution install: `make package-smoke`
- Container runtime and mounted-project persistence: `make container-smoke`

Pytest owns Python tests. Cypress is component-only. Playwright owns all E2E tests. Live Ollama,
provider, and real-harness tests use the `live` marker and remain explicit opt-in proof.

## Design constraints

- Preserve the exact user message; optimize surrounding context only.
- Give every excerpt and generated claim current version, hash, and location provenance.
- Treat repository text, tool metadata, and MCP content as untrusted data.
- Keep SQLite/CAS canonical and every search or analytics index rebuildable.
- Put provider behavior behind an adapter and explicit outbound consent.
- Never merge projected, provider-observed, and verified token measurements.
- Treat custom adapters as trusted in-process code; collectors and tokenizers are not public plugins.

## Pull requests

Explain the user-visible outcome, fidelity and security implications, changed public contracts, exact
validation commands, and proof boundaries. Include migration and compatibility notes for schema or
adapter changes.

Never commit credentials, raw private workspaces, local databases, message logs, machine-local paths,
or internal handoff material. Keep local, browser, container, provider, real-harness, hosted, and
production proof separate.
