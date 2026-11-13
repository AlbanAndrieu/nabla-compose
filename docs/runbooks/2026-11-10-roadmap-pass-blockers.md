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

## 6. Reprise du 12/11 (accords 1, 2, 4, 5 de la section 5)

| Point | État | Preuve ou reste à faire |
| --- | --- | --- |
| 5.1 Vaultwarden | Champs ajoutés : `HOMARR_ASSISTANT_API_KEY`, `OPENWEBUI_LITELLM_API_KEY`, `LANGFUSE_AI_API_KEY`, `JOBS_REDIS_PASSWORD` ; item `nabla/prod/ntopng` créé ; login admin Scanopy rangé | Relecture : aucun champ manquant. Restent, par SSH : `HOMARR_API_KEY` (dernier caractère), item `nabla/prod/grafana` (`GRAFANA_ADMIN_PASSWORD` n'est que dans le `.env` TrueNAS) |
| 5.3 LiteLLM | Clés `homarr_assistant` (5 USD), `openwebui`, `langfuse`, `grafana` enregistrées (HTTP 200) | Replanification : `existing`, périmètre de modèles `verified` pour les quatre |
| Reboot | `--resume` puis `--verify` : 13 vagues RUNNING, 61 Apps en marche, 0 échec, 1 avertissement (audit ingress indisponible) ; phase `VERIFIED` | Le bundle `98d592f…` précède `4f9c00b6` et n'embarque pas `check-homelab-services.sh` : `--verify` lancé avec `NABLA_SERVICE_HEALTH_CHECK` pointant sur le checkout |
| 5.4 Redéploiements | Langfuse (web et worker `healthy`), Grafana (`/api/health` 200), Prometheus (Alertmanager prêt, receiver `slack` par `api_url_file`, fichier 600 non vide) redéployés ; Open WebUI recréé par le resume après ses secrets (`healthy`) ; ntopng déployé (`healthy`, capture `br0`) | Homarr tourne et sa clé API s'authentifie, mais `homarr-sync` sort en 1 (App `CRASHED`) : Homarr v2.6 exige `pingUrl` (corrigé dans `apps/homarr/sync.py`, à déployer). Plumber attend Q15 : pgx lit `sslrootcert` même en `prefer` |
| Slack (Q12) | `SLACK_WEBHOOK` vaut l'exemple `replace_this_with_your_slack_webhook` ; `SLACK_TOKEN` est le bot d'un espace d'entreprise, écarté | Créer un webhook entrant dans un espace perso, l'exporter en `SLACK_WEBHOOK`, puis `import_env_to_bitwarden.py --app prometheus` |
| Q8 / B7 | Rien de neuf | Vérifier par SSH les noms réels des datasets absents (Apps encore planifiées ?), puis supprimer les tâches 17 à 19 après un cycle des tâches par classe |
| Q11 | `planned` exclut déjà les quatre jobs depuis e5a4c165 : le Prometheus de TrueNAS n'a pas été rechargé. `postgres_exporter` passe dans `apps/postgres-exporter` (le répertoire `apps/postgres` portait le nom de l'App native) | `docker kill -s HUP prometheus` ; puis rôle `pg_monitor`, secret et App (`apps/postgres-exporter/README.md`). TLS : `lib/pq` refuse `prefer`, seul `disable` marche tant que Q15 n'est pas fait |
| Q16 | `s3.int` est le seul `*.int` public non autorisé (IP WAN) ; `hello.int` reste, c'est le canari approuvé | Plan d'adoption : 1 import, 0 ajout, 0 modification, 0 destruction. Apply, puis plan `retire` (1 destruction), puis apply |
| Q17 | Workflow `terragrunt-cd.yaml` retiré : aucun runner `infra-runners`, environnement `TrueNAS` vide, backend Garage LAN seul | Supprimer à la main l'environnement GitHub `TrueNAS`, vide |
| Q18 | 9 services sur 10 lisent `/mnt/cpool/secrets/runtime/<app>/` (`env_file` obligatoire) ; Redis reste, son mot de passe est interpolé dans `command:` | Par App : vérifier `root:root 600`, redéployer une à une (bichon, langflow, nexus, ollama, sentry-clickhouse, mongo, clickhouse, pihole en dernier), puis `--finalize`. Ne pas relancer `materialize_runtime.py --install` (Pi-hole perdrait `FTLCONF_webserver_api_password`) |
| Q19 | Aucun ticket amont ; v1.4.0 appelle toujours `auth.login_with_api_key` | Brouillon prêt, à publier sur accord |
| B12 | Le login admin `nabla/prod/defectdojo` n'a pas de mot de passe ; le MCP DefectDojo n'a pas d'URL | Lire `DD_ADMIN_PASSWORD` sur TrueNAS sans l'afficher, puis produit `nabla-compose`, engagement `Trivy images`, compte `nabla-import` (API Importer), jeton dans `nabla/prod/defectdojo-import` et `import-token` |
| Q15 | Aucune CA n'a existé : `runtime/postgres/tls/ca.crt` est un répertoire vide créé par Docker le 10/11. Traefik n'est qu'un client ACME (Let's Encrypt), pas une CA ; son STARTTLS PostgreSQL forcerait à changer hôte et port de chaque client | `sudo bash scripts/truenas/enable-postgres-tls.sh` (contrôle), puis `--apply` sur accord ; redéployer Keycloak, Plumber et Sample, puis repasser Plumber et Sample en `verify-full` |
| B6, Q13, Q14 | Rien de neuf | Demandent l'accès SSH (et une décision pour Q13) |

