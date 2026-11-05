# Remédiation des sondes FastAPI Sample — 4 novembre 2026

Origine : comparaison en lecture seule FastAPI Cloud / local (04/11,
19:10–19:20 UTC, `v0+1.27.0`). Ce runbook liste les corrections **non
codifiables depuis le dépôt** ; les corrections de code et de catalogue sont
dans les PR associées (fastapi-sample : sondes Tavily/Keycloak/LiteLLM et
cache `/sickz` ; nabla-compose : catalogue et `tunnel.tofu`).

Règle : une sonde ne passe au vert que lorsque la cause réelle est corrigée.
Ne jamais modifier une politique de sonde, un catalogue ou un seuil pour
masquer un échec. Chaque étape se termine par sa preuve d'acceptation.

## 0. Ordre recommandé

1. Fusionner les PR code/catalogue (le runtime lit le catalogue de `master`).
2. Cloudflare : routes (§1), Access (§2–§3).
3. FastAPI Cloud : variables (§5).
4. TrueNAS : Graylog, Lidarr, Homarr (§6).
5. Rejouer la campagne de sondes (§8).

## 1. Routes Tunnel des services internes

**Tunnel partagé (`tunnel.tofu`)** : 23 routes de services déclarés
`external=false` sont retirées du code (20 refusées au bord en 403
Default-Deny, plus `garage-admin`, `bichon`, `clamav` dont la politique
documentée interdit toute exposition Tunnel). Le module étant encore en
adoption *import-first*, le premier `plan` doit montrer **uniquement**, sur
`cloudflare_zero_trust_tunnel_cloudflared_config.homelab` :

- les 23 suppressions d'`ingress` ci-dessus ;
- la suppression de la route `litellm.albandrieu.com` (05/11 : LiteLLM n'est
  plus publié sur Internet) ;
- pour `keycloak.albandrieu.com`, une route limitée au `path`
  `^/(realms|resources|\.well-known)/` puis un `http_status:404` pour le reste
  (`/admin/`, `/metrics`, `/health`, racine), selon
  [la doc Keycloak](https://www.keycloak.org/server/reverseproxy) ;
- le renommage `sample` → `fastapi-sample` déjà codé.

Toute autre différence : arrêter et réconcilier. Le plan s'exécute depuis la
workstation LAN (jeton Cloudflare **lecture** et clés de l'état Garage depuis
Vaultwarden, jamais affichés) ; l'apply exige l'accord explicite du
propriétaire après relecture du plan.

```bash
export BW_SESSION="$(bw-unlock)"   # puis exporter CLOUDFLARE_API_TOKEN et AWS_* sans les afficher
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare init -reconfigure
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare plan -out=routes.tfplan -no-color \
  | tee /tmp/cloudflare-plan.txt
# relire /tmp/cloudflare-plan.txt (aucun secret dans un plan Tunnel/DNS/Access)
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare apply routes.tfplan
bw lock
```

Après l'apply, supprimer dans le dashboard l'enregistrement DNS
`litellm.albandrieu.com` (non géré par ce module) et l'application Access
LiteLLM devenue inutile.

Procédure complète et accord propriétaire : [README du module](../../terraform/cloudflare/README.md).
Au moment du renommage `sample` → `fastapi-sample`, mettre aussi à jour
l'entrée `fastapi-sample` de `catalog/homelab-services.json`.

**Tunnel de la workstation (dashboard, non codifié)** : supprimer les Public
Hostnames `anythingllm-albandrieu`, `litellm-albandrieu`,
`plumber-albandrieu`, `portracker-albandrieu`, `reactive-albandrieu` et
`stirling-albandrieu` (`*.albandrieu.com`), tous `external=false`.

**Preuve :** `/sickz` ne contient plus de ligne
`external=false but a Cloudflare Tunnel ingress exists` ; ces services
passent `ok` (`not reachable from the external probe`).

## 2. Access : jeton de service de l'observateur

L'observateur FastAPI Cloud présente son Service Token, mais Access le
refuse sur ces applications (`Service Token did not pass Access`) :
2fauth, adguardhome, affine, clickhouse, freshrss, garage (Web UI), gatus,
grafana, heimdall, homarr, ittools, karakeep, keycloak, langfuse,
languagetool, litellm, minio, openwebui, plumber-api-albandrieu,
prometheus, scrutiny, searxng, uptime-kuma.

Prérequis (une fois, dashboard) : une politique **réutilisable** d'action
`Service Auth` (`decision=non_identity`) qui inclut le jeton de
l'observateur (même client que `CLOUDFLARE_ACCESS_SERVICE_TOKEN_*` côté
FastAPI Cloud). Jamais `Bypass`.

