#!/usr/bin/env bash
# Read-only review of a proposed systemd override; nothing is installed.
set -euo pipefail
# Add emoji/color only for interactive operator output; preserve machine-readable pipes.
if [[ -z "${OPENCLAW_STYLE_ACTIVE:-}" && -z "${NO_COLOR+x}" && "${OPENCLAW_COLOR:-auto}" != never && ( -t 1 || "${OPENCLAW_COLOR:-auto}" == always ) ]]; then
  export OPENCLAW_STYLE_ACTIVE=1
  bash "${BASH_SOURCE[0]}" "$@" | python3 "$(dirname -- "${BASH_SOURCE[0]}")/openclaw-terminal-style.py"
  exit "${PIPESTATUS[0]}"
fi
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
pinned="$(tr -d 'v[:space:]' < "${repo_root}/.nvmrc")"
[[ "${pinned}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Invalid Node version pin' >&2; exit 1; }
NODE_ROOT="${OPENCLAW_NODE_ROOT:-${HOME}/.local/share/mise/installs/node/${pinned}}"
UNIT="${OPENCLAW_UNIT:-openclaw-gateway.service}"
[[ "${NODE_ROOT}" == "${HOME}/"* && -x "${NODE_ROOT}/bin/node" && -f "${NODE_ROOT}/lib/node_modules/openclaw/dist/index.js" ]] || { echo 'Invalid or missing mise runtime' >&2; exit 1; }
entry="$(systemctl --user show "${UNIT}" -p ExecStart --value 2>/dev/null || :)"
[[ "${entry}" == *"${HOME}/.local/share/mise/installs/node/"*"/lib/node_modules/openclaw/dist/index.js"* ]] || { echo 'Service package owner mismatch; abort' >&2; exit 1; }
[[ "${entry}" == *'--max-old-space-size=16053'* && "${entry}" == *'gateway --port 18789'* ]] || { echo 'Unexpected service flags; manual review required' >&2; exit 2; }
cat <<TEMPLATE
# PROPOSAL ONLY: ~/.config/systemd/user/${UNIT}.d/10-mise-runtime.conf
# Apply only after private backup and maintenance approval.
[Service]
ExecStart=
ExecStart=${NODE_ROOT}/bin/node --max-old-space-size=16053 ${NODE_ROOT}/lib/node_modules/openclaw/dist/index.js gateway --port 18789
Environment=NPM_CONFIG_PREFIX=${NODE_ROOT}
TEMPLATE
echo 'No files changed. Preserve the existing EnvironmentFile and PATH.' >&2
