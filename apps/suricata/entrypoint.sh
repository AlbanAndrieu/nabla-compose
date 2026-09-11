#!/bin/sh
set -eu

RULE_FILE="${SURICATA_RULE_FILE:-/var/lib/suricata/rules/suricata.rules}"

if [ ! -s "${RULE_FILE}" ]; then
  printf 'Suricata rules are missing; bootstrapping with suricata-update...\n'
  suricata-update
fi

if [ ! -s "${RULE_FILE}" ]; then
  printf 'ERROR: Suricata rule bootstrap did not produce %s\n' "${RULE_FILE}" >&2
  exit 1
fi

printf 'Suricata rules ready: %s\n' "${RULE_FILE}"
exec /docker-entrypoint.sh "$@"
