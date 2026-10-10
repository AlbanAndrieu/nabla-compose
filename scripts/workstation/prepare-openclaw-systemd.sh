#!/usr/bin/env bash
# Read-only review of a proposed systemd override; nothing is installed.
set -euo pipefail
NODE_ROOT="${OPENCLAW_NODE_ROOT:-$HOME/.local/share/mise/installs/node/24.18.1}"
UNIT="${OPENCLAW_UNIT:-openclaw-gateway.service}"
[[ "$NODE_ROOT" == "$HOME/"* && -x "$NODE_ROOT/bin/node" && -f "$NODE_ROOT/lib/node_modules/openclaw/dist/index.js" ]] || { echo 'Invalid or missing mise runtime' >&2; exit 1; }
entry="$(systemctl --user show "$UNIT" -p ExecStart --value 2>/dev/null || :)"
[[ "$entry" == *"$NODE_ROOT/lib/node_modules/openclaw/dist/index.js"* ]] || { echo 'Service package mismatch; abort' >&2; exit 1; }
[[ "$entry" == *'/usr/bin/node'* && "$entry" == *'--max-old-space-size=16053'* && "$entry" == *'gateway --port 18789'* ]] || { echo 'Unexpected service flags; manual review required' >&2; exit 2; }
cat <<TEMPLATE
# PROPOSAL ONLY: ~/.config/systemd/user/$UNIT.d/10-mise-runtime.conf
# Apply only after private backup and maintenance approval.
[Service]
ExecStart=
ExecStart=$NODE_ROOT/bin/node --max-old-space-size=16053 $NODE_ROOT/lib/node_modules/openclaw/dist/index.js gateway --port 18789
Environment=NPM_CONFIG_PREFIX=$NODE_ROOT
TEMPLATE
echo 'No files changed. Preserve the existing EnvironmentFile and PATH.' >&2
