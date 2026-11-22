#!/usr/bin/env bash
# Start the read-only Gatus MCP (adambenhassen/gatus-mcp) for one session.
#
# The server only speaks Streamable HTTP and has no published image: build it
# once at a pinned commit, run it on a random loopback port for the life of this
# launcher, and bridge it to stdio with mcp-remote. No GATUS_TOKEN is given, so
# its only write tool (submit_external_result) stays unusable.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/mcp/lib.sh
source "${HERE}/lib.sh"

GATUS_MCP_COMMIT=4c7ed599114d920437bd37f6590744573e361e46
BIN_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/nabla/mcp/gatus-mcp-${GATUS_MCP_COMMIT:0:12}"
BIN="${BIN_DIR}/gatus-mcp"

if [[ ! -x "${BIN}" ]]; then
  echo "gatus: building gatus-mcp@${GATUS_MCP_COMMIT:0:12}" >&2
  GOBIN="${BIN_DIR}" GOTOOLCHAIN=auto go install \
    "github.com/adambenhassen/gatus-mcp/cmd/gatus-mcp@${GATUS_MCP_COMMIT}" >&2
fi

port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
# stdout is the MCP channel: the server logs go to stderr.
GATUS_URL="${GATUS_MCP_GATUS_URL:-http://172.17.0.24:8085}" MCP_HOST=127.0.0.1 MCP_PORT="${port}" \
  "${BIN}" </dev/null >&2 &
server=$!
trap 'kill "${server}" 2>/dev/null || true' EXIT

for _ in $(seq 50); do
  curl -fsS -o /dev/null "http://127.0.0.1:${port}/health" 2>/dev/null && break
  kill -0 "${server}" 2>/dev/null || {
    echo "gatus: gatus-mcp exited" >&2
    exit 1
  }
  sleep 0.2
done

cd "${HERE}"
npx -y "${MCP_REMOTE_PACKAGE}" "http://127.0.0.1:${port}/mcp" --allow-http
