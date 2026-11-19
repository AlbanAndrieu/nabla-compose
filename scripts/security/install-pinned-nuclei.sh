#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 1 ]] || exit 2
destination=$1
archive=$(mktemp)
trap 'rm -f "${archive}"' EXIT
curl --fail --location --silent --show-error --max-time 90 \
  "https://github.com/projectdiscovery/nuclei/releases/download/v3.11.1/nuclei_3.11.1_linux_amd64.zip" \
  --output "${archive}"
printf '%s  %s\n' \
  'ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6' "${archive}" \
  | sha256sum --check --status
unzip -p "${archive}" nuclei > "${destination}"
chmod 700 "${destination}"
"${destination}" -version
