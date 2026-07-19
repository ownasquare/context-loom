#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
npm --prefix frontend run build
uv run context-loom demo
uv run context-loom serve
