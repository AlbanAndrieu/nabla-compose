#!/usr/bin/env bash
# Read-only shared PostgreSQL/Redis diagnostics for TrueNAS and post-reboot triage.
# shellcheck shell=bash
set -euo pipefail

for command in docker grep; do
  command -v "$command" >/dev/null 2>&1 || { echo "ERROR: missing $command" >&2; exit 2; }
done

# Terminal-only ANSI styling; honor NO_COLOR and noninteractive logs.
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != dumb ]]; then
  C_GREEN=section 'PostgreSQL partagé · ix-postgres-postgres-1'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'PostgreSQL absent ou arrêté'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  ok 'PostgreSQL accepte les connexions (authentification non testée)'
else
  failure 'PostgreSQL ne répond pas'
  failures=$((failures + 1))
fi

section 'Redis partagé · redis'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'Redis absent ou arrêté'
  failures=$((failures + 1))
else
  # Prefer operator-provided REDIS_AUTH. Never derive credentials from docker inspect.
  # The optional canonical runtime file is expected to be root:root 0600.
  redis_password="${REDIS_AUTH:-}"
  secret_file=/mnt/cpool/secrets/runtime/redis/.env.secrets
  if [[ -z "$redis_password" && -r "$secret_file" ]]; then
    # Read only the simple, single-line REDIS_AUTH assignment; never source the file.
    redis_password="$(python3 - "$secret_file" <<'PY'
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
  if [[ -z "$redis_password" ]]; then
    warning 'Redis non authentifié : fournir REDIS_AUTH ou le secret runtime'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      ok 'Redis authentifié : PING → PONG'
      section 'Redis · compteurs des bases utilisées'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      failure 'Redis : PING authentifié en échec'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
