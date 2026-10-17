#!/usr/bin/env bash
# Read-only TrueNAS shared data diagnostics. Never print credentials.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/diagnostic-ui.sh
source "${SCRIPT_DIR}/../lib/diagnostic-ui.sh"
diag_ui_init "${DIAG_COLOR:-auto}" "${DIAG_ICONS:-auto}" || exit 2

command -v docker >/dev/null || { diag_fail 'docker absent'; exit 2; }
diag_section '1/2' 'PostgreSQL partagé'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  diag_fail 'PostgreSQL absent ou arrêté'
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  diag_ok 'PostgreSQL accepte les connexions (authentification non testée)'
else
  diag_fail 'PostgreSQL ne répond pas'
fi
diag_section '2/2' 'Redis partagé'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  diag_fail 'Redis absent ou arrêté'
else
  password="${REDIS_AUTH:-}"
  secret_file=/mnt/cpool/secrets/runtime/redis/.env.secrets
  if [[ -z "${password}" && -r "${secret_file}" ]]; then
    # Only REDIS_AUTH is read; the rest of the env file is never parsed.
    password="$(sed -n 's/^REDIS_AUTH=//p' "${secret_file}" | head -n 1)"
    if [[ "${password}" == \"*\" && ${#password} -ge 2 ]]; then
      password="${password:1:${#password}-2}"
    fi
  fi
  if [[ -z "${password}" ]]; then
    diag_warn 'Redis : secret indisponible ; authentification non testée'
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
      diag_ok 'Redis authentifié : PING → PONG'
      diag_info 'Redis · bases contenant des clés'
      redis_exec INFO keyspace | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      diag_fail 'Redis : PING authentifié en échec'
    fi
  fi
  unset password
fi
diag_summary
((DIAG_FAILURES == 0))
