# Functional observability exporters

This document defines the homelab metrics/exporter strategy for runtime diagnosis. The goal is to detect broken data paths even when containers, ports and basic healthchecks remain green.

## Design rule

Prefer the service's native metrics surface first, then a thin exporter. Do not add an exporter only to reproduce an existing TCP/HTTP healthcheck.

Use this hierarchy:

1. process/container state;
2. protocol readiness;
3. queue/backlog/consumer membership;
4. successful end-to-end work;
5. durable downstream result.

Before deploying any new receiver/exporter on TrueNAS, run:

```bash
sudo bash scripts/truenas/check-observability-exporter-conflicts.sh --check
```

The preflight is read-only. It inspects TrueNAS `reporting.exporters.query`, native Netdata state, listeners `8125/9125/9102/9308`, Docker publishers and relevant `intranet` containers.

TrueNAS 26 uses Netdata for system reporting. Its supported Reporting Exporters configuration currently exposes Graphite export, not an application-facing StatsD or Prometheus receiver. The live preflight remains authoritative because a Custom App or manually managed container can still own the proposed ports.

## Sentry / Taskbroker / Taskworker

### Current incident priority

Taskbroker recovery does **not** depend on StatsD or `kafka-exporter`. Recover Kafka consumer membership first with existing Kafka CLI evidence:

```text
Taskbroker running + Taskworker healthy
        +
Kafka group taskworker has zero active members
        ↓
restart Taskbroker only
        ↓
require active members > 0 AND lag decreases
        ↓
rerun Sentry end-to-end smoke
```

Use:

```bash
sudo bash scripts/truenas/diagnose-sentry-taskbroker.sh
sudo bash scripts/truenas/recover-sentry-taskbroker.sh
sudo bash scripts/truenas/diagnose-sentry-taskbroker.sh
sudo bash scripts/truenas/smoke-sentry-event.sh
```

The recovery helper refuses an unnecessary restart if `taskworker` already has an active member. It never resets offsets, deletes topics, deletes Taskbroker SQLite state, restarts Kafka or redeploys the Sentry App.

The diagnostic treats the optional exporter endpoints as supplemental evidence; `UNAVAILABLE` is expected before those exporters are deployed and does not block this recovery gate.

### StatsD candidate — intentionally not implemented yet

Sentry self-hosted can emit useful runtime telemetry over StatsD, including Taskbroker consumer/backpressure and Taskworker metrics. A candidate design is:

```text
Sentry / Taskbroker -> statsd-exporter:9125 on Docker intranet
                                 |
                                 v
                         /metrics :9102
                                 |
                                 v
                            Prometheus
```

However, PR #192 deliberately does **not** add the StatsD receiver, the Prometheus `sentry_statsd` scrape, or Sentry/Taskbroker StatsD configuration until the live TrueNAS conflict preflight has been reviewed. This prevents a duplicate receiver, port collision, or another knowingly DOWN Prometheus target.

If the preflight proves there is no equivalent existing receiver, a follow-up can add a pinned exporter with StatsD input kept internal to `intranet` and only its Prometheus `/metrics` endpoint exposed on the trusted LAN.

## Kafka

`kafka-exporter` belongs to the Kafka service boundary and therefore lives in `apps/kafka/compose.yml` beside the broker. It is explicitly bound to TrueNAS App ID `kafka`, waits for Kafka health, and exposes `172.17.0.24:9308/metrics` for Prometheus.

```text
Kafka App
├── kafka :9092
└── kafka-exporter :9308
             |
             v
         Prometheus
```

Primary metrics:

- `kafka_consumergroup_members`;
- `kafka_consumergroup_lag`;
- `kafka_consumergroup_current_offset`;
- topic/partition offsets and broker count.

Because adding this sidecar mutates the Kafka TrueNAS App lifecycle, do **not** deploy it during the initial Taskbroker recovery experiment. First restore/validate Sentry ingestion, then run the exporter conflict preflight and schedule a controlled Kafka App update.

Do not add JMX Exporter yet. Add it only if consumer membership/lag is insufficient to explain future coordinator stalls; then broker request latency, queue time, network-processor idle, controller/coordinator activity, ISR and JVM/GC become justified signals.

## Prometheus target reconciliation

Current connection-refused targets are tracked as runtime debt:

- Alloy `172.17.0.24:12345`;
- HAProxy exporter `:9101`;
- Loki `:3100`;
- Mimir `:9009`;
- OpenSearch exporter `:9114`;
- OpenSearch Security exporter `:9115`;
- PostgreSQL exporter `:9187`;
- Sybase exporter `:9113`;
- Tempo `:3200`.

For every target, prove owner/App/container state, host listener, `/metrics` behavior and Prometheus scrape result before changing the scrape config. A connection refusal can mean a stopped service, an exporter not published, a wrong port, or stale configuration; it is not by itself proof that the underlying application is down.

Mimir is first priority because Prometheus also remote-writes to `172.17.0.24:9009/api/v1/push`.

## Suricata

Do not add another exporter first. Suricata 8 already emits EVE `stats` records and Alloy tails `/var/log/suricata/*.json` into Loki.

Next work:

1. prove recent `event_type=stats` records exist;
2. reconcile the currently DOWN Alloy metrics target;
3. prove Alloy and CrowdSec advance while Suricata writes EVE;
4. alert on capture drops, decoder errors and EVE freshness;
5. add a dedicated exporter only if Loki/EVE statistics are insufficient.

## Wazuh

Wazuh exposes useful operational statistics through its API and manager state files but has no first-party Prometheus endpoint equivalent to node_exporter in the current design.

`scripts/truenas/diagnose-wazuh.sh` reads the manager state files without introducing API credentials. Priority evidence includes:

- active/disconnected/pending agents when API access is later added;
- `wazuh-remoted` queue usage and discarded messages;
- `analysisd` event rate, dropped events and queue pressure;
- manager daemon availability;
- indexer cluster/JVM/shard health.

A community Prometheus exporter remains deferred until a dedicated least-privilege API identity, credential handling and metric cardinality are reviewed.

## Immediate sequence

1. Diagnose Taskbroker now.
2. If `taskworker` still has zero active members while Taskbroker is running and Taskworker is healthy, run the guarded Taskbroker-only recovery.
3. Require membership recovery and lag decrease.
4. Rerun the diagnostic and `smoke-sentry-event.sh`; require Relay project config and end-to-end ingestion to recover.
5. Run the TrueNAS exporter/StatsD conflict preflight.
6. Reconcile the existing Prometheus DOWN targets, starting with Mimir.
7. Only then decide whether StatsD adds unique value and implement it if no equivalent receiver already exists.
8. Deploy `kafka-exporter` later through the Kafka App in a controlled lifecycle window.

No Kafka offset reset, topic purge, Taskbroker SQLite deletion or full Sentry redeploy is justified by the current evidence.
