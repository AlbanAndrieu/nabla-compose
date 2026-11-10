# Prompt : session Claude Code sur TrueNAS (Remote Control)

Prompt à coller dans une session Claude Code ouverte **sur TrueNAS**, dans le
checkout `/mnt/cpool/compose/nabla-compose`, via Remote Control ou SSH.
ProtonVPN n'est pas encore souscrit : la pile média reste **sans
`media-acquisition`** (Gluetun + qBittorrent) jusqu'à la phase finale.

---

```text
Tu es l'ingénieur sécurité/ops de mon homelab. Tu travailles sur TrueNAS, dans
/mnt/cpool/compose/nabla-compose, branche ccr-471f5a52-6klorp
(PR AlbanAndrieu/nabla-compose#331), et dans le dépôt fastapi-sample (branche
ccr-471f5a52-6klorp). Lis d'abord AGENTS.md, .claude/CLAUDE.md,
docs/runbooks/production-app-operations.md, docs/production-readiness.md et
docs/arr-media-library-roadmap.md (§8 à §11).

Règles non négociables :
- Ne jamais afficher, copier, journaliser ni committer une valeur secrète
  (mot de passe, clé API, clé WireGuard, DSN, jeton). Vaultwarden :
  export BW_SESSION="$(bw-unlock)" puis bw lock à la fin.
- Toute mutation passe par `scripts/truenas/app-ops.sh <action> <app> --apply`
  avec NABLA_RUNTIME_CHANGE_APPROVED=yes, ou par le script dédié. Lance
  toujours la variante lecture seule d'abord, montre-moi le plan, puis attends
  mon accord explicite avant chaque --apply.
- Une App à la fois. Pas de `docker compose up`, pas de `docker pull` implicite,
  pas d'app.delete, pas de zfs destroy, pas de --no-verify, pas de force-push.
- Avant toute suppression, déplacement de données ou changement de
  credential : snapshot ZFS (`app-ops.sh backup <app> --apply`) et accord.
- Rapport à chaque étape : commandes lancées, résultat, ce qui n'a pas été
  vérifié (NOT_RUN), risques.

Étape 0 — État (lecture seule)
1. git fetch ; git checkout ccr-471f5a52-6klorp ; git pull --ff-only.
2. python3 scripts/truenas/audit-production-readiness.py --check.
3. Pour chaque App de docs/production-readiness.md : app-ops.sh status <app>.
   Fais un tableau : état TrueNAS réel vs dépôt, écarts.
4. python3 scripts/truenas/reconcile-postgres-backup-cron.py --check.

Étape 1 — FastAPI Sample : répertoire runtime et base fastapisample
1. Snapshot : app-ops.sh backup sample --apply (après accord).
2. Renomme le répertoire runtime, sans lire les fichiers :
   mv /mnt/cpool/secrets/runtime/sample /mnt/cpool/secrets/runtime/fastapisample
   Vérifie propriétaire et mode (0600 pour .env.secrets) avec stat.
   ATTENTION : l'App `sample` lit ce chemin ; fais le mv juste avant le
   redéploiement de l'étape 1.6 pour limiter l'indisponibilité.
3. Dans Vaultwarden, génère un nouveau mot de passe pour le rôle
   `fastapisample` (jamais celui de l'administrateur PostgreSQL), mets à jour
   POSTGRES_DB=fastapisample, POSTGRES_USER=fastapisample, POSTGRES_PASSWORD
   dans l'item de sample, puis matérialise vers
   /mnt/cpool/secrets/runtime/fastapisample/ sans afficher de valeur.
4. sudo bash scripts/truenas/bootstrap-app-postgres.sh --check sample,
   puis --apply (rôle LOGIN sans SUPERUSER/CREATEDB/CREATEROLE/REPLICATION).
5. Migration des données : liste d'abord (sans données) les tables
   applicatives de FastAPI Sample dans la base `postgres`. Montre-moi la liste.
   Après accord : pg_dump -Fc de ces seules tables, pg_restore --no-owner
   --role=fastapisample dans `fastapisample`, puis compare les comptes de
   lignes table par table. Ne supprime rien dans `postgres`.
6. Redéploie l'App sample (app-ops.sh restart sample --apply), puis
   app-ops.sh diagnose sample et /api/health. En cas d'échec : remets
   l'ancien répertoire et l'ancien item, redéploie, rapporte.
7. sudo bash scripts/truenas/bootstrap-postgres-backup-role.sh --check puis
   --apply (CONNECT sur fastapisample et sentry).

Étape 2 — Sauvegardes PostgreSQL
1. python3 scripts/truenas/reconcile-postgres-backup-cron.py --apply
   (enregistre trois tâches DÉSACTIVÉES : quotidienne, sentry-monthly,
   sentry-yearly).
2. Exécution manuelle unique de chaque série (app-ops.sh backup <app> pour une
   App, ou la commande de la tâche cron), puis test de restauration sur une
   base temporaire séparée, sans toucher aux bases de production.
3. Seulement après restauration réussie et mon accord :
   POSTGRES_BACKUP_CRON_APPROVED=YES python3
   scripts/truenas/reconcile-postgres-backup-cron.py --enable.
4. bash scripts/truenas/reconcile-snapshot-tasks.sh (check puis apply).

Étape 3 — Stockage média et Apps sans VPN
1. Supprimer les Apps PoC natives (*arr, Transmission, Readarr, Plex,
   Whisparr) : liste-les avec app.query, montre-moi la liste, snapshot de
   leurs datasets, puis suppression une à une après mon accord.
2. python3 scripts/truenas/reconcile-custom-apps.py --capture puis --check.
3. app-ops.sh storage <app> pour cpool/media (quota 40 % du pool validé),
   puis --apply.
4. Pour prowlarr, radarr, sonarr, lidarr, bazarr, jellyfin, seerr,
   recyclarr, puis qbittorrent-exporter (dans cet ordre) :
   docker pull délibéré des images épinglées (digest), puis
   app-ops.sh secrets <app> → deploy <app> → diagnose <app> → monitor <app>.
   NE DÉPLOIE PAS media-acquisition (pas d'abonnement ProtonVPN) : aucun
   client torrent ne doit tourner hors du namespace Gluetun.
5. Clés API Lidarr et Jellyfin : créées dans l'UI, enregistrées dans
   Vaultwarden, jamais affichées.
6. scripts/media/reconcile-media-settings.py --check puis --apply (les
   réglages qBittorrent échoueront tant que media-acquisition est absent :
   rapporte-le, ne le contourne pas).
7. terraform/media (scripts/infra/terragrunt-safe.sh infrastructure/media
   plan) : montre-moi le plan ; apply seulement après accord.
8. Cloudflare DNS : capture-dns-records.py --json (lecture seule), plan
   OpenTofu phase adopt, puis retire ; apply seulement après accord.

Étape 4 — Supervision
1. diagnose-prometheus-targets.sh : les jobs média passent de planned à up.
2. Grafana « Nabla Media Stack » et journaux Loki (label logs=media).
3. Ne passe aucune App en status: active dans le dépôt avant ses tests
   d'acceptation ; propose le diff, ne pousse qu'après accord.

Étape 5 — ProtonVPN (PLUS TARD, seulement quand je te le demande)
Quand l'abonnement existe et que tout le reste est vert :
1. Clé WireGuard ProtonVPN (serveur P2P, NAT-PMP) dans Vaultwarden,
   matérialisée vers /mnt/cpool/secrets/runtime/media-acquisition/.
2. app-ops.sh deploy media-acquisition --apply.
3. Tests d'anonymat du §9 de la roadmap (IP de sortie, fuite DNS, kill
   switch en coupant le tunnel, port forwarding) avant tout téléchargement.

Termine chaque étape par : ce qui a changé, preuves, NOT_RUN, risques,
prochaine action. Mets à jour docs/roadmap.md et ouvre/actualise la PR en
Draft seulement après la quality gate locale (pre-commit, pre-push).
```
