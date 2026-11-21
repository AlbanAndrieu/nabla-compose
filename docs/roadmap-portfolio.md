# Portefeuille Homelab — arbitrage inter-dépôts

> Synthèse réconciliée le **21 novembre 2026** (doublons et éléments terminés retirés), établie à partir des deux roadmaps versionnées. **Ordre approuvé le 14 novembre : H01 → H02 → H04 → H05 → H12 → H13 → H16 ; autres chantiers conservés au backlog.** Ce tableau est un index de décisions : il ne remplace ni les procédures ni les mesures runtime.

## Autorités et règles

- **Infrastructure** : [roadmap nabla-compose](roadmap.md), source pour TrueNAS, Talos, CSI, pfSense, Cloudflare, sauvegardes et secrets.
- **Application/sondes/UI** : [engineering-roadmap fastapi-sample](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md), source pour FastAPI Cloud, OWNER, caches, qualité et rendu.
- **OpenClaw et clés matérielles** : [nabla-openclaw](https://github.com/AlbanAndrieu/nabla-openclaw) et [nabla-yubikey](https://github.com/AlbanAndrieu/nabla-yubikey) gardent leurs propres roadmaps. Ne pas recréer leur backlog ici.
- **CODED**, **TESTED**, **DEPLOYED** et **ACCEPTED (runtime)** ne sont jamais interchangeables. `NOT_VERIFIED` : aucune nouvelle preuve de réception datée. `PARTIAL` : plusieurs éléments, mais pas de réception bout-en-bout. Aucun statut inféré d'un simple merge.
- Les indisponibilités réversibles sont acceptées dans ce homelab ; une perte de données, une exposition WAN ou une mutation de clé matérielle réclame une approbation explicite.

## Backlog arbitrable

| ID | Priorité | Propriétaire | Code/préparation | Réception runtime | Preuve à produire et référence |
| --- | --- | --- | --- | --- | --- |
| H01 | P0 | nabla-compose | DEPLOYED | ACCEPTED | 21/11 : gate de la séquence atteinte sur le cluster : `smoke-truenas-csi-nfs.sh --apply` sur TrueNAS 27 RC (PVC liée, écriture taloswk01, lecture taloswk02, PV, dataset, partage NFS et ressource ZFS récupérés) et NetworkPolicy appliquée par Cilium (smoke B1) ; `truenas-csi` v1.0.3, Falco **DEPLOYED** (3/3, 0.44.1). Suites : Keycloak/Hermes/Vault sur Talos (secrets, Vaultwarden verrouillé), sortie de `auth.login_with_api_key` (H10), SPIRE P2 **PLANNED** (H16) — [Platform tools](kubernetes-platform-tools.md), [Préflight CSI](kubernetes-csi-preflight.md) |
| H02 | P0 | nabla-compose | DEPLOYED | PARTIAL | 21/11 : sauvegarde TLS verify-full, restauration isolée vérifiée et cron quotidien DEPLOYED ; reste la rotation de `postgres_exporter` (Vaultwarden verrouillé) — [Runbook G1](runbooks/postgres-g1-restore-and-secret-rotation.md) |
| H03 | P0 | nabla-compose | PARTIAL | NOT_VERIFIED | Secrets : finir les matérialisations 0600, corriger la clé Homarr sans afficher de valeur, contrôler fichier → conteneur — [Backlog des secrets](runbooks/2026-11-10-secrets-migration-backlog.md) |
| H04 | P0 | nabla-compose | PARTIAL | NOT_VERIFIED | Edge : prouver les politiques Access/Service Auth, garder s3.int public, publié par `cloudflare-ddns` (décision du 20/11), vérifier le DNS FastAPI public ; F17 Traefik/CrowdSec AppSec canary CODED (2 collections, acquisition 7422, middleware fail-closed), rateLimit Traefik, inventaire WAF Cloudflare read-only CODED, adoption import-first et preuves négatives avant bascule ; honeypot public sur `login` (décision du 20/11) : App DEPLOYED le 21/11, route Tunnel et Access bypass CODED, apply après le retrait du A mort (Vaultwarden verrouillé) ; API d'administration Traefik authentifiée et métriques séparées sur :8082 CODED (#432) — [IaC Cloudflare](../terraform/cloudflare/README.md) |
| H05 | P0 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | Catalogue : réconcilier Gatus, Prometheus, exports et app.query avec preuves fraîches, sans DOWN sur DENIED ou NOT_RUN ; 21/11 : Gatus 68/68, 11 cibles Prometheus DOWN (10 exporters `planned` et `keycloak`, App arrêtée faute de secrets), Sample : un seul `binding_conflict` (`sentry-edge`) ; CTEM : rapprochement Amass/V2 et conflits LAN-only à accepter — [Sondes TrueNAS](runbooks/2026-11-04-probe-remediation.md) |
| H06 | P0 | fastapi-sample | CODED | NOT_VERIFIED | Cloud/OWNER : recette navigateur sur SHA déployé, budget CPU/RAM/réplicas FastAPI Cloud avant/après, pas de réveil public — [Roadmap FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) |
| H07 | P1 | nabla-compose | CODED | NOT_VERIFIED | **Suspendu depuis le 18/11** : Netgate 1100 retiré, aucun remplaçant commandé, Freebox en routeur et R7000 en routeur du LAN derrière elle. pfSense 26.03.1 → 26.07 : PR #362 fusionnée (préparation seulement), prévoir, sauvegarde chiffrée, inventaire paquets dont REST API et contrôle après reboot — [Écarts pfSense ouverts](pfsense/roadmap.md#h07--pfsense--écarts-à-contrôler-ouverts-non-réceptionnés) ; [PR #362](https://github.com/AlbanAndrieu/nabla-compose/pull/362) ; [ADR ownership](adr/0003-repository-ownership-and-diagnostics.md), éventuelle extraction pfSense NON APPLIQUÉE |
| H08 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | NetBox DEPLOYED (constaté le 21/11 : App `RUNNING`, statut `active`) ; déployer Dependency-Track puis Joplin un par un ; vérifier authentification, Gatus et exporters avant état active — [Déploiements Apps](runbooks/2026-11-06-catalog-apps-to-compose.md) |
| H09 | P1 | nabla-compose | PARTIAL | PARTIAL | 21/11 : côté serveur, `pg_hba` n'accepte que `hostssl` + `scram-sha-256` depuis le réseau, `ssl_min_protocol_version` TLSv1.3, et les 8 clients connectés (defectdojo, fastapisample, jobs/plumber, langfuse, litellm, postgres_exporter, scanopy, sentry) sont en TLSv1.3 ; la validation CA/SAN côté client et la rotation restent à prouver. PostgreSQL : étendre verify-full aux clients restants, vérifier SAN et CA puis démontrer la rotation — [TLS 1.3 et FIPS](security/postgresql-fips-tls13-vault-oauth-20261110.md) |
| H10 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | TrueNAS 27 RC : readiness stricte 8/8 et provision/reclaim CSI prouvés le 21/11 ; restent MCP `truenas-readonly`, portracker et 2FA, puis remplacer auth.login_with_api_key avant TrueNAS 28 — [Couplage upgrades](truenas-operator-tools.md) |
| H11 | P1 | nabla-compose + fastapi-sample | CODED | NOT_VERIFIED | Fiabilité scripts : réception des wrappers partagés, diagnostics expurgés, quality gates L1/L2/L3 au HEAD exact, suppression contrôlée des doublons — [Registre de risque](runbooks/homelab-refactoring-risk-register.md) ; [hotspots mesurés](code-hotspots.md) (tests/TrueNAS/pfSense/catalogue/sondes/UI) ; découper par contrat, pas par taille — PR [#384](https://github.com/AlbanAndrieu/nabla-compose/pull/384) : vérifier en workstation les tests L1/L2/L3, la séquence TrueNAS → FastAPI Cloud /sickz et l'association des résultats Cloud aux services (identifiant non garanti dans /sickz). ; revue d'extraction Workstation/OpenClaw/pfSense et diagnostic : [ADR frontières](adr/0003-repository-ownership-and-diagnostics.md), [audit redondance](diagnostics-duplication-audit.md) — migration non commencée ; inventaire comparatif OpenClaw read-only : `python3 scripts/ops/plan-repository-split.py --openclaw-overlap-root ../nabla-openclaw` (égalité binaire ≠ parité fonctionnelle, aucun retrait autorisé) ; [inventaire opérateur D0–D4](runbooks/operator-script-ownership-inventory.md) — proposé, aucune migration réalisée |
| H12 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | OpenRAG/Docling/LiteLLM : accepter corpus privé, embeddings via workstation et clés applicatives LiteLLM ; éviter clé maître — [Runbook OpenRAG](runbooks/openrag-babou-ingestion-diagnostics.md) |
| H13 | P1 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | DefectDojo : compte d'import à droits restreints, suivi asynchrone, déduplication, preuve de non-exposition WAN — [Import privé](defectdojo-private-scan-ingestion.md) |
| H14 | P1 | fastapi-sample | CODED | NOT_VERIFIED | Tableaux de bord : inventaire Prometheus/Grafana écrit le 21/11 (fastapi-sample #452, `dashboard-coverage-inventory.md`) : aucun cAdvisor (désactivé exprès), heatmap F07 en `telemetry_unavailable` ; choisir la source des ressources par App (netdata TrueNAS ou cAdvisor allégé), ZFS par `node_filesystem_*`, flux pfSense sans objet depuis le 18/11 — [Roadmap FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) |
| H15 | P2 | nabla-compose | CODED | NOT_VERIFIED | Média : tests de non-exposition et de kill-switch avant activation de la pile VPN et des Apps planned — [Architecture média](arr-media-library-roadmap.md) |
| H16 | P1 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | PKI Vault et OAuth PostgreSQL, OIDC Keycloak/FastAPI : pilote séparé avec break-glass, révocation et RBAC négatif ; pilote P0 Entra Free IaC + CI OIDC CODED, state HCP Free isolé et plan/apply NOT_RUN, ZITADEL optionnel, SPIRE planifié sur Talos (non déployé)  ; CI Harden-Runner audit et signature YubiKey CODED, PostgreSQL `pg` POC privé NOT_RUN — [Lab Entra](security/entra-id-homelab-lab.md), [Roadmap sécurité PG](security/postgresql-fips-tls13-vault-oauth-20261110.md) |
| H17 | P0 | nabla-compose + fastapi-sample + nabla-site-alban | PARTIAL | NOT_VERIFIED | Backstage V2 : Compose [#365](https://github.com/AlbanAndrieu/nabla-compose/pull/365) et FastAPI [#424](https://github.com/AlbanAndrieu/fastapi-sample/pull/424) fusionnées ; [FastAPI #432](https://github.com/AlbanAndrieu/fastapi-sample/pull/432) fusionnée (snapshot V2 et cartes enrichies, **non réceptionnés au runtime**). Parité entityRef/catalogRevision sur SHA déployé, puis migration Site Alban avant suppression legacy ; 21/11 : `composeProfiles` dans `entities.json` CODED (état `on_demand` côté Sample, fastapi-sample#452), garde Site sans lecteur V1/legacy (nabla-site-alban#336) — [Contrat V2](service-catalog-v2-normalization.md) |
| H18 | P2 | nabla-compose | PLANNED | NOT_VERIFIED | EnOcean NodOn et Somfy io/RTS dans Home Assistant : étude de compatibilité, dongle/Overkiz, tests avant achat/appairage — [Étude HA](roadmap-homeassistant-integrations.md) |
| H19 | P1 | nabla-compose | CODED | NOT_VERIFIED | Home Assistant : migration de l'App native vers Compose et recorder PostgreSQL avec rollback et validation des intégrations — [Runbook Apps](runbooks/2026-11-06-catalog-apps-to-compose.md) |
| H20 | P1 | fastapi-sample + nabla-compose + nabla-openclaw | PARTIAL | NOT_VERIFIED | F15/F18 control plane GitHub et approbations YubiKey, pending-only PostgreSQL, cache Redis, outbox et Slack existant ; H04/H02/H16 avant write/dispatch. [Convergence](runbooks/fastapi-control-plane-convergence.md) |
| H21 | P1 | fastapi-sample + nabla-compose | CODED | NOT_VERIFIED | F16 FreshRSS privé + catalogue V2 + Langfuse + LiteLLM TrueNAS ; tests contractuels pytest, publication et adapters à faire après H17/H12/H03. [Convergence](runbooks/fastapi-control-plane-convergence.md) |

## Jalons déjà réceptionnés ou retirés du backlog

- **OpenClaw** : Gateway TrueNAS et intégration principale acceptées historiquement les 3–5 novembre ; propriété transférée à `nabla-openclaw`. Une modification future exige une nouvelle preuve, pas une réouverture de la migration.
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
