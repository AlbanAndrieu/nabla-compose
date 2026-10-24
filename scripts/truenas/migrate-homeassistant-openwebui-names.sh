#!/usr/bin/env bash
set -euo pipefail

# Explicit migration for standalone Compose only. No secrets or data are copied.
# TrueNAS-managed apps must be updated through TrueNAS application management.
mode="--check"
if [[ $# -gt 0 ]]; then mode="$1"; fi
if [[ "$mode" != "--check" && "$mode" != "--apply" ]]; then
  printf 'Usage: %s [--check|--apply]\n' "$0" >&2
  exit 2
fi

here="$(cd -- "$(dirname -- "$0")" && pwd)"
root="$(cd -- "$here/../.." && pwd)"
file="$root/apps/openwebui/compose.yml"
command -v docker >/dev/null || { printf 'NOT_RUN: Docker unavailable\n' >&2; exit 2; }

printf 'Canonical: homeassistant (already configured); openwebui (target)\n'
printf 'OpenWebUI: published 31028 -> container 8080; data mount unchanged\n'
printf 'Desired Cloudflare hostname: openwebui.albandrieu.com\n'
printf 'Cloudflare DNS/Tunnel/Access changes are MANUAL and outside this script\n'
printf 'Retain old hostname until new hostname and Access are verified\n'

if command -v midclt >/dev/null && command -v jq >/dev/null; then
  if midclt call app.query 2>/dev/null |
    jq -e 'any(.[]; (.id // .name) as $id | $id == "openwebui" or $id == "homeassistant" or $id == "home-assistant")' >/dev/null; then
    printf 'TrueNAS owns this app: use its management API/UI to redeploy.\n'
    if [[ "$mode" == "--apply" ]]; then exit 3; fi
  fi
fi

old_project=""
if docker inspect open-webui >/dev/null 2>&1; then
  old_project="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' open-webui)"
  printf 'Legacy container: open-webui; Compose project=%s\n' "$old_project"
  if [[ "$old_project" == ix-* ]]; then
    printf 'TrueNAS-managed legacy container. Do not recreate outside middleware.\n'
    if [[ "$mode" == "--apply" ]]; then exit 3; fi
  fi
fi
if docker inspect homeassistant >/dev/null 2>&1; then
  printf 'Home Assistant container already uses homeassistant; no recreation needed.\n'
fi
if docker inspect home-assistant >/dev/null 2>&1; then
  printf 'Legacy home-assistant container exists; migrate via its runtime owner.\n'
  if [[ "$mode" == "--apply" ]]; then exit 3; fi
fi

if [[ "$mode" == "--check" ]]; then
  printf 'CHECK ONLY. No container, DNS record, or volume changed.\n'
  printf 'Before apply: validate the manifest, runtime secrets and independent backup.\n'
  exit 0
fi

[[ "$old_project" == "openwebui" ]] || {
  printf 'FAIL: --apply supports only an existing standalone openwebui Compose project\n' >&2
  exit 3
}
if docker inspect openwebui >/dev/null 2>&1; then
  printf 'FAIL: canonical container already exists. Investigate first.\n' >&2
  exit 3
fi
if [[ ! -v NABLA_RUNTIME_CHANGE_APPROVED ]] ||
  [[ "$NABLA_RUNTIME_CHANGE_APPROVED" != "yes" ]]; then
  printf 'FAIL: set NABLA_RUNTIME_CHANGE_APPROVED=yes after review\n' >&2
  exit 3
fi
for secret in LITELLM_MASTER_KEY WEBUI_SECRET_KEY WEBUI_ADMIN_PASSWORD; do
  if [[ ! -v "$secret" ]] || [[ -z "$(printenv "$secret")" ]]; then
    printf 'FAIL: required runtime secret %s absent (value not logged)\n' "$secret" >&2
    exit 3
  fi
done
docker compose --project-directory "$root/apps/openwebui" -f "$file" \
  -p openwebui config --quiet --no-interpolate --no-env-resolution

backup="open-webui-rollback-$(date -u +%Y%m%dT%H%M%SZ)"
docker stop open-webui
if ! docker rename open-webui "$backup"; then
  docker start open-webui
  printf 'FAIL: could not preserve the original container\n' >&2
  exit 4
fi
if ! docker compose --project-directory "$root/apps/openwebui" -f "$file" \
  -p openwebui up -d --no-deps openwebui ||
  ! docker inspect -f '{{ .State.Running }}' openwebui | grep -qx true; then
  docker rm -f openwebui >/dev/null 2>&1 || true
  docker rename "$backup" open-webui
  docker start open-webui
  printf 'FAIL: new container failed; legacy container restarted\n' >&2
  exit 4
fi
printf 'New container is RUNNING; HTTP/auth/data readiness NOT VERIFIED.\n'
printf 'Rollback container preserved: %s (STOPPED; do not delete before acceptance)\n' "$backup"
printf 'Verify login, LiteLLM, health and Cloudflare Access before cleanup.\n'
