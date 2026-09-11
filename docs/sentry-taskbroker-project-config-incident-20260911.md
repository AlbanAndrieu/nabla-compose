# Sentry Taskbroker / Relay project-config incident — 2026-09-11

This document preserves the runtime evidence and current analysis for the Sentry 26.8 ingestion failure observed after the controlled TrueNAS reboot. It is historical incident evidence; current priorities remain in `docs/roadmap.md` and supported operator commands stay in `apps/sentry/README.md` / `scripts/truenas/*`.

## Executive summary

Sentry is process-healthy but not functionally healthy end to end.

The TrueNAS App is `RUNNING`, the edge accepts synthetic envelopes with HTTP 200, Kafka answers metadata requests, and the errors-only Sentry/Snuba consumers report healthy. Nevertheless, synthetic events never reach `sentry.errors_local`.

The first proven stalled stage is before `ingest-events`: its Kafka log-end offset does not advance after envelope acceptance. Relay repeatedly reports that the project config is still `pending` and eventually times out while fetching project state from the Sentry upstream.

The investigation then isolated the Taskbroker path used to build project configs. The `taskworker` Kafka consumer group has no active member and accumulates backlog, while Taskbroker's SQLite inflight table is empty. Taskbroker initially joined the Kafka group, then hit a 60-second group session timeout, revoked its assignments and never showed a later reassignment in the captured logs. The Taskbroker process remained running and its gRPC endpoint remained available, so process health concealed the functional consumer failure.

Current leading hypothesis: the Taskbroker Kafka consumer actor stopped after the coordinator/session timeout and did not successfully rejoin, leaving the process alive but unable to drain `taskworker`. This prevents asynchronous `sentry.tasks.relay.build_project_config` work from completing, so Relay remains stuck on `pending` project config and does not publish accepted envelopes into `ingest-events`.

## Runtime evidence

### End-to-end smoke

`smoke-sentry-event.sh` proves all of the following in one run:

- Kafka broker metadata request succeeds;
- Sentry edge health succeeds;
- synthetic envelope is accepted with HTTP 200;
- `ingest-events` log-end remains unchanged;
- `events` log-end therefore also remains unchanged;
- the event is absent from `sentry.errors_local` after the bounded wait;
- stage classification is `relay-kafka-publish`;
- Relay reports `deadline exceeded`, `errors=0`, `was_pending=true`, with roughly 275 project-config requests pending.

This places the active fault before normal Sentry ingest/Snuba processing.

### Relay / project config

Relay repeatedly logs failures equivalent to:

```text
error fetching project state <project-key>: deadline exceeded
errors=0
pending≈275
was_pending=true
```

Sentry 26.8 serves Relay project configuration through the private Relay project-config API. When a requested project config is not cached, Sentry returns it as `pending` and schedules `sentry.tasks.relay.build_project_config`; that task must complete and populate the project-config cache before Relay can process the project normally.

The observed symptom therefore makes the asynchronous project-config build path part of the critical ingestion path:

```text
Relay
  -> Sentry project-config API
  -> schedule_build_project_config
  -> taskworker Kafka topic
  -> Taskbroker
  -> Sentry Taskworker over gRPC
  -> project-config cache
  -> Relay can publish ingest event
```

### Taskbroker configuration

Taskbroker starts with the expected Sentry 26.8 configuration:

- Kafka cluster `default` -> `kafka:9092`;
- topic `taskworker`;
- consumer group `taskworker`;
- `consumer_disabled=false`;
- `kafka_session_timeout_ms=60000`;
- SQLite store `/opt/sqlite/taskbroker-activations.sqlite`;
- `max_pending_count=2048`;
- delivery mode `pull`;
- gRPC on `0.0.0.0:50051`;
- worker map `sentry -> http://127.0.0.1:50052`.

At startup Taskbroker successfully received Kafka partition assignments for `taskworker` and `events-subscription-results`.

At `17:01:22` it then logged a Kafka `SESSTMOUT` after approximately 60 seconds without a successful coordinator response, revoked the assignments and shut down the affected consumer actors. No later assignment for `taskworker` appears in the captured logs.

### Kafka group state

Later runtime inspection shows:

```text
topic            taskworker
partition        0
current-offset   562523
log-end-offset   598112
lag              35589
active members   0
```

The lag was observed increasing between diagnostics while no active consumer member existed.

This is the strongest direct evidence that Taskbroker is not draining the `taskworker` topic even though the Taskbroker container remains `running`.

### Sentry Taskworker state

`sentry-taskworker` is independently healthy and runs in pull mode:

```text
run taskworker --concurrency=2 --rpc-host=taskbroker:50051 ...
```

Its logs show successful connection to `taskbroker:50051` and worker child processes being spawned.

This is expected architecture: Sentry Taskworker does not directly own the Kafka consumer group. Taskbroker consumes Kafka, persists/claims activations and serves work to Taskworker over gRPC. Therefore `sentry-taskworker=healthy` does not prove that `taskworker` Kafka ingestion is healthy.

### Taskbroker SQLite state

Read-only SQLite inspection shows:

```text
tables: _sqlx_migrations, inflight_taskactivations
total: 0
application_empty=0
application_sentry=0
received_at_min=None
received_at_max=None
```

