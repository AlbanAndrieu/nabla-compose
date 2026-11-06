# Migration des Apps catalogue TrueNAS vers des Custom Apps Compose

**Décision du propriétaire (6 novembre 2026)** : corriger d'abord l'existant,
puis migrer toutes les Apps natives du catalogue TrueNAS (`custom_app=false`)
vers des Custom Apps issues de `apps/<app>/compose.yml`, **avant** de déployer
les services encore `planned`. Une Custom App inclut le Compose du dépôt
(`include: /mnt/cpool/compose/nabla-compose/apps/<app>/compose.yml`) : le dépôt
devient la seule source de vérité, et les scripts de cycle de vie, de reboot et
de catalogue couvrent toutes les Apps.

Procédure de référence par App : [Dockhand](../../apps/dockhand/README.md) et
[DDNS Updater](../../apps/ddns-updater/README.md) (PR #327).

## Inventaire de référence

Relevé en lecture seule le 2026-11-05 à 23:57, juste avant le `--prepare` du
reboot : 48 Apps natives, dont 6 seulement ont un `compose.yml` sur master
`31daa583`. `ixVolume` = données sous `cpool/ix-apps/app_mounts/<app>/<clé>`,
à copier. `hostPath` = données déjà sous `/mnt/cpool`, à remonter tel quel.

| Vague | Critère | Apps |
| --- | --- | --- |
| 0 | Compose déjà dans le dépôt | dockhand, ddns-updater (PR #327), docker-socket-proxy, portracker, bitcoind, n8n, postgres |
| 1 | Sans stockage, risque faible | glances, it-tools, open-speed-test, three-proxy |
| 2 | `hostPath` uniquement | clamav, databasus, emby, freshrss, memos, open-terminal, plex, reactive-resume, searxng, speedtest-tracker, transmission, zabbix, immich |
| 3 | `ixVolume` (copie de données) | convertx, domain-watchdog, heimdall, karakeep, paperless-ai, paperless-ngx, pgadmin, stirling-pdf, twofactor-auth, localai (mixte) |
| 4 | Critiques : fenêtre dédiée et retour arrière testé | cloudflared (ingress), adguard-home (DNS), home-assistant |
| — | STOPPED au relevé : décider migrer ou retirer | arti, cleanuparr, elastic-search, hermes-agent, kasm-workspaces, lidarr, netdata, smart-home-dashboard, tailscale, tracearr, wizarr |

Versions, ports publiés et clés de stockage relevés :

| App | Version catalogue | État | Ports | Stockage |
| --- | --- | --- | --- | --- |
| adguard-home | v0.107.79_1.3.19 | RUNNING | dns 553, web 30004 | config, work : ixVolume |
| arti | 2.6.0_1.3.15 | STOPPED | socks 9150 | arti_config, arti_state : ixVolume |
| bitcoind | 31.1_1.1.25 | STOPPED | p2p 8333, rpc 8332 | bitcoin : ixVolume |
| clamav | 1.5.4_1.4.15 | RUNNING | clamd 30005, milterd 30006 | hostPath `/mnt/cpool/logs`, `/mnt/cpool`, `/mnt/cpool/clamav` |
| cleanuparr | 2.10.7_1.1.36 | STOPPED | web 30263 | config : ixVolume |
| cloudflared | 2026.10.4_2.0.32 | RUNNING | — | — |
| convertx | v0.19.0_1.1.13 | RUNNING | web 30154 | data : ixVolume |
| databasus | v3.64.0_1.0.54 | RUNNING | web 30405 | hostPath `/mnt/cpool/databasus` |
| ddns-updater | v2.10.0_1.3.19 | RUNNING | web 30007 | data : ixVolume |
| docker-socket-proxy | v0.5.0_1.1.12 | RUNNING | tcp 2375 | — |
| dockhand | v1.0.55_1.1.44 | RUNNING | web 30328 | data : ixVolume |
| domain-watchdog | v1.4.6_1.2.46 | RUNNING | web 30317 | config, data, postgres_data : ixVolume |
| elastic-search | 9.5.5_1.4.26 | STOPPED | web 30003 | hostPath `/mnt/cpool/elasticsearch/data` |
| emby | 4.10.2.0_1.4.13 | RUNNING | http 8096, https 8920 | hostPath `/mnt/cpool/emby` |
| freshrss | 1.30.4_1.7.42 | RUNNING | web 30108 | hostPath `/mnt/cpool/freshrss/{data,extension,postgres}` |
| glances | 4.5.8_1.1.16 | RUNNING | web 30015 | — |
| heimdall | 2.8.3_1.1.17 | RUNNING | http 30119, https 30120 | config : ixVolume |
| hermes-agent | v0.22.4_1.0.33 | STOPPED | dashboard 30433, gateway 30432 | hostPath `/mnt/cpool/hermes` |
| home-assistant | 2026.10.4_1.8.82 | RUNNING | web 30103 | hostPath `/mnt/cpool/ha/{config,media,postgres}` |
| immich | v3.3.5_1.14.58 | RUNNING | web 30041, metrics 30363/30364 | hostPath `/mnt/cpool/immich/{data,ml,pgData}` |
| it-tools | 2024.10.22-7ca5933_1.1.11 | RUNNING | web 30063 | — |
| karakeep | 0.34.1_1.2.50 | RUNNING | web 30147 | data, meili_data : ixVolume |
| kasm-workspaces | 1.19.0_1.1.8 | STOPPED | web 30128, setup 30129 | opt, profiles : ixVolume |
| lidarr | 3.1.5.5066_1.4.12 | STOPPED | web 30071 | hostPath `/mnt/cpool/lidarr` |
| localai | v4.12.1_1.1.43 | RUNNING | web 30286 | hostPath `/mnt/cpool/localai/{backends,config,models}` ; data : ixVolume |
| memos | 0.31.0_1.2.47 | RUNNING | web 30311 | hostPath `/mnt/cpool/memos/{data,postgres}` |
| n8n | 2.45.4_1.10.155 | RUNNING | web 30109 | hostPath `/mnt/cpool/n8n/{data,postgres}` |
| netdata | v2.12.2_1.4.24 | STOPPED | web 20489 | hostPath `/mnt/cpool/netdata/{config,lib}` ; cache : ixVolume |
| open-speed-test | v2.0.8_1.1.11 | RUNNING | http 30116, https 30117 | — |
| open-terminal | 0.14.5_1.0.38 | RUNNING | api 30377 | hostPath `/mnt/cpool/openterminal` |
| paperless-ai | 3.0.9_1.1.11 | RUNNING | web 30226 | data : ixVolume |
| paperless-ngx | 3.3.4_1.6.71 | RUNNING | web 30070 | consume, data, media, postgres_data, trash : ixVolume |
| pgadmin | 9.18_1.3.17 | RUNNING | web 30056 | config : ixVolume |
| plex | 1.43.5.11079-b3b13e506_1.3.21 | RUNNING | web 32400 | hostPath `/mnt/cpool/plex/{config,data}` ; logs, transcode : temporary |
| portracker | 1.3.14_1.1.18 | RUNNING | web 30233 | data : ixVolume |
| postgres | 18.6-trixie_1.5.42 | RUNNING | tcp 5432 | hostPath `/mnt/cpool/postgres` |
| reactive-resume | v5.3.0_1.0.63 | RUNNING | web 30393 | hostPath `/mnt/cpool/reactive/{data,postgres}` |
| searxng | 2026.10.25-54ca1d9cf_1.4.139 | RUNNING | web 30053 | hostPath `/mnt/cpool/searxng` |
| smart-home-dashboard | 3.21.31_1.0.32 | STOPPED | web 30436 | hostPath `/mnt/cpool/smart` |
| speedtest-tracker | 1.15.1_1.1.26 | RUNNING | http 30220, https 30221 | hostPath `/mnt/cpool/speedtest` |
| stirling-pdf | 3.2.2_1.1.40 | RUNNING | web 30124 | configs, custom_files, logs, pipeline, tesseract_data : ixVolume |
| tailscale | v1.102.3_1.4.14 | STOPPED | — | state : ixVolume |
| three-proxy | 2.5.0_1.1.18 | RUNNING | proxy 30388, socks 30389 | — |
| tracearr | 2.2.3_1.2.56 | STOPPED | web 30316 | hostPath `/mnt/cpool/tracearr` |
| transmission | 4.1.3_1.3.16 | RUNNING | peer 50413, web 30096 | hostPath `/mnt/cpool/transmission/{config,downloads/complete,downloads/incomplete}` |
| twofactor-auth | 8.0.3_1.3.21 | RUNNING | web 30081 | config : ixVolume |
| wizarr | v2026.9.0_1.1.12 | STOPPED | web 30229 | hostPath `/mnt/cpool/wizarr` |
| zabbix | 7.4.16-ubuntu_1.0.50 | RUNNING | server 30385, web 30386 | hostPath `/mnt/cpool/zabbix` |

## Méthode par App

1. **Lecture seule** : exporter le Compose rendu de l'App catalogue en
   **masquant toutes les valeurs d'environnement** (clés conservées), relever
   l'image exacte, l'utilisateur, les ports, les volumes et le healthcheck.
2. **Dépôt** : écrire `apps/<app>/compose.yml` avec :
   - la même image et la même version, sans retour arrière ;
   - ports liés à `172.17.0.24` et numéros de port conservés ;
   - données sous `/mnt/cpool/<app>` et secrets sous
     `/mnt/cpool/secrets/runtime/<app>/` (mappage Vaultwarden dans
     `config/secrets/manifest.json`) ;
   - `x-nabla`, `catalog-info.yaml` et entity-ref, puis régénérer les
     contrats ; réutiliser les services partagés (PostgreSQL, Redis) quand
     c'est compatible, sinon documenter l'exception.
3. **Bascule**, App par App :
   - snapshot ;
   - arrêt de l'App catalogue ;
   - copie des `ixVolume` ;
   - `app.delete` avec `remove_ix_volumes: false` (retour arrière) ;
   - `app.create` du wrapper `include` ;
   - acceptation : listener, sonde, fonction métier.
4. **Retour arrière** : supprimer la Custom App et réinstaller l'App catalogue
   sur ses volumes conservés.

Aucune bascule n'est automatisée par ce document. Chaque vague est une PR
distincte, et chaque bascule demande une approbation runtime explicite.
