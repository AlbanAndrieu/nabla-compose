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

## Dernière preuve opérateur — 25 octobre 2026

Le contrôle read-only `finish-migrations-20261024.sh --check --section critical`
a retourné **PASS=8 FAIL=8 WARN=0 SKIP=0**. Les informations ci-dessous
sont une **preuve datée**, pas une sonde permanente :

- **Prometheus :** `prometheus-targets` et `prometheus-config-access`
  échouent ; `prometheus-rules-access` réussit. Ne pas réappliquer
  d'ancienne réparation POSIX sans consulter le rapport privé.
- **OpenRAG :** `openrag-startup`, `ai-runtime-recovery`,
  `openrag-opensearch-legacy-secret`, `openrag-backstage-bundle`
  échouent. Les dépendances et le préflight `openrag-env-migration`
  réussissent. Aucun restart ni changement de mot de passe implicite.
- **Sentry :** consommateurs et préflight de récupération réussissent.
  Cela ne remplace pas un événement E2E frais.
- **Akvorado :** configuration réussie ; `akvorado-blocked` et
  `akvorado-fresh-inserts` échouent. Les compteurs historiques ne
  valent pas une nouvelle insertion ClickHouse.
- **DefectDojo :** préflight et accès privé réussissent ; ne pas
  ouvrir davantage le service.

**Séquence de diagnostic recommandée :** Prometheus → OpenRAG → Akvorado,
sans intervention globale sur Sentry ou DefectDojo.
Rapport privé sur TrueNAS : `/mnt/cpool/var/nabla/migration-20261024/session-uPAiEbSW`.
Ne pas copier les secrets ou les logs bruts dans Git.

**Gatus (catalogue/observabilité) :** 85 sondes déclarées dans le
dernier relevé de la PR #277, pas 85 services fonctionnellement attestés.
Les nouveaux scripts `diagnose-gatus-monitors.py --check` et
`diagnose-service-bundle.py --plan|--check` séparent `down`,
`unverified`, observation périmée, disponibilité réseau et intention
de déploiement. Refaire la comparaison sur l'API Gatus LAN avant
d'affirmer une couverture.
[Entrée diagnostique](runbooks/2026-10-25-homelab-operator-diagnostics.md) ·
[Observabilité spécialisée](runbooks/2026-10-25-observability-triage.md).

## P0 — Terminer la stabilisation réelle

| ID | Domaine | Dernière preuve datée, sans extrapolation | Condition d'acceptation |
| --- | --- | --- | --- |
| H-01 | OpenRAG | Le 25/10 : startup, récupération IA, secret historique OpenSearch et bundle Backstage en FAIL ; dépendances et migration env PASS | App `RUNNING`, backend et frontend `running+healthy`, authentifications Langflow/OpenSearch et modèles LiteLLM testés |
| H-02 | Sentry | Le 25/10 : consumer et recovery preflight PASS ; ingestion E2E non reconfirmée | Consommateurs sains, Kafka/Relay et smoke d'ingestion E2E contrôlés |
| H-03 | DefectDojo | Le 25/10 : préflight et ingress privé PASS ; pas de preuve de bout en bout actuelle | Origine HTML, uWSGI, DNS privé Pi-hole/Unbound et HTTPS SNI/TLS contrôlés séparément |
| H-04 | pfSense / Unbound | OOM du noyau observés ; causalité des tâches Snort/CrowdSec/pfBlockerNG **non démontrée** | Horaires et mémoire corrélés, plan de changement unique avec sauvegarde et rollback |

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
- [ ] **H-04 :** étudier les traces OOM, les processus et les tâches planifiées
  en lecture seule ; ne déplacer aucune tâche sur simple corrélation temporelle.

Les contrôles regroupés sont décrits dans
[Runtime acceptance](runbooks/homelab-runtime-acceptance.md).
Les procédures spécialisées restent dans
[le répertoire des runbooks](runbooks/README.md).

## P1 — Corriger les causes instrumentées, sans panne induite

| ID | Domaine | Fait établi | Reste à prouver |
| --- | --- | --- | --- |
| H-05 | Prometheus | Le 25/10 : `prometheus-targets` et `prometheus-config-access` FAIL ; rules access PASS | Réconcilier les scrapes non UP sans réparer à nouveau les règles |
| H-06 | Akvorado | Flux Kafka historiques ; erreurs metadata provider cumulées ; aucune nouvelle insertion ClickHouse attestée | Vérifier l'export NetFlow, les `ifIndex` et **de nouvelles lignes SQL datées** |
| H-07 | Catalogue OWNER/SERVICE | Identités Backstage/`x-nabla` déclarées ; consommateurs FastAPI/Site distincts | Vérifier dérive catalogue, puis comportement runtime par provenance |
| H-08 | Secrets et noms | Chemins canoniques, renommages `openwebui`/`homeassistant` préparés | Réconcilier chaque Custom App et chaque secret avec rollback indépendant |
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
- [ ] **H-08 :** migrer les secrets un service à la fois ; garder les
  sources historiques tant que la restauration n'est pas attestée.
