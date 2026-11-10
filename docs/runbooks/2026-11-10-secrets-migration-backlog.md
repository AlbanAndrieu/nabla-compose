# Migration des secrets runtime vers Vaultwarden — reste à faire (10/11/2026)

Inventaire **sans valeur** du 10/11/2026 : noms de clés des fichiers
`/mnt/cpool/secrets/runtime/<service>/` (TrueNAS, hors `*.bak*`, `*.crt`,
`*.pem`), croisés avec [`config/secrets/manifest.json`](../../config/secrets/manifest.json)
et la présence des items `nabla/prod/<app>` du dossier Vaultwarden `TrueNAS`
(`scripts/secrets/inventory_vaultwarden.py --json`). Les fichiers `.env`
portent des réglages non secrets et ne sont pas comptés.

Le manifeste fait foi : déclarer les clés avant tout import, puis importer
(`scripts/secrets/import_env_to_bitwarden.py --app <app>`, aperçu puis
`--apply` avec accord), et vérifier la parité
(`scripts/secrets/audit-vaultwarden-migration.py --verify --app <app>`).
Nouveaux noms : sans tiret (`postgresbackup`, `fastapisample`).

Bilan : 6 faits, 14 à importer,
15 à déclarer puis importer, 32 à créer au déploiement.

## 1. Faits (item présent)

| Service | Item | Clés runtime hors manifeste |
| --- | --- | --- |
| `cyberbro` | `nabla/prod/cyberbro` | — |
| `defectdojo` | `nabla/prod/defectdojo` | — |
| `fastapisample` | `nabla/prod/fastapisample` | `AZURE_OPENAI_DEFAULT_MODEL`, `AZURE_OPENAI_INSTANCE__A__API_ALIAS`, `AZURE_OPENAI_INSTANCE__A__API_KEY`, `AZURE_OPENAI_INSTANCE__A__AVAILABLE_MODELS`, `AZURE_OPENAI_INSTANCE__A__URL`, `AZURE_OPENAI_INSTANCE__B__API_ALIAS`, `AZURE_OPENAI_INSTANCE__B__API_KEY`, `AZURE_OPENAI_INSTANCE__B__AVAILABLE_MODELS`, `AZURE_OPENAI_INSTANCE__B__URL`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`, `CF_SERVICE_TOKEN_CLIENT_ID`, `CF_SERVICE_TOKEN_CLIENT_SECRET`, `CLOUDFLARE_API_TOKEN`, `DD_API_KEY`, `DIAGNOSTICS_ACCESS_KEY`, `KEYCLOAK_CLIENT_SECRET`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LITELLM_API_KEY`, `MAIL_PASSWORD`, `METRICS_SCRAPE_KEY`, `MIGRATION_DB_URL`, `OAUTH_TOKEN_SECRET`, `OPENAI_API_KEY`, `OPENAI_API_VERSION`, `OPENRAG_API_KEY`, `OVH_APPLICATION_KEY`, `OVH_APPLICATION_NAME`, `OVH_APPLICATION_SECRET`, `OVH_CONSUMER_KEY`, `PFSENSE_POSTURE_API_KEY`, `PFSENSE_SECURITY_API_KEY`, `POSTGRES_PASSWORD`, `REDIS_AUTH`, `STATSIG_API_KEY`, `SUPABASE_DATABASE_URL`, `SUPABASE_KEY`, `SUPABASE_PASSWORD`, `SUPABASE_PROJECT_REF`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_TOKEN`, `SUPABASE_URL`, `TRUENAS_API_KEY`, `TRUENAS_INFRA_API_KEY`, `UNLEASH_API_TOKEN`, `UNLEASH_API_URL`, `UNLEASH_APP_NAME`, `UNLEASH_INSTANCE_ID`, `VERCEL_OIDC_TOKEN` |
| `langfuse` | `nabla/prod/langfuse` | `CLICKHOUSE_VERSION`, `DB_URL`, `DIRECT_URL`, `LANGFUSE_BASE_URL`, `LANGFUSE_INIT_ORG_ID`, `LANGFUSE_INIT_ORG_NAME`, `LANGFUSE_INIT_PROJECT_ID`, `LANGFUSE_INIT_PROJECT_NAME`, `LANGFUSE_INIT_USER_EMAIL`, `LANGFUSE_INIT_USER_NAME`, `LANGFUSE_INIT_USER_PASSWORD`, `LANGFUSE_S3_BATCH_EXPORT_ACCESS_KEY_ID`, `LANGFUSE_S3_BATCH_EXPORT_ENABLED`, `LANGFUSE_S3_BATCH_EXPORT_REGION`, `LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY`, `LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID`, `LANGFUSE_S3_EVENT_UPLOAD_BUCKET`, `LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT`, `LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE`, `LANGFUSE_S3_EVENT_UPLOAD_REGION`, `LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY`, `LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID`, `LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY`, `MINIO_ROOT_PASSWORD`, `MINIO_ROOT_USER`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_URL` |
| `n8n` | `nabla/prod/n8n` | — |
| `postgresbackup` | `nabla/prod/postgresbackup` | — |

