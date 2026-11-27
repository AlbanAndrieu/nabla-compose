#!/usr/bin/env bash
# Run a TrueNAS cron command quietly: nothing at all on success; on failure a
# short summary goes to OpenClaw by mail (TrueNAS mail.send, sender set by
# reconcile-mail-settings.py) and Slack. The cron jobs hide stdout and stderr,
# so TrueNAS never mails the raw output with its "If you don't wish..." footer.
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
summary="$(
  sed -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e '/^[[:space:]]*$/d' "${log}" |
    awk '
      { all[++n] = $0 }
      tolower($0) ~ /error|fail|fatal|refused|denied|traceback|exception|found|infect|❌|💥|🦠|⚠️/ { hit[++h] = $0 }
      END {
        if (h) { for (i = 1; i <= h; i++) pick[i] = hit[i]; m = h }
        else { s = n > 8 ? n - 7 : 1; for (i = s; i <= n; i++) pick[++m] = all[i] }
        if (h && hit[h] != all[n]) pick[++m] = all[n]
        for (i = 1; i <= m; i++) { line = substr(pick[i], 1, 200); if (!(line in c)) order[++k] = line; c[line]++ }
        for (i = 1; i <= k && i <= 12; i++) { line = order[i]; count = c[line]; print (count > 1 ? count "× " : "") line }
        if (k > 12) print "… " k - 12 " autre(s) ligne(s)"
      }'
)"
last="$(printf '%s\n' "${summary}" | tail -1 | sed 's/^[0-9]*× //' | cut -c1-90)"
elapsed=$((SECONDS - started))
duration="$((elapsed / 3600))h$(printf '%02d' $((elapsed % 3600 / 60)))"
host="$(hostname -s)"
last="${last% (*}"
# A summary line that starts with its own emoji (🦠, ❌, 💥) leads the subject.
if [[ -n "${last}" ]] && (($(printf '%s' "${last:0:1}" | LC_ALL=C wc -c) > 1)); then
  subject="${last%% *} [${host}] ${name} : ${last#* }"
else
  subject="❌ [${host}] ${name} : ${last:-exit ${rc}}"
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

webhook="$(as_root sed -n 's/^NABLA_CRON_SLACK_WEBHOOK_URL=//p' "${ENV_FILE}" 2>/dev/null | head -1 | tr -d "\"'")"
if [[ "${webhook}" == https://hooks.slack.com/* ]]; then
  # The webhook URL is a credential: hand it to curl on stdin, never in argv.
  jq -n --arg t "${text}" '{text: $t}' |
    curl -sf --max-time 15 -H 'Content-Type: application/json' --data-binary @- \
      -K <(printf 'url = "%s"\n' "${webhook}") >/dev/null && sent=1
fi
unset webhook

((sent)) || logger -t nabla-cron "${name} failed (exit ${rc}) and no notification could be sent; see ${log}"
exit "${rc}"
