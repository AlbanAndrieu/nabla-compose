# G1 — PostgreSQL : rotation de secret et restauration réellement vérifiée

Référence : [roadmap générale](../roadmap.md) · [politique PostgreSQL/TLS](../security/postgresql-fips-tls13-vault-oauth-20261110.md) · [migration Vaultwarden](vaultwarden-migration-closure-20261106.md).

**État au 13 novembre 2026 : CODED/TESTED sur tests unitaires isolés, runtime TrueNAS NOT_RUN.** Ce runbook ne constitue ni une preuve de rotation du rôle exposé ni une restauration effectuée. Le cron `postgresbackup` doit rester **désactivé**.

## G1.1 — Rotation du mot de passe postgres_exporter (P0 immédiat)

Le 13/11, un mot de passe de l'exporter a été imprimé dans une sortie opérationnelle. **Le considérer compromis**, même si aucun accès abusif n'est démontré. Ne jamais recopier ce mot de passe, un DSN ou une session Bitwarden dans GitHub, la CI, les journaux publics ou une conversation.

1. Depuis une console privée TrueNAS et une session de coffre autorisée, vérifier que le rôle **dédié** PostgreSQL est `postgres_exporter` avec `pg_monitor`, jamais le compte administrateur. Préparer une nouvelle valeur aléatoire dans le gestionnaire de secrets, et conserver une voie d'administration PostgreSQL distincte.
2. Sur le conteneur PostgreSQL partagé, ouvrir `psql` **interactivement** en administrateur ; exécuter `\password postgres_exporter` pour changer son mot de passe sans l'insérer dans une commande, dans des arguments CLI ou dans un SQL journalisé. Ce point **modifie la base** : planifier une brève coupure des métriques si nécessaire.
3. Dans l'item Vaultwarden **`nabla/prod/postgres-exporter`**, remplacer le champ `DATA_SOURCE_NAME` par le DSN de l'exporter utilisant la **nouvelle** valeur. Conserver uniquement l'item autorisé ; ne pas recréer un second secret ni diffuser le DSN. Le champ est déclaré dans `config/secrets/manifest.json`.
4. Sur TrueNAS, vérifier les permissions `root:root 0600` et la parité du rendu via `scripts/secrets/materialize_runtime.py --app postgres-exporter --verify` ; si nécessaire, effectuer la matérialisation explicite `--install` après sauvegarde sécurisée du fichier précédent. Redéployer **uniquement** `postgres-exporter`.
5. Exécuter `sudo bash scripts/truenas/diagnose-postgres-exporter.sh` et vérifier les métriques `up{job="postgres_exporter"} = 1` ainsi que `pg_up = 1`. Confirmer que **l'ancien mot de passe n'authentifie plus le rôle**, avec un test négatif privé qui n'enregistre aucune valeur dans ses logs.

**Clôture G1.1 :** rotation effective, coffre/fichier/conteneur convergents, ancien secret refusé, exporter de nouveau opérationnel, historique d'exposition traité. Un script ou une modification du manifeste ne clôt pas la rotation à lui seul.

## G1.2 — Dump logique manuel (P0)

Sur le checkout canonique TrueNAS, confirmer d'abord que le rôle backup est sain et que la CA du PostgreSQL est installée :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/enable-postgres-tls.sh --check
sudo bash scripts/truenas/bootstrap-postgresbackup-role.sh --check
sudo python3 scripts/truenas/reconcile-postgresbackup-cron.py --check
# Lancement manuel UNIQUEMENT si la CA, le rôle, le stockage et l'image sont présents.
sudo docker compose --project-directory apps/postgresbackup \
  -f apps/postgresbackup/compose.yml --profile manual \
  run --rm --no-deps postgresbackup
```

Le Compose de backup impose `PGSSLMODE=verify-full` avec la CA locale en montage **lecture seule**. Aucun downgrade silencieux vers une connexion non vérifiée. Le dump utilise le rôle `pgbackup` sans privilège d'écriture ; `pg_restore --list` et le SHA-256 valident l'archive, **pas** une restauration.

## G1.3 — Restaurer sans toucher à la production

Prendre une **archive créée par G1.2**, stockée dans le répertoire canonique, et l'examiner en local ; ne pas donner au script d'accès à une base de production :

```bash
ARCHIVE=/mnt/cpool/backup/postgres/fastapisample/fastapisample-AAAAMMJJTHHMMSSZ.dump
sudo python3 scripts/truenas/verify-postgresbackup-restore.py \
  --check --archive "$ARCHIVE"
