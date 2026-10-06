#!/usr/bin/env bash
set -euo pipefail

# Fail-closed supply-chain admission for both Scanopy images.
# Read-only: no Docker pull/build/create/update/exec.
compose_path="${1:?usage: check-scanopy-image-lock.sh COMPOSE_PATH}"
allow_mutable="${SCANOPY_ALLOW_MUTABLE_IMAGE:-0}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${allow_mutable}" == "0" || "${allow_mutable}" == "1" ]] ||
  fail "SCANOPY_ALLOW_MUTABLE_IMAGE must be 0 or 1"
[[ -f "${compose_path}" ]] || fail "Scanopy Compose file is missing: ${compose_path}"
command -v docker >/dev/null 2>&1 || fail "docker is required"

# Command substitution checks the actual docker-compose exit status; process
# substitution with mapfile would hide upstream failures and fail open.
image_list="$(docker compose -f "${compose_path}" config --no-env-resolution --images)" ||
  fail "unable to enumerate Scanopy images from validated Compose config"
[[ -n "${image_list//[[:space:]]/}" ]] ||
  fail "Scanopy image inventory is empty"

mapfile -t images <<<"${image_list}"
((${#images[@]} == 2)) ||
  fail "expected exactly two Scanopy images (server and daemon), got ${#images[@]}"

server_image=""
daemon_image=""
for image in "${images[@]}"; do
  case "${image}" in
    ghcr.io/scanopy/scanopy/server:*)
      [[ -z "${server_image}" ]] || fail "duplicate Scanopy server image"
      server_image="${image}"
      ;;
    ghcr.io/scanopy/scanopy/daemon:*)
      [[ -z "${daemon_image}" ]] || fail "duplicate Scanopy daemon image"
      daemon_image="${image}"
      ;;
    *)
      fail "unexpected Scanopy image repository: ${image}"
      ;;
  esac
done
[[ -n "${server_image}" && -n "${daemon_image}" ]] ||
  fail "both Scanopy server and daemon images are required"

mutable_images=()
server_version=""
daemon_version=""
if [[ "${server_image}" =~ ^ghcr[.]io/scanopy/scanopy/server:([A-Za-z0-9][A-Za-z0-9._-]*)@sha256:([0-9a-f]{64})$ ]]; then
  server_version="${BASH_REMATCH[1]}"
else
  mutable_images+=("server")
fi
if [[ "${daemon_image}" =~ ^ghcr[.]io/scanopy/scanopy/daemon:([A-Za-z0-9][A-Za-z0-9._-]*)@sha256:([0-9a-f]{64})$ ]]; then
  daemon_version="${BASH_REMATCH[1]}"
else
  mutable_images+=("daemon")
fi

if ((${#mutable_images[@]} > 0)); then
  if [[ "${allow_mutable}" != "1" ]]; then
    fail "mutable or malformed Scanopy image references for: ${mutable_images[*]}; require release-tagged @sha256:64hex digests"
  fi
  printf 'WARNING: PoC-only mutable image override for: %s\n' "${mutable_images[*]}" >&2
fi

if [[ "${server_version}" == "latest" || "${daemon_version}" == "latest" ]]; then
  if [[ "${allow_mutable}" != "1" ]]; then
    fail "Scanopy image digest must also carry a non-latest release tag"
  fi
  printf 'WARNING: PoC-only override for Scanopy latest tag\n' >&2
fi

if [[ -n "${server_version}" && -n "${daemon_version}" &&
  "${server_version}" != "${daemon_version}" ]]; then
  if [[ "${allow_mutable}" != "1" ]]; then
    fail "Scanopy server/daemon image release tags differ"
  fi
  printf 'WARNING: PoC-only override for mismatched Scanopy releases\n' >&2
fi

if [[ "${allow_mutable}" == "1" ]]; then
  printf 'WARNING: Scanopy PoC override enabled; this is not production acceptance\n' >&2
else
  printf 'OK: Scanopy image references have complete SHA-256 digests and matching release tags\n'
fi
