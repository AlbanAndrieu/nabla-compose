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

## Sentry / Taskbroker / Taskworker

### Current implementation

Sentry self-hosted uses StatsD for runtime metrics. The homelab sends Sentry and Taskbroker metrics to the Prometheus `statsd-exporter`:

```text
Sentry processes -----------\
Sentry Taskworker -----------+--> UDP/TCP 172.17.0.24:9125
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

- `apps/prometheus/compose.yml`: `statsd-exporter`, pinned to `v0.30.0` by default;
- `apps/prometheus/prometheus.yml`: job `sentry_statsd`;
- `apps/sentry/config/sentry.conf.py`: `SENTRY_STATSD_ADDR`, default `172.17.0.24:9125`;
- `apps/sentry/config/taskbroker.yml`: `statsd_addr: 172.17.0.24:9125`.

The first metrics to validate during the current incident are Taskbroker consumer/backpressure and Sentry Taskworker fetch metrics. In particular, Sentry upstream incident evidence uses metrics in the families:

- `taskbroker_consumer_*`;
- `sentry_taskworker_*`;
- exporter self-metrics `statsd_exporter_*`.

Do not hard-code an alert to a Taskbroker metric name until the running 26.8 stack has emitted that metric at least once. Exporter availability plus Kafka membership/lag alerts are safe immediately.

### Current acceptance

Sentry functional acceptance still requires the synthetic event smoke:

```text
edge -> Relay -> Kafka ingest-events -> ingest consumer -> events -> Snuba -> ClickHouse
```

StatsD metrics accelerate diagnosis; they do not replace `smoke-sentry-event.sh`.

## Kafka

### Current implementation

Kafka itself stays unchanged. The exporter deliberately lives in the Prometheus TrueNAS App so adding observability cannot trigger a Kafka lifecycle change.

```text
Kafka :9092 <-intranet- kafka-exporter :9308 -> Prometheus
```

Repository configuration:

- `apps/prometheus/compose.yml`: `danielqsj/kafka-exporter:v1.9.0`;
- `apps/prometheus/prometheus.yml`: job `kafka_exporter`, 30-second scrape;
- `apps/prometheus/rules/sentry-kafka.rules.yml`: Taskbroker membership/lag alerts.

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

Recommended sequence:

1. extend `diagnose-wazuh.sh` with the read-only API/state counters first;
2. define a dedicated least-privilege Wazuh API identity for metrics;
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

After deploying only the Prometheus observability changes and the Sentry StatsD configuration:

1. run `scripts/truenas/diagnose-sentry-taskbroker.sh` and capture the exporter sections;
2. record `kafka_consumergroup_members{consumergroup="taskworker"}` and taskworker lag;
3. record the current Taskbroker/Sentry StatsD metrics;
4. if the group still has zero active members, perform the already-reviewed targeted Taskbroker-only restart;
5. verify group membership reappears and lag decreases;
6. verify Relay project-config pending counts fall;
7. rerun `smoke-sentry-event.sh` and require end-to-end success.

No Kafka offset reset, topic purge, Taskbroker SQLite deletion or full Sentry redeploy is justified before this sequence is observed.
