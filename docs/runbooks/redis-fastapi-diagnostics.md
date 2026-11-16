# Redis — diagnostic TrueNAS / Docker / FastAPI

Script en **lecture seule**. Aucun redémarrage, aucune modification de Redis,
aucun secret ou environnement Docker affiché.

Depuis un checkout de nabla-compose sur TrueNAS :

    sudo python3 scripts/truenas/diagnose-redis.py --check
    sudo python3 scripts/truenas/diagnose-redis.py --check --json | jq '{
      result, docker, redis_exporter, truenas, tcp, fastapi,
      docker_truenas_identity_consistent, failures, warnings
    }'

Prérequis : Python 3, Docker, midclt et droits de lecture du socket Docker.
Paramètres optionnels : --host (172.17.0.24), --fastapi-url
(http://172.17.0.24:8091/api/homelab/health), --timeout (0.5 à 10 s).

## Contrats vérifiés

| Source | Contrôle | Limitation |
| --- | --- | --- |
| Docker | conteneur redis, projet ix-redis, service Compose redis, healthcheck, trois derniers codes de sortie | healthy ne prouve pas PING authentifié |
| Docker exporter | conteneur redis_exporter et état | exporter en fonctionnement ne prouve pas un scrape Prometheus |
| TrueNAS | app redis RUNNING, container_details, ports | state RUNNING ne prouve pas l'usage applicatif |
| Réseau | port publié 172.17.0.24:30059 → Redis 6379 | TCP ne prouve ni AUTH ni lecture/écriture |
| FastAPI | extrait des états Redis, Sentry Snuba API et Sentry | services[] peut représenter une vague rotative |
| Surface réseau | adresse de binding 0.0.0.0 ou :: | ne démontre pas l'accès depuis Internet ; examiner pare-feu |

Le rapport ne fait **aucune supposition** sur l'absence d'un service à partir
de la seule réponse FastAPI. Lorsqu'une vague de 12 services ne contient
pas Redis, il affiche rotating_or_filtered_snapshot_not_catalog_absence.
Voir aussi probe_summary.internal.unobserved_slots et les mesures conservées.

## Interprétation des états Sentry

La propagation de dépendances doit rester visible :

    Redis local_state=warn
       ├── Snuba local_state=ok, effective_state=warn
       └── Sentry local_state=ok, effective_state=warn

Si Docker et TrueNAS sont sains mais FastAPI signale Redis local_state=warn,
examiner probe_source, runtime_app, runtime_state, internal_state et la
reconnaissance de l'identité Compose. Ne pas forcer les états au vert.

Une adresse de liaison 0.0.0.0:30059 appelle une revue des règles de
pare-feu et de segmentation ; elle ne prouve pas une exposition WAN.

## PING authentifié, existant

Ce nouveau script ne manipule **aucun** mot de passe. Pour contrôler
l'authentification, réutiliser le diagnostic existant qui lit
/mnt/cpool/secrets/runtime/redis/.env.compose sans révéler REDIS_AUTH :

    sudo bash scripts/truenas/diagnose-shared-data-services.sh

Ne jamais coller le contenu des secrets ni les variables d'environnement
du conteneur dans les issues ou les PR.

## Validation

    python3 -m py_compile scripts/truenas/diagnose-redis.py
    python3 -m pytest -q tests/unit/test_redis_diagnostics.py
    sudo python3 scripts/truenas/diagnose-redis.py --check

L'absence d'une preuve, un HTTP 401/403, ou une erreur de permission Docker
est **inconclusif**, pas un service confirmé DOWN. Un diagnostic sain ne
remplace pas un test métier d'ingestion et de recherche d'événements Sentry.
