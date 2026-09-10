# Workstation Compose runtime

The workstation runtime at `172.17.0.57` uses the repository checkout at `/workspace/users/albandrieu30/nabla-compose`.

The canonical Compose entrypoint is `docker-compose-albandrieu.yml`. That file includes `compose.monitoring.yml`, which owns the workstation observability services, including the Scrutiny collector. Do not manage `compose.monitoring.yml` as an independent stack.

Effective relationship:

```text
docker-compose-albandrieu.yml
  -> compose.monitoring.yml
     -> scrutiny-collector
```

The Scrutiny workstation component is a collector-only spoke. The Web/API hub runs on TrueNAS at `http://172.17.0.24:31054`. The workstation collector must use `COLLECTOR_HOST_ID=albandrieu` and the same Scrutiny release as the hub, currently `ghcr.io/analogj/scrutiny:v0.9.3-collector`.

The old running container was created from `compose.monitoring.yml` but its service definition had later been removed from that file. Docker Compose labels therefore still pointed to `compose.monitoring.yml` even though the current YAML no longer contained the service. This is an orphan-container state and can persist when Compose is reconciled without orphan cleanup.

To inspect the effective workstation project, run from the repository root:

```bash
docker compose -f docker-compose-albandrieu.yml config --services
docker compose -f docker-compose-albandrieu.yml config scrutiny-collector
```

To reconcile only the Scrutiny spoke after updating the repository:

```bash
docker compose -f docker-compose-albandrieu.yml pull scrutiny-collector
docker compose -f docker-compose-albandrieu.yml up -d --force-recreate scrutiny-collector
```

Then validate the collector and force a fresh sample with `scripts/observability/verify-scrutiny-workstation-collector.sh --submit`.

Accepted runtime evidence on 2026-09-10:

```text
workstation collector version=0.9.3
image=ghcr.io/analogj/scrutiny:v0.9.3-collector
host_id=albandrieu
/dev/sda /dev/sdb /dev/sdc visible
SMART submission ingested by server: devices=3
```

The TrueNAS-side acceptance then reported:

```text
collector host_id=truenas devices=4
collector host_id=albandrieu devices=3
Scrutiny collector acceptance passed for: truenas albandrieu
```

The dashboard at `http://172.17.0.24:31054/web/dashboard` showed both hosts after the compatible workstation collector submitted its first v0.9.3 sample.

## Transient `/api/summary` HTTP 500

The 2026-09-10 incident is now attributed to the InfluxDB query path, not SQLite locking. Scrutiny logged the exact backend failure:

```text
Post "http://influxdb:8086/api/v2/query?org=nabla":
context deadline exceeded (Client.Timeout exceeded while awaiting headers)
```

The matching `GET /api/summary` returned HTTP 500 after about 30.221 seconds, while a later request returned HTTP 200 in 225 ms. `GetSummary()` reads the Scrutiny InfluxDB buckets and the web handler returns HTTP 500 when that repository call fails.

Verification scripts therefore retry transient `/api/summary` failures with a bounded per-attempt timeout above 30 seconds. A recovered failure is a warning/diagnostic signal, not proof that the Scrutiny service is down. Repeated failures remain a hard failure and require inspection of both Scrutiny and InfluxDB query latency/logs.

Useful correlation commands on TrueNAS:

```bash
sudo docker logs --since 20m scrutiny 2>&1 |
  grep -Ei 'device summary|api/v2/query|context deadline|timeout|query error|influx'

sudo docker logs --since 20m ix-influxdb-influxdb-1 2>&1 |
  grep -Ei 'query|timeout|error|warn'
```

## SMART acceptance semantics

The TrueNAS acceptance gate checks freshness per device, not only the newest sample for a host. This prevents one recently updated disk from hiding another registered disk with stale or missing SMART data.

A `smartctl` non-zero bitmask does not necessarily mean collection failed. For example, exit code `64` can indicate that the drive error log contains records while Scrutiny still successfully publishes the SMART payload. Treat this as disk-health evidence to surface in Scrutiny, not automatically as collector transport failure.

Likewise, a device visible through udev but not passed through to the container can appear during discovery and then be skipped because it cannot be opened. The accepted TrueNAS inventory currently consists of the explicitly usable `/dev/sda` through `/dev/sdd`; investigate additional devices separately instead of failing the four-disk collector contract solely because an inaccessible extra device such as `/dev/sde` is discovered.
