# Convergence FastAPI TrueNAS — H04, H20, H21, H14

## Périmètre edge (F17)

Le routeur existant `apps/sample/compose.yml` expose `sample.int.albandrieu.com` via Traefik; `terraform/cloudflare/tunnel.tofu` envoie le public directement au port 8091. Conserver ce direct pour rollback/probes autorisées, pas d'ouverture WAN. Réutiliser `apps/traefik/dynamic/crowdsec.yml`, log JSON Traefik et acquisition `apps/crowdsec/acquis.d/traefik.yaml`. Le bouncer v1.8.1 préparé n'est attaché à aucun router: réception canary hello avant FastAPI. CrowdSec AppSec est un listener/règles WAF différent du blocage IP LAPI; acquis.d/appsec.yaml, les deux collections et le profil middleware `crowdsec-appsec@file` sont maintenant CODED, attachés exclusivement aux routeurs canary public FastAPI. Vérifier version/rules/metrics, listener interne 7422 non publié, clé existante, requêtes bénignes et tests WAF positifs/négatifs avant bascule. Ratelimit Traefik middleware natif avec quotas établis par métriques (séparer webhooks et UI, limiter sur IP réellement prouvée, ne pas bloquer le tunnel entier). Pas de nouveau rate limiter applicatif.

Canary: créer route Traefik public sans supprimer route LAN; prouver TLS/Host/SNI, headers Cloudflare Access JWT intacts, trusted forwarded headers et peer cloudflared exact (pas tous les réseaux privés), HMAC et absence de spoof; observer metrics Traefik/CrowdSec, vérifier charge UI et 429; changer la route Tunnel via plan signé et tester externe. Ne pas faire confiance à insecureSkipVerify global existant: revoir TLS origine et CA par service. Retirer accès direct seulement après preuves de sondes et rollback. Cloudflare Access exception path webhook reste off.

WAF edge: data sources `terraform/cloudflare/waf-inventory.tofu` opt-in, provider 5.28.1; `TF_VAR_waf_inventory_enabled=true` sur plan OpenTofu opérateur (si Terragrunt transmet la valeur; sinon ajouter input temporaire local hors Git). Inventorier rulesets existants et détails via lecture autorisée, comparer plan avant/après, préserver règles/challenges/skip existants et refs, aucune nouvelle règle Cloudflare rate limit standard; utiliser WAF custom pour contrôle méthode/path/IP GitHub, managed protection selon plan. Cloudflare et CrowdSec AppSec complémentaires, pas de double rate limit. Import-first, jamais d'apply automatique; un ruleset zone contient toutes les règles de sa phase. Les données brutes restent dans le state Garage privé. Runtime/plan NOT_RUN.

## H20 / F15 et F18

FastAPI #449: pending-only inventory PostgreSQL, pas de mutation approbation. Reprendre mécanisme signature Entra, durable SQL CAS et outbox, Redis cache; pas d'usage de legacy note.completed, prompt libre ni RPUSH/BLPOP comme autorité. Compose fournit rôle DB limité, réutilise backups/TLS et worker. Slack: app existante nabla-openclaw Socket Mode, intégration sortante via interface approuvée, aucun nouveau bot/xapp, canal fixe et notifications minimales; son installation/jetons restent à confirmer avec OpenClaw owner. Pas d'approbation depuis Slack.

## H21 / F16

Réutiliser GReader FreshRSS, identité privée séparée de securitypublic, idéalement compte FastAPI dédié, catalogue V2 (noms/types/tags sans IP, URL privée), Langfuse prompt source versionné dans FastAPI et publication self-hosted, LiteLLM TrueNAS virtual key distincte et alias modèle allowlist, pas de fallback fournisseur. Tester lecture/déduplication/cache/absence de prompt injection et rétention, pas de changement abonnement/lecture public. Pas de nouveau scraper, scheduler ou stack IA avant inventaire.

## H14 / F06/F07/F10/F15 — dashboard evidence-first