sudo python3 scripts/truenas/verify-postgresbackup-restore.py \
  --restore-test --archive "$ARCHIVE" --timeout 1800 --write-receipt
```

Le validateur refuse les symlinks, chemins hors base canonique, métadonnées SHA-256 mal formées et archives modifiées. Il utilise **la même image PostgreSQL 18.6 épinglée que le job**, uniquement si l'image est déjà présente (`--pull never`). Il crée un conteneur **sans réseau**, sans port publié ni accès au PostgreSQL en service, lance une restauration `pg_restore --exit-on-error`, relève le nombre de relations et détruit le conteneur. Il ne modifie ni cron, ni secrets, ni anciennes sauvegardes. Aucun résultat SQL brut n'est imprimé.

La variante `--write-receipt` (option explicite en mode restauration) écrit une preuve technique JSON dans `/mnt/cpool/secrets/runtime/postgresbackup/restore-acceptance.json` (fichier root `0600`, dossier privé root), uniquement si la restauration a réussi et qu'au moins un objet a été restauré. Sans ce paramètre, la restauration ne modifie pas ce fichier. Cette preuve expire après 7 jours et n'est **pas** une attestation métier.

États JSON : `ARCHIVE_CHECKSUM_VERIFIED` = intégrité **seulement**, `ISOLATED_RESTORE_VERIFIED` = restauration isolée achevée, `NOT_VERIFIED` = erreur, source absente ou étape non exécutée. Un nombre de relations égal à zéro exige un contrôle métier avant réception. Comparer ensuite, depuis une session autorisée, les comptages et contrôles fonctionnels choisis avec les données de référence à l'instant du dump ; une restauration réussie à elle seule ne prouve ni la fraîcheur ni la couverture de toutes les bases.

**Attention capacité :** le conteneur de restauration est limité à 1536 Mio de RAM, 2 CPU et 256 processus ; le contrôle `pg_restore --list` à 512 Mio, 1 CPU et 128 processus. Aucune image n'est téléchargée (`--pull never`) ni aucun réseau attaché. Le nettoyage est contrôlé même après un échec de démarrage ; un conteneur restant actif produit `isolated_cleanup_not_verified` plutôt qu'un reçu de succès. Les limites peuvent nécessiter une étude spécifique pour Sentry avant son activation.

Une sauvegarde déjà présente avec le même nom UTC n'est plus écrasée : l'archive et le checksum sont publiés par liens exclusifs, en staging privé. Un échec de checksum retire l'archive créée par cette tentative sans supprimer l'ancienne.

**Attention capacité :** une restauration de base volumineuse peut consommer du stockage Docker temporaire et de l'I/O. Les archives restent sur `cpool/backup`. Cette procédure n'implémente pas la réplication hors site ni la restauration ponctuelle WAL/PITR.

## G1.4 — Mise en service contrôlée

Pour auditer sans mutation le **runtime** des tâches TrueNAS, distinguer `reconcile-postgresbackup-cron.py --check` (déclaration offline seulement) et `sudo python3 scripts/truenas/reconcile-postgresbackup-cron.py --check-live` (`cronjob.query`, état réellement activé/désactivé et dérive du contrat).

Pour activer **uniquement la tâche quotidienne**, une preuve technique récente et intacte doit être présente, accompagnée de la décision opérateur : `sudo env POSTGRES_BACKUP_CRON_APPROVED=YES python3 scripts/truenas/reconcile-postgresbackup-cron.py --enable --job daily`. Les tâches Sentry mensuelle/annuelle restent bloquées à l'activation jusqu'à une preuve spécifique de leurs séries. En l'absence de fichier, en cas de mauvais propriétaire/mode, d'archive modifiée, de résultat vide ou d'expiration : **refus sans mutation**. Contrôler les données métier séparément avant de donner l'autorisation.

Seulement après une preuve G1.3 horodatée, revérifier la liste des bases (celles non déployées restent `SKIP`) et arbitrer la couverture Sentry mensuelle/annuelle. Le cron existe déjà et reste désactivé. Son activation exige le reçu de restauration technique, le choix explicite `--job daily` et `POSTGRES_BACKUP_CRON_APPROVED=YES` **uniquement après réception opérateur**, et non par une PR documentaire.

**Critères G1 complet :** compte compromis tourné, sauvegardes manuelles vérifiées, au moins une restauration indépendante constatée, contrôle de données représentatives, permissions et CA conformes, plan de restauration documenté, puis activation explicite du cron si voulue.
