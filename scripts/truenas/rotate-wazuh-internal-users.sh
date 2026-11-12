#!/usr/bin/env bash
# Replace the Wazuh indexer bootstrap users' sample passwords.
#
#   sudo bash scripts/truenas/rotate-wazuh-internal-users.sh --check
#   sudo NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/rotate-wazuh-internal-users.sh --apply
#
# admin takes INDEXER_PASSWORD and kibanaserver DASHBOARD_PASSWORD from the
# runtime file materialized from nabla/prod/wazuh; logstash gets a random,
# unrecorded password because nothing authenticates as it. --apply renders the
# bcrypt hashes into the runtime internal_users.yml mounted by the indexer,
# loads them into the security index with securityadmin.sh, then proves both
# logins. Passwords travel through files, the environment and stdin, never argv.
set -euo pipefail

MODE="${1:---check}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"

RUNTIME_DIR="${WAZUH_SECRETS_RUNTIME_DIR:-/mnt/cpool/secrets/runtime/wazuh}"
SECRETS_FILE="${RUNTIME_DIR}/.env.secrets"
RENDERED="${RUNTIME_DIR}/internal_users.yml"
TEMPLATE="${ROOT}/apps/wazuh/config/wazuh_indexer/internal_users.yml"
INDEXER="${WAZUH_INDEXER_CONTAINER:-wazuh-indexer}"
INDEXER_UID="${WAZUH_INDEXER_UID:-1000}"
TOOLS=/usr/share/wazuh-indexer/plugins/opensearch-security/tools
CERTS=/usr/share/wazuh-indexer/config/certs

case "${MODE}" in
--check | --apply) ;;
*) fail "usage: sudo bash scripts/truenas/rotate-wazuh-internal-users.sh [--check|--apply]" ;;
esac

require_root "run with sudo so the runtime secrets and the indexer can be read"
require_commands docker python3 stat
secrets_assert_file "${SECRETS_FILE}" INDEXER_PASSWORD DASHBOARD_PASSWORD ||
  fail "wazuh: materialize nabla/prod/wazuh first (materialize_runtime.py --app wazuh --install)"
[[ -f "${TEMPLATE}" ]] || fail "missing template: ${TEMPLATE}"
[[ "$(docker inspect -f '{{.State.Running}}' "${INDEXER}" 2>/dev/null)" == "true" ]] ||
  fail "${INDEXER} is not running"
ok "runtime secrets, template and ${INDEXER} are ready"

if [[ "${MODE}" == "--check" ]]; then
  info "--apply renders ${RENDERED}, loads it with securityadmin.sh and verifies the admin and kibanaserver logins"
  exit 0
fi
[[ "${NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes" ]] ||
  fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes after a reviewed --check"

admin_password="$(secrets_get_value "${SECRETS_FILE}" INDEXER_PASSWORD)"
kibanaserver_password="$(secrets_get_value "${SECRETS_FILE}" DASHBOARD_PASSWORD)"

tmp="$(mktemp "${RUNTIME_DIR}/.internal_users.yml.XXXXXX")"
trap 'rm -f "${tmp}"' EXIT
WAZUH_ADMIN_PASSWORD="${admin_password}" WAZUH_KIBANASERVER_PASSWORD="${kibanaserver_password}" \
  python3 - "${TEMPLATE}" "${tmp}" <<'PY'
import os
import secrets
import sys

import bcrypt
import yaml


def hashed(password: str) -> str:
    # $2b$ and $2y$ are the same algorithm; keep the prefix the Wazuh tooling emits.
    return "$2y$" + bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()[4:]


template, out = sys.argv[1:]
users = yaml.safe_load(open(template, encoding="utf-8"))
passwords = {
    "admin": os.environ["WAZUH_ADMIN_PASSWORD"],
    "kibanaserver": os.environ["WAZUH_KIBANASERVER_PASSWORD"],
    "logstash": secrets.token_urlsafe(32),
}
missing = sorted(set(passwords) - set(users))
if missing:
    raise SystemExit(f"template lacks users: {missing}")
users.update({name: {**users[name], "hash": hashed(password)} for name, password in passwords.items()})
with open(out, "w", encoding="utf-8") as handle:
    handle.write("---\n")
    yaml.safe_dump(users, handle, sort_keys=False)
PY
chown "${INDEXER_UID}:${INDEXER_UID}" "${tmp}"
chmod 600 "${tmp}"
mv -f "${tmp}" "${RENDERED}"
trap - EXIT
ok "rendered ${RENDERED}"

# Load through stdin so the result does not depend on which file the running container mounts.
docker exec -i "${INDEXER}" sh -c 'umask 077; cat >/tmp/internal_users.yml' <"${RENDERED}"
docker exec -e JAVA_HOME=/usr/share/wazuh-indexer/jdk "${INDEXER}" bash -c "
  bash ${TOOLS}/securityadmin.sh -f /tmp/internal_users.yml -t internalusers -icl -nhnv \
    -cacert ${CERTS}/root-ca.pem -cert ${CERTS}/admin.pem -key ${CERTS}/admin-key.pem -h 127.0.0.1 -p 9200
  rc=\$?; rm -f /tmp/internal_users.yml; exit \$rc" >/dev/null ||
  fail "securityadmin.sh failed; rerun it from ${INDEXER} to read its output"
ok "internal users loaded into the security index"

login_status() {
  printf 'user = "%s:%s"\n' "$1" "$2" |
    docker exec -i "${INDEXER}" curl -K - -s -o /dev/null -w '%{http_code}' \
      --cacert "${CERTS}/root-ca.pem" --resolve wazuh.indexer:9200:127.0.0.1 \
      https://wazuh.indexer:9200/_plugins/_security/authinfo
}
[[ "$(login_status admin "${admin_password}")" == "200" ]] || fail "admin login with INDEXER_PASSWORD failed"
[[ "$(login_status kibanaserver "${kibanaserver_password}")" == "200" ]] ||
  fail "kibanaserver login with DASHBOARD_PASSWORD failed"
ok "admin and kibanaserver authenticate with the rotated passwords; redeploy wazuh if the manager or dashboard still use the old ones"
