# Pyroscope on TrueNAS

This repository runs Grafana Pyroscope in single-node mode on TCP/4040.

## Persistence contract

Pyroscope v2 uses a stateful metastore backed by Raft. The Raft WAL/state and
the metastore data directory must survive container recreation.

The repository therefore keeps the whole Pyroscope state tree on the explicit
TrueNAS dataset:

```text
/mnt/cpool/pyroscope/data
  -> /var/lib/pyroscope
     +-- v1
     +-- v2/metastore/raft
     +-- v2/metastore/data
```

The Compose command pins the corresponding paths explicitly:

```text
-pyroscopedb.data-path=/var/lib/pyroscope/v1
-metastore.raft.dir=/var/lib/pyroscope/v2/metastore/raft
-metastore.data-dir=/var/lib/pyroscope/v2/metastore/data
```

Do not replace these paths with anonymous Docker volumes.

References:

- https://grafana.com/docs/pyroscope/latest/configure-server/reference-configuration-parameters/
- https://grafana.com/docs/pyroscope/latest/reference-pyroscope-v2-architecture/components/metastore/
- https://grafana.com/docs/pyroscope/latest/get-started/

## Recovery from `Metastore not ready`

The observed failure on 2026-09-07 was:

```text
HTTP 503
Metastore not ready: terminated after 50 retries
```

The previous container had anonymous persistent volumes, including the old
`/data`, `/data-compactor` and `/data-metastore` paths. Keep those volumes
until the replacement has passed the acceptance checks; do not delete them as
part of the first redeploy.

Before changing runtime state, record the current mounts:

```bash
docker inspect pyroscope --format '{{json .Mounts}}' | jq .
```

Then redeploy from `apps/pyroscope/compose.yml` using the explicit
`/mnt/cpool/pyroscope/data` bind mount.

If the target dataset already contains a failed or partially initialized v2
metastore, preserve it before attempting a fresh initialization. Move it to a
timestamped recovery directory rather than deleting it. Only reset Raft/
metastore state when preserving historical profile metadata is not required or
after an explicit backup/migration decision.

## Acceptance

Pyroscope is functional only when the readiness endpoint returns HTTP 200:

```bash
curl -fsS http://172.17.0.24:4040/ready
```

Then run the repository lifecycle audit:

```bash
scripts/truenas/audit-app-lifecycle.sh
```

A running container with a 503 readiness response is still degraded and must
not be reported as healthy.
