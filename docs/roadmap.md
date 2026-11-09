# Services Homelab — roadmap active

> Mise à jour : **9 novembre 2026**. Source d'autorité des **travaux restant à réaliser**. Une PR fusionnée ou un script versionné ne constitue pas une réception runtime. Les procédures courantes sont dans les runbooks spécialisés ; les problèmes passés utiles aux diagnostics sont dans [les leçons de migration](incidents/2026-11-06-migrations-retour-experience.md) et dans l'[archive immuable au 24/10](archive/roadmap-through-2026-10-24.md). Ne pas réexécuter d'anciennes commandes d'incident.

## Règles de suivi

- `CODED` : code présent dans Git ; `TESTED` : contrat local exécuté sur un SHA identifié ; `ACCEPTED (runtime)` : mesure fonctionnelle datée du service cible ; `NOT_VERIFIED` : preuve absente. Ne jamais déduire le dernier état du premier.
- Le catalogue `x-nabla` est l'autorité des identités ; `entityRef` et `catalogRevision` assurent le rapprochement entre Compose, FastAPI et sites. Les chemins `/mnt/cpool` et les secrets privés restent hors du dépôt.
- L'observation Cloudflare `DENIED`/`challenge`, un diagnostic non exécuté, ou une absence de télémétrie ne deviennent pas des services DOWN.
- Avant chaque mutation : sauvegarde, plan en lecture seule, accord opérateur, preuve de retour arrière. La quality gate locale s'exécute sans CI payante.

## Suivi consolidé — état du code et réception (8 novembre 2026)