Le script `scripts/cloudflare/attach-observer-service-auth.py` dérive la liste
des hôtes du catalogue (`external=true`, derrière Tunnel, Access non désactivé,
hors `*.int`) — `litellm` n'en fait plus partie — et n'ajoute que cette
politique, en conservant les autres réglages de chaque application. Il est en
lecture seule par défaut ; une application encore en politiques *inline* est
signalée et laissée intacte.

```bash
export CLOUDFLARE_ACCOUNT_ID=bdfe00eeee5845782ab91adfbff71ee1
export CLOUDFLARE_API_TOKEN=...   # Access: Apps and Policies Edit, depuis Vaultwarden
python3 scripts/cloudflare/attach-observer-service-auth.py --policy-id <uuid>          # check
python3 scripts/cloudflare/attach-observer-service-auth.py --policy-id <uuid> --apply  # après relecture
```

**Preuve :** dans `/api/homelab/health`, `public_probe_results[*]` de ces
services : `cloudflare_service_token_access_passed=true`, plus
d'`AUTH_FAILED`, `origin_reached=true`.

## 3. Vaultwarden : restreindre le bypass « Everyone »

Constat : bypass Access sur **tout** `vaultwarden.albandrieu.com`.
Cible : coffre web et `/admin` derrière Access ; bypass limité aux chemins
des clients Bitwarden.

1. Conserver l'application Access du hostname complet avec la politique
   `nabla` (Allow) et retirer le bypass « Everyone » de cette application.
2. Créer des applications Access **par chemin** avec bypass uniquement pour
   `/api/*`, `/identity/*`, `/notifications/*`, `/icons/*` et `/alive`.
   Access applique l'application au chemin le plus spécifique.
3. Ne jamais mettre `/admin*` ni `/` en bypass ; garder `ADMIN_TOKEN`.
4. Tester **avant** de supprimer l'ancien bypass : synchronisation d'un
   client mobile et d'un client desktop hors LAN, notifications temps réel,
   puis échec attendu (302 Access) sur `https://vaultwarden.albandrieu.com/`
   sans session.

**Preuve :** ligne Vaultwarden de `/sickz` en `warn` « path-scoped public
bypass » (comme n8n), plus en `fail` « Everyone bypass ».

## 4. Keycloak / LiteLLM : exposition et challenge Cloudflare

Keycloak (`/.well-known/openid-configuration`) et LiteLLM
(`/health/liveliness`) reçoivent la page challenge « Just a moment… » depuis
FastAPI Cloud, alors qu'un autre egress externe obtient 200.

**Décision propriétaire (05/11/2026) : aucune exception WAF/Bot.** Depuis
FastAPI Cloud, ces deux sondes restent `warn` « origin health is
unverified » (`edge_block=challenge`) : c'est l'état attendu, pas une panne.
La preuve de santé vient de l'observateur TrueNAS (LAN), qui ne traverse pas
le bord Cloudflare.

**Décision propriétaire (05/11/2026, suite) :** LiteLLM n'est plus publié
sur Internet (route Tunnel retirée, `external=false`) ; Keycloak ne publie que
ses endpoints de production (`/realms/`, `/resources/`, `/.well-known/`), son
interface `/admin/` reste interne. La doc Keycloak recommande aussi de garder
`/realms/master/` interne : c'est aujourd'hui le seul realm utilisé, il reste
donc publié tant qu'un realm applicatif dédié n'a pas été créé et les clients
migrés (suite à donner). FastAPI Sample ne sonde plus LiteLLM depuis Internet
(URL vide par défaut, URL LAN sur TrueNAS).