## 7. Suite du 12/11 au soir (accords Q13, Q15, B12, Scanopy)

| Point | État | Preuve ou reste à faire |
| --- | --- | --- |
| Q15 | Appliqué : CA locale dans `/mnt/cpool/secrets/pki/local-ca`, `ca.crt` publié à la place du répertoire vide, certificat serveur dans PGDATA, `ssl=on` TLS 1.3 minimum par rechargement | `--check` : 6/6 OK (TLS 1.3 vérifié contre la CA, TLS 1.2 rejeté). Sample redéployé (11 connexions TLSv1.3), Plumber déployé (4 connexions TLSv1.3). `verify-full` commité pour les deux : à redéployer après fusion |
| Q13 | App catalogue `bitcoind` supprimée avec ses `ix-volumes` (885 Go), Custom App créée sur `cpool/bitcoind`, nœud `healthy` (en-têtes en cours). Premier essai sous `systemd-run` arrêté sans effet par git (« dubious ownership », HOME de root) : relancé avec `GIT_CONFIG_*` `safe.directory` limité au processus | `cpool/bitcoin` (712 Go, 41 snapshots) non détruit : partage NFS 17 actif et automount `/media/bitcoin` dans le `/etc/fstab` de la workstation. Supprimer le partage, retirer l'entrée fstab (ansible-workstation ?), puis `zfs destroy -r cpool/bitcoin` |
| Plumber, ntopng | Déployés par `rollout-pending-apps.sh --apply` | 3 conteneurs Plumber sans erreur ; ntopng `healthy` |
| Scanopy | Admin initialisé : `.env` d'ouverture, redéploiement, `setup` 200 + `register` 200, `.env` supprimé, redéploiement | Login 200, inscription étrangère 403, `SCANOPY_DISABLE_REGISTRATION=true`, daemon injoignable depuis la workstation. Reste `bootstrap-repository-env-files.sh --finalize scanopy` |
| B12 | `DD_ADMIN_PASSWORD` du runtime ne correspond plus au compte admin (`api-token-auth` 400) | Script prêt : jeton admin par `manage.py drf_create_token admin` (sans `-r`), puis produit, engagement, compte `nabla-import`, item `nabla/prod/defectdojo-import` et `import-token` root 0600. Exécution refusée par le classifieur : à lancer par l'opérateur |
| Push | Le pre-push refuse : pointeur du sous-module `apps/openclaw` indexé par une autre session | Commiter ou désindexer ce pointeur, puis `git push` |