Réutiliser `apps/grafana/config/grafana-dashboards.yml`, dossiers provisionnés, `apps/prometheus/rules/traefik.rules.yml`, séries Traefik Prometheus déjà activées, cAdvisor et exporter PostgreSQL/Redis si réellement présents; Home Operations + health board + heatmap FastAPI existants. GitHub Actions et DefectDojo natifs pour détails. Avant design: dresser matrice question -> métrique exacte/labels/recording rule -> UID/panel -> fraîcheur/absence -> réutiliser/lien/écart. N'ajouter un panel/série qu'après vérification live des séries, coûts, cardinalité et accès OWNER. Aucune mesure ou disponibilité affirmée depuis Git.

References: https://docs.crowdsec.net/docs/appsec/quickstart/traefik/ ; https://developers.cloudflare.com/terraform/additional-configurations/waf-custom-rules/ ; https://github.com/cloudflare/terraform-provider-cloudflare/blob/v5.28.1/docs/data-sources/rulesets.md .

## Public Traefik canary CODED (21/11/2026)

`apps/sample/compose.yml` now has a dedicated public-host router with
`crowdsec@file` (existing bouncer, not AppSec WAF) plus native Traefik
rateLimit. Ordinary UI: **30/s, burst 100**; GitHub signed POST path has a
separate precedence router: **2/s, burst 10**. These are provisional shared
source-IP budgets, not measured deployment capacity; confirm actual
Cloudflare/Traefik IP provenance and traffic before applying. Neither route
changes the existing `sample.int.albandrieu.com` router.

`terraform/cloudflare/tunnel.tofu` has an explicit boolean switch
`fastapi_sample_tunnel_via_traefik=false` by default. The reviewed canary
target is `https://172.17.0.24:443`, `origin_server_name =
sample.int.albandrieu.com` and `http_host_header =
fastapi-sample.albandrieu.com` with TLS verification. It must not silently
set `no_tls_verify=true`. **Shared tunnel state:** confirm the *entire* plan
does not reconfigure unrelated hostnames and review any changes from null
`origin_request` attributes before an apply; if default plan is nonzero,
do NOT apply or claim a zero-impact default. Run local Traefik Host+SNI canary,
MFA OWNER, signed and unsigned webhook, rate limit, 403, 404, headers, LAPI
and plugin health first. CrowdSec AppSec is still not enabled. Observe
Cloudflare WAF/rulesets (import-first), never replace an existing phase.
After canary, separately turn on the switch with approved plan/rollback,
and only then review direct :8091 restriction for non-probe clients.
Provider init/plan, Docker compose validation and live acceptance NOT_RUN.

### AppSec WAF CODED — nouvelle frontière canary (21/11/2026)

`apps/crowdsec/acquis.d/appsec.yaml` active le moteur AppSec 7422 sur le réseau Docker, via les collections officielles. Aucun port hôte `7422`. `apps/traefik/dynamic/crowdsec.yml` conserve `crowdsec@file` pour LAPI streaming et crée `crowdsec-appsec@file` pour streaming + AppSec v1.8.1 ; les paramètres LAPI restent identiques entre profils. Les routes public et webhook dans `apps/sample/compose.yml` emploient le profil AppSec, en fail-closed lorsque ce composant est inaccessible. Tant que le Tunnel garde `:8091` (switch `false`), cela n'impacte pas la production publique. **Le probe officiel CrowdSec déclenche une alerte, pas nécessairement 403.** Pour prouver le WAF, comparer une requête de test bloquée selon une règle canary dédiée approuvée et les requêtes légitimes non bloquées, avec compteurs `cscli metrics show appsec` et traces Traefik expurgées. En cas d'erreur, ne PAS basculer le Tunnel ; envisager rollback de l'attachement. Étape suivante : CrowdSec AppSec métriques Prometheus et UX OWNER par réutilisation des séries actuelles. Runtime NOT_RUN.
