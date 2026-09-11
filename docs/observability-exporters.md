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

The preflight is read-only. It inspects TrueNAS `reporting.exporters.query`, the native Netdata service, host listeners `8125/9125/9102/9308`, Docker publishers and relevant containers on `intranet`.

TrueNAS 26 uses Netdata internally for system reporting. The supported Reporting Exporters configuration currently exposes Graphite export; that native reporting path is separate from the application-specific StatsD/Kafka metrics proposed here. The runtime preflight remains authoritative for the actual host because Custom Apps or manually managed containers can still occupy the same ports.

## Sentry / Taskbroker / Taskworker

### Current incident priority

The Taskbroker recovery experiment does **not** require StatsD or `kafka-exporter`. Diagnose and recover the broken Kafka consumer membership first with the existing Kafka CLI signal:

```text
Taskbroker process running
        +
Taskworker healthy
        +
Kafka group taskworker has zero active members
        ↓
restart Taskbroker only
        ↓
require active member > 0 AND lag decreases
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

The recovery helper refuses to restart Taskbroker if the `taskworker` group already has an active member. It never resets Kafka offsets, deletes topics, deletes Taskbroker SQLite state or redeploys the whole Sentry App.

### Staged StatsD instrumentation

Sentry self-hosted uses StatsD for runtime metrics. The staged homelab design sends Sentry and Taskbroker metrics to the Prometheus `statsd-exporter` over the Docker-only shared `intranet` network:

```text
Sentry processes -----------\
Sentry Taskworker -----------+--> statsd-exporter:9125 (Docker intranet only)
Taskbroker -----------------/               |
                                            v
                                  statsd-exporter :9102
                                            |
                                            v
                                        Prometheus
                                            |
                                            v
                                           Mimir
