# Sentry Taskbroker / Relay project-config incident — 2026-09-11

Status: **resolved and end-to-end accepted on 2026-09-12**.

This document is the post-mortem for the Sentry 26.8 ingestion incident observed after the controlled TrueNAS reboot. Current priorities remain in `docs/roadmap.md`; supported operator commands remain in `apps/sentry/README.md` and `scripts/truenas/*`.

## Executive summary

The incident was not an HTTP availability failure and not a ClickHouse/Snuba storage failure. It was a failure in Sentry's asynchronous control/task path between Relay, Kafka, Taskbroker and Sentry Taskworker.

The misleading symptom was that several shallow health indicators stayed green:

- the TrueNAS Sentry App was `RUNNING`;
- the Sentry edge returned HTTP 200 and accepted envelopes;
- Kafka broker metadata was reachable;
- Sentry Taskworker could still report Docker `healthy`;
- some Snuba/error consumers remained healthy.

Despite that, newly accepted events did not reach `sentry.errors_local`.

The causal chain was:

```text
Taskbroker Kafka consumer session failure
  -> taskworker consumer group loses its active member
  -> Kafka task backlog grows and Taskbroker SQLite receives no activations
  -> Sentry Taskworker does not execute async project-config work
  -> Relay project config remains pending / deadline exceeded
  -> Relay cannot complete the normal ingest publication path
  -> envelope HTTP 200 does not translate into an ingested event
  -> no row appears in sentry.errors_local
```

A targeted Taskbroker restart then exposed a second, temporary startup/configuration problem: Taskbroker restart-looped with `exit=101` in metrics initialization because an effective StatsD socket address could not be resolved. That restart regression masked the original Kafka rejoin problem until Taskbroker bootability was restored.

The final runtime acceptance on 2026-09-12 proved recovery:

```text
Taskbroker state=running restarts=0 exit=0
Taskbroker effective statsd_addr=127.0.0.1:8126
Taskworker -> taskbroker:50051 reachable
Kafka group taskworker: active member present
Kafka taskworker lag: 1
Taskbroker SQLite: 182 Pending activations, application='sentry'
diagnose-sentry: exit=0 ok=8 failed=0 warnings=0 skipped=0
smoke-sentry-event: exit=0 ok=5 failed=0 warnings=0 skipped=0
```

The final smoke accepted event `61aa04ce88bd49dd85aa69d65f897210` at the Sentry edge and then found exactly one matching row in ClickHouse for `project=1`, proving:

```text
edge -> Relay -> Kafka -> ingest -> Snuba -> ClickHouse
```

## User-visible and operational consequences

For this homelab, the practical consequence was **silent observability data loss/delay at the ingestion pipeline level while the front door still looked healthy**.

### What could be trusted

During the incident, HTTP 200 from the Sentry envelope endpoint proved only that the edge/Relay accepted the request. It did **not** prove that the event had reached Kafka ingest, Snuba or ClickHouse.

Likewise, Docker `healthy` on Sentry Taskworker did not prove that Taskworker could communicate with Taskbroker or that Taskbroker still owned a Kafka partition.

### What was affected

While `taskworker` had no active Kafka consumer member:

- asynchronous Sentry tasks accumulated in Kafka;
- project-config build work required by Relay was not processed normally;
- Relay requests could remain `pending` and reach their deadline;
- accepted error events could fail to progress into the durable Sentry event store;
- alerts, issue creation, dashboards and downstream processing based on those missing events could therefore be delayed or absent;
- Sentry could appear partially healthy from container/process checks while being functionally unable to ingest new errors end to end.

The incident evidence does not prove which individual production events, if any, were permanently lost versus delayed. Therefore the safe statement is that the ingestion path was unreliable during the incident window; HTTP acceptance alone cannot be used as proof of durable ingestion for that period.

### Why Relay showed the symptom

Relay was not the primary failing component. Relay needed project configuration that Sentry builds asynchronously. That asynchronous work travels through the `taskworker` Kafka topic, Taskbroker and Sentry Taskworker. When Taskbroker lost its Kafka consumer membership, project-config jobs stopped progressing. Relay therefore waited for data that was not being produced, reported `pending`, and eventually hit `deadline exceeded`.

Once Taskbroker rejoined Kafka and Taskworker processing resumed, the project-config path recovered without a Relay-specific repair. The final E2E smoke is the strongest evidence of that recovery.

### What was not the root cause

The final recovery shows that these components were not the primary root cause:

- ClickHouse storage;
- Snuba final write path;
- Kafka broker availability itself;
- Relay HTTP edge availability;
- the canonical repository `taskbroker.yml` StatsD configuration.

Once Taskbroker was stable and its Kafka consumer rejoined, Relay project-config processing recovered and the complete event path succeeded without resetting Kafka offsets, deleting topics, deleting SQLite state or redeploying the whole Sentry App.

## Detailed timeline and failure layers

### Layer 1 — original Taskbroker Kafka consumer failure

