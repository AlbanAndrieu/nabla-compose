#!/usr/bin/env bash
# Read-only shared PostgreSQL/Redis diagnostics for TrueNAS and post-reboot triage.
# shellcheck shell=bash
set -euo pipefail

for command in docker grep; do
  command -v "$command" >/dev/null 2>&1 || { echo "ERROR: missing $command" >&2; exit 2; }
done


# ANSI styling is restricted to interactive terminals; NO_COLOR disables it.
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != dumb ]]; then
  green=section 'PostgreSQL partagé · ix-postgres-postgres-1'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  fail 'Conteneur PostgreSQL absent ou arrêté'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  pass 'PostgreSQL accepte les connexions TCP · pg_isready (authentification non testée)'
else
  fail 'PostgreSQL ne répond pas à pg_isready'
  failures=$((failures + 1))
fi

section 'Redis partagé · redis'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  fail 'Conteneur Redis absent ou arrêté'
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
    warn 'Authentification Redis non testée · exporter REDIS_AUTH ou matérialiser le secret runtime'
    warnings=$((warnings + 1))
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      pass 'Redis authentifié · PING → PONG'
      printf '   📊 Bases Redis utilisées (compteurs uniquement) :\n'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      fail 'Redis authentifié · PING échoué'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf '\n%b❌ Bilan : %d échec(s), %d avertissement(s)%b\n' "$red$bold" "$failures" "$warnings" "$reset" >&2
  exit 1
