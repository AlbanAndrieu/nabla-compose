# Passe roadmap du 11/11/2026 — fait et blocages

Suite de la [passe du 10/11](2026-11-10-roadmap-pass-blockers.md). Chaque blocage indique ce qui
a été tenté, pourquoi ça bloque et comment réessayer.

## Fait le 11/11

| Sujet | Action | Preuve |
| --- | --- | --- |
| PR #346 (Q4 du 10/11) | Fusionnée (`30d1958b`), checkout TrueNAS avancé par `cron.sh` (`NABLA_CRON_FASTAPI_UPDATE=false`) | `14bc1567 -> 30d1958b` |
| FastAPI Sample | `midclt call -j app.redeploy sample` : `sslmode=prefer` tant que PostgreSQL tourne en `ssl=off` | `/health` `healthy` 4/4, 0 redémarrage (361 avant) |
| Docker Socket Proxy (Q9) | `deploy-docker-socket-proxy.sh --apply --replace-catalog-app` | Custom App `healthy` sur `docker-proxy` et `intranet`, `POST=0`, `EXEC=0`, `BUILD=0` (l'App catalogue avait `POST/EXEC/BUILD=1` et n'était joignable par personne) |
| Talos CSI (Q7) | Pod `truenas-csi-controller-…-qbk5n` supprimé : reste `Failed` de l'arrêt du nœud du 23/10 | Déploiement 1/1 |
| `pihole-dns-sync` | Repart seul une fois le proxy joignable et les sessions Pi-hole expirées (5 005 redémarrages avant, `api_seats_exceeded`) | 23:51 UTC : authentifié, routes et DNS synchronisés, plus de redémarrage |
| etcd | Snapshot local `~/.local/state/nabla/talos/etcd-20261111T0055.snapshot` (0600, 341 clés) | `talosctl etcd snapshot` |
| Redis (B14) | Empreintes `REDIS_AUTH` comparées sans afficher de valeur (`apps/redis/.env`, `secrets/runtime/redis/.env.compose`, Langfuse : identiques au mot de passe en service), puis `midclt call -j app.redeploy redis` à 09:50 UTC | `PING` authentifié `PONG`, 3 bases ; clients reconnectés seuls (dernière erreur de connexion 09:50:24), 0 erreur d'authentification |
| Pyroscope (B9) | Metastore sauvegardé (`/mnt/cpool/pyroscope/data/.metastore-backup-20261111T114039Z`, 70 Mo), puis `docker restart -t 60 pyroscope` à 11:41 UTC | Leader stable, compaction reprise, `/ready` 200 à 11:44 ; journal 79 Ko/min (≈ 840 Ko/min avant) |
| Cron FastAPI Sample | Liens morts `/mnt/cpool/sample/.env{,.secrets}` retirés à 12:36 UTC (voir plus bas) | Passages de 15:00 et 17:00 UTC réussis, Sample 1.32.0, post-check d'env OK |
| SLOG de `cpool` (B1) | Partition vide `sde3` (16 Go) du SSD de démarrage ajoutée en `log` à ~17:41 UTC | Écriture synchrone 4 Kio : 88 ms → 2,9 ms ; etcd « took too long » : 35 à 105/min (17:36–17:43) → 0 à 2/min (17:47–17:49) |
| Dataset système | `systemdataset.update` vers `boot-pool` à 17:47 UTC | syslog, rrd et netdata n'écrivent plus sur les disques durs |
| Snapshots (B7) | 20 datasets `noSnapshot` exclus des tâches 17, 18 et 19 ; 114 tâches par classe créées | `reconcile-snapshot-tasks.sh --plan` : `missing=0 covering-no-snapshot=0` |

## Blocages

### ~~B1. etcd lent : aucun SSD libre~~ (SLOG ajouté le 11/11)

- Constat : 437 « apply request took too long » en 25 min (p50 197 ms, p90 548 ms, max 1,37 s).
  Les sidecars du contrôleur CSI perdent leur bail (`etcdserver: request timed out`). Les 3 disques
  de VM Talos sont des zvols de `cpool` (RAIDZ2 de 4 HDD, ~88 ms par écriture synchrone).
- Seul SSD : le disque de démarrage `sde`, Kingston SKC600 256 Go en USB 3.0 (UAS, lien 5 Gb/s sur
  un port 20 Gb/s), 93 % de durée de vie, 442 Mo/s en lecture. Il porte `boot-pool` (32 Go utilisés
  sur 222) et une partition de 16 Go vide depuis l'installation de 2022 (`sde3`).
