# Remédiations encore ouvertes — sondes Homelab (6 novembre 2026)

**Périmètre :** actions opérateur **non réceptionnées** après les PR #325/#326. Les corrections d'`appId`, le `pfSense` Cloud `transport_only`, Tavily `GET /usage` et la décision de ne pas exempter Keycloak/LiteLLM au WAF sont **déjà codés ou décidés** : ne pas les rejouer. Leur contexte est dans [les leçons d'incident](../incidents/2026-11-06-migrations-retour-experience.md). Le plan de travail actuel est la [roadmap](../roadmap.md).

**Règle de sûreté :** ne jamais rendre une sonde verte en supprimant un contrôle, modifiant un seuil ou ouvrant un accès. Distinguer `CODED`, `NOT_VERIFIED` et `ACCEPTED (runtime)`. Avant chaque `--apply` : sauvegarde, politique validée, plan attendu et rollback.

## 1. Cloudflare Tunnel — exposition déclarative non réceptionnée

**Ouvert :** retirer des routes Tunnel les **23 entrées** des services `external=false` recensées dans la campagne du 4 novembre, **plus** la route `litellm.albandrieu.com` (décision du 5 novembre : LiteLLM n'est plus publié), et limiter `keycloak.albandrieu.com` aux chemins de production recommandés par [la doc Keycloak](https://www.keycloak.org/server/reverseproxy) (d'abord `^/realms/master(/|$)` → `http_status:404` — `master` est réservé à l'administration —, puis `^/(realms|resources|\.well-known)/` vers l'origine, puis `http_status:404` pour `/admin/`, `/metrics`, `/health` et la racine). Le plan OpenTofu a été préparé, **pas appliqué**. Les hostnames privés de la Workstation et l'enregistrement DNS `litellm.albandrieu.com` doivent aussi être retirés du dashboard après contrôle indépendant.

```bash
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare plan -out=routes.tfplan
# Arrêter si le plan diffère des 23 suppressions attendues, de la suppression LiteLLM,
# des deux règles Keycloak (path limité + 404) et du renommage FastAPI Sample.
# Mutation séparée, après validation humaine :
# scripts/infra/terragrunt-safe.sh infrastructure/cloudflare apply routes.tfplan
```

Pour le renommage `sample` → `fastapi-sample`, garder synchronisés les consommateurs du catalogue et les politiques Access. Ne jamais supprimer l'ancienne route avant l'acceptation de la nouvelle. [Contrat IaC](../../terraform/cloudflare/README.md).

**Gate :** aucun `external=false but a Cloudflare Tunnel ingress exists` dans `/sickz`, aucune nouvelle exposition publique, diff OpenTofu maîtrisé ; depuis Internet `https://keycloak.albandrieu.com/admin/` et `/realms/master/…` → 404.

## 2. Cloudflare Access — identité de l'observateur et coffre

**Ouvert :** les applications Access listées dans les preuves de campagne refusaient le Service Token de l'observateur : `Service Token did not pass Access`. Réconcilier **application par application**, avec une politique **Service Auth** et un token dédié, sans créer un `Bypass` général. L'état actuel des politiques reste **NOT_VERIFIED** tant que leurs actions n'ont pas été inspectées depuis Cloudflare.

**Outil :** `scripts/cloudflare/attach-observer-service-auth.py --policy-id <uuid>` (lecture seule par défaut, `--apply` explicite) dérive les hôtes du catalogue (`external=true`, Tunnel, Access requis, hors `*.int`), vérifie que la politique réutilisable est bien `Service Auth` avec un token, l'ajoute sans modifier les autres réglages et ignore les applications à politiques *inline*. Jeton `CLOUDFLARE_API_TOKEN` (Access Apps and Policies Edit) depuis Vaultwarden, jamais affiché.

**Vaultwarden :** supprimer le `Bypass Everyone` de l'application entière uniquement après avoir créé et testé les exceptions par chemin nécessaires aux clients Bitwarden (`/api/*`, `/identity/*`, `/notifications/*`, `/icons/*`, `/alive`). La racine et `/admin` conservent Access et `ADMIN_TOKEN` ; valider les clients hors LAN **avant** toute suppression de règle.

**Gate :** `cloudflare_service_token_access_passed=true` quand un service exige Service Auth ; Vaultwarden limité par chemin, jamais exposé en accès libre.

## 3. FastAPI Cloud — credentials OVH seulement

**Décision (5 novembre) :** OVH est **désactivé** pour le moment : la sonde `openstack_me` est ignorée par défaut côté FastAPI Sample (`OVH_API_PROBE_ENABLED=true` pour la réactiver). Avant réactivation : `openstack_me` avait renvoyé « This credential does not exist » ; auditer l'identité et son scope, régénérer uniquement si nécessaire, sans copier les secrets dans Git ni dans le ticket.