This result is important because it excludes two earlier candidate explanations:

1. Taskbroker is **not** blocked by a full local inflight queue (`max_pending_count=2048` while actual inflight count is zero).
2. The known migration pattern involving legacy SQLite activations with `application=''` is **not present** in this incident snapshot.

The backlog exists in Kafka and is not entering Taskbroker's local inflight store.

## Hypotheses eliminated or deprioritized

### Not a current Kafka broker outage

The shared Kafka broker is `healthy` and answers a real metadata request. Other Sentry consumer groups are active with zero lag. Earlier coordinator/time-out instability remains relevant version debt, but the current failure is more specifically the missing Taskbroker consumer membership.

### Not Snuba / ClickHouse as the first failing stage

`ingest-events` does not advance. Therefore the synthetic event does not reach the normal ingest consumer, `events` topic, Snuba consumer or ClickHouse write path. Restarting Snuba cannot repair this first stalled stage.

### Not an unhealthy errors-only consumer set

The allow-listed errors-only consumers remained healthy over a full health cycle. Their health does not compensate for the fact that Relay cannot obtain project config.

### Not a dead Taskworker process

Taskworker is healthy, connected to Taskbroker gRPC and running worker children. The broken component is before Taskworker receives tasks.

### Not the legacy `application=''` SQLite backlog pattern

The Taskbroker SQLite table contains zero activations. There are no empty-application rows to migrate or discard.

## Current working hypothesis

The evidence is consistent with a Taskbroker Kafka consumer-lifecycle failure:

1. Taskbroker starts and joins the Kafka consumer group.
2. A Kafka group session timeout occurs.
3. Taskbroker revokes `taskworker` partition 0 and shuts down the consumer actor.
4. The Taskbroker process and gRPC server remain alive.
5. The Kafka consumer does not successfully rejoin.
6. The `taskworker` topic backlog grows while SQLite stays empty.
7. Sentry can enqueue asynchronous work but it is not consumed by Taskbroker.
8. `build_project_config` does not complete.
9. Relay remains on `pending` project config and accepted envelopes never advance `ingest-events`.

This hypothesis still needs one recovery experiment to be considered confirmed: restart only Taskbroker and verify that it rejoins group `taskworker` and drains lag without resetting offsets or deleting state.

## Safe next recovery experiment

Do not reset Kafka offsets, delete Taskbroker SQLite, purge topics or redeploy the entire Sentry stack based on the current evidence.

The smallest useful recovery test is a targeted Taskbroker lifecycle restart, followed by observation only:

1. confirm the current Kafka `taskworker` group has no active member and record current/log-end offsets;
2. restart only the `taskbroker` container/service through the Sentry Compose/TrueNAS lifecycle;
3. require an active member to appear in group `taskworker`;
4. require lag to decrease from the recorded value;
5. confirm SQLite begins receiving/processing activations rather than remaining permanently empty;
6. confirm Relay `pending` counts fall and `deadline exceeded` messages stop;
7. rerun `smoke-sentry-event.sh` and require `ingest-events`, then `events`, to advance;
8. require the synthetic event to appear in `sentry.errors_local`.

If Taskbroker fails to rejoin after a targeted restart, investigate coordinator stability and Taskbroker 26.8 consumer lifecycle/upstream defects before considering destructive Kafka offset manipulation.

## Acceptance criteria

Sentry ingestion is accepted only when all of the following hold simultaneously:

- TrueNAS Sentry App is `RUNNING`;
- Kafka broker metadata readiness succeeds;
- Kafka group `taskworker` has an active member;
- `taskworker` lag is bounded and decreases under backlog;
- Relay project-config requests resolve instead of remaining indefinitely `pending`;
- synthetic envelope acceptance advances `ingest-events`;
- normal ingest advances `events`;
- Snuba writes the event into `sentry.errors_local`;
- `smoke-sentry-event.sh` exits 0.

Container/process health alone is explicitly insufficient for this acceptance.

## Diagnostics and guardrails

Use the repository diagnostics before mutating runtime state:

```bash
sudo bash scripts/truenas/diagnose-sentry.sh --check
sudo bash scripts/truenas/diagnose-sentry-taskbroker.sh
sudo bash scripts/truenas/smoke-sentry-event.sh
```

`diagnose-sentry-taskbroker.sh` is intentionally read-only. It must not reset Kafka offsets, delete SQLite rows, restart containers or change TrueNAS App state.

## Related platform findings from the same recovery window

### Suricata

Suricata is no longer an active startup incident:

- TrueNAS App `RUNNING`;
- container `healthy`, zero restarts;
- capture interface `br0`;
- persistent rule file contains 68,674 rules;
- engine loaded approximately 52,721 rules with zero rule-load failures;
- `eve.json` continues to receive post-redeploy events.

Remaining Suricata work is downstream EVE consumption by CrowdSec/Alloy/central observability and monitoring of rule refresh/kernel-drop health.

### pfSense NetFlow

Fresh NetFlow no longer appears in Cloudflare Network Analytics / Flow Analytics. This is tracked separately in the roadmap and must be diagnosed hop-by-hop from pfSense exporter configuration through any collector/tunnel path to Cloudflare. It is not coupled to the Sentry incident.
