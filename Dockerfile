# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm --prefix frontend ci
COPY frontend ./frontend
COPY src ./src
RUN npm --prefix frontend run build

FROM ghcr.io/astral-sh/uv:0.12.0 AS uv

FROM python:3.12-slim-bookworm AS builder
WORKDIR /build
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY --from=frontend /build/src/context_loom/static ./src/context_loom/static
RUN uv build --wheel --out-dir /dist \
    && uv export --quiet --frozen --no-dev --no-editable --no-emit-project \
      --format requirements-txt --output-file /tmp/runtime-requirements.txt \
    && uv venv /opt/context-loom \
    && uv pip sync --python /opt/context-loom/bin/python /tmp/runtime-requirements.txt \
    && uv pip install --python /opt/context-loom/bin/python --no-deps /dist/context_loom-*.whl

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/context-loom/bin:$PATH \
    CONTEXT_LOOM_HOME=/data \
    CONTEXT_LOOM_HOST=0.0.0.0 \
    CONTEXT_LOOM_ALLOW_NON_LOOPBACK=true \
    CONTEXT_LOOM_ALLOW_OUTBOUND=false
RUN groupadd --gid 10001 contextloom \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin contextloom \
    && mkdir -p /data \
    && chown 10001:10001 /data
COPY --from=builder /opt/context-loom /opt/context-loom
USER 10001:10001
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8768
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8768/readyz', timeout=2).read()"]
ENTRYPOINT ["context-loom"]
CMD ["serve"]
