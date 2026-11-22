# Portefeuille Homelab — arbitrage inter-dépôts

> **Arbitrage actualisé le 22 novembre 2026** : l'opérateur décide **H17 d'abord**, puis **Dependency-Track + outils CTEM**, pendant que l'étude **H18 EnOcean/Somfy** devient active ; **H08 autres Apps / Nexus non urgent**. Le précédent ordre H01 → H02 → H04 → H05 → H12 → H13 → H16 est conservé ci-dessous comme **séquence historique du 14/11**, sans priver les tests d'une référence. H01/H02 sont déjà réceptionnés sur leur gate principale. Les 21 IDs restent conservés.

## Autorités et règles

- **Infrastructure** : [roadmap nabla-compose](roadmap.md), source pour TrueNAS, Talos, CSI, pfSense, Cloudflare, sauvegardes et secrets.
- **Application/sondes/UI** : [engineering-roadmap fastapi-sample](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md), source pour FastAPI Cloud, OWNER, caches, qualité et rendu.
- **OpenClaw et clés matérielles** : [nabla-openclaw](https://github.com/AlbanAndrieu/nabla-openclaw) et [nabla-yubikey](https://github.com/AlbanAndrieu/nabla-yubikey) gardent leurs propres roadmaps. Ne pas recréer leur backlog ici.
- **CODED**, **TESTED**, **DEPLOYED** et **ACCEPTED (runtime)** ne sont jamais interchangeables. `NOT_VERIFIED` : aucune nouvelle preuve de réception datée. `PARTIAL` : plusieurs éléments, mais pas de réception bout-en-bout. Aucun statut inféré d'un simple merge.
- Les indisponibilités réversibles sont acceptées dans ce homelab ; une perte de données, une exposition WAN ou une mutation de clé matérielle réclame une approbation explicite.

## Ordre opérateur — 22 novembre 2026

La priorité est **décidée** ; les réceptions runtime restent indépendantes des merges. **Dependency-Track est extrait du lot applicatif non urgent H08** et suivi avec les outils de sécurité H13 (CTEM/SBOM) ; l'ID H08 reste réservé aux autres Apps et Nexus. Les dépendances nécessaires sont traitées de façon ciblée, et non comme une raison de bloquer tout un lot.

| Rang | Chantier | Action prioritaire | Gate / dépendances | Effort |
| --- | --- | --- | --- | --- |
| **1** | **H17 — terminer Backstage V2** | Résoudre `sentry-edge` par `appId=sentry`, régénérer les exports V2, vérifier `composeProfiles`, `entityRef` et `catalogRevision` des trois consommateurs ; auditer les lecteurs legacy et les retirer seulement après preuve de parité | Prérequis de CTEM et des tableaux de bord. **CODED / pas de réception runtime à partir de GitHub** | M |
| **2** | **H13 — Dependency-Track / CTEM** | Préflight de Dependency-Track (images épinglées, secrets 0600, rôle PostgreSQL, SBOM CycloneDX, Gatus + Prometheus), puis activer et qualifier Amass, Cartography, Prowler, OASM et DefectDojo sans inventaire concurrent | H17 pour la jointure des entités ; accès LAN et secrets applicatifs H03 uniquement. Pas de scan actif non autorisé ni de finding non vérifié | L |
| **3** | **H05 — preuves CTEM** | Recharger et observer Gatus/Prometheus, contrôler provenance externe/interne et fraîcheur, conserver `DENIED`/`NOT_RUN` distincts de `DOWN` | H17 + H13 ; H04 limité aux constats WAN pour l'attribution d'exposition | M |
| **4 (en parallèle)** | **H18 — EnOcean/Somfy** | Lancer maintenant les diagnostics Home Assistant, USB/serial et Overkiz ; inventorier les moteurs io/RTS et le modèle d'alarme ; sélectionner le pilote lecture seule | Pas besoin d'attendre la migration H19 pour étudier. Clé actuelle Zigbee ≠ EnOcean, USB300/box io potentiellement à acquérir **après** compatibilité | S–M |
| 5 (conditionnel) | **H03/H04** | Débloquer secrets de Dependency-Track ou accès strictement nécessaires aux sondes/CTEM ; réaliser tests négatifs WAN | Pas de refonte edge générale ni d'apply Cloudflare imprévu | M |
| Différé | **H08 — Nexus, Joplin et autres Apps** | Conserver [#438](https://github.com/AlbanAndrieu/nabla-compose/pull/438), sans en faire une dépendance artificielle de H17/H13 | À reprendre après les quatre rangs précédents ; NetBox est déjà opérationnel | M |
| Plus tard | **H09/H10/H11/H12/H14/H16/H19/H20/H21** | Fiabilisation TLS, ZFS, agent OpenClaw #437, RAG, IAM, migration Home Assistant, GitHub et FreshRSS | N'affecte pas la priorité du pilote H18 ni la phase CTEM actuelle | M–L |
| Suspendu | **H07/H15** | pfSense non remplacé et pile média VPN non activée | Études hors du chemin critique | L |

**Clôture H17** : les artefacts Git V2 doivent être synchronisés, `sentry-edge` doit correspondre à **une seule App** dans Sample, et les trois lecteurs doivent afficher la même révision sur leurs SHA déployés. **Sans ce dernier contrôle LAN/OWNER, H17 reste CODED/TESTED, non ACCEPTED.**

**Clôture CTEM** : import d'un CycloneDX volontaire via Dependency-Track, observation métriques et refus de l'API anonyme, rapport Amass privé borné (deux vantage autorisées), revue des findings et déduplication DefectDojo ; aucune nouvelle route publique implicite.

## Backlog arbitrable

| ID | Priorité | Propriétaire | Code/préparation | Réception runtime | Preuve à produire et référence |
| --- | --- | --- | --- | --- | --- |
| H01 | P0 | nabla-compose | DEPLOYED | PARTIAL | **GATE CSI ATTEINTE le 21/11** : NFS RWX multi-workers, reclaim ZFS et NetworkPolicy Cilium vérifiés ; Falco 3/3. Ne pas refaire la migration CSI. Le déploiement Keycloak/Hermes relève de H03/H08/H16, API TrueNAS de H10 et SPIRE du pilote H16 — [Préflight CSI](kubernetes-csi-preflight.md) |
| H02 | P0 | nabla-compose | DEPLOYED | PARTIAL | **GATE sauvegarde ATTEINTE le 21/11** : 9 bases, cron quotidien, trois restaurations isolées et TLS verify-full vérifiés. Reliquat précis : rotation privée de l'identité `postgres_exporter` après recette H03 ; ne pas relancer la migration backup — [Runbook G1](runbooks/postgres-g1-restore-and-secret-rotation.md) |
| H03 | P0 | nabla-compose | PARTIAL | NOT_VERIFIED | Vaultwarden **1.37.5 déjà déployé et healthy** le 21/11, `bitwarden-api` revenu healthy après suppression des anciens overrides Pi-hole ; `talosconfig`/kubeconfig placés en pièces jointes privées. Restent la matérialisation 0600 des secrets Keycloak, Joplin, Homarr, autres Apps et la rotation `postgres_exporter`, puis tests fichier→conteneur et refus sans clé — [Backlog secrets](runbooks/2026-11-10-secrets-migration-backlog.md) |
| H04 | P0 | nabla-compose | PARTIAL | NOT_VERIFIED | **#436 fusionnée le 22/11 (CODED)** : Traefik/CrowdSec AppSec, honeypot `login` sans credentials, Gatus/Prometheus et correction du graphe pfSense retiré ; Hello HTTPS/SNI + réseau Docker observés depuis le LAN, **pas de preuve WAN**. CNAME `login`, Access bypass ciblé, SNI réel, client IP, 403, rate limit, tests négatifs DNS et `/realms/master` restent à réceptionner. Cloudflare import-first via état Garage, `s3.int` exception publique explicite. Revoir séparément politique mail des 20 zones et WAF Vercel Bababou (#433), tous deux non appliqués selon dernier relevé — [Honeypot](../apps/honeypot/README.md), [Cloudflare](../terraform/cloudflare/README.md) |
| H05 | P0 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | 22/11 17:10 : Gatus 70/70, 11 cibles en panne toutes `planned`, 76 règles `ok` dont CrowdSec/Traefik de #436, 0 alerte. Gatus 68/68 et 11 cibles Prometheus `up=0` au dernier relevé du 21/11 (10 `planned`, 1 Keycloak volontairement arrêté). Reste : charger et recetter sondes/règles Traefik-CrowdSec de #436, `app.query`, fraîcheur, provenance, `entityRef`/`catalogRevision`, cible Keycloak ; CTEM Amass local/externe et confrontation WAN sous approbation, sans classement `DOWN` pour `DENIED`/`NOT_RUN` — [Sondes](runbooks/2026-11-04-probe-remediation.md), [CTEM](runbooks/ctem-external-exposure.md) |
| H06 | P0 | fastapi-sample | CODED | NOT_VERIFIED | Cloud/OWNER : recette navigateur sur SHA déployé, budget CPU/RAM/réplicas FastAPI Cloud avant/après, pas de réveil public — [Roadmap FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) |
| H07 | P1 | nabla-compose | CODED | NOT_VERIFIED | **Suspendu depuis le 18/11** : Netgate 1100 retiré, aucun remplaçant commandé, Freebox en routeur et R7000 en routeur du LAN derrière elle. pfSense 26.03.1 → 26.07 : PR #362 fusionnée (préparation seulement), prévoir, sauvegarde chiffrée, inventaire paquets dont REST API et contrôle après reboot — [Écarts pfSense ouverts](pfsense/roadmap.md#h07--pfsense--écarts-à-contrôler-ouverts-non-réceptionnés) ; [PR #362](https://github.com/AlbanAndrieu/nabla-compose/pull/362) ; [ADR ownership](adr/0003-repository-ownership-and-diagnostics.md), éventuelle extraction pfSense NON APPLIQUÉE |
| H08 | P2 | nabla-compose | PARTIAL | NOT_VERIFIED | **Non urgent par arbitrage du 22/11** : Nexus [#438](https://github.com/AlbanAndrieu/nabla-compose/pull/438), Joplin, autres Apps. NetBox était `RUNNING` le 21/11. **Dependency-Track sort de ce lot** et appartient désormais au suivi sécurité H13, sans changer son identité technique — [Apps](runbooks/2026-11-06-catalog-apps-to-compose.md) |
| H09 | P1 | nabla-compose | PARTIAL | PARTIAL | 21/11 : côté serveur, `pg_hba` n'accepte que `hostssl` + `scram-sha-256` depuis le réseau, `ssl_min_protocol_version` TLSv1.3, et les 8 clients connectés (defectdojo, fastapisample, jobs/plumber, langfuse, litellm, postgres_exporter, scanopy, sentry) sont en TLSv1.3 ; la validation CA/SAN côté client et la rotation restent à prouver. PostgreSQL : étendre verify-full aux clients restants, vérifier SAN et CA puis démontrer la rotation — [TLS 1.3 et FIPS](security/postgresql-fips-tls13-vault-oauth-20261110.md) |
| H10 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | TrueNAS 27 RC readiness 8/8 et CSI acceptés le 21/11 ; MCP `truenas-readonly` réparé le 22/11 (00f0bc7c) ; restent portracker, 2FA, préparation finale 27 et sortie de `auth.login_with_api_key` avant TrueNAS 28 ; performance IO nocturne (snapshots 04h), ZFS et restauration hors NAS à attribuer/valider ; migration Paperless seulement avec export et rollback approuvés — [Outils TrueNAS](truenas-operator-tools.md), [Restauration](homelab-reboot-runbook.md) |
| H11 | P1 | nabla-compose + nabla-openclaw + ansible-workstation | CODED | NOT_VERIFIED | Refactorisation D0–D4 et quality gates sur SHA exact, sans doubler les scripts déportés. **#437** pin OpenClaw `fe43cc3` en PR : devbox cinq dépôts + passes de roadmap quotidiennes 01–05 **NOT_DEPLOYED**. Après merge : `submodule update`, recette egress Squid, autorisations App GitHub minimales, une PR existante par dépôt, rebase et gate avant push, métriques tokens/FinOps, aucune fusion auto ; 41 scripts OpenClaw historiquement résiduels à auditer — [Inventaire ownership](runbooks/operator-script-ownership-inventory.md), [Boucle 21/11](runbooks/2026-11-21-roadmap-loop-state.md) |
| H12 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | OpenRAG/Docling/LiteLLM : accepter corpus privé, embeddings via workstation et clés applicatives LiteLLM ; éviter clé maître — [Runbook OpenRAG](runbooks/openrag-babou-ingestion-diagnostics.md) |
| H13 | P0 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | 22/11 : `rollout --check dependency-track` BLOCKED sur `DT_DATASOURCE_PASSWORD` absent du secret runtime (rendu depuis Vaultwarden verrouillé, V1). **Priorité décidée 22/11 : Dependency-Track + CTEM**. Préflight sécurité des deux conteneurs D-Track et DB PostgreSQL, API/SBOM CycloneDX privé, métriques et statut, puis Amass LAN/externe sous autorisation, OASM, Cartography, Prowler et DefectDojo (findings vérifiés, RBAC asynchrone, déduplication). Code sans réception runtime tant que les smokes ne sont pas exécutés — [CTEM](runbooks/ctem-external-exposure.md), [Dependency-Track](runbooks/ctem-dependency-track-acceptance.md) |
| H14 | P1 | fastapi-sample + nabla-compose | CODED | NOT_VERIFIED | Inventaire Grafana/Prometheus et métriques ZFS/CPU/RAM à recetter ; **question ouverte F07a** : TrueNAS 27 ne fournit pas de série netdata par App ; comparer abonnement `app.stats` (niveau App) à cAdvisor allégé, sans cardinalité excessive ni faux zéro. OTLP FastAPI/LiteLLM vers Alloy + Tempo à prouver — [Roadmap FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) |
| H15 | P2 | nabla-compose | CODED | NOT_VERIFIED | Média : tests de non-exposition et de kill-switch avant activation de la pile VPN et des Apps planned — [Architecture média](arr-media-library-roadmap.md) |
| H16 | P1 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | PKI Vault et OAuth PostgreSQL, OIDC Keycloak/FastAPI : pilote séparé avec break-glass, révocation et RBAC négatif ; pilote P0 Entra Free IaC + CI OIDC CODED, state HCP Free isolé et plan/apply NOT_RUN, ZITADEL optionnel, SPIRE planifié sur Talos (non déployé)  ; CI Harden-Runner audit et signature YubiKey CODED, PostgreSQL `pg` POC privé NOT_RUN — [Lab Entra](security/entra-id-homelab-lab.md), [Roadmap sécurité PG](security/postgresql-fips-tls13-vault-oauth-20261110.md) |
| H17 | P0 | nabla-compose + fastapi-sample + nabla-site-alban | PARTIAL | NOT_VERIFIED | 22/11 16:16Z : Sample TrueNAS lit la `catalogRevision` de `master` 6ae78b89, `sentry-edge` `in_sync`, 0 `binding_conflict` (recette Compose/Sample faite ; reste le Site). **Priorité 1.** Source Sentry edge corrigée en `appId: sentry` pour éviter les collisions entre conteneurs `nginx` de plusieurs Apps, test auteur + projection V2 ; régénération du catalogue, parité `composeProfiles`, `entityRef`/`catalogRevision` et suppression des lecteurs V1 **après** recette Compose/Sample/Site sur SHAs déployés. Les PRs #365/#424/#432/#452/#301/#336 sont fusionnées ; le code n'atteste pas la réception runtime — [Cutover V2](service-catalog-v2-normalization.md), [Recette H17](runbooks/h17-catalog-runtime-acceptance.md) |
| H18 | P1 | nabla-compose | PLANNED | NOT_VERIFIED | 22/11 : seul dongle Sonoff Zigbee (pas d'EnOcean USB300), ZHA sur `/dev/ttyUSB0` ; le Compose H19 le mappe désormais par `by-id`. **Étude active (22/11), sans dépendance bloquante à H19** : inventorier radio Flexom EnOcean vs Zigbee (clé actuelle Sonoff Zigbee), modèle io/RTS et centrale Somfy Protect ; diagnostics USB et Overkiz en lecture seule ; décider clé USB300/ESP3 ou passerelle locale seulement après vérification des appareils et essai sécurisé — [Étude HA](roadmap-homeassistant-integrations.md) |
| H19 | P1 | nabla-compose | CODED | NOT_VERIFIED | Home Assistant natif → Compose/recorder PostgreSQL : `--check` 21/11 bloqué par fichier secret absent, rôle DB non prêt et `trusted_proxies` vide. Export, rollback et migration unitaire sans perte de données — [Runbook Apps](runbooks/2026-11-06-catalog-apps-to-compose.md) |
| H20 | P1 | fastapi-sample + nabla-compose + nabla-openclaw | PARTIAL | NOT_VERIFIED | Contrôle GitHub F15/F18 en `pending` privé, signatures/approbations YubiKey, outbox PostgreSQL ; dissocier droits de gouvernance de `fastapi-sample-release`, faire vérifier la signature HMAC des webhooks et les refus non autorisés. Devbox OpenClaw #437 sans App GitHub dédiée réellement créée selon dernier relevé ; Slack sortie seule, aucun dispatch privilégié automatique — [Convergence](runbooks/fastapi-control-plane-convergence.md), [GitHub App](github-app-control-plane.md) |
| H21 | P1 | fastapi-sample + nabla-compose | CODED | NOT_VERIFIED | FreshRSS/GReader privé + prompt Langfuse + clé LiteLLM dédiée et filtre catalogue V2 : adapters, budget, sécurité et exécution réels non vérifiés. Dépendances H03/H12/H17, aucune modification des abonnements publics — [Convergence](runbooks/fastapi-control-plane-convergence.md) |

### Traçabilité CTEM H04/H05

La [PR #436 fusionnée](https://github.com/AlbanAndrieu/nabla-compose/pull/436) contient les contrôles déclaratifs et les sondes Traefik/CrowdSec, les scripts Amass agrégés et la correction de topologie pfSense. **Fusion CODED ≠ réception WAN/AppSec**. Une campagne externe est soumise à autorisation explicite ; les candidats Amass ne deviennent jamais des vulnérabilités DefectDojo sans qualification. Voir le [runbook CTEM](runbooks/ctem-external-exposure.md) et le [runbook honeypot](../apps/honeypot/README.md) pour les recettes sans exposition non approuvée.

## Jalons déjà réceptionnés ou retirés du backlog

- **OpenClaw** : Gateway TrueNAS historiquement réceptionné les 3–5 novembre ; la **nouvelle** devbox/cadence #437 est un autre changement, non réceptionné. L'ownership du code reste `nabla-openclaw`.
- **TrueNAS/PostgreSQL** : PostgreSQL 18.6, SCRAM et serveur TLS 1.3/`hostssl` vérifiés les 12–13 novembre. Le chiffrement actif ne vaut pas `verify-full` universel : H09 reste ouvert.
- **Apps** : Scanopy, Plumber, ntopng et Bitcoind déclarés déployés les 11–12 novembre ; le déploiement de NetBox, Joplin et Dependency-Track n'en découle pas.
- **Cloudflare** : premier retrait de 26 CNAME appliqué le 10 novembre ; la preuve du dernier nom `s3.int` et des politiques exposées reste H04.
- **Scripts** : extractions `scripts/lib/postgres.sh` et `scripts/lib/app-deploy.sh` fusionnées dans #330 ; conserver les wrappers compatibles jusqu'aux tests de leur remplacement. Le runner GitHub LXC reste **préparé mais inactif**.
- **Catalogue V2** : génération Compose #365 et lecteur FastAPI #424 fusionnés le 13 novembre ; l'affichage révisé et la synchronisation du snapshot ont été fusionnés via FastAPI #432 (205 entités / 139 bindings dans le snapshot, pas de preuve de déploiement). La réception reste H17.
- **FastAPI** : heatmap triable #418 et garde budgétaire Nano #419 fusionnées le 11 novembre. Pas de mesure CPU/réplicas ni de recette OWNER post-déploiement attribuée à ces PR.

## Séquence approuvée — 14 novembre 2026

| Rang | Chantier | Premier livrable vérifiable | Gate de réception |
| --- | --- | --- | --- |
| 1 | **H01 — Talos / Kubernetes CSI** | Contrat du driver déployé et diagnostic controller/DaemonSet, test RWX/persistance/reclaim, NetworkPolicy | PVC sur plusieurs workers et reclaim ZFS prouvés sur le cluster |
| 2 | **H02 — Sauvegardes PostgreSQL** | Audit de rotation du secret, backup TLS verify-full, checksum SHA-256 et procédure de restauration isolée | Restauration comparée et cron observé, sans exposition de secrets |
| 3 | **H04 — Cloudflare / WAN** | Matrice DNS/Tunnel/Access et tests de refus /realms/master, services privés et s3.int | Tests externes négatifs, plan OpenTofu approuvé avant mutation WAN |
| 4 | **H05 — Gatus / Prometheus** | Corrélation Gatus/prometheus/app.query avec provenance et fraîcheur | Preuves indépendantes, sans faux DOWN pour DENIED/NOT_RUN |
| 5 | **H12 — OpenRAG / Docling / LiteLLM** | Smoke d'ingestion et embedding workstation via proxy TrueNAS ; clé virtuelle restreinte | Corpus privé isolé et requêtes autorisées/refusées vérifiées |
| 6 | **H13 — DefectDojo** | Test import asynchrone, RBAC minimal et déduplication | Réimport idempotent et route WAN non accessible |
| 7 | **H16 — Vault PKI / OAuth / OIDC** | Pilote de certificats/identité séparé avec matrice des accès | Break-glass, révocation et RBAC négatif exercés |

**Conduite** : commencer les préparations de PR dès disponibilité du checkout ; séquencer les migrations runtime dans cet ordre. Reprendre une PR existante seulement si son périmètre correspond. Toujours relever SHA, quality gate locale, dépendances et test négatif. Sans accès LAN, marquer `NOT_VERIFIED` plutôt que `ACCEPTED`.

**Hors séquence** : H03/H06/H07/H08/H09/H10/H11/H14/H15/H17/H18/H19 restent au portefeuille. Les risques bloquants de secrets, H09 TLS ou H17 identités catalogue sont traités comme dépendances nécessaires sans changer l'ordre approuvé.

## Dette de code / H11 — revue ciblée au 14 novembre 2026

La [mesure inter-dépôts des hotspots](code-hotspots.md) met en évidence
`scripts/truenas/` (1,49 Mo), `scripts/pfsense/` (209 Ko) et
`scripts/nabla_ops/catalog_v2.py` (1 073 lignes) côté infrastructure,
puis `nabla/api/` (1,63 Mo), dont les contrôleurs JS de sondes,
côté FastAPI. **Ce sont des volumes, pas des diagnostics de défaut.**

- Après H02/H01/H05, isoler en **H11** les primitives read-only TrueNAS et les
  contrôles de récupération pfSense, en conservant exit codes et tests de refus.
- Dans **H05/F03+F09**, traiter en premier les bugs de fraîcheur/provenance des
  sondes ; la simplification UI ne justifie pas de nouveau polling Cloud.
- Dans **H17/F11**, éviter de dupliquer l'inventaire V2 ; réceptionner les
  contrats `entityRef`/`catalogRevision` avant tout retrait legacy.
- Mesurer en workstation via `just code-hotspots`, ou dans Codex avec un
  checkout via `python3 scripts/quality/code-hotspots.py --json`.
  **Pas de LAN requis** et pas de promotion automatique de `CODED` à
  `ACCEPTED`.

## Contrat de maintenance et d'archivage

- Après chaque PR, **séparer livraison code, contrôle local et réception runtime** avec SHA, date, cible et commande.
- Déplacer les récits d'incidents vers `docs/incidents/`, les procédures durables vers `docs/runbooks/`, les choix d'architecture vers `docs/adr/` ou `docs/security/`.
- Lorsqu'un item est reçu et n'a plus de suite, le retirer du backlog arbitrable et le résumer en jalon ci-dessus ; Git garde la chronologie, sans copier des runbooks dans plusieurs dépôts.
- Vérifier cet index sans réseau ni secrets : `python3 scripts/quality/check-roadmap-portfolio.py --check` (ou `--json` pour automatiser l'affichage).

### H17 — 19 novembre 2026 : projection opérateur

La projection générée `catalog/generated/operator-inventory.json` relie la révision Backstage v2 au graphe natif (révision `operatorRevision` indépendante), conserve les réseaux, dépendances, phases de démarrage et les 139 correspondances Compose explicites. Les lecteurs de démarrage, arrêt, restauration, redéploiement et audit TrueNAS utilisent cette projection ; la recette des plans avant/après et la réception runtime restent NOT_RUN. Les anciens exports sont conservés temporairement exclusivement pour parité, anciennes versions FastAPI et rollback. Owner : H17 Compose ; supprimer les exports après preuve de parité, déploiement FastAPI et recherche de lecteurs résiduels. Aucun changement TrueNAS ni Cloudflare appliqué.
