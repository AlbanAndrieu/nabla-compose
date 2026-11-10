# Opérations de production des Apps TrueNAS

Procédure commune à toutes les Apps du dépôt, déjà installées ou à installer.
L'état de chaque App est dans la matrice générée
[`docs/production-readiness.md`](../production-readiness.md) (régénérée par
`scripts/truenas/audit-production-readiness.py --write`, sans réseau).

## Règles

- Toutes les actions sont en lecture seule par défaut. Pour une mutation, il faut
  `--apply` **et** `NABLA_RUNTIME_CHANGE_APPROVED=yes`. Le refus intervient avant toute étape.
- Le point d'entrée est
  [`scripts/truenas/app-ops.sh`](../../scripts/truenas/app-ops.sh) `<action> <app> [--apply]`.
  Il délègue aux scripts existants et ne contient aucune nouvelle logique de mutation.
- Lancez-le depuis le checkout canonique `/mnt/cpool/compose/nabla-compose`, en root, sur le NAS.
- Aucune valeur secrète n'est affichée. Les secrets viennent de Vaultwarden
  (`export BW_SESSION="$(bw-unlock)"`), puis `bw lock`.
- Aucune image n'est tirée implicitement : faites un `docker pull <image@sha256>` délibéré.

## Ordre de mise en production d'une App

| Étape | Commande (lecture seule, puis `--apply`) | Outil appelé |
| --- | --- | --- |
| 1. État | `app-ops.sh status <app>` | audit + `app.query` + conteneurs |
| 2. Stockage | `app-ops.sh storage <app>` | `bootstrap-repository-storage.sh` (datasets APPS, profils `dataset-profiles.json`) |
| 3. Secrets | `app-ops.sh secrets <app>` | `scripts/secrets/materialize_runtime.py --verify/--install` |
| 4. Déploiement | `app-ops.sh deploy <app>` | `deploy-<app>.sh`, `deploy-media-stack.sh` ou plan `reconcile-custom-apps.py` |
| 5. Configuration | voir « Configuration as code » ci-dessous | API, OpenTofu |
| 6. Supervision | `app-ops.sh monitor <app>` | `x-nabla.monitoring`, jobs Prometheus |
| 7. Sauvegarde | `app-ops.sh backup <app>` | `zfs snapshot` + `postgres-backup` ponctuel |

Les snapshots périodiques se convergent avec
`scripts/truenas/reconcile-snapshot-tasks.sh` (`config/truenas/snapshot-tasks.json`).
La sauvegarde logique planifiée se règle avec `scripts/truenas/reconcile-postgres-backup-cron.py`.
Il gère trois tâches, toutes enregistrées désactivées :

| Tâche | Bases | Planification | Rétention |
| --- | --- | --- | --- |
| quotidienne | `BACKUP_DATABASES` du Compose | chaque jour à 03:20 | 14 jours |
| `sentry-monthly` | `sentry` | le 1er du mois à 04:20 | 370 jours |
| `sentry-yearly` | `sentry` | le 2 janvier à 05:20 | 1100 jours |

Sentry est exclu de la vague quotidienne : son nodestore est volumineux.
Chaque série écrit dans `<base>-<série>/` et ne purge que ses propres répertoires.

## Exploitation courante

```bash
cd /mnt/cpool/compose/nabla-compose
bash scripts/truenas/app-ops.sh diagnose radarr          # état, santé conteneurs, diagnostics dédiés
bash scripts/truenas/app-ops.sh restart radarr           # plan
NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/app-ops.sh restart radarr --apply   # app.redeploy + santé
NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/app-ops.sh backup defectdojo --apply # snapshot + pg_dump
```

`backup` crée `<dataset>@manual-<app>-<UTC>`. Il ignore les datasets classés
`noSnapshot` (médias, cache), et lance un dump `postgres-backup` limité aux bases de
l'App, avec `BACKUP_REQUIRE_ALL=true`. Une restauration se teste avant d'activer le cron.

## Configuration as code

| Domaine | Source | Commande |
| --- | --- | --- |
| Câblage *arr (Radarr, Sonarr, Prowlarr) | `terraform/media` | `scripts/infra/terragrunt-safe.sh infrastructure/media plan` |
| qBittorrent, proxy Prowlarr, Lidarr, Jellyfin | `config/media/settings.yml` | `scripts/media/reconcile-media-settings.py --check/--apply` |
| Profils qualité | `apps/recyclarr/config/recyclarr.yml` | conteneur Recyclarr |
| DNS et tunnel Cloudflare | `terraform/cloudflare` | `tofu plan` (voir son README) |
| Sondes Gatus | `catalog/` | `scripts/truenas/reconcile-gatus-catalog.py` |
| Custom Apps | `config/truenas/custom-apps.yml` | `scripts/truenas/reconcile-custom-apps.py --check` |

## Écarts

La matrice nomme les écarts par App :

- `NO_DEPLOY_PATH`
- `SECRETS_LEGACY_PATH`
- `SECRETS_NOT_IN_MANIFEST`
- `NO_AVAILABILITY_PROBE`
- `DB_NOT_IN_LOGICAL_BACKUP`
- `SNAPSHOT_UNCLASSIFIED`
- `SERVICE_WITHOUT_HEALTHCHECK`

Un service sans `healthcheck` Compose peut le justifier par le label
`com.albandrieu.nabla.healthcheck`, avec l'une de ces valeurs :

- `image` : `HEALTHCHECK` déjà présent dans l'image ;
- `prometheus-up` : un exportateur ;
- `scheduled-job` : un service sans écoute.

Toute autre valeur reste un écart. Corrigez les écarts App par App, avec une preuve.
N'ajoutez pas de sonde ou de base de sauvegarde sans qu'elle soit attestée dans le dépôt.
