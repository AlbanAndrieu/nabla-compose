#!/usr/bin/env bash
# Turn on TLS 1.3 for the shared TrueNAS PostgreSQL with a small local CA,
# pending the Vault PKI (docs/roadmap.md, TLS 1.3 item).
# --check (default) only reports; --apply creates the CA when missing, issues
# the server certificate when missing, expiring or not matching the SANs,
# publishes the CA certificate where clients mount it, enables ssl, then turns
# the remote pg_hba rule into hostssl, by reload (no restart). Private keys
# stay in root 0600 files or in PGDATA (postgres 0600) and are never printed.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/postgres.sh
source "${SCRIPT_DIR}/../lib/postgres.sh"

MODE="${1:---check}"
CA_DIR="${NABLA_LOCAL_CA_DIR:-/mnt/cpool/secrets/pki/local-ca}"
CLIENT_CA="${NABLA_POSTGRES_CA_FILE:-/mnt/cpool/secrets/runtime/postgres/tls/ca.crt}"
TLS_HOST="${NABLA_POSTGRES_TLS_HOST:-172.17.0.24}"
TLS_PORT="${NABLA_POSTGRES_TLS_PORT:-5432}"
SERVER_DNS="postgres.int.albandrieu.com"
SERVER_SAN="IP:${TLS_HOST},DNS:postgres,DNS:${SERVER_DNS}"
RENEW_BEFORE_SECONDS=$((30 * 86400))

case "${MODE}" in
--check | --apply) ;;
*) fail "usage: $0 [--check|--apply]" ;;
esac

require_root "run with sudo: the CA key and the PostgreSQL container are root-only"
require_commands docker openssl install cmp mktemp grep sed

POSTGRES_CONTAINER="$(postgres_shared_container)" || exit 1
POSTGRES_ADMIN="$(postgres_admin_role "${POSTGRES_CONTAINER}")" || exit 1
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

pgdata_cat() {
  docker exec "${POSTGRES_CONTAINER}" sh -c 'cat "${PGDATA}/$1"' sh "$1"
}

# Written as the postgres user: PostgreSQL refuses a key not owned by it at 0600.
pgdata_install() {
  docker exec -i -u postgres "${POSTGRES_CONTAINER}" \
    sh -c 'umask 077 && cat >"${PGDATA}/$1.tmp" && mv -f "${PGDATA}/$1.tmp" "${PGDATA}/$1"' sh "$1"
}

ca_ready() {
  [[ -s "${CA_DIR}/ca.key" && -s "${CA_DIR}/ca.crt" ]] &&
    openssl x509 -in "${CA_DIR}/ca.crt" -noout -checkend "${RENEW_BEFORE_SECONDS}" >/dev/null
}

client_ca_ready() {
  [[ -f "${CLIENT_CA}" && ! -L "${CLIENT_CA}" ]] && cmp -s "${CA_DIR}/ca.crt" "${CLIENT_CA}"
}

server_cert_ready() {
  pgdata_cat server.crt >"${WORK_DIR}/live.crt" 2>/dev/null &&
    docker exec "${POSTGRES_CONTAINER}" sh -c 'test -s "${PGDATA}/server.key"' &&
    openssl x509 -in "${WORK_DIR}/live.crt" -noout -checkend "${RENEW_BEFORE_SECONDS}" >/dev/null &&
    openssl verify -CAfile "${CA_DIR}/ca.crt" -purpose sslserver \
      -verify_ip "${TLS_HOST}" -verify_hostname "${SERVER_DNS}" "${WORK_DIR}/live.crt" >/dev/null 2>&1
}

ssl_enabled() {
  [[ "$(postgres_admin_query "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" "SHOW ssl")" == "on" &&
    "$(postgres_admin_query "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" "SHOW ssl_min_protocol_version")" == "TLSv1.3" ]]
}

# shellcheck disable=SC2329 # invoked through report
tls13_verified() {
  local out
  out="$(openssl s_client -starttls postgres -connect "${TLS_HOST}:${TLS_PORT}" -tls1_3 \
    -CAfile "${CLIENT_CA}" -verify_return_error -verify_ip "${TLS_HOST}" </dev/null 2>&1)" || return 1
  grep -q 'Verify return code: 0 (ok)' <<<"${out}"
}

# Only meaningful once TLS 1.3 answers: a server without ssl rejects TLS 1.2 too.
# shellcheck disable=SC2329 # invoked through report
tls12_rejected() {
  tls13_verified && ! openssl s_client -starttls postgres -connect "${TLS_HOST}:${TLS_PORT}" -tls1_2 </dev/null >/dev/null 2>&1
}

# Remote clients must use TLS; the loopback trust rules inside the container stay.
REMOTE_RULE='[[:space:]]+all[[:space:]]+all[[:space:]]+all[[:space:]]+scram-sha-256'

hostssl_enforced() {
  local hba
  hba="$(pgdata_cat pg_hba.conf)" || return 1
  grep -Eq "^hostssl${REMOTE_RULE}" <<<"${hba}" && ! grep -Eq "^host${REMOTE_RULE}" <<<"${hba}"
}

