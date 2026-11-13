# Audit TrueNAS du 12-13/11/2026 — SSD, Gatus/Prometheus, sondes Sample, couverture

Audit en lecture seule de `nabla` (172.17.0.24), du 12/11 22:59 au 13/11 00:35 UTC, trois heures
après le redémarrage de 19:43 UTC. Aucune App n'a été redéployée pendant l'audit. Les
redéploiements de Sample (22:57) et de Sentry (23:13) observés viennent d'autres acteurs.

## 1. Passage sur le SSD

Source : [passe du 11/11](2026-11-11-roadmap-pass-blockers.md), blocage B1.

| Date (UTC) | Changement |
| --- | --- |
| 11/11 ~17:41 | Partition vide `sde3` (16 Go) du SSD de démarrage (Kingston SKC600, USB 3.0) ajoutée en `log` (SLOG) de `cpool` (RAIDZ2 de 4 HDD) |
| 11/11 17:47 | Dataset système (syslog, rrd, netdata) déplacé vers `boot-pool` (même SSD) |

Rien d'autre n'a été déplacé : les données des Apps, les zvols Talos et l'ARC restent sur `cpool`.

### Comparatif avant / après (Prometheus, `job="truenas_node"`)

Moyenne / p95 sur des pas de 1 min (5 min pour 7 j). `sd[a-d]` = les 4 HDD, `sde` = SSD, `zd*` =
zvols des VM Talos. Fenêtres : **avant 7 j** 04/11 17:30 → 11/11 17:30 ; **avant 24 h** 10/11
17:30 → 11/11 17:30 ; **après 24 h** 11/11 18:45 → 12/11 18:45 (après la bascule Cilium de 18:30-18:40) ;
**après redémarrage** 12/11 20:00 → 23:00 (reprise des Apps par vagues).

| Métrique | Avant 7 j | Avant 24 h | Après 24 h | Après redémarrage |
| --- | --- | --- | --- | --- |
| Latence écriture HDD (ms/op) | 11,1 / 24,1 | 13,2 / 37,0 | **2,7 / 3,1** | 4,4 / 8,3 |
| Latence lecture HDD (ms/op) | 39,1 / 79,8 | 42,4 / 83,4 | **28,0 / 38,8** | 42,8 / 86,9 |
| IOPS HDD (lecture + écriture, 4 disques) | 322 / 481 | 342 / 520 | **170 / 231** | 459 / 1 044 |
| IOPS écriture HDD | 292 / 389 | 301 / 379 | **161 / 205** | 358 / 1 003 |
| Occupation HDD (% `io_time`, moyenne par disque) | 29,8 / 55,2 | 32,9 / 59,4 | **11,1 / 18,4** | 45,7 / 70,0 |
| Latence écriture zvols Talos (ms/op) | n/d / 6,8 | 6,3 / 24,9 | **1,9 / 2,9** | 6,1 / 18,7 |
| Latence écriture SSD `sde` (ms/op) | 0,21 / 0,25 | 0,21 / 0,27 | 0,75 / 0,78 | 1,08 / 1,65 |
| IOPS écriture SSD `sde` | 26 / 33 | 28 / 41 | 65 / 69 | 171 / 396 |
| CPU occupé (%) | 17,7 / 46,1 | 19,0 / 56,8 | **10,1 / 12,2** | 30,4 / 58,4 |
| iowait (%) | 8,4 / 32,8 | 10,7 / 49,0 | **1,7 / 3,8** | 16,6 / 41,6 |
| load1 | 5,9 / 14,9 | 5,6 / 21,7 | **1,9 / 3,3** | 7,0 / 18,3 |
| PSI io « some » (%) | 17,2 / 59,6 | 20,7 / 71,0 | **5,1 / 10,9** | 32,5 / 61,1 |
| PSI io « full » (%) | 15,9 / 55,3 | 19,2 / 65,8 | **4,8 / 10,2** | 28,8 / 52,9 |
| Processus bloqués (état D) | 2,5 / 9 | 2,7 / 14 | **0,2 / 1** | 4,0 / 15 |
| Gatus HTTP, médiane des sondes OK (ms) | 0,88 / 0,96 | 0,88 / 0,96 | 0,87 / 0,95 | 0,89 / 1,00 |
| Gatus HTTP, sonde OK la plus lente (ms) | 50,8 / 68,5 | 34,6 / 19,8 | 17,0 / 14,8 | 171,9 / 161,6 |
| Sondes Gatus en échec | 16,4 / 27 | 5,4 / 7 | 0,5 / 5 | 2,6 / 13 |
| *Charge : sondes Gatus OK* | 58,5 / 63 | 57,6 / 58 | 58,0 / 58 | 55,7 / 59 |
| *Charge : mémoire utilisée (Gio)* | 54,0 / 56,0 | 54,4 / 55,7 | 56,5 / 57,5 | 52,6 / 57,1 |
| *ARC (Gio)* | 7,4 / 10,7 | 6,8 / 8,0 | 6,3 / 7,0 | 8,8 / 13,3 |

