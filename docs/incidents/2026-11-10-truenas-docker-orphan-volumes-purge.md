# TrueNAS : purge des volumes Docker orphelins, `init: true` effectif, homarr et openrag

Date : 2026-11-10. Preuves : shell TrueNAS (`midclt`, `docker`, `zfs`),
journaux `/mnt/cpool/var/nabla/ops-logs/*-20261110.log`, plans
`/var/tmp/nabla-docker-orphan-volumes*.tsv` (root, `0600`). Actions
d'écriture approuvées par l'opérateur dans la session.

## Volumes Docker orphelins

Plan (`reconcile-docker-orphan-volumes.sh --plan`, 14:14) sur 725 volumes
dangling :

| Action | Nombre | Octets |
|---|---:|---:|
| `candidate:anonymous` | 659 | 853 220 711 |
| `candidate:removed-app` (`ix-affine_redis-data`) | 1 | 89 |
| `keep:installed-app` | 10 | 89 629 |
| `review:recent` | 41 | 31 383 167 |
| `review:unsized` (`du` > 10 s) | 10 | inconnu |
| `review:large` | 2 | 316 602 320 |
| `review:foreign-project` (`nabla-compose_*`) | 2 | 300 576 |

`--apply` (`NABLA_VOLUME_PURGE_APPROVED=yes`, `docker volume rm` sans
`--force`, aucune `prune`) : `removed=660 skipped=0 failed=0`.

| Mesure | Avant (14:14) | Après (15:21) |
|---|---:|---:|
| Volumes / dangling | 760 / 725 | 100 / 65 |
| `time docker volume ls -q` | 0,029 s | 0,023 s |
| `app.query` (`id,state`, 91 Apps) | 1,17 s | 0,29 s |
| `cpool/ix-apps/docker` used / snapshots | 654G / 182G | 655G / 183G |

L'espace ne baisse pas : les blocs supprimés restent référencés par les
snapshots ZFS jusqu'à leur expiration. Entre le 4/11 (658 dangling) et le
10/11 (725), la dérive a repris : relancer le plan régulièrement.

Second plan : 2 `candidate:anonymous` (anciens `unsized`, 7,8 et 9,4 Mo,
318 jours), 8 `review:unsized`, 41 `review:recent`, 2 `review:large`,
2 `review:foreign-project`, 10 `keep:installed-app`. Non supprimés.

Défaut du script : `--plan` finissait en `exit 2` après avoir écrit le
plan, car sous `pipefail` le `sort | head -15` du résumé mourait de
SIGPIPE. Le plan était complet ; corrigé par `sort -o` et test.

## `init: true` et zombies

Les 10 services ayant `init: true` (8db35d35, 9/11) tournaient encore avec
`HostConfig.Init=<nil>` : leurs conteneurs dataient des 6 et 7/11.
`redeploy-impacted-apps.py --from 8db35d35^ --to 8db35d35` donne l'ordre
bichon, clickhouse, kafka, minio, mongo, ollama, openwebui,
sentry-clickhouse, suricata (drawio STOPPED, laissé arrêté). L'apply du
script exige un checkout exactement à `--to` : `app.redeploy` lancé à la
main dans cet ordre, une App à la fois, avec attente de l'état RUNNING et
de conteneurs sains (15:55 → 16:09).

- Les 9 Apps ont `init=true` ; `ix-kafka-kafka-exporter-1` reste sans `init`.
- Zombies : 306 → **3**. Avant : 267 sous la JVM `ix-kafka-kafka-1`,
  17 sous suricata, 7 sous minio, 8 sous les deux ClickHouse.
- Aucun zombie à threads vivants avant ni après (pas de verrou containerd
  comme le [4/11](2026-11-04-truenas-app-query-stuck-container-lock.md)).
- Dépendants akvorado, crowdsec, grafana, langfuse, sentry : sains.

`wazuh` : `diagnose-wazuh.sh --check` → convergé (RUNNING, 0 événement
perdu).

## openrag : DEPLOYING depuis le 7/11

`app_lifecycle.log` : `dependency failed to start: container
openrag-backend is unhealthy`, à chaque `up` depuis septembre. Le backend
a démarré à 00:34 Z et n'était pas sain à 00:41 Z, alors que son
healthcheck tolère 60 s + 10 × 30 s. `depends_on: service_healthy` a
laissé `openrag-frontend` à `Created`.

- Runtime : `docker start openrag-frontend` (backend sain) → App RUNNING,
  deux conteneurs `healthy`.
- Code : `start_period` du backend passé à 600 s.

## homarr : CRASHED

Le job one-shot `homarr-sync` sortait en 2 (`HOMARR_API_KEY` absent ; le
fichier runtime ne porte que l'ancien `HOMARR_API_TOKEN`). Le correctif de
master (7ad0173d) accepte l'ancien nom : relancé, le job reçoit **401** de
Homarr, réessaie 20 fois et sort en 1. L'ancienne identité est révoquée.

- Code : 401/403 arrête immédiatement le job avec `RECONCILE_SKIPPED` et
  `exit 0`, comme une clé absente.
- Reste opérateur : créer une clé API Homarr, la ranger dans
  `nabla/prod/homarr` (`HOMARR_API_KEY`), rematérialiser
  `/mnt/cpool/secrets/runtime/homarr/.env.secrets`, puis relancer
  `homarr-sync`.
