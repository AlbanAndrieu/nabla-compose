# Services Homelab — roadmap active

> Mise à jour : **26 octobre 2026**. Source d'autorité pour le travail restant
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

## P0 — Reprise FastAPI / IA / Bababou sans LAN (26 octobre 2026)

**Accès au LAN rétabli : 26 octobre 2026, déclaration opérateur.**
La configuration Git reste distincte de la santé réelle des conteneurs :
reprendre d'abord les contrôles en lecture seule, puis les tests avec
identités restreintes. Aucun déploiement, redémarrage, appel à un modèle
payant ni ingestion de `cpool/bababou` sans validation dédiée.
Continuer en PR #285, local-first et commits `[skip ci]`.

| Liaison / chantier | Source Git vérifiée | Statut / prochaine preuve |
| --- | --- | --- |
| FastAPI TrueNAS → LiteLLM | `LITELLM_URL=http://172.17.0.24:4000`, `DEFAULT_CHAT_MODEL=fastapi-qwen` ; la sonde exécutée dans FastAPI retourne `litellm=http_200` | **HTTP REACHABLE / AUTH NOT_VERIFIED** : clé scoped, modèle réellement exposé, upstream workstation et tool calling restent à valider |
| LiteLLM TrueNAS → workstation | `apps/litellm/config.yaml`: `fastapi-qwen` vers `LITELLM_WORKSTATION_API_BASE` / `LITELLM_FASTAPI_WORKSTATION_API_KEY` | **CONFIGURED / RUNTIME NOT_VERIFIED** ; l'upstream GPU n'est pas un repli TrueNAS garanti |
| Ollama TrueNAS | Depuis FastAPI : `GET http://172.17.0.24:30068/api/tags` retourne **HTTP 200** | **HTTP REACHABLE / MODELS NOT_VERIFIED** : HTTP 200 ne prouve ni un modèle chargé ni le fallback FastAPI |
| FastAPI → OpenRAG | Backend `openrag-backend:8000/health` retourne **HTTP 200** depuis FastAPI ; frontend `/mcp` reste `unverified` et la recherche filtrée reste `not_tested_requires_auth` | **BACKEND REACHABLE / MCP NOT_VERIFIED** : diagnostiquer frontend, auth X-API-Key et `filter_id` privé. PR FastAPI #378 fusionnée, code seulement |
| OpenRAG → Bababou | `apps/openrag/compose.yml`: `cpool/bababou` monté read-only dans le backend sur `/mnt/bababou` | **MOUNT DECLARED / INDEX NOT_VERIFIED** : valider l'index privé séparé, sélection autorisée, recherche citée et suppression avant usage |
| Diagnostics Prometheus | `reconcile-fastapi-metrics-credential.py --apply` puis `--check` retournent **`credential_ready=true`** sur TrueNAS | **SECRET INSTALLED / RUNTIME NOT_VERIFIED** : vérifier variable FastAPI active, bind du fichier Prometheus, puis `fastapi_sample: state=scrape_up targets_up=1` |

**Preuves opérateur actualisées (26/10) :** le secret Prometheus est
`credential_ready` après installation ; sans `--ssh-sudo`, Docker refuse
l'accès au socket (`docker_socket_denied`). Avec `--ssh-sudo`, les
sondes exécutées **depuis le conteneur FastAPI** donnent
`litellm=http_200`, `ollama=http_200`,
`openrag_backend=http_200`, `openrag_mcp=unverified`,
`openrag_search=not_tested_requires_auth`. Aucune clé, requête de
modèle ni recherche privée n'a été validée. **Ne pas redéployer le
homelab pour un simple HTTP 200 ; confirmer les contrats actifs.**

**Avancement code en cours :** la PR Compose #285 fournit
`scripts/truenas/diagnose-fastapi-ai-chain.py --check` (inventaire Git
hors LAN), et son mode `--runtime` opt-in quand l'accès est rétabli.
La PR FastAPI #378 fournit un chemin de recherche OWNER-only, sans
activation automatique, plus des tests de refus. L'OpenRAG v0.7.1 upstream
déclare `/mcp` et `openrag_search(filter_id)`, mais l'image réellement
déployée reste à vérifier. **Aucun résultat Bababou n'a été consulté.**

**Gates de livraison IA (code ≠ runtime).**
- [x] **FastAPI → LiteLLM**, configuration déclarée : URL TrueNAS `:4000`,
  alias `fastapi-qwen` et fichier `sample/.env.secrets` non suivi par Git.
  Les clés virtuelles, le budget et les capacités de tool calling restent
  **NOT_VERIFIED** tant que le LAN est inaccessible.
- [x] **OpenRAG lecture OWNER**, implémentation privée en PR FastAPI #378 :
  `POST /private/ops/ai/bababou/search` appelle seulement
  `openrag_search` avec un `filter_id` imposé côté serveur.
  Le chemin général `/run` ne reçoit pas le corpus privé.
- [ ] **Activer le client MCP** : résoudre le vrai `/mcp` et sa politique
  d'authentification sur l'image OpenRAG déployée, configurer
  `MCP_CLIENTS` et `OPENRAG_BABABOU_FILTER_ID` comme secrets
  contrôlés. Ne pas supposer qu'une clé `X-API-Key` est effectivement
  exigée par OpenRAG 0.7.1 sans preuve.
- [ ] **Sélection de corpus** : vérifier filtre, index distinct, ACL,
  citations/page et suppression, puis indexer uniquement les documents
  Bababou explicitement autorisés. Le montage ZFS read-only ne signifie
  pas indexation.
- [ ] **Confidentialité de l'inférence** : le modèle `fastapi-qwen`
  utilise actuellement l'upstream workstation `172.17.0.57:4000/v1`.
  Ne jamais lui envoyer des extraits Bababou avant vérification du
  traitement local, de la rétention des prompts et de l'absence
  de trace Langfuse / tiers. Pour le corpus privé, privilégier
  un modèle Ollama TrueNAS validé et une identité LiteLLM dédiée ;
  ne pas activer un fallback inter-modèles non contrôlé.
- [ ] **E2E différé** : sur LAN rétabli, vérifier d'abord la résolution
  réseau et les réponses saines, ensuite les clés et scopes, puis un
  document synthétique avec citations, enfin un sous-ensemble privé
  approuvé. Toujours refuser et classer `UNVERIFIED` hors de ces preuves.

**Accès et confidentialité du corpus.** Le montage ZFS ne crée ni index
ni API de recherche. La recherche Bababou doit exiger une identité OWNER
ou service scoped, une séparation de corpus et des citations. Ne pas
exposer le corpus privé sur `/run` public ni à FastAPI Cloud, `nabla-site-alban`,
un endpoint RAG anonyme ou des logs LLM/Langfuse. Sans ACL validée,
afficher `NOT_VERIFIED` au lieu de répondre à partir de documents privés.

**Limite de preuve runtime :** la copie du secret est prête,
mais le `METRICS_SCRAPE_KEY` effectivement chargé par FastAPI,
le montage `/run/secrets/fastapi-sample-metrics.key` dans
Prometheus et le scrape `up{job="fastapi_sample"}=1` restent
**NOT_VERIFIED**. La recherche Bababou reste bloquée sur
authentification, filtre et index privé.

