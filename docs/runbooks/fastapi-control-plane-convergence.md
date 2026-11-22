# Convergence FastAPI TrueNAS — H04, H20, H21, H14

## Périmètre edge (F17)

Le routeur privé `sample.int.albandrieu.com` est retiré d'`apps/sample/compose.yml` après le redéploiement FastAPI confirmé par l'opérateur ; `terraform/cloudflare/tunnel.tofu` envoie le public directement au port 8091. Conserver ce direct pour rollback/probes autorisées, pas d'ouverture WAN. Réutiliser `apps/traefik/dynamic/crowdsec.yml`, log JSON Traefik et acquisition `apps/crowdsec/acquis.d/traefik.yaml`. Le bouncer v1.8.1 préparé n'est attaché à aucun router: réception canary hello avant FastAPI. CrowdSec AppSec est un listener/règles WAF différent du blocage IP LAPI; acquis.d/appsec.yaml, les deux collections et le profil middleware `crowdsec-appsec@file` sont maintenant CODED, attachés exclusivement aux routeurs canary public FastAPI. Vérifier version/rules/metrics, listener interne 7422 non publié, clé existante, requêtes bénignes et tests WAF positifs/négatifs avant bascule. Ratelimit Traefik middleware natif avec quotas établis par métriques (séparer webhooks et UI, limiter sur IP réellement prouvée, ne pas bloquer le tunnel entier). Pas de nouveau rate limiter applicatif.

Canary: maintenir les routeurs publics Traefik opt-in, sans réintroduire de route privée FastAPI ; prouver TLS/Host/SNI, headers Cloudflare Access JWT intacts, trusted forwarded headers et peer cloudflared exact (pas tous les réseaux privés), HMAC et absence de spoof; observer metrics Traefik/CrowdSec, vérifier charge UI et 429; changer la route Tunnel via plan signé et tester externe. Ne pas faire confiance à insecureSkipVerify global existant: revoir TLS origine et CA par service. Retirer accès direct seulement après preuves de sondes et rollback. Cloudflare Access exception path webhook reste off.

WAF edge: data sources `terraform/cloudflare/waf-inventory.tofu` opt-in, provider 5.28.1; `TF_VAR_waf_inventory_enabled=true` sur plan OpenTofu opérateur (si Terragrunt transmet la valeur; sinon ajouter input temporaire local hors Git). Inventorier rulesets existants et détails via lecture autorisée, comparer plan avant/après, préserver règles/challenges/skip existants et refs, aucune nouvelle règle Cloudflare rate limit standard; utiliser WAF custom pour contrôle méthode/path/IP GitHub, managed protection selon plan. Cloudflare et CrowdSec AppSec complémentaires, pas de double rate limit. Import-first, jamais d'apply automatique; un ruleset zone contient toutes les règles de sa phase. Les données brutes restent dans le state Garage privé. Runtime/plan NOT_RUN.

## H20 / F15 et F18

FastAPI #449: pending-only inventory PostgreSQL, pas de mutation approbation. Reprendre mécanisme signature Entra, durable SQL CAS et outbox, Redis cache; pas d'usage de legacy note.completed, prompt libre ni RPUSH/BLPOP comme autorité. Compose fournit rôle DB limité, réutilise backups/TLS et worker. Slack: app existante nabla-openclaw Socket Mode, intégration sortante via interface approuvée, aucun nouveau bot/xapp, canal fixe et notifications minimales; son installation/jetons restent à confirmer avec OpenClaw owner. Pas d'approbation depuis Slack.

## H21 / F16

Réutiliser GReader FreshRSS, identité privée séparée de securitypublic, idéalement compte FastAPI dédié, catalogue V2 (noms/types/tags sans IP, URL privée), Langfuse prompt source versionné dans FastAPI et publication self-hosted, LiteLLM TrueNAS virtual key distincte et alias modèle allowlist, pas de fallback fournisseur. Tester lecture/déduplication/cache/absence de prompt injection et rétention, pas de changement abonnement/lecture public. Pas de nouveau scraper, scheduler ou stack IA avant inventaire.

