## Consolidation des migrations — 24 octobre 2026 (PR #274)

- [x] Conserver `finish-migrations-20261024.sh --next-commands` comme affichage sans effet de bord du runbook opérateur.
- [x] Ajouter `--local-gates` (non-root, sans mutation TrueNAS) pour lancer dans l'ordre et s'arrêter au premier échec : `just migration-20261024-commands`, `just migration-20261024-test`, `just catalog-convergence-check`, `just agent-skills-check`, `just quality`.
- [x] Ajouter `--check --section sentry` : état des deux consommateurs Kafka et préflight de `recover-sentry-deploying.sh --check`, preuves privées et logs catégorisés sans contenu sensible.
- [x] Ajouter une régression hors réseau Sentry et les contrats du mode `--local-gates` dans la quality gate locale.
- [x] Constater les quality gates fournies par l'opérateur : règles Prometheus 4/4, readiness 84/84 ; la gate de maintenance rapide précédente 37/37. Ces chiffres datent des **révisions exécutées** et ne valent pas validation des nouveaux commits de la PR #274.
- [ ] **P0 Prometheus** : retour opérateur : 2221 redémarrages, `prometheus.yml=0644` (exposition non voulue), une seule règle `0600` encore illisible sur 15. L'échec du `--expected-unreadable 2` est correct. Revalider `--check`, approuver séparément le YAML en `0640` et l'unique règle en `0640`, puis obtenir `running`, `/-/ready`, targets et PromQL sans toucher aux données.
- [ ] **P0 OpenRAG** : App TrueNAS `STOPPED`, backend/frontend absents ; Langflow et OpenSearch sont `running+healthy`. Vérifier les jobs TrueNAS, le contrat Vaultwarden canonique et le stockage avant un démarrage explicitement approuvé.
- [ ] **P0 Sentry** : TrueNAS `DEPLOYING`, `sentry-events-consumer` et `sentry-post-process-forwarder-errors` unhealthy. Collecter les catégories Kafka/Redis/ClickHouse, les préflights et les preuves privées, puis cibler la cause sans réinitialiser les consumer offsets.
- [ ] **P1 migrations** : corriger séparément `live-language-patches`, `secrets-runtime`, `openwebui-pra` et les erreurs Hermes/AI. Ne pas lancer de vague Talos/TrueNAS ou de migration massive tant que les P0 ne sont pas acceptés.

# Roadmap opérationnelle — nabla-compose

**Réconciliation inter-dépôts du 24 octobre 2026.** Ce fichier contient uniquement les actions exécutées dans **nabla-compose** : inventaire déclaratif, GitOps, infrastructure TrueNAS/pfSense/Talos, réseau, secrets et exploitation. Les contrats/collecteurs de données sont propriétaires de [FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md), et les vues Next.js/Vercel de [Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/homelab-roadmap.md).

