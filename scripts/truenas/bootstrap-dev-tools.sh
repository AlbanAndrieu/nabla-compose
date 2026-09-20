#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

MISE_BIN="${MISE_BIN:-${HOME}/.local/bin/mise}"
DEV_VENV="${NABLA_TRUENAS_DEV_VENV:-${HOME}/.cache/nabla-compose/dev-venv}"
PRE_COMMIT_VERSION="${NABLA_PRE_COMMIT_VERSION:-4.6.2}"
SHELLCHECK_VERSION="${NABLA_SHELLCHECK_VERSION:-0.11.0}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
export MISE_LOCKFILE=false
PERSIST_SHELL_PATH=false

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${1:-}" in
  --persist-shell-path)
    PERSIST_SHELL_PATH=true
    shift
    ;;
  -h | --help)
    cat <<'EOF'
usage: bash scripts/truenas/bootstrap-dev-tools.sh [--persist-shell-path]

--persist-shell-path  idempotently add ~/.local/bin and the Nabla dev venv to ~/.bashrc
EOF
    exit 0
    ;;
  "") ;;
  *) fail "unknown argument: $1" ;;
esac
(($# == 0)) || fail "unexpected argument: $1"

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
# Keep the TrueNAS appliance immutable: tools live below the operator home,
# never under /usr and never through apt.
"${MISE_BIN}" --no-config install uv@latest
"${MISE_BIN}" --no-config install "shellcheck@${SHELLCHECK_VERSION}"

printf 'Preparing a minimal user-space development environment: %s\n' "${DEV_VENV}"
mkdir -p "$(dirname "${DEV_VENV}")"
if [[ -x "${DEV_VENV}/bin/python" ]]; then
  printf 'Reusing existing virtual environment: %s\n' "${DEV_VENV}"
else
  "${MISE_BIN}" --no-config exec uv@latest -- \
    uv venv --clear --python "${PYTHON_BIN}" "${DEV_VENV}"
fi
"${MISE_BIN}" --no-config exec uv@latest -- \
  uv pip install --python "${DEV_VENV}/bin/python" \
  "pre-commit==${PRE_COMMIT_VERSION}" pytest PyYAML

SHELLCHECK_BIN="$(
  "${MISE_BIN}" --no-config which \
    --tool "shellcheck@${SHELLCHECK_VERSION}" shellcheck
)"
[[ -x "${SHELLCHECK_BIN}" ]] || fail "mise-installed shellcheck is not executable: ${SHELLCHECK_BIN}"
ln -sfn "${SHELLCHECK_BIN}" "${DEV_VENV}/bin/shellcheck"
"${DEV_VENV}/bin/shellcheck" --version

printf 'Installing repository Git hooks with venv-managed pre-commit...\n'
"${DEV_VENV}/bin/pre-commit" install \
  --install-hooks --hook-type pre-commit --hook-type commit-msg
"${DEV_VENV}/bin/pre-commit" install \
  --config .pre-commit-pre-push.yaml --install-hooks --hook-type pre-push

if [[ "${PERSIST_SHELL_PATH}" == "true" ]]; then
  shell_rc="${NABLA_TRUENAS_SHELL_RC:-${HOME}/.bashrc}"
  marker="# >>> nabla-compose operator path >>>"
  touch "${shell_rc}"
  if ! grep -Fq -- "${marker}" "${shell_rc}"; then
    cat >>"${shell_rc}" <<'EOF'

# >>> nabla-compose operator path >>>
export NABLA_TRUENAS_DEV_VENV="${NABLA_TRUENAS_DEV_VENV:-$HOME/.cache/nabla-compose/dev-venv}"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
case ":$PATH:" in
  *":$NABLA_TRUENAS_DEV_VENV/bin:"*) ;;
  *) export PATH="$NABLA_TRUENAS_DEV_VENV/bin:$PATH" ;;
esac
# <<< nabla-compose operator path <<<
EOF
    printf 'Persisted Nabla operator PATH in %s\n' "${shell_rc}"
  else
    printf 'Nabla operator PATH is already present in %s\n' "${shell_rc}"
  fi
fi

cat <<EOF

✅ TrueNAS development tooling is ready without modifying the appliance OS.

The agent quality gate automatically prepends this venv when it exists:
  bash scripts/agent-quality-gate.sh --fix
  bash scripts/agent-quality-gate.sh

Optional persistent interactive PATH:
  bash scripts/truenas/bootstrap-dev-tools.sh --persist-shell-path
  source ~/.bashrc

Existing Kubernetes/Talos operator tools stay separate and root-managed:
  bash scripts/truenas/install-operator-tools.sh --check

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
