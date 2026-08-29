#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
version_file="${TALOS_VERSION_FILE:-${repo_root}/config/talos/VERSION}"
schematic_file="${TALOS_SCHEMATIC_FILE:-${repo_root}/config/talos/image-factory.yaml}"
factory_url="${TALOS_IMAGE_FACTORY_URL:-https://factory.talos.dev}"
factory_url="${factory_url%/}"
factory_registry="${TALOS_IMAGE_FACTORY_REGISTRY:-${factory_url#https://}}"

for command in curl jq; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    printf 'error: required command not found: %s\n' "${command}" >&2
    exit 1
  fi
done

if [[ ! -r "${version_file}" ]]; then
  printf 'error: Talos version file is not readable: %s\n' "${version_file}" >&2
  exit 1
fi

if [[ ! -r "${schematic_file}" ]]; then
  printf 'error: Talos schematic file is not readable: %s\n' "${schematic_file}" >&2
  exit 1
fi

talos_version="$(tr -d '[:space:]' <"${version_file}")"
if [[ ! "${talos_version}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf 'error: invalid Talos version: %s\n' "${talos_version}" >&2
  exit 1
fi

schematic_response="$(
  curl \
    --fail \
    --silent \
    --show-error \
    --request POST \
    --header 'Content-Type: application/yaml' \
    --data-binary "@${schematic_file}" \
    "${factory_url}/schematics"
)"

schematic_id="$(jq -er '.id | select(test("^[0-9a-f]{64}$"))' <<<"${schematic_response}")"

printf 'TALOS_VERSION=%s\n' "${talos_version}"
printf 'TALOS_SCHEMATIC_ID=%s\n' "${schematic_id}"
printf 'TALOS_ISO_URL=%s/image/%s/%s/metal-amd64.iso\n' \
  "${factory_url}" "${schematic_id}" "${talos_version}"
printf 'TALOS_INSTALLER_IMAGE=%s/metal-installer/%s:%s\n' \
  "${factory_registry}" "${schematic_id}" "${talos_version}"