Les anciennes sections datées et environ **639 points ouverts** étaient répétées entre incidents, snapshots et migrations. Elles restent intégralement retrouvables dans [la version précédente de la roadmap](https://github.com/AlbanAndrieu/nabla-compose/blob/62abf263f698b72b01f690d861e2bd27a91e0965/docs/roadmap.md) et les runbooks ; cet historique n'est pas une seconde liste d'actions actives. La consolidation par *chantier* ne certifie pas que chaque ancien point est terminé. Une tâche n'est close qu'avec preuve d'exécution sur son système cible.

**PR en cours :** [Compose #274](https://github.com/AlbanAndrieu/nabla-compose/pull/274) Draft. Site #254 et FastAPI #373 sont **fusionnées** le 24/10 mais leur déploiement n'est pas attesté. Aucun redémarrage, application GitOps, mutation de secret ou changement de pare-feu sans validation et préflight.

## P0 — 1. Fondation TrueNAS, Prometheus et observabilité

- [ ] Exécuter les diagnostics ciblés de `scripts/truenas/finish-migrations-20261024.sh` sur TrueNAS (lecture seule en priorité) ; conserver un relevé par état `NOT_RUN/UNKNOWN/STALE/FAIL/OK` avec heure, cible et origine.
- [ ] Confirmer sur plusieurs relevés l'écart **App Prometheus RUNNING / conteneur principal exited** ; vérifier utilisateur/UID 568, volumes, `prometheus.yml`, règles, TSDB, exporters, readiness `/-/ready` et les logs. Ne pas modifier permissions/WAL ou redéployer sans cause confirmée.
- [ ] Vérifier Gatus, exporters PostgreSQL/pfSense, Grafana, Alertmanager et leurs cibles, sans provoquer de sonde de masse vers pfSense. La **mesure** et le read-model appartiennent à FastAPI ; ici corriger seulement la cible/runtime/compose.
- [ ] Documenter topologie et disponibilité des composants de fondation : PostgreSQL, Redis, Kafka, ClickHouse, OpenSearch, Sentry, DNS, Traefik, cloudflared et leurs dépendances. Prioriser les incidents qui bloquent les services.
- [ ] Réconcilier ports internes et configurations réelles, sans exposer automatiquement les origines ni modifier les routes sur simple différence de catalogue.

**Done :** conteneurs critiques effectivement observés, cibles vérifiées et smoke non destructif reproductible après correction.

## P0 — 2. Collecteur FastAPI LAN et frontière OWNER

- [ ] Conserver le collecteur **TrueNAS** comme seul émetteur des sondes TCP/HTTP privées. `apps/sample/compose.yml` déclare déjà `HOMELAB_INTERNAL_PROBES_ENABLED=true` en staging ; vérifier l'environnement réel et les compteurs `eligible/sampled/completed` sans supposer que FastAPI Cloud partage ce runtime.
- [ ] Finaliser et valider sur le HEAD exact #274 `scripts/truenas/verify-fastapi-lan-probes.sh` et le runbook correspondant. L'ancienne version du script ajoutée après la fusion #272 n'était pas dans `master` ; cette PR réintègre les diagnostics.
- [ ] Vérifier DNS, connectivité des réseaux Docker, cibles/protocoles et règles anti-SSRF/CIDR du collecteur ; conserver budgets, délais et autorisations réseau restrictifs.
- [ ] Préparer un chemin OWNER **de lecture seule** et authentifié vers le collecteur LAN (Cloudflare Access/service token, origine protégée, JWT vérifié, RBAC et audit), sans autoriser Vercel ou FastAPI Cloud à lancer des sondes directes vers `172.17.0.0/24`.
- [ ] Déployer le service FastAPI staging TrueNAS seulement après quality gate Python propriétaire de FastAPI et préflight Compose ; ne jamais copier les clés OWNER dans un DTO SERVICE ou dans le navigateur.

**Dépendance :** la classification `internal_probe_execution` et la réconciliation par service sont **dans FastAPI**, l'affichage dans Site Alban.

## P0 — 3. Catalogue canonique, DNS, Traefik et Cloudflare

- [ ] Normaliser dans `catalog/`, les annotations `apps/*`, le registre `entityRef` et le mapping `catalog/service-icons.json:webAssets` : identité unique, relations Backstage v2 et intention d'exposition. Ne pas recréer de catalogue v1.
- [ ] Exécuter les validations du générateur Backstage v2 et comparer les IDs à ceux de FastAPI ; toute dérive est un défaut à diagnostiquer, pas une raison d'inventer des cartes ou icônes locales.
- [ ] Vérifier TrueNAS/Cloudflare/Traefik pour Gatus, Bichon, Garage Web UI et Garage Admin (ports, URL, règles Access et état réel) avant d'éditer les configurations GitOps. Qualifier les contradictions déclaratif/runtime.
- [ ] Consolider DNS public/local, HAProxy, Tunnel, Traefik et propriétaires des routes `*.int.albandrieu.com`. Séparer une destination déclarée d'un accès effectivement confirmé.
- [ ] Auditer `ops.albandrieu.com` et les autres surfaces d'administration : accès privé, politique Access MFA, certificats et origine. Les pages du site restent gérées par Site Alban.

**Done :** une seule source Compose pour services/ports/expositions, et vérification runtime de ses routes.

## P0 — 4. pfSense, Unbound, NetFlow et Akvorado

- [ ] Suivre les OOM Unbound et la pression mémoire pfSense : relever état des processus, tables, DNS et filtres avant toute modification ; conserver un export de configuration pour rollback.
- [ ] Valider la collecte NetFlow v5/`pflow`, les interfaces/`ifIndex`, les paquets, les deltas et les insertions Akvorado → ClickHouse avec les diagnostics bornés de #274. Le mapping `ifIndex=11` déclaré n'est pas une preuve d'arrivée des paquets.
- [ ] Stabiliser pfBlockerNG/ASN/DNSBL, rotation/rétention des logs et protection des API pfSense (auth, timeout, absence de boucle de login). Ne pas augmenter les limites de ressources pour masquer un défaut sans analyse.
- [ ] Vérifier règles WAN least-privilege, HAProxy TLS/backend, Snort/Suricata/CrowdSec, alertes et DNS Unbound résilient même lorsque TrueNAS Apps est arrêté.
- [ ] Examiner l'incident de flap `e6000sw0port2` et les responsabilités de Pi-hole/AdGuard Home. Ne pas présenter deux conteneurs sur le même hôte comme une redondance.

**Done :** mesures persistantes de mémoire/DNS/flux, absence d'erreur confirmée et rollback prêt.

## P0 — 5. Secrets, restauration et migrations bloquées

- [ ] Terminer le transfert des secrets TrueNAS depuis les anciennes variables/`.env.secrets` vers le chemin canonique Vaultwarden + `/mnt/cpool/secrets/runtime` avec propriétaires, permissions, audit sans impression et plan de rollback.
- [ ] Bloquer tout `--apply` OpenRAG/Docling/OpenSearch qui écrit dans un fichier historique ou contourne Vaultwarden. Le script #274 doit rester fail-closed et produire uniquement les commandes de préparation sûres.
- [ ] Diagnostiquer la chaîne OpenRAG du dataset `cpool/bababou` montée à `/mnt/bababou`, Docling, Langflow, permissions et ingestion, puis déployer uniquement une fois le chemin de secrets et la sauvegarde validés.
- [ ] Poursuivre migrations Apps par lot contrôlé (OpenRAG, OpenClaw, Gatus, Garage, Sentry, FreshRSS, Bichon, archives e-mail et services arrêtés) : inventaire avant/après, dépendances, données ZFS et healthchecks.
- [ ] Stabiliser sauvegardes/restauration OpenClaw, cron, gateway, embeddings LiteLLM, budget/identités et le chemin workstation/TrueNAS. Pas de suppression de volume ou redémarrage sans tests.

**Done :** migrateur idempotent, preuve de droits/secret source et smoke lecture seule, puis action mutante explicitement approuvée.

## P1 — 6. Talos/Kubernetes et déploiements GitOps

- [ ] Poursuivre la convergence Talos/Kubernetes (DNS/CNI, democratic-csi/NFS, Traefik, PVC smoke, secrets, RBAC et NetworkPolicy) en respectant la stabilité du cluster existant et les versions réellement installées.
- [ ] Vérifier manifests, chart Helm, image unique Next.js et image FastAPI par digest, provenance, Trivy, readiness/liveness, caches et TLS. **Le code des applications et leur build restent dans leurs propres dépôts.**
- [ ] Aligner SSH TrueNAS, DNS, accès API et configuration des volumes sans exposer les endpoints LAN ; tester rollback et tolérance à une panne de nœud avant changement.
- [ ] Pour TrueNAS 26, vérifier la transition WebSocket JSON-RPC côté appliances et préparer les permissions des observers ; la migration du client Python API appartient à FastAPI.

## P1 — 7. Sécurité, DefectDojo et gouvernance GitHub

- [ ] Finir la plateforme de collecte **LAN** DefectDojo : GitHub App unique, Vaultwarden, Cron, parsing Trivy/CycloneDX, ZAP/Nuclei/Semgrep et ingestion approuvée avec déduplication, provenance SHA/run et minimisation des artefacts.
- [ ] Conserver un seul modèle de CI économique (Draft, `[skip ci]` pour docs/agents, gates locaux, artefacts courts) sans supprimer les scans bloquants requis avant fusion.
- [ ] Valider les profils de sécurité Cloudflare/pfSense/TrueNAS et la revue STRIDE/DSOMM en lecture seule ; conserver les findings vérifiables, jamais d'UUID inventé.
- [ ] Continuer la migration GitOps des secrets, les quotas, les rôles de lecture, les clés YubiKey/FIDO2 et les mécanismes de sauvegarde sur workstation avec confirmation humaine pour toute action destructive.

## P1 — 8. Services applicatifs et architecture de plateforme

- [ ] Résoudre les anomalies et aligner les données des applications homelab (Garage/S3, FreshRSS, Homarr, Hermes, Bichon, DefectDojo, Pyroscope, Postgres, Kafka, ClickHouse et Sentry) selon leurs runbooks propres ; ne pas déplacer leur code frontend/backend ici.
- [ ] Stabiliser le modèle LiteLLM TrueNAS/workstation (clés à budget, modèles, fallback, observabilité) et les intégrations Hermes/OpenClaw/OpenRAG sans secrets versionnés.
- [ ] Standardiser les domaines internes, les probes d'application, les limites CPU/mémoire, la persistance ZFS et les chemins Compose. Préférer les recettes finissables aux migrations massives simultanées.

## P2 — 9. Évolutions différées

- [ ] Évaluer les améliorations Cloudflare OpenTofu/IaC, les optimisations de monitoring, l'agrégation DSOMM/CTI/SBOM et la migration des autres apps uniquement après stabilisation des P0.
- [ ] Revoir les skills externes Docker/Kubernetes avant installation éventuelle ; demander l'accord utilisateur, conserver la priorité des skills Nabla et ne pas installer de nouveau logiciel sur l'appliance sans permission.

## Frontière des trois projets

| Responsable | Ce qui reste chez lui |
| --- | --- |
| **Compose** | Déploiements, secret materialization, ZFS, Talos, pfSense, Docker/Traefik/Cloudflare, monitoring agents, GitOps et catalogue déclaratif |
| [FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) | Algorithmes des sondes, DTO, provenance et états, contrats de santé, UI native FastAPI, tests pytest et déploiement de l'application FastAPI Cloud |
| [Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/homelab-roadmap.md) | Next.js, ReactFlow, icons/frontend, cache navigateur, accessibilité/FR-EN, Vercel et pages de sécurité |

**Critère de clôture commun :** ne jamais confondre déclaration, test statique, merge, déploiement et mesure live. Une tâche nécessitant TrueNAS/pfSense doit être marquée `NOT_RUN` depuis un environnement agent sans accès à ces machines ; un `RUNNING` ne valide pas automatiquement une sonde. Les documents de détail restent dans `docs/runbooks/` et l'historique Git, sans nouvelle checklist active concurrente.
