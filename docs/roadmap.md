# Services Homelab — roadmap active

> **Consolidée le 22 novembre 2026 dans la [PR #437](https://github.com/AlbanAndrieu/nabla-compose/pull/437).** Cette page sert d'**index court des travaux encore ouverts**. Les 21 chantiers, leur propriétaire, l'effort indicatif, les arbitrages proposés et les preuves attendues sont dans le **[portefeuille H01–H21](roadmap-portfolio.md)** (source unique du backlog arbitrable). Procédures dans les runbooks, décisions dans les ADR et historique dans Git / [journal d'exécution du 21/11](runbooks/2026-11-21-roadmap-loop-state.md). Ne pas recopier les incidents ni considérer un merge comme une réception TrueNAS/Cloudflare.

**Dagger reste un POC expérimental**, jamais un substitut à la quality gate locale : les décisions et le contrôle de parité sont conservés dans l'[archive technique du 24/10](archive/roadmap-through-2026-10-24.md) ; voir également le skill `local-first-quality` et ses diagnostics avancés. Aucun changement de politique d'exécution n'est impliqué par la consolidation.

## Statuts et ordre de décision

- **CODED** : code source versionné, sans affirmation d'exécution ; **TESTED** : tests sur SHA identifié ; **DEPLOYED** : processus déployé observé ; **ACCEPTED (runtime)** : test fonctionnel réel, horodaté et réussi ; **PARTIAL** : réception incomplète ; **NOT_VERIFIED** : absence de preuve fraîche. `DENIED`, `NOT_RUN` et `UNVERIFIED` ne signifient jamais `DOWN`.
- **Nouvelle décision du 22/11 : H17 → Dependency-Track + outils CTEM (H13) → H05**, avec **H18 EnOcean/Somfy en étude active parallèle**. Les autres Apps H08, notamment Nexus/Joplin, ne sont pas urgentes. L'ordre H01 → H02 → H04 → H05 → H12 → H13 → H16 était celui du 14/11 ; il reste conservé comme référence historique du quality gate. Les gates CSI H01 et backup H02 sont atteints.
- **Arbitrage validé** : l'[ordre opérateur](roadmap-portfolio.md#ordre-opérateur--22-novembre-2026) est la source unique des priorités actuelles. Dependency-Track appartient au flux **CTEM H13** ; l'ID **H08** reste réservé aux autres Apps différées. Les reliquats H01/H02 sont repris dans H03/H09/H10/H16, sans deuxième migration CSI/backup.

## Ce qui est déjà reçu (ne pas relancer)

| Acquis | Preuve disponible | Reliquat, s'il existe |
| --- | --- | --- |
| **H01 CSI/NFS + Cilium** | 21/11 : PVC RWX lue sur un autre worker, reclaim ZFS/NFS, NetworkPolicy appliquée ; Falco 3/3 | Keycloak/Hermes, SPIRE et API TrueNAS sont des chantiers distincts H03/H08/H10/H16 |
| **H02 PostgreSQL backup** | 21/11 : 9 bases, cron quotidien, 3 restaurations isolées, TLS verify-full pour le backup | Rotation de l'identité `postgres_exporter` (H03/H09) |
| **Vaultwarden + correctif DNS** | 21/11 : Vaultwarden **1.37.5** healthy, adaptateur `bitwarden-api` healthy après suppression de surcharges Pi-hole obsolètes ; `talosconfig` et kubeconfig placés dans le coffre | Secrets applicatifs Keycloak/Joplin/Homarr toujours à matérialiser ; ne pas redéployer Vaultwarden 1.37.5 par réflexe |
| **pfSense retiré** | 18/11 : Freebox/R7000 remplace le pfSense ; #436 fusionnée le 22/11 retire l'ancien nœud HAProxy actif de la topologie | Revue DNS/Ingress H04, éventuel remplaçant H07 différé |
| **Hello via Traefik** | 22/11 : `nginx` dans `traefik_network` (`172.16.56.12`), commande `curl --fail-with-body --resolve` vers `:443` valide sans `-k` | Code HTTP exact, Gatus runtime et exposition WAN restent à mesurer |
| **MCP `truenas-readonly`** | 22/11 : clé dédiée `mcp_readonly` (READONLY_ADMIN), TLS vérifié, 19 outils en lecture (00f0bc7c) | portracker, 2FA et sortie de `auth.login_with_api_key` (H10) |
| **CTEM et catalogues déclaratifs** | PRs #421/#422/#431/#436 fusionnées ; contrats et projections V2 validés en CI | Amass LAN/externe réel, confrontation des contrôles Cloudflare et import DefectDojo validé |

## Travaux restant à réceptionner — lot d'exécution

### 1. H17 — terminer la migration Backstage V2 (P0)

**Code :** l'entité `sentry-edge` a une source canonique `apps/sentry/compose.yml` ; FastAPI Sample rapproche son conteneur `nginx` à toutes les Apps quand `appId` manque. La déclaration source a donc été précisée avec `appId: sentry` et un contrat V2 est ajouté. Le générateur doit synchroniser `catalog/services.json`, la topologie et les projections `catalog/generated` ; **ne pas modifier manuellement des JSON produits par le générateur**.

**Recette indépendante :** confronter `catalogRevision` et `entityRef` sur Compose, FastAPI Sample TrueNAS et site Alban ; vérifier `composeProfiles` (états `on_demand`), `sentry-edge = in_sync` sans autres `matchingApps`, puis rechercher tous les lecteurs V1 et ne supprimer les exports legacy **qu'après preuve de compatibilité et rollback**. Le Site a déjà la garde « aucun lecteur legacy » et Sample sait lire les projections V2 ; **les SHAs déployés restent à constater**. [Runbook H17](runbooks/h17-catalog-runtime-acceptance.md), [contrat](service-catalog-v2-normalization.md).

### 2. H13 — Dependency-Track et CTEM (P0, immédiat)

**Dependency-Track sort de H08.** Recevoir le `--check dependency-track` existant, le secret 0600, PostgreSQL partagé, la version des images (la déclaration actuelle autorise `latest`, **ne pas déployer sans épinglage et revue**), puis le statut API/GUI `:31083/:31084`, les scrapes et un **SBOM CycloneDX de test**, sans publication WAN. Import SCA privé sans confondre vulnérabilités SCA et actifs issus d'Amass. [Runbook Dependency-Track](runbooks/ctem-dependency-track-acceptance.md).

**CTEM** : réceptionner les deux points de vue Amass (LAN TrueNAS / extérieur GitHub autorisé), l'audit déclaratif LAN-only et la politique Cloudflare réelle ; qualifier les candidats avant tout scan actif et toute insertion DefectDojo ; déployer progressivement Cartography/Neo4j, Prowler, OASM et ingestion DefectDojo **avec tests de refus, RBAC et déduplication**. Aucun scan d'un réseau tiers ni import automatique des candidats. [CTEM](runbooks/ctem-external-exposure.md), [ADR 0004](adr/0004-ctem.md).

### 3. H05 — qualité de preuve, Gatus et Prometheus (P0)

Réceptionner le reload des règles et sondes Traefik/CrowdSec de [#436](https://github.com/AlbanAndrieu/nabla-compose/pull/436), les observations `app.query` et la fraîcheur/révision des sondes. Un `DENIED`, `NOT_RUN` ou un exporter `planned` ne devient pas `DOWN`. Le dernier relevé du 21/11 mentionne Gatus **68/68** et **11 cibles** `up=0` (10 `planned`, une Keycloak arrêtée) : à mesurer à nouveau. H04 reste un **contrôle de frontière** nécessaire aux preuves WAN, pas une raison de repousser H17/CTEM. [Sondes](runbooks/2026-11-04-probe-remediation.md).

### 4. H18 — EnOcean/Somfy : étude active parallèle (P1)

Le report P2 provenait de trois incertitudes **techniques**, non d'un arbitrage d'importance : l'USB branché est **Zigbee** (pas EnOcean USB300), les volets Flexom semblent io-homecontrol mais le pont local n'est pas confirmé, et H19 (migration de HA) reste bloqué par secrets/recorder. **Les diagnostics et l'inventaire radio n'ont pas à attendre H19.** Exécuter en lecture seule `diagnose-homeassistant.sh`, `diagnose-homeassistant-usb.sh` puis `diagnose-homeassistant-overkiz.sh --host <IP>` quand la passerelle est identifiée ; différer achat/réappairage/commande de volet jusqu'au choix documenté, et garder l'alarme en lecture seule. [Étude détaillée](roadmap-homeassistant-integrations.md).

### 5. H03/H04 — dépendances strictement nécessaires

Matérialiser les secrets de **Dependency-Track/CTEM** dans les fichiers root:root 0600, prouver l'authentification et l'isolation PostgreSQL sans exposer leurs valeurs ; Cloudflare DNS, Tunnel, AppSec et WAF sont validés par contrôles extérieurs négatifs et plans import-first, mais **aucun apply implicite**. WAF Vercel de Bababou : import fait, apply refusé le 22/11 (`payment_required`, OWASP Core Ruleset hors forfait), WAF inchangé ; décision du propriétaire : forfait Pro ou rate limiting seul ([runbook](../terraform/vercel-waf/README.md)). Vaultwarden 1.37.5 et son adaptateur étaient déjà sains au dernier relevé ; ne pas réinitialiser ces services.

### 6. H08 autres Apps et Nexus : non urgents

La [PR #438 Nexus](https://github.com/AlbanAndrieu/nabla-compose/pull/438), Joplin et les déploiements généraux restent suivis et sécurisés, mais ne prennent pas de capacité au chantier prioritaire H17/H13. NetBox était déjà en production le 21/11.

**Nexus, cache de paquets** (relevé du 22/11) : 3.92.3 Community, 9 dépôts Maven et NuGet seulement ; les dépôts de `terraform/nexus` (`apt-ubuntu-26-04`, `npm-all`, `pypi-all`, `docker-all`, `terraform-proxy`…) répondent 404, **jamais appliqués**.

- [x] proxy séparé `apt-ubuntu-26-04-security` (`security.ubuntu.com`, `resolute-security`), `CODED` le 22/11 ;
- [ ] `tofu plan` puis `apply` de `terraform/nexus` (jeton admin depuis Vaultwarden), relire la liste des dépôts ;
- [ ] accès HTTPS privé `nexus.int` et route publique CI via Traefik + CrowdSec (`nexus_tunnel_via_traefik`), `CODED` le 22/11 ([apps/nexus](../apps/nexus/README.md)) ; puis 3.98.3 après test de restauration de `cpool/nexus3` ;
- [ ] clients de la workstation (apt, npm, pip, uv) : `ansible-workstation`, `docs/workstation-nexus-package-cache.md`.

La [PR #437](https://github.com/AlbanAndrieu/nabla-compose/pull/437) continue le pin OpenClaw et les contrôles d'agents sans lancement automatique depuis le travail documentaire.

### 7. Autres chantiers conservés

**H16 Entra Nabla** — le 22/11, tenant personnel **confirmé par une sortie Azure CLI** fournie par l'opérateur ; deux YubiKeys signalées enrôlées, test FIDO2 non attesté indépendamment. P1 : tester la
connexion interactive FIDO2 principale + secours et le bon répertoire,
puis configurer les applications OIDC `entra-nabla-plan` /
`entra-nabla-apply` et le workspace HCP Free `entra-nabla-state`
avant tout plan/apply. Bootstrap OpenTofu de deux applications OIDC + Service Principals et FIC **CODED / NOT_APPLIED** (HCP Free non configuré, Graph consent en attente). [Skills Azure et Defender Free](security/entra-nabla-agent-skills-and-defender-free.md). Voir le [runbook](runbooks/entra-tenant-and-test-user.md).
Ce travail ne modifie pas l'ordre H17 → H13 → H05.

**H10 — RAM TrueNAS (23/11/2026)** — le message Slack « TrueNAS : RAM 9x % » venait du
heartbeat OpenClaw, qui ignorait l'ARC ZFS récupérable : corrigé et déployé
([nabla-openclaw#34](https://github.com/AlbanAndrieu/nabla-openclaw/pull/34), même
expression que `TrueNASHostOutOfMemory`). En régime normal : 84 %, PSI mémoire ≈ 0,
pas de swap. Mesuré le 23/11 sur 62 Gio : conteneurs ≈ 37,5 Gio (Sentry
`errors-only` 6,2, gateway OpenClaw 2,5, Wazuh 2,4, Nexus 2,1, OpenSearch 2,1),
3 VM Talos ≈ 9,5 Gio (H01), noyau ≈ 3,4 Gio. **Reste ouvert** : entre 01h et 06h,
l'usage atteint 91–93 % même en comptant l'ARC (processus +4 Gio, ARC réduit à 2,6 Gio),
sans conteneur dominant (pics cgroup : ClickHouse +1 Gio, gateway +0,8, mongo +0,5,
docling +0,4). Les heaps Java sont déjà plafonnés depuis le 06/11. Pour libérer au moins
4 Gio, il faut une décision du propriétaire : consolider OpenSearch et l'indexeur Wazuh,
mettre en pause OpenRAG (Langflow, Docling, OpenSearch : ≈ 4 Gio), ou réduire les
workers Talos hors des tests H01.

**H09** PostgreSQL `verify-full` ; **H10/H11** TrueNAS, IO et scripts ; **H12** OpenRAG/Docling/LiteLLM ; **H14/H06** tableaux de bord et budget ; **H16/H20** Entra/YubiKey/PKI et GitHub ; **H19** bascule réelle Home Assistant et recorder PostgreSQL ; **H21** FreshRSS/Langfuse. **H07/H15** restent différés (pfSense retiré et pile média VPN). Les statuts H01–H21 et les critères précis sont dans le [portefeuille](roadmap-portfolio.md), unique backlog arbitrable.

**Détection de dérive OpenTofu (23/11/2026) — CODED, NOT_RUN** : rien ne
signalait qu'un `apply` manquait (`cloudflaretokens` modifié par `PUT` d'API,
`nexus` #438 et `github` #424 jamais appliqués). `scripts/infra/opentofu-drift-check.py`
planifie chaque jour `origin/master` contre la prod pour `cloudflare`,
`cloudflaretokens`, `nexus` et `github` (`plan -detailed-exitcode`, jamais
d'`apply`) et remonte la dérive à Alertmanager (`OpenTofuDrift`) et par courriel
du cron. Hébergement TrueNAS et inclusion de `cloudflaretokens` validés par le
propriétaire le 23/11. **À faire par le propriétaire** : clé Garage en lecture,
jetons en lecture seule dans `/mnt/cpool/secrets/runtime/opentofu-drift/`, premier
passage manuel puis `--enable` du cron
([procédure](infrastructure-bootstrap.md#drift-detection-read-only)).
`entra` et `defender-free` restent hors périmètre (`NOT_APPLIED` volontaire).

**H16 / P1 — recette du POC verrouillage PostgreSQL à déléguer (NOT_RUN)** :
un agent disposant réellement de la workstation doit exécuter le
[mandat de test isolé](security/opentofu-postgresql-private-locking-poc.md#mandat-pour-un-autre-agent--recette-exécutable)
sur une **instance PostgreSQL jetable accessible uniquement par socket Unix ou
127.0.0.1**. Prouver un seul détenteur du verrou `pg` entre deux clients
OpenTofu, le refus du concurrent, la récupération après interruption, les ACL,
la sauvegarde/restauration isolée, et **aucune exposition WAN**.
Conserver Garage pour tous les états locaux et HCP Free pour Entra jusqu'à
un nouvel arbitrage ; ne lancer aucun `init -migrate-state`.
**Owner : agent workstation autorisé ; preuve attendue : rapport daté, SHA,
commandes expurgées, PASS/FAIL/BLOCKED par test et rollback.**
Cette recette **ne modifie pas** la priorité opérateur H17 → H13 → H05.

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

**Critère de clôture** : résultat négatif/protection attendu réellement observé, état après action, horodatage, version et retour arrière. Ne pas transformer un timeout fournisseur en `DOWN`, ni considérer une règle WAF/Access écrite mais non appliquée comme une défense effective. Arbitrage décidé et portes de réception : [portefeuille](roadmap-portfolio.md#ordre-opérateur--22-novembre-2026).

## Dernière priorité — IPv6 Freebox / R7000 / homelab (reporté le 22/11/2026)

**Décision opérateur : IPv6 est reporté en toute fin de roadmap, après les autres chantiers.**
Ne pas réactiver l'IPv6 du Netgear R7000 ni modifier la délégation Freebox,
le routage de la workstation, le pare-feu TrueNAS ou les règles Cloudflare
à l'occasion d'un autre chantier. L'IPv4 reste le chemin de production.

À la reprise (H04 réseau / H10 TrueNAS), établir d'abord l'état réel de la
Freebox et des préfixes délégués ; vérifier le next hop WAN du R7000, ses
annonces RA/SLAAC et la résolution NDP depuis la workstation. Le 22/11, après
la désactivation d'IPv6 sur le R7000, les voisins de l'ancienne passerelle
LAN (`fe80::120c:6bff:fe62:128e` et `…:3c01::1`) étaient `FAILED`, et
`tracepath -6` échouait au premier saut (`!H`) : **aucune route IPv6
fonctionnelle n'est actuellement démontrée**. Ne pas réutiliser un préfixe
historique ni autoriser un /64 complet à une application par défaut.

Avant toute activation sur TrueNAS : vérifier le filtrage IPv6 entrant,
le garde `scripts/truenas/ipv6-guard.nft`, les tests de non-exposition depuis
l'extérieur et le retour arrière. Conserver les détails techniques dans le
[runbook Freebox/R7000](pfsense/runbooks/freebox-router-mode.md) ; ce report
n'est ni une preuve de réception, ni une tâche à exécuter maintenant.

## Recommandations de la passe du 2026-11-23
- Prioriser H17 et H13, différer H08.
- Garder contrôle de secrets dans Vaultwarden.
- Ne pas activer IPv6 avant arbitrage final.
