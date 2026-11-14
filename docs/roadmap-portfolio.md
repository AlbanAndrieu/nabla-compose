# Portefeuille Homelab — arbitrage inter-dépôts

> Synthèse réconciliée le **14 novembre 2026**, établie à partir des deux roadmaps versionnées. **Ordre validé : G1/H02 → H01 → H05 ; autres chantiers à arbitrer.** Ce tableau est un index de décisions : il ne remplace ni les procédures ni les mesures runtime.

## Autorités et règles

- **Infrastructure** : [roadmap nabla-compose](roadmap.md), source pour TrueNAS, Talos, CSI, pfSense, Cloudflare, sauvegardes et secrets.
- **Application/sondes/UI** : [engineering-roadmap fastapi-sample](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md), source pour FastAPI Cloud, OWNER, caches, qualité et rendu.
- **OpenClaw et clés matérielles** : [nabla-openclaw](https://github.com/AlbanAndrieu/nabla-openclaw) et [nabla-yubikey](https://github.com/AlbanAndrieu/nabla-yubikey) gardent leurs propres roadmaps. Ne pas recréer leur backlog ici.
- **CODED**, **TESTED**, **DEPLOYED** et **ACCEPTED (runtime)** ne sont jamais interchangeables. `NOT_VERIFIED` : aucune nouvelle preuve de réception datée. `PARTIAL` : plusieurs éléments, mais pas de réception bout-en-bout. Aucun statut inféré d'un simple merge.
- Les indisponibilités réversibles sont acceptées dans ce homelab ; une perte de données, une exposition WAN ou une mutation de clé matérielle réclame une approbation explicite.

## Backlog arbitrable

| ID | Priorité | Propriétaire | Code/préparation | Réception runtime | Preuve à produire et référence |
| --- | --- | --- | --- | --- | --- |
| H01 | P0 | nabla-compose | CODED | NOT_VERIFIED | CSI Talos : #367 fusionnée (diagnostic code uniquement) ; identifier le driver installé, le rapprocher du pilote officiel TrueNAS CSI déclaré, prouver RWX/persistance/reclaim et valider NetworkPolicy avant Keycloak/Hermes/Vault — [Préflight CSI](kubernetes-csi-preflight.md) |
| H02 | P0 | nabla-compose | CODED | NOT_VERIFIED | G1 : rotation postgres_exporter, sauvegarde manuelle en TLS verify-full, restauration isolée et comparaison ciblée puis seulement activer le cron — [Runbook G1](runbooks/postgres-g1-restore-and-secret-rotation.md) |
| H03 | P0 | nabla-compose | PARTIAL | NOT_VERIFIED | Secrets : finir les matérialisations 0600, corriger la clé Homarr sans afficher de valeur, contrôler fichier → conteneur — [Backlog des secrets](runbooks/2026-11-10-secrets-migration-backlog.md) |
| H04 | P0 | nabla-compose | PARTIAL | NOT_VERIFIED | Edge : prouver les politiques Access/Service Auth, retirer s3.int public après plan approuvé, vérifier le DNS FastAPI public — [IaC Cloudflare](../terraform/cloudflare/README.md) |
| H05 | P0 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | Catalogue : réconcilier Gatus, Prometheus, exports et app.query avec preuves fraîches, sans DOWN sur DENIED ou NOT_RUN — [Sondes TrueNAS](runbooks/2026-11-04-probe-remediation.md) |
| H06 | P0 | fastapi-sample | CODED | NOT_VERIFIED | Cloud/OWNER : recette navigateur sur SHA déployé, budget CPU/RAM/réplicas FastAPI Cloud avant/après, pas de réveil public — [Roadmap FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) |
| H07 | P1 | nabla-compose | CODED | NOT_VERIFIED | pfSense 26.03.1 → 26.07 : PR #362 fusionnée (préparation seulement), prévoir, sauvegarde chiffrée, inventaire paquets dont REST API et contrôle après reboot — [Écarts pfSense ouverts](roadmap.md#h07--pfsense--écarts-à-contrôler-ouverts-non-réceptionnés) ; [PR #362](https://github.com/AlbanAndrieu/nabla-compose/pull/362) |
| H08 | P1 | nabla-compose | CODED | NOT_VERIFIED | Déployer NetBox, Dependency-Track et Joplin un par un ; vérifier authentification, Gatus et exporters avant état active — [Déploiements Apps](runbooks/2026-11-06-catalog-apps-to-compose.md) |
| H09 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | PostgreSQL : étendre verify-full aux clients restants, vérifier SAN et CA puis démontrer la rotation — [TLS 1.3 et FIPS](security/postgresql-fips-tls13-vault-oauth-20261110.md) |
| H10 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | TrueNAS 27 RC : clôturer la recette post-upgrade, puis remplacer auth.login_with_api_key avant TrueNAS 28 — [Couplage upgrades](truenas-operator-tools.md) |
| H11 | P1 | nabla-compose + fastapi-sample | CODED | NOT_VERIFIED | Fiabilité scripts : réception des wrappers partagés, diagnostics expurgés, quality gates L1/L2/L3 au HEAD exact, suppression contrôlée des doublons — [Risque refactoring](runbooks/homelab-refactoring-risk-register.md) — PR [#384](https://github.com/AlbanAndrieu/nabla-compose/pull/384) : vérifier en workstation les tests L1/L2/L3, la séquence TrueNAS → FastAPI Cloud /sickz et l'association des résultats Cloud aux services (identifiant non garanti dans /sickz). |
| H12 | P1 | nabla-compose | PARTIAL | NOT_VERIFIED | OpenRAG/Docling/LiteLLM : accepter corpus privé, embeddings via workstation et clés applicatives LiteLLM ; éviter clé maître — [Runbook OpenRAG](runbooks/openrag-babou-ingestion-diagnostics.md) |
| H13 | P1 | nabla-compose + fastapi-sample | PARTIAL | NOT_VERIFIED | DefectDojo : compte d'import à droits restreints, suivi asynchrone, déduplication, preuve de non-exposition WAN — [Import privé](defectdojo-private-scan-ingestion.md) |
| H14 | P1 | fastapi-sample | CODED | NOT_VERIFIED | Tableaux de bord : confirmer la heatmap cAdvisor OWNER, la distinction 0/absent et compléter séparément ZFS/NetFlow sourcés — [Roadmap FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) |
| H15 | P2 | nabla-compose | CODED | NOT_VERIFIED | Média : tests de non-exposition et de kill-switch avant activation de la pile VPN et des Apps planned — [Architecture média](arr-media-library-roadmap.md) |
| H16 | P2 | nabla-compose + fastapi-sample | PLANNED | NOT_VERIFIED | PKI Vault et OAuth PostgreSQL, OIDC Keycloak/FastAPI : pilote séparé avec break-glass, révocation et RBAC négatif — [Roadmap sécurité PG](security/postgresql-fips-tls13-vault-oauth-20261110.md) |
| H17 | P0 | nabla-compose + fastapi-sample + nabla-site-alban | PARTIAL | NOT_VERIFIED | Backstage V2 : Compose [#365](https://github.com/AlbanAndrieu/nabla-compose/pull/365) et FastAPI [#424](https://github.com/AlbanAndrieu/fastapi-sample/pull/424) fusionnées ; [FastAPI #432](https://github.com/AlbanAndrieu/fastapi-sample/pull/432) fusionnée (snapshot V2 et cartes enrichies, **non réceptionnés au runtime**). Parité entityRef/catalogRevision sur SHA déployé, puis migration Site Alban avant suppression legacy — [Contrat V2](service-catalog-v2-normalization.md) |
| H18 | P2 | nabla-compose | PLANNED | NOT_VERIFIED | EnOcean NodOn et Somfy io/RTS dans Home Assistant : étude de compatibilité, dongle/Overkiz, tests avant achat/appairage — [Étude HA](roadmap-homeassistant-integrations.md) |
| H19 | P1 | nabla-compose | CODED | NOT_VERIFIED | Home Assistant : migration de l'App native vers Compose et recorder PostgreSQL avec rollback et validation des intégrations — [Runbook Apps](runbooks/2026-11-06-catalog-apps-to-compose.md) |

## Jalons déjà réceptionnés ou retirés du backlog

- **OpenClaw** : Gateway TrueNAS et intégration principale acceptées historiquement les 3–5 novembre ; propriété transférée à `nabla-openclaw`. Une modification future exige une nouvelle preuve, pas une réouverture de la migration.
- **TrueNAS/PostgreSQL** : PostgreSQL 18.6, SCRAM et serveur TLS 1.3/`hostssl` vérifiés les 12–13 novembre. Le chiffrement actif ne vaut pas `verify-full` universel : H09 reste ouvert.
- **Apps** : Scanopy, Plumber, ntopng et Bitcoind déclarés déployés les 11–12 novembre ; le déploiement de NetBox, Joplin et Dependency-Track n'en découle pas.
- **Cloudflare** : premier retrait de 26 CNAME appliqué le 10 novembre ; la preuve du dernier nom `s3.int` et des politiques exposées reste H04.
- **Scripts** : extractions `scripts/lib/postgres.sh` et `scripts/lib/app-deploy.sh` fusionnées dans #330 ; conserver les wrappers compatibles jusqu'aux tests de leur remplacement. Le runner GitHub LXC reste **préparé mais inactif**.
- **Catalogue V2** : génération Compose #365 et lecteur FastAPI #424 fusionnés le 13 novembre ; l'affichage révisé et la synchronisation du snapshot ont été fusionnés via FastAPI #432 (205 entités / 139 bindings dans le snapshot, pas de preuve de déploiement). La réception reste H17.
- **FastAPI** : heatmap triable #418 et garde budgétaire Nano #419 fusionnées le 11 novembre. Pas de mesure CPU/réplicas ni de recette OWNER post-déploiement attribuée à ces PR.

## Séquence validée — H02 → H01 → H05

1. **H02/G1** — tourner le secret `postgres_exporter`, réaliser un backup en TLS `verify-full` et une **restauration indépendante** avant activation du cron. [Runbook](runbooks/postgres-g1-restore-and-secret-rotation.md).
2. **H01** — vérifier le pilote CSI réellement installé (pilote officiel TrueNAS versionné), puis PVC RWX, persistance multi-workers et nettoyage après suppression.
3. **H05** — statut du catalogue, disponibilité directe, Gatus frais et scrapes Prometheus corrélés sans faux DOWN.
4. **Recevoir H17**, catalogue V2 Compose → FastAPI #424 → Site Alban, et retirer le legacy seulement après preuve.
5. **Fermer les frontières de sécurité** : H03 (secrets) et H04 (Access/DNS), sans changement de privilèges implicite.
6. **Mesurer le runtime applicatif** : H06 (FastAPI Cloud et OWNER), puis H14 (heatmap).
7. **Choisir la migration suivante** : H07 (pfSense), H08 (trois Apps), H09 (PG verify-full), ou H12 (RAG). Ne pas lancer tout le portefeuille d'un coup.

## Contrat de maintenance et d'archivage

- Après chaque PR, **séparer livraison code, contrôle local et réception runtime** avec SHA, date, cible et commande.
- Déplacer les récits d'incidents vers `docs/incidents/`, les procédures durables vers `docs/runbooks/`, les choix d'architecture vers `docs/adr/` ou `docs/security/`.
- Lorsqu'un item est reçu et n'a plus de suite, le retirer du backlog arbitrable et le résumer en jalon ci-dessus ; Git garde la chronologie, sans copier des runbooks dans plusieurs dépôts.
- Vérifier cet index sans réseau ni secrets : `python3 scripts/quality/check-roadmap-portfolio.py --check` (ou `--json` pour automatiser l'affichage).
