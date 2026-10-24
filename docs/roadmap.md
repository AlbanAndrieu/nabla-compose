# Nabla Compose — roadmap opérationnelle

**Mise à jour : 25 octobre 2026.** Cette page est la **seule liste active de
priorités Compose**. Les livrables déjà fusionnés restent documentés dans Git ;
les anciens comptes rendus sont préservés dans
[archive du 24 octobre](archive/2026-10-24/roadmap.md).
Un merge ne prouve jamais qu'une application TrueNAS est déployée.

**Périmètre** : pfSense/Unbound, TrueNAS, Docker Compose, exporter/Prometheus,
Akvorado/NetFlow, Talos/Kubernetes, secrets runtime et services homelab.
Les sondes API, DTO et interfaces appartiennent à
[fastapi-sample](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md).
Les pages Next.js, icônes et cache du navigateur appartiennent à
[nabla-site-alban](https://github.com/AlbanAndrieu/nabla-site-alban).

## P0 — Collecte observabilité et sécurité des secrets

- [x] **Prometheus** : règle illisible corrigée sous UID 568, HTTP readiness 200.
  **Pyroscope** : metastore réinitialisé après sauvegarde horodatée,
  HTTP 200. Ne pas recommencer les resets sans preuve de nouvelle panne.
- [x] **Akvorado** : scrapes Inlet/Outlet UP, métriques présentes ;
  **Gatus**, **Redis**, **CrowdSec**, **pfSense exporter** UP au dernier
  inventaire opérateur. La santé d'un scrape ne prouve pas l'ingestion
  NetFlow → Kafka → ClickHouse.
- [ ] **PostgreSQL exporter** : conteneur absent et secret absent.
  Préparer un rôle SQL de monitoring sans privilèges d'administration ;
  matérialiser `DATA_SOURCE_NAME` depuis Vaultwarden dans le chemin dédié,
  vérifier `docker compose version` et `env_file.format: raw`. **Déploiement
  non effectué**. Accepter `up=1` et `pg_up=1` séparément.
- [ ] **FastAPI staging : scrape HTTP 401**. Après validation/déploiement
  [FastAPI #376](https://github.com/AlbanAndrieu/fastapi-sample/pull/376),
  provisionner la clé de scrape dédiée, puis seulement monter un
  `authorization.credentials_file` lisible par l'UID Prometheus 568.
  Ne jamais rendre `/metrics` public ni partager la clé diagnostics.
- [ ] **FastAPI Cloud HTTP 403** sur `/api/health-board` : diagnostic
  d'autorisation/proxy côté FastAPI, pas un échec démontré d'Akvorado.
  Valider la projection après déploiement du code au SHA exact.
- [ ] Vérifier ensuite les métriques **fonctionnelles** : NetFlow récent,
  consommation Kafka, écritures ClickHouse, Alertmanager et Mimir remote_write.

**Entrée opérateur :**
[observabilité et récupération](runbooks/2026-10-24-prometheus-pyroscope-dns-dot-recovery.md)
et [commandes de diagnostic](runbooks/2026-10-24-homelab-operator-next-commands.md).

## P0 — Résilience pfSense / DNS / réseau

- [ ] Corréler les OOM Unbound avec Snort, pfBlockerNG, PHP-FPM, CrowdSec
  et les tâches nocturnes **sans conclure à une causalité non prouvée**.
- [ ] Sauvegarder la configuration pfSense, puis valider une
  migration **progressive** de l'upstream Unbound vers DNS-over-TLS
  authentifié. Les overrides `int.albandrieu.com` restent locaux.
- [ ] Garder les scrapes pfSense lents (300 s) et les probes limités ;
  pas de relance ou de scan lourd sur Netgate 1100.
- [ ] Séparer le profil DNS de la workstation
  ([ansible-workstation](https://github.com/AlbanAndrieu/ansible-workstation))
  de la configuration serveur pfSense.

**Références :** [pfSense/Unbound/pfBlockerNG](runbooks/2026-10-24-pfsense-unbound-pfblocker-whatsapp.md),
[diagnostic pfSense](pfsense-diagnose-recover.md).

## P1 — Services TrueNAS et dépendances critiques

- [ ] **OpenRAG/Docling** : confirmer l'état App et conteneurs depuis
  TrueNAS, secret backend, Langflow global et OpenSearch, puis demander
  approbation avant tout démarrage ; ingestion synthétique avant données privées.
- [ ] **Sentry** : établir santé Taskbroker/Taskworker, Kafka lag et
  E2E frais ; ne pas réinitialiser les offsets pour corriger un faux rouge.
- [ ] **DefectDojo** : confirmer origine privée, TLS, uWSGI et droits
  minimaux avant intégration de nouveaux imports.
- [ ] Réconcilier catalog v2, Backstage/Gatus/AutoKuma, identité des
  services et secret matérialisé ; n'effectuer un cutover qu'avec rollback.
- [ ] Talos/NFS/CSI : vérifier le smoke inter-nœuds et les droits avant
  de planifier une migration de services.

**Références :** [Runbook commandes opérateur](runbooks/2026-10-24-homelab-operator-next-commands.md),
[Migration plateforme](homelab-platform-migration-roadmap.md),
[OpenRAG](../apps/openrag/README.md).

## P1 — Qualité locale et refactoring

- [ ] Refactoriser les diagnostics redondants en une entrée de lecture
  seule avec sélection explicite des services et états `PASS/FAIL/UNKNOWN`.
  Garder un budget réseau fixe, éviter les sorties de secrets et isoler
  chaque échec : un check en panne ne saute pas les autres.
- [ ] Utiliser des tests unitaires synthétiques, un rapport borné et
  la provenance par collecteur. Vérifier que les scripts sont exécutables
  dans Git sans toucher aux scripts bibliothèque sans shebang.
- [ ] Valider les changements sur un **worktree** local sans écraser
  les modifications préexistantes du dépôt opérateur. Aucune CI payante
  ne doit être lancée involontairement.

## Critères de clôture

Chaque entrée exige une preuve **runtime ou test du HEAD concerné**,
un propriétaire de dépôt unique, un statut de déploiement et un rollback
lorsqu'il y a mutation. `NOT_RUN` est distinct de `PASS`.
Les incidents résolus et commentaires par date restent en
[archive](archive/2026-10-24/) ou dans [incidents/](incidents/).

**Mode de travail de la présente PR** : quality gate complète volontairement
**NOT_RUN** sur demande de l'opérateur. Cela ne retire aucun contrôle de
publication et n'autorise aucun déploiement.
