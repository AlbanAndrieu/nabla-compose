# DefectDojo MCP (stdio only, pinned commit) behind mcp-proxy (streamable HTTP, inbound bearer).
FROM python:3.13-alpine@sha256:9ef1a599f863231c3d91e941389bfdc4a2d6070557243d54df1a4e57015b960e

ARG DEFECTDOJO_MCP_COMMIT=4d34d17f346dccab92e97e3d50e77b568689f283

# git is only needed to fetch the pinned commit.
# hadolint ignore=DL3018
RUN apk add --no-cache --virtual .fetch git \
    && pip install --no-cache-dir mcp-proxy==0.15.0 \
        "defectdojo-mcp-server @ git+https://github.com/dcianciulli/defectdojo-mcp-server@${DEFECTDOJO_MCP_COMMIT}" \
    && apk del .fetch

LABEL name="mcp-defectdojo" version="0.0.0+4d34d17f"
USER 65532:65532
# The bearer guards /mcp, so the probe only checks that mcp-proxy accepts connections (--port=8000).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python3", "-c", "import socket; socket.create_connection(('127.0.0.1', 8000), 3).close()"]
ENTRYPOINT ["mcp-proxy"]
