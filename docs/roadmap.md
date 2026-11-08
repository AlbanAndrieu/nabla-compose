# Services Homelab — roadmap active

> Mise à jour : **6 novembre 2026**. Source d'autorité des **travaux restant à réaliser**. Une PR fusionnée ou un script versionné ne constitue pas une réception runtime. Les procédures courantes sont dans les runbooks spécialisés ; les problèmes passés utiles aux diagnostics sont dans [les leçons de migration](incidents/2026-11-06-migrations-retour-experience.md) et dans l'[archive immuable au 24/10](archive/roadmap-through-2026-10-24.md). Ne pas réexécuter d'anciennes commandes d'incident.

## Règles de suivi

- `CODED` : code présent dans Git ; `TESTED` : contrat local exécuté sur un SHA identifié ; `ACCEPTED (runtime)` : mesure fonctionnelle datée du service cible ; `NOT_VERIFIED` : preuve absente. Ne jamais déduire le dernier état du premier.
- Le catalogue `x-nabla` est l'autorité des identités ; `entityRef` et `catalogRevision` assurent le rapprochement entre Compose, FastAPI et sites. Les chemins `/mnt/cpool` et les secrets privés restent hors du dépôt.
- L'observation Cloudflare `DENIED`/`challenge`, un diagnostic non exécuté, ou une absence de télémétrie ne deviennent pas des services DOWN.
- Avant chaque mutation : sauvegarde, plan en lecture seule, accord opérateur, preuve de retour arrière. La quality gate locale s'exécute sans CI payante.

## P0 — Réception du catalogue et des sondes (PR #326)

[PR Compose #326](https://github.com/AlbanAndrieu/nabla-compose/pull/326) : les `appId` de `graylog`, `bitcoind`, `elasticsearch` (`elastic-search`) et `hermes` (`hermes-agent`) sont **corrigés dans le code**, en conservant `containerService`. Cela supprime le double comptage `declared_only` + `observed_only` des Apps arrêtées, mais **ne les démarre pas**.

| Priorité | Travail restant | Critère de clôture |
| --- | --- | --- |
| P0 | Fusionner la PR après `mise run agent-pre-push` et contrôle des générateurs sur le HEAD réel | L3 locale + parité du catalogue sans erreur de liaison |
| P0 | Diagnostiquer `graylog`, `lidarr`, `homarr`, ainsi que les Apps arrêtées `bitcoind` / `elastic-search` / `hermes-agent` ; respecter les arrêts volontaires | État TrueNAS et preuves HTTP/health concordants, sans forcer un démarrage |
| P0 | Déployer sous contrôle `dependency-track`, `netbox`, `plumber`, `scanopy`, `joplin`, `ntopng` sur TrueNAS, si prérequis validés | `app.query` + `/api/homelab/status` = `in_sync` et sondes fraîches |
| P1 | Trancher l'exposition externe de Joplin, actuellement `external=true` mais DNS uniquement privé | Contrat et politique Access/Traefik alignés sans ouverture non autorisée |
| P1 | Conserver `aistor` et `wordpress` en `status: planned` ; les exclure des alertes d'indisponibilité | Les consommateurs affichent le statut planifié |
| P1 | Migration du nom canonique `homeassistant`/`openwebui` via procédure TrueNAS, pas par simple changement d'`appId` | Sauvegarde et rollback attestés, middleware + URL + Access + données validés |

Le [runbook des remédiations encore ouvertes](runbooks/2026-11-04-probe-remediation.md) contient **uniquement** les gestes non réceptionnés et le diagnostic des cas atypiques. Les identités canonisées, le mode pfSense `transport_only` et la décision de ne pas exempter Keycloak/LiteLLM au WAF sont des décisions **déjà intégrées**, pas des nouvelles tâches.

## P0 — Cloudflare, secrets et frontières d'accès

1. **Cloudflare Tunnel / Access** : valider le plan OpenTofu de retrait des routes `external=false`, le renommage public FastAPI Sample, puis appliquer seulement avec approbation et comparaison exacte des effets. Aucune exception WAF/Bot pour Keycloak/LiteLLM ; l'observateur TrueNAS fournit la preuve LAN. [Module IaC](../terraform/cloudflare/README.md).
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

- **Compose** garde LiteLLM TrueNAS, le réseau, les datasets, le catalogue et les contrats d'intégration ; **nabla-openclaw** devient propriétaire de la Gateway, du heartbeat, du cron et de leurs tests ; **ansible-workstation** garde les prérequis OS ; **nabla-yubikey** les politiques et diagnostics matériels.
- [Plan de séparation inter-dépôts](roadmap-openclaw-yubikey-extraction-20261030.md) : la préparation Git ne démontre pas de cutover. Ne retirer aucun consommateur ni déplacer un gitlink sans preuve que les chemins historiques ne sont plus référencés et qu'un rollback fonctionne.
- Gate OpenClaw : modèles disponibles sur LiteLLM TrueNAS, quotas RPM/TPM attestés, clés scindées main/cron, logs des deux proxys, politiques heartbeat/cron bornées et activées **une seule fois**, identité et session effectives vérifiées. Tant que la Gateway Workstation fonctionne, la bascule TrueNAS est `NOT_VERIFIED`.
- Gate YubiKey : sauvegardes age/SOPS restaurables sur supports distincts ; aucune mutation PIN/PUK/OTP/PIV/SSH-sk sans consentement explicite.

## P1 — Fiabilité des scripts et documentation

- Redéploiement ciblé des Apps TrueNAS : **CODE ADDED 7/11** — [`redeploy-impacted-apps.py`](../scripts/truenas/redeploy-impacted-apps.py) planifie, à partir des fichiers modifiés et des `dependsOn` du catalogue, les `app.redeploy` (fournisseurs d'abord) et ne redémarre un dépendant que s'il devient malsain ; le cron horaire n'affiche que le plan. À faire : lire le premier plan réel (Apps non liées au checkout par `include`), puis un premier `--apply` validé ; décider ensuite d'un apply automatique dans le cron. [Contrat](truenas-deployment-automation.md#redeploying-only-the-apps-a-change-touches).

- Remplacer les scripts de déploiement à mutation implicite par des contrats explicites `--check` / `--apply` et une preuve de non-mutation en préflight. En particulier, `ntopng` dépend d'une licence Enterprise, d'une identité ClickHouse limitée et de l'interface réseau approuvée.
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

## P1 — Remédiation des sondes et migration des Custom Apps (6 novembre 2026)

La PR [#327](https://github.com/AlbanAndrieu/nabla-compose/pull/327) code la transition de moniteurs Gatus/Prometheus sur services `planned` ou `disabled`, ainsi que les configurations préparatoires des Apps Dockhand et ddns-updater. Aucune bascule runtime n'est effectuée par la PR : les migrations restent conditionnées aux sauvegardes, au plan de retour arrière et à l'approbation explicite de l'opérateur. Voir [le runbook dédié](runbooks/2026-11-06-catalog-apps-to-compose.md).

L'acceptation doit distinguer les moniteurs exclus intentionnellement du rendu actif, les cibles Prometheus observées et la santé applicative réelle. Les observations du 6 novembre sont historiques et ne prouvent pas l'état courant.