fi
printf '\n%b%s Bilan : 0 échec, %d avertissement(s)%b\n' "$green$bold" "$(if (( warnings )); then printf '⚠️'; else printf '✅'; fi)" "$warnings" "$reset"
\033[32m'; yellow=printf '%s\n' '==> Shared PostgreSQL (ix-postgres-postgres-1)'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared PostgreSQL container not running'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  echo 'PASS: PostgreSQL accepting connections (pg_isready; not an authentication test)'
else
  echo 'FAIL: PostgreSQL not accepting connections'
  failures=$((failures + 1))
fi

printf '%s\n' '==> Shared Redis (redis)'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared Redis container not running'
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
    echo 'WARN: Redis authentication not checked (export REDIS_AUTH or materialize canonical runtime secret)'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      echo 'PASS: Redis authenticated PING=PONG'
      echo '==> Redis keyspace (counts only)'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      echo 'FAIL: Redis authenticated PING failed'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
echo 'OK: shared data diagnostics finished (WARN means incomplete authentication coverage)'
\033[33m'; red=printf '%s\n' '==> Shared PostgreSQL (ix-postgres-postgres-1)'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared PostgreSQL container not running'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  echo 'PASS: PostgreSQL accepting connections (pg_isready; not an authentication test)'
else
  echo 'FAIL: PostgreSQL not accepting connections'
  failures=$((failures + 1))
fi

printf '%s\n' '==> Shared Redis (redis)'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared Redis container not running'
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
    echo 'WARN: Redis authentication not checked (export REDIS_AUTH or materialize canonical runtime secret)'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      echo 'PASS: Redis authenticated PING=PONG'
      echo '==> Redis keyspace (counts only)'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      echo 'FAIL: Redis authenticated PING failed'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
echo 'OK: shared data diagnostics finished (WARN means incomplete authentication coverage)'
\033[31m'
  blue=printf '%s\n' '==> Shared PostgreSQL (ix-postgres-postgres-1)'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared PostgreSQL container not running'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  echo 'PASS: PostgreSQL accepting connections (pg_isready; not an authentication test)'
else
  echo 'FAIL: PostgreSQL not accepting connections'
  failures=$((failures + 1))
fi

printf '%s\n' '==> Shared Redis (redis)'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared Redis container not running'
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
    echo 'WARN: Redis authentication not checked (export REDIS_AUTH or materialize canonical runtime secret)'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      echo 'PASS: Redis authenticated PING=PONG'
      echo '==> Redis keyspace (counts only)'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      echo 'FAIL: Redis authenticated PING failed'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
echo 'OK: shared data diagnostics finished (WARN means incomplete authentication coverage)'
\033[36m'; bold=printf '%s\n' '==> Shared PostgreSQL (ix-postgres-postgres-1)'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared PostgreSQL container not running'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  echo 'PASS: PostgreSQL accepting connections (pg_isready; not an authentication test)'
else
  echo 'FAIL: PostgreSQL not accepting connections'
  failures=$((failures + 1))
fi

printf '%s\n' '==> Shared Redis (redis)'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared Redis container not running'
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
    echo 'WARN: Redis authentication not checked (export REDIS_AUTH or materialize canonical runtime secret)'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      echo 'PASS: Redis authenticated PING=PONG'
      echo '==> Redis keyspace (counts only)'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      echo 'FAIL: Redis authenticated PING failed'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
echo 'OK: shared data diagnostics finished (WARN means incomplete authentication coverage)'
\033[1m'; reset=printf '%s\n' '==> Shared PostgreSQL (ix-postgres-postgres-1)'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared PostgreSQL container not running'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  echo 'PASS: PostgreSQL accepting connections (pg_isready; not an authentication test)'
else
  echo 'FAIL: PostgreSQL not accepting connections'
  failures=$((failures + 1))
fi

printf '%s\n' '==> Shared Redis (redis)'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared Redis container not running'
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
    echo 'WARN: Redis authentication not checked (export REDIS_AUTH or materialize canonical runtime secret)'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      echo 'PASS: Redis authenticated PING=PONG'
      echo '==> Redis keyspace (counts only)'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      echo 'FAIL: Redis authenticated PING failed'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
echo 'OK: shared data diagnostics finished (WARN means incomplete authentication coverage)'
\033[0m'
else
  green=''; yellow=''; red=''; blue=''; bold=''; reset=''
fi
section() { printf '\n%b🔎 %s%b\n' "$blue$bold" "$1" "$reset"; }
pass() { printf '%b✅ PASS%b  %s\n' "$green" "$reset" "$1"; }
warn() { printf '%b⚠️  WARN%b  %s\n' "$yellow" "$reset" "$1"; }
fail() { printf '%b❌ FAIL%b  %s\n' "$red" "$reset" "$1" >&2; }

failures=0
warnings=0
printf '%s\n' '==> Shared PostgreSQL (ix-postgres-postgres-1)'
if ! docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared PostgreSQL container not running'
  failures=$((failures + 1))
elif docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  echo 'PASS: PostgreSQL accepting connections (pg_isready; not an authentication test)'
else
  echo 'FAIL: PostgreSQL not accepting connections'
  failures=$((failures + 1))
fi

printf '%s\n' '==> Shared Redis (redis)'
if ! docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  echo 'FAIL: shared Redis container not running'
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
    echo 'WARN: Redis authentication not checked (export REDIS_AUTH or materialize canonical runtime secret)'
  else
    # Transfer the password via stdin, never docker exec -e / redis-cli -a.
    # Suppress redis-cli output except an exact authenticated PONG.
    if [[ "$(printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
      IFS= read -r REDISCLI_AUTH
      export REDISCLI_AUTH
      redis-cli --raw PING 2>/dev/null
    ' 2>/dev/null)" == PONG ]]; then
      echo 'PASS: Redis authenticated PING=PONG'
      echo '==> Redis keyspace (counts only)'
      printf '%s\n' "$redis_password" | docker exec -i redis sh -c '
        IFS= read -r REDISCLI_AUTH
        export REDISCLI_AUTH
        redis-cli --raw INFO keyspace 2>/dev/null
      ' 2>/dev/null | grep -E '^db[0-9]+:keys=[0-9]+,' || true
    else
      echo 'FAIL: Redis authenticated PING failed'
      failures=$((failures + 1))
    fi
  fi
  unset redis_password
fi
if (( failures )); then
  printf 'FAIL: shared data diagnostics (%d failure(s))\n' "$failures" >&2
  exit 1
fi
echo 'OK: shared data diagnostics finished (WARN means incomplete authentication coverage)'
