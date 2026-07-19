# Validation strategy

Context Loom keeps proof layers separate.

| Layer | Evidence |
|---|---|
| Unit | contracts, redaction, chunking, intent, ranking, protected atoms, token math |
| Integration | migrations, WAL, CAS, sync lifecycle, FTS, hydration, usage, restart readback |
| Contract | API errors/routes, adapter payloads, MCP tools, proxy usage normalization |
| Component | React states and interactions in Cypress component mode only |
| E2E | complete workbench journeys in Playwright only |
| Package | wheel/sdist contents and clean-environment CLI/API smoke |
| Container | non-root startup, health, write-volume, restart/readback |
| Browser | desktop/tablet/mobile, light/dark, console, keyboard, screenshots |
| Live | optional Ollama, provider, and real-harness smoke tests |

Acceptance gates include 100% explicit safe-reference recall in fixtures, 100% protected-atom
preservation, valid citations for every digest claim, deterministic replay, no secret persistence or
emission, idempotent usage, unknown-not-zero missing usage, and at least 95% golden Recall@10.

Local fixture, localhost browser, container, live provider, hosted, and production proof are reported
independently. A high unit-test count never upgrades an unrun environment.

## Release commands

```bash
uv run pytest --cov=context_loom --cov-report=term-missing -q
uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
uv run mypy src
uv run bandit -q -r src
uv run pip-audit
npm --prefix frontend run typecheck
npm --prefix frontend run test:component
npm --prefix frontend run build
npm --prefix frontend run test:e2e
npm --prefix frontend audit --omit=dev
uv run python scripts/benchmark.py --iterations 5 --check
uv build
uv run python scripts/package_smoke.py
./scripts/container_smoke.sh
```

Run Cypress component tests and Playwright E2E serially because both can start a Vite server on the
configured preview port. The Playwright suite contains both Vite-backed demo journeys and a separate
journey that builds, installs, and serves the wheel from an isolated environment. The latter proves
the packaged FastAPI workbench, direct SPA route reloads, multi-turn continuity, and usage readback
without importing Context Loom from the source checkout.

The production dependency gate is `npm audit --omit=dev`. Also run and record the full
`npm --prefix frontend audit` report separately because it covers development tools such as Cypress
and Playwright and must not be conflated with the production dependency boundary. Both reports are
green for the current lockfile; any future development-only finding remains separately tracked even
when the production-only gate is green.

`scripts/benchmark.py --check` is a smoke-regression gate over the three versioned bundled cases. It
includes one-file-change synchronization latency and replay evidence, but it is not a full task-
quality, scanner-performance, or provider-savings proof. See `benchmark.md` for the exact metrics and
omissions.
