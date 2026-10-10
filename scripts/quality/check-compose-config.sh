#!/usr/bin/env bash
# Validate changed Compose documents without relying on inline YAML shell quoting.
set -euo pipefail

for file in "$@"; do
  if ! docker compose --project-directory "$(dirname -- "${file}")" \
    -f "${file}" config --quiet --no-interpolate --no-env-resolution; then
    printf 'ERROR: compose-config failed: %s\n' "${file}" >&2
    exit 1
  fi
done