Lecture :

- À charge égale (≈ 58 sondes OK, 54-56 Gio utilisés), la latence d'écriture des HDD baisse de
  79 % (13,2 → 2,7 ms, p95 37 → 3,1 ms) et celle des zvols Talos de 70 % (p95 24,9 → 2,9 ms).
- Les IOPS d'écriture HDD sont presque divisées par deux (301 → 161) : le ZIL n'est plus écrit
  sur le RAIDZ2 et le dataset système ne l'est plus du tout. Le SSD absorbe 37 IOPS de plus à
  0,75 ms.
- Moins d'attente disque : iowait 10,7 → 1,7 %, PSI io « some » 20,7 → 5,1 %, load1 5,6 → 1,9.
  Les lectures HDD profitent de la contention réduite (42 → 28 ms) sans être accélérées par le SSD.
- Après le redémarrage, la reprise des Apps sature de nouveau les HDD (PSI io 32 %, 1 000 IOPS en
  p95) : la latence de lecture revient à 43 ms (ARC froid), mais l'écriture reste à 4,4 ms contre
  13,2 ms avant le SSD.
- Temps de réponse des services : la médiane Gatus (≈ 0,9 ms) ne dépend pas du disque. La sonde la
  plus lente passe de 34,6 à 17,0 ms ; la baisse des échecs (5,4 → 0,5) mêle le SSD et les
  correctifs de la passe du 11/11 (Pyroscope, Redis, Pi-hole), elle ne lui est pas imputable seule.

### Démarrage des conteneurs

Pas de cAdvisor dans Prometheus : la mesure passe par le premier résultat Gatus OK de chaque
service après les deux redémarrages connus (05/11 23:58 UTC, avant le SSD ; 12/11 19:43 UTC, après).

| Indicateur (minutes après le boot) | 05/11 | 12/11 |
| --- | --- | --- |
| Premier échantillon Prometheus/Gatus | 72,5 | 72,5 |
| 50 sondes Gatus OK | 89,5 | 90,5 |
| 55 sondes Gatus OK | 99,5 | 100,5 |
| p90 du premier OK (52 sondes communes) | 97,0 | 90,2 |
| Dernier service commun OK | 101,5 | 129,0 (ntopng) |

- Aucun gain mesurable : le démarrage est dicté par les vagues de reprise. Le 12/11, les conteneurs
  démarrent de +14 min (19:57) à +3 h 14 (22:57) ; Prometheus et Gatus ne sont pas en tête.
- FastAPI Sample : 14 min de démarrage le 11/11 (18:27-18:42, PSI io 58 %) ; 10 min le 12/11
  (conteneur à 22:57:05, `healthy` à 23:07, étapes de démarrage espacées de 1 à 3 min).
- Limites : mesure censurée par le démarrage de Gatus lui-même (+72,5 min) ; facteurs mêlés
  (Cilium le 11/11, correctifs de la passe du 11/11, reprise par vagues).

## 2. Gatus et Prometheus

### Gatus (60 sondes déployées, 13/11 00:34 UTC)

| Sonde en échec | Cause | Suite |
| --- | --- | --- |
| Uptime Kuma (`tcp://172.17.0.24:31050`) | Custom App `uptimekuma` codée le 12/11 (`5b506cf8`, `f12cf67f`), jamais déployée | Blocage 2 |

Échecs transitoires vus pendant l'audit, revenus seuls : FastAPI Sample (redéploiement de 22:57,
`healthy` à 23:07), DefectDojo (`DEPLOYING` après le redémarrage, `RUNNING` à 23:14), Sentry et
Sentry Edge (redéploiement de 23:13-23:15). Les 5 sondes du briefing du 11/11 (OpenHands, DDNS
Updater, Dozzle, Dockhand, Draw.io) ne sont plus générées : leurs entités Backstage ne sont pas
`active`, le générateur les filtre.

