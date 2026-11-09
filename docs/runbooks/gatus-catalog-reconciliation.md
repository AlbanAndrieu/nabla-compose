# Réconciliation Gatus ↔ Backstage v2 (20 octobre 2026)

## Autorités déclaratives

- **Backstage** : `catalog/catalog-info.yaml` et `apps/*/catalog-info.yaml` — identité, dépendances, criticité, état `active/planned/disabled`.
- **Compose** : ports, conteneurs, labels `com.albandrieu.nabla.entity-ref`.
- **Gatus natif** : `config/monitoring/gatus-endpoints.yml` — cibles HTTP/TCP, intervalles, conditions. Ce fichier **n'est pas monté dans Gatus**, évitant le chargement des sondes en double.
- **Artefacts générés** : `apps/gatus/config/config.yml`, `apps/autokuma/static/generated-monitors.json` et le manifeste Homarr ; jamais édités manuellement.
- **Observations** : Gatus `/api/v1/endpoints/statuses`, Prometheus, Docker/TrueNAS ; une sonde négative n'implique pas qu'un service soit DOWN.

Le générateur conserve les 85 sondes Gatus existantes. Il ajoute l'étiquette
`nabla_entity_ref` aux sondes dont le service est déjà identifié dans
Backstage. La métrique `nabla_service_id` reste transitoirement publiée pour
les règles d'enregistrement Prometheus existantes. Les moniteurs sans entité
Backstage constituent un chantier d'inventaire, pas un prétexte pour en créer
une par déduction.

## Génération et vérification locales (sans réseau)

```bash
python scripts/generate-service-consumers.py --check
python scripts/generate-catalog-v2-artifacts.py --check
python -m unittest tests.test_service_consumers_status_contract -v
python -m pytest -q tests/test_service_consumer_monitor_coverage.py tests/test_reconcile_gatus_catalog.py
```

Pour ajouter ou modifier une sonde, éditer **uniquement** l'endpoint natif
dans `config/monitoring/gatus-endpoints.yml`, puis exécuter le générateur.
`catalog/service-consumers.static.yml` est supprimé : les paramètres du proxy
Docker Homarr proviennent directement de `apps/homarr/compose.yml`, les liens
de navigation proviennent de Backstage et les sondes du YAML Gatus natif.

## Diagnostic runtime (lecture seule)

```bash
python3 scripts/truenas/reconcile-gatus-catalog.py \
  --output /tmp/gatus-catalog-declared.json

# Snapshot privé sans affichage du corps HTTP ni des secrets :
umask 077
curl -fsS --max-time 10 http://127.0.0.1:8085/api/v1/endpoints/statuses \
  -o /tmp/gatus-statuses-private.json
python3 scripts/truenas/reconcile-gatus-catalog.py \
  --statuses /tmp/gatus-statuses-private.json \
  --output /tmp/gatus-catalog-runtime-redacted.json
rm -f /tmp/gatus-statuses-private.json
```

Le rapport ne publie pas les URL ni jetons. Il distingue
`probe_failed_unconfirmed`, `no_recent_evidence`,
`infrastructure_unmapped` et `unresolved` d'une panne de service.

Le réconciliateur `reconcile-gatus-catalog.py` et le diagnostic
`diagnose-gatus-monitors.py` utilisent désormais le **même interpréteur**
(`scripts/lib/gatus_observations.py`) : seul le dernier résultat d'une
sonde est retenu, avec horodatage timezone-aware et fraîcheur maximale
de **180 secondes**. Un succès ancien ne devient jamais `PASS`. Les
observations runtime dupliquées, absentes ou malformées restent
`UNVERIFIED`, et un refus `401/403` devient `DENIED`, non une panne
confirmée du service. Les champs de réconciliation `probe_verdict`,
`probe_reason` et `probe_verdict_counts` complètent les anciens champs
`evidence` et `classification` sans émettre le message brut des sondes.
Sans `--statuses`, le verdict est `NOT_RUN`.

