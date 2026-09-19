#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

MISE_BIN="${MISE_BIN:-${HOME}/.local/bin/mise}"
DEV_VENV="${NABLA_TRUENAS_DEV_VENV:-${HOME}/.cache/nabla-compose/dev-venv}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

command -v curl >/dev/null 2>&1 || fail "curl is required"
[[ -n "${PYTHON_BIN}" ]] || fail "python3 is required"

if [[ ! -x "${MISE_BIN}" ]]; then
  printf 'Installing mise into user space: %s\n' "${MISE_BIN}"
  installer="$(mktemp)"
  trap 'rm -f "${installer:-}"' EXIT
  curl -fsSL https://mise.run -o "${installer}"
  MISE_INSTALL_PATH="${MISE_BIN}" sh "${installer}"
  rm -f "${installer}"
  trap - EXIT
fi

"${MISE_BIN}" --version
"${MISE_BIN}" trust "${ROOT}/mise.toml"

# Keep the TrueNAS appliance immutable: tools live below the operator home,
# never under /usr and never through apt.
"${MISE_BIN}" install pre-commit@latest
"${MISE_BIN}" install uv@latest

printf 'Installing repository Git hooks with mise-managed pre-commit...\n'
"${MISE_BIN}" exec pre-commit@latest -- \
  pre-commit install --install-hooks --hook-type pre-commit --hook-type commit-msg
"${MISE_BIN}" exec pre-commit@latest -- \
  pre-commit install --config .pre-commit-pre-push.yaml --install-hooks --hook-type pre-push

printf 'Preparing a minimal user-space pytest environment: %s\n' "${DEV_VENV}"
mkdir -p "$(dirname "${DEV_VENV}")"
"${MISE_BIN}" exec uv@latest -- \
  uv venv --python "${PYTHON_BIN}" "${DEV_VENV}"
"${MISE_BIN}" exec uv@latest -- \
  uv pip install --python "${DEV_VENV}/bin/python" pytest PyYAML

cat <<EOF

✅ TrueNAS development tooling is ready without modifying the appliance OS.

Use:
  ${MISE_BIN} exec pre-commit@latest -- bash scripts/agent-quality-gate.sh --fix
  ${MISE_BIN} exec pre-commit@latest -- bash scripts/agent-quality-gate.sh

Focused pytest:
  ${DEV_VENV}/bin/python -m pytest -q \
    tests/test_legacy_secret_import.py \
    tests/test_secret_consumer_audit.py \
    tests/test_compare_dotenv_sources.py \
    tests/test_runtime_layout_policy_contract.py \
    tests/test_truenas_repository_bootstrap_contract.py \
    tests/test_observability_deploy_followup.py \
    tests/test_truenas_deployment_automation.py

Optional interactive shell activation:
  eval "\$(${MISE_BIN} activate bash)"
EOF
