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

Pyroscope is functional only when its HTTP service responds successfully and
its Prometheus exposition endpoint is readable:

```bash
curl -fsS http://172.17.0.24:4040/
curl -fsS http://172.17.0.24:4040/metrics | head
```

Do not use `/ready` as the canonical direct probe for this pinned runtime. The
repository monitoring contract uses `/` for direct service health and
`/metrics` independently for Prometheus.

Then run the repository lifecycle audit:

```bash
scripts/truenas/audit-app-lifecycle.sh
```

The audit follows the repository-managed Docker container rather than the legacy
TrueNAS App state. When `fastapi-sample` is running it also proves the profiling
data path, not merely TCP/HTTP reachability:

1. `PYROSCOPE_SERVER_ADDRESS=http://172.17.0.24:4040` is configured in the
   FastAPI runtime;
2. `LabelValues` contains `service_name=fastapi-sample` in the last 15 minutes;
3. the expected Python CPU profile series
   `process_cpu:cpu:nanoseconds:cpu:nanoseconds` exists;
4. `/pyroscope/render` returns a non-empty flamegraph with recent non-zero
   timeline samples.

A running container with an unavailable HTTP service, or a ready Pyroscope
server that receives no usable FastAPI profiles, is still degraded and must not
be reported as healthy.


## TrueNAS runtime identity (UID/GID 568)

The Compose service now runs as `568:568` (the TrueNAS `apps` identity).
Before deploying this revision, stop the existing Pyroscope App and provision
`/mnt/cpool/pyroscope/data` for `568:568` using the TrueNAS dataset ACL
management interface or a deliberate ownership change. Do not change owner on
a live Raft store. Keep the previous dataset archive for rollback.

```bash
sudo chown -R 568:568 /mnt/cpool/pyroscope/data
sudo chmod 770 /mnt/cpool/pyroscope/data
sudo docker inspect pyroscope --format '{{.Config.User}}'
curl -sS -o /dev/null -w 'ready HTTP=%{http_code}\n' --max-time 8 http://172.17.0.24:4040/ready
```

**Do not treat the UID change as a proven repair for Raft.** A disposable
container sharing the previous volumes could write as UID 10001, while the
Pyroscope metastore was still failing. Recheck the Raft data path, persistence,
`/ready`, and actual profile ingestion. The three image-declared Docker
volumes at `/data`, `/data-compactor`, and `/data-metastore` are separate
from the explicit `/var/lib/pyroscope` bind mount; never prune them blindly.