**Preuve :** sur l'instance TrueNAS, `/healthz` →
`checks.keycloak.reachable=true` et `checks.litellm.reachable=true` ;
depuis Internet, `https://keycloak.albandrieu.com/admin/` → 404 et
`/realms/master/.well-known/openid-configuration` → réponse Access ou 200.

## 5. FastAPI Cloud : variables (opérateur autorisé)

Ne pas coller de valeur dans un terminal partagé ni dans un ticket.

```bash
mise exec -- uv run fastapi cloud env list          # noms seulement
mise exec -- uv run fastapi cloud env set --secret OVH_APPLICATION_KEY   # etc.
```

- **OVH (`openstack_me`) — désactivé le 05/11/2026** : la sonde est ignorée
  par défaut (`OVH_API_PROBE_ENABLED=true` pour la réactiver après avoir
  régénéré un jeu de clés OVH en lecture seule).
- **pfSense — fait le 05/11/2026** : `PFSENSE_AUTHENTICATED_PROBES_ENABLED=false`
  sur FastAPI Cloud, conformément à la politique WAN qui réserve TCP/10443
  à `PFSENSE_ADMIN_WAN` ([roadmap](../pfsense-wan-exposure-roadmap.md)).
  Constaté en production : `checks.pfsense` en `transport_only`, `skipped`,
  `credential_mode=disabled`, `ingress_block.state=telemetry_disabled`. La
  posture pfSense authentifiée reste observée par l'instance TrueNAS (LAN).
- **Tavily** : rien à changer ; la sonde utilise maintenant `GET /usage`.

**Preuve :** `/healthz` → `openstack_me` `skipped` (désactivé),
`tavily.reachable=true` ; `pfsense` en `transport_only`/skip explicite.

## 6. TrueNAS : Graylog, Lidarr, Homarr

Lecture seule d'abord (pas de redémarrage avant d'avoir la cause) :

```bash
sudo midclt call app.query '[["name","in",["graylog","lidarr","homarr"]]]' \
  | jq -r '.[] | [.name, .state] | @tsv'
sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -E 'ix-(graylog|lidarr|homarr)'
sudo docker logs --tail 200 <conteneur>   # chercher OOM, migration, volume, port
```

- **Homarr CRASHED** : l'interface `homarr` tourne ; c'est le job ponctuel
  `homarr-sync` (`restart: "no"`, réconciliation via l'API Homarr) qui sort
  en erreur et fait passer l'App en `CRASHED`. Lire
  `sudo docker logs --tail 200 homarr-sync` (jeton API Homarr absent ou
  expiré dans `/mnt/cpool/secrets/runtime/homarr/.env.secrets`, API Homarr
  v2.6 modifiée, manifeste généré invalide), corriger la cause, puis
  redéployer l'App (`sudo midclt call -j app.redeploy homarr`). Possible en
  `HOMARR_SYNC_DRY_RUN=true` d'abord pour valider sans écrire.
- **Graylog / Lidarr STOPPED** : vérifier les dépendances (OpenSearch /
  MongoDB pour Graylog) puis `sudo midclt call -j app.start <app>`.

**Preuve :** `/api/homelab/runtime` → `RUNNING`, conteneur `running` ;
`/api/homelab/health` → service `ok` avec preuve HTTP fraîche.

### Migration Home Assistant (App native → `apps/homeassistant`)

`migrate-homeassistant-openwebui-names.sh --apply` refuse volontairement
quand l'App native `home-assistant` est gérée par TrueNAS : la bascule est
manuelle. Points d'arrêt **avant** toute action :

1. `sudo bash scripts/truenas/migrate-homeassistant-openwebui-names.sh --check`
   et `sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check homeassistant`.
2. Comparer le stockage de l'App native
   (`sudo midclt call app.config home-assistant | jq '.storage // .'`, sans
   afficher de secrets) au montage du dépôt
   `/mnt/storage0/home-assistant/config:/config`. S'ils diffèrent : arrêter.
3. L'App native embarque un PostgreSQL (recorder) ; `apps/homeassistant`
   n'en a pas. Sans migration du recorder vers le PostgreSQL partagé (ou
   acceptation écrite de repartir en SQLite), l'historique est perdu : arrêter
   et décider.
4. L'image du dépôt est `:stable` (flottante) alors que l'App native est
   épinglée par digest : épingler la même version avant la bascule.
