#!/usr/bin/env bash
set -euo pipefail

KUBECTL="${NABLA_KUBECTL:-/mnt/cpool/tools/bin/kubectl}"
KUBECONFIG="${NABLA_KUBECONFIG:-${HOME}/.config/nabla/talos/kubeconfig}"

EXPECTED=(
  "taloscp01=172.17.0.50"
  "taloswk01=172.17.0.51"
  "taloswk02=172.17.0.52"
)

[[ -x "${KUBECTL}" ]] || {
  echo "ERROR: kubectl not executable: ${KUBECTL}" >&2
  exit 1
}
[[ -r "${KUBECONFIG}" ]] || {
  echo "ERROR: kubeconfig not readable: ${KUBECONFIG}" >&2
  exit 1
}

payload="$("${KUBECTL}" --kubeconfig "${KUBECONFIG}" get nodes -o json)"

declare -A expected_names=()
for pair in "${EXPECTED[@]}"; do
  name="${pair%%=*}"
  ip="${pair#*=}"
  expected_names["${name}"]=1

  count="$(jq -r --arg name "${name}" '[.items[] | select(.metadata.name==$name)] | length' <<<"${payload}")"
  [[ "${count}" == "1" ]] || {
    echo "ERROR: expected exactly one Kubernetes Node named ${name}, found ${count}" >&2
    exit 1
  }

  observed_ip="$(jq -r --arg name "${name}" '
    .items[]
    | select(.metadata.name==$name)
    | [.status.addresses[]? | select(.type=="InternalIP") | .address]
    | if length==1 then .[0] else "AMBIGUOUS" end
  ' <<<"${payload}")"
  [[ "${observed_ip}" == "${ip}" ]] || {
    echo "ERROR: ${name} InternalIP drift expected=${ip} observed=${observed_ip}" >&2
    exit 1
  }

  ready="$(jq -r --arg name "${name}" '
    .items[]
    | select(.metadata.name==$name)
    | [.status.conditions[]? | select(.type=="Ready") | .status]
    | if length==1 then .[0] else "Unknown" end
  ' <<<"${payload}")"
  [[ "${ready}" == "True" ]] || {
    echo "ERROR: ${name} expected Ready=True observed=${ready}" >&2
    exit 1
  }

  printf 'OK: %s InternalIP=%s Ready=True\n' "${name}" "${ip}"
done

mapfile -t extras < <(
  jq -r '.items[].metadata.name' <<<"${payload}" |
    while IFS= read -r name; do
      [[ -n "${expected_names[${name}]+x}" ]] || printf '%s\n' "${name}"
    done
)

if (("${#extras[@]}" > 0)); then
  echo "ERROR: stale/unexpected Kubernetes Node object(s): ${extras[*]}" >&2
  echo "Inspect Pods and VolumeAttachments before deleting stale Nodes." >&2
  exit 1
fi

echo "SUCCESS: Kubernetes Node identity contract is exactly taloscp01=.50 taloswk01=.51 taloswk02=.52"
