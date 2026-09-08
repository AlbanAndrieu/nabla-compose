# Sentry TrueNAS startup and convergence

Sentry 26.8 is a multi-stage TrueNAS Custom App. A full restart can take much
longer than a small single-container app because migrations, Kafka-topic
creation, long-running consumers and healthcheck grace windows are serialized.

## The TrueNAS 70% plateau

A TrueNAS deployment job can remain around **70%** for several minutes while
all Sentry containers already exist. Treat this as orchestration progress, not
as a Sentry readiness percentage.

The errors-only stack intentionally gives the long-running consumer heartbeat
checks up to **600 seconds** of first-start grace. Sentry web also has its own
startup grace, and NGINX waits for its dependencies.

Expected transient state during this period can include:

- `snuba-migrate` and `sentry-migrate` already exited as successful one-shot jobs;
- `snuba-replacer` and `snuba-subscription-consumer-events` already running;
- one or more dependency-gated services still `starting`;
- TrueNAS aggregate state still `DEPLOYING`.

Do not repeatedly redeploy during this grace period. Each redeploy restarts the
healthcheck clocks and makes the convergence diagnosis harder.

## Apply a changed Compose definition

`app.update` applies the stored Custom App configuration and can initiate the
Docker resource update itself. When changing the include or Compose definition,
run **only** the update first:

```bash
sudo midclt call -j app.update sentry \
'{
  "custom_compose_config": {
    "include": [
      "/mnt/cpool/compose/nabla-compose/apps/sentry/compose.yml"
    ]
  }
}'
```

Do **not** immediately follow a successful `app.update` with `app.redeploy`
unless a second restart is explicitly required. Doing both back-to-back can
start two deployment cycles and reset the long first-start grace window.

## Restart an unchanged definition

When the stored Compose definition is already correct and only a restart is
needed, use:

```bash
sudo midclt call -j app.redeploy sentry
```

Do not call `app.update` first merely to restart the existing configuration.

## Observe without resetting startup

While TrueNAS remains around 70%, use the read-only app status instead of
redeploying:

```bash
sudo midclt call app.query '[["id","=","sentry"]]' |
  jq '.[0] | {id,state,active_workloads}'
```

The important distinction is between expected one-shot exits and unexpected
steady-state failures. `snuba-migrate` and `sentry-migrate` exiting is expected;
a required consumer repeatedly exiting or remaining unhealthy after its grace
period is not.

## Acceptance after the grace window

After approximately 10 minutes, run:

```bash
sudo bash scripts/truenas/diagnose-sentry.sh --check
```

Sentry is not accepted until the diagnostic proves:

1. both one-shot migrations completed successfully;
2. all required Kafka topics exist;
3. steady-state Snuba/Sentry consumers have healthy heartbeats;
4. there are no unexpected `starting`, `unhealthy` or exited steady-state workloads;
5. Sentry edge and Snuba API health are green;
6. TrueNAS aggregate state converges to `RUNNING`;
7. the synthetic SDK event smoke succeeds through edge -> Relay -> Kafka -> Snuba -> ClickHouse.

Do not start the Docling/OpenRAG-LiteLLM activation phase until this Sentry gate
is complete.