- [ ] **H-09 :** exécuter les contrôles CSI/Talos uniquement après P0
  et dans la fenêtre approuvée.

## P1 — API gateway OSS et corrélation des causes (25 octobre 2026)

**Décision et backlog canoniques :** [ADR-0001 Apache APISIX](adr/0001-apisix-api-gateway-poc.md), [choix APISIX](api-gateway-selection.md), [gouvernance du dispatch](architecture-governance.md) et [runbook diagnostic bout en bout](runbooks/homelab-e2e-diagnostics.md). L'ADR-0001 est accepté pour un POC en staging, non déployé ; Traefik reste la gateway/ingress existante.
- [x] Comparer APISIX, Traefik ForwardAuth, Envoy Gateway et Kong OSS ;
  choisir **APISIX standalone YAML** pour un POC interne non exposé, sans etcd.
- [x] Documenter la chaîne Catalogue Compose → FastAPI → Site → utilisateur,
  avec séparation rôle/identité/reseau, sécurité des erreurs et rollback.
- [ ] Inventorier les routes Traefik/Cloudflare et les politiques PUBLIC/SERVICE/
  OWNER/INTERNAL avant tout changement de dataplane.
- [x] Livrer POC APISIX standalone opt-in dans `apps/apisix/` : route mock protégée, réseau interne sans port publié, recette de tests `just apisix-contract` (L1 historique 4/4 PASS (HEAD précédent)). Aucune preuve de démarrage Docker à ce stade.
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

- [x] Documenter le rollback isolé du POC APISIX ; la commande `down`
  fonctionne sans conserver la clé POC. Tests synthétiques ajoutés,
  **non encore exécutés sur le HEAD courant**.
- [ ] Faire une recette négative runtime avant toute migration de routes.
  Aucun cutover ni déploiement de gateway en production autorisé par ce document.

- [x] Affecter le rendu C4 interactif au Site Alban avec React Flow existant, sans service supplémentaire ; source C4 dérivée du catalogue v2, pas un nouvel inventaire Compose.

## P1 — Dette de code et de documentation

- [x] **D-01 :** séparer la roadmap active de ses 3 770 lignes historiques
  sans supprimer l'historique ni contourner le contrôle de diff destructif.
- [x] **D-02 :** créer un index des runbooks avec statut `actif` ou
  `historique` ; une seule procédure d'acceptation courante.
- [ ] **D-03 :** la CLI refuse désormais les modes d'exécution mixtes et
  expurge les motifs non maîtrisés du planificateur ; tests négatifs ajoutés
  mais quality gate complète **NOT_RUN**. Le registre read-only a été extrait de
  `finish-migrations-20261024.sh` vers
  `scripts/truenas/migration-diagnostic-sections.sh` et les tests négatifs
  ont été ajoutés ; **quality gate complète à exécuter**. Conserver les modes
  `--apply-*` dans la CLI protégée ; toute extraction de mutation reste différée.
- [ ] **D-04 :** parseur HTTP/MIME DefectDojo factorisé et contrôle DNS
  fail-closed ajouté ; tests négatifs versionnés mais **non exécutés**.
  Valider 200 HTML / 200 JSON / 403 / 000 / DNS timeout.
- [ ] **D-05 :** extraire les primitives redondantes de diagnostics Docker
  (état, health, compteurs, expurgation) uniquement avec tests négatifs.
- [ ] **D-06 :** une CLI stable `scripts/truenas/migration-operator.sh`
  délègue au runner historique dans un Bash enfant. Valider les contrats
  et migrer progressivement les références `pr274` après la quality gate.
  [Contrat opérateur](runbooks/truenas-migration-operator.md).
- [ ] **D-07 :** réduire la duplication de preuves datées entre les runbooks
  d'incident et la roadmap ; publier les observations futures dans
  l'incident correspondant, puis ne garder ici que l'état et le lien.

[Registre des risques des refactorings](runbooks/homelab-refactoring-risk-register.md) :
R-01 à R-07, avec conditions de rollback et seuils L1/L3.

**Conditions de clôture documentaire :** liens relatifs valides, archivage
intègre, conformité `agent-skills-check`, tests ciblés et quality gate
complète sur le HEAD exact. **Aucune CI GitHub payante** pendant la Draft.

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
