# Sentry Taskbroker / Relay project-config incident — 2026-09-11

This document preserves the runtime evidence and current analysis for the Sentry 26.8 ingestion failure observed after the controlled TrueNAS reboot. It is historical incident evidence; current priorities remain in `docs/roadmap.md` and supported operator commands stay in `apps/sentry/README.md` / `scripts/truenas/*`.

## Executive summary

Sentry is not functionally healthy end to end even when most process/container health signals are green.

The TrueNAS App reports `RUNNING`, the edge accepts synthetic envelopes with HTTP 200, Kafka answers metadata requests, and the errors-only Sentry/Snuba consumers report healthy. Nevertheless, synthetic events do not reach `sentry.errors_local`.

The first proven stalled stage is before `ingest-events`: its Kafka log-end offset does not advance after envelope acceptance. Relay repeatedly reports that project config remains `pending` and eventually times out while fetching project state from Sentry.

The investigation isolated two distinct Taskbroker failure layers:

1. **Original functional failure:** Taskbroker initially joined Kafka, then hit a 60-second `SESSTMOUT`, revoked `taskworker` and `events-subscription-results`, and never showed a successful rejoin. The process and gRPC server remained alive while Kafka group `taskworker` had zero active members and growing lag.
2. **Restart/configuration regression exposed by the recovery experiment:** restarting only Taskbroker caused it to enter a restart loop with exit code `101`, panicking in `src/metrics.rs` because the effective metrics/StatsD socket address could not be resolved. This startup failure now masks the original Kafka rejoin failure until Taskbroker bootability is restored.

The Sentry Taskworker container remained Docker `healthy` during the Taskbroker crash loop, but its logs showed repeated gRPC `UNAVAILABLE`, `Socket closed`, `No route to host` and `Connection refused` errors against `taskbroker:50051`. Docker health is therefore explicitly insufficient for this path.

## Runtime evidence

### End-to-end smoke before targeted recovery

`smoke-sentry-event.sh` proved all of the following in one run:

- Kafka broker metadata request succeeds;
- Sentry edge health succeeds;
- synthetic envelope is accepted with HTTP 200;
- `ingest-events` log-end remains unchanged;
- `events` log-end therefore also remains unchanged;
- the event is absent from `sentry.errors_local` after the bounded wait;
- stage classification is `relay-kafka-publish`;
- Relay reports `deadline exceeded`, `errors=0`, `was_pending=true`, with roughly 275 project-config requests pending.

This places the original ingestion fault before normal Sentry ingest/Snuba processing.

### Relay / project config

Relay repeatedly logs failures equivalent to:

```text
error fetching project state <project-key>: deadline exceeded
errors=0
pending≈275
was_pending=true
```

When project config is not cached, Sentry schedules asynchronous `sentry.tasks.relay.build_project_config` work. The critical path is therefore:

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

### Original Taskbroker runtime state

Before the targeted restart, Taskbroker was `running`, restart count `0`, with gRPC listening on `0.0.0.0:50051`. Its effective startup configuration reported:

- Kafka cluster `default -> kafka:9092`;
- topic/group `taskworker`;
- `consumer_disabled=false`;
- `kafka_session_timeout_ms=60000`;
- SQLite `/opt/sqlite/taskbroker-activations.sqlite`;
- delivery mode `pull`;
- effective `statsd_addr=127.0.0.1:8126`;
- worker map `sentry -> http://127.0.0.1:50052`.

At startup it received assignments for both `taskworker/0` and `events-subscription-results/0`.

At `17:01:22` it logged Kafka `SESSTMOUT` after roughly 60 seconds without a successful coordinator response, revoked both assignments and shut down the affected consumer actors. No later `taskworker` assignment appeared in the captured logs.

### Kafka group and SQLite before restart

Immediately before the targeted recovery:

```text
taskworker current-offset = 562523
log-end-offset            = 615727
lag                       = 53204
active members            = 0
```

Taskbroker SQLite was empty:

```text
inflight_taskactivations total = 0
application_empty              = 0
application_sentry             = 0
```

This excludes a full local inflight queue and the previously considered legacy `application=''` activation pattern. The backlog remained in Kafka and was not entering the local Taskbroker store.

## Targeted Taskbroker restart experiment

The guarded recovery restarted **only** `ix-sentry-taskbroker-1`. It did not reset Kafka offsets, delete topics, delete SQLite state, restart Kafka or redeploy the Sentry App.

The expected recovery did not occur:

```text
before_members = 0
before_lag     = 53204

after_members = 0
after_lag     ≈54204
```

During the observation window Taskbroker transitioned into `restarting`. A subsequent diagnostic showed:

```text
state    = restarting
restarts = 11
pid      = 0
exit     = 101
```

Every restart failed at metrics initialization:

```text
thread 'main' panicked at src/metrics.rs:18:14
Could not resolve into a socket address
failed to lookup address information: Name or service not known
```

This means the targeted restart did **not** provide a valid test of Kafka consumer rejoin. It first exposed a Taskbroker startup-input drift that must be identified before the Kafka experiment can resume.

### Effective StatsD configuration precedence

The repository `apps/sentry/config/taskbroker.yml` intentionally has **no explicit `statsd_addr`**. Upstream Taskbroker 26.8 defaults to the numeric loopback `127.0.0.1:8126`, which does not require DNS resolution. Taskbroker configuration precedence is:

```text
TASKBROKER_STATSD_ADDR environment
  > /etc/taskbroker/config.yml statsd_addr
  > upstream default 127.0.0.1:8126
```

Upstream Sentry self-hosted also supplies `TASKBROKER_STATSD_ADDR` explicitly. Consequently, the current panic must not be attributed to the repository YAML alone: an effective environment override, a stale live bind mount, or a different live image/configuration may supersede the reviewed file.