Taskbroker initially started normally and received partition assignments for both `taskworker/0` and `events-subscription-results/0`.

It later logged Kafka `SESSTMOUT` after roughly the configured 60-second session timeout, revoked its assignments and shut down the affected consumer actors. No successful `taskworker` reassignment was present in the captured failure window.

The Kafka group then showed:

```text
taskworker current-offset = 562523
log-end-offset            = 615727
lag                       = 53204
active members            = 0
```

The lag continued growing during the failed recovery experiment.

Taskbroker SQLite was initially empty:

```text
inflight_taskactivations total = 0
application_sentry             = 0
```

That combination is important: work existed in Kafka, but Taskbroker was not consuming it into its local activation store.

### Layer 2 — Relay project-config starvation

Relay repeatedly reported project-state fetches equivalent to:

```text
error fetching project state <project-key>: deadline exceeded
errors=0
pending≈275
was_pending=true
```

Relay project configuration depends on asynchronous Sentry work. The relevant path is:

```text
Relay
  -> Sentry project-config API
  -> schedule_build_project_config
  -> Kafka topic taskworker
  -> Taskbroker consumer
  -> Sentry Taskworker over gRPC
  -> project-config/cache update
  -> Relay can continue normal ingest publication
```

With the `taskworker` consumer group having zero members, this async path stalled. Relay therefore surfaced the downstream symptom (`pending` / deadline exceeded), but Relay itself was not the primary failure.

### Layer 3 — targeted restart exposed a startup-input regression

A guarded recovery restarted **only** `ix-sentry-taskbroker-1`. It deliberately did not:

- reset Kafka offsets;
- delete Kafka topics;
- delete Taskbroker SQLite;
- restart Kafka;
- redeploy the entire Sentry App.

Instead of testing Kafka rejoin, that restart initially exposed a second failure:

```text
state    = restarting
restarts = 11
pid      = 0
exit     = 101

thread 'main' panicked at src/metrics.rs:18:14
Could not resolve into a socket address
failed to lookup address information: Name or service not known
```

This was a bootability problem, not evidence that Kafka itself was still broken.

The diagnostic was therefore hardened to reconstruct Taskbroker's effective StatsD configuration using the real precedence:

```text
TASKBROKER_STATSD_ADDR environment
  > /etc/taskbroker/config.yml statsd_addr
  > Taskbroker default 127.0.0.1:8126
```

The canonical repository `apps/sentry/config/taskbroker.yml` contains no explicit `statsd_addr`.

At final acceptance the live inputs were:

```text
taskbroker_live_config=/mnt/cpool/compose/nabla-compose/apps/sentry/config/taskbroker.yml
taskbroker_yaml_statsd_addr=not-set
taskbroker_statsd_source=taskbroker-default
taskbroker_effective_statsd_addr=127.0.0.1:8126
taskbroker_statsd_resolution=ok
```

Taskbroker then started cleanly, gRPC listened on `0.0.0.0:50051`, and it immediately received assignments for `events-subscription-results/0` and `taskworker/0`.

## Why the incident was difficult to detect

The incident exposed three false-green classes.

### 1. HTTP acceptance is not durable ingestion

An envelope returning HTTP 200 only proves edge acceptance. It does not prove the event traversed Kafka, ingest consumers, Snuba and ClickHouse.

The required functional health signal is therefore a synthetic event that is later queryable in ClickHouse.

### 2. Container health is not dependency health

Sentry Taskworker stayed Docker `healthy` while logs showed gRPC failures such as:

```text
StatusCode.UNAVAILABLE
Socket closed
No route to host
Connection refused
```

A process-local Docker health check did not validate Taskworker -> Taskbroker RPC.

The contract now includes direct reachability from Taskworker to `taskbroker:50051`.

### 3. A running Taskbroker is not a consuming Taskbroker

Before the restart experiment, Taskbroker itself was running and gRPC was listening, but Kafka group `taskworker` had zero active members and lag was growing.

Therefore process liveness and RPC liveness must be combined with **Kafka consumer-group membership and lag**.

## Recovery evidence

### Taskbroker startup accepted

After the corrected targeted restart:

```text
taskbroker state=running pid>0 restarts=0 exit=0
statsd_addr=127.0.0.1:8126
GRPC server listening on 0.0.0.0:50051
Taskworker -> taskbroker:50051 connected
```

The historical `metrics.rs` panic lines remained in Docker logs, but they were previous restart-loop entries rather than the state of the current process.

### Kafka consumer rejoined

The Kafka group recovered to:

```text
GROUP       TOPIC       PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG  CONSUMER
 taskworker taskworker  0          625511+         625512+         1    rdkafka
```

Later diagnostic output showed the offset continuing to advance while lag remained `1`.

### Taskbroker SQLite became active

After consumer recovery:

```text
total: 182
application_sentry: 182
by_status:
  Pending: 182
```

This is the inverse of the failure state: Taskbroker was again consuming Kafka work into its activation store and Sentry Taskworker was processing tasks.