### Prometheus (40 cibles, 14 `down`)

`NablaExporterTargetDown` ne se déclenche plus : les exporters non déployés portent
`operational_state: planned`. Seule alerte active : `PiHoleAdsBlockedTooLow`.

| Job | Cible | Erreur | Dernier `up` (15 j) | Cause |
| --- | --- | --- | --- | --- |
| `keycloak` | 172.17.0.24:30239 | connection refused | 05/11 23:10 | **Keycloak ne tourne nulle part** (blocage 1) |
| `netbox`, `dependency_track` | :31082, :31083 | connection refused | jamais | Apps non déployées (roadmap P0) ; label `planned` ajouté |
| `postgres_exporter`, `opensearch`, `opensearch-security`, `haproxy` | :9187, :9114, :9115, :9101 | connection refused | jamais | Exporters codés non déployés (`planned`) |
| `exportarr_*` (5), `qbittorrent`, `jellyfin` | noms Docker / :30013 | no such host / refused | jamais | Pile média non déployée (`planned`) |
| `fastapi_sample` | :8091 | deadline exceeded | 12/11 23:10 | Transitoire (redéploiement de 22:57) |

`litellm_hermes` (signalé par le briefing du 11/11) est `up`.

## 3. Sondes FastAPI Sample

- Instance TrueNAS : **1.32.1**, construite depuis `master` amont `2f1bffc9` par le cron de
  22:00 UTC (`update-fastapi-sample.sh`, `healthy` 4/4 à 22:04). Elle est à jour :
  `update-fastapi-sample.sh` n'a pas été relancé. FastAPI Cloud : 1.32.1, `/healthz` `degraded`
  (un composant), ce qui bloque les mises à jour automatiques du cron.
- Les sondes tournent : `HOMELAB_INTERNAL_PROBES_ENABLED=true`, 88 cibles internes (TCP) tirées de
  `catalog/homelab-services.json` sur `master` (GitHub), 12 par passage, cycle complet ≈ 810 s.
  Les sondes publiques dépassent le budget de 4 s (9/12 coupées par la deadline).