ok 'Diagnostic des données terminé (vérifier les WARN éventuels)'
\033[32m'
  C_YELLOW=section 'PostgreSQL partagé · ix-postgres-postgres-1'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'PostgreSQL absent ou arrêté'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  ok 'PostgreSQL accepte les connexions (authentification non testée)'
else
  failure 'PostgreSQL ne répond pas'
  failures=$((failures + 1))
fi

section 'Redis partagé · redis'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'Redis absent ou arrêté'
  failures=$((failures + 1))
else
  # Prefer operator-provided REDIS_AUTH. Never derive credentials from docker inspect.
  # The optional canonical runtime file is expected to be root:root 0600.
  redis_password="${REDIS_AUTH:-}"
  secret_file=/mnt/cpool/secrets/runtime/redis/.env.secrets
  if [[ -z "$redis_password" && -r "$secret_file" ]]; then
    # Read only the simple, single-line REDIS_AUTH assignment; never source the file.
    redis_password="$(python3 - "$secret_file" <<'PY'
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
  if [[ -z "$redis_password" ]]; then
    warning 'Redis non authentifié : fournir REDIS_AUTH ou le secret runtime'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      ok 'Redis authentifié : PING → PONG'
      section 'Redis · compteurs des bases utilisées'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      failure 'Redis : PING authentifié en échec'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
ok 'Diagnostic des données terminé (vérifier les WARN éventuels)'
\033[33m'
  C_RED=section 'PostgreSQL partagé · ix-postgres-postgres-1'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'PostgreSQL absent ou arrêté'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  ok 'PostgreSQL accepte les connexions (authentification non testée)'
else
  failure 'PostgreSQL ne répond pas'
  failures=$((failures + 1))
fi

section 'Redis partagé · redis'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'Redis absent ou arrêté'
  failures=$((failures + 1))
else
  # Prefer operator-provided REDIS_AUTH. Never derive credentials from docker inspect.
  # The optional canonical runtime file is expected to be root:root 0600.
  redis_password="${REDIS_AUTH:-}"
  secret_file=/mnt/cpool/secrets/runtime/redis/.env.secrets
  if [[ -z "$redis_password" && -r "$secret_file" ]]; then
    # Read only the simple, single-line REDIS_AUTH assignment; never source the file.
    redis_password="$(python3 - "$secret_file" <<'PY'
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
  if [[ -z "$redis_password" ]]; then
    warning 'Redis non authentifié : fournir REDIS_AUTH ou le secret runtime'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      ok 'Redis authentifié : PING → PONG'
      section 'Redis · compteurs des bases utilisées'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      failure 'Redis : PING authentifié en échec'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
ok 'Diagnostic des données terminé (vérifier les WARN éventuels)'
\033[31m'
  C_BLUE=section 'PostgreSQL partagé · ix-postgres-postgres-1'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'PostgreSQL absent ou arrêté'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  ok 'PostgreSQL accepte les connexions (authentification non testée)'
else
  failure 'PostgreSQL ne répond pas'
  failures=$((failures + 1))
fi

section 'Redis partagé · redis'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'Redis absent ou arrêté'
  failures=$((failures + 1))
else
  # Prefer operator-provided REDIS_AUTH. Never derive credentials from docker inspect.
  # The optional canonical runtime file is expected to be root:root 0600.
  redis_password="${REDIS_AUTH:-}"
  secret_file=/mnt/cpool/secrets/runtime/redis/.env.secrets
  if [[ -z "$redis_password" && -r "$secret_file" ]]; then
    # Read only the simple, single-line REDIS_AUTH assignment; never source the file.
    redis_password="$(python3 - "$secret_file" <<'PY'
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
  if [[ -z "$redis_password" ]]; then
    warning 'Redis non authentifié : fournir REDIS_AUTH ou le secret runtime'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      ok 'Redis authentifié : PING → PONG'
      section 'Redis · compteurs des bases utilisées'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      failure 'Redis : PING authentifié en échec'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
ok 'Diagnostic des données terminé (vérifier les WARN éventuels)'
\033[36m'
  C_RESET=section 'PostgreSQL partagé · ix-postgres-postgres-1'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'PostgreSQL absent ou arrêté'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  ok 'PostgreSQL accepte les connexions (authentification non testée)'
else
  failure 'PostgreSQL ne répond pas'
  failures=$((failures + 1))
fi

section 'Redis partagé · redis'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'Redis absent ou arrêté'
  failures=$((failures + 1))
else
  # Prefer operator-provided REDIS_AUTH. Never derive credentials from docker inspect.
  # The optional canonical runtime file is expected to be root:root 0600.
  redis_password="${REDIS_AUTH:-}"
  secret_file=/mnt/cpool/secrets/runtime/redis/.env.secrets
  if [[ -z "$redis_password" && -r "$secret_file" ]]; then
    # Read only the simple, single-line REDIS_AUTH assignment; never source the file.
    redis_password="$(python3 - "$secret_file" <<'PY'
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
  if [[ -z "$redis_password" ]]; then
    warning 'Redis non authentifié : fournir REDIS_AUTH ou le secret runtime'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      ok 'Redis authentifié : PING → PONG'
      section 'Redis · compteurs des bases utilisées'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      failure 'Redis : PING authentifié en échec'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
ok 'Diagnostic des données terminé (vérifier les WARN éventuels)'
\033[0m'
else
  C_GREEN='' C_YELLOW='' C_RED='' C_BLUE='' C_RESET=''
fi
section() { printf '\n%b🔎 %s%b\n' "$C_BLUE" "$1" "$C_RESET"; }
ok() { printf '%b✅ PASS%b %s\n' "$C_GREEN" "$C_RESET" "$1"; }
warning() { printf '%b⚠️ WARN%b %s\n' "$C_YELLOW" "$C_RESET" "$1"; }
failure() { printf '%b❌ FAIL%b %s\n' "$C_RED" "$C_RESET" "$1" >&2; }

failures=0
section 'PostgreSQL partagé · ix-postgres-postgres-1'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'PostgreSQL absent ou arrêté'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  ok 'PostgreSQL accepte les connexions (authentification non testée)'
else
  failure 'PostgreSQL ne répond pas'
  failures=$((failures + 1))
fi

section 'Redis partagé · redis'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  failure 'Redis absent ou arrêté'
  failures=$((failures + 1))
else
  # Prefer operator-provided REDIS_AUTH. Never derive credentials from docker inspect.
  # The optional canonical runtime file is expected to be root:root 0600.
  redis_password="${REDIS_AUTH:-}"
  secret_file=/mnt/cpool/secrets/runtime/redis/.env.secrets
  if [[ -z "$redis_password" && -r "$secret_file" ]]; then
    # Read only the simple, single-line REDIS_AUTH assignment; never source the file.
    redis_password="$(python3 - "$secret_file" <<'PY'
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
  if [[ -z "$redis_password" ]]; then
    warning 'Redis non authentifié : fournir REDIS_AUTH ou le secret runtime'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      ok 'Redis authentifié : PING → PONG'
      section 'Redis · compteurs des bases utilisées'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      failure 'Redis : PING authentifié en échec'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
ok 'Diagnostic des données terminé (vérifier les WARN éventuels)'
