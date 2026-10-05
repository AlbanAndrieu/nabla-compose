# shellcheck shell=bash

# Shared bounded HTTP/HTTPS probe primitives.
# Callers own application-specific status interpretation and diagnostics.

probe_http_code() {
  local url="${1:-}" connect_timeout="${2:-3}" max_time="${3:-8}" code

  [[ -n "${url}" ]] || {
    printf 'HTTP probe URL is required\n' >&2
    return 2
  }
  [[ "${connect_timeout}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid HTTP connect timeout: %s\n' "${connect_timeout}" >&2
    return 2
  }
  [[ "${max_time}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid HTTP max time: %s\n' "${max_time}" >&2
    return 2
  }

  code="$(
    curl --silent --show-error \
      --connect-timeout "${connect_timeout}" \
      --max-time "${max_time}" \
      --output /dev/null \
      --write-out '%{http_code}' \
      "${url}" 2>/dev/null || true
  )"
  printf '%s\n' "${code:-000}"
}

probe_http_success() {
  local url="${1:-}" connect_timeout="${2:-3}" max_time="${3:-8}"

  [[ -n "${url}" ]] || {
    printf 'HTTP probe URL is required\n' >&2
    return 2
  }
  [[ "${connect_timeout}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid HTTP connect timeout: %s\n' "${connect_timeout}" >&2
    return 2
  }
  [[ "${max_time}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid HTTP max time: %s\n' "${max_time}" >&2
    return 2
  }

  curl --fail --silent --show-error \
    --connect-timeout "${connect_timeout}" \
    --max-time "${max_time}" \
    --output /dev/null \
    "${url}"
}

probe_http_wait() {
  local url="${1:-}" wait_seconds="${2:-240}" poll_seconds="${3:-4}"
  local connect_timeout="${4:-3}" max_time="${5:-8}" deadline

  [[ "${wait_seconds}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid HTTP wait timeout: %s\n' "${wait_seconds}" >&2
    return 2
  }
  [[ "${poll_seconds}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid HTTP poll interval: %s\n' "${poll_seconds}" >&2
    return 2
  }

  deadline=$((SECONDS + wait_seconds))
  while ((SECONDS < deadline)); do
    if probe_http_success "${url}" "${connect_timeout}" "${max_time}"; then
      return 0
    fi
    sleep "${poll_seconds}"
  done
  return 1
}
