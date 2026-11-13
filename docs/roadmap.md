# Services Homelab — roadmap active

> Mise à jour : **13 novembre 2026** ([passe du 13/11](runbooks/2026-11-10-roadmap-pass-blockers.md#8-reprise-du-1311), [audit TrueNAS du 13/11](runbooks/2026-11-13-truenas-audit-ssd-coverage.md)). Source d'autorité des **travaux restant à réaliser**. Une PR fusionnée ou un script versionné ne constitue pas une réception runtime. Les procédures courantes sont dans les runbooks spécialisés ; les problèmes passés utiles aux diagnostics sont dans [les leçons de migration](incidents/2026-11-06-migrations-retour-experience.md) et dans l'[archive immuable au 24/10](archive/roadmap-through-2026-10-24.md). Ne pas réexécuter d'anciennes commandes d'incident.

## Ordre d’exécution validé — 13 novembre 2026

**Ordre modifié dans la PR #369 : H02/G1 → H01 → H05.** G1 (sauvegardes et rotation du secret exposé `postgres_exporter`) est avancé sans déclarer H01 terminé. Conserver le [portefeuille unique H01–H19](roadmap-portfolio.md), sans rouvrir les anciens groupes G1–G7.

1. **H02 — Sauvegarde et restauration PostgreSQL** : rotation privée du secret exporter, backup TLS `verify-full` avec SHA-256, restauration Docker sans réseau, puis comparaison des données. Code proposé dans cette PR ; **rotation et restauration runtime non vérifiées**. Cron désactivé. [Runbook G1](runbooks/postgres-g1-restore-and-secret-rotation.md).
2. **H01 — CSI TrueNAS / Talos** : controller/DaemonSet, PVC RWX multi-workers, reclaim ZFS, NetworkPolicy et driver installé à réceptionner. [Préflight](kubernetes-csi-preflight.md).
3. **H05 — Gatus et Prometheus** : preuves fraîches `app.query`, Gatus et scrapes `up` ; `NOT_RUN` et `DENIED` ne prouvent pas `DOWN`. [Runbook](runbooks/2026-11-04-probe-remediation.md).

**Gates communes** : contrôles en lecture seule, tests locaux, SHA et preuves datées avant toute réception LAN. Aucune suppression de données ni exposition WAN implicite.

## Règles de suivi

- `CODED` : code présent dans Git ; `TESTED` : contrat local exécuté sur un SHA identifié ; `ACCEPTED (runtime)` : mesure fonctionnelle datée du service cible ; `NOT_VERIFIED` : preuve absente. Ne jamais déduire le dernier état du premier.
- Le catalogue `x-nabla` est l'autorité des identités ; `entityRef` et `catalogRevision` assurent le rapprochement entre Compose, FastAPI et sites. Les chemins `/mnt/cpool` et les secrets privés restent hors du dépôt.
- L'observation Cloudflare `DENIED`/`challenge`, un diagnostic non exécuté, ou une absence de télémétrie ne deviennent pas des services DOWN.
- Avant chaque mutation : identifier le risque de perte de données, les dépendances et une restauration proportionnée. **L'opérateur accepte la coupure de service et les redémarrages réversibles pour expérimenter ; pas d'accord supplémentaire pour la disponibilité.** Toute opération irréversible, destruction de données ou exposition non prévue exige une autorisation spécifique. La quality gate locale s'exécute sans CI payante.

## Vue inter-dépôts — choix des prochains chantiers (13 novembre 2026)
  
**[Portefeuille unique H01–H19](roadmap-portfolio.md)**. Les groupes G1–G7 antérieurs sont conservés dans [l'archive datée](archive/2026-11-13-roadmap-before-compaction.md), et non comme seconde source de priorités. **Ordre proposé par la PR #369 : H02/G1 → H01 → H05.**

### Responsabilités canoniques (ne pas dupliquer les checklists)

- **Compose** : réseau, sécurité edge, TrueNAS/Talos/pfSense, catalogue infra, secrets, Gatus et Prometheus ; scripts opérateur sous [scripts/README.md](../scripts/README.md).
- **[FastAPI engineering](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md)** : API, collecte et preuve exposée, cache, front FastAPI Cloud, qualité et budget Nano ; aucune réimplémentation dans Compose.
- **[Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/quality-roadmap.md)** : SSR/SSG, sécurité Vercel, a11y et [interfaces homelab Next.js](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/homelab-roadmap.md).
- **[Site Bababou](https://github.com/AlbanAndrieu/nabla-site-bababou/blob/master/docs/roadmap.md)** : pages, preuves documentaires, NRE, contrôle de diffusion ; [#270](https://github.com/AlbanAndrieu/nabla-site-bababou/pull/270) encore Draft.
- **[OpenClaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md)** : Gateway, heartbeat et FinOps Vercel ; intégration Compose limitée au runtime et à l’observabilité, le code de collecte appartient à OpenClaw.

**Politique de nettoyage :** les migrations OpenClaw/YubiKey déjà réceptionnées ne sont pas rouvertes ; conserver les wrappers de rollback qui ont encore des consommateurs. Déplacer une procédure datée en archive uniquement après mise à jour de ses références et des tests de contrat. Les documents historiques ne réintroduisent pas de tâches clôturées.

## Suivi consolidé — état du code et réception (8 novembre 2026)
  
Le tableau de déploiements/sondes/versions **daté du 8–13 novembre** est [archivé intégralement](archive/2026-11-13-roadmap-before-compaction.md) : ne pas le confondre avec la situation runtime actuelle. Pour l'état `CODED` vs `ACCEPTED (runtime)`, consulter [H01–H19](roadmap-portfolio.md).

## P0 — Réception du catalogue et des sondes (PR #326)

- **H05** : fraîcheur des résultats Gatus, jobs Prometheus, contrôle direct, `app.query`, `entityRef` et `catalogRevision` ; respecter `NOT_RUN`/`DENIED`/`planned`. [Runbook](runbooks/2026-11-04-probe-remediation.md).
- **H17** : [#365 Compose](https://github.com/AlbanAndrieu/nabla-compose/pull/365) fusionnée, [#424 FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/pull/424) en attente ; réception inter-dépôts du catalogue V2 avant suppression de l'inventaire legacy. [Contrat](service-catalog-v2-normalization.md).
- **H03/H08** : matérialisation Homarr/secret `0600`, puis NetBox, Dependency-Track, Joplin. [Secrets](runbooks/2026-11-10-secrets-migration-backlog.md) et [Apps](runbooks/2026-11-06-catalog-apps-to-compose.md).
- Anciennes instructions Kibana/Graylog/AIStor et Apps déjà déployées : [archive du 13/11](archive/2026-11-13-roadmap-before-compaction.md), **ne pas relancer**.

## P0 — Keycloak, Home Assistant, PostgreSQL et Apps en attente (#330)

- **H01** : ne pas déplacer Keycloak/Hermes/Vault sur Talos sans preuve CSI RWX, reclaim et NetworkPolicy. [Préflight CSI](kubernetes-csi-preflight.md).
- **H02** : `postgresbackup` dump signé par SHA-256 puis **restore isolé** avant d'activer le cron. [Runbook sauvegarde](runbooks/production-app-operations.md).
- **H19** : migration de Home Assistant vers une App Compose, recorder sur PostgreSQL et rollback prouvés. [Runbook Apps](runbooks/2026-11-06-catalog-apps-to-compose.md).
- **H08** : NetBox, Dependency-Track, Joplin, `rollout-pending-apps.sh --check` et un seul `--apply` à la fois après la séquence P0.
- L'ancien ordre de déploiement et le retrait de Databasus restent dans [l'archive](archive/2026-11-13-roadmap-before-compaction.md), sans autoriser de suppression de données.

## P0 — Cloudflare, secrets et frontières d'accès

1. **Cloudflare Tunnel / Access** (10/11 : `fastapi-sample.albandrieu.com` n'a **aucun** enregistrement DNS — le code bascule déclaration, catalogue, scripts et sondes, mais rien n'est servi tant que le plan suivant n'est pas appliqué ; l'ancien nom reste servi derrière Access) : valider le plan OpenTofu de retrait des routes `external=false`, le renommage public FastAPI Sample, et la précédence du refus `/realms/master` avant les routes Keycloak publiques ; n'appliquer qu'avec approbation et comparaison exacte des effets. Aucune exception WAF/Bot pour Keycloak/LiteLLM ; l'observateur TrueNAS fournit la preuve LAN. [Module IaC](../terraform/cloudflare/README.md). Inclut les sept noms média publics observés le 7/11 (`radarr`, `sonarr`, `prowlarr`, `lidarr`, `transmission`, `sabnzbd`, `emby` : `403` Cloudflare sans Access, [§2.3](arr-media-library-roadmap.md)). **10/11** : apply OpenTofu (2 ajouts dont l'application Access `postgres`, 4 modifications, 0 suppression, re-plan vide) avec le jeton dédié `nabla-opentofu` géré par l'unité `cloudflaretokens` (état chiffré) ; puis applications en contournement `keycloakoidc` (`/realms/nabla`, `/resources` seulement) et `joplin`. `fastapi-sample` et `postgres` répondent 302 Access ; `/realms/master`, `/admin` et la racine Keycloak restent refusés au bord (403). Phase `retire` du DNS appliquée le 10/11 : 26 CNAME détruits (sept noms média, kibana et 18 routes retirées du Tunnel), NXDOMAIN au serveur autoritaire, re-plan vide. Restent deux enregistrements publics `hello` et `s3` sous `.int.albandrieu.com` signalés par le contrôle `no_public_private_namespace_records` ; 12/11 : `hello` est le canari approuvé (`config/public-int-dns-exceptions.txt`), `s3` part au troisième tour de retrait (plan d'adoption : 1 import, apply en attente d'accord, Q16).
2. **Service Auth observateur** : aligner les politiques des applications concernées sans `Bypass` général ; protéger le coffre web et `/admin` Vaultwarden en limitant les exceptions aux chemins clients. Recetter depuis un client externe avant retrait d'une ancienne politique.
3. **Secrets** : prouver la concordance Vaultwarden → fichier canonique 0600 → environnement conteneur, sans afficher de valeur. Une ancienne session `BW_SESSION` exposée ne doit jamais être réutilisée. [Roadmap secrets](secrets-migration-roadmap.md). **10/11** : bichon, clickhouse, graylog, langflow, mongo, nexus, ollama, pihole, redis et sentry-clickhouse déclarés dans le manifeste ; leurs copies runtime sont identiques aux anciens fichiers `/mnt/cpool/<service>/` encore lus par le Compose (contrôle par empreinte), importés dans Vaultwarden le 10/11 (parité vérifiée) ; bascule vers les chemins canoniques **CODED le 12/11** pour neuf d'entre eux (`env_file` obligatoire sur `/mnt/cpool/secrets/runtime/<app>/`), redéploiement un par un à faire ; Redis reste sur son `.env`, son mot de passe étant interpolé dans `command:` (Q18). Redis, MinIO et Open WebUI refusent désormais de démarrer sans leur mot de passe au lieu d'utiliser une valeur publique (aucun conteneur ne l'utilisait). **Wazuh : rotation APPLIED le 12/11** : `rotate-wazuh-internal-users.sh --apply` a chargé dans l'index de sécurité les hashes de `admin` et `kibanaserver` (mots de passe de `nabla/prod/wazuh`, différents des valeurs d'exemple), puis redéploiement. Le manager parle à l'indexer en TLS 1.3 sans 401 (114 refus entre 21:35 et la rotation). Aucune route Tunnel publique.
4. **OVH / FastAPI Cloud** : vérifier la nouvelle identité de lecture seule et les scopes ; `pfSense` y reste `transport_only` (contrat accepté) et la sonde Tavily `GET /usage` ne nécessite plus de migration. Au 6/11, FastAPI Cloud répond mais reste `degraded` : le contrôle `openstack_me` échoue (identifiant OVH « does not exist »). **10/11** : `livez`, `readyz` et `healthz` sains.

**Clôture** : règles Access du moindre privilège et sondes de bord expurgées, sans régression du DNS ni création d'une exposition WAN.

## P0 — Accepter les services critiques

- **TrueNAS 27** : hôte passé de 26.0.0-BETA.3 à 27.0.0-RC.1 les 5–6/11 (TrueNAS 26 renommé 27 ; API REST supprimée, aucun client du dépôt ne l'utilise). Contrôles post-upgrade encore à exécuter **sur l'hôte TrueNAS via SSH** : `midclt call system.version`, `just talos-stopped-vms-check`, `just truenas-readiness-check`, `just truenas-fastapi-check`, MCP `truenas-readonly`, données TrueNAS de portracker, provision/bind d'un PVC CSI, 2FA. Conserver l'environnement de boot précédent tant qu'ils ne passent pas. [Upgrade coupling](truenas-operator-tools.md#upgrade-coupling).
- TrueNAS : prouver la disponibilité réelle (et non le seul état du conteneur), les ACL NFS, les secrets et les dépendances Postgres/ClickHouse.
- **FastAPI Sample** : base `fastapisample` en `verify-full` (TLS 1.3), `healthy` le 13/11 ; ses erreurs arrivent dans Sentry (événement de test `083754a9`, issue 3), lisibles par le MCP Sentry de nabla-compose. Démarrage de 3 min 40 (trois pauses d'environ 1 min avant Unleash, Logfire et Sentry) à corriger dans fastapi-sample. [Diagnostic TrueNAS](runbooks/fastapi-sample-truenas-diagnostics.md). FastAPI Cloud `degraded` : voir le point 4 OVH ci-dessus.
- FastAPI Sample : vérifier la parité API/UI et le mode OWNER, les cibles Prometheus, le routeur LiteLLM et la sélection du corpus OpenRAG privé ; test navigateur Chromium uniquement si disponible. [Diagnostic consolidé](runbooks/fastapi-consolidated-diagnostics-20261030.md).
- Talos / Kubernetes : valider le retained smoke `democratic-csi` NFS, les trois nœuds Ready et les politiques NetworkPolicy avant nouveaux workloads. 10/11 : trois nœuds `Ready`, mais `truenas-csi-controller` en `Error` depuis 18 jours, aucun PVC ni NetworkPolicy ([passe du 10/11](runbooks/2026-11-10-roadmap-pass-blockers.md), Q7). [Préflight](kubernetes-csi-preflight.md).
- pfSense / CrowdSec : conserver la preuve que PF charge les règles, puis démontrer le rattachement WAN exact sans bloquer une IP d'administration ; ne pas prendre une ancre chargée pour une preuve de filtrage effectif.
- Authentification et monitoring : réparer les exporters sans confondre un `401` Prometheus avec un `401` OpenClaw ; Gatus/Prometheus sont des preuves indépendantes.

**Clôture** : `ACCEPTED (runtime)` sur le SHA déployé, avec date, source et un test négatif pour chaque frontière sensible ; sinon `NOT_VERIFIED`.

## P1 — Performance, stockage et restauration TrueNAS

- Mesurer mémoire/PSI/ARC, OOM, zombies, limites de conteneurs et descripteurs containerd, puis appliquer les limites mesurées à partir du pic cgroup `memory.peak` (4/11 : nexus 1,9 Gio, opensearch-security 1,8, docling 1,5, kafka 1,2, keycloak 0,9, litellm 0,7). L'arrêt de certains services par décision opérateur n'est pas une réparation définitive. 13/11 : 61 Gio, conteneurs ~35 Gio, ARC 11,7 Gio (plancher 1,9), PSI mémoire < 1 % ; Sentry et sa ClickHouse (~5,9 Gio, 18 conteneurs) repassent `running` par décision opérateur ; `bitcoind` plafonne à sa limite (1,36/1,5 Gio, CPU 100 % en synchronisation initiale).
- Après le reboot de la mise à niveau 27 : vérifier avec `diagnose-performance.sh` que le thread noyau de l'ancienne JVM `wazuh-indexer` a disparu, que les zombies restants sont purgés et que l'ARC remonte ; confirmer le redéploiement `deploy-wazuh.sh` du 4/11 (non vérifié).
- Zombies : `init: true` (4/11, sur master le 9/11) **effectif le 10/11** sur 9 Apps redéployées une par une (bichon, clickhouse, kafka, minio, mongo, ollama, openwebui, sentry-clickhouse, suricata) : 306 zombies → 3, dont 267 sous la JVM kafka ([preuve](incidents/2026-11-10-truenas-docker-orphan-volumes-purge.md)). Restent drawio (App STOPPED, `init` au prochain démarrage), `kafka-exporter` (`init` ajouté le 10/11, effectif au prochain redéploiement de `kafka`) et `reactive-resume` (App catalogue) non versionné.
- Réconcilier le proxy Docker Socket versionné avec les consommateurs avant de retirer l'ancien réseau `intranet` ; `POST=0` doit rester la valeur par défaut. Choisir explicitement le sort de Doco-CD.
- Appliquer les tâches ZFS de rétention **après `--plan`**, vérifier par dataset les snapshots, puis tester une restauration hors du TrueNAS. Ne jamais effectuer `docker volume prune` ou un nettoyage global de snapshots.
- Prendre en compte la mémoire du `wazuh-indexer` et la politique de rétention des bases selon le dernier audit read-only. Volumes Docker orphelins : **purgés le 10/11** ([preuve](incidents/2026-11-10-truenas-docker-orphan-volumes-purge.md)), 760 volumes dont 725 dangling → 100 dont 65 ; 660 `candidate:*` supprimés (~853 Mo, 0 échec), `app.query` 1,2 s → 0,3 s. Reste à décider volume par volume : 41 `review:recent`, 8 `review:unsized`, 2 `review:large` (195 et 122 Mo), 2 `nabla-compose_*` et 2 nouveaux `candidate:anonymous` ; relancer [`reconcile-docker-orphan-volumes.sh`](../scripts/truenas/reconcile-docker-orphan-volumes.sh) `--plan` (`just docker-orphan-volumes-plan`) car la dérive reprend (+67 dangling entre le 4/11 et le 10/11).
- [`bitcoind`](../apps/bitcoind/README.md) : **Custom App déployée le 12/11** (App catalogue et ses `ix-volumes` de 885 Go supprimés, `cpool/bitcoind` créé, nœud `healthy` en synchronisation initiale). 13/11 : partage NFS 17 et montage `/media/bitcoin` de la workstation retirés (aussi dans ansible-workstation, PR #24), `cpool/bitcoin` (712 Go) encore présent, car l'appel `pool.dataset.delete` est resté bloqué sans créer de job (runbook du 10/11, section 8) ; reprendre hors charge la purge du cache de build Docker (~10 Go) ; décider la consolidation des moteurs de recherche (2 OpenSearch + indexer Wazuh).
- Vérifier les alertes Restic `workstation_restic` et configurer au moins un récepteur Alertmanager, puis une restauration hors site. 10/11 : le récepteur `default` est vide, aucune alerte ne part ; `NablaExporterTargetDown` depuis le 07/11 pour quatre exporters jamais déployés (Q11, Q12 de la [passe du 10/11](runbooks/2026-11-10-roadmap-pass-blockers.md)). 12/11 : ces jobs sont `planned` et exclus de l'alerte depuis e5a4c165 ; récepteur Slack actif (`api_url_file`, Prometheus redéployé). 13/11 : `postgres_exporter` déployé, Prometheus rechargé. Reste la restauration Restic hors site.

Références : [performance](../scripts/truenas/diagnose-performance.sh), [snapshots ZFS](truenas-zfs-snapshot-policy.md), [cycle de vie des Apps](truenas-app-lifecycle.md).

## P1 — Janvier 2027 : mise à niveau TrueNAS 27.0 finale

La 27.0 finale est annoncée début décembre 2026 (hôte en 27.0.0-RC.1, profil Early Adopter, aucune RC.2). Planifier la mise à niveau en **janvier 2027**, une fois les premiers retours publiés, avec la transaction du [runbook de reboot](homelab-reboot-runbook.md) : bundle régénéré depuis `master`, `--check`, `--prepare`, mise à niveau, puis `--post-reboot-check`, `--resume` et `--verify`. Avant : relire les [notes de version 27](https://www.truenas.com/docs/scale/27/gettingstarted/versionnotes/) et les reboots bloqués après un échec du script de mise à niveau signalés sur le forum. Ne pas lancer `zpool upgrade` (le flag `dynamic_gang_header` empêche le retour arrière en lecture seule) et garder l'environnement de boot précédent. **Clôture** : 27.0 installée, transaction `VERIFIED`, contrôles post-upgrade du P0 TrueNAS 27 passés.

## P1 — Avant TrueNAS 28 : sortir de `auth.login_with_api_key`

`auth.login_with_api_key` est déprécié en 27 et supprimé en 28. TrueNAS CSI `v1.0.3` (encore en `v1.3.0`), `@profanter-dev/truenas-mcp` `1.0.6` et portracker (ancien `/websocket`) l'utilisent : les migrer vers `auth.login_ex` (`API_KEY_PLAIN` ou SCRAM), puis rejouer provision/persistance/reclaim CSI. **Clôture** : aucun client sur l'ancienne méthode avant toute mise à niveau en 28. [Upgrade coupling](truenas-operator-tools.md#upgrade-coupling).

## P1 — Séparation OpenClaw / Workstation / YubiKey

Migration de dépôt **historiquement réceptionnée**. Les futurs travaux Gateway/heartbeat relèvent de [nabla-openclaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md), les mutations matérielles et certificats de [nabla-yubikey](https://github.com/AlbanAndrieu/nabla-yubikey). [Bilan figé](roadmap-openclaw-yubikey-extraction-20261030.md).

## P1 — Bibliothèque média \*arr (acquisition anonymisée)

- [Roadmap canonique](arr-media-library-roadmap.md) : Gluetun + qBittorrent seuls dans un namespace VPN (kill switch, DoT Quad9 dans le tunnel), Prowlarr via le proxy HTTP Gluetun, reste du homelab et DNS pfSense/Unbound inchangés ; schéma réseau et tableau des flux au §4.1.
- Décisions du 7/11 : ProtonVPN (à souscrire), Jellyfin cible, Emby seulement si la Samsung Frame l'exige, aucun accès distant, Usenet différé. Les Apps \*arr natives sont des PoC : suppression sans migration (Transmission et Readarr d'abord) ; le diagnostic `lidarr` est remplacé par cette suppression.
- Ordre : P0 suppression des sept noms publics, test de la TV, suppression des PoC, souscription → stockage `cpool/media` avec quota → frontière VPN → Prowlarr → Radarr/Sonarr/Lidarr/Recyclarr → Jellyfin/Bazarr/Seerr.
- IaC et télémétrie `CODED` le 8/11 : DNS public en OpenTofu (CNAME des routes du tunnel, retrait en deux plans des 7 noms média), profil déclaratif `cpool/media` dans le bootstrap de stockage, câblage \*arr en OpenTofu (`terraform/media`) et réconciliateur `config/media/settings.yml`, exporters + règles + tableau Grafana + journaux Loki ([§10.1](arr-media-library-roadmap.md)).
- `CODED` le 8/11 (non déployé, `status: planned`) : `apps/media-acquisition`, `prowlarr`, `radarr`, `sonarr`, `lidarr`, `bazarr`, `recyclarr`, `jellyfin`, `seerr`, `scripts/truenas/deploy-media-stack.sh` et `tests/test_media_stack_contract.py` ; route Tunnel `emby` retirée du code. Suppression de Plex et Whisparr confirmée.

**Clôture** : batterie de tests d'anonymat (§9) verte et datée sur le SHA déployé ; aucun service média joignable depuis l'extérieur.

## P1 — Assistants IA, IaC et observabilité (11 novembre 2026)

- **H12** : OpenRAG/LiteLLM/Docling, embeddings workstation, clés virtuelles non maîtresses, corpus privé. [Runbook](runbooks/openrag-babou-ingestion-diagnostics.md).
- **H05** : vérifier les exports `postgres-exporter`/`pg_up`, jobs Gatus/Prometheus et la fraîcheur ; aucun succès supposé à partir des chiffres du 11/11. [Remédiation](runbooks/2026-11-04-probe-remediation.md).
- États de livraison des assistants, clés LiteLLM, Slack et exporters : [archive datée](archive/2026-11-13-roadmap-before-compaction.md).

## P1 — Fiabilité des scripts et documentation

- Redéploiement ciblé des Apps TrueNAS : **CODE ADDED 7/11** — [`redeploy-impacted-apps.py`](../scripts/truenas/redeploy-impacted-apps.py) planifie, à partir des fichiers modifiés et des `dependsOn` du catalogue, les `app.redeploy` (fournisseurs d'abord) et ne redémarre un dépendant que s'il devient malsain ; le cron horaire n'affiche que le plan. À faire : lire le premier plan réel (Apps non liées au checkout par `include`), puis un premier `--apply` validé ; décider ensuite d'un apply automatique dans le cron. [Contrat](truenas-deployment-automation.md#redeploying-only-the-apps-a-change-touches).
- **CODED dans #330** : extractions `scripts/lib/postgres.sh` et `scripts/lib/app-deploy.sh`, wrappers historiques conservés, `rollout-pending-apps.sh` plan/check/apply avec sortie expurgée et code de retour réel. La réception runtime reste ouverte. Contrôler ensuite `deploy-autokuma.sh`, `deploy-docling.sh` et `deploy-bitcoind.sh` pour les réconciliations inline ; `ntopng` nécessite licence Enterprise et interface réseau explicitement approuvées.
- Terragrunt CD : **retiré le 12/11** (Q17). Aucun runner `infra-runners` (0 runner enregistré, environnement `TrueNAS` sans secret, exécutions d'août annulées après 24 h d'attente) et le backend Garage n'est joignable que du LAN. Plan et apply restent sur la workstation via `terragrunt-safe.sh` ; la CI garde la validation statique (`terragrunt-ci.yaml`). Un contrat refuse tout `terragrunt init/plan/apply` ou `tofu plan/apply` dans un workflow.
- Factoriser les primitives de diagnostic Docker/HTTP seulement si les scénarios d'erreur, le journal expurgé et le refus des opérations mixtes sont couverts par tests.
- Exécuter `just agent-skills-check`, `just quality` et `mise run agent-pre-push` sur un worktree non root au HEAD exact. Des échecs identiques à `master` dus au DNS ou à un utilisateur root ne valent pas une gate PASS.
- `Ask the user` avant d'installer des skills externes. Aucun nouveau skill Talos ou Docker n'est installé implicitement.

## P2 — Étude : EnOcean (NodOn) dans Home Assistant

**H18 · PLANNED** — [Étude EnOcean/Somfy et radio Flexom](roadmap-homeassistant-integrations.md), sans configuration ni achat implicite.

## P2 — Étude : volets et alarme Somfy dans Home Assistant

**H18 · PLANNED** — [Même étude](roadmap-homeassistant-integrations.md) ; protocole des moteurs et modèle d'alarme à identifier.

## Historique minimal : problèmes à ne pas reproduire

Les leçons d'exploitation sont dans [les incidents](incidents/2026-11-06-migrations-retour-experience.md) ; le tableau original est dans [l'archive datée](archive/2026-11-13-roadmap-before-compaction.md). Aucune ancienne procédure n'autorise une mutation actuelle.

## Gouvernance et clôture

`nabla-compose` : infrastructure déclarative ; `fastapi-sample` : sondes et statuts ; `nabla-site-alban` : rendu utilisateur. Le contrat `entityRef`/`catalogRevision` est partagé, mais aucune logique de déploiement ne doit se déplacer vers les sites.

**DONE global** : catalogue et topology générés sans dérive, politiques d'accès conformes, services obligatoires prouvés `ACCEPTED (runtime)`, migrations de dépôts sans doublons et récupération testée. Toute ligne sans preuve demeure ouverte.


## P0/P1/P2 — Cible cryptographique FIPS, PostgreSQL 16 → 18, TLS 1.3, Vault et OAuth (10 novembre 2026)

**H09** : durcir les clients PostgreSQL restants en `verify-full` avec CA/SAN contrôlés. PostgreSQL 18.6, SCRAM et `hostssl` ont été préparés, mais cela n'atteste pas la conformité de tous les clients.

**H16** : pilote Vault PKI/OAuth SQL/OIDC Keycloak, révocation et break-glass. L'objectif FIPS 140-3 est un **alignement technique**, non une certification.

[Runbook détaillé FIPS, TLS 1.3, Vault et OAuth](security/postgresql-fips-tls13-vault-oauth-20261110.md). La matrice datée initiale est [archivée](archive/2026-11-13-roadmap-before-compaction.md).
