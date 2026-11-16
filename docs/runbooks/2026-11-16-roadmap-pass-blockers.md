# Passe roadmap du 16/11/2026 — catalogue, sondes et TrueNAS

Cette passe couvre deux sections de [la roadmap](../roadmap.md) : « P0 — Réception du catalogue et des sondes » et « P1 — Performance, stockage et restauration TrueNAS ».

Une session parallèle traite Cloudflare, H07, H11 et la fiabilité des scripts, sur la branche `fix/roadmap-pass-edge-pfsense-20261116`. Les sous-points Cloudflare et pfSense du diagnostic du 16/11 lui reviennent.

Tout ce qui ne demandait ni décision ni changement sur TrueNAS a été fait dans Git. Le reste figure en questions à la fin.

Les relevés TrueNAS ont été faits en SSH entre 01:30 et 01:55 CET, en lecture seule :
- `midclt app.query`, `app.config` et `cronjob.query` ;
- `docker ps`, `ss -ltn` et `ps` ;
- les modes `--plan` et `--check` des scripts versionnés ;
- `diagnose-performance.sh --quick` ;
- l'API Prometheus.

Aucun secret n'a été lu.

## 1. Fait dans Git pendant la passe

| Point roadmap | Changement | Preuve |
| --- | --- | --- |
| Catalogue : liaisons d'exécution | `runtime.appId` sur redis, nginx, dockhand, dozzle, drawio, ddns-updater et openhands. `x-nabla.runtime` ajouté sur adguardhome, ittools, stirling, postgresql et openclaw. Home Assistant et lidarr sont inchangés : le Compose de Home Assistant décrit la future Custom App `homeassistant` (H19), et la pile média `planned` interdit `appId`. | Identifiants lus dans `app.query` et `docker ps` ; générateurs `--check` ; suite complète (3 382 tests) |
| Sonde LanguageTool | La route publique sonde `/v2/languages` (`probePath` et `healthPath` legacy) | HTTP 200 depuis TrueNAS |
| Entités non déployées | affine, anythingllm, localai-gpu, netalertx, netbootxyz, openarchiver, portainer, sabnzbd et transmission passent en `planned` | Aucune App, aucun conteneur, aucun port en écoute |
| Plumber | Passe en `active` (3 entités) ; App déclarée `running` | App RUNNING depuis 3 jours ; HTTP 200 sur :31070 |
| `custom-apps.yml` | bitcoind, docker-socket-proxy, graylog et plumber déclarées. arti, databasus, plex, smart-home-dashboard et transmission retirées de `catalog_native`, ainsi que bitcoind et docker-socket-proxy. | Dossiers d'include lus dans `app.config` ; rejeu hors ligne de `classify` |
| Entités manquantes | `immich` et `glances` créées en `active`, avec route LAN et `probePath`. `emby`, `memos` et `tailscale` créées en `disabled`. BIA provisoire. | `/api/server/ping` et `/api/4/status` répondent 200 |
| Zombies | `init: true` sur scanopy (2 services), litellm et ntopng ; le test de contrat couvre aussi `kafka-exporter` | 17 zombies relevés, tous sous ces conteneurs |
| Noms publics `*-albandrieu` | Le propriétaire a décidé de retirer ces noms du tunnel workstation (branche `fix/roadmap-pass-edge-pfsense-20261116`). Les entités `anythingllm-albandrieu`, `plumber-albandrieu`, `portracker-albandrieu` et `stirling-albandrieu` perdent donc leur nom public, en v2 comme dans l'inventaire legacy, et gardent leur route LAN directe. | Sur le poste (172.17.0.57), :3007, :3001 et :8085 n'écoutent pas ; :4999 n'écoute qu'en boucle locale |
| Prometheus | Rien à changer | Les 13 cibles à `up=0` portent `operational_state="planned"`, ce qui les exclut de `NablaExporterTargetDown`. Les exporters OpenSearch (:9114, :9115) et HAProxy (:9101) ne sont déployés nulle part. |

### Suite du 16/11 après-midi (plan de performance, Talos, réception)

