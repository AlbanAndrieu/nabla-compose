# Consommateurs de `docker.sock` et du réseau `intranet` — inventaire (18/11/2026)

Relevé **statique** (checkout `09d6743b` plus le lot en cours, mode
`offline`) préalable au point P1 de [la feuille de route](../roadmap.md) :
réconcilier le proxy Docker Socket versionné avec ses consommateurs avant de
retirer l'ancien réseau `intranet`. Source : tous les fichiers Compose suivis par Git
(`git ls-files '*compose*.yml' '*compose*.yaml'`, hors `.github/` et
`.agents/`), analysés en YAML ; les lignes commentées ne comptent pas. État
runtime `NOT_RUN` : un fichier racine n'est pas forcément déployé.

## Synthèse

- **Socket monté directement (12 services)** : `docker-socket-proxy` (le
  proxy lui-même, TrueNAS et poste de travail), `dockhand`, `openhands`,
  `portracker`, `traefik` et `dnsupdater` (`apps/traefik`), `app`
  (`bootstrap/compose.yaml`, Doco-CD de secours), `dockge` et `portainer`
  (`compose.tool.yml`), `homarr` (`compose.truenas.yml`) et `doco-cd`
  (`docker-compose-albandrieu.yml`, profil désactivé).
- **`dozzle` passe au socket-proxy dans ce même lot** (réseau `docker-proxy`) :
  le tableau montre l'état après ce lot ; à `09d6743b` il montait encore le
  socket.
- **Via le socket-proxy (10 clients)** : `autoxpose`, `dozzle`, `gatus`,
  `alloy` (`apps/grafana`), `homarr`, `pihole-dns-sync`, `watchtower` par le
  réseau `docker-proxy` ; `doco-cd` (`docker-compose-truenas.yml`) et
  `dozzle-agent` (`compose.monitoring.yml`) **par `intranet` seulement** : ils perdent le
  proxy si `intranet` disparaît avant leur bascule sur `docker-proxy`.
  `doco-cd` de `docker-compose.yml` vise le proxy poste de travail.
- **`intranet` (99 services, 55 fichiers dont 49 `apps/*/compose.yml`)** : le
  proxy TrueNAS garde l'alias `docker-socket-proxy` sur `intranet` pour ces
  clients historiques ; ne le retirer qu'après eux.

## Ordre proposé

