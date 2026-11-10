# Préparation à la production des Apps TrueNAS

> Fichier généré par `scripts/truenas/audit-master-readiness.py --write` à partir
> du dépôt seul (aucun appel réseau). Ne pas éditer à la main. Opérations par App :
> [`scripts/truenas/app-ops.sh`](../scripts/truenas/app-ops.sh) ; procédure :
> [runbook](runbooks/production-app-operations.md).

Apps : 90 ; actives : 57 ; planifiées : 29.

## Écarts par type

| Écart | Apps |
| --- | --- |
| `NO_AVAILABILITY_PROBE` | 29 |
| `NO_DEPLOY_PATH` | 21 |
| `SECRETS_LEGACY_PATH` | 19 |
| `SECRETS_NOT_IN_MANIFEST` | 1 |
| `SERVICE_WITHOUT_HEALTHCHECK` | 48 |

## Matrice

| App | État | Déploiement | Datasets (snapshot) | Secrets | Sonde | Métriques | Sauvegarde BD | Diagnostic | Config as code | Écarts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `2fauth` | active | ❌ | — | n/a | ❌ | — | — | générique | — | `NO_AVAILABILITY_PROBE`, `NO_DEPLOY_PATH` |
| `akvorado` | planned | ❌ | `cpool/akvorado` (none (noSnapshot)) | legacy | ✅ | — | — | diagnose-akvorado-config.sh<br>diagnose-akvorado-flow.py | apps/akvorado/config/ | `SECRETS_LEGACY_PATH`, `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `apisix` | planned | ❌ | — | n/a | — | — | — | générique | apps/apisix/config/ | `NO_DEPLOY_PATH` |
| `autokuma` | active | custom-apps.yml | `cpool/autokuma` (app-state) | manifest | ❌ | — | — | générique | bootstrap-autokuma-token.sh<br>render-autokuma-monitors.py | `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `autoxpose` | active | custom-apps.yml | `cpool/autoxpose` (app-state) | n/a | ✅ | — | — | générique | — | ✅ |
| `bazarr` | planned | deploy-media-stack.sh | `cpool/bazarr` (app-state)<br>`cpool/media` (none (noSnapshot)) | manifest | ✅ | bazarr-exporter | — | générique | — | ✅ |
| `bichon` | active | custom-apps.yml | `cpool/bichon` (app-state) | legacy | ✅ | — | — | générique | — | `SECRETS_LEGACY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `bitcoind` | active | deploy-bitcoind.sh | `cpool/bitcoind` (resync-shortcut) | n/a | ❌ | — | — | générique | — | `NO_AVAILABILITY_PROBE` |
| `cartography` | active | custom-apps.yml | — | manifest | ❌ | — | — | générique | — | `NO_AVAILABILITY_PROBE` |
| `clickhouse` | active | custom-apps.yml | `cpool/clickhouse` (databases)<br>`cpool/logs` (none (noSnapshot)) | legacy | ❌ | clickhouse | — | diagnose-sentry-runtime-clickhouse-credential.sh | apps/clickhouse/config/<br>reconcile-sentry-runtime-clickhouse-credential.sh | `SECRETS_LEGACY_PATH`, `NO_AVAILABILITY_PROBE` |
| `code` | active | custom-apps.yml | `cpool/code` (app-state) | manifest | ✅ | — | — | générique | — | ✅ |
| `crowdsec` | planned | deploy-crowdsec.sh | — | manifest | — | crowdsec | — | diagnose-crowdsec-cutover.sh | provision-crowdsec-pfsense-bouncer.sh | ✅ |
| `cyberbro` | active | custom-apps.yml | `cpool/cyberbro` (app-state) | manifest | ✅ | — | — | diagnose-cyberbro.sh | bootstrap-cyberbro-env.sh | `SERVICE_WITHOUT_HEALTHCHECK` |
| `ddns-updater` | active | custom-apps.yml | `cpool/ddns-updater` (app-state) | n/a | ✅ | — | — | générique | — | `SERVICE_WITHOUT_HEALTHCHECK` |
| `defectdojo` | active | custom-apps.yml | `cpool/defectdojo` (app-state) | manifest | ✅ | — | ✅ defectdojo | diagnose-defectdojo-deploying.py<br>diagnose-defectdojo-https-route.py<br>diagnose-defectdojo-memory-pressure.py<br>diagnose-defectdojo-postgres-waits.py<br>diagnose-defectdojo.sh | reconcile-defectdojo-admin-password.py<br>reconcile-defectdojo-artifact-cron.py | `SERVICE_WITHOUT_HEALTHCHECK` |
| `dependency-track` | planned | ❌ | `cpool/dependency-track` (app-state) | manifest | ✅ | dependency-track-api | ✅ dependencytrack | générique | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `docker-socket-proxy` | active | deploy-docker-socket-proxy.sh | — | n/a | ❌ | — | — | générique | — | `NO_AVAILABILITY_PROBE` |
| `dockhand` | active | custom-apps.yml | `cpool/dockhand` (app-state) | n/a | ✅ | — | — | générique | — | `SERVICE_WITHOUT_HEALTHCHECK` |
| `docling` | active | custom-apps.yml | — | n/a | ✅ | docling | — | diagnose-docling-readiness.py | — | ✅ |
| `dozzle` | active | custom-apps.yml | `cpool/dozzle` (app-state) | legacy | ✅ | — | — | générique | — | `SECRETS_LEGACY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `drawio` | active | custom-apps.yml | — | n/a | ✅ | — | — | générique | — | ✅ |
| `dsomm` | planned | deploy-dsomm.sh | `cpool/dsomm` (app-state) | manifest | ✅ | — | — | diagnose-dsomm-assessment.sh | apps/dsomm/config/ | ✅ |
| `garage` | active | custom-apps.yml | `cpool/garage` (backup-targets) | legacy | ❌ | — | — | générique | terraform/garage | `SECRETS_LEGACY_PATH`, `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `gatus` | active | custom-apps.yml | `cpool/gatus` (app-state) | n/a | ❌ | gatus | — | diagnose-gatus-monitors.py<br>diagnose-gatus.sh | apps/gatus/config/<br>reconcile-gatus-catalog.py | `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `grafana` | active | custom-apps.yml | `cpool/alloy` (none (noSnapshot))<br>`cpool/grafana` (app-state)<br>`cpool/loki` (none (noSnapshot))<br>`cpool/mimir` (none (noSnapshot))<br>`cpool/tempo` (none (noSnapshot)) | n/a | ✅ | alloy, grafana, loki, mimir, tempo | — | générique | apps/grafana/config/ | `SERVICE_WITHOUT_HEALTHCHECK` |
| `graylog` | disabled | ❌ | `cpool/graylog` (databases) | legacy | — | — | — | générique | — | `SECRETS_LEGACY_PATH`, `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `haproxy-exporter` | planned | ❌ | — | n/a | — | haproxy-exporter | — | générique | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `hermes` | planned | ❌ | `cpool/compose` (none (noSnapshot))<br>`cpool/hermes` (app-state) | manifest | — | — | — | diagnose-hermes-agent.sh | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `homarr` | active | custom-apps.yml | `cpool/homarr` (app-state) | manifest | ❌ | — | — | générique | apps/homarr/config/ | `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `homeassistant` | active | ❌ | `cpool/ha` (app-state) | n/a | ✅ | — | — | diagnose-homeassistant-overkiz.sh<br>diagnose-homeassistant-usb.sh<br>diagnose-homeassistant.sh | bootstrap-homeassistant-postgres.sh | `NO_DEPLOY_PATH` |
| `influxdb` | active | custom-apps.yml | `cpool/influxdb` (none (noSnapshot)) | n/a | ❌ | influxdb | — | diagnose-influxdb.sh | bootstrap-scrutiny-influxdb.sh | `NO_AVAILABILITY_PROBE` |
| `jellyfin` | planned | deploy-media-stack.sh | `cpool/jellyfin` (app-state)<br>`cpool/jellyfin-cache` (none (noSnapshot))<br>`cpool/media` (none (noSnapshot)) | n/a | ✅ | jellyfin | — | générique | config/media/settings.yml | ✅ |
| `joplin` | planned | deploy-joplin.sh | — | manifest | ✅ | — | ✅ joplin | générique | bootstrap-joplin-postgres.sh | ✅ |
| `kafka` | active | custom-apps.yml | `cpool/kafka` (none (noSnapshot)) | n/a | ✅ | kafka-exporter | — | générique | — | `SERVICE_WITHOUT_HEALTHCHECK` |
| `keycloak` | active | custom-apps.yml | `cpool/secrets` (critical) | legacy | ✅ | keycloak | ✅ keycloak | générique | apply-keycloak-config.sh<br>apps/keycloak/config/ | `SECRETS_LEGACY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `langflow` | active | custom-apps.yml | — | legacy | ❌ | — | — | générique | bootstrap-openrag-langflow-key.sh | `SECRETS_LEGACY_PATH`, `NO_AVAILABILITY_PROBE` |
| `langfuse` | active | custom-apps.yml | — | manifest | ❌ | — | ✅ langfuse | générique | — | `NO_AVAILABILITY_PROBE` |
| `languagetool` | active | custom-apps.yml | `cpool/languagetool` (none (noSnapshot)) | n/a | ✅ | — | — | générique | — | ✅ |
| `lidarr` | planned | deploy-media-stack.sh | `cpool/lidarr` (app-state)<br>`cpool/media` (none (noSnapshot)) | manifest | ✅ | lidarr-exporter | — | générique | config/media/settings.yml | ✅ |
| `litellm` | active | custom-apps.yml | — | manifest | ❌ | litellm | — | diagnose-litellm-dashboard-auth.py<br>diagnose-workstation-litellm-upstream-auth.py | provision-openclaw-litellm-keys.py | `NO_AVAILABILITY_PROBE` |
| `media-acquisition` | planned | deploy-media-stack.sh | `cpool/media` (none (noSnapshot))<br>`cpool/qbittorrent` (app-state) | manifest | ✅ | qbittorrent | — | générique | config/media/settings.yml<br>terraform/media | ✅ |
| `minio` | active | custom-apps.yml | `cpool/minio` (app-state) | n/a | ❌ | — | — | générique | — | `NO_AVAILABILITY_PROBE` |
| `mongo` | active | custom-apps.yml | `cpool/mongo` (databases) | legacy | ❌ | — | — | générique | — | `SECRETS_LEGACY_PATH`, `NO_AVAILABILITY_PROBE` |
| `n8n` | planned | native App | — | n/a | — | n8n | ✅ n8n | générique | — | ✅ |
| `neo4j` | planned | ❌ | `cpool/neo4j` (databases) | manifest | ✅ | — | — | générique | — | `NO_DEPLOY_PATH` |
| `netbox` | planned | ❌ | `cpool/netbox` (app-state) | manifest | ✅ | netbox | ✅ netbox | générique | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `nexus` | active | custom-apps.yml | `cpool/nexus3` (recreatable) | legacy | ✅ | — | — | générique | terraform/nexus | `SECRETS_LEGACY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `nginx` | active | custom-apps.yml | `cpool/nginx` (app-state) | n/a | ✅ | — | — | diagnose-nginx-proxy-manager.sh | — | `SERVICE_WITHOUT_HEALTHCHECK` |
| `nginx-proxy-manager` | disabled | ❌ | `cpool/npm` (app-state) | n/a | ✅ | — | — | diagnose-nginx-proxy-manager.sh | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `npmplus` | planned | ❌ | `cpool/npmplus` (app-state) | n/a | ✅ | — | — | générique | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `ntopng` | active | custom-apps.yml | `cpool/compose` (none (noSnapshot))<br>`cpool/ntopng` (none (noSnapshot)) | n/a | ❌ | — | — | générique | — | `NO_AVAILABILITY_PROBE` |
| `obsidian` | active | custom-apps.yml | `cpool/obsidian` (app-state) | n/a | ❌ | — | — | générique | — | `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `ollama` | active | custom-apps.yml | `cpool/model` (none (noSnapshot))<br>`cpool/ollama` (none (noSnapshot)) | legacy | ❌ | ollama | — | générique | — | `SECRETS_LEGACY_PATH`, `NO_AVAILABILITY_PROBE` |
| `opconnect` | disabled | ❌ | `cpool/opconnect` (app-state) | n/a | ✅ | — | — | générique | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `openclaw` | active | ❌ | — | n/a | ❌ | — | — | générique | provision-openclaw-litellm-keys.py | `NO_AVAILABILITY_PROBE`, `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `opencre` | planned | deploy-opencre.sh | `cpool/opencre` (app-state) | n/a | ✅ | — | — | générique | — | ✅ |
| `openhands` | active | custom-apps.yml | `cpool/openhands` (app-state) | n/a | ✅ | — | — | générique | — | `SERVICE_WITHOUT_HEALTHCHECK` |
| `openrag` | active | custom-apps.yml | — | manifest | ❌ | — | — | diagnose-openrag-dependencies.sh<br>diagnose-openrag-startup.sh | apps/openrag/config/<br>bootstrap-openrag-langflow-key.sh<br>reconcile-openrag-opensearch-secret.sh | `NO_AVAILABILITY_PROBE` |
| `opensearch` | active | custom-apps.yml | `cpool/opensearch` (databases)<br>`cpool/opensearch-security` (databases) | legacy | ❌ | opensearch, opensearch-security | — | générique | reconcile-openrag-opensearch-secret.sh | `SECRETS_LEGACY_PATH`, `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `opensearch-exporter` | planned | ❌ | — | n/a | — | opensearch-exporter, opensearch-security-exporter | — | générique | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `openwebui` | active | custom-apps.yml | `cpool/openwebui` (app-state) | n/a | ❌ | — | — | diagnose-openwebui-backup-pra.sh | — | `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `pihole` | active | custom-apps.yml | `cpool/pihole` (app-state)<br>`cpool/traefik` (app-state) | legacy | ✅ | — | — | générique | — | `SECRETS_LEGACY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `plumber` | planned | ❌ | `cpool/secrets` (critical) | manifest | ✅ | — | ✅ jobs | générique | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `portracker` | active | native App | `cpool/portracker` (app-state) | n/a | ✅ | — | — | générique | — | `SERVICE_WITHOUT_HEALTHCHECK` |
| `postgres` | active | native App | — | legacy | ✅ | postgres_exporter | — | diagnose-defectdojo-postgres-waits.py<br>diagnose-postgres-exporter.sh | bootstrap-app-postgres.sh<br>bootstrap-homeassistant-postgres.sh<br>bootstrap-joplin-postgres.sh<br>bootstrap-postgresbackup-role.sh<br>bootstrap-scanopy-postgres.sh<br>bootstrap-security-tooling-postgres.sh<br>reconcile-postgresbackup-cron.py | `SECRETS_LEGACY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `postgresbackup` | active | ❌ | `cpool/backup` (backup-targets) | manifest | ❌ | — | — | générique | bootstrap-postgresbackup-role.sh<br>reconcile-postgresbackup-cron.py | `NO_AVAILABILITY_PROBE`, `NO_DEPLOY_PATH` |
| `prometheus` | active | custom-apps.yml | `cpool/prometheus` (none (noSnapshot)) | n/a | ✅ | alertmanager, pfsense-exporter, prometheus | — | diagnose-prometheus-targets.sh | — | `SERVICE_WITHOUT_HEALTHCHECK` |
| `prowlarr` | planned | deploy-media-stack.sh | `cpool/prowlarr` (app-state) | manifest | ✅ | prowlarr-exporter | — | générique | config/media/settings.yml<br>terraform/media | ✅ |
| `pyroscope` | active | custom-apps.yml | `cpool/pyroscope` (none (noSnapshot)) | n/a | ✅ | pyroscope | — | diagnose-pyroscope.sh | — | `SERVICE_WITHOUT_HEALTHCHECK` |
| `qbittorrent-exporter` | planned | deploy-media-stack.sh | — | manifest | — | qbittorrent-exporter | — | générique | — | ✅ |
| `radarr` | planned | deploy-media-stack.sh | `cpool/media` (none (noSnapshot))<br>`cpool/radarr` (app-state) | manifest | ✅ | radarr-exporter | — | générique | terraform/media | ✅ |
| `reactive` | untracked | ❌ | — | legacy | — | — | — | générique | — | `SECRETS_LEGACY_PATH`, `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `recyclarr` | planned | deploy-media-stack.sh | `cpool/recyclarr` (app-state) | manifest | — | — | — | générique | apps/recyclarr/config/ | ✅ |
| `redis` | active | custom-apps.yml | `cpool/redis` (none (noSnapshot)) | n/a | ❌ | redis_exporter | — | générique | — | `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `sample` | active | custom-apps.yml | `cpool/secrets` (critical) | legacy | ✅ | — | ✅ fastapisample | diagnose-fastapi-sample.sh | — | `SECRETS_LEGACY_PATH` |
| `scanopy` | planned | deploy-scanopy.sh | `cpool/scanopy` (app-state) | manifest | ✅ | — | ✅ scanopy | générique | bootstrap-scanopy-postgres.sh | `SERVICE_WITHOUT_HEALTHCHECK` |
| `scorecard` | active | custom-apps.yml | — | manifest | ❌ | — | — | générique | — | `NO_AVAILABILITY_PROBE` |
| `scrutiny` | active | custom-apps.yml | `cpool/scrutiny` (app-state) | manifest | ✅ | — | — | diagnose-scrutiny.sh | bootstrap-scrutiny-influxdb.sh | `SERVICE_WITHOUT_HEALTHCHECK` |
| `seerr` | planned | deploy-media-stack.sh | `cpool/seerr` (app-state) | n/a | ✅ | — | — | générique | — | ✅ |
| `sentry` | active | custom-apps.yml | `cpool/sentry` (app-state) | unmanaged | ✅ | — | ✅ sentry | diagnose-sentry-consumers.sh<br>diagnose-sentry-migrator-credential.sh<br>diagnose-sentry-runtime-clickhouse-credential.sh<br>diagnose-sentry-taskbroker.sh<br>diagnose-sentry.sh | apps/sentry/config/<br>reconcile-sentry-migrator-credential.sh<br>reconcile-sentry-runtime-clickhouse-credential.sh<br>reconcile-sentry-system-secret.sh | `SECRETS_NOT_IN_MANIFEST`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `sentry-clickhouse` | active | custom-apps.yml | `cpool/sentry-clickhouse` (databases) | legacy | ✅ | — | — | générique | — | `SECRETS_LEGACY_PATH` |
| `sonarqube` | planned | ❌ | — | n/a | — | — | ✅ sonarqube | générique | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `sonarr` | planned | deploy-media-stack.sh | `cpool/media` (none (noSnapshot))<br>`cpool/sonarr` (app-state) | manifest | ✅ | sonarr-exporter | — | générique | terraform/media | ✅ |
| `squid` | active | custom-apps.yml | — | n/a | ✅ | — | — | générique | — | `SERVICE_WITHOUT_HEALTHCHECK` |
| `suricata` | active | custom-apps.yml | `cpool/suricata` (none (noSnapshot)) | n/a | ❌ | — | — | générique | — | `NO_AVAILABILITY_PROBE` |
| `sybase-exporter` | planned | ❌ | — | n/a | — | sybase-exporter | — | générique | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `traefik` | active | custom-apps.yml | `cpool/traefik` (app-state) | legacy | ❌ | — | — | générique | — | `SECRETS_LEGACY_PATH`, `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `vaultwarden` | active | custom-apps.yml | `cpool/vaultwarden` (critical) | n/a | ❌ | — | — | diagnose-vaultwarden-cli.sh | — | `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `watchtower` | planned | ❌ | — | n/a | — | — | — | générique | — | `NO_DEPLOY_PATH`, `SERVICE_WITHOUT_HEALTHCHECK` |
| `wazuh` | active | custom-apps.yml | `cpool/wazuh` (databases) | legacy | ❌ | — | — | diagnose-wazuh.sh | apps/wazuh/config/<br>bootstrap-wazuh.sh | `SECRETS_LEGACY_PATH`, `NO_AVAILABILITY_PROBE`, `SERVICE_WITHOUT_HEALTHCHECK` |
