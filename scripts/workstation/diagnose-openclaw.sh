#!/usr/bin/env bash
# Read-only OpenClaw workstation diagnostic; no doctor or secret output.
set -euo pipefail
# Add emoji/color only for interactive operator output; preserve machine-readable pipes.
if [[ -z "${OPENCLAW_STYLE_ACTIVE:-}" && -z "${NO_COLOR+x}" && "${OPENCLAW_COLOR:-auto}" != never && ( -t 1 || "${OPENCLAW_COLOR:-auto}" == always ) ]]; then
  export OPENCLAW_STYLE_ACTIVE=1
  bash "${BASH_SOURCE[0]}" "$@" | python3 "$(dirname -- "${BASH_SOURCE[0]}")/openclaw-terminal-style.py"
  exit "${PIPESTATUS[0]}"
fi
export LC_ALL=C
UNIT="${OPENCLAW_UNIT:-openclaw-gateway.service}"
# Prefer the actual Gateway service owner, not a stale hardcoded Node minor.
# Pinned Node is used only if the service does not report a managed runtime.
NODE_ROOT="${OPENCLAW_NODE_ROOT:-}"
if [[ -z "${NODE_ROOT}" ]]; then
  entry_probe="$(systemctl --user show "${UNIT}" -p ExecStart --value 2>/dev/null || :)"
  runtime_pattern='/node/([0-9]+\.[0-9]+\.[0-9]+)/bin/node'
  if [[ "${entry_probe}" =~ ${runtime_pattern} ]]; then
    candidate="${HOME}/.local/share/mise/installs/node/${BASH_REMATCH[1]}"
    if [[ "${entry_probe}" == *"${candidate}/bin/node"* ]]; then
      NODE_ROOT="${candidate}"
    fi
  fi
fi
if [[ -z "${NODE_ROOT}" ]]; then
  repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
  pinned="$(tr -d 'v[:space:]' < "${repo_root}/.nvmrc")"
  [[ "${pinned}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'FAIL invalid Node pin'; exit 1; }
  NODE_ROOT="${HOME}/.local/share/mise/installs/node/${pinned}"
fi
errors=0; warnings=0
ok(){ printf 'OK %s\n' "$1"; }
warn(){ printf 'WARN %s\n' "$1"; warnings=$((warnings+1)); }
fail(){ printf 'FAIL %s\n' "$1"; errors=$((errors+1)); }
[[ "${NODE_ROOT}" == "${HOME}/"* ]] || { fail 'runtime outside HOME'; exit 1; }
if [[ -x "${NODE_ROOT}/bin/node" ]]; then
  version="$("${NODE_ROOT}/bin/node" --version)"
  ok "Node ${version}"
  if [[ "${version}" =~ ^v24\.([0-9]+)\.([0-9]+)$ ]]; then
    minor="${BASH_REMATCH[1]}"; patch="${BASH_REMATCH[2]}"
    if (( minor < 22 || (minor == 22 && patch < 1) )); then
      warn 'Gateway Node below OpenClaw 2026.10.7 minimum 24.22.1'
    fi
  fi
else fail 'mise Node missing'; fi
if [[ -x "${NODE_ROOT}/bin/npm" ]]; then
  prefix="$(env PATH="${NODE_ROOT}/bin:${PATH}" NPM_CONFIG_PREFIX="${NODE_ROOT}" "${NODE_ROOT}/bin/npm" prefix -g 2>/dev/null || :)"
  if [[ "${prefix}" == "${NODE_ROOT}" ]]; then
    ok 'npm prefix selects mise'
  else
    fail 'npm prefix differs from mise'
  fi
else fail 'mise npm missing'; fi
if [[ -f "${NODE_ROOT}/lib/node_modules/openclaw/openclaw.mjs" ]]; then
  ok 'OpenClaw package exists'
else
  fail 'OpenClaw package missing'
fi
for path in /usr/bin/openclaw /usr/lib/node_modules/openclaw; do
  [[ ! -e "${path}" && ! -L "${path}" ]] || warn "foreign system destination: ${path} (preserve)"
done
if command -v systemctl >/dev/null; then
  state="$(systemctl --user is-active "${UNIT}" 2>/dev/null || :)"
  if [[ "${state}" == active ]]; then
    ok 'Gateway active'
  else
    fail 'Gateway inactive'
  fi
  entry="$(systemctl --user show "${UNIT}" -p ExecStart --value 2>/dev/null || :)"
  if [[ "${entry}" == *"${NODE_ROOT}/bin/node"* ]]; then ok 'service Node matches mise'
  elif [[ "${entry}" == *'/usr/bin/node'* ]]; then warn 'service Node uses /usr/bin/node'
  else warn 'service Node unknown'; fi
  if [[ "${entry}" == *"${NODE_ROOT}/lib/node_modules/openclaw/dist/index.js"* ]]; then
    ok 'service package matches mise'
  else
    fail 'service package differs'
  fi
else fail 'systemctl missing'; fi
printf 'SUMMARY errors=%d warnings=%d\n' "${errors}" "${warnings}"
(( errors == 0 )) || exit 1
(( warnings == 0 )) || exit 2