```bash
mise exec -- uv run fastapi cloud env list
# L'édition de secrets exige une session opérateur distincte :
# mise exec -- uv run fastapi cloud env set --secret OVH_APPLICATION_KEY
```

**Gate :** santé de l'API OVH prouvée par une requête autorisée, et non par une simple présence de variables. **Ne pas réactiver** les sondes pfSense authentifiées depuis FastAPI Cloud.

## 4. TrueNAS — résoudre les états réels avant les changements

Le rapprochement `x-nabla` est déjà corrigé en PR #326. L'état `in_sync/STOPPED` n'est pas un PASS de disponibilité.

```bash
sudo midclt call app.query | jq -r '
  .[] | select(.name == "graylog" or .name == "lidarr" or
               .name == "homarr" or .name == "bitcoind" or
               .name == "elastic-search" or .name == "hermes-agent")
  | [.name, .state] | @tsv'
sudo docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -E 'ix-(graylog|lidarr|homarr|bitcoind|elastic-search|hermes-agent)' || true
```

**Ouvert :** pour `homarr` CRASHED, l'interface `homarr` tourne : c'est le job ponctuel `homarr-sync` (`restart: "no"`) qui sort en erreur. Lire `sudo docker logs --tail 200 homarr-sync` (jeton API Homarr, API v2.6, manifeste généré), corriger, valider avec `HOMARR_SYNC_DRY_RUN=true`, puis redéployer l'App ; pour `graylog`/`lidarr` STOPPED, vérifier leurs dépendances. Les arrêts volontaires (`bitcoind` et autres) exigent **une nouvelle décision** avant redémarrage. Aucun `app.start` automatique.

**Gate :** `/api/homelab/runtime` cohérent avec TrueNAS, `/api/homelab/health` avec HTTP frais et causes documentées pour les arrêts voulus.

## 5. Applications TrueNAS encore absentes

| Application | Procédure versionnée | Prérequis/gate avant mutation |
| --- | --- | --- |
| `netbox`, `dependency-track`, `plumber` | `scripts/truenas/deploy-security-tooling.sh --apply <app>` | Secrets, stockage, PostgreSQL et plan contrôlés |
| `scanopy` | `scripts/truenas/deploy-scanopy.sh --check` puis `--apply` (`NABLA_RUNTIME_CHANGE_APPROVED=yes`) | Autorisation du daemon privilégié, secrets, rôle PostgreSQL et image |
| `joplin` | `scripts/truenas/deploy-joplin.sh --check` puis `--apply` (`NABLA_RUNTIME_CHANGE_APPROVED=yes`) | Postgres, permissions 0600 ; décision d'exposition `external=true` à réconcilier |
| `ntopng` | `scripts/truenas/deploy-ntopng.sh --check` puis `--apply` **si le préflight passe** | Licence Enterprise M+, ClickHouse dédié, interface de capture approuvée, secret canonique 0600 |

**Attention :** `deploy-security-tooling.sh --check` est **un test d'acceptation runtime**, pas un simple dry-run initial. Il échoue normalement si une App requise manque ; avant son premier déploiement, contrôler indépendamment `prepare-security-tooling-secrets.sh --check`, `bootstrap-repository-storage.sh --check`, `bootstrap-security-tooling-postgres.sh --check` et le contrat Compose. `--apply` provoque de véritables mutations.

**Scanopy/Joplin (8 novembre) :** les deux déployeurs partagent désormais le contrat `scripts/lib/app-deploy.sh` : `--check` par défaut (`<app>_mutations=0`, aucune mutation), `--apply` seulement avec `NABLA_RUNTIME_CHANGE_APPROVED=yes` ; `accept-runtime-env-first-wave.sh --accept` exige la même approbation. Les bootstraps PostgreSQL (`bootstrap-joplin-postgres.sh`, `bootstrap-scanopy-postgres.sh`, `bootstrap-homeassistant-postgres.sh`, `bootstrap-security-tooling-postgres.sh`) sont des wrappers de `bootstrap-app-postgres.sh [--check|--apply|--describe] <app>` (une seule implémentation idempotente, mot de passe jamais sur argv). La réception TrueNAS reste requise après tout premier déploiement.

**ntopng :** la version déclarative requiert une licence non fournie par ce dépôt et l'accès `NET_ADMIN`/`NET_RAW` au réseau hôte ; aucun démarrage n'est permis par la seule présence du script. Le backend ClickHouse doit être testé avec une identité `ntopng` limitée.

