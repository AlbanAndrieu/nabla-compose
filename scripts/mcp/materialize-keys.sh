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
  "homarr.headers|nabla/prod/homarr|HOMARR_API_KEY|ApiKey: %s"
  "grafana.env|nabla/prod/grafana-observability|GRAFANA_SERVICE_ACCOUNT_TOKEN|GRAFANA_SERVICE_ACCOUNT_TOKEN=%s"
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
  if ! value="$(bw list items --search "${item}" | jq -er --arg n "${item}" --arg f "${field}" \
    '[.[] | select(.name == $n)] | if length == 1 then .[0] else error("expected one item") end
     | [.fields[]? | select(.name == $f) | .value | select(. != null and . != "")] | first // error("field absent")')"; then
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
