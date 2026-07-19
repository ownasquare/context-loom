# Troubleshooting

Start with:

```bash
context-loom version
context-loom doctor
```

These commands verify the installed CLI, private state directory, database schema, search support,
and current privacy settings without requiring provider credentials.

## `context-loom` is not found

The executable installed by `uv tool install .` may not yet be on the current shell's `PATH`.

```bash
uv tool update-shell
```

Open a new terminal afterward. If installation itself failed, verify Python 3.11-3.13 is available and
rerun `uv tool install --reinstall .` from the repository root.

## The workbench cannot see my project

Context Loom resolves paths from the machine and process where the server runs.

- Native install: use an existing absolute path readable by your user account.
- Docker: mount the host folder with `CONTEXT_LOOM_PROJECT` and register `/workspace` inside the
  container. The host path is not valid inside the container.
- Remote machine, VM, or subsystem: a path on your laptop is invisible unless mounted or shared into
  that environment.

Context Loom deliberately refuses missing paths, files outside the chosen root, and symlinks that
escape it.

## Port 8768 is already in use

Choose another loopback port:

```bash
context-loom serve --port 8769
```

Then open `http://127.0.0.1:8769`. For Docker, change only the host side of the port mapping in a local
Compose override; keep the container service on port 8768.

## A project scans but no useful sources appear

```bash
context-loom workspace status my-project
context-loom workspace sync my-project
```

Check that the relevant files are text, below the configured size limit, and not excluded by
`.gitignore`, `.contextloomignore`, secret-file rules, binary detection, or an outside-root symlink.
Then make the request more specific by naming the relevant file, symbol, feature, or constraint.

Deterministic similarity is lexical in version 0.1.0. A concept phrased very differently from the
project text may not rank highly without an explicit file or symbol reference.

## A prepared message or explanation now returns `410`

Raw messages are not persisted by default. The full envelope lives in a bounded current-process cache
for a limited time, so it can expire or disappear after a restart. Prepare the message again, or keep
the returned envelope in the calling tool.

Message retention can be enabled explicitly with `--retain-messages`, but that stores exact messages
and envelopes in the private local database. Review the security and retention implications first.

## A desktop chat app cannot start Context Loom

GUI applications often inherit a smaller `PATH` than an interactive terminal. Confirm the installed
binary location with your shell, then put that absolute path into the reviewed MCP configuration.

```bash
command -v context-loom
context-loom adapter preview codex
```

`adapter preview` accepts a harness name such as `codex`, `claude`, `cursor`, `copilot`, `gemini`, or
`generic`. It does not accept renderer IDs such as `openai_responses`, and it never edits configuration.

## Docker starts but `/workspace` is empty or wrong

Set the host path before creating the container:

```bash
export CONTEXT_LOOM_PROJECT=/absolute/path/to/project
docker compose up --build --detach --force-recreate
```

Register `/workspace` inside the container. If permissions still fail, confirm the host directory is
shared with Docker Desktop or readable by the Docker daemon and the image's non-root user (UID
10001). Do not make private source world-readable; grant only the narrow read access your container
runtime requires. The project mount is intentionally read-only; application state belongs in the
separate `/data` named volume.

## MCP or local API connections fail

- For desktop chat apps, prefer MCP over its stdio transport: `context-loom mcp serve --transport stdio`.
- Keep HTTP, SSE, and streamable HTTP on a trusted loopback boundary unless an authenticated local
  gateway is added.
- The HTTP API has no browser CORS allowlist and is not a hosted service.
- Run `context-loom serve` before calling `http://127.0.0.1:8768/api/v1/...`.

If the problem remains, follow [Support](../SUPPORT.md) and remove project text, messages, database
files, credentials, and identifying paths from any report.