- Problème corrigé : le gitlink `apps/fastapi-sample` pointait `de5607b1` (10/11). Chaque
  `git submodule update` du checkout TrueNAS (12/11 22:52 UTC) ramène le sous-module en arrière ;
  le cron voit alors une « nouvelle » version et reconstruit puis redéploie Sample pour rien
  (10 à 14 min d'indisponibilité sous charge). Gitlink passé à `2f1bffc9`.

## 4. Trous de couverture comblés (cette PR)

| Couverture | Changement |
| --- | --- |
| Sondes Sample ajoutées (11) | autoxpose, crowdsec, langflow, obsidian, open-terminal, openrag, opensearch, pyroscope, redis, squid, wazuh |
| Sondes Sample corrigées | ntopng `172.17.0.57:4000` (le LiteLLM du poste) → `172.17.0.24:31080` ; clamav `3310` (non publié) → `30005` |
| Schéma Sample | `internalSecure` faux sur 8 ports servis en HTTP clair : clickhouse, freshrss, hello-int, langfuse, litellm, litellm-albandrieu, openwebui, searxng |
| Priorités Sample | Redis (4) et Pyroscope (11) classés selon l'ordre d'amorçage de fastapi-sample |
| Gatus actif | InfluxDB (`http://influxdb:8086/health`), MongoDB (`tcp://mongo:27017`), via le réseau `intranet` |
| Gatus et Backstage | CrowdSec (`/health`), DSOMM (`/`), n8n (`/healthz`), Akvorado Console (`/api/v0/console/healthcheck`) : leurs Apps tournent, leurs entités étaient `planned` depuis la bascule Backstage v2 du 21/10. Entités passées à `active` (décision opérateur du 13/11) avec un profil BIA `provisional` copié de Grafana (criticité faible, MTPD 7 j, RTO 3 j, à revoir) ; inlet, outlet et console héritent de `akvorado-orchestrator`. Effet de bord : tuiles Homarr pour CrowdSec, DSOMM, n8n et la console Akvorado |
| Prometheus | `operational_state: planned` sur `keycloak`, `netbox`, `dependency_track` (miroir de Backstage) ; ces jobs entrent dans `NablaExporterTargetDown`, qui alertera dès leur passage à `active` (aucune alerte ne couvrait Keycloak) |

## 5. Trous restants et blocages

### Blocage 1 — Keycloak arrêté depuis le 05/11

App TrueNAS supprimée, manifestes `kubernetes/keycloak` non appliqués (NodePorts 30238/30239
fermés sur les trois nœuds Talos, `https://keycloak.albandrieu.com` en 502). Pas de kubeconfig
Talos sur le poste. Suite (roadmap P0) : épingler les digests, `kubectl apply -k kubernetes/keycloak`,
repointer le job Prometheus et la sonde Sample (`172.17.0.24:30238`) vers le nœud Talos, puis
retirer `operational_state: planned`.

### Blocage 2 — Uptime Kuma non déployé

Accord opérateur requis : dataset `cpool/uptimekuma` (568:568), Custom App `uptimekuma` avec
`include: /mnt/cpool/compose/nabla-compose/apps/uptimekuma/compose.yml`, compte admin, puis
`bootstrap-autokuma-token.sh` et `deploy-autokuma.sh` ([README](../../apps/uptimekuma/README.md)).

### Blocage 3 — Homarr `CRASHED`

`homarr-sync` sort en erreur (`GET /api/boards/<id>/items` → 404). Le correctif `2108f065`
(« stop crashing on boards Homarr v2.6 cannot list ») est poussé sur
`fix/roadmap-questions-20261112` par une autre session, pas encore fusionné.

### Gatus impossible sans entité Backstage

Les contrats `test_catalog_v2_identity_map` et `test_observability_contract` refusent une sonde
dont le service n'a pas d'entité, et la règle du dépôt interdit d'en créer une par déduction. Cibles
vérifiées le 13/11, à déclarer avec l'entité lors de la [migration catalogue → Compose](2026-11-06-catalog-apps-to-compose.md) :

| Service | Cible Gatus vérifiée |
| --- | --- |
| adguardhome | `http://172.17.0.24:30004/login.html` (200) |
| clamav | `tcp://172.17.0.24:30005` |
| freshrss | `http://172.17.0.24:30108/i/` (200) |
| glances | `http://172.17.0.24:30015/api/4/status` (200) |
| ittools | `http://172.17.0.24:30063/` (200) |
| karakeep | `http://172.17.0.24:30147/api/health` (200) |
| localai | `http://172.17.0.24:30286/readyz` (200) |
| open-speed-test | `tcp://172.17.0.24:30117` |
| open-terminal | `http://172.17.0.24:30377/health` (200) |
| reactive-resume | `http://172.17.0.24:30393/api/health` (200) |
| searxng | `http://172.17.0.24:30053/healthz` (200) |
| three-proxy | `tcp://172.17.0.24:30388` |
| zabbix | `http://172.17.0.24:30386/` (200) |

### Autres trous

- Sondes Sample sans icône web : glances, three-proxy, zabbix. `sync-homelab-icons.mjs` de
  nabla-site-alban refuse une icône absente de `public/assets/selfh-icons` : l'y ajouter d'abord.
- Sans port réseau joignable par Sample : autokuma, cloudflared, suricata, bitcoind (aucun port
  publié), openclaw-gateway (127.0.0.1), openclaw-devbox, docker-socket-proxy (réseau dédié),
  influxdb (127.0.0.1), mongo et kafka (réseau `intranet` seul).
- Plumber : l'App TrueNAS tourne (31070/31071) mais son entité reste `planned` (roadmap P0,
  déploiement contrôlé) ; l'id Sample `plumber` vise l'instance du poste.
- Profils BIA `provisional` de crowdsec, dsomm, n8n et akvorado : valeurs reprises de Grafana,
  à valider par l'opérateur.
- Métriques Prometheus : aucune App en marche sans métriques n'expose de `/metrics` exploitable
  sans authentification (`/metrics` de Langflow et Open WebUI renvoient du HTML ; MinIO exige
  `MINIO_PROMETHEUS_AUTH_TYPE=public` ; Nexus et Home Assistant un jeton). Il faut un exporter ou
  une décision d'exposition par service. Les sondes Gatus publient déjà `gatus_results_*` dans
  Prometheus pour la disponibilité.
- Pyroscope : `/ready` oscille (503 « Segment Writer not ready » puis 200 dix secondes plus tard).
  La sonde Gatus teste `/`, pas `/ready`. À surveiller.
