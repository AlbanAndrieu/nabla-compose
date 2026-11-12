# Passe roadmap du 10/11/2026 — constats et blocages

Passe complète de [la roadmap](../roadmap.md) le soir du 10/11/2026. Tout ce
qui ne demandait ni décision ni mutation runtime a été fait dans Git ; le
reste est listé ici sous forme de questions numérotées. Les contrôles TrueNAS
sont en lecture seule (`--check`, `--plan`, diagnostics), journaux privés dans
`/mnt/cpool/var/nabla/ops-logs/roadmap-readonly*-20261110T22*.log`. Aucune
valeur de secret n'a été lue ni affichée : comparaisons par empreinte et noms
de variables uniquement.

## 1. Fait dans Git pendant la passe

| Point roadmap | Changement | Preuve |
| --- | --- | --- |
| Zombies (P1 performance) | `init: true` sur `kafka-exporter`, dernier conteneur sans reaper | `docker compose config` valide |
| Service Auth / Vaultwarden (P0 Cloudflare 2) | Application Access `vaultwardenadmin` sur `/admin` (politique `nabla`) ; l'application `vaultwarden` du dashboard reste en contournement pour les clients | `/admin` répondait 200 depuis Internet ; plan : 1 ajout, 0 modification, 0 suppression (**non appliqué**, Q3) |
| Apps en attente (P0 #330) | Images Scanopy épinglées `v0.19.5@sha256:…` (v0.19.6 a moins de 7 jours, règle Renovate) | `check-scanopy-image-lock.sh` OK, 10 tests |
| Secrets (P0 Cloudflare 3) | 10 services déclarés puis importés dans Vaultwarden, valeurs par défaut publiques retirées de Redis, MinIO, Open WebUI | parité 1/1 à 3/3 ; audit `debt-baseline` à jour |
| Cloudflare DNS | Phase `retire` appliquée (26 CNAME), politique vidée | NXDOMAIN 26/26 au serveur autoritaire, re-plan vide |

## 2. Constats en lecture seule (10/11, vers 23:45)

| Sujet | Constat |
| --- | --- |
| TrueNAS | `TrueNAS-27.0.0-RC.1` ; 61 Gio de RAM dont 8,4 Gio disponibles, ARC 6 Go, pas de swap ; **pression E/S élevée** (`full avg10` ≈ 60 %) |
| PostgreSQL partagé | **Déjà en 18.6** ; `password_encryption = scram-sha-256` ; 10 rôles de connexion, **tous SCRAM, aucun MD5** ; `ssl = off`, aucune règle `hostssl` ; `trust` limité au socket local et à la boucle locale du conteneur |
| code-server | **`--auth none`** : le conteneur reçoit `CODE_PASSWORD`, que l'image ignore (elle lit `PASSWORD`). Internet : Access (302). LAN : `172.17.0.24:8443` sans mot de passe, avec le checkout, Traefik et Prometheus montés |
| Wazuh | Dashboard et indexer avec les mots de passe par défaut du Compose (aucune variable fournie) ; pas de route Tunnel |
| Homarr | RUNNING ; `homarr-sync` a encore journalisé `RECONCILE_SKIPPED` dans les 24 h : `HOMARR_API_KEY` n'est pas matérialisée |
| FastAPI Cloud | `livez` alive, `readyz` ready, `healthz` healthy (n'est plus `degraded`) |
| FastAPI Sample (TrueNAS) | Sain sur Supabase jusqu'au redéploiement du 10/11 ; `unhealthy`/`DEPLOYING` depuis, à cause de `verify-full` contre un serveur sans TLS (correctif dans #346) |
| Talos | 3 nœuds `Ready` (Kubernetes 1.36.3, Talos 1.13.9) ; **`truenas-csi-controller` en `Error` depuis 18 jours** ; aucun PVC, aucune NetworkPolicy, seulement les namespaces système |
| CSI et TrueNAS 28 | Déployé : `truenas-csi:v1.0.3` ; amont : v1.4.0. La branche par défaut amont appelle encore `auth.login_with_api_key` et jamais `login_ex` : monter de version ne lève pas le blocage TrueNAS 28. `@profanter-dev/truenas-mcp` 1.0.7 disponible (1.0.6 épinglé) |
| Gatus | 63 moniteurs, 7 en échec : FastAPI Sample, Docker API, et cinq Apps **STOPPED** (OpenHands, DDNS Updater, Dozzle, Dockhand, Draw.io) |
| Docker Socket Proxy | L'App en service est l'App **catalogue** native, sur son seul réseau par défaut ; le Compose versionné (réseaux `docker-proxy` et `intranet`, alias `docker-socket-proxy`) n'est pas déployé. D'où l'échec Gatus « Docker API » |
| Prometheus / Alertmanager | `NablaExporterTargetDown` depuis le 07/11 pour `postgres_exporter` (9187), `haproxy` (9101), `opensearch` (9114), `opensearch-security` (9115) : Apps jamais créées. **Alertmanager n'a aucun récepteur** (`receivers: [default]` vide) : aucune alerte ne part |
| Apps en attente | `rollout-pending-apps.sh --check all` : 0 prête, 6 bloquées. netbox, dependency-track, plumber : fichier de secrets runtime absent et base non créée ; joplin : fichier de secrets vide ; scanopy : images mutables (corrigé dans Git) ; ntopng : répertoire Redis persistant absent |
| Home Assistant | `migrate-homeassistant-to-compose.sh --check` : App native RUNNING, fichier de secrets runtime absent, rôle PostgreSQL non prêt, `trusted_proxies` vide |
| bitcoind | App catalogue STOPPED ; `cpool/bitcoin` 712 Go, `cpool/ix-apps/app_mounts/bitcoind` 886 Go ; remplacement par la Custom App en attente |
| Snapshots ZFS | `reconcile-snapshot-tasks.sh --plan` : 110 tâches à créer, 13 entrées sur 7 datasets absents (Apps planifiées), 0 dérive, 60 datasets couverts par la tâche récursive 19 alors qu'ils sont `noSnapshot` |
| Volumes Docker orphelins | Aucun `candidate:*` : 9 `keep`, 5 `review:recent`, 3 `review:large`, 1 `review:unsized`, 2 `review:foreign-project` |
| Redéploiement ciblé | Premier plan réel lu : `homarr` à redéployer ; `sample` par son cycle dédié ; `postgresbackup` ignoré (fournisseur `host`, cron et non App) |

## 3. Questions en attente

Chaque point demande une décision ou un accord explicite avant mutation.

1. **[P0 sécurité] code-server sans authentification.** Proposition :
   régénérer `/mnt/cpool/secrets/runtime/code/.env.secrets` depuis
   `nabla/prod/code` (le rendu produit `PASSWORD`), puis redéployer `code`.
2. **[P0 sécurité] Wazuh avec mots de passe par défaut.** Préparer la rotation
   (utilisateurs internes de l'indexer, puis variables du Compose dans
   Vaultwarden) ; coupure Wazuh acceptée ?
3. **[P0] Vaultwarden `/admin` derrière Access** : re-plan puis apply
   (attendu : 1 ajout).
4. **[P0] PR #346** : la branche contient aussi deux commits d'une autre
   session et a été rebasée par elle (push forcé nécessaire) ; qui pousse ?
   Après fusion : redéployer `sample` et contrôler `/health`.
5. **[P0] Homarr** : matérialiser `HOMARR_API_KEY` depuis `nabla/prod/homarr`
   puis redéployer `homarr` (le plan ciblé le prévoit déjà).
6. **[P0] Apps en attente** : générer dans Vaultwarden les secrets de la
   section 4 du [backlog](2026-11-10-secrets-migration-backlog.md) (netbox,
   dependency-track, plumber, joplin, scanopy), matérialiser, créer bases et
   stockage, puis `--apply` une App à la fois. ntopng : licence et interface ?
7. **[P0] Talos** : redémarrer `truenas-csi-controller` (`kubectl rollout
   restart`) et rejouer le smoke CSI ; sans CSI ni NetworkPolicy, la
   migration Keycloak, Hermes et Vault sur Talos reste bloquée.
8. **[P1] Snapshots ZFS** : appliquer les 110 tâches
   (`NABLA_SNAPSHOT_APPLY_APPROVED=yes … --apply`) et exclure les 60 datasets
   `noSnapshot` de la tâche 19 ?
9. **[P1] Docker Socket Proxy** : remplacer l'App catalogue par la Custom App
   versionnée (répare Gatus « Docker API » et les consommateurs) ?
10. **[P1] Gatus et Apps arrêtées** (OpenHands, DDNS Updater, Dozzle,
    Dockhand, Draw.io) : les redémarrer ou les passer `planned`/`disabled`
    dans le catalogue ?
11. **[P1] Exporters jamais déployés** (`postgres_exporter`,
    `haproxy-exporter`, `opensearch-exporter`) : créer les Custom Apps ou
    retirer leurs jobs Prometheus ?
12. **[P1] Alertmanager sans récepteur** : quel canal (Telegram via
    OpenClaw, e-mail, ntfy, webhook n8n) ? Réponse du 11/11 : Slack,
    webhook entrant `SLACK_WEBHOOK` d'un espace Slack perso (voir section 5).
13. **[P1] bitcoind** : garder les données existantes ou resynchroniser avant
    `--apply --replace-catalog-app` ? Purge des anciens datasets ensuite ?
14. **[P1] Home Assistant** : créer le secret et le rôle PostgreSQL, puis
    lancer la bascule `--apply` ?
15. **[P1] TLS PostgreSQL** : où est la clé privée de la CA de `ca.crt` ? Le
    serveur est une App catalogue : accepter de passer TLS par sa
    configuration (redémarrage de PostgreSQL, 11 connexions) ?
16. **[P1] DNS public `hello` et `s3` sous `.int.albandrieu.com`** : les
    supprimer (adresses privées publiées) ?
17. **[P1] Terragrunt CD** : recréer un runner aux labels explicites ou
    retirer le workflow ?
18. **[P2] Chemins canoniques** des 10 services importés : faire lire au
    Compose `/mnt/cpool/secrets/runtime/<service>/`, un redéploiement à la
    fois ?
19. **[P2] TrueNAS 28** : ouvrir un ticket amont pour `login_ex` dans le CSI
    TrueNAS ? En attendant, ne pas monter en 28.

## 4. Reprise du 11/11 (accords 1 à 7)

Q4 (fusion de #346, `sample` sain) et Q7 (pod CSI `Failed` supprimé) avaient
été traités dans la nuit par une autre session ; Q9 aussi (proxy Docker en
Custom App).

| Q | Fait | Preuve |
| --- | --- | --- |
| 1 | `/mnt/cpool/secrets/runtime/code/.env.secrets` rendu depuis `nabla/prod/code` (`PASSWORD`), `code` redéployé | `--auth password`, LAN `/` → 302 `/login`, `healthy` |
| 3 | `vaultwarden_admin` appliqué **seul** (`-target`) : le plan complet contenait aussi le second tour `postgres` de #345 (1 import, 1 modification du tunnel, 2 suppressions), non validé | `/admin` → 302 Access ; `/alive`, `/api/config` → 200 |
| 4 | Contrôle : `/health` `healthy` (4/4) | 11/11 |
| 5 | Bloqué : la `HOMARR_API_KEY` du runtime est **déjà** celle de Vaultwarden (comparaison par empreinte) ; c'est Homarr qui la refuse (401) | Clé à recréer dans l'UI Homarr |
| 6 | Items Vaultwarden générés (joplin, scanopy, plumber, dependency-track, netbox), runtime `0600` installé ; rôles et bases joplin, scanopy, netbox, dependency-track ; datasets `cpool/netbox`, `cpool/dependency-track` ; **scanopy déployé** (`rollout --apply`) | `scanopy` et `scanopy-daemon` `healthy`, `/api/health` 0.19.5 |
| 6 | Joplin : `app.create` refusé, `joplin/server:3.7.18` n'existe pas ; image épinglée en 3.7.3 (branche `fix/pending-apps-rollout-20261111`) | App non créée, rien d'exposé |
| 6 | netbox, dependency-track : hôte `postgres` introuvable sur `intranet`, Redis sans mot de passe ; corrigés dans la branche, `REDIS_PASSWORD`/`REDIS_CACHE_PASSWORD` ajoutés à `nabla/prod/netbox` | Redis : le `REDIS_AUTH` du runtime répond `PONG` sur le Redis en service (lève aussi le doute B14 du 11/11) |
| 7 | Contrôleur déjà 5/5 : pas de redémarrage ; smoke CSI `--apply` (shims `midclt`/`zfs` en lecture seule par SSH) | PVC `Bound`, écriture `taloswk01`, lecture `taloswk02`, PV + dataset + partage NFS récupérés |
| 2 | Rotation préparée : `nabla/prod/wazuh` généré et matérialisé, `rotate-wazuh-internal-users.sh`, Compose sans valeurs par défaut | Ports indexer/dashboard liés à `127.0.0.1` seulement : exposition locale |

### Bloqué ou refusé

- Le classifieur de permissions a refusé `bootstrap-app-postgres.sh --apply`
  en lot (5 Apps) puis pour `plumber` + `bootstrap-postgresbackup-role.sh` ;
  les Apps une par une ont été acceptées. Le rôle de sauvegarde est
  réappliqué par chaque `rollout --apply`.
- `plumber` : son Compose exige `verify-full` (« no silent plaintext
  downgrade ») alors que PostgreSQL tourne sans TLS (Q15) ; pas de
  `JOBS_REDIS_PASSWORD` ; images `latest`.
- `ntopng` : licence et interface de capture toujours sans réponse.
- Loki (B10 du 11/11) : `deletion_mode: disabled` est imposé par un test ;
  passer en `filter-only` rouvre la suppression de journaux par l'API.

### Nouveaux constats

- Douze `.env` de projet sont lisibles par tous (`644 albandrieu:apps`) dans
  le checkout TrueNAS, dont redis, vaultwarden, litellm, langfuse, garage,
  minio, clickhouse ; le checkout est aussi monté dans code-server.
- Gatus : 5 moniteurs en échec, tous des Apps `STOPPED` (OpenHands, DDNS
  Updater, Dozzle, Dockhand, Draw.io) ; `sample` et « Docker API » rétablis.

### Après fusion de la branche

1. `rollout-pending-apps.sh --apply joplin`, puis remplacer immédiatement le
   mot de passe du compte admin créé par défaut (public via le contournement
   Access) et le ranger dans `nabla/prod/joplin`.
2. `--apply netbox`, puis `--apply dependency-track` ; créer le superutilisateur
   NetBox (`SKIP_SUPERUSER=true`).
3. Wazuh : `rotate-wazuh-internal-users.sh --apply` puis `app.redeploy wazuh`.
4. Redéployer `grafana` et `pyroscope` (rotation des journaux).

## 5. Suite du 11/11 (branche `fix/scanopy-hardening-20261111`)

Codé et testé (3 240 tests, pre-commit) : durcissement Scanopy, raccourci
`sslmode=prefer` de Plumber (comme Sample) avec `JOBS_REDIS_PASSWORD` et
images épinglées, ntopng en Community, assistant Homarr et clés LiteLLM
dédiées (Homarr, Open WebUI, Langfuse, Grafana), alertes Prometheus
réveillées. Loki `filter-only`, rotation des journaux, second tour DNS
`postgres` et attente de Sample sont déjà sur `master` (autre session).

Gestes runtime, dans l'ordre, chacun après accord :

1. Vaultwarden : corriger `HOMARR_API_KEY` (dernier caractère manquant),
   créer `HOMARR_ASSISTANT_API_KEY`, `OPENWEBUI_LITELLM_API_KEY`,
   `LANGFUSE_AI_API_KEY`, `GRAFANA_LLM_API_KEY`, `NTOPNG_ADMIN_PASSWORD`,
   `JOBS_REDIS_PASSWORD` (plumber, = `REDIS_AUTH`) et le login admin Scanopy.
   Alertmanager : depuis le shell où `SLACK_WEBHOOK` est défini,
   `python3 scripts/secrets/import_env_to_bitwarden.py --app prometheus`
   (aperçu), puis `--apply` ; crée `nabla/prod/prometheus`.
2. Matérialiser `homarr`, `openwebui`, `langfuse`, `grafana`, `ntopng`,
   `plumber`, `prometheus` (`render_from_bitwarden.py` puis
   `install-runtime-secret.sh`).
3. `sudo python3 scripts/truenas/register-litellm-app-keys.py` (plan), puis
   `--apply` ; budget Homarr porté à 5 USD/30 j.
4. Redéployer une App à la fois : `homarr`, `openwebui`, `langfuse`,
   `grafana`, `prometheus` ; puis `rollout-pending-apps.sh --apply` pour
   `plumber` et `ntopng` ; bootstrap admin puis redémarrage de `scanopy`
   (README).
5. `chmod 600` des onze `.env` de projet lisibles par tous (accord 5). Le
   redéploiement de Redis (accord 4) a été fait par l'autre session le 11/11
   à 09:50 UTC (B14 du runbook du 11/11).
