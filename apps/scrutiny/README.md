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
5. Restore the Scrutiny bucket/history into the standalone InfluxDB instance and create a Scrutiny-scoped token. Do not reuse the InfluxDB admin token as `SCRUTINY_WEB_INFLUXDB_TOKEN`.
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

## Canonical runtime helper

After the snapshot/history review is complete and
`/mnt/cpool/scrutiny/.env.secrets` contains a dedicated
`SCRUTINY_WEB_INFLUXDB_TOKEN`, run the read-only gate:

```bash
sudo bash scripts/truenas/deploy-scrutiny.sh --check
```

For the actual repository-managed cutover:

```bash
sudo env SCRUTINY_CUTOVER_APPROVED=1 \
  bash scripts/truenas/deploy-scrutiny.sh --apply
```

The explicit approval variable prevents an accidental first cutover. The helper
does **not** create InfluxDB backups, restore historical buckets or mint tokens.
It validates those runtime prerequisites, reconciles InfluxDB first, waits for
`http://127.0.0.1:31055/health`, then reconciles Scrutiny and requires both
the web/API and collector containers to be running.

Before creating/updating Scrutiny, the helper runs:

```bash
smartctl --scan-open
```

on the TrueNAS host. Every discovered SMART device is rendered into the
host-specific Custom App Compose as an explicit Docker `devices:` mapping.
This follows Scrutiny's upstream container contract: merely bind-mounting
`/dev` is not a substitute for granting the container device access.

If an NVMe controller is discovered, the generated collector override adds
`SYS_ADMIN` in addition to the baseline `SYS_RAWIO`, because smartctl needs
that capability for NVMe SMART access. SATA/SAS-only hosts do not receive the
extra capability.

The rendered YAML is sent through TrueNAS
`custom_compose_config_string`. Environment secrets remain referenced through
`/mnt/cpool/scrutiny/.env.secrets`; the helper uses
`docker compose config --no-interpolate --no-env-resolution` so secret values
are not expanded into the stored Compose definition.

`app.update` is already a deployment job. The helper therefore does **not**
immediately call `app.redeploy` after an update; doing both would unnecessarily
start a second lifecycle cycle.

The final acceptance gate additionally runs `smartctl --scan-open` inside the
`scrutiny-collector` container. A RUNNING container with zero SMART-visible
devices is treated as a failed deployment.


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
- `SYS_RAWIO` is the baseline collector capability.
- host SMART devices are passed explicitly from the `smartctl --scan-open`
  inventory at cutover time; do not use `privileged: true`.
- `SYS_ADMIN` is added only to the rendered collector configuration when an
  NVMe controller is actually discovered.
