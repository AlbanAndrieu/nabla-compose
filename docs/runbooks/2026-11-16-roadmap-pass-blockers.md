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
| Prometheus | Rien à changer | Les 13 cibles à `up=0` portent `operational_state="planned"`, ce qui les exclut de `NablaExporterTargetDown`. Les exporters OpenSearch (:9114, :9115) et HAProxy (:9101) ne sont déployés nulle part. |

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

Les questions numérotées, avec commande, impact et retour arrière, figurent dans le compte rendu de la passe. En voici l'index.

1. Redéployer Prometheus et clamav, qui relisent les règles d'alerte du 15/11.
2. Créer les tâches cron de la fenêtre nocturne.
3. Uptime Kuma : la déployer, ou la passer en `planned` avec `autokuma`.
4. cartography et scorecard : les créer, ou les passer en `planned`.
5. OpenClaw : retirer la route LAN :30325 du catalogue, ou publier un port dans le sous-module.
6. `clamav-scan` : corriger le scan, et l'avancer dans la fenêtre ou sortir clamav de la fenêtre (ansible-workstation).
7. Créer la tâche de snapshot mensuelle de `cpool/bitcoind`.
8. Purger les 59 volumes `candidate:anonymous`.
9. Après fusion : redéployer scanopy, litellm et ntopng (zombies).
10. Relire les BIA provisoires d'immich, glances et Plumber.
