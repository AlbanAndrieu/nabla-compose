# Shared InfluxDB

This stack adopts the existing TrueNAS Community InfluxDB 2.x datastore as a
standalone reusable service for Scrutiny and future homelab consumers.

## Version and network contract

The TrueNAS Community application currently uses InfluxDB 2.9.1. The Compose
target is pinned to the same version to avoid a datastore downgrade.

```text
Docker intranet consumers --> http://influxdb:8086
TrueNAS host diagnostics --> http://127.0.0.1:31055
LAN / Internet            -X-> no direct InfluxDB listener by default
```

Do not expose TCP/8086 or TCP/31055 through Cloudflare Tunnel or pfSense unless
a separately reviewed use case requires it.

## Adopt the existing host-path datastore

The stopped native application already uses the desired durable paths:

```text
/mnt/cpool/influxdb/data   -> /var/lib/influxdb2
/mnt/cpool/influxdb/config -> /etc/influxdb2
```

Take a recursive ZFS snapshot before first Compose start. For example:

```bash
zfs snapshot -r cpool/influxdb@pre-compose-migration-$(date +%Y%m%d)
```

Do not set `DOCKER_INFLUXDB_INIT_MODE=setup` when adopting this datastore.
Setup variables are only appropriate for an empty first-time InfluxDB 2.x
instance; replaying setup against an existing instance creates avoidable
migration ambiguity.

The official InfluxDB 2 entrypoint starts as root when necessary, fixes the
ownership of the engine/config directories, then drops to the `influxdb` user.
The host paths must remain writable during that first adoption.

Start the Compose-backed app and validate:

```bash
curl -fsS http://127.0.0.1:31055/health | jq
docker logs --tail=100 influxdb
```

Then inspect the existing organizations and buckets with an existing authorized
token before changing any retention policy.

## Scrutiny

Scrutiny should use a dedicated least-privilege token through:

```text
SCRUTINY_INFLUXDB_TOKEN
```

and connect over the shared Docker network:

```text
http://influxdb:8086
```

Do not give Scrutiny the InfluxDB administrator token. Restart the standalone
Scrutiny stack only after InfluxDB reports healthy and the expected historical
bucket is visible.

## Rollback

If adoption fails, stop the Compose-backed InfluxDB before rolling back. Do not
start the native TrueNAS app and the Compose service simultaneously against the
same host paths.

Keep the pre-migration ZFS snapshot until Scrutiny historical timelines have
been verified.
