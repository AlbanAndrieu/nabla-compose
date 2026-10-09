#!/usr/bin/env bash
# OpenClaw workstation preflight: intentionally read-only.
set -euo pipefail

OPENCLAW_NODE_VERSION="${OPENCLAW_NODE_VERSION:-24.18.1}"
NODE_ROOT="${HOME}/.local/share/mise/installs/node/${OPENCLAW_NODE_VERSION}"
SERVICE="openclaw-gateway.service"
errors=0
warnings=0

ok() { printf 'OK: %s\n' "$1"; }
warn() { printf 'WARN: %s\n' "$1"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL: %s\n' "$1"; errors=$((errors + 1)); }

printf 'OpenClaw workstation audit (read-only)\n'
printf 'Expected mise runtime: %s\n' "$NODE_ROOT"
if [[ -x "$NODE_ROOT/bin/node" ]]; then
  ok "mise Node available: $("$NODE_ROOT/bin/node" --version)"
else
  fail "mise Node executable missing"
fi

if [[ -x "$NODE_ROOT/bin/npm" ]]; then
  actual_prefix="$(PATH="$NODE_ROOT/bin:$PATH" NPM_CONFIG_PREFIX="$NODE_ROOT" "$NODE_ROOT/bin/npm" prefix -g 2>/dev/null || true)"
  [[ "$actual_prefix" == "$NODE_ROOT" ]] && ok 'isolated npm prefix matches mise runtime' || fail 'isolated npm prefix mismatch'
else
  fail 'mise npm executable missing'
fi

if [[ -f "$NODE_ROOT/lib/node_modules/openclaw/openclaw.mjs" ]]; then
  ok 'mise OpenClaw package exists'
else
  fail 'mise OpenClaw entrypoint missing'
fi

for path in /usr/bin/openclaw /usr/lib/node_modules/openclaw; do
  if [[ -e "$path" || -L "$path" ]]; then
    warn "separate system destination present; DO NOT modify: $path"
  fi
done

if command -v systemctl >/dev/null 2>&1; then
  state="$(systemctl --user is-active "$SERVICE" 2>/dev/null || true)"
  [[ "$state" == "active" ]] && ok 'Gateway user service active' || fail "Gateway user service not active ($state)"
  # 'systemctl show' reads unit metadata only; do not print Environment or EnvironmentFiles.
  entry="$(systemctl --user show "$SERVICE" -p ExecStart --value 2>/dev/null || true)"
  if [[ "$entry" == *"/usr/bin/node"* ]]; then
    warn 'Gateway runs /usr/bin/node rather than canonical mise Node'
  elif [[ "$entry" == *"$NODE_ROOT/bin/node"* ]]; then
    ok 'Gateway uses canonical mise Node'
  else
    warn 'Gateway Node launcher could not be confirmed'
  fi
  if [[ "$entry" == *"$NODE_ROOT/lib/node_modules/openclaw/dist/index.js"* ]]; then
    ok 'Gateway points to canonical mise OpenClaw package'
  else
    fail 'Gateway package path differs from canonical mise installation'
  fi
else
  fail 'systemctl is not available'
fi

# Do not run doctor: the 2026.9.5 doctor --non-interactive was observed to install a plugin.
# Do not print systemd Environment, gateway JSON, process commandlines or message content.
printf 'Summary: errors=%s warnings=%s\n' "$errors" "$warnings"
if (( errors > 0 )); then exit 1; fi
if (( warnings > 0 )); then exit 2; fi
exit 0