Taskworker logs also showed normal child recycling after `taskworker.max_task_count_reached (count=10000)`, followed by clean child exits and replacements.

### Full Sentry acceptance

Final diagnostic:

```text
diagnose-sentry: exit=0 ok=8 failed=0 warnings=0 skipped=0
```

Final E2E smoke:

```text
✅ Kafka broker metadata readiness
✅ Sentry edge health
✅ Sentry envelope accepted: event_id=61aa04ce88bd49dd85aa69d65f897210 http=200
✅ Sentry event queryable in ClickHouse: project=1 event_id=61aa04ce88bd49dd85aa69d65f897210 rows=1
✅ Sentry end-to-end smoke passed: edge -> Relay -> Kafka -> ingest -> Snuba -> ClickHouse

smoke-sentry-event: exit=0 ok=5 failed=0 warnings=0 skipped=0
```

This closes the functional incident.

## Root-cause statement

The root operational failure was **loss of the active Taskbroker Kafka consumer for the `taskworker` group after a Kafka session timeout, without automatic functional recovery being detected by the existing health model**.

That caused asynchronous Sentry work, including Relay project-config generation, to stop progressing even though several containers and HTTP surfaces remained healthy.

A targeted restart then temporarily introduced/exposed an independent Taskbroker startup configuration failure in metrics address resolution. That second failure complicated recovery but was not the original cause of the project-config backlog.

The exact lower-level reason for the original Kafka coordinator/session timeout and why Taskbroker did not rejoin automatically remains **upstream/version debt to monitor**; the evidence in this incident is sufficient to identify the failed functional boundary, but not to prove a deeper librdkafka/network implementation cause.

## Permanent guardrails

### `diagnose-sentry-taskbroker.sh`

The diagnostic now:

- reports image and image ID;
- reports the actual bind source for `/etc/taskbroker/config.yml`;
- reconstructs the effective StatsD source/value;
- validates StatsD address parsing/resolution;
- reports container state, restart count, PID and exit code;
- probes Taskworker -> `taskbroker:50051`;
- inspects Kafka `taskworker` topic/group membership and lag;
- inspects Taskbroker SQLite activation counts;
- remains read-only.

### `recover-sentry-taskbroker.sh`

The recovery helper:

- validates effective startup inputs before restart;
- refuses invalid/unresolvable StatsD configuration;
- refuses unnecessary recovery when Kafka already has an active member;
- fast-fails on `restarting`, `exited` or `dead`;
- verifies gRPC reachability after restart;
- requires Kafka membership to return and lag to decrease;
- never resets offsets, deletes topics, deletes SQLite or redeploys the whole Sentry App.

### `smoke-sentry-event.sh`

Sentry is considered functionally healthy only when a synthetic event proves the full path:

```text
edge -> Relay -> Kafka -> ingest -> Snuba -> ClickHouse
```

The smoke invokes diagnostics through `bash` so an executable-bit problem cannot hide the real Sentry state.

## Acceptance criteria after this incident

Sentry ingestion is accepted only when all of the following hold simultaneously:

- TrueNAS Sentry App is `RUNNING`;
- Taskbroker is stably `running`, with no restart growth;
- Taskworker can reach Taskbroker gRPC `:50051`;
- Kafka broker metadata readiness succeeds;
- Kafka group `taskworker` has an active member;
- `taskworker` lag is bounded and moves under load/backlog;
- Taskbroker SQLite receives activations when work exists;
- Relay project-config does not remain indefinitely pending;
- a synthetic envelope is accepted;
- the same event becomes queryable in `sentry.errors_local` / ClickHouse;
- `smoke-sentry-event.sh` exits 0.

Container/process health alone is explicitly insufficient.

## Operator commands

Read-only diagnosis:

```bash
sudo bash scripts/truenas/diagnose-sentry.sh --check
sudo bash scripts/truenas/diagnose-sentry-taskbroker.sh
sudo bash scripts/truenas/check-observability-exporter-conflicts.sh --check
```

Functional acceptance:

```bash
sudo bash scripts/truenas/smoke-sentry-event.sh
```

Use `recover-sentry-taskbroker.sh` only when functional diagnostics prove that recovery is actually required. Do not restart a healthy Taskbroker just to re-test it.

## Deferred work

The incident is closed, but the following are still valid follow-ups:

- monitor Sentry self-hosted 26.8 / Taskbroker Kafka coordinator-session behavior as upstream/version debt;
- alert when Kafka `taskworker` has zero active members or sustained/growing lag;
- alert when Taskworker cannot reach `taskbroker:50051` even if Docker health is green;
- alert on repeated Relay project-config deadline/pending growth;
- keep end-to-end Sentry smoke available as the authoritative functional check;
- keep StatsD exporter deployment deferred until separately justified;
- deploy Kafka exporter only in a controlled Kafka App lifecycle window after the functional Sentry recovery baseline is preserved.

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
