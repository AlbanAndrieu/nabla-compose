# shellcheck shell=bash

# Shared, side-effect-free Docker runtime guards.
# Mutation and recovery actions remain in their owner-specific scripts.

docker_orphan_shim_recovery_guard() {
  local running="${1:-}" restarting="${2:-}" pid="${3:-}" shim_count="${4:-}" container_id="${5:-unknown}"

  case "${running}" in
    true | false) ;;
    *)
      printf 'invalid Docker running state: %s\n' "${running}" >&2
      return 2
      ;;
  esac
  case "${restarting}" in
    true | false) ;;
    *)
      printf 'invalid Docker restarting state: %s\n' "${restarting}" >&2
      return 2
      ;;
  esac
  [[ "${pid}" =~ ^[0-9]+$ ]] || {
    printf 'invalid container init PID: %s\n' "${pid}" >&2
    return 2
  }
  [[ "${shim_count}" =~ ^[0-9]+$ ]] || {
    printf 'invalid containerd shim count: %s\n' "${shim_count}" >&2
    return 2
  }

  [[ "${pid}" == "0" ]] || {
    printf 'live init PID %s exists; refusing orphan-shim recovery\n' "${pid}" >&2
    return 1
  }
  [[ "${running}" == "true" || "${restarting}" == "true" ]] || {
    printf 'container is not in a running/restarting ghost state\n' >&2
    return 1
  }
  ((shim_count == 1)) || {
    printf 'expected exactly one containerd shim for %s, found %s\n' \
      "${container_id}" "${shim_count}" >&2
    return 1
  }
}