1. Basculer `doco-cd` TrueNAS et `dozzle-agent` sur `docker-proxy` (sort de
   Doco-CD à décider, voir
   [l'inventaire des secrets](2026-11-18-secrets-consumers-inventory.md)).
2. Remplacer les montages directs restants par le proxy en lecture seule
   (`POST=0` par défaut) ; `traefik`, `openhands` et `portainer`/`dockge`
   demandent une justification ou une écriture explicite.
3. Migrer les services `intranet` vers des réseaux dédiés par dépendance
   (bases, observabilité, ingress), fichier par fichier, puis retirer l'alias
   `intranet` du proxy et le réseau externe.

## Inventaire

| Fichier | Service | Socket monté | Via socket-proxy | `intranet` | Autres réseaux |
| --- | --- | --- | --- | --- | --- |
| `apps/akvorado/compose.yml` | `akvorado-console` | non | non | oui | — |
| `apps/akvorado/compose.yml` | `akvorado-inlet` | non | non | oui | — |
| `apps/akvorado/compose.yml` | `akvorado-orchestrator` | non | non | oui | — |
| `apps/akvorado/compose.yml` | `akvorado-outlet` | non | non | oui | — |
| `apps/autokuma/compose.yml` | `autokuma` | non | non | oui | — |
| `apps/autoxpose/compose.yml` | `autoxpose` | non | oui | oui | `docker-proxy` |
| `apps/bazarr/compose.yml` | `bazarr-exporter` | non | non | oui | `media` |
| `apps/cartography/compose.yml` | `cartography` | non | non | oui | — |
| `apps/clickhouse/compose.yml` | `clickhouse` | non | non | oui | — |
| `apps/cyberbro/compose.yml` | `cyberbro` | non | non | oui | — |
| `apps/cyberbro/compose.yml` | `mcp-cyberbro` | non | non | oui | — |
| `apps/defectdojo/compose.yml` | `defectdojo` | non | non | oui | `traefik_network` |
| `apps/defectdojo/compose.yml` | `defectdojo-celerybeat` | non | non | oui | — |
| `apps/defectdojo/compose.yml` | `defectdojo-celeryworker` | non | non | oui | — |
| `apps/defectdojo/compose.yml` | `defectdojo-initializer` | non | non | oui | — |
| `apps/defectdojo/compose.yml` | `defectdojo-uwsgi` | non | non | oui | — |
| `apps/dependency-track/compose.yml` | `dependency-track` | non | non | oui | — |
| `apps/dependency-track/compose.yml` | `dependency-track-api` | non | non | oui | — |
| `apps/docker-socket-proxy/compose.yml` | `docker-socket-proxy` | oui | oui | oui | `docker-proxy` |
| `apps/dockhand/compose.yml` | `dockhand` | oui | non | non | — |
| `apps/docling/compose.yml` | `docling` | non | non | oui | `traefik_network` |
| `apps/dozzle/compose.yml` | `dozzle` | non | oui | non | `traefik_network`, `docker-proxy` |
| `apps/dsomm/compose.yml` | `dsomm` | non | non | oui | — |
| `apps/dsomm/compose.yml` | `dsomm-baseline` | non | non | oui | — |
| `apps/gatus/compose.yml` | `gatus` | non | oui | oui | `docker-proxy` |
| `apps/grafana/compose.yml` | `alloy` | non | oui | non | `default`, `docker-proxy` |
| `apps/graylog/compose.yml` | `graylog` | non | non | oui | `nabla-security` |
| `apps/hermes/compose.api.yml` | `hermes` | non | non | oui | `hermes` |
| `apps/homarr/compose.yml` | `homarr` | non | oui | oui | `docker-proxy` |
| `apps/homarr/compose.yml` | `homarr-sync` | non | non | oui | — |
| `apps/homeassistant/compose.yml` | `homeassistant` | non | non | oui | `traefik_network` |
| `apps/influxdb/compose.yml` | `influxdb` | non | non | oui | — |
| `apps/joplin/compose.yml` | `joplin` | non | non | oui | `traefik_network` |
| `apps/kafka/compose.yml` | `kafka` | non | non | oui | — |
| `apps/kafka/compose.yml` | `kafka-exporter` | non | non | oui | — |
| `apps/keycloak/compose.yml` | `keycloak` | non | non | oui | — |
| `apps/langflow/compose.yml` | `langflow` | non | non | oui | `traefik_network` |
| `apps/langfuse/compose.yml` | `langfuse-web` | non | non | oui | — |
| `apps/langfuse/compose.yml` | `langfuse-worker` | non | non | oui | — |
| `apps/lidarr/compose.yml` | `lidarr-exporter` | non | non | oui | `media` |
| `apps/minio/compose.yml` | `minio` | non | non | oui | — |
| `apps/mongo/compose.yml` | `mongo` | non | non | oui | — |
| `apps/neo4j/compose.yml` | `neo4j-security` | non | non | oui | — |
| `apps/netbox/compose.yml` | `netbox` | non | non | oui | — |
| `apps/netbox/compose.yml` | `netbox-worker` | non | non | oui | — |
| `apps/opencre/compose.yml` | `opencre` | non | non | oui | — |
| `apps/openhands/compose.yml` | `openhands` | oui | non | oui | — |
| `apps/openrag/compose.yml` | `openrag-backend` | non | non | oui | `traefik_network` |
| `apps/openrag/compose.yml` | `openrag-frontend` | non | non | oui | `traefik_network` |
| `apps/opensearch/compose.yml` | `dashboards` | non | non | oui | — |
| `apps/opensearch/compose.yml` | `opensearch` | non | non | oui | — |
| `apps/pihole/compose.yml` | `pihole` | non | non | oui | — |
| `apps/pihole/compose.yml` | `pihole-dns-sync` | non | oui | oui | `docker-proxy` |
| `apps/pihole/compose.yml` | `pihole-exporter` | non | non | oui | — |
| `apps/plumber/compose.yml` | `plumber` | non | non | oui | — |
| `apps/plumber/compose.yml` | `plumber-api` | non | non | oui | — |
| `apps/plumber/compose.yml` | `plumber-worker` | non | non | oui | — |
| `apps/portracker/compose.yml` | `portracker` | oui | non | non | — |
| `apps/postgresbackup/compose.yml` | `postgresbackup` | non | non | oui | — |
| `apps/prometheus/compose.yml` | `prometheus` | non | non | oui | — |
| `apps/prowlarr/compose.yml` | `prowlarr-exporter` | non | non | oui | `media` |
| `apps/qbittorrent-exporter/compose.yml` | `qbittorrent-exporter` | non | non | oui | `media` |
| `apps/radarr/compose.yml` | `radarr-exporter` | non | non | oui | `media` |
| `apps/redis/compose.yml` | `redis` | non | non | oui | — |
| `apps/redis/compose.yml` | `redis_exporter` | non | non | oui | — |
| `apps/sample/compose.yml` | `fastapi-sample` | non | non | oui | `sample-observer`, `traefik_network` |
| `apps/scanopy/compose.yml` | `scanopy` | non | non | oui | — |
| `apps/scrutiny/compose.yml` | `scrutiny` | non | non | oui | — |
| `apps/scrutiny/compose.yml` | `scrutiny-collector` | non | non | oui | — |
| `apps/sentry-clickhouse/compose.yml` | `sentry-clickhouse` | non | non | oui | — |
| `apps/sentry/compose.yml` | `nginx` | non | non | oui | `sentry`, `traefik_network` |
| `apps/sentry/compose.yml` | `relay` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `sentry-attachments-consumer` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `sentry-events-consumer` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `sentry-migrate` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `sentry-post-process-forwarder-errors` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `sentry-taskscheduler` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `sentry-taskworker` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `sentry-web` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `snuba-api` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `snuba-errors-consumer` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `snuba-group-attributes-consumer` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `snuba-migrate` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `snuba-outcomes-billing-consumer` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `snuba-outcomes-consumer` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `snuba-replacer` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `snuba-subscription-consumer-events` | non | non | oui | `sentry` |
| `apps/sentry/compose.yml` | `taskbroker` | non | non | oui | `sentry` |
| `apps/sonarr/compose.yml` | `sonarr-exporter` | non | non | oui | `media` |
| `apps/squid/compose.yml` | `squid` | non | non | oui | — |
| `apps/traefik/compose.yml` | `dnsupdater` | oui | non | non | — |
| `apps/traefik/compose.yml` | `traefik` | oui | non | non | `traefik_network` |
| `apps/uptimekuma/compose.yml` | `uptimekuma` | non | non | oui | — |
| `apps/watchtower/compose.yml` | `watchtower` | non | oui | oui | `docker-proxy` |
| `bootstrap/compose.yaml` | `app` | oui | non | non | — |
| `compose.clickhouse.yml` | `clickhouse` | non | non | oui | — |
| `compose.monitoring.yml` | `dozzle-agent` | non | oui | oui | — |
| `compose.monitoring.yml` | `github-exporter` | non | non | oui | — |
| `compose.monitoring.yml` | `grafana` | non | non | oui | — |
| `compose.monitoring.yml` | `prometheus` | non | non | oui | — |
| `compose.monitoring.yml` | `scrutiny-collector` | non | non | oui | — |
| `compose.monitoring.yml` | `telegraf` | non | non | oui | — |
| `compose.redis.yml` | `redis-server` | non | non | oui | — |
| `compose.tool.yml` | `dockge` | oui | non | non | — |
| `compose.tool.yml` | `portainer` | oui | non | non | — |
| `compose.truenas.yml` | `homarr` | oui | non | non | — |
| `docker-compose-albandrieu.yml` | `doco-cd` | oui | non | non | — |
| `docker-compose-truenas.yml` | `doco-cd` | non | oui | oui | `default`, `secrets-backend` |
| `docker-compose.override.yml` | `litellm` | non | non | oui | — |
| `docker-compose.yml` | `docker-socket-proxy` | oui | non | oui | — |
| `docker-compose.yml` | `doco-cd` | non | oui | non | — |
