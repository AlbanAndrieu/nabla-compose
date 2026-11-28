#!/usr/bin/env bash
# Run a TrueNAS cron command quietly: nothing at all on success; on failure a
# short summary goes to OpenClaw by mail (TrueNAS mail.send, sender set by
# reconcile-mail-settings.py) and Slack. The cron jobs hide stdout and stderr,
# so TrueNAS never mails the raw output with its "If you don't wish..." footer.
# Slack: with NABLA_CRON_SLACK_BOT_TOKEN (xoxb-, chat:write) and
# NABLA_CRON_SLACK_CHANNEL in the env file, a one-line headline is posted and the
# detail goes to its thread; with only the webhook, both go in one message.
#   cron-notify.sh <job-name> -- <command> [args...]
set -uo pipefail

name="${1:-}"
shift || true
[[ "${1:-}" == "--" ]] && shift
if [[ ! "${name}" =~ ^[a-z0-9][a-z0-9-]*$ ]] || (($# == 0)); then
  echo "usage: cron-notify.sh <job-name> -- <command> [args...]" >&2
  exit 2
fi

MAIL_TO="${NABLA_CRON_MAIL_TO:-openclaw@albandrieu.com}"
ENV_FILE="${NABLA_CRON_NOTIFY_ENV:-/mnt/cpool/secrets/runtime/cron-notify/.env.secrets}"
LOG_DIR="${NABLA_CRON_LOG_DIR:-/mnt/cpool/var/nabla/ops-logs/cron}"
mkdir -p "${LOG_DIR}" 2>/dev/null
if [[ ! -w "${LOG_DIR}" ]]; then
  LOG_DIR="${TMPDIR:-/tmp}/nabla-cron-$(id -un)"
  mkdir -p "${LOG_DIR}"
fi
log="${LOG_DIR}/${name}-$(date +%Y%m%d-%H%M%S).log"

started=${SECONDS}
"$@" >"${log}" 2>&1
rc=$?
find "${LOG_DIR}" -maxdepth 1 -name "${name}-*.log" -mtime +30 -delete 2>/dev/null
# A quiet success leaves no empty log: the 5-minute jobs would pile up thousands.
((rc == 0)) && [[ ! -s "${log}" ]] && rm -f "${log}"
((rc == 0)) && exit 0

as_root() { if ((EUID == 0)); then "$@"; else sudo -n "$@"; fi; }

# Keep only what matters: error-looking lines when there are any, else the
# tail; repeated lines collapse into one with a count, in first-seen order.
# A `logger -s` echo (<13>Nov 28 14:01:22 tag: ...) repeats a line already in the
# log, and a hyphenated name (ix-sentry-snuba-errors-consumer-1) is not an error.
# The first output line is the first error-looking line, empty when there is none.
digest="$(
  sed -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e '/^[[:space:]]*$/d' \
    -e '/^<[0-9]\{1,3\}>[A-Z][a-z][a-z] [ 0-9][0-9] [0-9:]\{8\} /d' "${log}" |
    awk '
      { all[++n] = $0; l = tolower($0); gsub(/[[:alnum:]_.]+(-[[:alnum:]_.]+)+/, "", l) }
      l ~ /error|fail|fatal|refused|denied|rejected|traceback|exception|found|infect|❌|💥|🦠|⚠️/ { hit[++h] = $0 }
      END {
        print (h ? substr(hit[1], 1, 200) : "")
        if (h) { for (i = 1; i <= h; i++) pick[i] = hit[i]; m = h }
        else { s = n > 8 ? n - 7 : 1; for (i = s; i <= n; i++) pick[++m] = all[i] }
        if (h && hit[h] != all[n]) pick[++m] = all[n]
        for (i = 1; i <= m; i++) { line = substr(pick[i], 1, 200); if (!(line in c)) order[++k] = line; c[line]++ }
        for (i = 1; i <= k && i <= 12; i++) { line = order[i]; count = c[line]; print (count > 1 ? count "× " : "") line }
        if (k > 12) print "… " k - 12 " autre(s) ligne(s)"
      }'
)"
first_hit="${digest%%$'\n'*}"
summary="${digest#*$'\n'}"
last="$(printf '%s\n' "${summary}" | tail -1 | sed 's/^[0-9]*× //')"
elapsed=$((SECONDS - started))
duration="$((elapsed / 3600))h$(printf '%02d' $((elapsed % 3600 / 60)))"
host="$(hostname -s)"
starts_with_emoji() { [[ -n "$1" ]] && (($(printf '%s' "${1:0:1}" | LC_ALL=C wc -c) > 1)); }
# The key line leads the mail subject and the Slack message: a closing verdict that
# starts with its own emoji (🦠, ❌, 💥), else the first error-looking line, else the last.
if starts_with_emoji "${last}"; then key="${last}"; else key="${first_hit:-${last}}"; fi
key="$(printf '%s' "${key}" | cut -c1-120)"
key="${key% (*}"
if starts_with_emoji "${key}"; then
  subject="${key%% *} [${host}] ${name} : ${key#* }"
else
  subject="❌ [${host}] ${name} : ${key:-exit ${rc}}"
fi
text="❌ ${name} a échoué (exit ${rc}) sur ${host}, durée ${duration}.

${summary}

📄 Journal complet : ${log}"

html_escape() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
html="<div style=\"font-family:sans-serif;font-size:14px\">
<p style=\"margin:0 0 8px;color:#b42318;font-weight:bold\">❌ ${name} a échoué (exit ${rc})</p>
<p style=\"margin:0 0 8px;color:#475467\">🖥️ ${host} · ⏱️ ${duration} · 📄 ${log}</p>
<pre style=\"margin:0;padding:8px 12px;background:#fef3f2;border-left:4px solid #d92d20;white-space:pre-wrap\">$(printf '%s\n' "${summary}" | html_escape)</pre>
</div>"

sent=0
message="$(jq -n --arg s "${subject}" --arg t "${text}" --arg h "${html}" --arg to "${MAIL_TO}" \
  '{subject: $s, text: $t, html: $h, to: [$to]}')"
as_root midclt call -j mail.send "${message}" >/dev/null 2>&1 && sent=1

# Slack: a one-line headline with the key line; the detail goes to its thread. Slack
# text escapes &, < and > like HTML.
headline="❌ *${name}* a échoué sur ${host} (exit ${rc}, ${duration})"
[[ -z "${key}" ]] || headline+=$'\n'"> $(printf '%s' "${key}" | html_escape)"
detail="\`\`\`
$(printf '%s\n' "${summary}" | html_escape)
\`\`\`
📄 Journal complet : \`${log}\`"

env_value() { as_root sed -n "s/^$1=//p" "${ENV_FILE}" 2>/dev/null | head -1 | tr -d "\"'"; }
# Credentials reach curl through a config on a descriptor, never through argv.
slack_api() { # METHOD; JSON body on stdin
  curl -sS --max-time 15 -H 'Content-Type: application/json; charset=utf-8' --data-binary @- \
    -K <(printf 'url = "https://slack.com/api/%s"\nheader = "Authorization: Bearer %s"\n' "$1" "${token}")
}
# A bot token can thread (chat.postMessage returns the ts); the incoming webhook
# returns no ts, so it sends the headline and the detail as one message.
ts=""
token="$(env_value NABLA_CRON_SLACK_BOT_TOKEN)"
channel="$(env_value NABLA_CRON_SLACK_CHANNEL)"
if [[ "${token}" == xoxb-* && -n "${channel}" ]]; then
  ts="$(jq -n --arg c "${channel}" --arg t "${headline}" '{channel: $c, text: $t}' |
    slack_api chat.postMessage | jq -r 'select(.ok == true) | .ts // empty' 2>/dev/null)"
  if [[ -n "${ts}" ]]; then
    sent=1
    jq -n --arg c "${channel}" --arg ts "${ts}" --arg t "${detail}" '{channel: $c, thread_ts: $ts, text: $t}' |
      slack_api chat.postMessage >/dev/null
  fi
fi
unset token
webhook="$(env_value NABLA_CRON_SLACK_WEBHOOK_URL)"
if [[ -z "${ts}" && "${webhook}" == https://hooks.slack.com/* ]]; then
  jq -n --arg t "${headline}"$'\n'"${detail}" '{text: $t}' |
    curl -sf --max-time 15 -H 'Content-Type: application/json' --data-binary @- \
      -K <(printf 'url = "%s"\n' "${webhook}") >/dev/null && sent=1
fi
unset webhook

((sent)) || logger -t nabla-cron "${name} failed (exit ${rc}) and no notification could be sent; see ${log}"
exit "${rc}"
