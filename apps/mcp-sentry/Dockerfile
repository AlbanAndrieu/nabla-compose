# Sentry MCP (stdio only) behind mcp-proxy (streamable HTTP, inbound bearer).
FROM python:3.13-alpine@sha256:9ef1a599f863231c3d91e941389bfdc4a2d6070557243d54df1a4e57015b960e

# Alpine's nodejs follows the pinned base image; the npm and PyPI packages are pinned.
# hadolint ignore=DL3018
RUN apk add --no-cache nodejs npm \
    && npm install --global --omit=dev @sentry/mcp-server@0.39.0 \
    && npm cache clean --force \
    && pip install --no-cache-dir mcp-proxy==0.15.0

LABEL name="mcp-sentry" version="0.39.0"
USER 65532:65532
ENTRYPOINT ["mcp-proxy"]