| Point roadmap | Changement | Preuve |
| --- | --- | --- |
| H01 CSI | Le rôle du controller peut lire les Pods (csi-resizer v2). Le smoke attend le marqueur de son écrivain et accepte un namespace jetable. | `install-truenas-csi-nfs.sh --apply` puis `--check` convergé ; PVC RWX écrit sur taloswk01 et relu sur taloswk02 |
| Plan perf. 4 | VMs Talos arrêtées par `just talos-vms-stop` (workers d'abord, autostart désactivé) | Snapshot etcd préalable sur le poste ; `MemAvailable` passe de 5,7 à 13 Gio ; `--check` : trois VMs `STOPPED` |
| Incident Talos | taloscp01 a tenu l'IP publique du WAN du 14 au 15/11 ([incident](../incidents/2026-11-14-talos-control-plane-public-wan-lease.md)). `config/talos/nodes/*.yaml` fixe adresse, passerelle et nom d'hôte. | `talosctl validate --mode metal --strict` hors ligne ; test de contrat |
| Plan perf. 1 | Profil `recordsize=16K` pour `cpool/ntopng` | `tests/test_dataset_profiles.py` |
| Plan perf. 6 et 8 | `mem_limit` (pic cgroup × 1,5) sur 11 services, rotation du journal de docker-socket-proxy, test cliquet | Relevé `memory.peak` des 133 conteneurs ; `docker compose config` ; générateurs `--check` |
| Plumber | CORS et URL du frontend sur `http://172.17.0.24:31070` (décision transmise par la session parallèle) | `docker compose config` |
| Réception TrueNAS 27 | `just truenas-fastapi-check` passe par `sudo -n` | Sans sudo : faux échec critique `docker_fastapi unknown` ; avec sudo : `warning`, aucun échec critique |

## 2. Constats en lecture seule

| Sujet | Constat |
| --- | --- |
| Uptime Kuma | Jamais déployée : pas de dataset `cpool/uptimekuma`, pas de volume Docker, pas de montage `ix-apps`, aucun `kuma.db` sous `/mnt/cpool`. Le MCP Uptime Kuma ne joint aucune instance. `autokuma` tourne sans cible. |
| `reconcile-custom-apps.py` | Rejeu de `classify` sur l'état réel. `MISSING → create` : cartography, keycloak, scorecard et uptimekuma. `clamav` : `RUNNING_BUT_DESIRED_STOPPED`, car la fenêtre nocturne n'est pas appliquée. openclaw-gateway et openclaw-devbox : `UNMANAGED_LIVE`, voulu (sous-module). `--apply` traite toutes les actions à la fois, et s'arrête sous 6 Gio disponibles : il en restait 5,7. |
| OpenClaw | La gateway n'écoute que sur `127.0.0.1:18789`. Rien n'écoute sur :30325, et `openclaw.albandrieu.com` ne répond pas depuis le poste. |
| Performance (01:47) | PSI IO `full` 7,2 % sur 5 min (10 % sur 1 min), contre 33 % le 15/11. PSI mémoire nulle. ARC 9,5 Gio (`c_min` 2,0). 5,7 Gio disponibles, aucun swap. Pools sains. Uptime 3 jours (reboot du 12/11 à 20:43). Les zombies de kafka ont disparu. |
| Redéploiement | `redeploy-impacted-apps.py --from 8e807691 --to 64f5c767` : clamav puis prometheus. bitcoind suit son propre cycle de vie. Le checkout TrueNAS est à `64f5c767` (cron horaire). |
| Volumes orphelins | `--plan` (`/var/tmp/nabla-docker-orphan-volumes.tsv`) : 59 `candidate:anonymous` (48,6 Mo), 33 `review:recent`, 8 `review:unsized`, 2 `review:large` (195 et 122 Mo), 2 `review:foreign-project` (`nabla-compose_op_data`) et 8 `keep:installed-app`. |
| Snapshots ZFS | `--plan` : 1 tâche manquante (`cpool/bitcoind`, mensuelle, 1 mois). 5 datasets de la politique sont absents (ddns-updater, neo4j, opencre, recyclarr, uptimekuma), pour des Apps non déployées. 0 dérive. 0 tâche sur un dataset `noSnapshot`. |
| Fenêtre nocturne | `--check` liste 15 Apps et 2 tâches. Les tâches cron ne sont pas créées, donc rien n'arrête les Apps à 07:00. bitcoind reste STOPPED. |
| `clamav-scan` | Tâche cron root gérée par ansible-workstation (`truenas-stabilize.yml`), 06:00 le 1er du mois. Les journaux du 1/09 (82 octets) et du 1/11 (229 octets) s'arrêtent après quelques secondes, sans résumé : le scan mensuel ne va pas au bout depuis au moins septembre. Il tombera aussi dans l'arrêt de 07:00. |
| SMART longs | Tâches à 02:00 les 7, 14, 21 et 28 du mois : elles tombent dans la fenêtre nocturne, déjà chargée en IO par bitcoind. |

## 3. Questions pour l'opérateur

Les questions numérotées, avec commande, impact et retour arrière, figurent dans le compte rendu de la passe. En voici l'index (mis à jour l'après-midi du 16/11).

