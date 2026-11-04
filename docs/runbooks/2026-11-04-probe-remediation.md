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
2. Cloudflare : routes (§1), Access (§2–§3), WAF (§4).
3. FastAPI Cloud : variables (§5).
4. TrueNAS : Graylog, Lidarr, Homarr (§6).
5. Rejouer la campagne de sondes (§8).

## 1. Routes Tunnel des services internes

**Tunnel partagé (`tunnel.tofu`)** : 23 routes de services déclarés
`external=false` sont retirées du code (20 refusées au bord en 403
Default-Deny, plus `garage-admin`, `bichon`, `clamav` dont la politique
documentée interdit toute exposition Tunnel). Le module étant encore en
adoption *import-first*, le premier `plan` doit montrer **uniquement** ces
23 suppressions d'`ingress` en plus du renommage `sample` déjà codé.
Toute autre différence : arrêter et réconcilier.

```bash
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare plan -out=routes.tfplan
# relire : seules ces 23 routes disparaissent (et le renommage déjà prévu)
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare apply routes.tfplan
```

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

Pour chaque application : *Access → Applications → Policies* → ajouter la
politique réutilisable **Service Auth** qui inclut le jeton de
l'observateur (même jeton que `CLOUDFLARE_ACCESS_SERVICE_TOKEN_*` côté
FastAPI Cloud). Action `Service Auth`, pas `Bypass`. Faire de même pour les
applications de `ddns-updater`, `ollama`, `ollama-gpu` (désormais déclarées
externes derrière Access) et `sample` (observateur TrueNAS ajouté au
catalogue).

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

## 4. WAF / Bot : challenge sur l'egress FastAPI Cloud

Keycloak (`/.well-known/openid-configuration`) et LiteLLM
(`/health/liveliness`) reçoivent la page challenge « Just a moment… » depuis
FastAPI Cloud, alors qu'un autre egress externe obtient 200. Les sondes les
classent désormais `warn` « origin health is unverified » (et non plus
« injoignable »), sans les déclarer saines.

1. *Security → Events* : filtrer `host` = `keycloak.albandrieu.com` /
   `litellm.albandrieu.com`, action *Managed Challenge*, pour identifier la
   règle (règle personnalisée, Bot Fight Mode, réputation IP/ASN).
2. Ajouter une exception **étroite** : chemin exact de la sonde ET présence
   de l'en-tête `CF-Access-Client-Id`, puis exiger le Service Auth (§2) qui
   valide réellement le jeton. Ne jamais exempter tout le hostname ni une
   plage d'IP Cloud (egress non contractuel).
3. Si la règle est Bot Fight Mode (non exemptable), déplacer la preuve vers
   l'observateur TrueNAS (LAN) plutôt que d'élargir l'exception.

**Preuve :** `/healthz` → `checks.keycloak.reachable=true`,
`checks.litellm.reachable=true`, sans `edge_block`.

## 5. FastAPI Cloud : variables (opérateur autorisé)

Ne pas coller de valeur dans un terminal partagé ni dans un ticket.

```bash
mise exec -- uv run fastapi cloud env list          # noms seulement
mise exec -- uv run fastapi cloud env set --secret OVH_APPLICATION_KEY   # etc.
```

- **OVH (`openstack_me`)** : l'API répond « This credential does not
  exist ». Régénérer le jeu OVH (application key/secret + consumer key) en
  lecture seule, mettre à jour les secrets, redéployer.
- **pfSense** : la politique WAN réserve TCP/10443 à `PFSENSE_ADMIN_WAN`
  ([roadmap](../pfsense-wan-exposure-roadmap.md)). Positionner
  `PFSENSE_AUTHENTICATED_PROBES_ENABLED=false` sur FastAPI Cloud : la
  posture pfSense est observée par l'instance TrueNAS (LAN). Sans ce
  réglage, chaque tentative coûte ~6 s de `ConnectTimeout`.
- **Tavily** : rien à changer ; la sonde utilise maintenant `GET /usage`.

**Preuve :** `/healthz` → `openstack_me.reachable=true`,
`tavily.reachable=true` ; `pfsense` en `transport_only`/skip explicite.

## 6. TrueNAS : Graylog, Lidarr, Homarr

Lecture seule d'abord (pas de redémarrage avant d'avoir la cause) :

```bash
sudo midclt call app.query '[["name","in",["graylog","lidarr","homarr"]]]' \
  | jq -r '.[] | [.name, .state] | @tsv'
sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -E 'ix-(graylog|lidarr|homarr)'
sudo docker logs --tail 200 <conteneur>   # chercher OOM, migration, volume, port
```

- **Homarr CRASHED** : corriger la cause dans les logs (volume, migration
  de base, variable manquante) avant `sudo midclt call -j app.start homarr`.
- **Graylog / Lidarr STOPPED** : vérifier les dépendances (OpenSearch /
  MongoDB pour Graylog) puis `sudo midclt call -j app.start <app>`.

**Preuve :** `/api/homelab/runtime` → `RUNNING`, conteneur `running` ;
`/api/homelab/health` → service `ok` avec preuve HTTP fraîche.

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
