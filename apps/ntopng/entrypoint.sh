#!/bin/sh
set -eu

secret_file="/run/secrets/ntopng_runtime_env"
password="$(sed -n 's/^NTOPNG_ADMIN_PASSWORD=//p' "${secret_file}" 2>/dev/null | tail -n 1)"
# The Vaultwarden renderer quotes dotenv values: strip one pair of outer quotes, never evaluate.
case "${password}" in
  \'*\') password=${password#\'} password=${password%\'} ;;
  \"*\") password=${password#\"} password=${password%\"} ;;
esac
if [ "${#password}" -lt 16 ]; then
  printf '%s\n' "NTOPNG_ADMIN_PASSWORD missing or shorter than 16 characters: refusing admin/admin" >&2
  exit 1
fi

# Redis keeps ntopng users and preferences: the bind-mounted host directory
# must belong to the image's redis user or every write fails after a BGSAVE error.
chown -R redis:redis /var/lib/redis
/etc/init.d/redis-server start >/dev/null
tries=0
until redis-cli ping >/dev/null 2>&1; do
  tries=$((tries + 1))
  [ "${tries}" -lt 30 ] || { printf '%s\n' "local Redis did not start" >&2; exit 1; }
  sleep 1
done

# ntopng writes admin/admin only when this key is absent (Redis::setDefaults):
# set the Vaultwarden password first, so the UI is never reachable with the default.
hash="$(printf '%s' "${password}" | md5sum | cut -d ' ' -f 1)"
unset password
redis-cli SET ntopng.user.admin.password "${hash}" >/dev/null
redis-cli SET ntopng.prefs.admin_password_changed 1 >/dev/null
unset hash
exec ntopng /etc/ntopng/nabla.conf