- Services du poste (`*-albandrieu`, 172.17.0.57) fermés : hors périmètre TrueNAS.

## 6. Méthode et requêtes

- Latence par opération : `rate(node_disk_write_time_seconds_total[5m]) / rate(node_disk_writes_completed_total[5m])`,
  agrégée par groupe de disques ; moyenne et p95 par `avg_over_time` / `quantile_over_time` sur
  une sous-requête `[24h:1m]`.
- Pression : `rate(node_pressure_io_waiting_seconds_total[5m])` (some) et `..._stalled_...` (full).
- Démarrage : premier `gatus_results_endpoint_success == 1` par `nabla_service_id` après
  `node_boot_time_seconds`.
- Réponse interne : `curl -k` sans suivre les redirections vers `internalHost:internalPort`, puis
  en les suivant, plus un `connect` TCP. HTTP clair retenté quand HTTPS échoue en TLS.

## Annexe — matrice de couverture

Une ligne par service (Apps TrueNAS, catalogue Sample, sondes Gatus, jobs Prometheus), au
13/11 00:34 UTC. **Gatus** : `oui` = déployée et OK, `ajoutée` = dans cette PR,
`déclarée, inactive` = filtrée tant que l'entité est `planned`. **Sonde Sample** : cible du
catalogue après cette PR. **Réponse interne** : sans tunnel Cloudflare ; « attendu » = bon
fonctionnement (login, redirection, API sans page racine, protocole non HTTP), « arrêt volontaire »
= App `STOPPED`, « non déployée » = App absente de TrueNAS.

