# Sentry ClickHouse compatibility bridge

This TrueNAS Custom App is a **temporary compatibility bridge** for Sentry
self-hosted 26.8.0.

The homelab target remains one shared ClickHouse. Snuba 26.8.0 cannot complete
its migrations on the shared ClickHouse 26.8.2.7 because ClickHouse 26.7+
rejects the legacy AggregatingMergeTree layout used by Snuba migration
`generic_metrics:0041_adjust_partitioning_meta_tables` unless
`allow_dimensions_outside_sorting_key=1` is enabled. Do not enable that
compatibility setting globally merely for Sentry.

The image is therefore pinned to the exact Altinity line used by upstream
Sentry self-hosted 26.8.0:

```text
altinity/clickhouse-server:25.3.6.10034.altinitystable
```

## Runtime

- Docker DNS: `sentry-clickhouse`
- native protocol: `9000/tcp` on the external `intranet` Docker network
- HTTP protocol: `8123/tcp` on the external `intranet` Docker network
- no host port is published
- data: `/mnt/cpool/sentry-clickhouse/data`
- logs: `/mnt/cpool/sentry-clickhouse/logs`
- secret file: `/mnt/cpool/sentry-clickhouse/.env.secrets`

Because no host port is published, this service can listen on container port
9000 while the shared ClickHouse also listens on container port 9000.

## Required filesystem preparation

The Altinity image runs ClickHouse as UID/GID 101. Prepare persistent paths:

```bash
sudo install -d -m 700 /mnt/cpool/sentry-clickhouse
sudo install -d -m 750 -o 101 -g 101 \
  /mnt/cpool/sentry-clickhouse/data \
  /mnt/cpool/sentry-clickhouse/logs
```

The repository-mounted config file must be readable by the ClickHouse process.
A mode such as `0644` is required for the bind-mounted file:

```bash
chmod 0644 apps/sentry-clickhouse/config.xml
```

If startup remains in `DEPLOYING`, inspect:

```bash
sudo docker logs --tail 200 ix-sentry-clickhouse-sentry-clickhouse-1
```

An error like:

```text
Failed to merge config ... Access to file denied
```

means ClickHouse never reached the network-listener phase. It is not a TCP/9000
port collision.

## Retirement gate

Do not delete this datastore merely because a newer shared ClickHouse exists.
Retire this app only after a future supported Sentry/Snuba release passes fresh
migrations, synthetic event ingestion, querying, restart persistence and
rollback validation against the single shared ClickHouse.
