#!/usr/bin/env bash
# Read-only capture of the Cloudflare objects imported by terraform/cloudflare.
# Only GET requests reach the Cloudflare API, and `tofu plan` never writes state.
set -euo pipefail

usage() {
  cat <<'EOF'
usage: scripts/cloudflare/capture-homelab-tofu.sh [public-hostname]

Discover the zone, DNS record and the two Access applications (host-wide and
/api) of <public-hostname> (default: sample.albandrieu.com), write their identifiers to
terraform/cloudflare/import-ids.auto.tfvars, then let OpenTofu
generate their live configuration into terraform/cloudflare/generated.tofu.

Requires CLOUDFLARE_API_TOKEN in the environment; read permissions are enough.
See terraform/cloudflare/README.md.
EOF
}

case "${1:-}" in
  -h | --help)
    usage
    exit 0
    ;;
esac

hostname="${1:-sample.albandrieu.com}"
zone_name="albandrieu.com"
account_id="bdfe00eeee5845782ab91adfbff71ee1"
module_dir="$(git rev-parse --show-toplevel)/terraform/cloudflare"
api="https://api.cloudflare.com/client/v4"

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo "CLOUDFLARE_API_TOKEN is not set." >&2
  exit 2
fi
if [[ -e "${module_dir}/generated.tofu" ]]; then
  echo "${module_dir}/generated.tofu already exists: review and remove it first." >&2
  exit 2
fi

# The token goes through stdin so it never appears in the process list.
cf_get() {
  printf 'Authorization: Bearer %s\n' "${CLOUDFLARE_API_TOKEN}" |
    curl -fsS --max-time 20 -H @- "${api}$1"
}

only_id() {
  jq -er --arg label "$1" \
    'if length == 1 then .[0].id else error("expected exactly one \($label), got \(length)") end'
}

zone_id="$(cf_get "/zones?name=${zone_name}" | jq '.result' | only_id zone)"
record_id="$(cf_get "/zones/${zone_id}/dns_records?type=CNAME&name=${hostname}" |
  jq '.result' | only_id "CNAME ${hostname}")"
apps="$(cf_get "/accounts/${account_id}/access/apps?domain=${hostname}")"
# A path app left on the old hostname would silently fall back to the host-wide app's policies.
jq -e --arg h "${hostname}" \
  '[.result[] | select(any(.domain, .destinations[]?.uri; (. // "") | split("/")[0] == $h))]
   | length == 2' <<<"${apps}" >/dev/null || {
  echo "expected exactly the ${hostname} and ${hostname}/api Access applications" >&2
  exit 1
}
app_id="$(jq --arg d "${hostname}" '[.result[] | select(.domain == $d)]' <<<"${apps}" |
  only_id "Access application ${hostname}")"
api_app_id="$(jq --arg d "${hostname}/api" '[.result[] | select(.domain == $d)]' <<<"${apps}" |
  only_id "Access application ${hostname}/api")"

# HCL rather than JSON so Access UUIDs carry the repository's gitleaks:allow marker.
cat >"${module_dir}/import-ids.auto.tfvars" <<EOF
zone_id                                  = "${zone_id}"
fastapi_sample_dns_record_id             = "${record_id}"
fastapi_sample_access_application_id     = "${app_id}" # gitleaks:allow
fastapi_sample_api_access_application_id = "${api_app_id}" # gitleaks:allow
EOF
echo "Identifiers (not secrets) written to ${module_dir}/import-ids.auto.tfvars"

tofu -chdir="${module_dir}" init -input=false >/dev/null
tofu -chdir="${module_dir}" plan -input=false -lock=false -generate-config-out=generated.tofu
echo "Review ${module_dir}/generated.tofu, then follow the README 'Capture' step."
