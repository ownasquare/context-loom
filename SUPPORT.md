# Support

Start with the [troubleshooting guide](docs/troubleshooting.md), then run:

```bash
context-loom version
context-loom doctor
```

Contributors should also run the smallest relevant test target from [Contributing](CONTRIBUTING.md).

For a reproducible report, include:

- Context Loom version and installation method;
- operating system and Python version;
- command, route, or workbench page;
- expected behavior and sanitized actual behavior;
- a minimal public fixture when one is necessary; and
- whether evidence is local, container, browser, live Ollama, provider, or real-harness proof.

Never attach raw databases, workspace content, chat messages, credentials, identifying absolute paths,
or private provider responses.

## Public support routes

Use the repository's [structured issue forms](https://github.com/ownasquare/context-loom/issues/new/choose)
for bugs and feature requests. Context Loom does not currently claim a hosted support service or a
PyPI distribution.

Report vulnerabilities only through a private security-advisory route that is visibly available on
the published repository. Do not put vulnerability details in a public issue. If no private route is
available, retain the sanitized report until the project publishes one rather than transmitting it
through an insecure channel.
