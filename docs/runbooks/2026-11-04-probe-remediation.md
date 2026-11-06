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
| `scanopy` | `scripts/truenas/deploy-scanopy.sh` | Autorisation du daemon privilégié, secrets, rôle PostgreSQL et image |
| `joplin` | `scripts/truenas/deploy-joplin.sh` | Postgres, permissions 0600 ; décision d'exposition `external=true` à réconcilier |
| `ntopng` | `scripts/truenas/deploy-ntopng.sh --check` puis `--apply` **si le préflight passe** | Licence Enterprise M+, ClickHouse dédié, interface de capture approuvée, secret canonique 0600 |

**Attention :** `deploy-security-tooling.sh --check` est **un test d'acceptation runtime**, pas un simple dry-run initial. Il échoue normalement si une App requise manque ; avant son premier déploiement, contrôler indépendamment `prepare-security-tooling-secrets.sh --check`, `bootstrap-repository-storage.sh --check`, `bootstrap-security-tooling-postgres.sh --check` et le contrat Compose. `--apply` provoque de véritables mutations.

**Scanopy/Joplin :** jusqu'à la disponibilité d'un `--check` de leur déployeur, **ne pas exécuter leur script pour inspecter**. Utiliser les bootstrap `--check` et relire les scripts. La réception TrueNAS reste requise après tout premier déploiement.

**ntopng :** la version déclarative requiert une licence non fournie par ce dépôt et l'accès `NET_ADMIN`/`NET_RAW` au réseau hôte ; aucun démarrage n'est permis par la seule présence du script. Le backend ClickHouse doit être testé avec une identité `ntopng` limitée.

**Gate commune :** une App TrueNAS unique, `in_sync` dans `/api/homelab/status`, runtime et HTTP frais, données restaurables. Ne pas requalifier un service en `planned` pour supprimer artificiellement une panne. `aistor` et `wordpress` ont été **supprimés** du dépôt le 5 novembre. Décision du 6 novembre : le dataset `cpool/aistor` est retiré de la politique de snapshots et **doit être détruit** (voir la [roadmap](../roadmap.md)) : la réconciliation des snapshots ne supprime jamais une tâche existante.

## 6. Identité canonique et dettes d'exposition

- `homeassistant` n'est pas rebaptisé en `home-assistant` dans le catalogue. Suivre [la migration contrôlée](openwebui-homeassistant-canonical-rename.md) avec rollback et preuve du middleware. **Cible (6 novembre) : le recorder utilise le PostgreSQL global.** L'image du dépôt est désormais épinglée sur la même version et le même digest que l'App native (`2026.10.4`), et les deux PostgreSQL sont en `18.6-trixie` (même digest) : `pg_dump`/`pg_restore` sont compatibles.
  1. Secret `POSTGRES_PASSWORD` dans `/mnt/cpool/secrets/runtime/homeassistant/.env.secrets` (0600), puis `sudo bash scripts/truenas/bootstrap-homeassistant-postgres.sh` (`--check`) et `--apply` : rôle et base `homeassistant` dans le PostgreSQL global.
  2. Snapshot ZFS des datasets HA ; arrêter l'App native ; `pg_dump -Fc` de la base recorder depuis son conteneur `postgres`, `pg_restore --no-owner --role=homeassistant` dans la base globale.
  3. Dans `/config/secrets.yaml` (0600) : `recorder_db_url: postgresql://homeassistant:<mot de passe>@172.17.0.24:5432/homeassistant` ; dans `configuration.yaml` : `recorder: db_url: !secret recorder_db_url`.
  4. **Bloquant avant bascule :** `apps/homeassistant/compose.yml` attribue au conteneur l'IP `172.17.0.24` sur `iot_macvlan`, c'est-à-dire l'IP de l'hôte TrueNAS, et un conteneur macvlan ne peut pas joindre l'IP de son propre hôte (donc ni PostgreSQL `:5432`). Choisir une IP IoT libre, ou un réseau bridge/hôte qui atteint le PostgreSQL global ; vérifier aussi le domaine Traefik `homeassistant.albanandrieu.com`.
  5. Gate : historique visible, recorder sans erreur dans les journaux, `homeassistant` `in_sync` ; rollback : arrêter le nouveau conteneur et redémarrer l'App native (base d'origine intacte).