- Retenu par l'opérateur : `sde3` en SLOG de `cpool` (`zpool add cpool log`), plutôt que
  `sync=disabled` sur le zvol d'etcd. Toutes les écritures synchrones en profitent (etcd, PostgreSQL,
  NFS, VM). Réversible : `zpool remove cpool <partuuid>`. Non géré par l'interface TrueNAS ; si le
  SSD meurt, réinstaller TrueNAS puis `zpool import -m cpool`.
- Contrôle : `talosctl -n 172.17.0.50 logs etcd --tail 5000 | grep -c 'took too long'`, à comparer
  par fenêtre de 10 min.

### ~~B2. Publication nabla-compose depuis le checkout partagé~~ (contourné le 11/11)

- Le checkout partagé porte la branche et l'index d'une autre session. Avec l'accord de l'opérateur,
  les correctifs passent par un clone séparé (`~/w/nabla-compose-claude`), hooks installés.

### B4. Secrets à matérialiser : pas de session Vaultwarden

- Bloque Homarr (Q5, `HOMARR_API_KEY`), code-server sans mot de passe (Q1, `PASSWORD`), Wazuh
  (Q2) et les Apps en attente (Q6) : `materialize_runtime.py` exige `BW_SESSION` ; `bw` n'est pas
  installé sur TrueNAS. Déverrouiller le coffre demande le mot de passe maître : opérateur.
- Réessayer : `export BW_SESSION="$(bw unlock --raw)"` dans le terminal de l'opérateur, puis
  `python3 scripts/secrets/materialize_runtime.py --app homarr --install` (idem `code`), puis
  `midclt call -j app.redeploy homarr` (idem `code`).

### B5. Vaultwarden `/admin` derrière Access (Q3) : jeton Cloudflare

- `CLOUDFLARE_API_TOKEN` vient de Vaultwarden (B4).
- Réessayer : `cd terraform/cloudflare && tofu plan` (attendu : 1 ajout), puis `tofu apply`.

### B6. Cron `clamav-cleanup` (ansible-workstation) : apply par l'opérateur

- Le plan ne contient que la mise à jour du cron 5 (motif `clamav-scan-*.log`). Depuis
  `~/w/ansible-workstation` :
  `.venv/bin/ansible-playbook -i truenas, playbooks/truenas-stabilize.yml -e truenas_stabilize_apply=true -e truenas_stabilize_apply_approved=true`

### B7. Snapshots ZFS (Q8) : reste la suppression des tâches globales

- Fait : exclusions puis création (voir « Fait le 11/11 »). Les tâches 17 (mensuelle, 1 an),
  18 (hebdomadaire, 12 semaines) et 19 (quotidienne, 30 jours) couvrent encore tout le reste de
  `cpool`, en doublon des tâches par classe : 11 958 snapshots le 11/11.
- Suite à décider : supprimer 17, 18 et 19 une fois les tâches par classe vérifiées sur un cycle
  (les snapshots existants expirent selon leur rétention). 9 datasets de la politique n'existent
  pas (`neo4j`, `ddns-updater`, `opencre`, `recyclarr`, `bitcoind`) : corriger
  `config/truenas/snapshot-tasks.json`.

### B8. Hermes, Keycloak, Vault sur Talos : la gate NetworkPolicy ne peut pas passer

- Le CNI est **flannel**, qui accepte les NetworkPolicy sans les appliquer :
  `smoke-networkpolicy-enforcement.sh` échoue par construction.
- Retenu par l'opérateur : **Cilium** (filtrage par nom de domaine pour Telegram/Discord).
  Bascule réseau de tout le cluster : `cluster.network.cni.name: none` dans la config Talos (et
  `cluster.proxy.disabled: true` si Cilium remplace kube-proxy), puis Cilium par Helm. Restent aussi les digests d'images à épingler dans
  `kubernetes/hermes` et `kubernetes/keycloak`.
- Réessayer : `bash scripts/talos/smoke-networkpolicy-enforcement.sh` vert, puis
  `kubectl apply -k kubernetes/keycloak` et `kubernetes/hermes`.

### ~~B9. Pyroscope : metastore Raft sans leader depuis le 6/11~~ (levé le 11/11 à 11:41 UTC)

