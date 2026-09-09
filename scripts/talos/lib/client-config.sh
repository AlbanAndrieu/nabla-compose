# Shared Talos/Kubernetes client configuration resolution.
#
# Prefer the current operator's private config directory when populated, while
# preserving the repository-local generated config fallback used by existing
# workstation workflows.

nabla_resolve_talos_client_config() {
  local root="$1"
  local operator_dir="${NABLA_TALOS_CONFIG_DIR:-${HOME}/.config/nabla/talos}"
  local repo_dir="${root}/.talos/generated"

  if [[ -z "${TALOSCONFIG:-}" ]]; then
    if [[ -s "${operator_dir}/talosconfig" ]]; then
      TALOSCONFIG="${operator_dir}/talosconfig"
    else
      TALOSCONFIG="${repo_dir}/talosconfig"
    fi
  fi

  if [[ -z "${KUBECONFIG:-}" ]]; then
    if [[ -s "${operator_dir}/kubeconfig" ]]; then
      KUBECONFIG="${operator_dir}/kubeconfig"
    else
      KUBECONFIG="${repo_dir}/kubeconfig"
    fi
  fi

  export TALOSCONFIG KUBECONFIG
}
