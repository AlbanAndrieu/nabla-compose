# Remédiations encore ouvertes — sondes Homelab (6 novembre 2026)

**Périmètre :** actions opérateur **non réceptionnées** après les PR #325/#326. Les corrections d'`appId`, le `pfSense` Cloud `transport_only`, Tavily `GET /usage` et la décision de ne pas exempter Keycloak/LiteLLM au WAF sont **déjà codés ou décidés** : ne pas les rejouer. Leur contexte est dans [les leçons d'incident](../incidents/2026-11-06-migrations-retour-experience.md). Le plan de travail actuel est la [roadmap](../roadmap.md).

**Règle de sûreté :** ne jamais rendre une sonde verte en supprimant un contrôle, modifiant un seuil ou ouvrant un accès. Distinguer `CODED`, `NOT_VERIFIED` et `ACCEPTED (runtime)`. Avant chaque `--apply` : sauvegarde, politique validée, plan attendu et rollback.

## 1. Cloudflare Tunnel — exposition déclarative non réceptionnée

**Ouvert :** retirer des routes Tunnel les **23 entrées** des services `external=false` recensées dans la campagne du 4 novembre. Le plan OpenTofu a été préparé, **pas appliqué**. Les hostnames privés de la Workstation doivent aussi être retirés du dashboard après contrôle indépendant.

```bash
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare plan -out=routes.tfplan
# Arrêter si le plan diffère des 23 suppressions attendues et du renommage FastAPI Sample.
# Mutation séparée, après validation humaine :
# scripts/infra/terragrunt-safe.sh infrastructure/cloudflare apply routes.tfplan
```

Pour le renommage `sample` → `fastapi-sample`, garder synchronisés les consommateurs du catalogue et les politiques Access. Ne jamais supprimer l'ancienne route avant l'acceptation de la nouvelle. [Contrat IaC](../../terraform/cloudflare/README.md).

**Gate :** aucun `external=false but a Cloudflare Tunnel ingress exists` dans `/sickz`, aucune nouvelle exposition publique, diff OpenTofu maîtrisé.

## 2. Cloudflare Access — identité de l'observateur et coffre

**Ouvert :** les applications Access listées dans les preuves de campagne refusaient le Service Token de l'observateur : `Service Token did not pass Access`. Réconcilier **application par application**, avec une politique **Service Auth** et un token dédié, sans créer un `Bypass` général. L'état actuel des politiques reste **NOT_VERIFIED** tant que leurs actions n'ont pas été inspectées depuis Cloudflare.

**Vaultwarden :** supprimer le `Bypass Everyone` de l'application entière uniquement après avoir créé et testé les exceptions par chemin nécessaires aux clients Bitwarden (`/api/*`, `/identity/*`, `/notifications/*`, `/icons/*`, `/alive`). La racine et `/admin` conservent Access et `ADMIN_TOKEN` ; valider les clients hors LAN **avant** toute suppression de règle.

**Gate :** `cloudflare_service_token_access_passed=true` quand un service exige Service Auth ; Vaultwarden limité par chemin, jamais exposé en accès libre.

## 3. FastAPI Cloud — credentials OVH seulement

**Ouvert :** `openstack_me` a renvoyé « This credential does not exist » : auditer l'identité et son scope, régénérer uniquement si nécessaire, sans copier les secrets dans Git ni dans le ticket.

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

**Ouvert :** pour `homarr` CRASHED, traiter les erreurs de volume, base ou secret ; pour `graylog`/`lidarr` STOPPED, vérifier leurs dépendances. Les arrêts volontaires (`bitcoind` et autres) exigent **une nouvelle décision** avant redémarrage. Aucun `app.start` automatique.

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

**Gate commune :** une App TrueNAS unique, `in_sync` dans `/api/homelab/status`, runtime et HTTP frais, données restaurables. Ne pas requalifier un service en `planned` pour supprimer artificiellement une panne. `aistor` et `wordpress` restent des exceptions **planifiées** assumées.

## 6. Identité canonique et dettes d'exposition

- `homeassistant` n'est pas rebaptisé en `home-assistant` dans le catalogue. Suivre [la migration contrôlée](openwebui-homeassistant-canonical-rename.md) avec rollback et preuve du middleware.
- `joplin.int.albandrieu.com` est privé tandis que la déclaration historique indique `external=true` ; ne pas publier un hostname automatiquement pour faire passer une assertion.
- `hello.int` reste `warn` par décision ; `s3.int` demeure une exception jusqu'à la migration du backend d'état OpenTofu.

## 7. Réception globale

Depuis les réseaux autorisés, comparer des captures **datées et sur le même SHA** de `/healthz`, `/api/homelab/health`, `/api/homelab/status` et `/sickz`. Le second `/sickz` dans la minute doit être servi du cache. Contrôler que les `warn` WAF volontaires ne sont pas affichés comme `DOWN`, et que toutes les Apps requises ont une preuve indépendante de leur santé.

**Clôture :** résultats `ACCEPTED (runtime)` ; sinon maintenir `NOT_VERIFIED`. La PR et la quality gate ne remplacent pas ce contrôle.