- Cause : le 6/11 à 20:40:11 UTC, une écriture du journal Raft dépasse 10 s (`log store write
  timed out after 10s`, latence de `cpool`). Elle aboutit quand même en arrière-plan ; à chaque
  élection, Raft retente l'index 366111 et `raft-wal` le refuse (`non-monotonic log entries`) :
  ~657 000 élections perdues. Bogue connu
  ([grafana/pyroscope#5432](https://github.com/grafana/pyroscope/issues/5432),
  [#5307](https://github.com/grafana/pyroscope/pull/5307)) : un redémarrage suffit, sans perte.
- Peut revenir sous forte latence : même remède. Suivre une version qui intègre
  [#5536](https://github.com/grafana/pyroscope/pull/5536) (sortie sur dépassement, redémarrage
  par Docker).
- Les options `-metastore.raft.dir` et `-metastore.data-dir` du Compose sont sans effet : l'état est
  dans `data/v2/metastore`, relatif au `working_dir`, sur le dataset persistant.
- Contrôle : `sudo tail -n 5000 <LogPath> | grep -c 'not the leader'` doit valoir 0.

### ~~B10. Loki : erreur du compacteur à chaque requête~~ (code le 11/11)

- `limits_config.deletion_mode: disabled` alors que les requêteurs demandent
  `GetCacheGenNumbers` au compacteur : `deletion is not available for this tenant` deux fois par
  requête.
- Décision de l'opérateur : `filter-only` (l'API de suppression peut masquer des lignes à la
  lecture ; rien n'est effacé du stockage). Prend effet au prochain `app.redeploy grafana`.

### Apps arrêtées dans Gatus (11/11)

- OpenHands, DDNS Updater, Dozzle, Dockhand et Draw.io sont arrêtées : marquées
  `albandrieu.com/operational-state: disabled`, elles sortent de Gatus, Homarr et AutoKuma. Les
  repasser en `active` au redémarrage, puis régénérer (`scripts/generate-service-consumers.py`).

### ~~B11. Journaux Docker sans rotation sur TrueNAS~~ (code le 11/11)

- `logging: json-file, max-size 10m, max-file 3` ajouté à `loki` et `pyroscope`, comme `bitcoind`.
  Prend effet au prochain `app.redeploy grafana` et `app.redeploy pyroscope` (le journal de 6 Go de
  Pyroscope disparaît avec son conteneur).

### B12. Import DefectDojo : jeton et engagement absents

- DefectDojo est `RUNNING`. `import-scan-defectdojo.sh --apply` exige
  `/mnt/cpool/secrets/runtime/defectdojo/import-token` (root:root 0600) : **absent** (B4), et un
  `DEFECTDOJO_ENGAGEMENT_ID` existant : aucun n'est documenté.
- Réessayer : créer le produit et l'engagement dans l'UI, matérialiser le jeton d'un compte
  d'import dédié, puis `--check` et `--apply` avec un rapport Trivy d'une image du dépôt.

### ~~B13. Mise à jour FastAPI Sample : attente de santé trop courte sous charge~~ (code le 11/11)

- Échec du cron du 10/11 à 18:10 : pas de réponse dans les 90 essais de 2 s ; les imports Python
  ont pris plus de 4 min. `update-fastapi-sample.sh` attend maintenant 180 essais (6 min).

### ~~B14. Redis non redéployé~~ (levé le 11/11 à 09:50 UTC)

- Voir « Fait le 11/11 ». `diagnose-shared-data-services.sh` lisait
  `secrets/runtime/redis/.env.secrets`, absent : il lit maintenant `.env.compose`, où
  `apps/redis/.env` est matérialisé, et teste donc vraiment l'authentification.

## Cron FastAPI Sample : échec du post-check d'env (11/11, 12:12 UTC)

- Cause : `fd98421b` (10/11 19:39) a déplacé l'env de Sample vers `secrets/runtime/fastapisample`,
  mais les liens `/mnt/cpool/sample/.env{,.secrets}` visaient encore `runtime/sample`, supprimé vers
  11:57 UTC. `bootstrap-repository-env-files.sh --check sample` les traitait en source à migrer :
  `exit=1` en fin de mise à jour, alors que Sample était déployé et sain.
- Corrigé sur TrueNAS : les deux liens morts retirés (aucun lecteur, cibles absentes).
- Code : `update-fastapi-sample.sh` écrit dans le mail les lignes `❌`/`⚠️` du contrôle (chemins
  seuls, jamais de valeur) au lieu d'un fichier `/tmp` privé ; `bootstrap-repository-env-files.sh`
  indique `sudo unlink` sur un lien mort ; README de Sample à jour.
- Reste : `litellm: http_401` dans la recette IA de Sample (clé virtuelle refusée), à traiter à part.

## Mesures TrueNAS

| Moment (UTC) | PSI `io full` | Charge | `cpool` |
| --- | --- | --- | --- |
| 11/11 00:10 | 55 à 60 % | 19 | ~670 écritures/s à 61 ms |
| 11/11 11:45 | ~30 % | 5,8 | ~300 écritures/s à 55 ms |
