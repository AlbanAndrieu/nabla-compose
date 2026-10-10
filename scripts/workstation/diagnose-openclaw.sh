#!/usr/bin/env bash
# Read-only OpenClaw workstation diagnostic; no doctor or secret output.
set -euo pipefail
export LC_ALL=C
NODE_ROOT="${OPENCLAW_NODE_ROOT:-$HOME/.local/share/mise/installs/node/24.18.1}"
UNIT="${OPENCLAW_UNIT:-openclaw-gateway.service}"
errors=0; warnings=0
ok(){ printf 'OK %s\n' "$1"; }
warn(){ printf 'WARN %s\n' "$1"; warnings=$((warnings+1)); }
fail(){ printf 'FAIL %s\n' "$1"; errors=$((errors+1)); }
[[ "$NODE_ROOT" == "$HOME/"* ]] || { fail 'runtime outside HOME'; exit 1; }
if [[ -x "$NODE_ROOT/bin/node" ]]; then ok "Node $("$NODE_ROOT/bin/node" --version)"; else fail 'mise Node missing'; fi
if [[ -x "$NODE_ROOT/bin/npm" ]]; then
  prefix="$(env PATH="$NODE_ROOT/bin:$PATH" NPM_CONFIG_PREFIX="$NODE_ROOT" "$NODE_ROOT/bin/npm" prefix -g 2>/dev/null || :)"
  [[ "$prefix" == "$NODE_ROOT" ]] && ok 'npm prefix selects mise' || fail 'npm prefix differs from mise'
else fail 'mise npm missing'; fi
[[ -f "$NODE_ROOT/lib/node_modules/openclaw/openclaw.mjs" ]] && ok 'OpenClaw package exists' || fail 'OpenClaw package missing'
for path in /usr/bin/openclaw /usr/lib/node_modules/openclaw; do
  [[ ! -e "$path" && ! -L "$path" ]] || warn "foreign system destination: $path (preserve)"
done
if command -v systemctl >/dev/null; then
  state="$(systemctl --user is-active "$UNIT" 2>/dev/null || :)"
  [[ "$state" == active ]] && ok 'Gateway active' || fail 'Gateway inactive'
  entry="$(systemctl --user show "$UNIT" -p ExecStart --value 2>/dev/null || :)"
  if [[ "$entry" == *"$NODE_ROOT/bin/node"* ]]; then ok 'service Node matches mise'
  elif [[ "$entry" == *'/usr/bin/node'* ]]; then warn 'service Node uses /usr/bin/node'
  else warn 'service Node unknown'; fi
  [[ "$entry" == *"$NODE_ROOT/lib/node_modules/openclaw/dist/index.js"* ]] && ok 'service package matches mise' || fail 'service package differs'
else fail 'systemctl missing'; fi
printf 'SUMMARY errors=%d warnings=%d\n' "$errors" "$warnings"
(( errors == 0 )) || exit 1
(( warnings == 0 )) || exit 2