**Ordre de démarrage préparé le 7 novembre, outillé le 8** (une App à la fois, réception avant la suivante ; aucune de ces commandes n'est exécutée depuis une session agent). Point d'entrée unique : `bash scripts/truenas/rollout-pending-apps.sh --plan` (sans root, affiche les étapes), `sudo … --check [app]` (toutes les gates en lecture seule, verdict READY/BLOCKED par App, journaux privés), `sudo NABLA_RUNTIME_CHANGE_APPROVED=yes … --apply <app>` (une App, par son déployeur, puis `bootstrap-postgres-backup-role.sh --apply`). Détail des gates :

1. Dépendances de données déjà `RUNNING` : PostgreSQL global (`172.17.0.24:5432`), Redis partagé (NetBox : bases 5/6), ClickHouse (ntopng), Prometheus/Gatus. Snapshot ZFS de `cpool/backup` et du dataset cible avant chaque première mutation.
2. `netbox` → `dependency-track` → `plumber` : `prepare-security-tooling-secrets.sh --check <app>`, `bootstrap-repository-storage.sh --check <app>`, `bootstrap-app-postgres.sh --check <app>` (bases `netbox`, `dependencytrack`, `jobs`), contrat Compose ; puis `deploy-security-tooling.sh --apply <app>` (stockage, rôle PostgreSQL, réconciliation, santé, HTTP) ; `deploy-security-tooling.sh --check <app>` reste l'acceptation runtime après coup.
3. `scanopy` : `deploy-scanopy.sh --check` (image lock, runtime, secrets, rôle PostgreSQL, Compose) ; puis `bootstrap-app-postgres.sh --apply scanopy` et `deploy-scanopy.sh --apply` ; autorisation explicite du daemon privilégié.
4. `joplin` : `deploy-joplin.sh --check` ; puis `bootstrap-app-postgres.sh --apply joplin` et `deploy-joplin.sh --apply` ; l'exposition `external=true` reste à trancher (roadmap).
5. `ntopng` : `deploy-ntopng.sh --check` seulement tant que la licence, l'interface de capture et l'identité ClickHouse `ntopng` ne sont pas prouvées ; `cpool/ntopng` est hors politique de snapshots (données reconstruibles).
6. Après chaque App : `app.query` `RUNNING`, sonde Gatus verte (`apps/gatus/config/config.yml` couvre déjà les six), `/api/homelab/status` `in_sync`, puis `bootstrap-postgres-backup-role.sh --apply` (relecture : le rôle `pgbackup` reçoit `CONNECT` sur les bases désormais présentes) et un run manuel du job `postgres-backup`.
7. Prometheus : `dependency_track` (`ALPINE_METRICS_ENABLED`, `172.17.0.24:31083/metrics`) et `netbox` (`METRICS_ENABLED`, `172.17.0.24:31082/metrics`) sont déclarés dans `apps/prometheus/prometheus.yml` et agrégés par `nabla:telemetry:service_exporter_up` ; ils restent `down` jusqu'au démarrage des Apps (pas d'alerte `NablaExporterTargetDown` pour eux). Scanopy, Plumber, Joplin et ntopng n'ont pas d'export Prometheus vérifié : sondes Gatus uniquement. Synergies d'intégration (SSO Keycloak, SBOM → Dependency-Track → DefectDojo, Scanopy → NetBox) : [analyse du 7 novembre](../integration-synergies-20261107.md).

**Gate commune :** une App TrueNAS unique, `in_sync` dans `/api/homelab/status`, runtime et HTTP frais, données restaurables. Ne pas requalifier un service en `planned` pour supprimer artificiellement une panne. `aistor` et `wordpress` ont été **supprimés** du dépôt le 5 novembre. Décision du 6 novembre : le dataset `cpool/aistor` est retiré de la politique de snapshots et **doit être détruit** (voir la [roadmap](../roadmap.md)) : la réconciliation des snapshots ne supprime jamais une tâche existante.

## 6. Identité canonique et dettes d'exposition

