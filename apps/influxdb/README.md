# Shared InfluxDB

This stack provides a reusable InfluxDB 2.x service for Scrutiny and future homelab consumers.

## Network contract

```text
Docker intranet consumers --> http://influxdb:8086
TrueNAS host diagnostics --> http://127.0.0.1:31055
LAN / Internet            -X-> no direct InfluxDB listener by default
```

Do not expose TCP/8086 or TCP/31055 through Cloudflare Tunnel or pfSense unless a separately reviewed use case requires it.

## Durable data

```text
/mnt/cpool/influxdb/data   -> /var/lib/influxdb2
/mnt/cpool/influxdb/config -> /etc/influxdb2
```

Create these as explicit datasets/directories before first start and include them in the normal backup policy.

## Bootstrap secrets

The Compose target requires:

```text
INFLUXDB_ADMIN_PASSWORD
INFLUXDB_ADMIN_TOKEN
```

Non-secret defaults:

```text
INFLUXDB_ADMIN_USERNAME=admin
INFLUXDB_ORG=nabla
INFLUXDB_DEFAULT_BUCKET=scrutiny
```

Keep admin credentials in the configured secret provider, never in Git.

After bootstrap, issue a least-privilege token per consumer. Scrutiny should receive a dedicated token through:

```text
SCRUTINY_INFLUXDB_TOKEN
```

Do not give application containers the admin token.

## Scrutiny history migration

The stopped native Scrutiny omnibus app used embedded InfluxDB 2.2 under:

```text
/mnt/.ix-apps/app_mounts/scrutiny/influxdb
```

The target image is InfluxDB 2.8. Preserve the source dataset and prefer a logical `influx backup` / `influx restore` migration over copying database engine files across versions.

Before migration, identify the source organization, bucket and retention settings. Restore into the standalone service, then validate:

```bash
curl -fsS http://127.0.0.1:31055/health
```

and confirm Scrutiny's historical timelines before deleting any native-app dataset.

## Future consumers

Containers attached to the shared external `intranet` network should use:

```text
http://influxdb:8086
```

rather than introducing additional host port bindings. Each new consumer should receive its own organization/bucket/token scope where practical.
