#!/usr/bin/env bash
# FreshRSS existing TrueNAS App: read-only preflight or explicit, isolated account bootstrap.
set -euo pipefail
set +x

MODE="${1:---check}"
CONTAINER="${FRESHRSS_CONTAINER:-freshrss}"
CLI_USER="${FRESHRSS_CLI_USER:-www-data}"
ROOT="${FRESHRSS_REPO_ROOT:-/mnt/cpool/compose/nabla-compose}"
SECRETS="${FRESHRSS_SECRET_ROOT:-/mnt/cpool/secrets/runtime/freshrss}"
OPML="${FRESHRSS_OPML:-${ROOT}/config/freshrss/public-security.opml}"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf 'INFO: %s\n' "$*"; }
case "${MODE}" in
  --check|--apply|--import-opml|--enable-api) ;;
  *) die "usage: bash scripts/truenas/freshrss-ops.sh [--check|--apply|--import-opml|--enable-api]" ;;
esac
command -v docker >/dev/null || die "docker required"
[[ "${CONTAINER}" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,80}$ ]] || die "invalid container name"
[[ "${CLI_USER}" == www-data || "${CLI_USER}" == apache ]] || die "CLI user must be www-data or apache"
[[ -r "${OPML}" ]] || die "missing OPML file: ${OPML}"
docker inspect "${CONTAINER}" >/dev/null 2>&1 ||
  die "FreshRSS container not found; inspect midclt app.query and choose FRESHRSS_CONTAINER explicitly"
image="$(docker inspect -f '{{.Config.Image}}' "${CONTAINER}")"
[[ "${image}" == *freshrss* ]] || die "container image is not FreshRSS"
running="$(docker inspect -f '{{.State.Running}}' "${CONTAINER}")"
[[ "${running}" == true ]] || die "FreshRSS container is not running (no automatic start/redeploy)"
docker exec --user "${CLI_USER}" "${CONTAINER}" cli/list-users.php >/dev/null ||
  die "official FreshRSS CLI unavailable; verify image user/path"
info "existing FreshRSS healthy for CLI; container=${CONTAINER}, mode=${MODE}"
if [[ "${MODE}" == --check ]]; then
  for user in securitypublic securityagent; do
    if docker exec --user "${CLI_USER}" "${CONTAINER}" cli/list-users.php |
      grep -Fxq "${user}"; then
      info "account present: ${user} (credentials and subscriptions not validated)"
    else
      info "account missing: ${user}"
    fi
  done
  info "read-only check complete; no account, subscription or runtime change"
  exit 0
fi

[[ "${EUID}" == 0 ]] || die "apply must be run as root on TrueNAS"
[[ "${FRESHRSS_APPROVE_APPLY:-}" == YES ]] ||
  die "explicit approval required: FRESHRSS_APPROVE_APPLY=YES"
# Global API enablement is an independent and explicitly approved operation.
if [[ "${MODE}" == --enable-api ]]; then
  [[ "${FRESHRSS_ENABLE_GLOBAL_API:-}" == YES ]] ||
    die "FRESHRSS_ENABLE_GLOBAL_API=YES required; review instance-wide API exposure"
  docker exec --user "${CLI_USER}" "${CONTAINER}" cli/reconfigure.php --api-enabled >/dev/null
  info "global API enable request applied; verify protections and GReader auth independently"
  exit 0
fi
# A native CLI must receive passwords as argv: short-lived exposure to privileged
# process observers remains possible. For stronger isolation create passwords in UI.
check_secret() {
  local file="$1" permission owner
  [[ -f "${file}" && ! -L "${file}" && -s "${file}" ]] || die "secret file missing: ${file}"
  permission="$(stat -c %a "${file}")"
  owner="$(stat -c %u:%g "${file}")"
  [[ "${permission}" == 600 && "${owner}" == 0:0 ]] ||
    die "secret must be root:root 0600: ${file}"
}

import_one() {
  local user="$1" target="/tmp/nabla-security-${user}-$$.opml"
  # Import only explicit opt-in or once on a newly created account.
  docker cp "${OPML}" "${CONTAINER}:${target}" >/dev/null
  if ! docker exec --user "${CLI_USER}" "${CONTAINER}" cli/import-for-user.php \
    --user "${user}" --filename "${target}" >/dev/null; then
    docker exec "${CONTAINER}" rm -f "${target}" >/dev/null 2>&1 || true
    die "FreshRSS import failed for ${user}"
  fi
  docker exec "${CONTAINER}" rm -f "${target}" >/dev/null 2>&1 ||
    die "temporary OPML cleanup failed for ${user}"
  info "import submitted for ${user}; verify subscriptions via GReader before publication"
}
if [[ "${MODE}" == --import-opml ]]; then
  [[ "${FRESHRSS_IMPORT_APPROVED:-}" == YES ]] || die "FRESHRSS_IMPORT_APPROVED=YES required"
  for user in securitypublic securityagent; do
    docker exec --user "${CLI_USER}" "${CONTAINER}" cli/list-users.php |
      grep -Fxq "${user}" || die "account does not exist: ${user}"
    import_one "${user}"
  done
  exit 0
fi

# No implicit password reset or API key rotation on existing accounts.
for user in securitypublic securityagent; do
  if docker exec --user "${CLI_USER}" "${CONTAINER}" cli/list-users.php |
    grep -Fxq "${user}"; then
    info "existing account ${user}: skip create and skip credential changes"
    continue
  fi
  login_file="${SECRETS}/${user}.login-password"
  api_file="${SECRETS}/${user}.api-password"
  check_secret "${login_file}"
  check_secret "${api_file}"
  # FreshRSS official CLI supports --no-default-feeds and --api-password.
  # Secrets are never echoed, but native CLI argv is visible to privileged
  # process observers for the short duration of docker exec.
  login_pass="$(<"${login_file}")"
  api_pass="$(<"${api_file}")"
  [[ "${#login_pass}" -ge 24 && "${#api_pass}" -ge 24 ]] ||
    die "password lengths must be >=24 characters"
  docker exec --user "${CLI_USER}" "${CONTAINER}" cli/create-user.php \
    --user "${user}" --password "${login_pass}" --api-password "${api_pass}" \
    --language fr --no-default-feeds >/dev/null
  unset login_pass api_pass
  info "created isolated FreshRSS account ${user}"
  import_one "${user}"
done
info "bootstrap complete. API enablement, client login, read-only MCP, Cloudflare Access and site publication remain separate gates."
