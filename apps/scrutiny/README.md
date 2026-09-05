# Scrutiny migration

The target deployment replaces the stopped native TrueNAS Scrutiny omnibus app with two repository-managed Scrutiny workloads backed by the independent `apps/influxdb` service.

## Target architecture

```text
LAN browser
  |
  +--> http://172.17.0.24:31054
  |
Cloudflare Access
  |
Cloudflare Tunnel
  |
  +--> https://scrutiny.albandrieu.com
          |
          v
       scrutiny:8080
          |
          +--> influxdb:8086
          |
          <--- scrutiny-collector
                 |
                 +--> TrueNAS /dev + /run/udev
```

The LAN endpoint is **HTTP**:

```text
http://172.17.0.24:31054/
```

The externally navigable endpoint is:

```text
https://scrutiny.albandrieu.com/
```

Do not construct or publish `https://truenas.albandrieu.com:31054/`; TCP/31054 is not the TrueNAS HTTPS listener.

Cloudflare Access is part of the declared security boundary for the public hostname. The FastAPI Sample `/sickz` observer must see both the Tunnel ingress and a matching Access application/policy.

## Current source and target datasets

The stopped native TrueNAS app used:

```text
/mnt/.ix-apps/app_mounts/scrutiny/config
/mnt/.ix-apps/app_mounts/scrutiny/influxdb
```

The repository-managed targets are:

```text
/mnt/cpool/scrutiny/config
/mnt/cpool/influxdb/data
/mnt/cpool/influxdb/config
```

The user has already created the Scrutiny application dataset and stopped the native app. Keep the native datasets intact until historical SMART data has been verified in the replacement.

## Migration sequence

1. Snapshot the stopped native Scrutiny datasets before any conversion.
2. Copy the Scrutiny SQLite/config state:

```bash
rsync -aHAX --numeric-ids \
  /mnt/.ix-apps/app_mounts/scrutiny/config/ \
  /mnt/cpool/scrutiny/config/
```

3. **Do not blindly rsync** the old embedded InfluxDB directory into the new InfluxDB 2.8 data directory. The old omnibus runtime was observed on InfluxDB 2.2. Use a logical InfluxDB backup/restore path, preserving the stopped source dataset as rollback evidence.
4. Create/start `apps/influxdb/compose.yml` with admin credentials supplied through the secret provider.
5. Restore the Scrutiny bucket/history into the standalone InfluxDB instance and create a Scrutiny-scoped token. Do not reuse the InfluxDB admin token as `SCRUTINY_INFLUXDB_TOKEN`.
6. Start `apps/scrutiny/compose.yml`.
7. Validate the LAN path:

```bash
curl -fsS http://172.17.0.24:31054/api/health
```

8. Validate InfluxDB only from the host loopback or Docker `intranet` network:

```bash
curl -fsS http://127.0.0.1:31055/health
```

9. Validate the Cloudflare path from an external browser/client:

```text
https://scrutiny.albandrieu.com/
```

The expected result is the Cloudflare Access authentication/policy flow followed by the Scrutiny UI. A direct anonymous origin response is not the target security posture.

10. Verify all previously known disks and historical SMART timelines before retiring the native app.

## Cloudflare audit

From a workstation, use the repository helper backed by FastAPI Sample's read-only Cloudflare observer:

```bash
scripts/security/audit-cloudflare-access-via-fastapi.sh
```

If `/sickz` is protected by `DIAGNOSTICS_ACCESS_KEY`:

```bash
export FASTAPI_SAMPLE_DIAGNOSTICS_KEY='...'
scripts/security/audit-cloudflare-access-via-fastapi.sh
```

The helper fails when an Access-required service has no matching Access application/policy or when a broad public/bypass policy defeats the declared protection.

## Security notes

- Scrutiny keeps LAN TCP/31054 for migration compatibility.
- InfluxDB is not LAN-published by default; host access is loopback-only on TCP/31055 and Docker consumers use `influxdb:8086` on the external `intranet` network.
- `/run/udev` and `/dev` remain read-only in the collector.
- only `SYS_RAWIO` is granted initially;
- add `SYS_ADMIN` only if an actual NVMe compatibility requirement is demonstrated.