| Service | App TrueNAS | Gatus | Prometheus | Sonde Sample (IP:port) | Réponse interne |
| --- | --- | --- | --- | --- | --- |
| 2fauth | RUNNING | oui | non | oui `172.17.0.24:30081` | 200 |
| adguardhome | RUNNING | non | non | oui `172.17.0.24:30004` | 302 → login : attendu (authentification) |
| affine | absente | non | non | oui `172.17.0.24:30169` | fermé : App absente (non déployée) |
| akvorado-console | RUNNING | ajoutée | akvorado_inlet up, akvorado_outlet up | oui `172.17.0.24:31056` | 200 |
| alloy | — (autre App) | oui | alloy up | non | — |
| anythingllm | absente | non | non | oui `172.17.0.24:30318` | fermé : App absente (non déployée) |
| anythingllm-albandrieu | absente | non | non | oui `172.17.0.57:3007` | fermé : hors TrueNAS (poste), service arrêté |
| autokuma | RUNNING | non | non | non | — |
| autoxpose | RUNNING | oui | non | ajoutée `172.17.0.24:4949` | 200 |
| bazarr | absente | non | exportarr_bazarr down (planned) | non | — |
| bichon | RUNNING | oui | non | oui `172.17.0.24:15630` | 200 |
| bitcoind | RUNNING | non | non | non | — |
| clamav | RUNNING | non | non | corrigée `172.17.0.24:30005` (était `172.17.0.24:3310`) | TCP ouvert, protocole non HTTP : attendu |
| cleanuparr | STOPPED | non | non | non | — |
| clickhouse | RUNNING | oui | clickhouse up | oui `172.17.0.24:8123` | 200 |
| cloudflared | RUNNING | non | non | non | — |
| code-server | RUNNING | oui | non | oui `172.17.0.24:8443` | 302 → login : attendu (authentification) |
| convertx | STOPPED | non | non | oui `172.17.0.24:30154` | fermé : App STOPPED (arrêt volontaire) |
| crowdsec | RUNNING | ajoutée | crowdsec up | ajoutée `172.17.0.24:8084` | 404 : attendu (API, pas de page racine) |
| cyberbro | RUNNING | oui | non | oui `172.17.0.24:5100` | 200 |
| ddns-updater | STOPPED | déclarée, inactive (entité `planned`) | non | oui `172.17.0.24:30007` | fermé : App STOPPED (arrêt volontaire) |
| defectdojo | RUNNING | oui | non | oui `172.17.0.24:31085` | 302 → login : attendu (authentification) |
| dependency-track | absente | déclarée, inactive (entité `planned`) | dependency_track down | oui `172.17.0.24:31084` | fermé : App absente (non déployée) |
| dependency-track-api | absente | déclarée, inactive (entité `planned`) | non | non | — |
| docker-socket-proxy | RUNNING | oui | non | non | — |
| dockhand | STOPPED | déclarée, inactive (entité `planned`) | non | oui `172.17.0.24:3050` | fermé : App STOPPED (arrêt volontaire) |
| docling | RUNNING | oui | docling up | oui `172.17.0.24:5001` | 404 : attendu (API, pas de page racine) |
| doco-cd | absente | déclarée, inactive (entité `planned`) | non | non | — |
| domain-watchdog | STOPPED | non | non | oui `172.17.0.24:30317` | fermé : App STOPPED (arrêt volontaire) |
| dozzle | STOPPED | déclarée, inactive (entité `planned`) | non | oui `172.17.0.24:8888` | fermé : App STOPPED (arrêt volontaire) |
| drawio | STOPPED | déclarée, inactive (entité `planned`) | non | oui `172.17.0.24:9080` | fermé : App STOPPED (arrêt volontaire) |
| dsomm | RUNNING | ajoutée | non | oui `172.17.0.24:31088` | 200 |
| elasticsearch | STOPPED | non | non | non | — |
| emby | STOPPED | non | non | non | — |
| fastapi-sample | RUNNING | oui | fastapi_sample up | oui `172.17.0.24:8091` | 200 |
| freshrss | RUNNING | non | non | oui `172.17.0.24:30108` | 302 → /i/ (200) : attendu (redirection applicative) |
| garage | RUNNING | oui | garage up | oui `172.17.0.24:3900` | 403 : attendu (authentification requise) |
| garage-admin | absente | non | non | oui `172.17.0.24:3903` | 400 : attendu (API, pas de page racine) |
| garage-webui | absente | non | non | oui `172.17.0.24:3909` | 200 |
| gatus | RUNNING | oui | gatus up | oui `172.17.0.24:8085` | 200 |
| glances | RUNNING | non | non | non | — |
| grafana | RUNNING | oui | grafana up | oui `172.17.0.24:30037` | 302 → login : attendu (authentification) |
| graylog | STOPPED | déclarée, inactive (entité `planned`) | non | oui `172.17.0.24:30319` | fermé : App STOPPED (arrêt volontaire) |
| haproxy | absente | non | haproxy down (planned) | non | — |
| haproxy-exporter | absente | déclarée, inactive (entité `planned`) | non | non | — |
| heimdall | STOPPED | non | non | oui `172.17.0.24:30120` | fermé : App STOPPED (arrêt volontaire) |
| hello-int | RUNNING | oui | non | oui `172.17.0.24:8099` | 200 |
| hermes | STOPPED | non | non | non | — |
| homarr | CRASHED | oui | non | oui `172.17.0.24:30100` | 200 |
| home | absente | non | non | oui `172.17.0.1:10443` | 200 |
| homeassistant | RUNNING | oui | non | oui (sans hôte:port) | — |
| immich | STOPPED | non | non | non | — |
| influxdb | RUNNING | ajoutée | influxdb up | non | — |
| ittools | RUNNING | non | non | oui `172.17.0.24:30063` | 200 |
| jellyfin | absente | non | jellyfin down (planned) | non | — |
| joplin | absente | déclarée, inactive (entité `planned`) | non | oui `172.17.0.24:22300` | fermé : App absente (non déployée) |
| kafka | RUNNING | oui | kafka_exporter up | non | — |
| karakeep | RUNNING | non | non | oui `172.17.0.24:30147` | 307 → login : attendu (authentification) |
| kasm-workspaces | STOPPED | non | non | non | — |
| keycloak | absente | non | keycloak down | oui `172.17.0.24:30238` | fermé : App absente (non déployée) |
| langflow | RUNNING | oui | non | ajoutée `172.17.0.24:7860` | 200 |
| langfuse | RUNNING | oui | non | oui `172.17.0.24:3000` | 200 |
| languagetool | RUNNING | oui | non | oui `172.17.0.24:8010` | 400 : attendu (API, pas de page racine) |
| lidarr | STOPPED | non | exportarr_lidarr down (planned) | oui `172.17.0.24:30071` | fermé : App STOPPED (arrêt volontaire) |
| litellm | RUNNING | oui | litellm_hermes up | oui `172.17.0.24:4000` | 200 |
| litellm-albandrieu | absente | non | non | oui `172.17.0.57:4000` | 200 |
| localai | RUNNING | non | non | oui `172.17.0.24:30286` | 301 → /app (200) : attendu (redirection applicative) |
| localai-gpu | absente | non | non | oui `172.17.0.24:30320` | fermé : App absente (non déployée) |
| loki | — (autre App) | oui | loki up | non | — |
| memos | STOPPED | non | non | non | — |
| mimir | — (autre App) | oui | mimir up | non | — |
| minio | RUNNING | oui | non | oui `172.17.0.24:9091` | 200 |
| mongo | RUNNING | ajoutée | non | non | — |
| n8n | RUNNING | ajoutée | n8n up | oui `172.17.0.24:30109` | 200 |
| neo4j-security | absente | déclarée, inactive (entité `planned`) | non | non | — |
| netalertx | absente | non | non | oui `172.17.0.24:30321` | fermé : App absente (non déployée) |
| netbootxyz | absente | non | non | oui `172.17.0.24:31010` | fermé : App absente (non déployée) |
| netbox | absente | déclarée, inactive (entité `planned`) | netbox down | oui `172.17.0.24:31082` | fermé : App absente (non déployée) |
| netdata | STOPPED | non | non | non | — |
| nexus | RUNNING | oui | non | oui `172.17.0.24:8081` | 200 |
| nginx-proxy-manager | absente | déclarée, inactive (entité `planned`) | non | non | — |
| npmplus | absente | déclarée, inactive (entité `planned`) | non | non | — |
| ntopng | RUNNING | oui | non | corrigée `172.17.0.24:31080` (était `172.17.0.57:4000`) | 302 → login : attendu (authentification) |
| obsidian | RUNNING | oui | non | ajoutée `172.17.0.24:3002` | 200 |
| ollama | RUNNING | oui | non | oui `172.17.0.24:30068` | 200 |
| ollama-gpu | absente | non | non | oui `172.17.0.24:30323` | fermé : App absente (non déployée) |
| open-speed-test | RUNNING | non | non | oui `172.17.0.24:30117` | 200 |
| open-terminal | RUNNING | non | non | ajoutée `172.17.0.24:30377` | 404 : attendu (API, pas de page racine) |
| openarchiver | absente | non | non | oui `172.17.0.24:30288` | fermé : App absente (non déployée) |
| openclaw | absente | non | non | oui `172.17.0.24:30325` | fermé : App absente (non déployée) |
| openclaw-devbox | RUNNING | non | non | non | — |
| openclaw-gateway | RUNNING | non | non | non | — |
| openhands | STOPPED | déclarée, inactive (entité `planned`) | non | oui `172.17.0.24:3010` | fermé : App STOPPED (arrêt volontaire) |
| openrag | RUNNING | oui | non | ajoutée `172.17.0.24:31060` | 200 |
| opensearch | RUNNING | oui | opensearch down (planned) | ajoutée `172.17.0.24:9200` | 401 : attendu (authentification requise) |
| opensearch-exporter | absente | déclarée, inactive (entité `planned`) | non | non | — |
| opensearch-security | absente | non | opensearch-security down (planned) | non | — |
| opensearch-security-exporter | absente | déclarée, inactive (entité `planned`) | non | non | — |
| openwebui | RUNNING | oui | non | oui `172.17.0.24:31028` | 200 |
| paperless-ai | STOPPED | non | non | oui `172.17.0.24:30226` | fermé : App STOPPED (arrêt volontaire) |
| paperless-ngx | STOPPED | non | non | oui `172.17.0.24:30070` | fermé : App STOPPED (arrêt volontaire) |
| pfsense | hôte | oui | pfsense_exporter up | oui `172.17.0.1:10443` | 200 |
| pgadmin | STOPPED | non | non | oui `172.17.0.24:30056` | fermé : App STOPPED (arrêt volontaire) |
| pihole | RUNNING | oui | pihole_exporter up | oui `172.17.0.24:20720` | 403 : attendu (authentification requise) |
| plumber | RUNNING | déclarée, inactive (entité `planned`) | non | oui `172.17.0.57:3001` | fermé : hors TrueNAS (poste), service arrêté |
| plumber-api | absente | déclarée, inactive (entité `planned`) | non | non | — |
| plumber-api-albandrieu | absente | non | non | oui `172.17.0.57:3003` | fermé : hors TrueNAS (poste), service arrêté |
| portainer | absente | non | non | oui `172.17.0.24:31015` | fermé : App absente (non déployée) |
| portracker | RUNNING | oui | non | oui `172.17.0.24:30233` | 200 |
| portracker-albandrieu | absente | non | non | oui `172.17.0.57:4999` | fermé : hors TrueNAS (poste), service arrêté |
| postgres-exporter | absente | déclarée, inactive (entité `planned`) | non | non | — |
| postgresql | RUNNING | oui | postgres_exporter down (planned) | oui `172.17.0.24:5432` | TCP ouvert, protocole non HTTP : attendu |
| prometheus | RUNNING | oui | alertmanager up, prometheus up | oui `172.17.0.24:9090` | 302 → /query (200) : attendu (redirection applicative) |
| prowlarr | absente | non | exportarr_prowlarr down (planned) | oui `172.17.0.24:30050` | fermé : App absente (non déployée) |
| pyroscope | RUNNING | oui | pyroscope up | ajoutée `172.17.0.24:4040` | 200 |
| qbittorrent | absente | non | qbittorrent down (planned) | non | — |
| radarr | absente | non | exportarr_radarr down (planned) | oui `172.17.0.24:30025` | fermé : App absente (non déployée) |
| reactive-albandrieu | absente | non | non | oui `172.17.0.57:3008` | fermé : hors TrueNAS (poste), service arrêté |
| reactive-resume | RUNNING | non | non | oui `172.17.0.24:30393` | 200 |
| redis | RUNNING | oui | redis_exporter up | ajoutée `172.17.0.24:30059` | TCP ouvert, protocole non HTTP : attendu |
| sabnzbd | absente | non | non | oui `172.17.0.24:30055` | fermé : App absente (non déployée) |
| scanopy | RUNNING | oui | non | oui `172.17.0.24:60072` | 200 |
| scrutiny | RUNNING | oui | non | oui `172.17.0.24:31054` | 302 → /web (200) : attendu (redirection applicative) |
| scrutiny-collector-albandrieu | absente | non | non | oui (sans hôte:port) | — |
| searxng | RUNNING | non | non | oui `172.17.0.24:30053` | 200 |
| sentry | RUNNING | oui | non | oui `172.17.0.24:9005` | 302 → login : attendu (authentification) |
| sonarqube | absente | déclarée, inactive (entité `planned`) | non | non | — |
| sonarr | absente | non | exportarr_sonarr down (planned) | oui `172.17.0.24:30113` | fermé : App absente (non déployée) |
| speedtest | absente | non | non | oui `172.17.0.24:30221` | fermé : App absente (non déployée) |
| speedtest-tracker | STOPPED | non | non | non | — |
| squid | RUNNING | oui | non | ajoutée `172.17.0.24:3128` | 400 : attendu (API, pas de page racine) |
| stirling | absente | non | non | oui `172.17.0.24:30124` | fermé : App absente (non déployée) |
| stirling-albandrieu | absente | non | non | oui `172.17.0.57:8085` | fermé : hors TrueNAS (poste), service arrêté |
| stirling-pdf | STOPPED | non | non | non | — |
| suricata | RUNNING | non | non | non | — |
| sybase-exporter | absente | déclarée, inactive (entité `planned`) | non | non | — |
| tailscale | STOPPED | non | non | non | — |
| tempo | — (autre App) | oui | tempo up | non | — |
| three-proxy | RUNNING | non | non | non | — |
| tracearr | STOPPED | non | non | non | — |
| traefik | RUNNING | oui | traefik up | oui `172.17.0.24:443` | 404 : attendu (API, pas de page racine) |
| transmission | absente | non | non | oui `172.17.0.24:30096` | fermé : App absente (non déployée) |
| truenas | hôte | oui | truenas_node up | oui `172.17.0.24:7000` | 302 → /ui/ (200) : attendu (redirection applicative) |
| uptimekuma | absente | **échec** | non | oui `172.17.0.24:31050` | fermé : App absente (non déployée) |
| vaultwarden | RUNNING | oui | non | oui `172.17.0.24:30032` | 200 |
| wazuh | RUNNING | oui | non | ajoutée `172.17.0.24:1514` | TCP ouvert, protocole non HTTP : attendu |
| wizarr | STOPPED | non | non | non | — |
| workstation | hôte | non | workstation_node up | non | — |
| zabbix | RUNNING | non | non | non | — |