```

Repository configuration:

- `apps/prometheus/compose.yml`: staged `statsd-exporter`, pinned to `v0.30.0` by default;
- only Prometheus exposition port `172.17.0.24:9102` is host-published; StatsD TCP/UDP 9125 is not exposed on the LAN;
- `apps/prometheus/prometheus.yml`: job `sentry_statsd`;
- `apps/sentry/config/sentry.conf.py`: `SENTRY_STATSD_ADDR`, default `statsd-exporter:9125`;
- `apps/sentry/config/taskbroker.yml`: `statsd_addr: statsd-exporter:9125`.

Do not deploy this staged receiver until `check-observability-exporter-conflicts.sh --check` proves there is no conflicting host publisher and identifies any pre-existing StatsD/Netdata receiver on the TrueNAS host.

The first metrics to validate during the current incident are Taskbroker consumer/backpressure and Sentry Taskworker fetch metrics. Useful families include:

- `taskbroker_consumer_*`;
- `sentry_taskworker_*`;
- exporter self-metrics `statsd_exporter_*`.

Do not hard-code an alert to a Taskbroker metric name until the running 26.8 stack has emitted that metric at least once. Exporter availability plus Kafka membership/lag alerts are safe immediately after the exporter is actually deployed.

The upstream self-hosted stack can also route Snuba and Relay telemetry through `SNUBA_STATSD_ADDR` and `RELAY_STATSD_ADDR`. Add those only after Taskbroker incident acceptance if their metrics answer a concrete unresolved question.

### Current acceptance

Sentry functional acceptance still requires the synthetic event smoke:

```text
edge -> Relay -> Kafka ingest-events -> ingest consumer -> events -> Snuba -> ClickHouse
```

StatsD metrics accelerate diagnosis; they do not replace `smoke-sentry-event.sh`.

## Kafka

### Current implementation

`kafka-exporter` belongs to the Kafka service boundary and therefore lives in `apps/kafka/compose.yml` beside the broker. It waits for the Kafka service healthcheck before starting and is explicitly bound to TrueNAS App ID `kafka`.

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
- `apps/prometheus/prometheus.yml`: job `kafka_exporter`, 30-second scrape;
- `apps/prometheus/rules/sentry-kafka.rules.yml`: Taskbroker membership/lag alerts.

Because the exporter is in the Kafka TrueNAS App, adding or changing it is a Kafka App lifecycle mutation. Do **not** deploy it during the first Taskbroker recovery experiment. First complete the targeted Taskbroker-only restart and end-to-end smoke; then use the exporter conflict preflight and a controlled Kafka App update window.

Primary metrics:

- `kafka_consumergroup_members`;
- `kafka_consumergroup_lag`;
- `kafka_consumergroup_current_offset`;
- topic/partition offsets and broker count.

For the Sentry incident, group `taskworker` must have at least one active member and its lag must drain under normal load. A healthy Kafka TCP socket is not sufficient.

### Later broker internals

Do not add JMX Exporter yet. Add it only if broker-internal metrics are needed to explain coordinator stalls after consumer membership/lag is observable. Candidate broker metrics would include request latency, request queue time, network processor idle, controller/coordinator activity, ISR and JVM/GC.

## Suricata

Do not add another exporter first. Suricata 8 already emits periodic statistics and EVE `stats` records, and Alloy already tails `/var/log/suricata/*.json` into Loki.

Current path:

```text
Suricata eve.json -> Alloy -> Loki -> Grafana
                  -> CrowdSec acquisition
```

Useful Suricata counters include:

- capture packets/bytes and kernel drops;
- decoder packets/errors;
- flow memory/emergency-mode counters;
- detection/alert counters;
- app-layer parser errors;
- rule/reload health where available.

Next work:

1. prove recent `event_type=stats` records exist in EVE;
2. build Grafana/Loki panels and alerts for capture drops, decoder errors and EVE freshness;
3. prove CrowdSec and Alloy both advance while Suricata writes EVE;
4. only introduce a dedicated Suricata Prometheus exporter if Loki-derived statistics are insufficient for alerting.

This avoids another privileged/security-sensitive sidecar beside the packet-capture engine.

## Wazuh

Wazuh 4.14 exposes rich operational statistics through its authenticated server API and state files, but it does not currently provide a first-party native Prometheus endpoint equivalent to node_exporter.

Useful API/state surfaces include:

- `/manager/status`: daemon state;
- `/manager/stats`: alert/event statistics;
- `/manager/stats/hourly`;
- `/manager/daemons/stats`: `wazuh-remoted`, `wazuh-analysisd`, queue/discard information;
- `/agents/summary` and `/agents/summary/status`;
- `/var/ossec/var/run/wazuh-remoted.state`;
- `/var/ossec/var/run/wazuh-analysisd.state`.

The first read-only step is implemented in `scripts/truenas/diagnose-wazuh.sh`: it reads the manager state files directly from the running manager container without introducing API credentials. It reports `remoted` queue size, sessions, event count, discarded messages and queue usage, plus `analysisd` received/processed/dropped events, EPS and queue-pressure counters.

Recommended next sequence:

1. validate the new state-file counters against the live manager and establish normal baselines;
2. define a dedicated least-privilege Wazuh API identity for metrics only if agent-summary/API-only data is needed continuously;
3. evaluate a pinned community Wazuh Prometheus exporter only after reviewing its API calls, cardinality and credential handling;
4. keep the Wazuh indexer separate: use an OpenSearch-compatible exporter for JVM/index/shard health if the existing OpenSearch telemetry does not cover the Wazuh indexer.

Do not deploy an unpinned `latest` community exporter containing manager credentials.

Priority Wazuh metrics are:

- active/disconnected/pending/never-connected agents;
- `wazuh-remoted` queue usage and discarded messages;
- analysisd event rate and queue pressure;
- manager daemon availability;
- indexer cluster health, JVM pressure and shard health.

## Existing metrics already worth using

The homelab already exposes/scrapes several useful surfaces:

- TrueNAS node exporter;
- PostgreSQL exporter;
- pfSense exporter with intentionally slow scrape cadence;
- CrowdSec metrics;
- ClickHouse `/metrics`;
- OpenSearch exporters;
- Akvorado inlet/outlet metrics;
- Grafana, Alloy, Loki, Mimir, Tempo and Alertmanager self-metrics.

Before adding Redis or Memcached exporters specifically for Sentry, first observe whether the current Sentry/Taskbroker/Kafka metrics indicate cache or Redis pressure. Add those exporters only when they answer a concrete unresolved question.

## Immediate Sentry diagnostic sequence

1. Run `diagnose-sentry-taskbroker.sh` now; exporter sections may legitimately report `UNAVAILABLE` because they are not required for this recovery gate.
2. If Kafka group `taskworker` has zero active members while Taskbroker is running and Taskworker is healthy, run `recover-sentry-taskbroker.sh`.
3. Require Taskbroker to rejoin the group and `taskworker` lag to decrease.
4. Rerun `diagnose-sentry-taskbroker.sh`, then `smoke-sentry-event.sh`; require Relay project config to clear and end-to-end ingestion to pass.
5. Only after Sentry functional acceptance, run `check-observability-exporter-conflicts.sh --check`.
6. If the preflight is clean and no equivalent native/custom receiver already exists, deploy the staged StatsD exporter.
7. Deploy `kafka-exporter` later through the Kafka App in a controlled lifecycle window, then validate Prometheus membership/lag alerts.

No Kafka offset reset, topic purge, Taskbroker SQLite deletion or full Sentry redeploy is justified before this sequence is observed.