`fastapisample` : seul `POSTGRES_PASSWORD` est dans l'item ; les autres clés
restent à déclarer. `postgresbackup` : renommé depuis `postgres-backup`.

## 2. À importer (déclarés, fichier runtime présent, item absent)

À trier avant import : des clés de `.env.compose` sont des réglages non secrets
(`*_VERSION`, `*_HOST`, `*_PORT`, `MINIO_ROOT_USER`, `BRAVE_PLAN`…) à garder
hors Vaultwarden. Pour `dozzle` et `scanopy`, aucune clé `KEY=value` n'a été
lue dans `.env.secrets` : fichier vide ou format à vérifier.

| Service | Fichiers | Clés runtime hors manifeste | Déclarées absentes du runtime |
| --- | --- | --- | --- |
| `akvorado` | `.env.secrets` | `AKVORADO_CLICKHOUSE_PASSWORD` | — |
| `code` | `.env`, `.env.secrets` | `CODE_PASSWORD` | `PASSWORD` |
| `crowdsec` | `.env.secrets` | — | — |
| `dozzle` | `.env`, `.env.secrets` | — | `DOZZLE_ADMIN_PASSWORD_BCRYPTED` |
| `hermes` | `.env` | — | `DISCORD_ALLOWED_USERS`, `DISCORD_BOT_TOKEN`, `HERMES_LITELLM_API_KEY`, `TELEGRAM_ALLOWED_USERS`, `TELEGRAM_BOT_TOKEN` |
| `homarr` | `.env.secrets` | `HOMARR_API_TOKEN`, `HOMARR_ENCRYPTION_KEY` | — |
| `keycloak` | `.env.secrets` | — | — |
| `litellm` | `.env.secrets` | `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `AZURE_API_BASE`, `AZURE_API_KEY`, `AZURE_API_VERSION`, `DATABASE_URL`, `DEFAULT_MODELS`, `GEMINI_API_KEY`, `LANGFUSE_INIT_PROJECT_PUBLIC_KEY`, `LANGFUSE_INIT_PROJECT_SECRET_KEY`, `LITELLM_API_KEY`, `LITELLM_MODEL`, `LITELLM_N8N_API_KEY`, `LITELLM_REACTIVE_API_KEY`, `LITELLM_TRUENAS_MASTER_KEY`, `OPENAI_BASE_URL`, `STORE_MODEL_IN_DB`, `V1__AZURE_OPENAI_INSTANCE__A__API_KEY`, `V1__AZURE_OPENAI_INSTANCE__A__URL`, `V1__AZURE_OPENAI_INSTANCE__B__API_KEY`, `V1__AZURE_OPENAI_INSTANCE__B__URL`, `V2__AZURE__SUB__C__A__API_KEY`, `V2__AZURE__SUB__C__B__API_KEY`, `V2__AZURE__SUB__C__C__API_KEY`, `V2__AZURE__SUB__C__D__API_KEY`, `V2__AZURE__SUB__C__E__API_KEY`, `V2__AZURE__SUB__C__F__API_KEY`, `V2__AZURE__SUB__C__G__API_KEY`, `V2__AZURE__SUB__C__H__API_KEY`, `V2__AZURE__SUB__C__I__API_KEY`, `V2__AZURE__SUB__C__J__API_KEY`, `V2__AZURE__SUB__C__K__API_KEY`, `V2__AZURE__SUB__C__L__API_KEY`, `V2__AZURE__SUB__E__A__API_KEY`, `V2__AZURE__SUB__E__B__API_KEY`, `V2__AZURE__SUB__E__C__API_KEY`, `V2__AZURE__SUB__E__D__API_KEY`, `V2__AZURE__SUB__E__E__API_KEY`, `V2__AZURE__SUB__E__F__API_KEY`, `V2__AZURE__SUB__E__G__API_KEY`, `V2__AZURE__SUB__E__H__API_KEY`, `V2__AZURE__SUB__E__I__API_KEY`, `V2__AZURE__SUB__E__J__API_KEY`, `V2__AZURE__SUB__E__K__API_KEY`, `V2__AZURE__SUB__E__L__API_KEY` | `LITELLM_OPENCLAW_CODER_API_KEY` |
| `minio` | `.env.compose` | `MINIO_ROOT_USER` | — |
| `openrag` | `.env.secrets` | `LANGFLOW_KEY` | — |
| `opensearch` | `.env` | — | `OPENSEARCH_PASSWORD` |
| `openwebui` | `.env.compose` | `LANGFUSE_INIT_PROJECT_PUBLIC_KEY`, `LANGFUSE_INIT_PROJECT_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LITELLM_MASTER_KEY`, `OPEN_WEBUI_API_KEY`, `OPEN_WEBUI_EMAIL`, `OPEN_WEBUI_PASSWORD`, `OPEN_WEBUI_PORT`, `OPEN_WEBUI_URL`, `PIPELINES_API_KEY`, `WEBUI_ADMIN_EMAIL`, `WEBUI_ADMIN_NAME` | — |
| `scanopy` | `.env.secrets` | — | `POSTGRES_PASSWORD`, `SCANOPY_DATABASE_URL` |
| `scrutiny` | `.env.secrets` | — | — |

## 3. À déclarer dans le manifeste, puis importer

| Service | Fichiers | Clés runtime |
| --- | --- | --- |
| `bichon` | `.env.secrets` | `BICHON_ENCRYPTION_PASSWORD` |
| `clickhouse` | `.env.compose`, `.env.secrets` | `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_VERSION` |
| `garage` | `.env.compose`, `.env.secrets` | `AUTH_USER_PASS`, `GARAGE_ADMIN_TOKEN`, `GARAGE_RPC_SECRET`, `GARAGE_WEBUI_ADMIN_PASS` |
| `graylog` | `.env.secrets` | `GRAYLOG_MONGODB_URI`, `GRAYLOG_PASSWORD_SECRET`, `GRAYLOG_ROOT_PASSWORD_SHA2` |
| `langflow` | `.env.secrets` | `LANGFLOW_SUPERUSER_PASSWORD` |
| `mongo` | `.env.secrets` | `MONGO_INITDB_ROOT_PASSWORD`, `MONGO_INITDB_ROOT_USERNAME` |
| `nexus` | `.env`, `.env.secrets` | `SMTP_PASSWORD` |
| `npmplus` | `.env` | — |
| `ollama` | `.env`, `.env.compose` | `OLLAMA_API_KEY` |
| `openclaw` | `.env.compose`, `.env.secrets`, `gateway.env` | `BRAVE_API_KEY`, `BRAVE_PLAN`, `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`, `DISCORD_OPENCLAW_SERVER_ID`, `GITHUB_TOKEN`, `GOG_ACCOUNT`, `GOG_CLIENT`, `LITELLM_API_KEY`, `LITELLM_IDE_API_KEY`, `LITELLM_N8N_API_KEY`, `LITELLM_OPENCLAW_CRON_API_KEY`, `LITELLM_OPENCLAW_MAIN_API_KEY`, `LITELLM_REACTIVE_API_KEY`, `MOLTBOOK_API_KEY`, `N8N_API_KEY`, `N8N_BASE_URL`, `NABLA_FREE_OPENAI_API_KEY`, `NABLA_OPENAI_CLI_API_KEY`, `NABLA_PLUS_OPENAI_API_KEY`, `OPENAI_API_KEY`, `OPENCLAW_GATEWAY_PASSWORD`, `OPENCLAW_GATEWAY_TOKEN`, `SEARXNG_BASE_URL`, `TAVILY_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TWITTER_API_BACKEND`, `VAULT_ADDR`, `VAULT_TOKEN`, `WEB_SEARCH_BACKEND`, `X_BEARER_TOKEN` |
| `pihole` | `.env.secrets` | `FTLCONF_webserver_api_password`, `PIHOLE_PASSWORD` |
| `redis` | `.env.compose` | `REDIS_AUTH` |
| `sentry` | `.env.compose`, `.env.migrator.secrets`, `.env.secrets` | `CELERY_BROKER_URL`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_READONLY_PASSWORD`, `CLICKHOUSE_TRACE_PASSWORD`, `REDIS_PASSWORD`, `RELAY_ID`, `RELAY_PUBLIC_KEY`, `RELAY_REDIS_URL`, `RELAY_SECRET_KEY`, `SENTRY_CLICKHOUSE_PASSWORD`, `SENTRY_DB_PASSWORD`, `SENTRY_REDIS_PASSWORD`, `SENTRY_REDIS_URL`, `SENTRY_SECRET_KEY`, `SENTRY_SYSTEM_SECRET_KEY` |
| `sentry-clickhouse` | `.env.secrets` | `CLICKHOUSE_PASSWORD` |
| `traefik` | `.env`, `.env.secrets` | `CF_API_EMAIL`, `CF_API_KEY`, `CF_DNS_API_TOKEN`, `CF_EMAIL`, `CF_TOKEN`, `CF_ZONE_ID`, `CLOUDFLARE_API_TOKEN`, `DOMAIN1_ZONE_ID`, `DOMAIN2_ZONE_ID`, `PIHOLE_PASSWORD`, `TRAEFIK_DASHBOARD_BASIC_AUTH` |