Les snapshots utilisés par `--statuses` doivent être **récents** :
un export ancien n'établit pas la disponibilité actuelle. Aucun de ces
scripts ne déclenche de probe active ni de modification de service.

### Verdicts des sondes Gatus

Le script `scripts/truenas/diagnose-gatus-monitors.py --check` partage
désormais le transport HTTP JSON borné avec FastAPI et Prometheus
(`scripts/lib/http_diagnostics.py`) : pas de proxy implicite, pas de
redirection et pas de réponse brute dans le rapport.

L'état historique `up/down/unverified` demeure celui de **la sonde Gatus**,
jamais une preuve directe du statut du service. Le champ supplémentaire
`verdict` et les compteurs `verdict_counts` distinguent :

- `PASS` : observation récente et réussie ;
- `FAIL` : observation récente négative de la sonde, hors accès interdit ;
- `DENIED` : erreur d'accès HTTP 401/403, ne doit pas classer le service DOWN ;
- `NOT_RUN` : monitor déclaré mais sans résultat d'exécution disponible ;
- `UNVERIFIED` : preuve périmée, ambiguë ou absente du runtime.

Les codes de sortie sont `0` pour preuves complètes, `1` pour un échec
confirmé de sonde (mais pas nécessairement du service), `2` pour un refus
d'accès ou une preuve insuffisante sans échec confirmé. L'ancien compteur
`down` peut compter un refus 403 pour compatibilité, mais **ne décide plus
seul du code de sortie**. Les consommateurs du rapport doivent privilégier
`verdict_counts`.

### Services HTTP protégés : Garage et LiteLLM

Un 401/403 est une barrière d'authentification attendue, ni un 200 ni une
preuve fonctionnelle ; un 403 vu du LAN ne prouve pas non plus une exposition
Internet.

| Service | Sonde anonyme | Réponse attendue | Vérification fonctionnelle distincte |
| --- | --- | --- | --- |
| Garage S3 `:3900` | `GET /` LAN | HTTP 401/403 = **auth attendue**, pas S3 OK | Opération S3 signée, identifiant limité, aucun secret dans les logs |
| LiteLLM `:4000` | `GET /health` LAN | HTTP 401 = **auth attendue**, pas modèles OK | `GET /health/liveliness` = 200, puis requête API autorisée et upstreams |
| LiteLLM Docker | `apps/litellm/compose.yml` | `healthcheck` interne sur `/health/liveliness` (30 s) | `docker inspect` : `healthy/unhealthy/starting` |
| Gatus | `apps/gatus/config/config.yml` | **TCP CONNECTED** sur `:3900` et `:4000` | Ne valide ni l'auth, ni l'écriture S3, ni l'inférence |

Garder ces sondes Gatus en **TCP** : ne pas les remplacer par
`[STATUS] == 200` sur un endpoint protégé. `just protected-http-diagnostics`
(`scripts/truenas/diagnose-protected-service-http.py --check`) n'interroge que
ces trois URLs LAN, sans proxy ni redirection, timeout 4 s, sans secret ni
corps HTTP ; `auth_required_expected` et `liveness_up` ne sont ni un test
d'inférence ni une preuve S3 signée. Une absence de healthcheck Docker n'est
jamais convertie en `healthy`.

Tests locaux ciblés, sans connexion au homelab :

```bash
python3 -m pytest -q tests/test_http_diagnostics.py tests/test_gatus_monitor_failures.py tests/test_prometheus_failed_scrapes_diagnostic.py tests/test_fastapi_stack_consolidated.py
```

Priorités de diagnostic : Home Assistant HTTP vs TCP ; exporters
PostgreSQL/OpenSearch distincts des bases ; Scanopy, NetBox, Graylog,
Plumber et NPMplus selon état attendu et environnement. Garder
`nabla:service:synthetic_probe_success` observable pour pfSense,
PostgreSQL et TrueNAS, sans considérer un label comme preuve de scrape.

Les 85 sondes déclarées sont un **inventaire Git**, pas une mesure
de disponibilité réelle. Aucun déploiement TrueNAS ni migration
des deux autres lecteurs FastAPI/site n'est effectué par la génération.
