# shellcheck shell=bash
# Shared by the scripts/mcp launchers started from .mcp.json.
#
# The Claude desktop app passes no shell variables to MCP servers, so the
# credentials live in private files written by scripts/mcp/materialize-keys.sh
# (Vaultwarden stays the source of truth).

MCP_KEY_DIR="${NABLA_MCP_KEY_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/nabla/mcp}"

# Print the path of a private credential file; refuse a missing, linked or
# readable one. Call as: path="$(mcp_private_file NAME LABEL)" || exit 1
mcp_private_file() {
  local file="${MCP_KEY_DIR}/$1"
  if [[ ! -f "${file}" || -L "${file}" ]]; then
    echo "$2: ${file} is missing; run scripts/mcp/materialize-keys.sh" >&2
    return 1
  fi
  if [[ "$(stat -c '%a %u' "${file}")" != "600 $(id -u)" ]]; then
    echo "$2: ${file} must be yours with mode 600" >&2
    return 1
  fi
  printf '%s\n' "${file}"
}

# mcp-remote bridges a Streamable HTTP MCP to stdio; headers come from a file so
# that no key ever appears in a process command line.
# shellcheck disable=SC2034 # read by the launchers that source this file
MCP_REMOTE_PACKAGE="mcp-remote@0.16.5"
