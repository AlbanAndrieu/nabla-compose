#!/usr/bin/env bash
set -euo pipefail

mode="${1:-plan}"
case "${mode}" in
  plan | apply) ;;
  *)
    echo "usage: $0 [plan|apply]" >&2
    exit 2
    ;;
esac

errors=0
warnings=0

ok() { printf '✅ %s\n' "$*"; }
warn() {
  printf '⚠️  %s\n' "$*" >&2
  warnings=$((warnings + 1))
}
fail() {
  printf '❌ %s\n' "$*" >&2
  errors=$((errors + 1))
}

require_command() {
  if command -v "$1" >/dev/null 2>&1; then
    ok "command available: $1"
  else
    fail "missing command: $1"
  fi
}

require_env() {
  local name="$1"
  if [[ -n "${!name:-}" ]]; then
    ok "environment variable present: ${name}"
  else
    fail "missing environment variable: ${name}"
  fi
}

expect_env() {
  local name="$1" expected="$2"
  if [[ "${!name:-}" == "${expected}" ]]; then
    ok "${name}=${expected}"
  else
    fail "${name} must be ${expected} for ${mode}"
  fi
}

check_endpoint() {
  local name="$1" url="$2"
  if [[ -z "${url}" ]]; then
    fail "${name} URL is empty"
    return
  fi

  local status
  status="$(curl --silent --show-error --location --connect-timeout 5 --max-time 10 \
    --output /dev/null --write-out '%{http_code}' "${url}" || true)"
  if [[ "${status}" =~ ^[1-4][0-9][0-9]$ ]]; then
    ok "${name} reachable (HTTP ${status})"
  else
    fail "${name} is not reachable over HTTP(S)"
  fi
}

printf '🔎 TrueNAS/Talos infrastructure preflight (%s)\n' "${mode}"
printf 'Secrets are checked for presence only; values are never printed.\n\n'

for command in curl jq tofu terragrunt; do
  require_command "${command}"
done

printf '\n🔐 Remote-state / Garage credentials\n'
require_env AWS_ACCESS_KEY_ID
require_env AWS_SECRET_ACCESS_KEY
require_env GARAGE_ADMIN_TOKEN

printf '\n🗄️  TrueNAS provider inputs\n'
for name in TRUENAS_URL TRUENAS_USER TRUENAS_API_KEY TRUENAS_POOL TRUENAS_VM_BRIDGE; do
  require_env "${name}"
done

if [[ -n "${TALOS_ISO_PATH:-}" ]]; then
  ok "optional environment variable present: TALOS_ISO_PATH"
else
  ok "TALOS_ISO_PATH not set (optional; no Talos CDROM will be attached)"
fi

expect_env TRUENAS_ENABLED true
expect_env TRUENAS_DESTROY_PROTECTION true
expect_env TRUENAS_INSECURE_SKIP_VERIFY false
if [[ "${mode}" == "plan" ]]; then
  expect_env TRUENAS_READ_ONLY true
else
  expect_env TRUENAS_READ_ONLY false
fi

if [[ -n "${TRUENAS_URL:-}" && ! "${TRUENAS_URL}" =~ ^https:// ]]; then
  fail "TRUENAS_URL must use https://"
fi

if [[ -n "${TALOS_ISO_PATH:-}" && ! "${TALOS_ISO_PATH}" =~ ^/mnt/ ]]; then
  fail "TALOS_ISO_PATH must be a TrueNAS-local absolute path under /mnt"
fi

printf '\n🌐 Endpoint reachability\n'
check_endpoint "Garage S3 backend" "https://s3.int.albandrieu.com"
check_endpoint "Garage admin API" "https://garage-admin.int.albandrieu.com"
if [[ -n "${TRUENAS_URL:-}" ]]; then
  check_endpoint "TrueNAS API" "${TRUENAS_URL}"
fi

printf '\n📦 Repository inputs\n'
for file in \
  config/talos/VERSION \
  config/talos/image-factory.yaml \
  terraform/garage/.terraform.lock.hcl \
  terraform/truenas/.terraform.lock.hcl \
  infrastructure/garage/terragrunt.hcl \
  infrastructure/truenas/terragrunt.hcl; do
  if [[ -r "${file}" ]]; then
    ok "readable: ${file}"
  else
    fail "missing repository input: ${file}"
  fi
done

if command -v bw >/dev/null 2>&1; then
  ok "Bitwarden CLI available (optional for preflight)"
else
  warn "Bitwarden CLI not found; infrastructure can still run with already-exported secrets"
fi

printf '\n'
if ((errors > 0)); then
  printf '❌ Preflight failed: %d error(s), %d warning(s).\n' "${errors}" "${warnings}" >&2
  exit 1
fi

printf '✅ Preflight passed with %d warning(s).\n' "${warnings}"