1. Redéployer clamav (Prometheus relit déjà ses règles depuis cba8016b).
2. Créer les tâches cron de la fenêtre nocturne.
3. Uptime Kuma : la déployer, ou la passer en `planned` avec `autokuma`.
4. cartography et scorecard : les créer, ou les passer en `planned`.
5. OpenClaw : retirer la route LAN :30325 du catalogue, ou publier un port dans le sous-module.
6. `clamav-scan` : corriger le scan, et l'avancer dans la fenêtre ou sortir clamav de la fenêtre (ansible-workstation). Y joindre le déplacement des tests SMART longs (plan perf. 5).
7. Créer la tâche de snapshot mensuelle de `cpool/bitcoind`.
8. Purger les 59 volumes `candidate:anonymous`.
9. Après fusion : redéployer scanopy, litellm et ntopng (zombies), plumber (CORS) et les Apps qui reçoivent une limite mémoire.
10. Relire les BIA provisoires d'immich, glances et Plumber.
11. Services du poste : passer anythingllm et stirling `-albandrieu` en `disabled` ; portracker : écoute LAN ou retrait de la route.
12. Appliquer `recordsize=16K` sur `cpool/ntopng`, puis réécrire les fichiers existants, ntopng arrêté.
13. Abandonner le point 2 du plan (`recordsize` des bases), dont le gain mesuré est faible.
14. Au redémarrage de Talos : appliquer l'adressage statique des nœuds, supprimer le nœud fantôme et les namespaces de smoke, puis vérifier le reclaim ZFS.
15. Chemin de niveau 2 entre `br0` et la Freebox (incident du 14/11), côté pfSense et commutateur.
16. H08 : premier `--apply` de `rollout-pending-apps.sh` (netbox, dependency-track ou joplin).
17. CSI : passer de `truenas-csi` v1.0.3 à une version sans `auth.login_with_api_key`, testée au redémarrage de Talos.

### Décisions de l'opérateur (16/11 soir)

« Tes suggestions me conviennent, met les en production », « modifie les 151 autres services d'un coup », « Ok pour les planned ». Traduites dans Git :
- Q3 et Q4 : uptimekuma, autokuma, cartography et scorecard passent en `planned`. Les trois Apps jamais déployées sortent de `custom-apps.yml`, et autokuma y est déclarée `stopped`.
- Q5 et Q11 : les routes LAN d'OpenClaw (:30325) et de portracker (:4999) sont retirées ; anythingllm et stirling `-albandrieu` passent en `disabled`.
- Q12 : `rewrite-ntopng-records.sh` réécrit une fois les fichiers de ntopng. Q13 : point 2 du plan abandonné.
- Plan perf. 8 : rotation des journaux sur les 151 services restants.
- `just` est déjà installé sur TrueNAS (1.58.0, `bootstrap-dev-tools.sh`). Il est dans le PATH des shells interactifs (`ssht`), pas dans celui des commandes SSH non interactives (`bash -ic`), ni sous `sudo`.
- Q17 (CSI) reste ouvert : les notes de v1.3.0 et v1.4.0 ne disent pas si `auth.login_ex` remplace `auth.login_with_api_key`. Q14 attend le prochain démarrage de Talos. Q15 est transmise à la session pfSense.