- LiteLLM n'est plus publié sur Internet ; sa santé est prouvée par l'observateur TrueNAS (`LITELLM_HEALTHZ_URL` LAN). Keycloak ne publie que `/realms/`, `/resources/` et `/.well-known/`, et refuse `/realms/master/` (réservé à l'administration, LAN). Les applications utilisent le realm `nabla`, déclaré dans `apps/keycloak/config/realms/nabla.yaml` et importé par `scripts/truenas/apply-keycloak-config.sh` (keycloak-config-cli épinglé ; `--check` puis `--apply` avec `NABLA_RUNTIME_CHANGE_APPROVED=yes`). Keycloak est actuellement `STOPPED` : le démarrer avant l'import.
- `joplin.int.albandrieu.com` est privé tandis que la déclaration historique indique `external=true` ; ne pas publier un hostname automatiquement pour faire passer une assertion.
- `hello.int` reste `warn` par décision ; `s3.int` demeure une exception jusqu'à la migration du backend d'état OpenTofu.

## 6 bis. Observabilité — Gatus via Prometheus

Constat du 6 novembre (FastAPI Cloud) : toute la stack tourne sur TrueNAS (`prometheus`, `alertmanager`, `node-exporter`, `pfsense-exporter`, `grafana`, `alloy`, `loki`, `mimir`, `tempo`, `gatus`, `pyroscope` en `running`). Côté Cloud, `platform_metrics.state=not_configured` : `HOMELAB_PROMETHEUS_URL` n'y est pas défini, d'où `internal_probe_delegation.blockers = [prometheus_not_configured, gatus_not_observed]`. La chaîne est codée de bout en bout : Gatus `metrics: true`, job Prometheus `gatus`, règles `nabla:telemetry:gatus_up` et `nabla:service:synthetic_*`, requêtes de FastAPI Sample.

- **TrueNAS (LAN, source de vérité) :** `HOMELAB_PROMETHEUS_URL=http://172.17.0.24:9090` est déjà dans `compose.yml` de FastAPI Sample ; vérifier `curl -fsS http://172.17.0.24:8091/api/health-board | jq '.platform_metrics | {state, synthetic_probes: .synthetic_probes.state, gatus_up: .synthetic_probes.gatus_up}'` et `up{job="gatus"}` dans Prometheus.
- **FastAPI Cloud (optionnel) :** définir `HOMELAB_PROMETHEUS_URL=https://prometheus.albandrieu.com`, `HOMELAB_PROMETHEUS_CF_ACCESS_CLIENT_ID` et `HOMELAB_PROMETHEUS_CF_ACCESS_CLIENT_SECRET` (jeton de l'observateur, envoyé uniquement à ce domaine épinglé) et attacher la politique Service Auth à l'application Access Prometheus (§2).
- **CI :** `observability-ci.yml` monte désormais des fichiers vides pour chaque `credentials_file` afin que `promtool check config` valide la syntaxe et les règles sans secret.

**Gate :** `platform_metrics.state` ≠ `not_configured`/`telemetry_unavailable`, `synthetic_probes.gatus_up=1` et services Gatus visibles dans `/api/health-board`.

## 7. Réception globale

Depuis les réseaux autorisés, comparer des captures **datées et sur le même SHA** de `/healthz`, `/api/homelab/health`, `/api/homelab/status` et `/sickz`. Le second `/sickz` dans la minute doit être servi du cache. Contrôler que les `warn` WAF volontaires ne sont pas affichés comme `DOWN`, et que toutes les Apps requises ont une preuve indépendante de leur santé.

**Clôture :** résultats `ACCEPTED (runtime)` ; sinon maintenir `NOT_VERIFIED`. La PR et la quality gate ne remplacent pas ce contrôle.
