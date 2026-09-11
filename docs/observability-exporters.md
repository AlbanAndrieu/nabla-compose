# Functional observability exporters

This document defines the homelab metrics/exporter strategy for runtime diagnosis. The goal is to detect broken data paths even when containers, ports and basic healthchecks remain green.

## Design rule

Prefer the service's native metrics surface first, then a thin exporter. Do not add an exporter only to reproduce a TCP/HTTP healthcheck that already exists.

The useful hierarchy is:

1. process/container state;
2. protocol readiness;
3. queue/backlog/consumer membership;
4. successful end-to-end work;
5. durable downstream result.

An incident is not closed at level 1 or 2 when the service is a pipeline component.

Before deploying a new receiver/exporter on TrueNAS, run:

```bash
sudo bash scripts/truenas/check-observability-exporter-conflicts.sh --check
```

## TrueNAS native/exporter preflight — accepted 2026-09-11

The live TrueNAS preflight is complete:

```text
native reporting exporter: netdata, enabled=false, GRAPHITE -> 172.17.0.57:2003
netdata service: active
8125: FREE
9125: FREE
9102: FREE
9308: FREE
Docker publisher 9102: none
Docker publisher 9308: none
```

Existing exporter containers include Redis exporter on `:9121` and Pi-hole exporter on `:9617`; Kafka is present on the shared `intranet` network. No conflicting Docker publisher was found for proposed future StatsD exposition `:9102` or Kafka exporter `:9308`.

TrueNAS 26 uses Netdata internally for system reporting. Its configured Reporting Exporter path here is Graphite and is currently disabled. This does not provide an application StatsD receiver for Sentry/Taskbroker.

The clean port inventory means future exporters are technically possible, but it is **not** a reason to mutate Sentry during the active incident. Functional recovery stays ahead of new telemetry.

## Sentry / Taskbroker / Taskworker

### Current incident priority

The targeted Taskbroker restart exposed two separate failure layers:

```text
original state
  Taskbroker running
  Kafka group taskworker has zero active members
  lag growing
       |
       v
restart Taskbroker only
       |
       v
new startup failure exposed
  live metrics/StatsD hostname cannot resolve
  Taskbroker panic in src/metrics.rs
  exit=101 / restart loop
       |
       v
Taskworker still Docker healthy but gRPC unavailable
```

Therefore the recovery order is now:

1. restore Taskbroker bootability and gRPC reachability;
2. only then resume Kafka membership/lag diagnosis;
3. only then rerun the Sentry end-to-end smoke;
4. only after functional Sentry recovery consider adding StatsD instrumentation.

`recover-sentry-taskbroker.sh` now validates the actual bind-mounted `/etc/taskbroker/config.yml` before restarting. An explicit non-loopback `statsd_addr` must resolve from the Sentry network or the restart is refused. After restart, `restarting`/`exited`/`dead` is a fast failure and Taskworker must be able to reach `taskbroker:50051`.

The repository configuration intentionally contains no new `statsd_addr` while this incident is active. The long-running pre-restart Taskbroker had reported the default effective value `127.0.0.1:8126`; a stale bind-mounted external hostname must not be allowed to turn the original Kafka problem into another crash loop.

### Future StatsD instrumentation

Sentry self-hosted can emit StatsD runtime metrics. If functional recovery later leaves an observability gap, a repository-managed `statsd-exporter` remains a candidate design:

```text
Sentry / Taskbroker -> statsd-exporter:9125 (Docker intranet only)
                              |
                              v
                     Prometheus :9102
```

Requirements before implementation:

- no LAN publication for unauthenticated StatsD ingestion;
- only Prometheus exposition may be host-published;
- pin the exporter version;
- validate the metric names emitted by the running Sentry/Taskbroker version before creating alerts;
- do not make Sentry startup depend on a DNS name that is absent from the current Docker network.

StatsD accelerates diagnosis; it never replaces the end-to-end Sentry smoke.

## Kafka

`kafka-exporter` belongs to the Kafka service boundary and lives in `apps/kafka/compose.yml` beside the broker. It waits for Kafka health before starting and is explicitly bound to TrueNAS App ID `kafka`.

```text
Kafka App
├── kafka :9092
└── kafka-exporter :9308
             |
             v
         Prometheus
```

Repository configuration:

- `apps/kafka/compose.yml`: `danielqsj/kafka-exporter:v1.9.0`;
- `apps/prometheus/prometheus.yml`: job `kafka_exporter`;
- `apps/prometheus/rules/sentry-kafka.rules.yml`: Taskbroker membership/lag alerts.

Because exporter addition is a Kafka TrueNAS App lifecycle mutation, do **not** deploy it during Taskbroker recovery. First restore Taskbroker and prove end-to-end Sentry ingestion. Then use a controlled Kafka App update window.

Primary metrics:

- `kafka_consumergroup_members`;
- `kafka_consumergroup_lag`;
- `kafka_consumergroup_current_offset`;
- topic/partition offsets and broker count.

Do not add JMX Exporter yet. Add it only if broker-internal metrics are needed after consumer membership/lag is observable.

## Suricata

Do not add another exporter first. Suricata 8 already emits periodic statistics and EVE `stats` records, and Alloy already tails `/var/log/suricata/*.json` into Loki.

Current path:

```text
Suricata eve.json -> Alloy -> Loki -> Grafana
                  -> CrowdSec acquisition
```

Next work:

1. prove recent `event_type=stats` records exist in EVE;
2. build Grafana/Loki panels and alerts for capture drops, decoder errors and EVE freshness;
3. prove CrowdSec and Alloy both advance while Suricata writes EVE;
4. only introduce a dedicated Suricata Prometheus exporter if Loki-derived statistics are insufficient.

## Wazuh

Wazuh operational statistics are currently collected from official manager state files without adding API credentials. `scripts/truenas/diagnose-wazuh.sh` reads:

- `/var/ossec/var/run/wazuh-remoted.state`;
- `/var/ossec/var/run/wazuh-analysisd.state`.

Priority evidence includes queue usage, discarded messages, received/processed/dropped events and EPS. A community Prometheus exporter remains deferred until a least-privilege API identity, credential handling and metric cardinality are reviewed.

## Existing metrics already worth using

The homelab already exposes or plans to reconcile several useful surfaces:

- TrueNAS node exporter;
- PostgreSQL exporter;
- pfSense exporter with intentionally slow scrape cadence;
- CrowdSec metrics;
- ClickHouse `/metrics`;
- OpenSearch exporters;
- Akvorado inlet/outlet metrics;
- Grafana, Alloy, Loki, Mimir, Tempo and Alertmanager self-metrics.

The current Prometheus target page also has several connection-refused DOWN targets. Reconcile those endpoints before adding broad new exporter coverage; Mimir `:9009` is highest priority because Prometheus remote-write depends on it.

## Immediate Sentry sequence

```text
repair live Taskbroker config / stop exit=101 restart loop
  -> prove Taskworker -> taskbroker:50051
  -> inspect taskworker Kafka group
  -> require active member + decreasing lag
  -> rerun Relay/project-config diagnostics
  -> rerun smoke-sentry-event.sh
  -> only then deploy optional telemetry
```

No Kafka offset reset, topic purge, Taskbroker SQLite deletion or full Sentry redeploy is justified by the current evidence.
