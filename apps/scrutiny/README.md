# Scrutiny migration

This Compose service replaces the current TrueNAS Apps Scrutiny omnibus deployment.

## Current native source

The current TrueNAS app stores durable data under:

```text
/mnt/.ix-apps/app_mounts/scrutiny/config
/mnt/.ix-apps/app_mounts/scrutiny/influxdb
```

The target Compose datasets are:

```text
/mnt/cpool/scrutiny/config
/mnt/cpool/scrutiny/influxdb
```

Do not run the native TrueNAS app and the Compose replacement simultaneously against the same data.

## Cutover

1. Verify the current native app is healthy and capture `/api/health`.
2. Stop the native Scrutiny app.
3. Snapshot the source datasets.
4. Create the target datasets/directories if they do not exist.
5. Copy the durable data while the source app is stopped:

```bash
rsync -aHAX --numeric-ids \
  /mnt/.ix-apps/app_mounts/scrutiny/config/ \
  /mnt/cpool/scrutiny/config/

rsync -aHAX --numeric-ids \
  /mnt/.ix-apps/app_mounts/scrutiny/influxdb/ \
  /mnt/cpool/scrutiny/influxdb/
```

6. Start `apps/scrutiny/compose.yml`.
7. Validate:

```bash
curl -fsS http://172.17.0.24:31054/api/health
curl -fsS http://127.0.0.1:31055/health
docker inspect scrutiny | jq -r '.[0].State.Health.Status'
```

8. Confirm the existing disks/history are present before retiring the native app.

The image is pinned to `v0.9.3-omnibus`, matching the currently observed native app version.

## Security notes

- the web/API is bound only to the TrueNAS LAN address on TCP/31054;
- embedded InfluxDB is host-loopback only on TCP/31055;
- `/run/udev` and `/dev` remain read-only;
- only `SYS_RAWIO` is added initially;
- add `SYS_ADMIN` only if an actual NVMe compatibility requirement is demonstrated.
