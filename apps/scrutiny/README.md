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

## Fresh cutover decision — 2026-09-09

Historical Scrutiny data from the stopped native app is no longer a cutover
requirement. The replacement uses a fresh, isolated InfluxDB base bucket named
`scrutiny` in organization `nabla`.

This means:

- do not restore the old embedded InfluxDB 2.2 datastore into the shared InfluxDB;
- do not reuse the shared `metrics` bucket for Scrutiny;
- provision the four Scrutiny buckets, placeholder downsampling tasks and
  restricted API token with
  `scripts/truenas/bootstrap-scrutiny-influxdb.sh`;
- keep the old native dataset only until the new collector/web path is accepted,
  then it may be deleted as explicitly approved.

## Migration sequence

1. Keep the stopped native Scrutiny dataset untouched until the replacement is accepted.
2. Ensure the shared InfluxDB 2.9 runtime is healthy.
An existing **empty** `/mnt/cpool/scrutiny/.env.secrets` is treated as
uninitialized and is safely populated by `--apply`. Rotation is required only
when the file already contains a non-empty `SCRUTINY_WEB_INFLUXDB_TOKEN`.

3. Provision fresh Scrutiny InfluxDB resources and the restricted token:

```bash
sudo env INFLUXDB_ADMIN_TOKEN="${INFLUXDB_ADMIN_TOKEN}" \
  bash scripts/truenas/bootstrap-scrutiny-influxdb.sh --apply
sudo bash scripts/truenas/bootstrap-scrutiny-influxdb.sh --check
```

4. Run the repository cutover preflight.
5. Start the repository-managed Scrutiny app.
6. Validate that the collector sees the host disks and the web API is healthy.
7. After acceptance, inspect the legacy mount/dataset ownership and delete the old
   native Scrutiny data only when no running container/app references it.
8. Validate the LAN path:

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

When the repository-managed Scrutiny app is still `MISSING`, this is a true
preflight: it requires the shared InfluxDB runtime/health, validates the rendered
Compose, discovers host SMART devices and then reports `ready=APPLY` without
creating or updating any TrueNAS app. If Scrutiny is already `RUNNING`,
`--check` additionally performs the full web/collector acceptance checks.

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
