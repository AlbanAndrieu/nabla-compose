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

Then validate the collector and force a fresh sample with `scripts/observability/verify-scrutiny-workstation-collector.sh --submit`. Final acceptance requires both `host_id=truenas` and `host_id=albandrieu` in the TrueNAS Scrutiny `/api/summary` response.

## Transient `/api/summary` HTTP 500

Scrutiny v0.9.3 configures SQLite with a 30-second busy timeout. A `/api/summary` request observed on 2026-09-10 returned HTTP 500 after about 30.2 seconds, then a later request returned HTTP 200 in 225 ms. This timing is consistent with transient SQLite lock contention while SMART writes are in progress.

Verification scripts therefore retry transient `/api/summary` failures with a per-attempt timeout longer than Scrutiny's internal 30-second SQLite busy timeout. A recovered single failure is reported as a warning; repeated failures remain a hard failure and require inspection of Scrutiny logs for `database is locked`, `busy`, `query error`, `timeout`, or `context deadline` evidence.
