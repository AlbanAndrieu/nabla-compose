#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
ROOT="$(git rev-parse --show-toplevel)"
RUNTIME_DIR="${WAZUH_RUNTIME_DIR:-/mnt/cpool/wazuh}"
CERT_DIR="${WAZUH_CERTS_DIR:-${RUNTIME_DIR}/certs}"
SECRET_FILE="${WAZUH_SECRET_FILE:-${RUNTIME_DIR}/.env.secrets}"
LEGACY_CERT_DIR="${ROOT}/apps/wazuh/config/wazuh_indexer_ssl_certs"

fail() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

case "${MODE}" in
--check | --apply) ;;
*)
	fail "usage: sudo bash scripts/truenas/bootstrap-wazuh.sh [--check|--apply]"
	;;
esac

[[ "${EUID}" -eq 0 ]] ||
	fail "run with sudo so Wazuh secrets and private keys remain root-owned"

for command in docker git grep openssl stat; do
	command -v "${command}" >/dev/null 2>&1 ||
		fail "${command} is required"
done

cd "${ROOT}"

expected=(
	root-ca.pem
	root-ca-manager.pem
	wazuh.indexer.pem
	wazuh.indexer-key.pem
	admin.pem
	admin-key.pem
	wazuh.manager.pem
	wazuh.manager-key.pem
	wazuh.dashboard.pem
	wazuh.dashboard-key.pem
)

cleanup_legacy_false_directories() {
	local name
	[[ -d "${LEGACY_CERT_DIR}" ]] || return 0

	for name in "${expected[@]}"; do
		path="${LEGACY_CERT_DIR}/${name}"
		if [[ -d "${path}" ]]; then
			if find "${path}" -mindepth 1 -print -quit | grep -q .; then
				fail "legacy PEM path is a non-empty directory; refusing to remove: ${path}"
			fi
			rmdir "${path}"
			printf 'Removed stale empty directory created for missing PEM: %s\n' "${path}"
		fi
	done

	rmdir "${LEGACY_CERT_DIR}" 2>/dev/null || true
}

cert_status() {
	local present=0
	local missing=0
	local name

	for name in "${expected[@]}"; do
		path="${CERT_DIR}/${name}"
		if [[ -f "${path}" && -s "${path}" ]]; then
			((present += 1))
		else
			((missing += 1))
		fi
	done

	printf '%s|%s' "${present}" "${missing}"
}

verify_runtime() {
	local name
	local mode

	[[ -f "${SECRET_FILE}" && -s "${SECRET_FILE}" ]] ||
		fail "missing Wazuh runtime secret file: ${SECRET_FILE}"

	mode="$(stat -c '%a' "${SECRET_FILE}")"
	[[ "${mode}" == "600" ]] ||
		fail "${SECRET_FILE} must be mode 0600 (current: ${mode})"

	grep -q '^API_PASSWORD=.' "${SECRET_FILE}" ||
		fail "API_PASSWORD is missing from ${SECRET_FILE}"

	for name in "${expected[@]}"; do
		path="${CERT_DIR}/${name}"
		[[ -f "${path}" ]] ||
			fail "Wazuh certificate/key must be a regular file: ${path}"
		[[ -s "${path}" ]] ||
			fail "Wazuh certificate/key is empty: ${path}"
	done

	docker compose -f apps/wazuh/compose.yml config --quiet --no-interpolate --no-env-resolution

	printf 'OK: Wazuh runtime prerequisites are complete\n'
	printf '    secret=%s mode=0600\n' "${SECRET_FILE}"
	printf '    cert_dir=%s files=%s\n' "${CERT_DIR}" "${#expected[@]}"
}

if [[ "${MODE}" == "--check" ]]; then
	verify_runtime
	exit 0
fi

cleanup_legacy_false_directories

install -d -o root -g root -m 700 "${RUNTIME_DIR}" "${CERT_DIR}"

if [[ ! -f "${SECRET_FILE}" ]]; then
	umask 077
	password="Wz!$(openssl rand -hex 24)Aa1"
	printf 'API_PASSWORD=%s\n' "${password}" >"${SECRET_FILE}"
	unset password
	chown root:root "${SECRET_FILE}"
	chmod 600 "${SECRET_FILE}"
	printf 'Generated Wazuh API password in %s without printing it\n' "${SECRET_FILE}"
elif ! grep -q '^API_PASSWORD=.' "${SECRET_FILE}"; then
	password="Wz!$(openssl rand -hex 24)Aa1"
	printf 'API_PASSWORD=%s\n' "${password}" >>"${SECRET_FILE}"
	unset password
	chown root:root "${SECRET_FILE}"
	chmod 600 "${SECRET_FILE}"
	printf 'Added Wazuh API password to %s without printing it\n' "${SECRET_FILE}"
else
	chown root:root "${SECRET_FILE}"
	chmod 600 "${SECRET_FILE}"
	printf 'Preserved existing Wazuh API password\n'
fi

IFS='|' read -r present missing <<<"$(cert_status)"
if ((present > 0 && missing > 0)); then
	fail "partial Wazuh TLS set detected in ${CERT_DIR}; preserve/backup it and resolve it before regeneration"
fi

if ((missing == ${#expected[@]})); then
	printf 'Generating Wazuh 4.14 TLS material into %s...\n' "${CERT_DIR}"
	WAZUH_CERTS_DIR="${CERT_DIR}" docker compose -f apps/wazuh/generate-indexer-certs.yml run --rm generator
else
	printf 'Preserved existing complete Wazuh TLS material\n'
fi

find "${CERT_DIR}" -type f -exec chown root:root {} +
find "${CERT_DIR}" -type f -name '*-key.pem' -exec chmod 600 {} +
find "${CERT_DIR}" -type f ! -name '*-key.pem' -exec chmod 644 {} +

verify_runtime
