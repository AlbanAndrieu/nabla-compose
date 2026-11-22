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

# Print one non-empty custom field of the Vaultwarden item named exactly ITEM
# (BW_SESSION required). Capture it, never echo it: value="$(bw_field ITEM FIELD)"
bw_field() {
  bw list items --search "$1" | jq -er --arg n "$1" --arg f "$2" '
    [.[] | select(.name == $n)] | if length == 1 then .[0] else error("expected one item named \($n)") end
    | [.fields[]? | select(.name == $f) | .value | select(. != null and . != "")] | first // error("\($n) has no \($f)")'
}

# mcp-remote bridges a Streamable HTTP MCP to stdio; headers come from a file so
# that no key ever appears in a process command line.
# shellcheck disable=SC2034 # read by the launchers that source this file
MCP_REMOTE_PACKAGE="mcp-remote@0.16.5"
