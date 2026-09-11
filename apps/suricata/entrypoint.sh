#!/bin/sh
set -eu

RULE_FILE="${SURICATA_RULE_FILE:-/var/lib/suricata/rules/suricata.rules}"
RULE_DIR="${RULE_FILE%/*}"
UPDATE_TIMEOUT_SECONDS="${SURICATA_UPDATE_TIMEOUT_SECONDS:-120}"

case "${UPDATE_TIMEOUT_SECONDS}" in
  ''|*[!0-9]*)
    printf 'ERROR: SURICATA_UPDATE_TIMEOUT_SECONDS must be a positive integer\n' >&2
    exit 1
    ;;
esac

if [ "${UPDATE_TIMEOUT_SECONDS}" -lt 1 ]; then
  printf 'ERROR: SURICATA_UPDATE_TIMEOUT_SECONDS must be greater than zero\n' >&2
  exit 1
fi

mkdir -p "${RULE_DIR}"
if [ ! -w "${RULE_DIR}" ]; then
  printf 'ERROR: Suricata rule directory is not writable: %s\n' "${RULE_DIR}" >&2
  exit 1
fi

if [ ! -s "${RULE_FILE}" ]; then
  printf 'Suricata rules are missing; bootstrapping with suricata-update (timeout=%ss)...\n' \
    "${UPDATE_TIMEOUT_SECONDS}"

  python3 - "${UPDATE_TIMEOUT_SECONDS}" <<'PY'
import subprocess
import sys

timeout = int(sys.argv[1])
try:
    result = subprocess.run(
        ["suricata-update", "--no-test", "--no-reload"],
        check=False,
        timeout=timeout,
    )
except subprocess.TimeoutExpired:
    print(
        f"ERROR: suricata-update exceeded the {timeout}s bootstrap timeout",
        file=sys.stderr,
    )
    raise SystemExit(124)
except OSError as exc:
    print(f"ERROR: failed to execute suricata-update: {exc}", file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(result.returncode)
PY
fi

if [ ! -s "${RULE_FILE}" ]; then
  printf 'ERROR: Suricata rule bootstrap did not produce %s\n' "${RULE_FILE}" >&2
  exit 1
fi

printf 'Suricata rules ready: %s\n' "${RULE_FILE}"
exec /docker-entrypoint.sh "$@"
