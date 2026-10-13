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


## Prometheus → FastAPI Sample: couverture contractuelle (2026-10-11)

Le dépôt déclare les cibles `gatus` (`172.17.0.24:8085/metrics`),
`fastapi_sample` (`:8091/metrics`), `postgres_exporter` (`:9187`),
`redis_exporter` (`redis_exporter:9121`), `pfsense_exporter` (proxy
`:9945` vers pfSense, 300 s), `crowdsec` (`:6060`) et
`truenas_node` (`:9100`). Ceci est **un état déclaré**, non une preuve
de scrapes réussis. Aucun job `cloudflare_exporter` n'est actuellement
déclaré : ne pas inventer de données Cloudflare ni exposer un token API.

FastAPI Sample (code inspecté dans `nabla/api/platform_metrics.py` et
`nabla/api/topology_telemetry.py`) lit déjà les règles `nabla:core:*`,
`nabla:telemetry:gatus_up`, les métriques de sondes synthétiques Gatus,
le `pfsense_metrics_up`, et les flux Akvorado/cAdvisor. La vue de
plateforme ne consomme pas encore les données de fonctionnement Postgres/Redis,
ni un état de collecte CrowdSec/Cloudflare normalisé. Cette lacune de
**consommation** est différente d'un exporter absent ou cassé.

### Contrat ajouté côté producteur

`apps/prometheus/rules/nabla-core.rules.yml` exporte maintenant :

- `nabla:telemetry:service_exporter_up{job=...}` : état de scrape pour
  Gatus, FastAPI, PostgreSQL, Redis, pfSense, CrowdSec, Cloudflare (lorsqu'un
  job existe) et node-exporter ;
- `nabla:telemetry:postgres_functional_up` basé sur `pg_up` ;
- `nabla:telemetry:redis_functional_up` basé sur `redis_up`.

Ces règles ne produisent aucune série pour un exporter non déployé.
`up=1` prouve seulement que l'endpoint de métriques répond ; les séries
fonctionnelles et les contrôles end-to-end restent indispensables.

### Audit reproductible, non intrusif

```bash
python3 scripts/prometheus/audit-telemetry-coverage.py
# Optionnel, lors du lot de vérifications runtime ultérieur :
python3 scripts/prometheus/audit-telemetry-coverage.py \
  --prometheus-url http://172.17.0.24:9090
```

Le mode live limite les requêtes aux noms de métriques fixés, à des origines
HTTP internes explicitement autorisées et à des délais courts. Il ne lit ni
variables secrètes, ni labels utilisateurs, ni corps HTTP/logs. Il ne modifie
pas Prometheus et ne fait aucun appel pfSense direct.

### Lacunes et chantiers suivants

1. **Gatus :** vérifier l'existence effective de
   `gatus_results_total` avec les labels attendus
   `nabla_service_id` et `type` ; confronter au nombre de moniteurs
   réels pour éviter une série vide malgré `up=1`.
2. **PostgreSQL :** `:9187` est déclaré mais l'exporter était absent
   au dernier diagnostic. Déployer un exporter dédié avec identité SQL
   lecture seule, sans ajouter de dépendance de démarrage à PostgreSQL.
3. **Redis :** vérifier que `redis_exporter:9121` est résolu et
   joignable depuis le réseau du conteneur Prometheus ; relever `redis_up`.
4. **pfSense :** conserver le scrape à 300 s pour éviter le fan-out
   pfREST sur le Netgate. Un exporter indisponible = angle mort, pas
   panne avérée du pare-feu.
5. **Cloudflare :** pas de job dédié constaté. Comparer d'abord avec
   Cloudflare API/Access et les métriques déjà présentes, puis envisager
   un collecteur minimisé à permissions et cardinalité bornées. Aucun
   token Cloudflare ne doit être rendu public dans /metrics.
6. **FastAPI Sample :** intégrer ultérieurement ces trois règles et
   les catégories `not_declared`/`no_up_series`/`scrape_down`/
   `metric_present` comme preuves d'observabilité, **sans** convertir
   une absence de télémétrie en DOWN d'un service. Les changements
   consommateurs relèvent du dépôt `fastapi-sample`.
7. **cAdvisor :** `topology_telemetry.py` l'utilise mais sa collecte
   demeure à confirmer ; ne pas inventer des métriques CPU/RAM conteneur.

### Multi-target Prometheus scrape interpretation

The read-only coverage audit now treats each job as a **set of targets**,
not a single Boolean. It reports `targets_up` and `targets_total`
when Prometheus supplies valid `up` samples. If a job has both reachable
and unreachable targets, the state is `scrape_partial` rather than
`scrape_up`; malformed or nonfinite samples give `query_unavailable`.
An empty vector is `no_up_series`, not evidence of health.

An exporter metric may exist while only some instances remain reachable:
`metric_present=true` does not override `scrape_partial`. These distinctions
matter when FastAPI Sample displays missing telemetry independently of service
status. No service is declared DOWN solely because of a scrape failure.



### Internal Prometheus query boundary (2026-10-12)

`scripts/prometheus/audit-telemetry-coverage.py` is an opt-in, read-only
diagnostic, not an Internet-facing general PromQL client. Its approved
origin is an explicit loopback/TrueNAS LAN HTTP endpoint; it disables
ambient HTTP proxy settings and **does not follow redirects**. This
prevents an internal query expression being forwarded to an untrusted
endpoint via a proxy or a 30x response. Responses are capped at 1 MiB,
must contain a Prometheus instant vector, and are aggregated without
printing the returned labels or time series. A redirect, non-vector
payload or connection failure means `query_unavailable`, not service DOWN.
