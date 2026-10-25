# Garage S3 et LiteLLM — HTTP protégé, santé et exposition

**25 octobre 2026 — runbook de diagnostic, lecture seule.**
Un HTTP 401/403 est une réponse HTTP valide ; ce n'est ni un HTTP 200,
ni une preuve de disponibilité fonctionnelle. Une réponse 403 observée
depuis le LAN ne démontre pas une exposition depuis Internet.

## Contrat par service

| Service | Sonde anonyme | Réponse attendue | Vérification fonctionnelle distincte |
| --- | --- | --- | --- |
| Garage S3 `:3900` | `GET /` LAN | HTTP 401/403 = **auth attendue** (bleu), pas S3 OK | Opération S3 signée, identifiant/permissions limités, aucun secret dans les logs |
| LiteLLM `:4000` | `GET /health` LAN | HTTP 401 = **auth attendue** (bleu), pas modèles OK | `GET /health/liveliness` = 200, puis requête API autorisée et vérification des upstreams |
| LiteLLM Docker | `apps/litellm/compose.yml` | `healthcheck` interne sur `/health/liveliness`, intervalle 30 s | `docker inspect` révèle `healthy/unhealthy/starting` si le conteneur est déployé |
| Gatus | `apps/gatus/config/config.yml` | **TCP CONNECTED** sur Garage `:3900` et LiteLLM `:4000` | Les deux sondes TCP ne valident ni auth ni écriture S3 ou inférence LLM |

Le code source est le contrat ici : Garage et LiteLLM utilisent des sondes
**TCP** Gatus, déjà déclarées dans le dépôt Compose. Ne remplacez pas leurs
conditions TCP par `[STATUS] == 200` sur des endpoints protégés.
Les conditions des endpoints HTTP autres services doivent être révisées
**individuellement**, avec une route de santé dédiée si l'application en propose.

## Exécuter le diagnostic sur TrueNAS

```bash
just protected-http-diagnostics
just protected-http-contracts
```

Le script `scripts/truenas/diagnose-protected-service-http.py --check`
ne touche qu'à trois URLs LAN fixes : Garage `/`, LiteLLM
`/health` et `/health/liveliness`.
Il désactive les proxys, refuse les redirections, borne le timeout à
4 secondes, n'envoie aucun secret et n'affiche aucun corps HTTP.
Il lit uniquement `Docker.State.Health.Status` pour les conteneurs
`garage` et `litellm` lorsqu'ils existent. Une identité Docker
introuvable ou sans healthcheck reste `not_observed/not_configured`.

Une sortie `auth_required_expected` signifie **service HTTP a répondu
par une barrière d'authentification**. La sortie `liveness_up` atteste
uniquement le succès de la route de vivacité au moment de l'observation.
Ce n'est pas un test d'inférence LiteLLM ni une preuve S3 signée.

## Statut d'exposition : plan distinct

Le **Policy Failed** de `/sickz` concerne une contradiction entre
`external=false` et un ingress réellement observé. Il peut être
légitime et doit rester visible, même si la route répond 401/403 :
une authentification n'est pas une preuve que l'endpoint n'est pas publié.
À l'inverse, un 403 provenant de `172.17.0.24:3900` dans le LAN ne
suffit **pas** à prouver une exposition publique.

Vérifier séparément les déclarations, routes Traefik/Cloudflare et
observations outside-in. Ne pas créer de tunnel public, contourner Access
ou publier un endpoint admin pour obtenir un voyant vert.

## Normalisation future de toutes les sondes

P1 : exporter un contrat explicite par service :
`service_id`, `vantage_point`, `protocol`, `target`,
`expected_anonymous_status`, `healthcheck_kind`,
`functional_check`, `freshness` et `security_policy`.

La définition Docker `HEALTHCHECK`, si présente, peut fournir un
signal local supplémentaire. Elle ne remplace pas les sondes Gatus,
la validation S3/LLM authentifiée, la politique d'exposition ni
l'observation depuis FastAPI Cloud. Une absence de healthcheck ne doit
jamais être convertie en `healthy`.
