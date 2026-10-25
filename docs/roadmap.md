# Services Homelab — roadmap active

> Mise à jour : **25 octobre 2026**. Source d'autorité pour le travail restant
> dans `nabla-compose`. Ce document décrit des **décisions et gates**,
> pas une preuve de fonctionnement des services.
>
> L'[historique intégral jusqu'au 24 octobre](archive/roadmap-through-2026-10-24.md)
> est conservé, octet pour octet (blob Git identique à l'ancien `docs/roadmap.md`).
> Les états et commandes datés de cet historique **ne sont pas des consignes
> de réparation courantes**.

## Convention de suivi

- **DONE (code)** : implémentation versionnée et contrôle ciblé identifié ;
  ne prouve pas le déploiement.
- **NOT_VERIFIED (runtime)** : preuve opérateur absente ou antérieure à la
  dernière modification ; ne pas marquer `UP` par inférence.
- **BLOCKED** : prérequis explicite manquant ; noter la cause.
- **ACCEPTED (runtime)** : preuves datées issues de TrueNAS/pfSense, test
  fonctionnel et critère de rollback satisfaits.

Sur la base du relevé opérateur du 25 octobre, l'ordre de diagnostic actif
est **Prometheus → OpenRAG → Akvorado**. Sentry et DefectDojo ont passé
leurs sondes ciblées mais leur E2E reste à confirmer. La sécurité mémoire
pfSense est un chantier indépendant. Ne traiter qu'une cause à la fois.

## Priorités opérationnelles et preuves

| Ordre | Domaine | Contrôle à valider | État |
| --- | --- | --- | --- |
| 1 | Prometheus | Configuration corrigée (0640), 21 targets UP, 7 DOWN | **Serveur sain, collecte dégradée** |
| 2 | OpenRAG / LiteLLM | `--strict --scope openrag` et `--scope litellm` : `blockers=[]`, `missingKeys=[]`, fichiers `ready=true`, conteneurs RUNNING | **Secrets déclarés PASS ; authentification et rechargement runtime NOT_VERIFIED** |
| 3 | Akvorado | +5 flux / +4 metadata missing / +0 lots ClickHouse ; statique ifIndex=11 à vérifier en mémoire | **Ingestion bloquée** |
| Suivi | Sentry et DefectDojo | Smoke métier / E2E après sondes PASS | **NOT_VERIFIED E2E** |
| Indépendant | pfSense / Unbound | Kill Unbound par OOM **confirmé** (17/22/24 oct.) ; routine DNSBL de minuit fortement corrélée aux sorties Python, initiateur des redémarrages **non prouvé** | **OOM_CONFIRMED / RESTART_PROVENANCE_PENDING** |
| Différé | Workstation split-DNS | DNS pfSense/Pi-hole corrects, NSS privé indisponible via Quad9 ; 19 tests de diagnostic PASS opérateur | **Correction reportée par décision utilisateur ; ne pas modifier la workstation** |

**Dernière preuve datée :** [second relevé du 25 octobre](runbooks/2026-10-25-critical-acceptance-followup.md) — `PASS=9 FAIL=7 WARN=0 SKIP=0` (contre [8/8 au premier relevé](runbooks/2026-10-25-critical-acceptance-evidence.md)) ; révision du checkout TrueNAS inconnue. Une réussite de sondes sur Sentry ou DefectDojo ne prouve pas la disponibilité E2E. Les 85 sondes Gatus déclarées ne représentent pas 85 services opérationnels : [diagnostic spécialisé](runbooks/2026-10-25-homelab-operator-diagnostics.md).

**Quatrième preuve (25/10) :** `openrag` et `litellm` ont chacun `ready=true`, `missingKeys=[]`, `blockers=[]` au diagnostic `--strict` de l'opérateur ; le comparateur OpenSearch reste bloqué sur **legacy_env UID 1000/GID 568/mode 0644**. La lecture des nouvelles variables par les processus, les authentifications et la finalisation sont **NOT_VERIFIED**. [Clôture guidée](runbooks/truenas-secret-migration-closure.md).

**Troisième preuve ciblée (25/10) :** [deux sessions à 1 PASS / 6 FAIL](runbooks/2026-10-25-critical-acceptance-followup.md) avant réparation Prometheus `0644 → 0640`. Les résultats individuels du serveur Prometheus et d'Akvorado détaillent désormais les causes ; aucun E2E de migration n'est clos. Ne pas réutiliser les anciens états 9/7 comme preuve actuelle.

## P0 — Accepter les services critiques

| ID | Domaine | Dernière preuve datée, sans extrapolation | Condition d'acceptation |
| --- | --- | --- | --- |
| H-01 | OpenRAG | Dernières sondes : secret OpenRAG `ready=true`, `missingKeys=[]`, `blockers=[]` ; OpenSearch App RUNNING mais conteneur exact `ABSENT_OR_UNVERIFIED` ; égalité du credential bloquée par les droits de `legacy_env` | App `RUNNING`, backend et frontend `running+healthy`, authentifications Langflow/OpenSearch et modèles LiteLLM testés |
| H-02 | Sentry | Le 25/10 : consumer et recovery preflight PASS ; ingestion E2E non reconfirmée | Consommateurs sains, Kafka/Relay et smoke d'ingestion E2E contrôlés |
| H-03 | DefectDojo | Le 25/10 : préflight et ingress privé PASS ; pas de preuve de bout en bout actuelle | Origine HTML, uWSGI, DNS privé Pi-hole/Unbound et HTTPS SNI/TLS contrôlés séparément |
| H-04 | pfSense / Unbound | OOM Unbound **confirmés** le 17/22/24 octobre ; fermeture DNSBL Python vers 00:04 répétée ; chronologie pfBlockerNG à la seconde **manquante** | Identifier le déclencheur du restart, vérifier appartenance Service Watchdog et version pfBlockerNG ; corréler RSS des jobs avant tout changement |

Actions :
- [ ] **H-01 :** exécuter `diagnose-openrag-startup.sh --check`,
  `diagnose-openrag-dependencies.sh --check` et
  `reconcile-openrag-opensearch-secret.sh --check` depuis TrueNAS.
- [ ] **H-01 :** accepter backend/frontend et les authentifications sans
  régénérer de clé ni indexer le corpus `cpool/bababou`.
- [ ] **H-02 :** contrôler les deux consommateurs avec
  `diagnose-sentry-consumers.sh --check` et le smoke Sentry déjà versionné.
- [ ] **H-03 :** isoler la panne par `diagnose-defectdojo.sh --check`,
  sans modifier PostgreSQL, l'initializer ou la route publique.
- [ ] **H-04 :** séparer le **OOM Unbound confirmé** vers 02:10 des
  redémarrages 23:38/00:04 non attribués ; exécuter
  `just pfsense-unbound-restart-test` puis
  `just pfsense-unbound-restart-check` en lecture seule, et rapprocher
  les catégories kernel, DNSBL, cron, Watchdog et configd sans leur
  attribuer une causalité implicite.
  [Runbook causalité](runbooks/2026-10-25-pfsense-unbound-restart-causality.md).
- [ ] **Workstation DNS :** valider le parseur DHCP et le chemin de la zone privée via
  `just pfsense-wifi-path-test` et `just pfsense-wifi-path` ; isoler le
  propriétaire de la divergence NetworkManager ↔ `systemd-resolved` sans
  modifier DHCP, Pi-hole ou pfSense. [Runbook daté](runbooks/2026-10-25-pfsense-wifi-dns-root-cause.md).

Les contrôles regroupés sont décrits dans
[Runtime acceptance](runbooks/homelab-runtime-acceptance.md).
Les procédures spécialisées restent dans
[le répertoire des runbooks](runbooks/README.md).

## P1 — Corriger les causes instrumentées

| ID | Domaine | Fait établi | Reste à prouver |
| --- | --- | --- | --- |
| H-05 | Prometheus | Correction du fichier `prometheus.yml` par opérateur : uid 1000, gid 568, mode 0640 ; promtool OK, 21/28 targets UP | Réconcilier les scrapes non UP sans réparer à nouveau les règles |
| H-06 | Akvorado | Nouvelle preuve : 5 flux reçus, 4 rejets metadata, 0 insertion ; le PASS ponctuel précédent ne prouve pas l'absence de blocage | Vérifier l'export NetFlow, les `ifIndex` et **de nouvelles lignes SQL datées** |
| H-07 | Catalogue OWNER/SERVICE | Identités Backstage/`x-nabla` déclarées ; consommateurs FastAPI/Site distincts | Vérifier dérive catalogue, puis comportement runtime par provenance |
| H-08 | Secrets et noms | OpenRAG et LiteLLM : validations de présence/format PASS ; `apps/opensearch/.env` legacy actuellement UID=1000 GID=568 mode=0644, encore déclaré par Compose | **BLOCKED** : mode/propriétaire OpenSearch, égalité des credentials, runtime effectif et finalisation legacy |
| H-09 | Talos / Kubernetes | CSI NFS antérieurement accepté | Retained smoke multi-nœuds avant changement d'Ingress ou migration d'App |

Actions :
- [ ] **H-05 :** classer chaque cible restante `DNS`, `TLS`, `HTTP`,
  `TCP` ou `auth`, à partir des preuves Prometheus assainies. Le `401`
  FastAPI `/metrics` nécessite la clé de scrape dédiée **après**
  déploiement du correctif FastAPI ; `postgres_exporter:9187` refusé
  ne signifie pas `PostgreSQL:5432` indisponible.
- [ ] **H-06 :** comparer la configuration Akvorado effectivement montée,
  le metadata provider, les compteurs sur deux fenêtres et ClickHouse ;
  ne pas élargir le tracking pfSense sans décision.
- [ ] **H-07 :** garder le catalogue Compose/`x-nabla` comme source
  déclarative ; ne pas transformer une sonde inaccessible en preuve `DOWN`
  d'une application.
- [ ] **H-08 :** présence et format des clés OpenRAG/LiteLLM **PASS** sur TrueNAS.
  Corriger **uniquement** les métadonnées du candidat OpenSearch `legacy_env`
  (UID=1000, GID=568, mode=0644 au dernier relevé) : fichier encore
  utilisé par `apps/opensearch/compose.yml`. Vérifier l'égalité des valeurs
  après réparation, puis l'identifiant effectivement chargé et l'authentification.
  Vérifier que les clés Langfuse sont réelles et issues du même projet : un
  PASS syntaxique ne prouve pas le callback. Ne pas finaliser le legacy
  OpenRAG avant une acceptation runtime vérifiée.
  [Gates de clôture](runbooks/truenas-secret-migration-closure.md) · [preuves et commandes](runbooks/2026-10-25-critical-acceptance-followup.md).
- [ ] **H-09 :** exécuter les contrôles CSI/Talos uniquement après P0
  et dans la fenêtre approuvée.

## P1 — API gateway APISIX (ADR-0001)

**Décision et backlog canoniques :** [ADR-0001 Apache APISIX](adr/0001-apisix-api-gateway-poc.md), [choix APISIX](api-gateway-selection.md), [gouvernance du dispatch](architecture-governance.md) et [runbook diagnostic bout en bout](runbooks/homelab-e2e-diagnostics.md). L'ADR-0001 est accepté pour un POC en staging, non déployé ; Traefik reste la gateway/ingress existante.
- [x] Comparer APISIX, Traefik ForwardAuth, Envoy Gateway et Kong OSS ;
  choisir **APISIX standalone YAML** pour un POC interne non exposé, sans etcd.
- [x] Documenter la chaîne Catalogue Compose → FastAPI → Site → utilisateur,
  avec séparation rôle/identité/reseau, sécurité des erreurs et rollback.
- [ ] Inventorier les routes Traefik/Cloudflare et les politiques PUBLIC/SERVICE/
  OWNER/INTERNAL avant tout changement de dataplane.
- [x] **APISIX code livré :** `apps/apisix/`, identité `apisix`,
  `x-nabla.id=apisix`, route `/health`, clé `APISIX_KEY`, réseau isolé,
  sans exposition hôte. Les commandes `just apisix-*` sont opt-in.
  **Contrat APISIX Python : 10/10 PASS local** sur copies de fichiers
  identiques par blob Git ; déploiement et smoke réseau **NOT_VERIFIED**.
- [ ] **APISIX (API Gateway OSS, ADR-0001, Compose owner)** : préparer et tester un POC APISIX **staging** sur hostname interne,
  sans exposer l'Admin API, avec tests 401/403/429/502/timeout/trace.
- [ ] Valider OIDC Keycloak, rotation des credentials, mTLS et observabilité
  lorsque le service Keycloak existe réellement ; ne pas bloquer le
  durcissement immédiat de FastAPI sur cet ajout.
- [x] Approuver ADR-0001 pour un POC APISIX staging (sans cutover) et adopter le fast-track ADR/RACI/C4 pour les agents ; le processus documentaire ne doit pas bloquer les changements réversibles.
- [ ] Après preuve des tests APISIX, arbitrer un éventuel cutover Traefik via ADR successeur, sans changer les routes publiques par défaut.
- [ ] Inventorier les besoins d'auth, quotas, rate-limit, logs et traçage par route avant configuration APISIX ; rejeter une Admin API externe et pinning incomplet.
- [ ] **OIDC sûr en standalone :** secrets `session.secret` et `client_secret`
  hors Git, `redirect_uri` HTTPS absolu, cookies sécurisés, vérification
  TLS/JWKS, validation d'audience et tests `Host`/`Forwarded` falsifiés.
  APISIX reste interdit en production sans ADR de cutover spécifique.

- [x] Documenter le rollback isolé d'APISIX ; la commande `down`
  fonctionne sans conserver la clé. Tests synthétiques ajoutés,
  **non encore exécutés sur le HEAD courant**.
- [ ] Faire une recette négative runtime avant toute migration de routes.
  Aucun cutover ni déploiement de gateway en production autorisé par ce document.

- [x] Affecter le rendu C4 interactif au Site Alban avec React Flow existant, sans service supplémentaire ; source C4 dérivée du catalogue v2, pas un nouvel inventaire Compose.

## P1 — Fiabilité des scripts et documentation

- [x] **D-01 :** séparer la roadmap active de ses 3 770 lignes historiques
  sans supprimer l'historique ni contourner le contrôle de diff destructif.
- [x] **D-02 :** créer un index des runbooks avec statut `actif` ou
  `historique` ; une seule procédure d'acceptation courante.
- [ ] **D-03 :** conserver le registre read-only séparé de la CLI protégée,
  le refus des modes mutateurs mixtes et l'expurgation des plans.
  **Qualité locale complète : non attestée.** Toute extraction du code mutateur
  reste différée jusqu'aux tests négatifs et à la preuve du HEAD exact.
- [ ] **D-04 :** parseur HTTP/MIME DefectDojo factorisé et contrôle DNS
  fail-closed ajouté ; tests négatifs versionnés mais **non exécutés**.
  Valider 200 HTML / 200 JSON / 403 / 000 / DNS timeout.
- [x] **D-08 (code) :** sections read-only `postmigration` et `apisix` ;
  états PASS/FAIL/UNVERIFIED et tests synthétiques ajoutés.
  Acceptation sur TrueNAS **NOT_VERIFIED**.
- [ ] **D-05 :** extraire les primitives redondantes de diagnostics Docker
  (état, health, compteurs, expurgation) uniquement avec tests négatifs.
- [ ] **D-06 :** une CLI stable `scripts/truenas/migration-operator.sh`
  délègue au runner historique dans un Bash enfant. Valider les contrats
  et migrer progressivement les références `pr274` après la quality gate.
  [Contrat opérateur](runbooks/truenas-migration-operator.md).
- [x] **D-07 :** preuve `critical` du 25/10 externalisée dans un
  [runbook daté](runbooks/2026-10-25-critical-acceptance-evidence.md).
  Les observations futures doivent aller dans un rapport daté distinct.
- [x] **D-09 (code) :** compatibilité Node 22/npm 10, sans dépendances
  installées : `just node22-fast` ; **6/6 PASS** sur espace de test
  isolé et **cas négatif PASS**. Les artefacts APISIX copiés sont identiques
  aux blobs de la PR, mais les scripts de migration utilisés dans cette
  suite rapide sont des substituts. [Preuves et limites](runbooks/node22-local-fast-tests.md).
- [x] **D-11 (code) :** aligner l'env_file OpenRAG sur le secret
  canonique, isoler `diagnose-ai-secret-recovery.py --scope openrag`
  des erreurs Scrutiny/LiteLLM et ajouter le triage privé des **sept
  gates**. Tests négatifs ajoutés, **runtime TrueNAS NOT_VERIFIED**.
  [Reprise ciblée](runbooks/2026-10-25-critical-acceptance-followup.md).
- [x] **D-12 (code) :** ajouter icônes et couleurs au triage ciblé
  (`--color auto|always|never`, `--icons auto|always|never`,
  `NO_COLOR`, `--no-color`), sans ANSI dans les preuves privées.
  Le comparateur OpenSearch indique désormais une **classe de fichier**
  incorrecte, sans afficher sa valeur.
- [x] **D-14 (code) :** validation de la clé AES-256-GCM OpenRAG
  (32 octets Base64), des guillemets dotenv et de la paire
  `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` dans le secret
  **LiteLLM canonique**. Tests synthétiques ajoutés, runtime
  **NOT_VERIFIED**. [Procédure](runbooks/truenas-secret-migration-closure.md).
- [ ] **D-13 (runtime) :** démontrer séparément l'accès au secret
  canonique, l'absence de chemin legacy, les identifiants authentifiés,
  la disponibilité des 7 exporters Prometheus et des lots ClickHouse
  datés ; ne pas clore la migration sur la seule base des copies staged.
- [ ] **D-10 :** exécuter la suite Python complète de migration,
  `agent-skills-check`, ShellCheck et `just quality` dans un vrai worktree
  au HEAD exact. Aucune gate L3 complète n'est déclarée PASS.

[Registre des risques des refactorings](runbooks/homelab-refactoring-risk-register.md) :
R-01 à R-07, avec conditions de rollback et seuils L1/L3.

**Conditions de clôture documentaire :** liens relatifs valides, archivage
intègre, conformité `agent-skills-check`, tests ciblés et quality gate
complète sur le HEAD exact. **Aucune CI GitHub payante** pendant la Draft.

## Quality gate locale et compatibilité Node

- **Version principale du dépôt :** Node 24 (`.nvmrc`, `mise.toml`) ; ne pas
  modifier l'environnement de production pour lancer les tests.
- **Mode rapide de compatibilité :** Node 22 + npm 10, préflight explicite,
  tests Node natifs sans `npm install`, `npx`, réseau ni GitHub Actions.
- **Portée :** contrats statiques des chemins/commandes APISIX et migrations,
  distincts des tests Python, ShellCheck, du smoke Docker et de `just quality`.
- **Validé localement :** lanceur Node 22/npm 10 (6/6 et refus d'une
  identité Compose incorrecte), ainsi que 10/10 tests Python APISIX
  avec correspondance SHA des fichiers concernés.
- **Reste à valider :** `just node22-fast` dans le **checkout complet**,
  puis `just migration-operator-contracts`, `just agent-skills-check`
  et `just quality` sur **le HEAD exact**.

## Autorités, sécurité et séquence opérateur

| Projet | Autorité |
| --- | --- |
| `nabla-compose` | Compose/`x-nabla`, exposition déclarée, topologie, scripts TrueNAS/Talos/pfSense, runbooks |
| `fastapi-sample` | Sondes, diagnostic runtime, DTO OWNER/SERVICE, contrôle d'accès |
| `nabla-site-alban` | Présentation des services, icônes, filtres, cache client expurgé |
| `nabla-site-bababou` | Site et données privées, sans duplication de la logique transverse |

Lire [la politique des skills](agent-skills-architecture.md) et
[`AGENTS.md`](../AGENTS.md). Les skills externes
`docker-compose-patterns` et `kubernetes-specialist` exigent de
**Ask the user** avant installation. Respecter le stockage TrueNAS,
Vaultwarden, `democratic-csi`, `entityRef` et `catalogRevision`.
Ne pas ouvrir la production, assouplir TLS, supprimer des données, ni
exécuter de remédiation implicite pour obtenir un `PASS`.

### Contrôle local-first

1. Créer un worktree isolé à partir du HEAD vérifié, sans toucher au checkout TrueNAS.
2. Préparer une `.venv` par worktree à l'aide de `uv` et du lockfile.
3. Exécuter les tests ciblés avec cas négatifs.
4. Exécuter `just agent-skills-check` puis `just quality`.
5. Vérifier le HEAD testé avant toute déclaration `PASS`.

La [procédure qualité versionnée](runbooks/2026-10-24-pr274-local-quality-one-shot.md)
appartient à l'historique de la PR fusionnée ; préférer le
[skill local-first](../.agents/skills/local-first-quality/SKILL.md)
pour toute nouvelle PR.

## Archives et chantiers spécialisés

Les preuves et décisions antérieures (DSOMM, GitOps, YubiKey, OpenClaw,
Cloudflare, Sentry, Gatus, Scrutiny, Talos et sécurité) sont **conservées**
dans l'[archive datée](archive/roadmap-through-2026-10-24.md).
Pour les chantiers durables, consulter également :
[secrets](secrets-migration-roadmap.md) ·
[catalogue sécurité](service-catalog-security-graph.md) ·
[plateforme Kubernetes](homelab-platform-migration-roadmap.md) ·
[gestion des skills](agent-skills-architecture.md).
