#!/usr/bin/env bash
# Read-only TrueNAS shared data diagnostics. Never print credentials.
set -euo pipefail
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != dumb ]]; then
  GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; BLUE=$'\e[36m'; RESET=$'\e[0m'
else
  GREEN='' RED='' YELLOW='' BLUE='' RESET=''
fi
section() { printf '\n%b🔎 %s%b\n' "${BLUE}" "$1" "${RESET}"; }
pass() { printf '%b✅ PASS%b %s\n' "${GREEN}" "${RESET}" "$1"; }
warn() { printf '%b⚠️ WARN%b %s\n' "${YELLOW}" "${RESET}" "$1"; }
fail() { printf '%b❌ FAIL%b %s\n' "${RED}" "${RESET}" "$1" >&2; }
failures=0
warnings=0
command -v docker >/dev/null || { fail 'docker absent'; exit 2; }
section 'PostgreSQL partagé'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  fail 'PostgreSQL absent ou arrêté'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  pass 'PostgreSQL accepte les connexions (authentification non testée)'
else
  fail 'PostgreSQL ne répond pas'
  failures=$((failures + 1))
fi
section 'Redis partagé'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  fail 'Redis absent ou arrêté'
  failures=$((failures + 1))
else
  password="${REDIS_AUTH:-}"
  secret_file=/mnt/cpool/secrets/runtime/redis/.env.secrets
  if [[ -z "${password}" && -r "${secret_file}" ]]; then
    password="$(python3 - "${secret_file}" <<'PY'
import pathlib
import sys
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    if line.startswith("REDIS_AUTH="):
        value = line.partition("=")[2]
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        print(value, end="")
        break
PY
)"
  fi
  if [[ -z "${password}" ]]; then
    warn 'Redis : secret indisponible ; authentification non testée'
    warnings=$((warnings + 1))
  else
    # Supply the credential on stdin, not on the command line.
    redis_exec() {
      printf '%s\n' "${password}" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw "$@" 2>/dev/null
      ' sh "$@" 2>/dev/null
    }
    if [[ "$(redis_exec PING)" == PONG ]]; then
      pass 'Redis authentifié : PING → PONG'
      section 'Redis · bases contenant des clés'
      redis_exec INFO keyspace | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      fail 'Redis : PING authentifié en échec'
      failures=$((failures + 1))
    fi
  fi
  unset password
fi
if (( failures > 0 )); then
  fail "Bilan : ${failures} échec(s), ${warnings} avertissement(s)"
  exit 1
fi
pass "Bilan : 0 échec, ${warnings} avertissement(s)"