5. Snapshot ZFS récursif des datasets concernés, puis
   `sudo midclt call -j app.stop home-assistant`, déploiement
   `sudo bash scripts/truenas/bootstrap-repository-runtime.sh --apply homeassistant`,
   vérification (UI, intégrations, historique). Retour arrière : arrêter
   `homeassistant`, `sudo midclt call -j app.start home-assistant`.

**Preuve :** `/api/homelab/status` → `homeassistant` `in_sync` (conteneur
`homeassistant`), plus d'`observed_only` `home-assistant`.

## 6 bis. Liaisons runtime et services à déployer (05/11/2026)

Liaisons corrigées dans `x-nabla` (ajout de l'`appId` déjà utilisé par les
scripts du dépôt, car une App TrueNAS arrêtée n'expose aucun conteneur ;
`containerService` est conservé) : `graylog`, `bitcoind`,
`elasticsearch` → `elastic-search`, `hermes` → `hermes-agent`. Elles
apparaissent désormais `in_sync` avec l'état réel `STOPPED` : ce n'est plus
une erreur de détection, c'est l'arrêt à traiter (§6).

`homeassistant` n'est **pas** relié à l'App native `home-assistant` :
l'identité canonique `homeassistant` est un contrat
(`tests/test_openwebui_canonical_migration.py`) et l'écart se résout par la
migration `scripts/truenas/migrate-homeassistant-openwebui-names.sh`, pas
en modifiant la déclaration.

`aistor` et `wordpress` sont **supprimés** du dépôt (décision propriétaire
du 05/11) : Compose, catalogue, moniteurs, secrets et inventaires. La tâche
de snapshot ZFS `cpool/aistor` est conservée : supprimer le dataset reste une
décision explicite du propriétaire après vérification de son contenu.

Services qui **doivent** tourner sur TrueNAS mais n'y existent pas encore
(restent en échec jusqu'au déploiement, volontairement).

`deploy-security-tooling.sh` a un mode `--check` : l'exécuter et relire
avant `--apply`.

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/deploy-security-tooling.sh --check netbox
sudo bash scripts/truenas/deploy-security-tooling.sh --check dependency-track
sudo bash scripts/truenas/deploy-security-tooling.sh --check plumber
```

`deploy-joplin.sh` et `deploy-scanopy.sh` **appliquent directement** (pas
de mode `--check`) : relire le script, vérifier que la base PostgreSQL
dédiée existe (`bootstrap-joplin-postgres.sh` / `bootstrap-scanopy-postgres.sh`
en `--check`), puis lancer le déploiement avec accord explicite.

`ntopng` n'a pas de script de déploiement dans le dépôt : à créer sur le
modèle de `deploy-scanopy.sh` avant toute installation (l'instance de la
workstation n'est pas concernée).

**Preuve :** `/api/homelab/status` → ces services `in_sync` ;
`/api/homelab/health` → `effective_state=ok` avec preuve HTTP fraîche.

## 7. Décisions restantes du propriétaire

- **Joplin** : déclaré `external=true` (contrat
  `tests/test_homelab_external_services_contract.py`) mais
  `joplin.int.albandrieu.com` n'a pas de DNS public ni de route. Soit
  publier un hostname Tunnel derrière Access, soit changer le contrat.
- **hello.int** : exception directe documentée dans le catalogue ; `/sickz`
  reste en `warn` (dette assumée), pas en `ok`.
- **s3.int** : exception connue jusqu'à la bascule du backend d'état
  OpenTofu ; reste en `fail` tant que la route WAN existe.
- **garage-admin, bichon, clamav** : routes retirées conformément à la
  politique documentée ; les rouvrir exige une exception explicite.

## 8. Preuve d'acceptation globale

Rejouer la même campagne (GET séquentiels, lecture seule) depuis la
workstation LAN contre TrueNAS (`https://sample.int.albandrieu.com`),
FastAPI Cloud et une instance locale, puis comparer `/healthz`,
`/api/homelab/health`, `/api/homelab/status` et `/sickz`. `/sickz` doit
répondre depuis le cache (`probe_cache.source=cache`) au second appel dans
la minute.
