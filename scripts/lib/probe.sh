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

probe_tcp_success() {
  local host="${1:-}" port="${2:-}" timeout_seconds="${3:-3}"

  [[ "${host}" =~ ^[A-Za-z0-9._:-]+$ ]] || {
    printf 'invalid TCP probe host: %s\n' "${host}" >&2
    return 2
  }
  [[ "${port}" =~ ^[0-9]+$ ]] && ((port >= 1 && port <= 65535)) || {
    printf 'invalid TCP probe port: %s\n' "${port}" >&2
    return 2
  }
  [[ "${timeout_seconds}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid TCP probe timeout: %s\n' "${timeout_seconds}" >&2
    return 2
  }

  timeout "${timeout_seconds}" bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "${host}" "${port}" \
    >/dev/null 2>&1
}

probe_tcp_wait() {
  local host="${1:-}" port="${2:-}" wait_seconds="${3:-60}"
  local poll_seconds="${4:-2}" connect_timeout="${5:-3}" deadline

  [[ "${wait_seconds}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid TCP wait timeout: %s\n' "${wait_seconds}" >&2
    return 2
  }
  [[ "${poll_seconds}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid TCP poll interval: %s\n' "${poll_seconds}" >&2
    return 2
  }

  deadline=$((SECONDS + wait_seconds))
  while ((SECONDS < deadline)); do
    if probe_tcp_success "${host}" "${port}" "${connect_timeout}"; then
      return 0
    fi
    sleep "${poll_seconds}"
  done
  return 1
}

probe_dns_addresses() {
  local hostname="${1:-}" timeout_seconds="${2:-3}"

  [[ "${hostname}" =~ ^[A-Za-z0-9._-]+$ ]] || {
    printf 'invalid DNS probe hostname: %s\n' "${hostname}" >&2
    return 2
  }
  [[ "${timeout_seconds}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid DNS probe timeout: %s\n' "${timeout_seconds}" >&2
    return 2
  }

  timeout "${timeout_seconds}" getent ahostsv4 "${hostname}" 2>/dev/null |
    awk '{print $1}' |
    sort -u
}

probe_dns_success() {
  local hostname="${1:-}" timeout_seconds="${2:-3}" addresses

  addresses="$(probe_dns_addresses "${hostname}" "${timeout_seconds}")" || return $?
  [[ -n "${addresses}" ]]
}

probe_dns_wait() {
  local hostname="${1:-}" wait_seconds="${2:-60}"
  local poll_seconds="${3:-2}" resolve_timeout="${4:-3}" deadline

  [[ "${wait_seconds}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid DNS wait timeout: %s\n' "${wait_seconds}" >&2
    return 2
  }
  [[ "${poll_seconds}" =~ ^[1-9][0-9]*$ ]] || {
    printf 'invalid DNS poll interval: %s\n' "${poll_seconds}" >&2
    return 2
  }

  deadline=$((SECONDS + wait_seconds))
  while ((SECONDS < deadline)); do
    if probe_dns_success "${hostname}" "${resolve_timeout}"; then
      return 0
    fi
    sleep "${poll_seconds}"
  done
  return 1
}
