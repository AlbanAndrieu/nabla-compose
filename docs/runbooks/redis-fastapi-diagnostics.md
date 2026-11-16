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
(http://172.17.0.24:8091/api/homelab/health), --timeout (0.5 à 10 s,
Docker/TCP) et --fastapi-timeout (0.5 à 30 s ; 10 s par défaut).
L'appel HTTP direct ignore explicitement les variables HTTP_PROXY/HTTPS_PROXY.

Si FastAPI est indisponible, le rapport court affiche reason et http_status.
Vérifier sans exposer le corps ou les en-têtes d'authentification :

    sudo python3 scripts/truenas/diagnose-redis.py --check --json |
      jq '{fastapi, warnings, failures}'

    curl --noproxy '*' -sS -o /dev/null --max-time 10 \
      -w 'HTTP=%{http_code} total=%{time_total}s\n' \
      http://172.17.0.24:8091/api/homelab/health

Interprétation : timeout indique un délai API ; api_auth_required et un code
401/403 indiquent un contrôle d'accès ; network_error indique une erreur
transport ; invalid_json ou response_too_large indiquent un problème de
contrat de réponse. Aucune de ces conditions ne prouve Redis indisponible.

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

## Durcissement du bind Redis : 172.17.0.24:30059 uniquement

Le fichier canonique apps/redis/compose.yml fixe host_ip à 172.17.0.24.
Les accès sont maintenus via redis:6379 sur le réseau intranet et via
172.17.0.24:30059 sur le LAN. La publication sur 0.0.0.0 et :: doit
disparaître après redéploiement.

Vérification statique des consommateurs :
- Sentry, Snuba, Redis Exporter, FastAPI Sample et Langfuse utilisent
  le DNS Docker redis:6379 dans leurs déclarations ;
- Gatus, AutoKuma et les sondes LAN utilisent 172.17.0.24:30059 ;
- Reactive Resume est documenté avec cette même adresse LAN ;
- aucune référence localhost:30059 ou 127.0.0.1:30059 n'est trouvée
  dans les sources suivies.

La vérification statique n'exclut pas un client dans une configuration
runtime secrète ou un outil externe. Sur TrueNAS, vérifier uniquement
les noms des fichiers secrets contenant une référence loopback
(ne jamais afficher les valeurs) :

    sudo grep -RIlE '(localhost|127[.]0[.]0[.]1):30059' \
      /mnt/cpool/secrets/runtime/ 2>/dev/null || true

Confirmer l'adresse LAN, les membres du réseau et l'include réellement
utilisé par TrueNAS :

    ip -4 addr show | grep -F '172.17.0.24/'
    sudo docker network inspect intranet --format '{{json .Containers}}' |
      jq -r 'to_entries[] | .value.Name' | sort
    sudo midclt call app.config redis | jq '{include: .include}'

Inspecter les clients actifs, en sachant que le NAT Docker peut masquer
l'utilisation du port publié dans les sockets observés :

    sudo ss -Htn state established '( sport = :30059 or dport = :30059 )'

Ne pas appliquer si l'App ne pointe pas sur le Compose canonique, si
172.17.0.24 n'est pas une adresse locale, ou si un client runtime
nécessite 127.0.0.1:30059.

Valider le Compose sans interpoler ni afficher le secret REDIS_AUTH :

    docker compose -f apps/redis/compose.yml \
      config --quiet --no-interpolate --no-env-resolution

Après fusion et mise à jour du checkout sur TrueNAS, utiliser le
mécanisme versionné existant. La première commande ne modifie rien :

    sudo bash scripts/truenas/app-ops.sh restart redis
    sudo env NABLA_RUNTIME_CHANGE_APPROVED=yes \
      bash scripts/truenas/app-ops.sh restart redis --apply

L'App Redis seule est redéployée ; le dataset /mnt/cpool/redis est
préservé. Une interruption brève des clients est possible.

Réception après application :

    sudo python3 scripts/truenas/diagnose-redis.py --check --json |
      jq '{docker_truenas_identity_consistent, redis_published_host_ips,
           redis_lan_bind_compliant, tcp, failures, warnings}'
    sudo docker inspect redis --format '{{json .NetworkSettings.Ports}}' |
      jq '."6379/tcp"'
    sudo bash scripts/truenas/diagnose-shared-data-services.sh
    sudo docker inspect ix-sentry-snuba-api-1 \
      --format '{{.State.Status}} {{.State.Health.Status}}'

Attendu : une seule publication 172.17.0.24:30059,
redis_lan_bind_compliant=true, TCP accessible, Snuba running healthy.
Un WARN FastAPI ne prouve pas une panne Redis.

En cas de régression, corriger la cause cliente ou restaurer
temporairement la définition Compose antérieure par un changement
versionné, puis relancer app-ops.sh restart redis --apply. Le retour à
0.0.0.0 élargit la surface d'attaque et doit être exceptionnel.

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
