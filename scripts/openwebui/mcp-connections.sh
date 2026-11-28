#!/usr/bin/env bash
# Open WebUI -> LiteLLM MCP gateway connections as code (check, then apply).
#
# One MCP connection per LiteLLM MCP server, at http://172.17.0.24:4000/mcp/<server>:
# a chat enables only the servers it needs, which keeps the tool list small for
# the local model. Authentication: the MCP client virtual key that
# scripts/litellm/mcp-gateway.sh writes to litellm-gateway.headers (MCP access
# group nabla-mcp, no LLM model). The key reaches the container through ssh
# stdin, never an argv, and is never printed. The rows carry no access_grants,
# so Open WebUI keeps them admin-only.
#
# Usage (workstation, TrueNAS ControlMaster open):
#   scripts/openwebui/mcp-connections.sh check
#   scripts/openwebui/mcp-connections.sh apply
set -euo pipefail

MODE="${1:-}"
case "${MODE}" in
  check | apply) ;;
  *)
    echo "usage: $0 check|apply" >&2
    exit 2
    ;;
esac

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SSH_HOST="${TRUENAS_SSH_HOST:-truenas}"
GATEWAY=http://172.17.0.24:4000/mcp
HEADERS_FILE="${MCP_KEY_DIR:-${HOME}/.config/nabla/mcp}/litellm-gateway.headers"
# The servers LiteLLM serves to the nabla-mcp group (config.yaml, mcp-gateway.sh), 28/11.
SERVERS=(fastapisample gatus cyberbro grafana sentry defectdojo homarr ntopng)
REMOTE_SCRIPT=/tmp/nabla-openwebui-tool-servers.py

die() {
  echo "❌ $*" >&2
  exit 1
}

remote() { # ARGS... : run in the openwebui container, stdin forwarded
  ssh -o BatchMode=yes "${SSH_HOST}" "sudo -n docker exec -i openwebui $*"
}

remote "sh -c 'cat > ${REMOTE_SCRIPT}'" <"${ROOT}/scripts/openwebui/tool_servers.py"
want="$(printf 'litellm-%s\n' "${SERVERS[@]}" | sort | xargs)"
have="$(remote "python3 ${REMOTE_SCRIPT} check" </dev/null)"

if [[ "${MODE}" == check ]]; then
  if [[ "${have}" == "${want}" ]]; then
    echo "✅ Open WebUI has the ${#SERVERS[@]} LiteLLM MCP connections"
    remote "python3 ${REMOTE_SCRIPT} verify" </dev/null
  else
    echo "⚠️  drift: have [${have}], want [${want}]"
  fi
  exit 0
fi

[[ -r "${HEADERS_FILE}" ]] || die "${HEADERS_FILE} missing: run scripts/litellm/mcp-gateway.sh apply first"
KEY="$(sed -n 's/^x-litellm-api-key:[[:space:]]*//Ip' "${HEADERS_FILE}")"
[[ -n "${KEY}" ]] || die "${HEADERS_FILE} has no x-litellm-api-key header"
printf '%s\n' "${SERVERS[@]}" | KEY="${KEY}" jq -Rnc --arg gw "${GATEWAY}" '[inputs | {
    url: "\($gw)/\(.)", path: "", type: "mcp", auth_type: "none", key: "",
    headers: {"x-litellm-api-key": $ENV.KEY},
    config: {enable: true},
    info: {id: "litellm-\(.)", name: "\(.) (LiteLLM)", description: "LiteLLM MCP gateway: \(.) tools"}
  }]' | remote "python3 ${REMOTE_SCRIPT} apply"
remote "python3 ${REMOTE_SCRIPT} verify" </dev/null