# shellcheck disable=SC2329 # invoked through report
plaintext_rejected() {
  local out
  out="$(docker exec "${POSTGRES_CONTAINER}" psql -w \
    "host=${TLS_HOST} port=${TLS_PORT} sslmode=disable dbname=postgres user=nabla_hba_probe" -c 'SELECT 1' 2>&1)" && return 1
  grep -q 'no pg_hba.conf entry' <<<"${out}"
}

enforce_hostssl() {
  pgdata_cat pg_hba.conf | sed -E "s/^host(${REMOTE_RULE})/hostssl\\1/" >"${WORK_DIR}/pg_hba.conf"
  pgdata_install pg_hba.conf <"${WORK_DIR}/pg_hba.conf"
  postgres_admin_query "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" "SELECT pg_reload_conf()" >/dev/null
  [[ "$(postgres_admin_query "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" \
    "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL")" == "0" ]] ||
    fail "pg_hba.conf has errors after the edit; PostgreSQL keeps the previous rules, fix it by hand"
  ok "remote pg_hba rule is now hostssl (reloaded)"
}

issue_ca() {
  install -d -o root -g root -m 700 "${CA_DIR}"
  (
    umask 077
    openssl req -x509 -new -noenc -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
      -keyout "${CA_DIR}/ca.key" -out "${CA_DIR}/ca.crt" -days 3650 -subj "/CN=Nabla Local CA" \
      -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
      -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
  )
  chmod 644 "${CA_DIR}/ca.crt"
  ok "local CA created: ${CA_DIR}/ca.crt (key root 0600, 10 years)"
}

issue_server_cert() {
  (
    umask 077
    openssl req -new -noenc -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
      -keyout "${WORK_DIR}/server.key" -out "${WORK_DIR}/server.csr" -subj "/CN=${SERVER_DNS}" 2>/dev/null
    printf '%s\n' \
      "basicConstraints=critical,CA:FALSE" \
      "keyUsage=critical,digitalSignature" \
      "extendedKeyUsage=serverAuth" \
      "subjectAltName=${SERVER_SAN}" >"${WORK_DIR}/server.ext"
    openssl x509 -req -in "${WORK_DIR}/server.csr" -CA "${CA_DIR}/ca.crt" -CAkey "${CA_DIR}/ca.key" \
      -days 825 -extfile "${WORK_DIR}/server.ext" -out "${WORK_DIR}/server.crt" 2>/dev/null
  )
  pgdata_install server.key <"${WORK_DIR}/server.key"
  pgdata_install server.crt <"${WORK_DIR}/server.crt"
  ok "server certificate issued in PGDATA: ${SERVER_SAN} (825 days)"
}

publish_client_ca() {
  [[ ! -L "${CLIENT_CA}" ]] || fail "${CLIENT_CA} is a symlink; inspect it by hand"
  if [[ -d "${CLIENT_CA}" ]]; then
    # Docker created this directory when a client bind-mounted the missing file.
    rmdir "${CLIENT_CA}" || fail "${CLIENT_CA} is a non-empty directory; inspect it by hand"
    warn "removed the empty ${CLIENT_CA} directory; redeploy (not restart) keycloak, plumber and sample"
  fi
  install -d -o root -g root -m 755 "$(dirname -- "${CLIENT_CA}")"
  install -o root -g root -m 644 "${CA_DIR}/ca.crt" "${CLIENT_CA}"
  ok "CA certificate published for clients: ${CLIENT_CA}"
}

enable_ssl() {
  postgres_admin_query "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" "ALTER SYSTEM SET ssl = on" >/dev/null
  postgres_admin_query "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" \
    "ALTER SYSTEM SET ssl_min_protocol_version = 'TLSv1.3'" >/dev/null
  postgres_admin_query "${POSTGRES_CONTAINER}" "${POSTGRES_ADMIN}" "SELECT pg_reload_conf()" >/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    ssl_enabled && return 0
    sleep 1
  done
  fail "ssl still off after reload; read the PostgreSQL log (a bad key or certificate keeps the old setting)"
}

if [[ "${MODE}" == "--apply" ]]; then
  ca_ready || issue_ca
  client_ca_ready || publish_client_ca
  server_cert_ready || issue_server_cert
  ssl_enabled || enable_ssl
  hostssl_enforced || enforce_hostssl
fi

failed=0
report() {
  if "$2"; then ok "$1"; else
    warn "NOT READY: $1"
    failed=1
  fi
}
report "local CA present and valid for 30+ days (${CA_DIR})" ca_ready
report "clients' CA file matches the local CA (${CLIENT_CA})" client_ca_ready
report "server certificate signed by the local CA for ${SERVER_SAN}, valid 30+ days" server_cert_ready
report "ssl=on with ssl_min_protocol_version=TLSv1.3" ssl_enabled
report "TLS 1.3 handshake verified against the CA on ${TLS_HOST}:${TLS_PORT}" tls13_verified
report "TLS 1.2 handshake rejected" tls12_rejected
report "remote pg_hba rule is hostssl" hostssl_enforced
report "plaintext TCP connection refused by pg_hba" plaintext_rejected
exit "${failed}"