## H14 / F06/F07/F10/F15 — dashboard evidence-first

Réutiliser `apps/grafana/config/grafana-dashboards.yml`, dossiers provisionnés, `apps/prometheus/rules/traefik.rules.yml`, séries Traefik Prometheus déjà activées, cAdvisor et exporter PostgreSQL/Redis si réellement présents; Home Operations + health board + heatmap FastAPI existants. GitHub Actions et DefectDojo natifs pour détails. Avant design: dresser matrice question -> métrique exacte/labels/recording rule -> UID/panel -> fraîcheur/absence -> réutiliser/lien/écart. N'ajouter un panel/série qu'après vérification live des séries, coûts, cardinalité et accès OWNER. Aucune mesure ou disponibilité affirmée depuis Git.

References: https://docs.crowdsec.net/docs/appsec/quickstart/traefik/ ; https://developers.cloudflare.com/terraform/additional-configurations/waf-custom-rules/ ; https://github.com/cloudflare/terraform-provider-cloudflare/blob/v5.28.1/docs/data-sources/rulesets.md .

**Réception opérateur (21/11, après mise à jour CrowdSec)** :
`appsec_collections=PASS_INSTALLED`, métriques AppSec disponibles,
7422 non publié et `traefik_network` joint. Ce sont des preuves de
préparation, **pas encore** une preuve de blocage HTTP 403 ni de
protection publique. La frontière dashboard/métriques Traefik reste
`NOT_VERIFIED_REQUIRE_AUTH_AND_METRICS_RECEIPT`.
Le certificat vérifié pour le canary utilise désormais le SNI
`traefik.int.albandrieu.com` (certificat interne Traefik), et le
Host de routage reste `fastapi-sample.albandrieu.com`.
La variable `APP_DOMAIN` FastAPI vaut `fastapi-sample.albandrieu.com`, le
domaine du déploiement, depuis le 22/11/2026, après vérification dans
l'application : libellé, démo socket et clé Redis de l'historique des
propriétaires (qui repart à vide s'il est activé).

## Public Traefik canary CODED (21/11/2026)

`apps/sample/compose.yml` now has a dedicated public-host router with
`crowdsec@file` (existing bouncer, not AppSec WAF) plus native Traefik
rateLimit. Ordinary UI: **30/s, burst 100**; GitHub signed POST path has a
separate precedence router: **2/s, burst 10**. These are provisional shared
source-IP budgets, not measured deployment capacity; confirm actual
Cloudflare/Traefik IP provenance and traffic before applying. Neither route
recreates the retired `sample.int.albandrieu.com` router.

`terraform/cloudflare/tunnel.tofu` has an explicit boolean switch
`fastapi_sample_tunnel_via_traefik=false` by default. The reviewed canary
target is `https://traefik:443` (Traefik joins cloudflared's own network
`ix-cloudflared_default`), `origin_server_name =
traefik.int.albandrieu.com` and `http_host_header =
fastapi-sample.albandrieu.com` with TLS verification. It must not silently
set `no_tls_verify=true`. **Shared tunnel state:** confirm the *entire* plan
does not reconfigure unrelated hostnames and review any changes from null
`origin_request` attributes before an apply; if default plan is nonzero,
do NOT apply or claim a zero-impact default. Run local Traefik Host+SNI canary,
MFA OWNER, signed and unsigned webhook, rate limit, 403, 404, headers, LAPI
and plugin health first. CrowdSec AppSec canary is now CODED but NOT_DEPLOYED; its fail-closed profile must pass runtime tests before enabling the Tunnel switch. Observe
Cloudflare WAF/rulesets (import-first), never replace an existing phase.
After canary, separately turn on the switch with approved plan/rollback,
and only then review direct :8091 restriction for non-probe clients.
Provider init/plan, Docker compose validation and live acceptance NOT_RUN.

### AppSec WAF CODED — nouvelle frontière canary (21/11/2026)

`apps/crowdsec/acquis.d/appsec.yaml` active le moteur AppSec 7422 sur le réseau Docker, via les collections officielles. Aucun port hôte `7422`. `apps/traefik/dynamic/crowdsec.yml` conserve `crowdsec@file` pour LAPI streaming et crée `crowdsec-appsec@file` pour streaming + AppSec v1.8.1 ; les paramètres LAPI restent identiques entre profils. Les routes public et webhook dans `apps/sample/compose.yml` emploient le profil AppSec, en fail-closed lorsque ce composant est inaccessible. Tant que le Tunnel garde `:8091` (switch `false`), cela n'impacte pas la production publique. **Le probe officiel CrowdSec déclenche une alerte, pas nécessairement 403.** Pour prouver le WAF, comparer une requête de test bloquée selon une règle canary dédiée approuvée et les requêtes légitimes non bloquées, avec compteurs `cscli metrics show appsec` et traces Traefik expurgées. En cas d'erreur, ne PAS basculer le Tunnel ; envisager rollback de l'attachement. Étape suivante : CrowdSec AppSec métriques Prometheus et UX OWNER par réutilisation des séries actuelles. Runtime NOT_RUN.

### Commandes de réception AppSec (read-only, 21/11)

```bash
# Exécuter dans le repo Compose sur workstation/TrueNAS
bash scripts/truenas/diagnose-crowdsec-appsec.sh --check
# Exécuter uniquement sur TrueNAS où Docker est accessible ; ne change pas l'état
sudo bash scripts/truenas/diagnose-crowdsec-appsec.sh --runtime
```

Le contrôle runtime distingue explicitement **configuration/collections/metrics** de la **preuve de blocage HTTP**. Vérifier le portail de métriques `cscli metrics show appsec` avant et après la sonde bénigne `/crowdsec-test-NtktlJHV4TfBSK3wvlhiOBnl` (officielle ; crée une alerte, pas obligatoirement un 403), puis un test de blocage contrôlé contre le canary isolé. Comparer les traces (sans JWT ni secret) et tester le webhook GitHub signé avant toute ouverture. L'étape Docker AppSec et les règles WAF peuvent consommer plus que la limite CrowdSec actuelle de 384 MiB : surveiller RSS/OOM/latence et adapter le budget seulement avec mesures. Les logs de Traefik conservent le User-Agent ; veiller à sa minimisation au regard des attaques qui injectent des chaînes sensibles. Tester `429` avec trafic non destructif, vérifier LAPI fail-open existant et WAF fail-closed sur seul canary. `fastapi_sample_tunnel_via_traefik` reste `false` par défaut. Aucune preuve de bon fonctionnement runtime n'est annoncée.

### Preuve WAF 403 contrôlée (canary, pas le trafic public)

La nouvelle règle `nabla/fastapi-canary` ne correspond qu'à `GET /__nabla_appsec_canary_7de17a3fb1134292` ; elle est installée dans les répertoires AppSec `nabla/` et référencée après `crowdsecurity/appsec-default`. Montages dédiés en lecture seule. Vérifier `cscli appsec-rules list` et `cscli appsec-configs list`, redémarrer CrowdSec si nécessaire selon le runbook, avant test. Tester depuis un conteneur curl éphémère sur `traefik_network` après confirmation de la résolution et de la chaîne TLS, pour que toute décision CrowdSec éventuelle concerne seulement son adresse de test. Exécuter une requête GET au chemin canary avec SNI `traefik.int.albandrieu.com` et en-tête Host `fastapi-sample.albandrieu.com`. Réponse **403 attendue** pour cette règle ; distinguer `403` AppSec confirmé par métriques/règle et `403` provenant d'Access ou de FastAPI. Comparer une requête témoin `/health`, vérifier les compteurs `cscli metrics show appsec`, les logs de règle sans contenu sensible et l'absence de blocage de POST signé /webhooks/github. La règle canary ne protège aucune route métier ; elle ne remplace pas le test des règles Hub en production. Test réel NOT_RUN.

### P0 — Traefik admin boundary (21/11 ; blocker pour H04)

Le code existant porte `--api.insecure=true` avec le port dashboard `8080` publié, tandis que `apps/prometheus/prometheus.yml` récupère Traefik sur `172.17.0.24:8080`. Les API Traefik peuvent révéler la configuration dynamique du plugin, notamment la clé LAPI rendue depuis le dotenv (`crowdsecLapiKey`). **Ne pas déclarer le WAF comme une protection publique reçue tant que cette frontière n'est pas traitée.** Le diagnostic runtime signale explicitement `NO_GO_UNAUTHENTICATED_API` si le processus Traefik fonctionne encore ainsi. Ne pas simplement mettre `--api.insecure=false` sans migrer la cible Prometheus : cela casserait les métriques existantes. Étape de migration : activer entrypoint `metrics` déjà publié sur `8082`, configurer `--metrics.prometheus.entrypoint=metrics`, transférer le scrape `:8080` → `:8082`, placer `api@internal` derrière un routeur LAN authentifié avec politique d'accès stricte, puis fermer la publication du port `8080` ; réception des dashboards et série Prometheus avant suppression. Également réévaluer `--serversTransport.insecureSkipVerify=true` (désactivation TLS backend globale) et la remplacer par un transport TLS vérifié ciblé après inventaire. Aucune de ces mutations n'est appliquée ici, pour préserver l'observabilité jusqu'à preuve. **Blocking runtime acceptance gate CODED**.

### Correctif IaC Traefik admin + Prometheus (CODED, NOT_APPLIED)

L'API Traefik cesse d'être exposée via `--api.insecure=true` ; un routeur explicite `api@internal` sur `traefik.int.albandrieu.com` ne répond qu'aux préfixes `/api` et `/dashboard` derrière BasicAuth via le provider fichier (secret runtime `TRAEFIK_DASHBOARD_BASIC_AUTH` existant). Le port hôte `8080` disparaît. La métrique Prometheus passe à un entrypoint `:8082` lié au LAN `172.17.0.24`, et la configuration `apps/prometheus/prometheus.yml` est mise à jour simultanément. Le log Traefik passe de DEBUG à INFO pour éviter d'exposer inutilement la configuration du plugin.

**Avant déploiement** : vérifier la matérialisation réelle `TRAEFIK_DASHBOARD_BASIC_AUTH` (format `user:hash`), le DNS split `traefik.int.albandrieu.com`, le certificat TLS DNS-01, `docker compose config` qui doit masquer les valeurs sensibles, et les tests de contrôle 401 sans identifiants / 200 après authentification. Redéployer Traefik **avant** ou en même temps que Prometheus selon la fenêtre de courte indisponibilité acceptée ; le scrape :8080 échouera après le changement Traefik si Prometheus n'est pas encore redéployé. Vérifier `up{job=\"traefik\"}=1` et les séries/règles Grafana existantes sur :8082 avant de conclure. Le risque global `serversTransport.insecureSkipVerify=true` reste un chantier distinct et non corrigé ici. L'adresse Docker socket brute reste également à auditer. Le WAF public reste derrière le switch Tunnel `false`.

La route d'administration durcie applique maintenant un IPAllowList Traefik **sur le peer TCP réel**, avant BasicAuth, pour les LAN `192.168.1.0/24` (Freebox) et `172.17.0.0/24` (ancien homelab). Les proxys Cloudflare ne sont pas dans la liste; aucun X-Forwarded-For non authentifié n'élargit l'accès. Si les adresses de la workstation changent, mettre à jour ces CIDR après vérification du peer réel ; prévoir accès de secours LAN avant déploiement. Prouver refus depuis un réseau non LAN, avec et sans entête X-Forwarded-For simulé, et autorisation LAN avec BasicAuth valide ; ne pas publier le dashboard sur Cloudflare. Les deux contrôles (IP et BasicAuth) sont nécessaires.