## 8. Reprise du 13/11

| Point | État | Preuve ou reste à faire |
| --- | --- | --- |
| Q15 clients | `defectdojo`, `langfuse`, `litellm`, `sentry` redémarrés ; Plumber et Sample redéployés en `verify-full` (0.74.0, checkout TrueNAS avancé par le cron de 01:00) | `pg_stat_ssl` : tous les rôles applicatifs en TLSv1.3 (`jobs` 4, `langfuse` 16, `sentry` 11, `litellm` 5, `scanopy` 4, `defectdojo` 1, `fastapisample` 11), seul le socket local d'administration reste en clair. Sample `healthy` après un démarrage de 3 min 40 (trois pauses d'environ 1 min avant Unleash, Logfire et Sentry, sans lien avec TLS : la connexion PostgreSQL prend 157 ms). `hostssl` appliqué ensuite par `enable-postgres-tls.sh --apply` (lancé par stdin depuis `scripts/truenas`, rien copié) : `--check` 8/8, connexion TCP en clair refusée, aucun client rejeté |
| B12 | Fait. Jeton admin par `DD_ADMIN_USER`/`DD_ADMIN_PASSWORD` de l'environnement opérateur (celui du runtime donne 400). DefectDojo 3.4 OSS n'a plus les rôles (`/roles/` 404, passés en Pro) : `nabla-import` (non staff) est dans `authorized_users` du produit `nabla-compose` | Jeton dans `nabla/prod/defectdojo-import` et `import-token` root 0600 ; avec ce jeton, engagement `Trivy images` 200, liste des utilisateurs 403 |
| Scanopy | `bootstrap-repository-env-files.sh --finalize scanopy` fait | — |
| Q13 bitcoin | Partage NFS 17 supprimé ; entrée `/etc/fstab` de la workstation retirée (copie `/etc/fstab.bak-20261113-bitcoin`), `/media/bitcoin` supprimé | Partage, montage et gabarit `bitcoind-systemd` retirés d'ansible-workstation (PR #24). `cpool/bitcoin` reste à 712 Go : à 01:48, `midclt call -j pool.dataset.delete` attendait depuis 1 h 45 sans job créé (`core.get_jobs` vide, `freeing` 0). Le dataset est démonté, sans snapshot ni enfant. À faire par l'opérateur : suppression depuis l'interface, ou arrêt du client bloqué puis `zfs destroy cpool/bitcoin` |
| Q11 | Rôle `postgres_exporter` (`pg_monitor`), item `nabla/prod/postgres-exporter` et runtime root 0600 faits (DSN `sslmode=require`, `lib/pq` ne connaît pas `prefer`). Activation commitée (App déclarée, `active`, job Prometheus sans `planned`) | App créée (`app.create`, wrapper `include` comme `reconcile-custom-apps.py`) et Prometheus rechargé : `up` = 1, mais `pg_up` = 0. Le renderer met le DSN entre apostrophes (il contient `?`) et `format: raw` les garde : corrigé dans #361. Le mot de passe du rôle a été affiché par un diagnostic le 13/11 : à changer (SCRAM calculé côté client, Vaultwarden, runtime), puis redéployer l'App et refaire le HUP après fusion |
| Sentry | Décision opérateur du 13/11 : `running` (`custom-apps.yml`). ~5,9 Gio pour 18 conteneurs ; ARC 11,7 Gio, PSI < 1 % | `/sentry-debug` (clé lue dans le conteneur, passée par stdin) : événement `083754a9` reçu (issue 3). MCP Sentry : `SENTRY_URL` exportée faisait refuser `--insecure-http` (« connection closed ») ; vidée pour ce serveur dans `.mcp.json` ; fastapi-sample visait `sentry.albandrieu.com`, derrière Access (302). Sa correction (API du LAN) est commitée sans push : le jeton Sentry y circule en HTTP sur le LAN, comme dans nabla-compose depuis #120. Risque à accepter, ou route TLS interne à créer |