**Diagnostics améliorés (code PR #285)** : la sonde SSH distingue désormais
`docker_socket_denied`, `sudo_noninteractive_denied`,
`docker_daemon_unavailable`, `fastapi_container_missing`,
`fastapi_container_not_running`, `fastapi_container_python_missing`,
`docker_cli_missing`, `docker_exec_failed` et
`probe_output_invalid`. Une option `--ssh-sudo` est disponible **uniquement
si** le compte possède déjà les droits `sudo -n docker`.
Le faux `GET /search/health` OpenRAG est supprimé :
`openrag_search=not_tested_requires_auth` tant qu'une recherche
authentifiée, filtrée et autorisée n'est pas exercée.
Les statuts restent des preuves de transport et non d'accès au corpus.

Un HTTP 401/403 sur MCP ou LiteLLM confirme seulement la barrière
d'accès ; il faut une preuve *authentifiée* de la bonne clé et du bon
modèle pour passer à ACCEPTED.

**Gate de reprise LAN, dans cet ordre :** (1) réseau/service LiteLLM et
clé dédiée ; (2) modèle `fastapi-qwen` et capacité tool-calling ;
(3) Ollama TrueNAS `/api/tags` sans texte généré ;
(4) OpenRAG backend/OpenSearch/Langflow/Docling ;
(5) découverte MCP/API réelle et droits du corpus ;
(6) recherche de document synthétique et citations ;
(7) sous-ensemble privé Bababou explicitement approuvé. Aucune
indexation, rotation, diffusion de PII ou redéploiement automatique.

[Architecture RAG](runbooks/rag-bababou-poc-architecture.md) ·
[LiteLLM FastAPI](runbooks/fastapi-sample-litellm.md) ·
[Diagnostics OpenRAG](runbooks/openrag-babou-ingestion-diagnostics.md) ·
[Acceptation FastAPI IA/RAG](runbooks/fastapi-truenas-ai-bababou-20261026.md).

## P0 — TrueNAS redevient réactif après arrêt de Netdata (26 octobre)

**Observation opérateur :** Netdata a été arrêté, puis TrueNAS a
recommencé à répondre. Cette chronologie suggère une pression sur
l'hôte, mais ne permet pas d'attribuer l'OOM, le ralentissement ou
un blocage I/O à Netdata seul. Aucun prélèvement avant son arrêt
n'est disponible.

- [x] **Code de diagnostic :** nouveau
  `scripts/truenas/diagnose-truenas-pressure.py` :
  double snapshot MemAvailable, CPU/memory/I/O PSI,
  événements `oom_kill`, swap, direct reclaim et
  ZFS ARC, puis classement des conteneurs Docker par CPU et
  mémoire avec timeout. Mode `--skip-docker` pour une machine
  déjà en forte contention ; aucune mutation.
- [x] **Qualité locale :** 15/15 tests hermétiques PASS sur
  l'environnement agent ; exécution sur TrueNAS **NOT_VERIFIED**.
- [ ] **Réception LAN :** baseline hôte pendant que Netdata reste
  arrêté, classement Docker lorsque TrueNAS répond, puis revue
  des processus QEMU et des latences ZFS.
- [ ] **Cause racine :** confirmer ou écarter pression mémoire,
  swap/OOM, I/O stall et charge CPU ; distinguer limitation
  conteneur et pression physique. Aucune réduction ARC ni
  suppression de service sans preuve.

[Runbook TrueNAS / Netdata](runbooks/truenas-host-service-pressure-20261026.md).

## Priorités opérationnelles et preuves

| Ordre | Domaine | Contrôle à valider | État |
| --- | --- | --- | --- |
| 1 | Prometheus | Configuration corrigée (0640), 21 targets UP, 7 DOWN | **Serveur sain, collecte dégradée** |
| Suivi | OpenRAG / LiteLLM | Contrôles ciblés OpenRAG (`startup`, `ai-runtime-recovery`, `opensearch-legacy-secret`, `backstage-bundle`) tous PASS ; fichiers OpenRAG/LiteLLM `ready=true` | **5/5 côté configuration ; authentification/rechargement runtime NOT_VERIFIED** |
| 2 | Akvorado | Dernière preuve : `metadata missing` sur les nouveaux flux, aucun lot ClickHouse confirmé | **Ingestion non acceptée, vérifier mapping ifIndex et Outlet chargé** |
| Suivi | Sentry et DefectDojo | Smoke métier / E2E après sondes PASS | **NOT_VERIFIED E2E** |
| Indépendant | pfSense / Unbound | **2 causes d'interruption confirmées** : OOM noyau (17/22/24 oct.) et marqueurs explicites stop/start Unbound par pfBlockerNG DNSBL (22/23/24 oct., vers 00:04). Raison du choix stop/start et processus à l'origine du pic RAM inconnus | **OOM_CONFIRMED / DNSBL_STOP_START_REPORTED / UPSTREAM_CAUSE_PENDING** |
| Différé | Workstation split-DNS | DNS pfSense/Pi-hole corrects, NSS privé indisponible via Quad9 ; 19 tests de diagnostic PASS opérateur | **Correction reportée par décision utilisateur ; ne pas modifier la workstation** |

**Dernière preuve datée :** [second relevé du 25 octobre](runbooks/2026-10-25-critical-acceptance-followup.md) — `PASS=9 FAIL=7 WARN=0 SKIP=0` (contre [8/8 au premier relevé](runbooks/2026-10-25-critical-acceptance-evidence.md)) ; révision du checkout TrueNAS inconnue. Une réussite de sondes sur Sentry ou DefectDojo ne prouve pas la disponibilité E2E. Les 85 sondes Gatus déclarées ne représentent pas 85 services opérationnels : [diagnostic spécialisé](runbooks/2026-10-25-homelab-operator-diagnostics.md).

**Dernière preuve ciblée (25/10) :** `triage-critical-failures.sh --check` → **PASS=5 FAIL=2 UNVERIFIED=0**, dossier privé `focused-4SkRmq`. L'App OpenRAG, ses fichiers et le comparateur OpenSearch sont PASS après la correction `legacy_env` **UID=0, GID=568, mode=0640** ; deux gates restent ouvertes : `prometheus-targets` et `akvorado-fresh-inserts`. La vérification des authentifications et la suppression des chemins hérités **ne sont pas attestées**. [Runbook daté](runbooks/2026-10-25-critical-acceptance-followup.md).

**Troisième preuve ciblée (25/10) :** [deux sessions à 1 PASS / 6 FAIL](runbooks/2026-10-25-critical-acceptance-followup.md) avant réparation Prometheus `0644 → 0640`. Les résultats individuels du serveur Prometheus et d'Akvorado détaillent désormais les causes ; aucun E2E de migration n'est clos. Ne pas réutiliser les anciens états 9/7 comme preuve actuelle.

## P0 — Accepter les services critiques

| ID | Domaine | Dernière preuve datée, sans extrapolation | Condition d'acceptation |
| --- | --- | --- | --- |
| H-01 | OpenRAG | Quatre gates OpenRAG du triage `PASS` ; secret OpenRAG/LiteLLM `ready=true` et mot de passe déclaré identique dans deux candidats ; conteneur OpenSearch exact distinct non encore attesté | App `RUNNING`, backend et frontend `running+healthy`, authentifications Langflow/OpenSearch et modèles LiteLLM testés |
| H-02 | Sentry | **Preuve plus récente 26/10 :** `recover-sentry-deploying.sh --check` valide les secrets système/Relay, l'utilisateur ClickHouse `sentry`, le migrator et `diagnose-sentry exit=0 ok=14 failed=0 warnings=0` | **Préflight + diagnostic PASS** ; ingestion d'un nouvel événement Relay → Kafka → Snuba → ClickHouse **NOT_VERIFIED**, sans nouveau redeploy |
| H-03 | DefectDojo | **Preuve plus récente 26/10 :** frontend/uWSGI RUNNING ; DNS privé/HTTPS TLS vérifiés ; depuis workstation, `curl --location` retourne `http=200 redirects=1 tls=0` | **Transport + page HTTP accessibles** ; authentification Django et parcours utilisateur **NOT_VERIFIED**. Aucun redeploy nécessaire à cette preuve |
| H-04 | pfSense / Unbound | **Deux mécanismes prouvés** : OOM noyau (dernier visible **25/10 22:12 CET** avant cutover PHP-FPM) et **nouveau PID Unbound `19252` → `2611`, lancé le 26/10 à 00:04:32 CET** pendant les marqueurs pfBlockerNG stop (~00:04:25) / start (~00:04:37) ; sortie DNSBL Python 00:04:30. **Hashes Unbound + INI legacy inchangés** depuis 23:56 ; Unbound Control REACHABLE à 00:12, free+inactive ~167 Mio, pas de nouvel OOM dans la fenêtre retenue. Profil PHP-FPM 4/30/1/2/500 confirmé précédemment, Snort AC-BNFA. **65/65 tests offline initiaux PASS, puis 56/56 Unbound PASS ; 64/64 Unbound/capture/compare PASS ; comparaison réelle 00:40:15→00:40:22 validée, PID 2611 stable et hashes MATCH**. | **P0 :** nouvelle sonde DNS LAN bornée dans PR #285 (73/73 tests déclarés PASS par opérateur avant les derniers changements ; nouvelle gate de 18 tests LAN à exécuter localement) ; capture/compare fiable et reconstitution des changements antérieurs ; diagnostiquer pourquoi pfBlockerNG `3.2.17_1` exige un stop/start même sans modification des deux fichiers vérifiés ; précontrôler DNS split valide et mesurer 00:04 (non mesurée). **P1 :** identifier le pic RAM / `php_pfb` lors des OOM, stabiliser marge mémoire sous cron Snort et documenter bouncer CrowdSec. **P2 :** confirmer accès GUI/pfREST, DNS privé LAN. |

Actions :
- [ ] **H-01 :** exécuter `diagnose-openrag-startup.sh --check`,
  `diagnose-openrag-dependencies.sh --check` et
  `reconcile-openrag-opensearch-secret.sh --check` depuis TrueNAS.
- [ ] **H-01 :** accepter backend/frontend et les authentifications sans
  régénérer de clé ni indexer le corpus `cpool/bababou`.
- [ ] **H-02 :** contrôler les deux consommateurs avec
  `diagnose-sentry-consumers.sh --check` et le smoke Sentry déjà versionné.
- [ ] **H-03 :** depuis TrueNAS, exécuter
  `sudo bash scripts/truenas/diagnose-defectdojo.sh --check`.
  Le script indique **séparément** les anomalies d'origine HTTP,
  de réseau Traefik, de DNS Pi-hole/Unbound et de HTTPS SNI/TLS,
  sans fuite de secret ni redéploiement. Depuis la workstation,
  exécuter `bash scripts/workstation/diagnose-defectdojo-lan.sh --check`
  pour identifier un chemin client différent. Ne pas modifier PostgreSQL,
  réinitialiser l'initializer, créer de DNS public ou redémarrer pfSense.
  [Runbook](runbooks/defectdojo-private-ingress-acceptance.md).
- [ ] **H-04 :** séparer le **OOM Unbound confirmé** vers 02:10 des
  redémarrages 23:38/00:04 non attribués ; exécuter
  `just pfsense-unbound-restart-test` puis
  `just pfsense-unbound-restart-check` en lecture seule, et rapprocher
  les catégories kernel, DNSBL, cron, Watchdog et configd sans leur
  attribuer une causalité implicite.
  [Runbook causalité](runbooks/2026-10-25-pfsense-unbound-restart-causality.md).
- [x] **H-04 / PHP-FPM P0 — déploiement du profil mémoire allégé :**
  commande appliquée par l'opérateur le **25 octobre 2026** ;
  `just pfsense-security-capacity-test` **13/13 PASS** et
  `just pfsense-unbound-restart-test` **49/49 PASS** (21 Unbound, 23 console,
  5 échantillonneur) **le 26/10 à 00:06 CET**. Les gates hors réseau
  ne constituent pas un relevé runtime post-cron pfBlockerNG.
  Avant : générateur + pool `8/3600/2/7/5000`, **7 workers nginx**.
  Après : générateur + pool **`4/30/1/2/500`**, **1 worker nginx**,
  socket PHP-FPM présente, DNS public localhost et contrôle Unbound HEALTHY.
  Sauvegarde versionnée localement sur pfSense.
  Les commandes ont indiqué un `[: NaN: bad number` **non fatal** au
  redémarrage natif, d'origine **non déterminée** ; voir runbook.
- [ ] **H-04 / PHP-FPM P0 — acceptation après changement :**
  **Deuxième preuve à 23:56 CET :** générateur/pool **`4/30/1/2/500`**,
  **2 vrais workers nginx**, socket présente, Unbound PID `19252`
  (`22:46:18`) et control `REACHABLE` ; public DNS localhost/LAN PASS.
  Snapshot **252948 Kio = 247,0 Mio free+inactive**, agrégat RSS PHP-FPM
  **97476 Kio sur 3 processus** (`comm`, master inclus), au lieu de
  **195792 Kio sur 5 processus** au snapshot initial postcutover.
  Les deux mesures ne représentent pas une comparaison isochargée.
  L'OOM le plus récent **22:12 CET** reste antérieur au cutover ;
  **aucun événement plus récent n'a été identifié dans les journaux
  consultés**, sans certifier toutes les plages temporelles.
  `just pfsense-security-capacity-test` **16/16 PASS** (5 PHP-FPM,
  8 wrapper, 3 posture) le 26/10 à 00:06 CET et
  `just pfsense-php-fpm-postcheck` exécuté ; posture **37 PASS / 5 WARN
  / 0 FAIL**. **À confirmer depuis le LAN :** HTTPS GUI **:10443**,
  pfREST authentifié, DNS privé, saturation FastCGI et stabilité
  pendant les crons de nuit. Ne pas réappliquer le changement.
  Rollback uniquement en cas de régression démontrée :
  `PFSENSE_PHP_FPM_CHANGE_CONFIRM=RESTORE_BACKUP just pfsense-php-fpm-restore`.
  [Runbook PHP-FPM](pfsense-php-fpm-hardening.md).
- [x] **H-04 / Snort P1 — réglages basse mémoire confirmés :**
  Snort **WAN en mode passif**, `search_method=ac-bnfa` et
  HTTP Inspect `memcap=33554432` (**32 Mio**) dans l'audit opérateur ;
  également confirmé dans l'interface Snort. Pas besoin de retirer
  de règles à ce stade. Ne pas éditer le `snort.conf` généré.
- [ ] **H-04 / Snort P2 — OOM des mises à jour :** mesurer la vraie
  fenêtre **02:08:30–02:11:30** et déterminer si Snort ou un autre
  processus déclenche la pression mémoire, sans modifier la couverture.
- [ ] **H-04 / pfBlockerNG P1 — feeds et pression mémoire :**
  conserver UT1 Adult, catégories lourdes et TLD désactivés ;
  conserver `PHP memory_limit=128M`. Vérifier les feeds 403/404
  déjà signalés, la récence des tentatives IPinfo/ASN, le nombre
  d'entrées DNSBL et les tailles via
  `just pfsense-feed-pressure-check`. Ne désactiver une liste
  supplémentaire que si elle est redondante/obsolète et si
  la couverture IP/DNSBL est documentée.
- [ ] **H-04 / CrowdSec P1 — état de l'application firewall :**
  audit du 25/10 : `crowdsec.engine=running` et
  `crowdsec.firewall_bouncer=stopped_or_unknown` ; arrêt volontaire
  rapporté par l'opérateur. Les décisions de blocage peuvent ne plus
  être appliquées localement. Ne pas réactiver le bouncer pendant la
  mesure mémoire ; documenter le gain et restaurer la couverture lors
  d'une fenêtre dédiée. Vérifier également
  `service.pfb_filter=0` (helper filterlog absent).
- [ ] **H-04 / capacité P2 — preuve et seuils :**
  viser au moins **128 Mio free+inactive** en régime ordinaire,
  aucune chute prolongée sous 64 Mio, et zéro nouvel OOM Unbound.
  Capturer la vraie fenêtre **02:08:30–02:11:30** avec
  `just pfsense-memory-window`, corréler RSS PHP/CrowdSec/Snort,
  cron et logs noyau. Écarter les changements simultanés.
- [ ] **H-04 / OOM 22:12 — pfBlockerNG :** le **25/10 à
  22:12 CET**, nouvel OOM noyau avec kills **Unbound** et **php_pfb**,
  après le cron pfBlockerNG planifié à **22:00** (proximité horaire,
  causalité du traitement non prouvée). Le redémarrage manuel d'Unbound
  a créé le PID `19252` à **22:46:18 CET**. Enquêter sur l'exécution
  et la mémoire des traitements `php_pfb`/DNSBL à 22:00, puis
  distinguer nouveaux kills **après 23:40** des OOM historiques.
  `pfblocker.dnsbl_loaded_entries=0` signifie compteur **inconnu**,
  pas preuve d'une liste réellement vide ; dernier marqueur `PASSED`
  connu à **00:05:12**. Ne pas forcer de téléchargement/rebuild.
- [x] **H-04 / réception du 26/10 après minuit :** à **00:12:48 CET**
  `just pfsense-unbound-restart-check` donne `unbound_pid=2611`,
  `started_local=26/10 00:04:32`, `unbound_control=REACHABLE`.
  Baseline à **23:56 CET le 25/10** : PID `19252`, démarré
  à **22:46:18**. pfBlockerNG **rapporte** stop ~00:04:25,
  start ~00:04:37, DNSBL exit **00:04:30.252+01:00**,
  update end ~00:08:53 ; les temps `preceding_header_local`
  sont des **heures d'en-tête contextuelles**, pas des appels exacts.
  Les SHA-256 de `unbound.conf` et `dnsbl_legacy_ini` restent
  identiques, donc aucune différence de **contenu des fichiers
  inspectés** ; état module Python et feeds non certifiés.
  Dernier OOM observable **25/10 à 22:12** (avant optimisation
  PHP-FPM), **aucun kill ultérieur dans les fenêtres bornées**.
  `free+inactive` à 00:12 ~**167,1 Mio**, baisse depuis les
  **247,0 Mio** de 23:56 sous une charge différente. Le cron
  pfBlockerNG a bien entraîné un **changement de PID cohérent
  avec sa séquence stop/start** ; pas de preuve de durée
  d'indisponibilité DNS ni de condition de fallback exacte.
- [x] **H-04 / instrumentation réutilisable :** nouvel utilitaire
  **`scripts/pfsense/compare-unbound-snapshots.py`**, sans SSH,
  pour comparer deux relevés read-only : PID/uptime, hashes,
  séquence pfBlockerNG/DNSBL et OOM visibles **après la baseline**,
  en refusant d'attribuer un restart sur une fenêtre DST ambiguë.
  Recette : `PFSENSE_BEFORE=... PFSENSE_AFTER=... just pfsense-unbound-compare`.
  Il n'affiche ni lignes brutes ni feed URLs. Le match SHA-256
  n'établit pas l'absence de changement en mémoire du module Python.
- [x] **H-04 / validation du premier comparateur :**
  `just pfsense-unbound-restart-test` **56/56 PASS opérateur**
  (21 Unbound, 23 console, 5 sampler, 7 comparaison).
  La commande de comparaison réelle a cependant échoué avec
  `ERROR: unbound_comparison_incomplete: ValueError` : le script
  n'explicitait pas les entrées manquantes, vides ou inversées.
- [x] **H-04 / reprise et qualité du nouvel outillage — contrats et capture :**
  `pfsense-unbound-capture` sauvegarde désormais chaque relevé
  complet dans un dossier local privé **0700**, fichier **0600** ;
  le comparateur donne des raisons `before_file_missing`,
  `after_file_empty`, `reports_same_timestamp`,
  `reports_out_of_order`, etc., sans imprimer les données privées.
  **8 nouveaux tests** (3 erreurs de comparateur et 5 capture)
  portent la gate Unbound de **56 à 64 tests** : **64/64 PASS
  opérateur**. Deux captures réelles réussies à **00:40:15** et
  **00:40:22 CET** sur la workstation, toutes deux **postérieures**
  au stop/start DNSBL vers 00:04. L'erreur de comparaison suivante
  `reason=before_file_missing` concernait le chemin
  **placeholder** `/chemin/reel/avant.log`, pas le collecteur.
  Les vrais chemins `snapshot_saved` figurent dans le runbook.
  **Cette paire de sept secondes ne constitue pas un avant/après
  du cron** ; confirmer celui-ci lors d'un prochain cycle.
  Document canonique de reprise :
  [RCA / runbook 2026-10-26](runbooks/2026-10-26-pfsense-memory-dnsbl-reprise.md).
  Aucun rollback PHP-FPM exploratoire ni reload DNSBL forcé.
- [x] **H-04 / comparaison de deux fichiers réels :**
  exécution opérateur réussie avec les captures de **00:40:15**
  et **00:40:22 CET** le 26/10 : PID **2611 → 2611**
  (`unbound_pid_changed=no`), `unbound_control=REACHABLE`,
  hashes `unbound_config` et `dnsbl_legacy_ini` **MATCH** ;
  `dnsbl_python_ini=UNKNOWN_MISSING_EVIDENCE`.
  `kernel_oom_since_baseline=NONE_IN_BOUNDED_VISIBLE_LOGS`
  signifie **0 événement nouveau visible dans ce créneau et
  ces journaux**, pas une preuve d'absence de tout OOM.
  `restart_assessment=NO_PID_CHANGE_IN_THIS_INTERVAL`.
  **Une stabilité sur 7 secondes à 00:40 ne réfute pas** le
  redémarrage pfBlockerNG observé à 00:04.
- [ ] **H-04 / disponibilité DNS LAN au cycle DNSBL :**
  sonde workstation `scripts/pfsense/probe-unbound-lan-dns.py`
  dans **PR #285**. Premier essai réel du **26/10 20:09–20:10**
  sur `172.17.0.1` : **45/45 DNS publics OK**, **45/45
  `NXDOMAIN` privés** avec l'ancien nom non vérifié
  `nexus-albanandrieu.int`, **0 timeout / 0 SERVFAIL**.
  Cela **ne prouve pas une panne Unbound** : le nom privé
  était une mauvaise baseline. La zone canonique actuelle
  est **`int.albandrieu.com` via Pi-hole TrueNAS**.
  **Correctif en PR #285 :** précontrôle A public + privé
  avec **IPv4 attendue obligatoire** (pas seulement `NOERROR`).
  Si le contrôle privé pfSense échoue, diagnostic Pi-hole :
  `BASELINE_INVALID` si référence non confirmée, ou
  `SPLIT_DNS_FAILURE` si l'A attendu existe sur Pi-hole.
  Code de sortie 2 et **aucun prélèvement** dans les deux cas.
  Après baseline valide : `SPLIT_DNS_FAILURE` (privé seul),
  `DNS_OUTAGE_OBSERVED` (deux timeouts au même prélèvement)
  ou `DNS_FAILURE_OBSERVED` (autres erreurs).
  Vérifier `s3.int.albandrieu.com` et son IPv4 réelle sur
  pfSense `172.17.0.1` et Pi-hole `172.17.0.24` avant
  l'observation du cron vers **00:04** ; captures avant/après.
  **P0 ouvert : aucune durée de panne DNS mesurée.**
- [ ] **H-04 / gate collecteur LAN + précontrôle :**
  `just pfsense-unbound-lan-dns-test` **9/9 PASS opérateur**
  et `just pfsense-unbound-restart-test` **73/73 PASS**
  le **26/10** (voir journal de validation).
  Le relevé opérateur du **26/10** confirme **18/18 tests LAN**
  et **82/82 tests Unbound PASS** sur HEAD `dca3bb4e`.
  Le contrôle DNS réel à 20:49 CET confirme
  `s3.int.albandrieu.com → 172.17.0.24` via pfSense et Pi-hole.
  Le premier préflight public `example.com` a expiré
  (`TIMEOUT`), avec le privé `OK`. Aucun échantillon n'a démarré.
  **Correction PR #285 :** au plus une relance publique transitoire ;
  résultat `PUBLIC_DNS_BASELINE_UNAVAILABLE` si le public reste
  indisponible. L'échec initial reste signalé si la relance passe.
  **Gate opérateur récente : 22/22 tests DNS LAN PASS et
  86/86 tests Unbound PASS** (les 22 tests LAN sont inclus dans
  la gate Unbound, pas additionnés). Test Nexus privé : **2/2 PASS**
  sur le code précédent. Ces tests ne valident pas le runtime LAN.
  Après la mise à jour documentaire ci-dessous, rejouer les
  tests ciblés et le contrat Nexus à **3 cas**.
  [Runbook H-04](runbooks/2026-10-26-pfsense-memory-dnsbl-reprise.md).
- [ ] **Nexus / DNS privé / ingress :** le public
  `nexus.albandrieu.com` est déclaré accessible par l'opérateur,
  `nexus.int.albandrieu.com` ne l'est pas encore. Compose expose
  `172.17.0.24:8081`, mais les labels Traefik privés étaient
  commentés. La PR #285 prépare le routeur et son service `:8081`,
  **désactivés par défaut**, sans modifier la route publique.
  **Nouveau relevé opérateur :** `dig @172.17.0.24` et
  `dig @172.17.0.1` ont tous deux expiré pour Nexus, ainsi
  que `curl` HTTP direct sur `:8081` et HTTPS `:443`
  (`http=000`). Cela **ne prouve ni NXDOMAIN, ni défaut TLS,
  ni panne certaine des deux appliances**. Classer
  `LAN_TRANSPORT_UNVERIFIED` et vérifier d'abord les routes
  et la connectivité depuis la même workstation (Gate 0
  du runbook), puis séparer DNS Pi-hole/Unbound, NSS,
  HTTP direct et HTTPS SNI/TLS **uniquement une fois le
  transport confirmé**. La preuve S3 `NOERROR` sur les deux
  DNS à 20:49 CET est antérieure à ce second relevé ;
  l'état de connexion peut avoir changé entre temps.
  **Nouveau relevé 21:18 CET :** workstation `eno1=172.17.0.57/24`,
  routes directement vers `.1` et `.24` ; ICMP 2/2 de chaque côté
  (moyennes 0,498 ms / 0,166 ms), ARP `REACHABLE` et connexions
  TCP à `.1:10443`, `.24:8081`, `.24:443` réussies.
  **Transport LAN joignable pendant ce relevé**, sans conclusion sur
  DNS port 53 ni sur HTTP/TLS applicatifs ; les anciens timeouts
  peuvent être intermittents ou propres aux protocoles.
  **Gate DNS et tests confirmée par l'opérateur :** worktree neuf
  au commit `ebbacf8a`, `just nexus-private-ingress-test`
  **4/4 PASS** (corrige le précédent `Ran 0 tests`).
  Les huit interrogations DNS `dig` sont **8/8 PASS**
  (pfSense/Pi-hole × UDP/TCP × S3/Nexus), toutes
  `NOERROR A 172.17.0.24`. **Le nom privé Nexus existe déjà.**
  Origine de cet A dans Pi-hole non attribuée : une réponse
  autoritative ne prouve pas que les labels Traefik du conteneur
  sont actifs. Ne pas créer un A doublon ni modifier Unbound.
  **Prochain contrôle :** `getent` workstation,
  `curl http://172.17.0.24:8081/` et HTTPS avec
  `--resolve nexus.int.albandrieu.com:443:172.17.0.24`
  pour isoler application, routeur Traefik et certificat.
  **P1 ouvert :** réponse HTTP/TLS et labels réellement
  déployés non vérifiés après les tests DNS. Conserver
  `NEXUS_PRIVATE_INGRESS_ENABLED=false` par défaut,
  ne pas redéployer ni publier de DNS public `*.int`.
  [Runbook Nexus](runbooks/nexus-private-dns-ingress.md).
- [ ] **H-04 / causalité des modifications antérieures :**
  corréler upgrades/paramètres pfBlockerNG, Snort et DHCP/DNS,
  bouncer CrowdSec, changement PHP-FPM et reboot/restore aux
  **premières occurrences** OOM/stop-start.
  Les cycles DNSBL 22–24 octobre et les OOM anciens précèdent
  la réduction PHP-FPM du 25 octobre : celle-ci n'en explique
  pas l'origine, mais peut modifier leur sévérité.
  Vérifier config diffs et gains RAM sous charge équivalente
  avant toute correction/rollback isolé.
- [ ] **H-04 feed-pressure :** exécuter `just pfsense-feed-pressure-check`
  en lecture seule lors des prochaines anomalies Unbound/Snort/pfBlockerNG.
  Examiner les erreurs HTTP 403/404/429/5xx, timeouts, retries IPinfo,
  épuisements mémoire PHP et artefacts DNSBL >=16/64 Mio ou Snort
  >=64/128 Mio. Les résultats sont des signaux historiques bornés :
  recouper avec la chronologie des OOM et la version installée avant
  tout changement de feeds, cron, mémoire ou service.
  [Runbook](runbooks/2026-10-25-pfsense-unbound-restart-causality.md).
- [ ] **Workstation DNS :** valider le parseur DHCP et le chemin de la zone privée via
  `just pfsense-wifi-path-test` et `just pfsense-wifi-path` ; isoler le
  propriétaire de la divergence NetworkManager ↔ `systemd-resolved` sans
  modifier DHCP, Pi-hole ou pfSense. [Runbook daté](runbooks/2026-10-25-pfsense-wifi-dns-root-cause.md).

Les contrôles regroupés sont décrits dans
[Runtime acceptance](runbooks/homelab-runtime-acceptance.md).
Les procédures spécialisées restent dans
[le répertoire des runbooks](runbooks/README.md).

## Code — dernière réception TrueNAS (26 octobre 2026)

- Fichier `/mnt/cpool/secrets/runtime/code/.env.secrets` :
  UID/GID `0:0`, mode `0600`, taille `39` octets.
- Dry-run depuis **ce fichier canonique** : `mapped=1/1`,
  clé acceptée par l'importeur, sans divulgation de valeur.
- Gate `--check code` : Backstage/dataset PASS ; arrêt sur le
  comparateur dotenv car Python système n'a pas `python-dotenv`.
  PR #285 corrige le fallback avec le venv de `SUDO_USER` non-root.
- Risque résiduel : `.env` staged peut contenir l'ancien
  `CODE_PASSWORD` alors que le legacy `.env` a été nettoyé.
  Comparer les sources avant toute correction ciblée ;
  **ne pas utiliser `--restage code`**.
- Élément Vaultwarden `nabla/prod/code` absent au dernier contrôle ;
  import `--apply` distinct, après revue de la source.
  Pas de rotation, de finalisation ni de redeploy.
## Code / secret migration — dernier changement déclaré (26 octobre)

- **Tests validés sur TrueNAS :** comparateur + renderer de secrets
  27/27 PASS. Le dry-run Code historique a rendu `mapped=1/1`
  depuis `/mnt/cpool/code/.env` **avant** suppression manuelle de
  `CODE_PASSWORD` dans ce fichier.
- **Fichier cible modifié :**
  `/mnt/cpool/secrets/runtime/code/.env.secrets` a été édité,
  mais le contrat `PASSWORD`, les permissions `root:root 0600`,
  la présence de l'entrée `nabla/prod/code` dans Vaultwarden et le
  runtime après édition restent **NOT_VERIFIED**.
- **Prochaines gates :** `accept-runtime-env-first-wave.sh --check code`,
  puis dry-run `import_dotenv_to_bitwarden.py --app code --input
  /mnt/cpool/secrets/runtime/code/.env.secrets` (sans `--apply`).
  Pas de rotation ni de redéploiement avant vérification.

## Résultats de validation TrueNAS supplémentaires — 26 octobre

- **Tests :** contrat secrets 8/8 PASS, métadonnées OpenRAG 4/4
  PASS, syntaxe Bash des deux helpers PASS.
- **OpenRAG / secrets :** `left=2 right=4 onlyLeft=0 onlyRight=2
  differentValue=0 sameValue=2`. Le canonique est un surensemble
  strict du legacy, pas un conflit des valeurs communes. Il conserve
  `LITELLM_IDE_API_KEY` et `OPENRAG_ENCRYPTION_KEY`, qui ne
  doivent pas disparaître. Comparaison en venv acceptée ; migration
  et authentification runtime restent bloquées, pas de `--restage`.
- **Code / Vaultwarden :** `materialize_runtime.py --verify`
  atteint le coffre, mais l'élément exact `nabla/prod/code`
  n'existe pas dans le dossier TrueNAS (`found 0`). Contrôler
  d'abord l'ancienne source `/mnt/cpool/code/.env` via le dry-run
  de `import_dotenv_to_bitwarden.py`, sans afficher le mot de passe.
  L'import `--apply` reste une étape distincte et conditionnelle.

## Manifest Vaultwarden — réparation P0 (26 octobre)

- **Validation bloquante identifiée :** trois `importEnv` partagés
  entre Karakeep, LiteLLM, OpenSearch et OpenRAG. Les sources d'import
  ont été rendues uniques, sans modifier les clés Docker ni les valeurs.
  Rejouer le validateur local et la comparaison OpenRAG avec le
  Python de l'opérateur (venv, sans `sudo`).
- **Comparateur OpenRAG :** le `sudo python3` système ne fournit
  pas `python-dotenv` ; le précédent « conflit sémantique » de
  bootstrap reste **à confirmer avec l'interpréteur approprié**.
  Ne pas lancer `--restage openrag`.
- **Scanopy :** `apps/scanopy/` ne stocke volontairement aucun secret.
  Le fichier canonique sous `/mnt/cpool/secrets/runtime/scanopy/`
  reste vide et doit être matérialisé depuis Vaultwarden.

## Relevé opérateur du 26 octobre — DefectDojo, Docling et migration

- **DefectDojo :** les sondes depuis TrueNAS et la workstation confirment
  le DNS privé Pi-hole/Unbound (172.17.0.24), l'absence d'A public,
  l'origine HTTP 302 et Traefik HTTPS/TLS vérifié 302 vers la même
  origine. Le problème réseau signalé ne se reproduit plus. La page
  de connexion et l'authentification Django restent non vérifiées.
- **Docling :** 10/10 tests de contrat PASS ; `--apply` sur TrueNAS :
  `PASS: docling_synthetic_conversion`. La conversion PDF synthétique est
  acceptée. **OpenRAG ingestion/Opensearch retrieval non testés**.
- **Catalogue :** `core` et `deferred` non prêts, `gatus` planifiable
  (sans acceptation runtime). Le relevé brut contient 12 secrets core absents,
  12 bloqueurs core de dépendances, 5 états core inactifs, 18 Apps
  différées déjà running et 44 Apps sans mapping. Ces compteurs globaux
  sont répétés dans les plans ; le lecteur corrigé les classe **par vague**
  sans exposer les identités privées. Revoir explicitement le crosswalk.
- **Secrets :** `canonical-secret-files`, `first-wave-env`,
  `openrag-env-migration` en échec ; le comparateur OpenRAG/OpenSearch,
  le bundle et Akvorado env passent. Les anciennes catégories de conflit
  étaient heuristiques et nécessitent un contrôle détaillé du rapport privé.
  Pas de `--finalize`, copie ou rotation automatique.
- **Première vague secrets (26/10) :** contrats Backstage PASS ;
  `scanopy`, `joplin`, `autokuma` possèdent des matérialisations
  vides (canonique ou legacy) ; `code` a `PASSWORD` absent malgré
  deux copies staged ; `openrag` révèle une différence sémantique
  legacy/canonique. **Bloqué** tant que Vaultwarden et la source
  réellement chargée ne sont pas vérifiés. Ne pas restage OpenRAG.
- **Sentry plus récent (26/10) :** `recover-sentry-deploying.sh
  --check` valide les credentials et `diagnose-sentry:
  exit=0 ok=14 failed=0`. Le FAIL Sentry préflight de l'ancien
  rapport n'est plus courant. E2E ingestion NOT_VERIFIED.
- **DefectDojo poste de travail :** `curl --location` renvoie
  `http=200 redirects=1 tls=0`. Page privée accessible, login non testé.
- **Postmigration :** catalogue dérivé, readiness, Gatus et Prometheus en
  échec. **Critical :** 11 PASS / 5 FAIL (Prometheus, migration env
  OpenRAG, Sentry preflight, Akvorado blocage/insertions).
  La catégorie `sentry_credential_preflight_blocked` n'était pas
  une preuve de défaut de credential car le titre du diagnostic est inconditionnel.
- **Talos :** trois nœuds Kubernetes Ready au dernier contrôle, mais le
  smoke CSI multi-nœuds avec reclaim reste à exécuter avant un upgrade.

Prochaine action : `triage-migration-session.py --check` avec les
quatre sessions déjà conservées, puis contrôles ciblés service par service.
Aucun redéploiement, aucune application de vague et aucune utilisation de
GitHub Actions n'est compris dans ce relevé.

## P0 — OOM global avéré / catalogue des capacités par service (26 octobre)

- **Incident confirmé :** relevé initial `MemAvailable ≈2 Gio/62 Gio`,
  PSI à 5 min `some=23,35 %` / `full=19,65 %`, swap absent.
  Plusieurs `global_oom` ont tué des processus JVM, Python,
  Obsidian et **2 QEMU** entre 21:27 et 22:18. Vérifier Talos/VM
  avant de relancer la flotte. Lien causal Netdata/DefectDojo
  **non démontré** (Netdata ~572 Mio, initializer ~129 Mio au snapshot).
- **Contributeurs observés :** MongoDB ~9,55 Gio ; plusieurs JVM,
  OpenSearch, Docling, Graylog et autres services consomment
  chacun des centaines de Mio à plusieurs Gio. Échantillon
  Docker distinct d'un pic et non une preuve causale.
- **Collecte versionnée :**
  `scripts/truenas/collect-service-resource-evidence.py` produit
  `nabla-service-resources/v1`, une projection privée horodatée
  Backstage/Compose avec `memory.working_set_bytes`,
  `gpu.process_memory_bytes` et
  `storage.writable_layer_bytes` + datasets ZFS partagés.
  Valeur `null/unverified` si GPU distant, donnée absente ou
  mapping non vérifiable. Pas de duplication permanente de cAdvisor.
- **UI OWNER :** la branche
  `nabla-site-alban:feat/homelab-service-resource-snapshots-20261026`
  accepte un import JSON local et affiche RAM/GPU/ZFS dans
  les cards. Mesures périmées après 30 minutes. Aucun upload
  SERVICE/public ; collecte automatique OWNER à planifier.
- **Qualité :** tests hermétiques
  `tests/test_service_resource_evidence.py` ajoutés ;
  exécution locale complète et collecte sur TrueNAS **à confirmer**.
  [Runbook d'inventaire](runbooks/2026-10-26-homelab-service-resource-inventory.md).

## P0 — Pression mémoire TrueNAS après redémarrage DefectDojo (26 octobre)

- **Symptôme :** opérateur rapporte une disponibilité RAM très faible
  depuis le redémarrage DefectDojo. **OOM et attribution à DefectDojo
  NON CONFIRMÉS** : distinguer ZFS ARC récupérable et pression réelle
  via `MemAvailable`, PSI, swap, cgroup OOM et statistiques Docker.
- **Instrumentation versionnée :**
  `scripts/truenas/diagnose-defectdojo-memory-pressure.py --check
  --observe-seconds 20` produit un JSON sans secrets avec
  `defectdojo_total_bytes`, ARC, PSI et delta OOM sur 20 secondes.
  Baseline puis arrêt ciblé de DefectDojo pour comparer, jamais
  arrêt global PostgreSQL ou limitation de l'ARC sans preuve.
- **Option DB :** DefectDojo déclaré non utilisé par l'opérateur ;
  n'en déduire aucune absence de données d'intégration.
  `inspect-defectdojo-db-reset.py --check` inventorie
  **uniquement** la base `defectdojo` (finding/product/
  engagement/test) et les sessions dans PostgreSQL partagé.
  **AUCUN DROP** ni régénération de clé. Si la base est vierge :
  backup isolé + reset ciblé distinct après accord.
- **Dimensionnement :** la documentation officielle DefectDojo
  donne un ordre de grandeur minimum de **8 Go de RAM**
  (base distincte) et des réglages uWSGI (4 processus, 4 threads
  par défaut). Ne pas attribuer une mémoire saturée aux tables
  PostgreSQL sans preuve ; une réinitialisation ne réduit pas
  automatiquement l'empreinte des workers.
- **Tests :** contrats hermétiques `test_defectdojo_memory_pressure.py`
  et `test_defectdojo_db_reset_inventory.py` versionnés.
  **Runtime TrueNAS NOT_VERIFIED**, pas de validation OOM réelle.
  [Runbook mémoire et remise à zéro](runbooks/2026-10-26-defectdojo-memory-db-reset.md).

## P0 — DefectDojo : DNS sain, HTTPS indisponible, admin désynchronisé

- **DNS privé : prouvé OK le 26/10 à 20:51 CET** :
  pfSense/Unbound `172.17.0.1` et Pi-hole `172.17.0.24`
  renvoient tous deux `NOERROR A 172.17.0.24`.
- **HTTP origine : répond sur `:31085`** ; domaine HTTPS
  inaccessible depuis la workstation. Le diagnostic
  `scripts/truenas/diagnose-defectdojo-https-route.py --check`
  localise la panne entre TLS/SNI, labels Traefik, réseau Docker
  et backend sans afficher de secrets. **HTTPS NOT_VERIFIED**.
- **Lifecycle :** à 21:00:02, `app.up` échoue sur
  `/mnt/cpool/secrets/runtime/defectdojo/.env` absent ;
  l'opérateur l'a copié depuis `.env.example`.
  `prepare-defectdojo-runtime-env.py --inspect/--apply`
  valide et normalise uniquement ce metadata en `root:root 0600`,
  sans toucher aux secrets.
- **Compte admin Django :** nouveau `DD_ADMIN_PASSWORD` ajouté
  manuellement dans `.env.secrets` ; le hash PostgreSQL du compte
  historique `admin` ne change pas automatiquement.
  `reconcile-defectdojo-admin-password.py --check`
  diagnostique la parité. `--apply --acknowledge` synchronise
  uniquement le compte existant, sans créer de superuser ni
  redémarrer. **Login réel et Vaultwarden NOT_VERIFIED**.
- **À faire après reprise :** contrôler la parité avec l'entrée
  Vaultwarden `TrueNAS/nabla/prod/defectdojo` (login.username
  réel `admin`) avant une future régénération.
  [Runbook](runbooks/defectdojo-admin-access-recovery.md).

## LiteLLM UI / DefectDojo / Prometheus — réception 26 octobre

- **LiteLLM :** le 401 observé appartient à `litellm-dashboard` avec
  zéro token et une session expirée le 25/10 à 20:35:59 UTC.
  **Session navigateur**, pas une clé fournisseur ou service invalide.
  Correctif opérateur : fermer les onglets LiteLLM, se déconnecter et
  se reconnecter. Classification locale par
  `diagnose-litellm-dashboard-auth.py`. Upstream #35789/#35791
  référence le défaut de SpendLogs sur les routes d'information.
  Pas de rotation des clés métier ni de redeploy.
- **DefectDojo :** ancienne preuve HTTP 200 après redirection et
  TLS validé, mais disponibilité du **login actuellement NOT_VERIFIED**.
  `check-defectdojo-login-lan.sh --check` teste l'URL exacte via
  HTTPS/SNI vers TrueNAS et refuse les certificats non valides ;
  aucun domaine `.int` exposé au public.
- **Prometheus :** jeton métriques installé `credential_ready`, App
  redéployée et quatre conteneurs annoncés RUNNING. Malgré cela,
  `172.17.0.24:9090/-/ready` refuse les connexions.
  **Montage réparé ; API non rétablie**. Diagnostic du listener et
  du process via `diagnose-prometheus-targets.sh --check`, sans
  toucher au TSDB ni au secret.
- **Qualité :** 12 tests synthétiques locaux PASS sur les nouveaux
  classificateurs LiteLLM et DefectDojo ; suite GitHub complète et
  validation LAN encore NOT_VERIFIED.
  [Runbook](runbooks/2026-10-26-litellm-ui-session-defectdojo-prometheus.md).

## P0 — Échecs TrueNAS lifecycle du 26 octobre : Scrutiny / Prometheus

- **Scrutiny :** `app.up` bloque sur
  `/mnt/cpool/scrutiny/.env.secrets`, une **ancienne définition
  enregistrée dans TrueNAS**. Le fichier canonique
  `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets` est déjà présent
  (319 octets, `root:root 0600`). Le helper
  `deploy-scrutiny.sh` valide désormais le chemin du Compose rendu
  avant `--apply`, puis réconcilie le Custom App et les devices SMART.
  **Reprise runtime non exécutée.**
- **Prometheus :** démarrage échoué à cause du bind absent
  `/mnt/cpool/prometheus/secrets/fastapi-sample-metrics.key` ;
  cela explique l'exception `URLError` de la collecte.
  `reconcile-fastapi-metrics-credential.py --apply --acknowledge`
  prépare le dossier privé `root:568 0750` s'il manque puis installe
  **le jeton FastAPI existant** avec `root:568 0640`.
  Un redémarrage ciblé reste nécessaire ; résultat non vérifié.
- **Journal :** `triage-app-lifecycle-log.py` classe les erreurs
  récentes sans afficher les messages ni traiter les incidents
  historiques comme des pannes actuelles. Les incidents datés de
  septembre/début octobre nécessitent `app.query` avant action.
- **Akvorado :** nouveau relevé opérateur :
  `delta_received_flows=2`, `delta_metadata_missing=2`,
  `delta_clickhouse_batches=0`. Le blocage des métadonnées est
  désormais **prouvé actif**, vérifier l'Orchestrator/Outlet
  réellement configuré et les ifIndex des flux.
- [Runbook de reprise ciblée](runbooks/2026-10-26-scrutiny-prometheus-lifecycle-recovery.md).
  Nouveaux tests hors LAN : `just truenas-lifecycle-recovery-test`.
  **Tests GitHub/local checkout non exécutés par l'agent.**

## H-05 / H-06 — collecte LAN unifiée (code PR #285, 26 octobre)

- **Point d'entrée :** `scripts/truenas/collect-observability-evidence.py`
  et `just observability-evidence-lan`. En lecture seule, ces
  outils collectent les sept scrapes Prometheus restants et deux
  instantanés de métriques Akvorado, sans accès aux secrets ni au SQL.
- **Sortie :** rapport JSON avec horodatage, classes d'erreur et deltas
  `received_flows`, `metadata_missing`, Kafka, lots ClickHouse ;
  aucun `lastError`, label, endpoint brut ou token n'est conservé.
  Dossier de preuves privé en mode `0700`, fichier `0600`.
- **Statuts :** `PASS` (preuve instrumentée concluante),
  `FAIL` (scrape DOWN/partial ou rejets metadata actifs),
  `UNVERIFIED` (cible absente/inconnue, mesure inaccessible,
  activité de lots sans preuve SQL). L'absence de lignes SQL
  vérifiées reste explicitement `sql_rows=NOT_VERIFIED`.
- **Qualité :** contrats synthétiques créés dans
  `tests/test_collect_observability_evidence.py` ;
  `just observability-evidence-test` et tests H-05/H-06
  **à exécuter sur le checkout complet**. Aucune CI payante lancée.
- **Exécution LAN différée :** aucun résultat live inventé.
  [Runbook de collecte et commandes](runbooks/prometheus-akvorado-lan-evidence-20261026.md).

## Prometheus + Akvorado — campagne LAN préparée (26 octobre)

- **Point d'entrée unique :** `scripts/truenas/observe-prometheus-akvorado-lan.sh`
  (sans sudo) agrège baseline + sept scrapes restants et deux snapshots
  Akvorado espacés de 1 à 60 secondes ; écrit un JSON privé 0600.
  `--scope all` dans `collect-observability-evidence.py`
  supprime les doublons de jobs. Synthèse `PASS/FAIL/UNVERIFIED`.
- **Commandes opérateur :** voir
  [runbook observabilité](runbooks/2026-10-25-observability-triage.md).
  L'agent n'a pas observé le LAN : les scrapes courants, les erreurs
  de métadonnées et les lignes ClickHouse sont **NOT_VERIFIED**.
- **Critère de clôture :** Prometheus vérifié pour chaque job configuré ;
  Akvorado deux fenêtres sans rejets actifs et preuve SQL de nouvelles
  lignes, distincte du compteur de lots. Ne pas promouvoir le
  status Akvorado `UNVERIFIED` à `PASS` sans SQL.
- **Qualité :** test unitaire du scope `all` ajouté ; validation
  sur le HEAD du checkout de l'opérateur encore requise.

## H-05 / H-06 — durcissement des diagnostics hors LAN (26 octobre)

- **Prometheus (code livré dans PR #285) :** `health=unknown`,
  vide ou inattendu ne sera plus décompté comme `scrape_down` :
  `scrape_unverified`, `targets_unverified` et
  `failure_domains` distinguent `auth` (HTTP 401/403),
  `http`, `tcp`, `dns`, `tls`, `timeout`, `network`
  et `unverified`. Les labels, URLs et messages bruts restent
  exclus du rapport. **Pas de nouveau scrape LAN** ; les 21/28
  du 25/10 sont des données historiques, pas une preuve live.
- **Akvorado (code livré dans PR #285) :** les compteurs négatifs
  ou non finis sont `COUNTER_INVALID_INCONCLUSIVE` au lieu de
  fournir de fausses preuves de nouvelles insertions. `--fail-on-blocked`
  considère cet état comme une défaillance de preuve ; les nouveaux
  lots SQL et le mapping NetFlow/ifIndex restent **NOT_VERIFIED**.
- **Validation agent :** 9 tests synthétiques de la logique isolée
  **PASS** dans le conteneur de l'agent. Tests ciblés versionnés
  en PR ; leur exécution sur le checkout Git complet **NOT_RUN**.
  Aucune CI GitHub, aucun changement de secret ou de service.

## P1 — Corriger les causes instrumentées

| ID | Domaine | Fait établi | Reste à prouver |
| --- | --- | --- | --- |
| H-05 | Prometheus | Correction du fichier `prometheus.yml` par opérateur : uid 1000, gid 568, mode 0640 ; promtool OK, 21/28 targets UP | Réconcilier les scrapes non UP sans réparer à nouveau les règles |
| H-06 | Akvorado | Nouvelle preuve : 5 flux reçus, 4 rejets metadata, 0 insertion ; le PASS ponctuel précédent ne prouve pas l'absence de blocage | Vérifier l'export NetFlow, les `ifIndex` et **de nouvelles lignes SQL datées** |
| H-07 | Catalogue OWNER/SERVICE | Identités Backstage/`x-nabla` déclarées ; consommateurs FastAPI/Site distincts | Vérifier dérive catalogue, puis comportement runtime par provenance |
| H-08 | Secrets et noms | Secret OpenSearch `legacy_env` corrigé en UID=0/GID=568/0640, 2 candidats égaux à OpenRAG ; gates ciblées PASS | **PARTIEL** : credential réellement chargé, authentifications et finalisation legacy non attestés |
| H-09 | Talos / Kubernetes | CSI NFS antérieurement accepté | Retained smoke multi-nœuds avant changement d'Ingress ou migration d'App |

Actions :
- [x] **D-15 (code) :** mode `triage-critical-failures.sh --check --remaining`
  limité aux **deux gates encore en échec** ; classificateur Prometheus
  `--check --scope remaining` limité aux sept cibles précédemment DOWN,
  recommandations statiques sans URLs ni secrets.
  [Reprise ciblée](runbooks/2026-10-25-critical-acceptance-followup.md).
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
  Le candidat OpenSearch `legacy_env` est maintenant corrigé
  (UID=0, GID=568, mode=0640) et l'égalité avec le secret OpenRAG
  est confirmée pour deux fichiers. Valider ensuite le secret **effectivement
  chargé** et l'authentification sans nouvelle rotation.
  Vérifier que les clés Langfuse sont réelles et issues du même projet : un
  PASS syntaxique ne prouve pas le callback. Ne pas finaliser le legacy
  OpenRAG avant une acceptation runtime vérifiée.
  [Gates de clôture](runbooks/truenas-secret-migration-closure.md) · [preuves et commandes](runbooks/2026-10-25-critical-acceptance-followup.md).
- [ ] **H-09 :** exécuter les contrôles CSI/Talos uniquement après P0
  et dans la fenêtre approuvée.

**Tests opérateur :** `just migration-recovery-contracts` : **12 PASS**.
`just node22-fast` : **5 PASS / 1 FAIL** car exécuté sous Node 24 ;
la recette sélectionne désormais Node 22 via `mise` et doit être rejouée
sur le HEAD exact. `just quality` reste NOT_RUN.

## Régression DefectDojo et dernières validations locales

- **DefectDojo** : URL privée signalée inaccessible par l'opérateur.
  Ancienne acceptation ingress **supplantée**, origine réelle non prouvée.
  Les preuves historiques indiquent une panne du forwarder Unbound
  vers Pi-hole malgré un Traefik HTTP 302 fonctionnel le 17 octobre ;
  **ne pas assimiler cet historique au défaut courant sans sondes**.
  [Diagnostic et branches de correction](runbooks/defectdojo-private-ingress-acceptance.md).
- **Node22/npm10** : `just node22-fast` **6/6 PASS** à la révision
  de l'opérateur. Les tests sur l'ancien contrat npm sont résolus.
- **Migration/Docling** : `just migration-recovery-contracts` a un échec
  `test_no_mutation_before_preflight` sur une assertion d'ordonnancement ;
  corrigée dans la PR pour comparer l'état guardé, la matérialisation et
  l'**action réelle app.update**, sans affaiblir le mode read-only.
  Rejouer après mise à jour du checkout.
- **CSI** : `CONTROLLER_READY_WITH_TERMINATED_PODS`; Pod Failed
  du RS actif et contrôleur sain, aucun cleanup automatique.
- **Docling** : `DEPLOYING`, conteneur `running` mais `unhealthy`,
  redémarrages `0`, TCP host :5001 refuse la connexion.
  **Pas de seconde app.apply**. Inspecter les métadonnées healthcheck
  et l'API avant toute mise à jour ciblée.

## Preuves de déploiement et quality gate — 25 octobre, dernier relevé

- **CSI contrôleur** : `deployment/truenas-csi-controller` **1/1
  Available** et `rollout status` réussi. ReplicaSet actif
  `truenas-csi-controller-6556bff5d6` **1/1 READY**. Un autre pod
  **0/5 Error** (`qbk5n`, 144 restarts) porte **le même hash de
  ReplicaSet**, et **n'est donc pas un pod d'un ancien ReplicaSet**.
  Examiner ses propriétaires et l'état `Error` sans supprimer le RS actif
  ou le contrôleur sain. Le smoke `--apply` avec PVC/reclaim reste
  **NOT_RUN**.
- **Docling** : `app.create` a terminé **OK** ; App `DEPLOYING`,
  conteneur `running`, endpoint hôte `/ready` **UNREACHABLE**,
  sondage OpenRAG **UNVERIFIED**. **Ce n'est plus une App absente**.
  Ne pas relancer `deploy-docling.sh --apply` pendant `DEPLOYING`.
  Le diagnostic expose désormais `INITIALIZING`, le healthcheck
  du conteneur et le nombre de redémarrages sans lire ses logs.
- **Node22/npm10** : la paire de versions **PASS** sous le
  `just node22-fast` corrigé. Les tests ont donné **5 PASS / 1 FAIL**
  sur une **assertion obsolète** de `node22-fast.test.mjs`
  qui attendait encore `npm --offline run`, alors que le script
  appelle `npm-cli.js --offline run`. L'assertion a été mise à jour
  dans la PR ; **6/6 au dernier HEAD non encore rejoué**.
- **Qualité des opérateurs** : `just migration-recovery-contracts`
  **23 tests Python PASS**, syntaxe Bash PASS, y compris gestion d'un
  timeout Talos et préflight Docling. Les nouveaux tests ajoutés
  après ce relevé n'ont pas encore été exécutés sur le dernier HEAD.

[Runbook Talos/CSI/Docling](runbooks/2026-10-25-talos-secret-permissions-openrag-pdf.md) ·
[Node 22](runbooks/node22-local-fast-tests.md).

## P0 — Reprise Talos VM, secret modes et preuve PDF (25 octobre)

**Nouvelle preuve :** les trois VM Talos `taloscp01`, `taloswk01`,
`taloswk02` sont **RUNNING** côté middleware TrueNAS après reprise.
La première commande `vm.start` a expiré mais le second inventaire
confirme le démarrage du control-plane ; workers démarrés ensuite.
**Talos API, etcd, nœuds Kubernetes et CSI restent NOT_VERIFIED.**
Ne pas lancer fast-batch-upgrade avant validation du cluster.

- [x] **Code :** `resume-stopped-talos-vms.py --check` et
  `--start --acknowledge I_ACCEPT_STARTING_EXISTING_TALOS_VMS` :
  liste de VM figée, refuse l'inventaire ambigu et confirme le middleware,
  aucun upgrade/etcd reset.
- [x] **Runtime VM :** les trois VM sont RUNNING côté middleware ;
  script amélioré pour gérer le timeout sans double `vm.start`.
- [x] **Runtime Talos/Kubernetes :** `validate-cluster.sh` exit 0
  (5 OK, 2 WARN) ; 3 nœuds Ready Talos 1.13.9 et K8s 1.36.3.
  Controller CSI récent 5/5 ; anciens pods à inspecter avant nettoyage.
- [ ] **CSI E2E :** smoke retained cross-node + final reclaim
  **NOT_RUN** ; le `--check` a validé uniquement les prérequis.
  Ne pas lancer d'upgrade Talos tant que les vérifications etcd et
  reclaim ne sont pas achevées.
- [x] **Code :** `audit-runtime-secret-permissions.py --check` pour
  tous les fichiers reguliers et repertoires du root canonique ; `--apply` exige un
  acquittement, refuse symlinks/proprietaires non-root, conserve
  UID/GID ainsi que l'acces groupe necessaire. **Pas de chown/chmod -R**.
- [x] **Runtime secrets canoniques :** audit `mode_changes=1 blockers=0`
  puis correction de `openclaw/.env.secrets` `0644 → 0640` ;
  UID/GID préservés. Réexécution de `--check` conseillée ; les legacy
  hors du root canonique restent un chantier séparé.
- [x] **Code :** `check-openrag-private-pdf.sh --check --file` pour
  la lecture du PDF depuis le dataset bind RO, la readiness Docling
  et la sante search, sans jamais envoyer ou indexer le PDF.
- [x] **Runtime montage :** PDF Mickey privé de 849129 octets valide
  et lisible par `openrag-backend` selon le relevé opérateur.
- [x] **Création Docling :** `app.create` OK ; ne pas répéter `deploy --apply`.
- [x] **Readiness (preuve opérateur 25/10) :** `RUNNING`, conteneur
  `running+healthy`, 0 restart, `/ready` depuis TrueNAS et OpenRAG.
  État `READY_ONLY` ; reconfirmer avant le test réel.
- [x] **Code :** test hermétique de conversion d'un PDF synthétique,
  `just docling-synthetic-test` (8 tests unitaires exécutés localement).
- [ ] **Conversion réelle Docling :** résultat opérateur `/ready=READY` puis
  HTTP 200 avec `CONVERSION_UNVERIFIED` (aucun marqueur accepté) ;
  extraction E2E **non validée**. Le script classe maintenant les
  statuts d'erreur, texte vide, marqueur absent et Markdown échappé
  sans imprimer la réponse. Rejouer une seule fois sur TrueNAS après mise
  à jour ; aucun redeploy Docling ni indexation automatique.

- [ ] **E2E OpenRAG :** conversion, ingestion et retrieval **NOT_TESTED** ;
  commencer par un document synthétique, sans publier le billet.
  [Runbook cible](runbooks/2026-10-25-talos-secret-permissions-openrag-pdf.md) ·
  [Runbook ingestion de reference](runbooks/openrag-babou-ingestion-diagnostics.md).

**Dernieres gates critiques :** Prometheus sept scrapes non-UP
(dont 2 HTTP 401) et Akvorado rejetant les nouveaux flux
(`metadata missing`, delta +20 en 60s, aucune insertion).
Le dossier prive `focused-1CBwrm` donne `PASS=0 FAIL=2` sur
les deux gates restantes. N'appliquer aucune remediation de masse.

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
