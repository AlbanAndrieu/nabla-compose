# Portefeuille Homelab — arbitrage inter-dépôts

> Réconciliation documentaire du **22 novembre 2026** : toutes les lignes H01–H21 restent visibles, sans relancer les travaux déjà réceptionnés. **La séquence approuvée le 14/11 reste une décision historique : H01 → H02 → H04 → H05 → H12 → H13 → H16.** Les gates CSI/NetworkPolicy (H01) et sauvegarde/restauration (H02) sont atteints selon les constats du 21/11 : le **point d'entrée opérationnel actuel est H04/H05**, sous réserve des dépendances de secrets H03. Une proposition d'ordre figure ci-dessous, à valider par l'opérateur.

## Autorités et règles

- **Infrastructure** : [roadmap nabla-compose](roadmap.md), source pour TrueNAS, Talos, CSI, pfSense, Cloudflare, sauvegardes et secrets.
- **Application/sondes/UI** : [engineering-roadmap fastapi-sample](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md), source pour FastAPI Cloud, OWNER, caches, qualité et rendu.
- **OpenClaw et clés matérielles** : [nabla-openclaw](https://github.com/AlbanAndrieu/nabla-openclaw) et [nabla-yubikey](https://github.com/AlbanAndrieu/nabla-yubikey) gardent leurs propres roadmaps. Ne pas recréer leur backlog ici.
- **CODED**, **TESTED**, **DEPLOYED** et **ACCEPTED (runtime)** ne sont jamais interchangeables. `NOT_VERIFIED` : aucune nouvelle preuve de réception datée. `PARTIAL` : plusieurs éléments, mais pas de réception bout-en-bout. Aucun statut inféré d'un simple merge.
- Les indisponibilités réversibles sont acceptées dans ce homelab ; une perte de données, une exposition WAN ou une mutation de clé matérielle réclame une approbation explicite.

## Arbitrage proposé — à valider (22 novembre 2026)

**La colonne « rang proposé » n'est pas une nouvelle décision approuvée.**
Effort indicatif : **S** = petite réception/configuration, **M** = plusieurs smokes / intégrations, **L** = migration ou chantier interdépôts ; ce n'est pas une estimation calendaire. Toutes les étapes runtime nécessitent des preuves sur la version réellement déployée.

| Rang proposé | Chantier et statut | Action concrète non terminée | Dépendance / décision | Gate de clôture | Effort |
| --- | --- | --- | --- | --- | --- |
| 0 | **H03 — Secrets** (pré-requis transversal) | Fournir les seuls secrets manquants Keycloak/Joplin/Homarr, prouver l'identité fichier 0600 → conteneur ; ne **pas** redéployer Vaultwarden 1.37.5 déjà réceptionné le 21/11 | Session Vaultwarden autorisée, séparation admin/service | Tests négatifs sans secret, aucune valeur dans logs | M |
| 1 | **H04 — Frontière WAN, honeypot, CrowdSec** (#436 fusionnée) | Inventorier DNS/Tunnel/Access, appliquer **seulement après plan revu** le CNAME `login` et le canary via Traefik, tester IP d'origine, 403 AppSec, 429 ; traiter la politique mail et WAF Vercel séparément | État Garage/Cloudflare + fenêtre d'essai ; pas de NAT implicite ; `s3.int` exception assumée | Matrice DNS/Tunnel/Access, refus extérieurs indépendants, rollback direct disponible | L |
| 2 | **H05 — Gatus/Prometheus/CTEM** | Recharger règles Traefik/CrowdSec et sondes Gatus ; contrôler `up`/LAPI/AppSec, qualifier la cible Keycloak et les exporters `planned`, exécuter Amass LAN vs externe sous approbation | H04 pour preuve WAN ; H03 pour Keycloak | Horodatage/source, 200 Hello + honeypot `/healthz`, aucun faux `DOWN` | M |
| 3 | **H17 — Catalogue Backstage V2** | Réceptionner `entityRef`/`catalogRevision` et `composeProfiles` sur TrueNAS, Sample et site ; résoudre `sentry-edge`, puis auditer les derniers lecteurs V1 | H05 + SHA déployés ; pas de suppression legacy prématurée | Même révision et provenance sur les 3 lecteurs, zéro identité ambiguë | M |
| 4 | **H08/H04 — Nexus privé + CI** ([#438](https://github.com/AlbanAndrieu/nabla-compose/pull/438)) | Réceptionner `nexus.int` (APT security/npm/pip/uv), routage public CI via Access et Traefik, import-first des 35 ressources prévues | Revue des realms admin et route Tunnel avant apply ; une instance Nexus | Tests package cache LAN, Maven CI et refus sans identité | M |
| 5 | **H11/H20 — Coder OpenClaw** ([#437](https://github.com/AlbanAndrieu/nabla-compose/pull/437)) | Après fusion : sous-module `fe43cc3`, devbox et cinq dépôts, sorties des passes quotidiennes 01–05, collision de PR, coût tokens/FinOps | App GitHub de devbox à privilèges minimaux ; aucune mutation autonome de secrets, WAN ou `master` | Rebase/quality gate de PR existante, aucun doublon ni merge automatique | M |
| 6 | **H09 — Clients PostgreSQL TLS** | Généraliser `verify-full`, CA/SAN et rotation progressive client par client | H03, sauvegarde H02 déjà réceptionnée | Tests connectivité + refus certificat invalide et restauration inchangée | M |
| 7 | **H12 — OpenRAG/Docling/LiteLLM** | Activer `qwen-cpu` de secours et clé virtuelle dédiée ; smoke ingestion privée/embeddings GPU workstation et bascule hors ligne | H03, ressources CPU/RAM, disponibilité de la workstation | Réponse avec clé, refus sans clé, absence de fuite de corpus | L |
| 8 | **H13 — DefectDojo/CTEM** | Import privé de *findings qualifiés* (pas des candidats Amass), RBAC d'importeur, statut async, réimport idempotent | H05, H09 et identités H03 | Dédoublonnage, rejets non autorisés, absence de route WAN | M |
| 9 | **H06/H14 — FastAPI Cloud et observabilité** | Vérifier budget CPU/réplicas, fraîcheur OWNER, séries par App (`app.stats` vs cAdvisor allégé), OTLP, ZFS | H05/H17, arbitrer source per-App sans cardinalité nouvelle | Comparaison télémétrie avant/après + indicateur `unavailable` si absent | M |
| 10 | **H08/H19 — Apps à activer** | Keycloak/Hermes, Dependency-Track, Joplin ; Home Assistant vers Compose/recorder PostgreSQL un service à la fois | H03, H09, rollback HA et données personnelles | Auth, datastore, logs expurgés, réversibilité prouvée | L |
| 11 | **H16/H20 — IAM et contrôle GitHub** | Séparer App de gouvernance de l'App de release ; pilote PKI/OIDC/Entra, approbation YubiKey, webhook signé | H03/H04/H09 ; aucune permission Graph étendue implicite | Révocation, break-glass, HMAC négatif, RBAC et audit | L |
| 12 | **H21 — Veille FreshRSS** | GReader privé + Langfuse prompt + LiteLLM virtuel + catalogue V2 et filtre pertinent | H03/H12/H17 | Sources isolées, coût borné, pas de modification des flux publics | M |
| 13 | **H10/H11 — Performance / opérateur** | Préciser pic IO ZFS de 04h, découpler proxy Docker Socket, vérifier TrueNAS 27 final et migration API avant 28 | Laisser preuves H01/H02 acquises ; capture sans redémarrage destructif | Mesure IO attribuée, snapshots restaurables, contrôles d'accès conservés | M |
| Différé | **H07/H15/H18** | pfSense retiré, pile média VPN, EnOcean/Somfy : étude seulement | Choix de matériel et périmètre ultérieur | Aucune exposition ou migration implicite | L |

**Arbitrage demandé :** choisir les **3 à 5 rangs** à lancer, avec indication des fenêtres de mutation Cloudflare/TrueNAS. Les rangs sont **proposés**, les P0/P1/P2 du tableau canonique restent inchangés avant décision. Les preuves de [la passe du 21/11](runbooks/2026-11-21-roadmap-loop-state.md) sont datées, non une télémétrie temps réel.

## Backlog arbitrable

| ID | Priorité | Propriétaire | Code/préparation | Réception runtime | Preuve à produire et référence |
| --- | --- | --- | --- | --- | --- |
| H01 | P0 | nabla-compose | DEPLOYED | PARTIAL | **GATE CSI ATTEINTE le 21/11** : NFS RWX multi-workers, reclaim ZFS et NetworkPolicy Cilium vérifiés ; Falco 3/3. Ne pas refaire la migration CSI. Le déploiement Keycloak/Hermes relève de H03/H08/H16, API TrueNAS de H10 et SPIRE du pilote H16 — [Préflight CSI](kubernetes-csi-preflight.md) |
| H02 | P0 | nabla-compose | DEPLOYED | PARTIAL | **GATE sauvegarde ATTEINTE le 21/11** : 9 bases, cron quotidien, trois restaurations isolées et TLS verify-full vérifiés. Reliquat précis : rotation privée de l'identité `postgres_exporter` après recette H03 ; ne pas relancer la migration backup — [Runbook G1](runbooks/postgres-g1-restore-and-secret-rotation.md) |
| H03 | P0 | nabla-compose | PARTIAL | NOT_VERIFIED | Vaultwarden **1.37.5 déjà déployé et healthy** le 21/11, `bitwarden-api` revenu healthy après suppression des anciens overrides Pi-hole ; `talosconfig`/kubeconfig placés en pièces jointes privées. Restent la matérialisation 0600 des secrets Keycloak, Joplin, Homarr, autres Apps et la rotation `postgres_exporter`, puis tests fichier→conteneur et refus sans clé — [Backlog secrets](runbooks/2026-11-10-secrets-migration-backlog.md) |
| H04 | P0 | nabla-compose | PARTIAL | NOT_VERIFIED | **#436 fusionnée le 22/11 (CODED)** : Traefik/CrowdSec AppSec, honeypot `login` sans credentials, Gatus/Prometheus et correction du graphe pfSense retiré ; Hello HTTPS/SNI + réseau Docker observés depuis le LAN, **pas de preuve WAN**. CNAME `login`, Access bypass ciblé, SNI réel, client IP, 403, rate limit, tests négatifs DNS et `/realms/master` restent à réceptionner. Cloudflare import-first via état Garage, `s3.int` exception publique explicite. Revoir séparément politique mail des 20 zones et WAF Vercel Bababou (#433), tous deux non appliqués selon dernier relevé — [Honeypot](../apps/honeypot/README.md), [Cloudflare](../terraform/cloudflare/README.md) |
| H05 | P0 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | Gatus 68/68 et 11 cibles Prometheus `up=0` au dernier relevé du 21/11 (10 `planned`, 1 Keycloak volontairement arrêté). Reste : charger et recetter sondes/règles Traefik-CrowdSec de #436, `app.query`, fraîcheur, provenance, `entityRef`/`catalogRevision`, cible Keycloak ; CTEM Amass local/externe et confrontation WAN sous approbation, sans classement `DOWN` pour `DENIED`/`NOT_RUN` — [Sondes](runbooks/2026-11-04-probe-remediation.md), [CTEM](runbooks/ctem-external-exposure.md) |
| H06 | P0 | fastapi-sample | CODED | NOT_VERIFIED | Cloud/OWNER : recette navigateur sur SHA déployé, budget CPU/RAM/réplicas FastAPI Cloud avant/après, pas de réveil public — [Roadmap FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) |
| H07 | P1 | nabla-compose | CODED | NOT_VERIFIED | **Suspendu depuis le 18/11** : Netgate 1100 retiré, aucun remplaçant commandé, Freebox en routeur et R7000 en routeur du LAN derrière elle. pfSense 26.03.1 → 26.07 : PR #362 fusionnée (préparation seulement), prévoir, sauvegarde chiffrée, inventaire paquets dont REST API et contrôle après reboot — [Écarts pfSense ouverts](pfsense/roadmap.md#h07--pfsense--écarts-à-contrôler-ouverts-non-réceptionnés) ; [PR #362](https://github.com/AlbanAndrieu/nabla-compose/pull/362) ; [ADR ownership](adr/0003-repository-ownership-and-diagnostics.md), éventuelle extraction pfSense NON APPLIQUÉE |
| H08 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | NetBox `RUNNING` constaté le 21/11 ; Dependency-Track puis Joplin encore à démarrer (H03 secrets). **Nexus [#438](https://github.com/AlbanAndrieu/nabla-compose/pull/438) en PR**, proxy APT security et Nexus privé LAN via Traefik, CI publique via Access ; aucun plan/apply Nexus, bascule Tunnel ni build CI Maven attesté. À réceptionner après merge : realms, 35 ressources, caches client, tests d'accès et rollback — [Déploiements Apps](runbooks/2026-11-06-catalog-apps-to-compose.md), [Nexus](../apps/nexus/README.md) |
| H09 | P1 | nabla-compose | PARTIAL | PARTIAL | 21/11 : côté serveur, `pg_hba` n'accepte que `hostssl` + `scram-sha-256` depuis le réseau, `ssl_min_protocol_version` TLSv1.3, et les 8 clients connectés (defectdojo, fastapisample, jobs/plumber, langfuse, litellm, postgres_exporter, scanopy, sentry) sont en TLSv1.3 ; la validation CA/SAN côté client et la rotation restent à prouver. PostgreSQL : étendre verify-full aux clients restants, vérifier SAN et CA puis démontrer la rotation — [TLS 1.3 et FIPS](security/postgresql-fips-tls13-vault-oauth-20261110.md) |
| H10 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | TrueNAS 27 RC readiness 8/8 et CSI acceptés le 21/11 ; restent MCP readonly (variables privées), portracker, 2FA, préparation finale 27 et sortie de `auth.login_with_api_key` avant TrueNAS 28 ; performance IO nocturne (snapshots 04h), ZFS et restauration hors NAS à attribuer/valider ; migration Paperless seulement avec export et rollback approuvés — [Outils TrueNAS](truenas-operator-tools.md), [Restauration](homelab-reboot-runbook.md) |
| H11 | P1 | nabla-compose + nabla-openclaw + ansible-workstation | CODED | NOT_VERIFIED | Refactorisation D0–D4 et quality gates sur SHA exact, sans doubler les scripts déportés. **#437** pin OpenClaw `fe43cc3` en PR : devbox cinq dépôts + passes de roadmap quotidiennes 01–05 **NOT_DEPLOYED**. Après merge : `submodule update`, recette egress Squid, autorisations App GitHub minimales, une PR existante par dépôt, rebase et gate avant push, métriques tokens/FinOps, aucune fusion auto ; 41 scripts OpenClaw historiquement résiduels à auditer — [Inventaire ownership](runbooks/operator-script-ownership-inventory.md), [Boucle 21/11](runbooks/2026-11-21-roadmap-loop-state.md) |
| H12 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | OpenRAG/Docling/LiteLLM : accepter corpus privé, embeddings via workstation et clés applicatives LiteLLM ; éviter clé maître — [Runbook OpenRAG](runbooks/openrag-babou-ingestion-diagnostics.md) |
| H13 | P1 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | DefectDojo : compte d'import à droits restreints, suivi asynchrone, déduplication, preuve de non-exposition WAN — [Import privé](defectdojo-private-scan-ingestion.md) |
| H14 | P1 | fastapi-sample + nabla-compose | CODED | NOT_VERIFIED | Inventaire Grafana/Prometheus et métriques ZFS/CPU/RAM à recetter ; **question ouverte F07a** : TrueNAS 27 ne fournit pas de série netdata par App ; comparer abonnement `app.stats` (niveau App) à cAdvisor allégé, sans cardinalité excessive ni faux zéro. OTLP FastAPI/LiteLLM vers Alloy + Tempo à prouver — [Roadmap FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) |
| H15 | P2 | nabla-compose | CODED | NOT_VERIFIED | Média : tests de non-exposition et de kill-switch avant activation de la pile VPN et des Apps planned — [Architecture média](arr-media-library-roadmap.md) |
| H16 | P1 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | PKI Vault et OAuth PostgreSQL, OIDC Keycloak/FastAPI : pilote séparé avec break-glass, révocation et RBAC négatif ; pilote P0 Entra Free IaC + CI OIDC CODED, state HCP Free isolé et plan/apply NOT_RUN, ZITADEL optionnel, SPIRE planifié sur Talos (non déployé)  ; CI Harden-Runner audit et signature YubiKey CODED, PostgreSQL `pg` POC privé NOT_RUN — [Lab Entra](security/entra-id-homelab-lab.md), [Roadmap sécurité PG](security/postgresql-fips-tls13-vault-oauth-20261110.md) |
| H17 | P0 | nabla-compose + fastapi-sample + nabla-site-alban | PARTIAL | NOT_VERIFIED | Projection Backstage V2 et consommateurs fusionnés (#365 Compose, #424/#432 FastAPI, #301 Site) ; `composeProfiles` préparé dans `entities.json` et Sample #452 fusionné, déploiement/parité non vérifiés. Reste : `sentry-edge` ambigu, comparaison `entityRef`/`catalogRevision` sur les trois surfaces, validation OWNER et suppression des lecteurs legacy **après** preuve — [Contrat V2](service-catalog-v2-normalization.md) |
| H18 | P2 | nabla-compose | PLANNED | NOT_VERIFIED | EnOcean NodOn et Somfy io/RTS dans Home Assistant : étude de compatibilité, dongle/Overkiz, tests avant achat/appairage — [Étude HA](roadmap-homeassistant-integrations.md) |
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