## 4. Déclarés sans fichier runtime : à créer au déploiement

Aucune valeur à migrer depuis `/mnt/cpool/secrets/runtime` : générer le
secret dans Vaultwarden puis le matérialiser lors du déploiement. Certains
services gardent encore leurs secrets ailleurs (`SECRETS_LEGACY_PATH` de
[`docs/master-readiness.md`](../master-readiness.md)).

| Service | Clés déclarées |
| --- | --- |
| `2fauth` | `TWOFAUTH_APP_KEY` |
| `autokuma` | `AUTOKUMA__KUMA__AUTH_TOKEN` |
| `bazarr` | `API_KEY` |
| `cartography` | `NEO4J_PASSWORD` |
| `dependency-track` | `ALPINE_DATABASE_PASSWORD` |
| `dsomm` | `GH_TOKEN` |
| `grafana` | `GRAFANA_ADMIN_PASSWORD` |
| `grafana-observability` | `GRAFANA_SERVICE_ACCOUNT_TOKEN` |
| `infrastructure-bootstrap` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `GARAGE_ADMIN_TOKEN`, `TRUENAS_INFRA_API_KEY` |
| `joplin` | `POSTGRES_PASSWORD` |
| `karakeep` | `KARAKEEP_MEILISEARCH_MASTER_KEY`, `KARAKEEP_NEXTAUTH_SECRET`, `KARAKEEP_OPENAI_API_KEY` |
| `lidarr` | `API_KEY`, `LIDARR__AUTH__APIKEY` |
| `media-acquisition` | `HTTPPROXY_PASSWORD`, `HTTPPROXY_USER`, `WIREGUARD_PRIVATE_KEY` |
| `neo4j` | `NEO4J_AUTH` |
| `netbox` | `DB_PASSWORD`, `SECRET_KEY` |
| `nexus-infrastructure` | `NEXUS_PASSWORD`, `NEXUS_USERNAME` |
| `ntopng` | `NTOPNG_CLICKHOUSE_PASSWORD` |
| `open-terminal` | `OPEN_TERMINAL_API_KEY` |
| `pfsense-observability` | `PFSENSE_OBSERVABILITY_API_KEY` |
| `plumber` | `JOBS_DB_PASSWORD` |
| `portracker` | `TRUENAS_API_KEY` |
| `prowlarr` | `API_KEY`, `PROWLARR__AUTH__APIKEY` |
| `qbittorrent-exporter` | `QBITTORRENT_API_KEY` |
| `radarr` | `API_KEY`, `RADARR__AUTH__APIKEY` |
| `reactive-resume` | `REACTIVE_RESUME_AUTH_SECRET`, `REACTIVE_RESUME_DATABASE_PASSWORD`, `REACTIVE_RESUME_ENCRYPTION_SECRET`, `REACTIVE_RESUME_REDIS_PASSWORD` |
| `recyclarr` | `RADARR_API_KEY`, `SONARR_API_KEY` |
| `sample-litellm` | `LITELLM_API_KEY` |
| `scorecard` | `GITHUB_AUTH_TOKEN` |
| `sonarqube` | `SONAR_JDBC_PASSWORD` |
| `sonarr` | `API_KEY`, `SONARR__AUTH__APIKEY` |
| `truenas-csi` | `TRUENAS_CSI_API_KEY` |
| `wazuh` | `WAZUH_DASHBOARD_PASSWORD`, `WAZUH_INDEXER_PASSWORD` |
