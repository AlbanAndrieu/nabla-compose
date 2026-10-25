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
| H-02 | Sentry | Le 25/10 : consumer et recovery preflight PASS ; ingestion E2E non reconfirmée | Consommateurs sains, Kafka/Relay et smoke d'ingestion E2E contrôlés |
| H-03 | DefectDojo | **Nouvelle régression signalée le 25/10 :** `https://defectdojo.int.albandrieu.com/` inaccessible dans le navigateur ; cause runtime actuelle **NOT_VERIFIED**. L'ancienne acceptation HTTP 302 ne constitue plus une preuve présente | Rejouer la chaîne Nginx/uWSGI → LAN :31085 → DNS Pi-hole/Unbound → HTTPS Traefik/SNI et valider la page de connexion |
| H-04 | pfSense / Unbound | **Deux mécanismes prouvés** : OOM noyau (dernier visible **25/10 22:12 CET** avant cutover PHP-FPM) et **nouveau PID Unbound `19252` → `2611`, lancé le 26/10 à 00:04:32 CET** pendant les marqueurs pfBlockerNG stop (~00:04:25) / start (~00:04:37) ; sortie DNSBL Python 00:04:30. **Hashes Unbound + INI legacy inchangés** depuis 23:56 ; Unbound Control REACHABLE à 00:12, free+inactive ~167 Mio, pas de nouvel OOM dans la fenêtre retenue. Profil PHP-FPM 4/30/1/2/500 confirmé précédemment, Snort AC-BNFA. **65/65 tests offline PASS**. | **P0 :** diagnostiquer pourquoi pfBlockerNG `3.2.17_1` exige un stop/start même sans modification des deux fichiers vérifiés ; contrôler indisponibilité DNS pendant 00:04 (non mesurée). **P1 :** identifier le pic RAM / `php_pfb` lors des OOM, stabiliser marge mémoire sous cron Snort et documenter bouncer CrowdSec. **P2 :** confirmer accès GUI/pfREST, DNS privé LAN. |

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
- [ ] **H-04 / validation comparateur :** exécuter
  `just pfsense-unbound-restart-test` sur le HEAD courant ;
  **7 nouvelles régressions offline** ajoutées aux 49 tests
  Unbound/console/sampler validés auparavant (**56 attendus**).
  Vérifier également la disponibilité DNS pendant le prochain
  cycle stop/start, sans provoquer de reload.
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