The read-only Taskbroker diagnostic now reports:

- image and image ID;
- actual bind source for `/etc/taskbroker/config.yml`;
- explicit YAML `statsd_addr`, if any;
- whether `TASKBROKER_STATSD_ADDR` is present in the live container environment;
- the effective source and value after applying the real precedence;
- whether that address can be parsed/resolved from the Sentry network;
- Taskworker → `taskbroker:50051` reachability.

No new StatsD exporter or destination is introduced by this diagnostic work.

### Taskworker false-green state

While Taskbroker crash-looped, `ix-sentry-sentry-taskworker-1` still reported:

```text
state=running
health=healthy
```

but functional logs repeatedly showed failures such as:

```text
taskworker.fetch_task.failed ... StatusCode.UNAVAILABLE
Socket closed
No route to host
Connection refused
```

The failing peer addresses moved across stale/current Docker IPv4/IPv6 addresses while `taskbroker:50051` remained unavailable. This proves that container health for Taskworker does not validate the Taskbroker RPC dependency.

The recovery contract now requires a direct TCP reachability check from Taskworker to `taskbroker:50051` in addition to Docker state/health.

## Exporter / TrueNAS preflight result

The read-only TrueNAS conflict preflight found:

- native `netdata` service active;
- one configured TrueNAS Reporting Exporter named `netdata`, disabled, type `GRAPHITE`, destination `172.17.0.57:2003`;
- no listener on `8125`, `9125`, `9102` or `9308`;
- no Docker publisher on host ports `9102` or `9308`;
- existing exporters include Redis `:9121` and Pi-hole `:9617`;
- Kafka is present on the shared `intranet` network;
- no conflicting publisher for the proposed future StatsD exposition `:9102` or Kafka exporter `:9308`.

This establishes that future telemetry ports are available, but it does **not** justify changing Taskbroker metrics configuration during the current recovery. Restore Taskbroker functional startup first. StatsD remains deferred; Kafka exporter deployment remains a separate controlled Kafka App lifecycle change.

## Current two-stage recovery model

### Stage A — restore Taskbroker bootability

Before another restart:

1. run `diagnose-sentry-taskbroker.sh` and capture the live image, bind source and effective StatsD source/value;
2. identify whether the effective value comes from `TASKBROKER_STATSD_ADDR`, the live YAML or Taskbroker's default;
3. reconcile only the proven source of the invalid value; do not add a new exporter as a workaround;
4. require Taskbroker to stay `running`, `pid>0`, and stop increasing its restart counter;
5. require `GRPC server listening on 0.0.0.0:50051`;
6. require Taskworker to reach `taskbroker:50051` functionally.

Do not run the end-to-end Sentry smoke while Taskbroker is crash-looping.

### Stage B — resume the original Kafka/rejoin diagnosis

Once Taskbroker is stably running:

1. inspect Kafka group `taskworker`;
2. require an active member to appear;
3. require lag to decrease from the recorded backlog;
4. confirm SQLite begins receiving/processing activations when work exists;
5. require Relay project-config `pending` counts to fall;
6. rerun the synthetic smoke;
7. require `ingest-events`, then `events`, then `sentry.errors_local` to advance.

If Taskbroker is stable and reachable but still has zero Kafka members, the original Kafka coordinator/session-timeout/rejoin hypothesis remains active and becomes the next diagnostic target.

## Guardrails added after the experiment

`diagnose-sentry-taskbroker.sh` now:

- reconstructs the effective StatsD value from environment, live YAML and upstream default;
- reports image/image ID and the actual bind-mounted config source;
- validates address parsing/resolution without mutating the runtime;
- probes Taskworker → `taskbroker:50051` functionally;
- remains read-only.

`recover-sentry-taskbroker.sh` now:

- performs the same effective configuration reconstruction before a targeted restart;
- refuses restart when the effective StatsD address cannot be parsed/resolved from the Sentry network;
- detects `restarting`, `exited` or `dead` immediately and reports logs instead of waiting the full Kafka recovery window;
- verifies Taskworker can actually reach `taskbroker:50051`;
- still refuses an unnecessary restart when Kafka already has an active `taskworker` member;
- still forbids offset reset, topic deletion, SQLite deletion and whole-App redeploy.

`smoke-sentry-event.sh` invokes `scripts/run-diagnostic.sh` through `bash`, so a missing executable bit on a temporary/worktree copy can no longer hide the Sentry diagnostic behind `Permission denied`.

## Acceptance criteria

Sentry ingestion is accepted only when all of the following hold simultaneously:

- TrueNAS Sentry App is `RUNNING`;
- Taskbroker is stably `running`, not restart-looping, and gRPC `:50051` is reachable from Taskworker;
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
sudo bash scripts/truenas/check-observability-exporter-conflicts.sh --check
```

Only after Taskbroker is stable should `smoke-sentry-event.sh` be rerun.

## Related platform findings from the same recovery window

### Suricata

Suricata is no longer an active startup incident:

- TrueNAS App `RUNNING`;
- container `healthy`, zero restarts;
- capture interface `br0`;
- persistent rule file contains 68,674 rules;
- engine loaded approximately 52k rules with zero rule-load failures;
- `eve.json` continues to receive post-redeploy events.

Remaining Suricata work is downstream EVE consumption by CrowdSec/Alloy/central observability and monitoring of rule refresh/kernel-drop health.

### pfSense NetFlow

Fresh NetFlow no longer appears in Cloudflare Network Analytics / Flow Analytics. This is tracked separately in the roadmap and must be diagnosed hop-by-hop from pfSense exporter configuration through any collector/tunnel path to Cloudflare. It is not coupled to the Sentry incident.
