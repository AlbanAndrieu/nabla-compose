#!/usr/bin/env bash
# Write the private credential files read by the scripts/mcp launchers.
#
# Run in the owner's terminal with Vaultwarden unlocked (BW_SESSION). Values go
# from bw straight into 600 files under ~/.config/nabla/mcp and are never
# printed. A field still absent from Vaultwarden is reported and skipped.
# truenas-readonly.key has its own check/apply: scripts/truenas/mcp-readonly-identity.sh.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/mcp/lib.sh
source "${HERE}/lib.sh"

# file|Vaultwarden item|field|line written (printf format)
TARGETS=(
  "litellm-gateway.headers|nabla/prod/litellm-mcp-client|LITELLM_MCP_CLIENT_KEY|x-litellm-api-key: Bearer %s"
  "fastapi-sample.headers|nabla/prod/fastapisample|MCP_OPS_KEY|X-MCP-Key: %s"
)

[[ -n "${BW_SESSION:-}" ]] || {
  echo "❌ unlock Vaultwarden in this terminal first (BW_SESSION is empty)" >&2
  exit 1
}
install -d -m 700 "${MCP_KEY_DIR}"
umask 077

missing=0
for target in "${TARGETS[@]}"; do
  IFS='|' read -r file item field line <<<"${target}"
  if ! value="$(bw_field "${item}" "${field}")"; then
    echo "⚠️  ${file}: ${item} has no ${field}; skipped" >&2
    missing=$((missing + 1))
    continue
  fi
  tmp="$(mktemp "${MCP_KEY_DIR}/.${file}.XXXXXX")"
  # shellcheck disable=SC2059 # the format comes from TARGETS above
  printf "${line}\n" "${value}" >"${tmp}"
  chmod 600 "${tmp}"
  mv -f "${tmp}" "${MCP_KEY_DIR}/${file}"
  echo "✅ ${MCP_KEY_DIR}/${file} (600)"
done
unset value
exit $((missing > 0 ? 3 : 0))