- `homeassistant` n'est pas rebaptisé en `home-assistant` dans le catalogue. Suivre [la migration contrôlée](openwebui-homeassistant-canonical-rename.md) avec rollback et preuve du middleware. **Cible (6 novembre) : le recorder utilise le PostgreSQL global.** L'image du dépôt est désormais épinglée sur la même version et le même digest que l'App native (`2026.10.4`), et les deux PostgreSQL sont en `18.6-trixie` (même digest) : `pg_dump`/`pg_restore` sont compatibles.
  1. Secret `POSTGRES_PASSWORD` dans `/mnt/cpool/secrets/runtime/homeassistant/.env.secrets` (0600), puis `sudo bash scripts/truenas/bootstrap-homeassistant-postgres.sh` (`--check`) et `--apply` : rôle et base `homeassistant` dans le PostgreSQL global.
  2. Snapshot ZFS des datasets HA ; arrêter l'App native ; `pg_dump -Fc` de la base recorder depuis son conteneur `postgres`, `pg_restore --no-owner --role=homeassistant` dans la base globale.
  3. Dans `/config/secrets.yaml` (0600) : `recorder_db_url: postgresql://homeassistant:<mot de passe>@172.17.0.24:5432/homeassistant` ; dans `configuration.yaml` : `recorder: db_url: !secret recorder_db_url`.
  4. **Réseau (décision du 6 novembre) :** `apps/homeassistant/compose.yml` passe de `iot_macvlan` (qui attribuait au conteneur l'IP de l'hôte TrueNAS, injoignable depuis un macvlan) à un pont : réseaux `intranet` + `traefik`, port `8123` publié sur `172.17.0.24`. Le PostgreSQL global `172.17.0.24:5432` est donc joignable. Contrepartie : pas de découverte multicast (mDNS/SSDP) des équipements IoT depuis un pont ; configurer les intégrations par adresse explicite. Vérifier aussi le domaine Traefik `homeassistant.albanandrieu.com` (coquille probable).
  5. Gate : historique visible, recorder sans erreur dans les journaux, `homeassistant` `in_sync` ; rollback : arrêter le nouveau conteneur et redémarrer l'App native (base d'origine intacte).
