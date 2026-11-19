#!/usr/bin/env bash
# Install only in an isolated Linux amd64 runner or dedicated VM.
set -euo pipefail
umask 077
if [[ $# -ne 1 || "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo "Usage (Linux amd64): $0 /path/to/amass" >&2
  exit 2
fi
destination="$1"
tmp="$(mktemp -d)"
trap 'rm -rf -- "${tmp}"' EXIT
archive="${tmp}/amass.tar.gz"
curl --fail --location --silent --show-error --max-time 120 \
  https://github.com/owasp-amass/amass/releases/download/v5.1.3/amass_linux_amd64.tar.gz \
  --output "${archive}"
printf '%s  %s\n' \
  4c12b725e4ce4981ece93a5e1566bd7391be1f349468856a79d31a43012ae201 "${archive}" \
  | sha256sum --check --status
# Extract just the executable, never arbitrary archive paths.
tar -tzf "${archive}" > "${tmp}/members"
mapfile -t binaries < <(grep -E '^([a-zA-Z0-9_.-]+/)?amass$' "${tmp}/members")
if [[ ${#binaries[@]} -ne 1 ]]; then
  echo "Unexpected Amass archive layout" >&2
  exit 1
fi
tar -xOzf "${archive}" -- "${binaries[0]}" > "${tmp}/amass"
chmod 700 "${tmp}/amass"
version="$("${tmp}/amass" -version 2>&1)"
if [[ ! "${version}" =~ (^|[^0-9])5\.1\.3([^0-9]|$) ]]; then
  echo "Unexpected Amass version" >&2
  exit 1
fi
install -m 0700 "${tmp}/amass" "${destination}"
echo "Amass v5.1.3 archive verified"
