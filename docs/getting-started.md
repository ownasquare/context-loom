# Getting started

This guide takes you from a source checkout to one prepared, reviewable message. Package users do not
need Node; the built React workbench is included in the Python package.

## Requirements

- Python 3.11, 3.12, or 3.13
- [`uv`](https://docs.astral.sh/uv/)
- A local project folder containing text source or documentation

The checked-in CI workflow includes package/CLI smoke jobs for Linux, macOS, and Windows; its full
browser and container suites run on Linux. No hosted run is asserted until the public repository runs
that workflow successfully.

## Install from GitHub

Clone the public source repository and install its bundled workbench:

```bash
git clone https://github.com/ownasquare/context-loom.git
cd context-loom
uv tool install .
context-loom version
context-loom doctor
```

Context Loom is not currently distributed through PyPI; use this source install for the public beta.

If the command is not found, run `uv tool update-shell`, restart the terminal, and try again. Reinstall
the current checkout after an update with `uv tool install --reinstall .`.

## Flow A: try the generated demo

```bash
context-loom demo
context-loom serve
```

Open `http://127.0.0.1:8768`. The demo creates `demo-workspace` in Context Loom's private state
directory, indexes it, and prepares one message in `demo-thread`. It uses no provider credentials and
makes no outbound request.

First success looks like this:

1. **Home** shows the Demo workspace and a recent conversation.
2. **Prepare** can prepare another message for that project.
3. The result shows the exact request, cited project excerpts, and a complete copyable payload.
4. **Savings** labels the reduction as projected until provider usage is entered or imported.

## Flow B: use your own project

Start the service without running the demo:

```bash
context-loom init
context-loom serve
```

Open the workbench, choose **Add project**, enter an absolute local folder path, and select **Add and
scan project**. The folder must be readable by the same OS account that started Context Loom.

For a CLI-first setup:

```bash
context-loom workspace add /absolute/path/to/project --name "My project" --id my-project
context-loom workspace sync my-project
context-loom hydrate my-project "Where is retry behavior defined?" --thread-id retry-review
context-loom serve
```

Keep the same thread ID or conversation in later turns to build lifetime totals. Actual provider usage
remains unknown until a provider, proxy, wrapper, or operator records it.

## Flow C: run with Docker

Docker Compose stores application state in `context-loom-data` and mounts one host project read-only
at `/workspace`. The web service remains published only on host loopback.

```bash
export CONTEXT_LOOM_PROJECT=/absolute/path/to/project
docker compose up --build --detach
```

Register and scan the container path—not the host path:

```bash
docker compose exec context-loom context-loom workspace add /workspace --name "My project" --id my-project
docker compose exec context-loom context-loom workspace sync my-project
docker compose exec context-loom context-loom hydrate my-project "Where is retry behavior defined?" --thread-id retry-review
```

Open `http://127.0.0.1:8768`. If `CONTEXT_LOOM_PROJECT` is unset, Compose mounts
`./examples/demo-workspace`; you must still register `/workspace`. Changing the host variable requires
recreating the container. The named volume survives ordinary `docker compose down` operations.

## Next steps

- Choose a delivery method in [Harness integrations](harness-integrations.md).
- Learn what the numbers mean in [Token accounting](token-accounting.md).
- Review [Security](security.md) before enabling retention, network transports, Ollama, or forwarding.
- Use [Troubleshooting](troubleshooting.md) when the first run does not match this walkthrough.
