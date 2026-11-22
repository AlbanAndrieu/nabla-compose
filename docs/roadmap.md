# Services Homelab — roadmap d'exécution active

> **Consolidée le 22 novembre 2026 dans la [PR #437](https://github.com/AlbanAndrieu/nabla-compose/pull/437).** Cette page sert d'**index court des travaux encore ouverts**. Les 21 chantiers, leur propriétaire, l'effort indicatif, les arbitrages proposés et les preuves attendues sont dans le **[portefeuille H01–H21](roadmap-portfolio.md)** (source unique du backlog arbitrable). Procédures dans les runbooks, décisions dans les ADR et historique dans Git / [journal d'exécution du 21/11](runbooks/2026-11-21-roadmap-loop-state.md). Ne pas recopier les incidents ni considérer un merge comme une réception TrueNAS/Cloudflare.

## Statuts et ordre de décision

- **CODED** : code source versionné, sans affirmation d'exécution ; **TESTED** : tests sur SHA identifié ; **DEPLOYED** : processus déployé observé ; **ACCEPTED** : test fonctionnel réel, horodaté et réussi ; **PARTIAL** : réception incomplète ; **NOT_VERIFIED** : absence de preuve fraîche. `DENIED`, `NOT_RUN` et `UNVERIFIED` ne signifient jamais `DOWN`.
- **Séquence approuvée le 14/11** : **H01 → H02 → H04 → H05 → H12 → H13 → H16**. Les gates **H01 CSI/NetworkPolicy** et **H02 sauvegarde/restauration** sont atteints selon les preuves du **21/11** ; ne pas refaire ces migrations. Le **prochain point d'entrée effectif est H04/H05**, et H03 (secrets) est un prérequis transversal. La séquence historique reste conservée telle quelle pour les contrôles automatisés.
- **Aucune nouvelle priorité autorisée implicitement** : le [tableau d'arbitrage proposé](roadmap-portfolio.md#arbitrage-proposé--à-valider-22-novembre-2026) est un choix à confirmer. Le reste H01/H02 (Keycloak, rotation `postgres_exporter`) est suivi **dans H03/H08/H09/H10/H16**, pas comme une seconde migration CSI/backup.

## Ce qui est déjà reçu (ne pas relancer)

| Acquis | Preuve disponible | Reliquat, s'il existe |
| --- | --- | --- |
| **H01 CSI/NFS + Cilium** | 21/11 : PVC RWX lue sur un autre worker, reclaim ZFS/NFS, NetworkPolicy appliquée ; Falco 3/3 | Keycloak/Hermes, SPIRE et API TrueNAS sont des chantiers distincts H03/H08/H10/H16 |
| **H02 PostgreSQL backup** | 21/11 : 9 bases, cron quotidien, 3 restaurations isolées, TLS verify-full pour le backup | Rotation de l'identité `postgres_exporter` (H03/H09) |
| **Vaultwarden + correctif DNS** | 21/11 : Vaultwarden **1.37.5** healthy, adaptateur `bitwarden-api` healthy après suppression de surcharges Pi-hole obsolètes ; `talosconfig` et kubeconfig placés dans le coffre | Secrets applicatifs Keycloak/Joplin/Homarr toujours à matérialiser ; ne pas redéployer Vaultwarden 1.37.5 par réflexe |
| **pfSense retiré** | 18/11 : Freebox/R7000 remplace le pfSense ; #436 fusionnée le 22/11 retire l'ancien nœud HAProxy actif de la topologie | Revue DNS/Ingress H04, éventuel remplaçant H07 différé |
| **Hello via Traefik** | 22/11 : `nginx` dans `traefik_network` (`172.16.56.12`), commande `curl --fail-with-body --resolve` vers `:443` valide sans `-k` | Code HTTP exact, Gatus runtime et exposition WAN restent à mesurer |
| **CTEM et catalogues déclaratifs** | PRs #421/#422/#431/#436 fusionnées ; contrats et projections V2 validés en CI | Amass LAN/externe réel, confrontation des contrôles Cloudflare et import DefectDojo validé |

## Travaux restant à réceptionner — lot d'exécution

### 1. H03 + H04 — secrets et frontière réseau P0

**H03 (prérequis)** : matérialiser les fichiers 0600 autorisés Keycloak, Joplin et Homarr, valider leur lecture par la bonne App, les refus sans clé et la rotation `postgres_exporter`. Le coffre et `bitwarden-api` sont déjà sains **au dernier relevé du 21/11** ; ne pas confondre coffre opérationnel et secrets complets. [Backlog de migration](runbooks/2026-11-10-secrets-migration-backlog.md).

**H04 (environnement public)** : la [PR #436](https://github.com/AlbanAndrieu/nabla-compose/pull/436) est **fusionnée** : routeurs honeypot Traefik/CrowdSec, IP de confiance du Tunnel, AppSec, rate limiting, sondes Gatus et règles Prometheus **CODED**. Toutefois `login.albandrieu.com` n'avait pas de CNAME externe après retrait de l'A périmé lors du dernier constat ; `honeypot_tunnel_via_traefik=false` est le rollback par défaut. Ne déployer qu'après revue du plan import-first Cloudflare/Garage, puis mesurer **depuis Internet** les accès autorisés et refusés, SNI, IP réelle, `403` AppSec, `429`, absence de route `/realms/master` et maintien du DNS `s3.int` public **explicitement voulu**. [Cloudflare](../terraform/cloudflare/README.md), [Honeypot](../apps/honeypot/README.md), [CrowdSec](../apps/crowdsec/README.md). Le GET statique de [nabla-site-alban #338](https://github.com/AlbanAndrieu/nabla-site-alban/pull/338) ne transmet ni identifiant ni formulaire.

**Sous-lots H04 séparés** : politique mail SPF/DMARC/MTA-STS sur 20 zones (**CODED, apply non prouvé**), inventaire Access orphelin, règles Vercel WAF Bababou [#433](https://github.com/AlbanAndrieu/nabla-compose/pull/433) (SQLi/XSS/RCE et quotas, **non appliqués selon le dernier constat**) ; chacun demande plan sans destructions inattendues et tests de faux positifs. Un DNS public seul ne prouve pas un routage réel. Aucun port WAN ne doit être ouvert par la réconciliation documentaire.

### 2. H05 + H17 — observabilité, CTEM et catalogue P0

- **Sondes** : réceptionner `promtool check config`, recharger Prometheus, confirmer Gatus HTTPS Hello et `/healthz` honeypot, `up{job="traefik"}` et `up{job="crowdsec"}`, LAPI, Alertmanager et la vraie réponse AppSec. L'ancien diagnostic du 21/11 : Gatus **68/68**, Prometheus **11 cibles `up=0`**, dont **10 `planned`** et **Keycloak à l'arrêt faute de secrets**. Recontrôler à la date du test ; ne pas déclarer 11 services en panne. [Sondes](runbooks/2026-11-04-probe-remediation.md).
- **CTEM** : déclencher la campagne Amass externe uniquement avec autorisation et une collecte TrueNAS confinée ; comparer `catalogRevision`, fenêtre temporelle et comptes ; garder les noms en stockage privé. Aucun candidat n'est une vulnérabilité sans validation. [Runbook CTEM](runbooks/ctem-external-exposure.md).
- **H17 / Backstage V2** : vérifier les projections et `composeProfiles` sur **trois versions déployées** (Compose, FastAPI Sample et site Alban), identité `sentry-edge`, provenance `entityRef`/`catalogRevision`. Supprimer les derniers consommateurs V1 seulement après test de parité, pas à la seule fusion des PRs. [Contrat V2](service-catalog-v2-normalization.md).

### 3. H08 + H11 — Nexus et OpenClaw en cours de PR

- **[Nexus #438](https://github.com/AlbanAndrieu/nabla-compose/pull/438) — H08/H04** : APT security, npm/pip/uv cache privé `nexus.int` et CI Maven publique protégée par Access, Traefik et CrowdSec ; **CODED / NOT_DEPLOYED**. Après fusion, vérifier d'abord les realms d'administration, le TLS LAN, la non-régression de la route Tunnel initiale, les imports du state Nexus et les clients Workstation. [Runbook Nexus](../apps/nexus/README.md).
- **[OpenClaw #437](https://github.com/AlbanAndrieu/nabla-compose/pull/437) — H11/H20** : sous-module `fe43cc3`, devbox Node 24 et passes de roadmap de **01h à 05h** sur cinq dépôts ; CI GitHub verte au début de la consolidation, **pas de preuve d'application TrueNAS**. Après fusion : synchroniser sous-module, contrôler Squid egress, quotas/token budget, permission minimale de la GitHub App, **réutilisation d'une PR ouverte + rebase avant push**, quality gates et interdiction des merges automatiques. Le code OpenClaw reste maintenu dans `nabla-openclaw` ; Compose n'héberge que le runtime. [Journal de boucle](runbooks/2026-11-21-roadmap-loop-state.md).
- **H08 autres Apps** : Dependency-Track puis Joplin, Keycloak/Hermes et H19 Home Assistant seulement après leurs secrets, base et rollback ; NetBox était déjà `RUNNING` au 21/11. [Déploiement Apps](runbooks/2026-11-06-catalog-apps-to-compose.md).

### 4. P1 — Fiabilisation et services fonctionnels

**H09** : généraliser `verify-full`, CA/SAN et rotation PostgreSQL client par client (H02 disponible comme reprise). **H12** : ingestion OpenRAG/Docling, embeddings GPU workstation via proxy LiteLLM TrueNAS, repli CPU `qwen-cpu`, clé virtuelle dédiée et isolation du corpus. **H13** : import DefectDojo des *findings qualifiés* seulement, compte RBAC limité, asynchronisme et déduplication. **H06/H14** : budget FastAPI Cloud, UX OWNER, compteurs Grafana/ZFS, OTLP, puis trancher `app.stats` par App vs cAdvisor allégé (TrueNAS netdata ne fournit pas directement les séries par App).

**H10/H11** : analyser les pics IO ZFS vers 04h, sécuriser les accès Docker Socket, terminer les scripts déportés, vérifier MCP et 2FA TrueNAS, préparer TrueNAS 27 final puis la suppression de `auth.login_with_api_key` avant TrueNAS 28. **H16/H20** : séparer App GitHub de gouvernance de l'App de release, pilote Entra Free/HCP Free, Vault PKI/OIDC, YubiKey et webhook HMAC avec refus négatif. **H21** : FreshRSS/GReader + Langfuse + LiteLLM après H03/H12/H17. Chaque détail et sa preuve de clôture sont dans le [portefeuille](roadmap-portfolio.md).

### 5. P2 / différé explicitement

**H07** pfSense et migration vers un nouveau routeur (aucun équipement remplaçant choisi) ; **H15** pile média VPN et anonymisation ; **H18** EnOcean/Somfy. Pas d'installation, achat ni exposition WAN par défaut. **H19** Home Assistant est P1 mais sa bascule reste conditionnée à la sauvegarde des documents, aux secrets, aux `trusted_proxies` et au recorder PostgreSQL.

## Frontières de responsabilité et validation

| Dépôt | Responsabilité canonique |
| --- | --- |
| `nabla-compose` | Infrastructure TrueNAS/Talos, GitOps, edge, DNS, secrets, Prometheus/Gatus, générateurs Backstage V2 et smokes |
| [`fastapi-sample`](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) | Fxx : sondes, états et preuves datées, Cloud/OWNER, ingestion CTEM/DefectDojo, budget et UI FastAPI |
| [`nabla-site-alban`](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/homelab-roadmap.md) | Interface Next.js et affichage du catalogue ; ne pas réimplémenter les sondes ni gérer l'infra |
| [`nabla-openclaw`](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md) | Agent, scripts et cadence ; consommation de secrets uniquement par frontières approuvées |
| [`ansible-workstation`](https://github.com/AlbanAndrieu/ansible-workstation) | Système workstation, clients des proxys Nexus/LLM, contrôle local et durcissement |
| [`nabla-site-bababou`](https://github.com/AlbanAndrieu/nabla-site-bababou/blob/master/docs/roadmap.md) | Site, documentation et ZAP ; règles WAF Vercel déclarées côté Compose |

**Contrat d'une PR** : chercher la PR existante, vérifier son rebase sur `master`, corriger les conflits, exécuter les quality gates sur le HEAD exact, puis noter séparément preuves `CODED` / `TESTED` / `DEPLOYED` / `ACCEPTED`. Les suppressions volumineuses ne bloquent plus la quality gate ; les tests, secrets et références restent contrôlés. Ne pas pousser des micro-changements sans valeur de stabilité ni réutiliser un ancien runbook d'incident pour muter la production.

**Critère de clôture** : résultat négatif/protection attendu réellement observé, état après action, horodatage, version et retour arrière. Ne pas transformer un timeout fournisseur en `DOWN`, ni considérer une règle WAF/Access écrite mais non appliquée comme une défense effective. Arbitrage détaillé et portes de réception : [portefeuille](roadmap-portfolio.md#arbitrage-proposé--à-valider-22-novembre-2026).