| Chantier | État du code | Preuve runtime et prochain contrôle |
| --- | --- | --- |
| Catalogue / moniteurs (#326, #327) | **CODED** : appId natifs corrigés, alarmes des Apps `planned` / `disabled` exclues des alertes d'indisponibilité ; Gatus et Prometheus restent distincts | **NOT_VERIFIED** après déploiement : vérifier `app.query`, Gatus frais et `/api/homelab/status` |
| OpenClaw TrueNAS (#314, #323) | **CODED**, anciens scripts Workstation mutateurs retirés de Compose (#330) | **ACCEPTED** le 03–05/11 pour Gateway, Telegram/WhatsApp, LiteLLM, heartbeat/digest ; revérifier absence de doublons et rollback lors de tout changement |
| Vaultwarden / secrets | **CODED** : audit sans valeurs et procédure de clôture ; référence historique de 43 Apps / 117 champs déclarés | **NOT_VERIFIED globalement** : item → fichier canonique `0600` → conteneur ; `homarr-sync` exige `HOMARR_API_KEY` et non l'ancien jeton |
| PostgreSQL logique (#330) | **CODED** : job `postgres-backup`, contrôle `pg_restore --list`, SHA-256, 14 j, rôle `pgbackup` et cron créé **désactivé** | **NOT_VERIFIED** : sauvegarde manuelle + restauration sur cible séparée, avant toute activation du cron |
| Keycloak et Home Assistant (#330) | **CODED** : realm `nabla`, refus `master` au Tunnel ; HA bridge et bootstrap DB commun | **NOT_VERIFIED** : démarrage contrôlé, import realm avec autorisation, migration recorder et tests négatifs Cloudflare |
| Apps en attente (#330) | **CODED** : `rollout-pending-apps.sh` `--plan/--check/--apply`, scripts PostgreSQL partagés, métriques NetBox/Dependency-Track déclarées | **NOT_VERIFIED** : préflight sur TrueNAS puis déploiement **une App à la fois** avec accord, preuve de rollback |
| DefectDojo / sécurité | **CODED** : import et normalisation des rapports outillés | **NOT_VERIFIED** : réception API/Celery et déduplication sans données sensibles |

Les champs et nombres ci-dessus sont des **états déclaratifs datés**, pas un inventaire de santé temps réel. Les anciens comptes d'alertes ne sont pas des pannes actuelles. Un service écarté du rendu Gatus faute de déploiement n'est pas `PASS` ; il est `NOT_RUN` / `planned`.
| Préparation production (toutes Apps) | **CODED** : matrice générée [`production-readiness.md`](production-readiness.md), `app-ops.sh` (status/storage/secrets/deploy/restart/diagnose/monitor/backup, mutations sous `--apply` + `NABLA_RUNTIME_CHANGE_APPROVED=yes`), [runbook](runbooks/production-app-operations.md) ; `postgres-backup` couvre aussi `defectdojo`, `langfuse`, `n8n`, `sonarqube` ; datasets `ddns-updater`, `dockhand`, `npm` classés `app-state` | **NOT_VERIFIED** au runtime (pas d'accès SSH). Écarts restants à traiter App par App : `NO_AVAILABILITY_PROBE` (30), `NO_DEPLOY_PATH` (21), `SECRETS_LEGACY_PATH` (17), `SERVICE_WITHOUT_HEALTHCHECK` (48 hors stack média) ; décision requise pour la sauvegarde logique de `sentry` (nodestore volumineux) et le nom de base de `sample` |

## P0 — Réception du catalogue et des sondes (PR #326)

[PR Compose #326](https://github.com/AlbanAndrieu/nabla-compose/pull/326) : les `appId` de `graylog`, `bitcoind`, `elasticsearch` (`elastic-search`) et `hermes` (`hermes-agent`) sont **corrigés dans le code**, en conservant `containerService`. Cela supprime le double comptage `declared_only` + `observed_only` des Apps arrêtées, mais **ne les démarre pas**.

| Priorité | Travail restant | Critère de clôture |
| --- | --- | --- |
| P0 | Valider les changements de la PR #330 au HEAD rebasé, sans confondre génération de catalogue et santé effective | `generate-service-topology.py --check`, `generate-service-consumers.py --check`, `generate-catalog-v2-artifacts.py --check` et quality gate ciblée |
| P0 | Diagnostiquer `graylog`, `homarr`, ainsi que les Apps arrêtées `bitcoind` / `elastic-search` / `hermes-agent` ; respecter les arrêts volontaires | État TrueNAS et preuves HTTP/health concordants, sans forcer un démarrage |
| P0 | Déployer sous contrôle `dependency-track`, `netbox`, `plumber`, `scanopy`, `joplin`, `ntopng` sur TrueNAS, si prérequis validés | `app.query` + `/api/homelab/status` = `in_sync` et sondes fraîches |
| P1 | Trancher l'exposition externe de Joplin, actuellement `external=true` mais DNS uniquement privé | Contrat et politique Access/Traefik alignés sans ouverture non autorisée |
| P1 | Garder AIStor et WordPress **retirés du catalogue** ; vérifier l'absence de consommateur et de snapshot avant toute éventuelle suppression de `cpool/aistor` | Plan de retrait, sauvegarde, vérification des tâches ZFS et approbation séparée ; aucune suppression automatique |
| P1 | Migration du nom canonique `homeassistant`/`openwebui` via procédure TrueNAS, pas par simple changement d'`appId` | Sauvegarde et rollback attestés, middleware + URL + Access + données validés |

Le [runbook des remédiations encore ouvertes](runbooks/2026-11-04-probe-remediation.md) contient **uniquement** les gestes non réceptionnés et le diagnostic des cas atypiques. Les identités canonisées, le mode pfSense `transport_only` et la décision de ne pas exempter Keycloak/LiteLLM au WAF sont des décisions **déjà intégrées**, pas des nouvelles tâches.

## P0 — Keycloak, Home Assistant, PostgreSQL et Apps en attente (#330)

| Ordre | Étape préparée dans Git | Gate indispensable avant mutation | Terminé quand |
| --- | --- | --- | --- |
| 1 | `bootstrap-app-postgres.sh --describe` puis `--check` ; `rollout-pending-apps.sh --plan` | Exécuter `sudo bash scripts/truenas/rollout-pending-apps.sh --check` sur TrueNAS ; aucun diagnostic refusé ne vaut validation | Parité des fichiers privés et prérequis Docker/middleware, sans mutation |
| 2 | Keycloak : realm applicatif `nabla`, import via `apply-keycloak-config.sh` | Realm `master` jamais piloté, règles Tunnel ordonnées ; migration sauvegardée, autorisation explicite avant `--apply` | OIDC `nabla` sain en LAN ; `/realms/master/` refusé depuis Internet |
| 3 | Home Assistant : `intranet` + `traefik`, base `homeassistant` sur PostgreSQL partagé | Sauvegarder et restaurer l'ancien recorder avant bascule, confirmer réseau bridge et limitations multicast IoT | Historique HA accessible, DB/recorder sans erreur et `app.query` concordant |
| 4 | Backup PostgreSQL : `apps/postgres-backup`, rôle lecture seule, politique ZFS | Première sauvegarde manuelle vérifiée **et restauration indépendante** ; cron TrueNAS désactivé jusqu'à approbation | `pg_restore --list`, checksum, test de récupération, suivi `last-success` |
| 5 | Apps : NetBox → Dependency-Track → Plumber → Scanopy → Joplin → ntopng | Un seul `--apply <app>` à la fois ; ordre révisé par opérateur, licence/interface approuvées pour ntopng ; aucune preuve de métriques tant qu'elles ne sont pas observées | `RUNNING` confirmé, Gatus frais ; `up{job="netbox"}=1` / `up{job="dependency_track"}=1` quand déployées |
| 6 | Retirer Databasus après réconciliation des sauvegardes | Relever et préserver tout backup restant ; `app.stop` ne vaut pas autorisation de supprimer | Sauvegarde de substitution restaurable et retrait documenté |

L'outillage **ne déploie pas** ces Apps à l'occasion du rebase. Le contrat `--check` implique une exécution en lecture seule ; `--apply` doit conserver la validation des paramètres et l'accord `NABLA_RUNTIME_CHANGE_APPROVED=yes`. La récupération du code de retour des sous-processus doit rester **fail-closed** et ne jamais afficher les logs privés. Les scripts de bootstrap/refactoring remplacent les duplications historiques sans supprimer les points d'entrée documentés.

Références : [runbook de réception](runbooks/2026-11-04-probe-remediation.md), [migration des Apps du catalogue](runbooks/2026-11-06-catalog-apps-to-compose.md), [audit des secrets](runbooks/vaultwarden-migration-closure-20261106.md) et [synergies d'intégration](integration-synergies-20261107.md). Les synergies OIDC/SBOM/IPAM/SOAR sont **P2 proposées**, jamais des dépendances en production tant qu'elles ne sont pas vérifiées.

## P0 — Cloudflare, secrets et frontières d'accès

1. **Cloudflare Tunnel / Access** : valider le plan OpenTofu de retrait des routes `external=false`, le renommage public FastAPI Sample, et la précédence du refus `/realms/master` avant les routes Keycloak publiques ; n'appliquer qu'avec approbation et comparaison exacte des effets. Aucune exception WAF/Bot pour Keycloak/LiteLLM ; l'observateur TrueNAS fournit la preuve LAN. [Module IaC](../terraform/cloudflare/README.md). Inclut les sept noms média publics observés le 7/11 (`radarr`, `sonarr`, `prowlarr`, `lidarr`, `transmission`, `sabnzbd`, `emby` : `403` Cloudflare sans Access, [§2.3](arr-media-library-roadmap.md)).
2. **Service Auth observateur** : aligner les politiques des applications concernées sans `Bypass` général ; protéger le coffre web et `/admin` Vaultwarden en limitant les exceptions aux chemins clients. Recetter depuis un client externe avant retrait d'une ancienne politique.
3. **Secrets** : prouver la concordance Vaultwarden → fichier canonique 0600 → environnement conteneur, sans afficher de valeur. Une ancienne session `BW_SESSION` exposée ne doit jamais être réutilisée. [Roadmap secrets](secrets-migration-roadmap.md).
4. **OVH / FastAPI Cloud** : vérifier la nouvelle identité de lecture seule et les scopes ; `pfSense` y reste `transport_only` (contrat accepté) et la sonde Tavily `GET /usage` ne nécessite plus de migration. Au 6/11, FastAPI Cloud répond mais reste `degraded` : le contrôle `openstack_me` échoue (identifiant OVH « does not exist »).

**Clôture** : règles Access du moindre privilège et sondes de bord expurgées, sans régression du DNS ni création d'une exposition WAN.

## P0 — Accepter les services critiques

- **TrueNAS 27** : hôte passé de 26.0.0-BETA.3 à 27.0.0-RC.1 les 5–6/11 (TrueNAS 26 renommé 27 ; API REST supprimée, aucun client du dépôt ne l'utilise). Contrôles post-upgrade encore à exécuter **sur l'hôte TrueNAS via SSH** : `midclt call system.version`, `just talos-stopped-vms-check`, `just truenas-readiness-check`, `just truenas-fastapi-check`, MCP `truenas-readonly`, données TrueNAS de portracker, provision/bind d'un PVC CSI, 2FA. Conserver l'environnement de boot précédent tant qu'ils ne passent pas. [Upgrade coupling](truenas-operator-tools.md#upgrade-coupling).
- TrueNAS : prouver la disponibilité réelle (et non le seul état du conteneur), les ACL NFS, les secrets et les dépendances Postgres/ClickHouse.
- **FastAPI Sample DOWN depuis la mise à niveau 27** : `172.17.0.24:8091` refuse les connexions, cause non diagnostiquée ; il faut l'accès à l'hôte (état de l'App, `docker logs`) avant tout redéploiement. [Diagnostic TrueNAS](runbooks/fastapi-sample-truenas-diagnostics.md). FastAPI Cloud `degraded` : voir le point 4 OVH ci-dessus.
- FastAPI Sample : vérifier la parité API/UI et le mode OWNER, les cibles Prometheus, le routeur LiteLLM et la sélection du corpus OpenRAG privé ; test navigateur Chromium uniquement si disponible. [Diagnostic consolidé](runbooks/fastapi-consolidated-diagnostics-20261030.md).
- Talos / Kubernetes : valider le retained smoke `democratic-csi` NFS, les trois nœuds Ready et les politiques NetworkPolicy avant nouveaux workloads. [Préflight](kubernetes-csi-preflight.md).
- pfSense / CrowdSec : conserver la preuve que PF charge les règles, puis démontrer le rattachement WAN exact sans bloquer une IP d'administration ; ne pas prendre une ancre chargée pour une preuve de filtrage effectif.
- Authentification et monitoring : réparer les exporters sans confondre un `401` Prometheus avec un `401` OpenClaw ; Gatus/Prometheus sont des preuves indépendantes.

**Clôture** : `ACCEPTED (runtime)` sur le SHA déployé, avec date, source et un test négatif pour chaque frontière sensible ; sinon `NOT_VERIFIED`.

## P1 — Performance, stockage et restauration TrueNAS

- Mesurer mémoire/PSI/ARC, OOM, zombies, limites de conteneurs et descripteurs containerd, puis appliquer les limites mesurées à partir du pic cgroup `memory.peak` (4/11 : nexus 1,9 Gio, opensearch-security 1,8, docling 1,5, kafka 1,2, keycloak 0,9, litellm 0,7). L'arrêt de certains services par décision opérateur n'est pas une réparation définitive.
- Après le reboot de la mise à niveau 27 : vérifier avec `diagnose-performance.sh` que le thread noyau de l'ancienne JVM `wazuh-indexer` a disparu, que les zombies restants sont purgés et que l'ARC remonte ; confirmer le redéploiement `deploy-wazuh.sh` du 4/11 (non vérifié).
- Zombies : `init: true` ajouté le 4/11 sur 10 services (drawio, clickhouse, mongo, sentry-clickhouse, bichon, suricata, openwebui, kafka, minio, ollama), effectif au prochain redéploiement de chaque App ; `reactive-resume` (App catalogue) reste non versionné.
- Réconcilier le proxy Docker Socket versionné avec les consommateurs avant de retirer l'ancien réseau `intranet` ; `POST=0` doit rester la valeur par défaut. Choisir explicitement le sort de Doco-CD.
- Appliquer les tâches ZFS de rétention **après `--plan`**, vérifier par dataset les snapshots, puis tester une restauration hors du TrueNAS. Ne jamais effectuer `docker volume prune` ou un nettoyage global de snapshots.
- Prendre en compte la mémoire du `wazuh-indexer` et la politique de rétention des bases selon le dernier audit read-only. Volumes orphelins (658, dont 650 anonymes) : produire le plan [`reconcile-docker-orphan-volumes.sh`](../scripts/truenas/reconcile-docker-orphan-volumes.sh) (`just docker-orphan-volumes-plan`), puis `docker volume rm` volume par volume après revue.
- Déployer la Custom App [`bitcoind`](../apps/bitcoind/README.md) (`deploy-bitcoind.sh --apply --replace-catalog-app`) puis purger ses anciennes données ; reprendre hors charge la purge du cache de build Docker (~10 Go) ; décider la consolidation des moteurs de recherche (2 OpenSearch + indexer Wazuh).
- Vérifier les alertes Restic `workstation_restic` et configurer au moins un récepteur Alertmanager, puis une restauration hors site.

Références : [performance](../scripts/truenas/diagnose-performance.sh), [snapshots ZFS](truenas-zfs-snapshot-policy.md), [cycle de vie des Apps](truenas-app-lifecycle.md).

## P1 — Avant TrueNAS 28 : sortir de `auth.login_with_api_key`

`auth.login_with_api_key` est déprécié en 27 et supprimé en 28. TrueNAS CSI `v1.0.3` (encore en `v1.3.0`), `@profanter-dev/truenas-mcp` `1.0.6` et portracker (ancien `/websocket`) l'utilisent : les migrer vers `auth.login_ex` (`API_KEY_PLAIN` ou SCRAM), puis rejouer provision/persistance/reclaim CSI. **Clôture** : aucun client sur l'ancienne méthode avant toute mise à niveau en 28. [Upgrade coupling](truenas-operator-tools.md#upgrade-coupling).

## P1 — Séparation OpenClaw / Workstation / YubiKey

- `nabla-openclaw` possède Gateway, heartbeat, cron et tests ; `nabla-compose` conserve LiteLLM, réseau, datasets, inventaire et rollback ; `ansible-workstation` gère le système d'exploitation.
- Le cutover OpenClaw TrueNAS est **ACCEPTED historiquement (03–05/11)**. Ne pas rouvrir le chantier Workstation ; vérifier, lors des changements, qu'une seule Gateway/planification est active. Les anciennes tâches/mutateurs Workstation sont supprimés du dépôt ; le rollback reste documenté.
- [Roadmap inter-dépôts et historique](roadmap-openclaw-yubikey-extraction-20261030.md), [roadmap OpenClaw historique](openclaw-workstation-roadmap.md). Les fonctions Slack/Discord demeurent désactivées jusqu'à validation distincte.
- `nabla-yubikey` conserve le cycle matériel et les politiques ; aucune mutation PIN/PUK/OTP/PIV/SSH-sk sans consentement explicite. Les sauvegardes age/SOPS doivent rester restaurables sur supports distincts.

## P1 — Bibliothèque média \*arr (acquisition anonymisée)

- [Roadmap canonique](arr-media-library-roadmap.md) : Gluetun + qBittorrent seuls dans un namespace VPN (kill switch, DoT Quad9 dans le tunnel), Prowlarr via le proxy HTTP Gluetun, reste du homelab et DNS pfSense/Unbound inchangés ; schéma réseau et tableau des flux au §4.1.
- Décisions du 7/11 : ProtonVPN (à souscrire), Jellyfin cible, Emby seulement si la Samsung Frame l'exige, aucun accès distant, Usenet différé. Les Apps \*arr natives sont des PoC : suppression sans migration (Transmission et Readarr d'abord) ; le diagnostic `lidarr` est remplacé par cette suppression.
- Ordre : P0 suppression des sept noms publics, test de la TV, suppression des PoC, souscription → stockage `cpool/media` avec quota → frontière VPN → Prowlarr → Radarr/Sonarr/Lidarr/Recyclarr → Jellyfin/Bazarr/Seerr.
- IaC et télémétrie `CODED` le 8/11 : DNS public en OpenTofu (CNAME des routes du tunnel, retrait en deux plans des 7 noms média), profil déclaratif `cpool/media` dans le bootstrap de stockage, câblage \*arr en OpenTofu (`terraform/media`) et réconciliateur `config/media/settings.yml`, exporters + règles + tableau Grafana + journaux Loki ([§10.1](arr-media-library-roadmap.md)).
- `CODED` le 8/11 (non déployé, `status: planned`) : `apps/media-acquisition`, `prowlarr`, `radarr`, `sonarr`, `lidarr`, `bazarr`, `recyclarr`, `jellyfin`, `seerr`, `scripts/truenas/deploy-media-stack.sh` et `tests/test_media_stack_contract.py` ; route Tunnel `emby` retirée du code. Suppression de Plex et Whisparr confirmée.

**Clôture** : batterie de tests d'anonymat (§9) verte et datée sur le SHA déployé ; aucun service média joignable depuis l'extérieur.

## P1 — Fiabilité des scripts et documentation

- Redéploiement ciblé des Apps TrueNAS : **CODE ADDED 7/11** — [`redeploy-impacted-apps.py`](../scripts/truenas/redeploy-impacted-apps.py) planifie, à partir des fichiers modifiés et des `dependsOn` du catalogue, les `app.redeploy` (fournisseurs d'abord) et ne redémarre un dépendant que s'il devient malsain ; le cron horaire n'affiche que le plan. À faire : lire le premier plan réel (Apps non liées au checkout par `include`), puis un premier `--apply` validé ; décider ensuite d'un apply automatique dans le cron. [Contrat](truenas-deployment-automation.md#redeploying-only-the-apps-a-change-touches).
- **CODED dans #330** : extractions `scripts/lib/postgres.sh` et `scripts/lib/app-deploy.sh`, wrappers historiques conservés, `rollout-pending-apps.sh` plan/check/apply avec sortie expurgée et code de retour réel. La réception runtime reste ouverte. Contrôler ensuite `deploy-autokuma.sh`, `deploy-docling.sh` et `deploy-bitcoind.sh` pour les réconciliations inline ; `ntopng` nécessite licence Enterprise et interface réseau explicitement approuvées.
- Factoriser les primitives de diagnostic Docker/HTTP seulement si les scénarios d'erreur, le journal expurgé et le refus des opérations mixtes sont couverts par tests.
- Exécuter `just agent-skills-check`, `just quality` et `mise run agent-pre-push` sur un worktree non root au HEAD exact. Des échecs identiques à `master` dus au DNS ou à un utilisateur root ne valent pas une gate PASS.
- `Ask the user` avant d'installer des skills externes. Aucun nouveau skill Talos ou Docker n'est installé implicitement.

## Historique minimal : problèmes à ne pas reproduire

| Problème passé | Leçon conservée |
| --- | --- |
| App TrueNAS arrêtée et sans conteneur | `containerService` seul ne suffit pas : `appId` est nécessaire pour le rapprochement |
| OOM TrueNAS / instabilité Unbound, build, indexeurs | Diagnostiquer PSI/ARC/journaux avant d'accuser le réseau ou de redémarrer |
| Cloudflare challenge et 401 d'exporter | Séparer la preuve LAN, l'authentification et la protection du bord |
| Dépendances PyYAML de Pre-commit | Les hooks doivent déclarer leurs dépendances ; ne pas supposer le Python de `mise` |
| Drift cron OpenClaw, rate limits mal attribués | Inspecter l'identité et la session effectives ; éviter les tests de modèle coûteux |
| Anciens scripts de migration et données ZFS | Un runbook daté n'autorise jamais une nouvelle mutation ni une suppression sans preuve |
| UI Apps vide, `app.query` en timeout (4/11) | Un shim containerd bloqué tient le verrou d'un conteneur : isoler le conteneur dont `docker inspect` dépasse 5 s et tuer son seul shim, sans redémarrer dockerd ni containerd ([incident](incidents/2026-11-04-truenas-app-query-stuck-container-lock.md)) |
| Consolidation docs/scripts (6/11) | Les migrations terminées sont retirées du dépôt ; leur historique reste dans Git |

Voir [les symptômes et remédiations mémorisables](incidents/2026-11-06-migrations-retour-experience.md). Les opérations anciennes déjà exécutées ne sont plus suivies comme des tâches.

## Gouvernance et clôture

`nabla-compose` : infrastructure déclarative ; `fastapi-sample` : sondes et statuts ; `nabla-site-alban` : rendu utilisateur. Le contrat `entityRef`/`catalogRevision` est partagé, mais aucune logique de déploiement ne doit se déplacer vers les sites.

**DONE global** : catalogue et topology générés sans dérive, politiques d'accès conformes, services obligatoires prouvés `ACCEPTED (runtime)`, migrations de dépôts sans doublons et récupération testée. Toute ligne sans preuve demeure ouverte.