- LiteLLM n'est plus publié sur Internet ; sa santé est prouvée par l'observateur TrueNAS (`LITELLM_HEALTHZ_URL` LAN). Keycloak ne publie que `/realms/`, `/resources/` et `/.well-known/`, et refuse `/realms/master/` (réservé à l'administration, LAN). Les applications utilisent le realm `nabla`, déclaré dans `apps/keycloak/config/realms/nabla.yaml` et importé par `scripts/truenas/apply-keycloak-config.sh` (keycloak-config-cli épinglé ; `--check` puis `--apply` avec `NABLA_RUNTIME_CHANGE_APPROVED=yes`). Keycloak est désormais une Custom App TrueNAS construite depuis `apps/keycloak` (migrée le 6 novembre, `appId: keycloak`, plus `planned`), actuellement `STOPPED` : la démarrer avant l'import.
- `joplin.int.albandrieu.com` est privé tandis que la déclaration historique indique `external=true` ; ne pas publier un hostname automatiquement pour faire passer une assertion.
- `hello.int` reste `warn` par décision ; `s3.int` demeure une exception jusqu'à la migration du backend d'état OpenTofu.

## 6 bis. Observabilité — Gatus via Prometheus

Constat du 6 novembre (FastAPI Cloud) : toute la stack tourne sur TrueNAS (`prometheus`, `alertmanager`, `node-exporter`, `pfsense-exporter`, `grafana`, `alloy`, `loki`, `mimir`, `tempo`, `gatus`, `pyroscope` en `running`). Côté Cloud, `platform_metrics.state=not_configured` : `HOMELAB_PROMETHEUS_URL` n'y est pas défini, d'où `internal_probe_delegation.blockers = [prometheus_not_configured, gatus_not_observed]`. La chaîne est codée de bout en bout : Gatus `metrics: true`, job Prometheus `gatus`, règles `nabla:telemetry:gatus_up` et `nabla:service:synthetic_*`, requêtes de FastAPI Sample.

- **TrueNAS (LAN, source de vérité) :** `HOMELAB_PROMETHEUS_URL=http://172.17.0.24:9090` est déjà dans `compose.yml` de FastAPI Sample ; vérifier `curl -fsS http://172.17.0.24:8091/api/health-board | jq '.platform_metrics | {state, synthetic_probes: .synthetic_probes.state, gatus_up: .synthetic_probes.gatus_up}'` et `up{job="gatus"}` dans Prometheus.
- **FastAPI Cloud (optionnel) :** définir `HOMELAB_PROMETHEUS_URL=https://prometheus.albandrieu.com`, `HOMELAB_PROMETHEUS_CF_ACCESS_CLIENT_ID` et `HOMELAB_PROMETHEUS_CF_ACCESS_CLIENT_SECRET` (jeton de l'observateur, envoyé uniquement à ce domaine épinglé) et attacher la politique Service Auth à l'application Access Prometheus (§2).
- **Nouveaux jobs (7 novembre) :** `dependency_track` et `netbox` scrapent les endpoints natifs des Apps (`/metrics`) ; ils sont dans `nabla:telemetry:service_exporter_up` et dans `_EXPORTER_JOBS` de FastAPI Sample, donc visibles dans `platform_metrics.exporter_jobs` dès le démarrage des Apps.
- **CI :** `observability-ci.yml` monte désormais des fichiers vides pour chaque `credentials_file` afin que `promtool check config` valide la syntaxe et les règles sans secret.

**Gate :** `platform_metrics.state` ≠ `not_configured`/`telemetry_unavailable`, `synthetic_probes.gatus_up=1` et services Gatus visibles dans `/api/health-board`.

## 6 ter. Sauvegardes PostgreSQL — job `pg_dump` versionné (`apps/postgres-backup`)

Décision du 7 novembre : **Databasus** (App TrueNAS `databasus`, `ghcr.io/databasus/databasus:v3.64.0`, hors dépôt) n'a ni API HTTP publique, ni Terraform, ni import de configuration (CLI limitée aux comptes) ; il est **désactivé** (décision du 7 novembre) : `sudo midclt call -j app.stop databasus` ; supprimer l'App (`app.delete`, en conservant ses volumes) seulement après avoir vérifié qu'aucune sauvegarde utile n'y réside. Il n'a jamais été déclaré dans ce dépôt (`observed_only`) : aucune alerte ne découle de son arrêt. La référence « as code » est le job `apps/postgres-backup` : image `postgres:18.6-trixie` au **même digest que le serveur**, `pg_dump -Fc` par base vérifié par `pg_restore --list`, sidecar sha256, rétention locale 14 jours dans `/mnt/cpool/backup/postgres` (dataset de la classe `backup-targets`, snapshots 14 j / 8 sem), planifié par un cron natif TrueNAS. Sauvegardes **logiques** uniquement ; PITR (pgBackRest) quand PostgreSQL sera une Custom App.

1. Secret `POSTGRES_PASSWORD` dans `/mnt/cpool/secrets/runtime/postgres-backup/.env.secrets` (0600, déclaré au manifeste), puis `sudo bash scripts/truenas/bootstrap-postgres-backup-role.sh` (`--check`) et `--apply` : rôle `pgbackup` `LOGIN NOREPLICATION`, membre de `pg_read_all_data`, `CONNECT` sur `keycloak`, `joplin`, `homeassistant`, `netbox`, `dependencytrack`, `scanopy`, `jobs` (liste `POSTGRES_BACKUP_DATABASES`, alignée avec `BACKUP_DATABASES` du Compose). Une base pas encore créée est **ignorée avec un avertissement** par le script de rôle et reportée `SKIP` par le job (`BACKUP_REQUIRE_ALL=true` pour exiger toutes les bases) ; relancer `--apply` après chaque bootstrap d'App (§5).
2. `sudo bash scripts/truenas/bootstrap-repository-storage.sh --check postgres-backup` puis `--apply` (dataset `cpool/backup`, répertoire `postgres` possédé par `568:568`).
3. Première exécution manuelle depuis le checkout canonique : `docker compose --project-directory apps/postgres-backup --profile manual run --rm --no-deps postgres-backup` ; contrôler `OK <base> … bytes` et `.last-success.json`.
4. Test de restauration dans une base temporaire (`pg_restore --no-owner --role=<rôle> -d <base_test> <archive>`), avant la bascule Home Assistant (§6).
5. Cron : `python3 scripts/truenas/reconcile-postgres-backup-cron.py --check`, puis `sudo … --apply` (créé **désactivé**, 03:20 heure appliance), puis `sudo POSTGRES_BACKUP_CRON_APPROVED=YES … --enable` après les étapes 3 et 4.
6. Copie hors site : les archives sont sur `cpool/backup` ; la réplication hors site (Restic/Garage) reste le chantier existant de la roadmap.

**Gate :** `--check` du rôle vert ; `.last-success.json` daté du jour pour chaque base ; restauration de test réussie ; cron `enabled=true` seulement après ces preuves.

## 7. Réception globale

Depuis les réseaux autorisés, comparer des captures **datées et sur le même SHA** de `/healthz`, `/api/homelab/health`, `/api/homelab/status` et `/sickz`. Le second `/sickz` dans la minute doit être servi du cache. Contrôler que les `warn` WAF volontaires ne sont pas affichés comme `DOWN`, et que toutes les Apps requises ont une preuve indépendante de leur santé.

**Clôture :** résultats `ACCEPTED (runtime)` ; sinon maintenir `NOT_VERIFIED`. La PR et la quality gate ne remplacent pas ce contrôle.
