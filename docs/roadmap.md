# Services Homelab — roadmap active

> **Workstation/YubiKey :** l'[ADR Option A](adr/adr-workstation-option-a.md) fixe les sources de vérité inter-dépôts ; seule la [roadmap YubiKey/Compose](roadmap-workstation-yubikey.md) appartient à cette roadmap. Les tâches système Ubuntu restent dans `ansible-workstation`, les dotfiles dans `dotfiles`.

> Mise à jour : **28 octobre 2026**. Source d'autorité pour le travail restant
> dans `nabla-compose`. Ce document décrit des **décisions et gates**,
> pas une preuve de fonctionnement des services.
>
> L'[historique intégral jusqu'au 24 octobre](archive/roadmap-through-2026-10-24.md)
> est conservé, octet pour octet (blob Git identique à l'ancien `docs/roadmap.md`).
> Les états et commandes datés de cet historique **ne sont pas des consignes
> de réparation courantes**.

## P0 — FastAPI : diagnostic UI, Prometheus, LiteLLM et OpenRAG consolidé (30 octobre 2026)

**Mesures opérateur du 30/10, non exécutées par cet agent :**
- TrueNAS FastAPI /api, /api/ui/session, /api/ui/services : HTTP 200, catalogue autour de 0,52 s.
- Staging et Cloud : HTTP 403 sur les trois routes depuis le point de test = DENIED, pas DOWN. Chromium : Playwright absent = NOT_RUN. Mode secours UI annoncé fonctionnel ; mode riche non accepté.
- Prometheus : configuration promtool valide et identique au montage ; dernier snapshot : 22/28 UP. Six targets DOWN (haproxy, litellm_hermes HTTP 401, opensearch, opensearch-security, pihole_exporter, postgres_exporter). fastapi_sample DOWN/TCP puis UP dans deux mesures : **ne pas mélanger les instantanés**.
- LiteLLM TrueNAS et OpenRAG HEALTHY côté readiness. LITELLM_FASTAPI_WORKSTATION_API_KEY **absente du conteneur LiteLLM** ; fichiers sources ambigus. OpenRAG MCP GET 406 : transport seulement, pas handshake. Recherche Bababou privée NOT_RUN.

- [x] **CODED PR #295 :** scripts/truenas/diagnose-fastapi-stack.py ; une commande read-only pour UI, une capture unique des targets Prometheus et les contrôles IA, états PASS/FAIL/DENIED/UNVERIFIED/NOT_RUN ; mode navigateur Chromium opt-in. Les anciens scripts spécialisés restent disponibles.
- [x] **TESTED isolé :** 18 tests unittest et py_compile PASS sur les blobs identiques au code préparé ; tests complets du dépôt et runtime du lanceur NOT_RUN.
- [x] **Correction de diagnostic :** le prochain contrôle du job fastapi_sample suit le domaine TCP/DNS/timeout/auth observé, plutôt que de demander la clé en cas de connexion refusée.
- [ ] **Runtime :** exécuter sur TrueNAS le lanceur en lecture seule ; corréler les scrapes depuis son snapshot unique.
- [ ] **LiteLLM :** attribuer l'absence de clé upstream à la source Vaultwarden, au fichier runtime ou à l'environnement conteneur sans utiliser la clé IDE ni la master key.
- [ ] **OpenRAG :** prouver les ACL privées, la négociation MCP authentifiée, le filtre corpus et la recherche sur un document synthétique autorisé.
- [ ] **UI :** comparer les modes safe/full avec Chromium préinstallé sur une machine autorisée et le SHA réellement déployé.

Runbook : [Diagnostic consolidé FastAPI](runbooks/fastapi-consolidated-diagnostics-20261030.md).

## P0 CrowdSec — inspection LIVE sans vestige (30 octobre 2026)

- **Gate ciblé validé sur la workstation :** `just crowdsec-pf-synthetic-test`
  **24/24 PASS**, `just crowdsec-bouncer-config-test` **74/74 PASS**
  (5 URL, 11 authentification, 5 provisionneur, 10 provenance,
  19 cycle naturel, 24 synthétique). Cela prouve les contrats
  des scripts, **pas** l'application d'un ban réel dans PF.
- **Inspection réelle en lecture seule :** `just crowdsec-pf-synthetic-inspect`
  => `lapi_matches=0 decision_ids=none pf_present=false
  pf_bouncer=RUNNING`. Aucun vestige *actif* sur `203.0.113.77`
  à cet instant ; le premier essai reste non prouvé.
- **Amélioration complémentaire du diagnostic :** classifier sans
  exposer stderr les refus CrowdSec `ADD_DENIED_ALLOWLIST`,
  `CLI_UNSUPPORTED_OPTION`, les permissions SSH/sudo et autres
  échecs. **5 tests supplémentaires versionnés**, gate étendu
  prévu **79 tests** ; nouveau gate non encore exécuté sur workstation.
  Ne pas contourner une allowlist TEST-NET-3 à l'aveugle.
- **Suite :** `just crowdsec-pf-synthetic-preflight` puis, seulement
  après PASS, exécution active explicitement voulue. Baseline naturelle
  v1 conservée ; baseline v2 à établir séparément.
  **P0 PF reste NOT_VERIFIED**.

## P0 CrowdSec — diagnostic du test synthétique (30 octobre 2026, PR #295)

- **Évidence utilisateur :** `just crowdsec-pf-synthetic-test`
  **15/15 PASS**, puis gate ciblé CrowdSec **61/61 PASS**
  sur la workstation. `just crowdsec-pf-synthetic-preflight` :
  `initial_lapi=ABSENT initial_pf=ABSENT pf_bouncer=RUNNING`.
  L'exécution mutatrice explicite a retourné
  `synthetic_cleanup=NOT_VERIFIED manual_review_required=true`
  et `synthetic_cycle=NOT_VERIFIED reason=NotVerified`,
  **sans `synthetic_lapi=CREATED decision_id=...`**.
  Elle ne prouve ni succès ni échec du bannissement ; l'état de
  `203.0.113.77` doit être relu avant toute nouvelle tentative.
- **Cause de code confirmée upstream CrowdSec v1.8.1 :**
  `cscli decisions list -o json` renvoie une liste **d'alertes**
  contenant `decisions[]`, pas seulement des décisions au premier
  niveau. L'ancien parseur les ignorait au précontrôle puis échouait
  à attribuer l'ID après `cscli decisions add`.
- **Correctif PR #295 [skip ci] :** normalisation stricte des
  `alerts[].decisions[]`, rejet des schémas inconnus, propriété du
  ban vérifiée sur `origin=cscli` + `scenario=reason` aléatoire
  + cible/type/ID ; nettoyage **uniquement par cet ID**.
  Nouveau `just crowdsec-pf-synthetic-inspect` en lecture seule,
  statut de phase plus précis, tests hermétiques complémentaires.
  **Nouveaux tests pas encore exécutés sur workstation.**
- **Impact sur le suivi naturel :** le parseur flat-only initial
  pouvait produire un faux zéro. Nouvelle baseline au format v2,
  **fichier séparé** `crowdsec-pf-natural-cycle-v2.json` ;
  la baseline v1 historique en `0600` n'est ni écrasée ni
  considérée comme preuve valide. Refaire la baseline v2 en
  lecture seule une fois l'état du test synthétique vérifié.
- **P0 remédiation PF : NOT_VERIFIED.** Ne pas relancer `--apply`
  avant un `--inspect` / précontrôle propres ; aucun
  `cscli decisions delete --ip`, changement PF ou rotation de clé.
  La mise en évidence d'une entrée PF ne prouverait pas encore
  le blocage d'un paquet sur une règle active.

## P0 CrowdSec — validation synthétique réversible prête (28 octobre 2026)

- **Implémentation versionnée, PAS encore exécutée en runtime** :
  `scripts/workstation/smoke-crowdsec-pf-synthetic.py` pilote
  depuis la workstation les lectures LAPI TrueNAS et PF pfSense.
  Le mode `--preflight` reste en lecture seule. `--apply` nécessite
  `--confirm SYNTHETIC-203.0.113.77` ; il crée au maximum une
  décision `ban` documentée (TEST-NET-3, TTL **5 minutes**),
  observe la même IP dans `crowdsec_blacklists`, puis supprime
  **l'ID de décision créé uniquement** et vérifie son retrait de
  LAPI et PF. `finally` et capture Ctrl+C/SIGTERM tentent le nettoyage.
  Si l'ID ne peut être prouvé, aucun `delete --ip` n'est lancé ;
  revue manuelle et expiration TTL obligatoires.
- **Tests locaux ciblés : 15/15 PASS** en environnement isolé,
  sans SSH ou mutation réseau. Ajoutés au gate CrowdSec
  (`46` précédents + `15` nouveaux = **61** tests ciblés).
  **Le gate 61/61 sur workstation n'a pas encore été exécuté.**
  Commandes : `just crowdsec-pf-synthetic-test`,
  `just crowdsec-pf-synthetic-preflight`, puis action explicite
  dans le [runbook](runbooks/crowdsec-pfsense-decision-provenance.md).
- **P0 en attente** : le ban synthétique n'a pas été créé par l'agent,
  aucune application/retrait PF ne peut donc être revendiquée.
  Ce test vérifie un cycle *manuel* et **ne se substitue pas**
  à l'observation d'une décision naturelle. Une table PF alimentée
  ne prouve pas non plus qu'une règle a bloqué du trafic WAN.

## P0 CrowdSec pfSense Small — baseline LIVE établie le 28 octobre 2026

- **DONE — gate ciblé workstation :** `just crowdsec-pf-natural-test`
  **15/15 PASS**, puis `just crowdsec-bouncer-config-test` **46/46 PASS**
  sur `nabla-compose`, HEAD utilisateur `ba5aa198` après fast-forward.
  Décompte : URL 5, authentification 11, provisionneur 5,
  provenance 10, cycle PF 15. Les contrôles Bash/Python du gate passent.
  Ce n'est **pas** le quality gate global du dépôt.
- **DONE — baseline réelle en lecture seule :**
  `just crowdsec-pf-natural-baseline` a retourné
  `crowdsec_pf_baseline=READY source_mode=LIVE pf_networks=4016 natural_bans=0`.
  Les accès indépendants à TrueNAS et à pfSense, ainsi que le contrôle
  de l'état pfSense Small, ont réussi. La baseline privée est locale
  à la workstation et **ne doit pas être régénérée ni publiée**.
- **P0 en attente d'événement :** le premier
  `just crowdsec-pf-natural-observe` a retourné
  `pf_decision_cycle=NOT_VERIFIED reason=NO_ELIGIBLE_NEW_NATURAL_BAN`.
  Ce n'est **pas une panne** : aucune décision naturelle nouvelle ne
  peut encore démontrer le cycle LAPI → PF → retrait.
  Refaire seulement `just crowdsec-pf-natural-observe` depuis la
  même workstation quand une décision naturelle apparaît.
  Aucun ban synthétique ou `cscli decisions add/delete` n'a été exécuté.
- **À ne pas déduire :** les 4 016 *réseaux IPv4* dans la baseline PF
  ne correspondent pas directement à l'ancien décompte combiné IPv4/IPv6 ;
  leur présence ne prouve ni leur origine CrowdSec centrale,
  ni qu'une règle PF les applique à des paquets WAN.

## Historique CrowdSec — étapes validées ou supplantées

- **DONE — gate CrowdSec complet sur TrueNAS (preuve opérateur du 28/10) :**
  `just crowdsec-bouncer-config-test` **31/31 PASS**, code de sortie
  compatible avec une exécution réussie (aucune erreur dans le relevé) :
  parser URL **5/5** ; candidat bouncer **11/11** ;
  provisionnement hermétique **5/5** ; provenance pfSense **10/10**.
  Les `bash -n` et `py_compile` de la recette passent également.
  Cette preuve concerne **ce gate ciblé**, pas le quality gate global
  de `nabla-compose` ni un redéploiement.
  HEAD TrueNAS testé après fast-forward : `5f1cd05b`.
- **DONE — authentification et interrogation LAPI** : dernier
  `diagnose-crowdsec-cutover.sh --accept` fourni auparavant :
  **failures=0 warnings=2**, bouncer
  `PFSENSE_FIREWALL@172.17.0.1` à `172.17.0.1`,
  `last_pull=2026-10-27T23:12:07Z`. Pas de nouvelle exécution
  du diagnostic dans le relevé du gate actuel.
- **Implémenté — preuve naturelle PF sans mutation (PR #289) :**
  `scripts/workstation/observe-crowdsec-pf-decision.py` et recettes
  `just crowdsec-pf-natural-baseline`,
  `just crowdsec-pf-natural-observe` (sur la workstation).
  Baseline privée `0700/0600`, exclusion des décisions et IP PF
  historiques, recherche d'un `origin=crowdsec / ban / Ip` global
  non simulé et comparaison de **la même IP** avant/pendant/après.
  Vérification de l'état Small pfSense en lecture seule.
  Les données OFFLINE n'autorisent pas un verdict PASS runtime.
  **15/15 tests hermétiques PASS** en environnement d'agent,
  nouvellement inclus dans le gate ciblé (46 tests au total) ;
  **gate 46/46 non encore exécuté sur TrueNAS**.
  Aucune baseline réelle, nouvelle décision ou remédiation PF
  attestée dans la session d'agent.
- **P0 NON VÉRIFIÉ — cycle de remédiation PF** : toujours 0 décision
  centrale au dernier diagnostic. Le gate et le `last_pull` ne
  prouvent ni l'ajout d'une nouvelle décision dans PF ni son retrait.
  Préférer une nouvelle décision naturelle et suivre la même IP
  dans LAPI puis `crowdsec_blacklists` jusqu'à disparition. Toute
  décision synthétique requiert autorisation explicite.


- **DONE — runtime central :** TrueNAS CrowdSec 1.8.1 healthy ;
  LAPI LAN :8084, métriques :6060, acquisition Loki pfSense confirmée
  (`cs_lokisource_hits_total=940`), scénario
  `firewallservices/pf-scan-multi_ports` désactivé, secret `0600`.
- **DONE — connectivité/remédiateur :** moteur local pfSense arrêté,
  bouncer firewall actif et authentifié sur TrueNAS. La liste centrale
  distingue le probe `curl` `PFSENSE_FIREWALL` de TrueNAS
  (`172.17.0.24`, 21:46:28Z) du vrai bouncer
  `PFSENSE_FIREWALL@172.17.0.1` (`172.17.0.1`,
  `crowdsec-firewall-bouncer`, 22:35:27Z).
- **Correctifs diagnostiques après exécution TrueNAS :** ancien gate
  `just crowdsec-bouncer-config-test` arrêté sur 6 erreurs de
  connexion `127.0.0.1:8084` dans les fixtures du test d'authentification.
  Les tests définissent maintenant une fonction Bash `curl` locale,
  sans exécutable temporaire ni accès réseau ; `shift` préserve les
  arguments attendus lorsque le script est chargé avec `source`.
  L'ancien contrôle de provenance a rejeté le bouncer suffixé avec
  `last_pull=22:47:47Z` parce qu'il exigeait `valid=true` (absent
  du JSON de CrowdSec 1.8.1). Correction : `revoked=false` +
  nom/IP/type/date. **9/9 scénarios du prédicat `jq` confirmés
  précédemment, et 9/9 scénarios de la sonde candidate reproduits
  localement avec le mock Bash ; gate complet `just` et réception
  runtime déjà PASS sur un relevé précédent ; le gate complet du
  28/10 est maintenant **31/31 PASS**.**
- **Gate TrueNAS (exécution utilisateur, 28/10 local) :**
  `test_crowdsec_bouncer_url_parser.py` **5/5 PASS** ;
  `test_crowdsec_candidate_bouncer_auth.py` **11/11 PASS** ;
  `test_crowdsec_pfsense_bouncer_provision.py` **2/4 PASS**
  (deux fixtures `docker inspect` échouent dans le mock,
  **pas dans le runtime**). Correction [skip ci] : simuler `docker`
  **et `timeout` dans le même interpréteur Bash**, sans exécutable
  temporaire et sans appel Docker réel. Vérification isolée
  des 3 parcours read-only : **3/3 PASS** ; la suite complète du
  provisionneur est aussi **5/5 PASS sur une copie isolée** des
  fichiers versionnés (correction d'une assertion auto-référente).
  **Supplanté :** gate CrowdSec complet TrueNAS **31/31 PASS** sur
  `5f1cd05b` (28/10).
- **Réception runtime pfSense désormais PASS au 27/10 23:12:07 UTC :**
  `diagnose-crowdsec-cutover.sh --accept` **0 erreur, 2 warnings** ;
  `PFSENSE_FIREWALL@172.17.0.1`, IP 172.17.0.1, type firewall,
  `revoked=false`, appel 23:12:07Z ; 0 décision centrale.
  Ce contrôle prouve une lecture LAPI, **pas** l'activation PF.
- **P0 ouvert — application/révocation PF :** 0 décision centrale active ;
  4 074 entrées historiques observées en PF. Il faut attester une
  **même nouvelle IP** dans LAPI puis PF, et sa disparition des deux
  couches. Ne pas attribuer les tables historiques à la LAPI centrale.
- **Gates dans la PR #289 :** `diagnose-crowdsec-cutover.sh --accept`
  exige maintenant une provenance pfSense IP + User-Agent et refuse
  le `last_pull` de `curl` comme preuve. Tests hermétiques intégrés à
  `just crowdsec-bouncer-config-test`, **exécution sur le dernier
  HEAD `5f1cd05b` : **31/31 PASS**. [Runbook PF](runbooks/crowdsec-pfsense-decision-provenance.md).
- **P0 ingress inchangé :** refus explicites HAProxy pour S3,
  ses sous-domaines et Vault ; retirer le DNS public S3, contrôler
  Cloudflare Tunnel/Access et PF/NAT depuis WAN indépendant.

Les passages historiques ci-dessous signalant un cutover « bloqué »
décrivent des états **antérieurs** et sont supplantés par cette section.
Ne pas réémettre de clé et ne pas relancer le provisionneur `--apply`.

## Dépendance inter-dépôts : DNS privé de la workstation

**Architecture de référence (source de vérité du comportement) :**
[Split-DNS, DNSSEC NTA et NetworkManager Dispatcher](https://github.com/AlbanAndrieu/ansible-workstation/blob/fix/preserve-homelab-split-dns-20261027/docs/homelab-split-dns-architecture.md).

**État courant (28/10) :** le dispatcher `root:root` (`0700`) est
installé sur la workstation. La NTA privée de `eno1` a été
**supprimée puis restaurée par un événement réel `reapply`** :
`nta_restored_by_event=PASS`,
`diagnosis=PASS_REAPPLY_PERSISTENCE`. Le dernier
`just workstation-dnssec-dispatcher-check` en lecture seule confirme :
`lan_profile=MATCH`,
`dispatcher=ROOT_EXECUTABLE`,
`link_nta=EXPECTED_ONLY`,
`private_dns=PASS`,
`public_dnssec=AUTHENTICATED`.
**Le contrôle après reboot reste à recevoir** :
ne pas redémarrer uniquement pour ce test.

**Attention :** les paragraphes historiques de cette roadmap
relatifs aux timeouts `dig`, à l'override Quad9 et aux statuts
« NTA non installée » documentent le diagnostic d'origine, **pas
l'état actuel**.

**Runbook canonique pour les agents :**
[workstation-split-dns-recovery.md](runbooks/workstation-split-dns-recovery.md).
La configuration **persistante** (profil NetworkManager, domaine
route-only, arrêt du hook hide-location) appartient au dépôt
[ansible-workstation](https://github.com/AlbanAndrieu/ansible-workstation),
[PR Ansible #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15).
Ce dépôt nabla-compose contient le diagnostic et la recette de reprise :
`just workstation-split-dns-check`,
`just workstation-split-dns-test` et
`just workstation-split-dns-repair` (**application explicite**).
Les recettes Just s'exécutent depuis le checkout **nabla-compose**,
pas depuis le worktree ansible-workstation.

**Évidence nouvelle après acceptation Chrome :** `nmcli device reapply eno1`
conserve le DNS `172.17.0.1` et `~int.albandrieu.com` ;
`getent` retourne `172.17.0.24`, mais une requête directe UDP
`dig @172.17.0.1` a expiré et `resolvectl query -4` a répondu
en 11,5 s. **Ne pas confondre panne UDP pfSense intermittente
avec ancien override Quad9** : comparer UDP/TCP, collecter des
résultats contemporains, ne pas annoncer Unbound DOWN sur un essai.
La réparation locale est volontairement bloquée si UDP pfSense
n'est pas vérifié, car elle ne répare pas Unbound.

## Roadmaps spécialisées — responsabilités et priorités

- **OpenClaw Workstation** : [roadmap dédiée](openclaw-workstation-roadmap.md),
  mise à jour le 27/10 avec **51/51 tests locaux**, puis **6/6 tests**
  de permissions PASS, catalogue `cron` complet de 21 sessions sans
  `agent:cron:main`, nettoyage de sessions accepté **uniquement
  pour leur historique**, GitOps hors secrets et rectification du
  parent symlink `nabla` à vérifier. La maintenance n'est pas encore
  exécutée ; les modèles/identités LiteLLM TrueNAS ne sont pas basculés.
- Le suivi de l'authentification Workstation LiteLLM reste
  **P0 OpenClaw** : trace `/v1/models` sans clé attribuable
  à un client TrueNAS encore non identifié ; la correction de sonde
  OpenRAG est versionnée mais non attestée déployée.

Ces points sont documentés dans la [PR #289](https://github.com/AlbanAndrieu/nabla-compose/pull/289)
sans modifier les priorités TrueNAS/pfSense/DefectDojo hors de
ce périmètre.

### Escrow YubiKey / age / SOPS — récupération validée le 27/10

- **DONE :** copie age chiffrée NFS créée, égalité des octets contrôlée, visibilité TrueNAS confirmée et inspection ACL NFS4 du fichier réalisée (droits effectifs encore à revoir).
- **DONE :** SanDisk physique de récupération reconnectée, LUKS2 monté, identité age X25519 historique attestée.
- **DONE :** déchiffrement réel de la nouvelle copie NFS avec l'identité USB et récupération de la clé SOPS attendue ; **fixture YAML SOPS chiffrée et déchiffrée avec succès** (`PASS: SOPS recovery with USB-backed escrow`).
- **P0 DONE (28/10, preuve opérateur) :** sauvegarde de l'identité privée USB protégée par phrase secrète indépendante sur workstation + TrueNAS NFS. 14/14 tests de sauvegarde et 13/13 de restauration PASS ; copies chiffrées identiques ; déchiffrement des deux archives et destinataire age historique confirmés (`BOTH_BACKUPS_RESTORED_WITH_HISTORICAL_RECIPIENT`). Aucun test SOPS de production dans cette séquence.
- **Suivi PRA à attester :** conservation de la phrase secrète hors de la SanDisk et vérification du débranchement physique durant un exercice de restauration ; l'outil de restauration, lui, ne dépend pas du support USB. Ne pas relancer la sauvegarde.
- **P1 DONE (28/10, preuve réelle) :** ACL NFS4 inventoriées sur quatre niveaux (11/11 tests PASS). Une autorisation non propriétaire **potentielle sur l'export racine** (1), aucune sur les répertoires sensibles ni l'archive. Le contrôle complémentaire a réussi (**9/9 tests PASS**, `MODE_BOUNDARY_OBSERVED`) : `secret` et `usb-recovery-backups` en **`0700`**, archive age en **`0600`**, propriétaires sensibles cohérents. Aucune correction ACL justifiée sur la seule base de l'alerte racine ; aucune mutation réalisée.
- **P1 — export NFS inventorié dans PR #295 (30/10, preuve workstation réelle) :** `sharing.nfs.query` a confirmé `EXPORT_MATCHED` et `configuration_inventory_verified=true` ; export actif et écrivable, sans filtre `hosts` ni `networks`, `maproot/mapall=UNSET`, `security=DEFAULT_UNVERIFIED` (ne signifie pas `AUTH_SYS` désactivé). **Alertes :** `NO_NFS_HOST_OR_NETWORK_FILTER`, `EXPORT_WRITABLE`. Tests synthétiques : **8 PASS / 1 FAIL** dû au chemin d'export figé dans la fixture, sans impact sur la sonde réelle. Fixture corrigée, cas négatif ajouté et alerte `NFS_SECURITY_FLAVOR_DEFAULT_UNVERIFIED` introduite : **10 tests corrigés à exécuter**. Prochaines étapes : inventaire des clients NFS et dépendances de sauvegarde, proposition d'allowlist + rollback, puis vérification de l'authentification/mappage effectifs. Aucune modification NFS/ACL/SOPS/sauvegarde ; phrase secrète indépendante encore NON ATTESTÉE.

[Runbook et preuves](runbooks/yubikey-software-recovery-20261026.md) ·
[Plan YubiKey](runbooks/yubikey-capabilities-completion-plan.md).

## DONE — DNSSEC privé : dispatcher NetworkManager et reapply acceptés (28/10)

**Preuve opérateur complète, sans GitHub Actions :**
`just workstation-dnssec-dispatcher-test` :
**17/17 tests PASS (0,016 s)** ; le contrôle read-only,
puis l'exercice borné de `resolvectl nta eno1 ""` +
`nmcli device reapply eno1` ont réussi.
La sonde a confirmé successivement :

- `lan_profile=MATCH`, `dispatcher=ROOT_EXECUTABLE`,
  `link_nta=EXPECTED_ONLY` sur `eno1` ;
- `private_nta_temporarily_cleared=true`,
  `nm_reapply=PASS`, **`nta_restored_by_event=PASS`** ;
- `private_dns=PASS` pour DefectDojo privé et
  `public_dnssec=AUTHENTICATED` pour `cloudflare.com` ;
- **`diagnosis=PASS_REAPPLY_PERSISTENCE`** ;
- nouvelle vérification read-only : mêmes états PASS,
  y compris un second `just workstation-dnssec-dispatcher-check`.

**Conclusions :** la NTA `int.albandrieu.com` n'était plus
seulement héritée du réglage manuel : sa recréation par
l'événement NetworkManager `reapply` est réellement prouvée.
Le script persistant est installé via
[ansible-workstation PR #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15),
sans exception DNSSEC pour les autres interfaces.
Pas de mutation pfSense/Unbound, de politique DNSSEC globale
ou de redémarrage forcé.

**Seul gate restant pour fermer la persistance inter-reboot :**
après **le prochain redémarrage planifié**, exécuter
depuis `nabla-compose` **sans** `--exercise` :
`just workstation-dnssec-dispatcher-check`.
Attendu : `lan_profile=MATCH`,
`dispatcher=ROOT_EXECUTABLE`,
`link_nta=EXPECTED_ONLY`,
`private_dns=PASS`,
`public_dnssec=AUTHENTICATED`.
Ne pas provoquer de reboot maintenant ; ne pas répéter
l'exercice mutateur. Le risque de latence `getent` NSS
par défaut (4,8 s dans une mesure antérieure) et les
messages DNSSEC historiques sur les domaines publics
restent des sujets **séparés**.
[Runbook](runbooks/workstation-split-dns-recovery.md).

## P0 — Gate Ansible DNS validée sur l'hôte — 28 octobre 2026

**Réception opérateur définitive du preflight sur le worktree
Ansible de la PR #15 (HEAD `d0b93e8`) :**
`test_homelab_dns_gate.py` **14/14 PASS**,
`test_homelab_dns_guard_contract.py` **8/8 PASS**,
`test_homelab_dns_nta_dispatcher.py` **17/17 PASS** ;
`--list-tasks --tags dns` trouve les tâches demandées ;
`ansible-playbook --check --diff` **PASS** :
`ok=11 changed=1 failed=0 skipped=10`.
`changed=1` prédit la seule création du dispatcher
`/etc/NetworkManager/dispatcher.d/90-nabla-private-dnssec-nta`,
**aucun fichier installé** à cette étape.
Warning Python 3.14 informatif.

**État P0 : PRÊT À APPLIQUER après décision explicite,
mais pas DONE**. L'installation ciblée du dispatcher,
la vérification de la NTA privée et du DNSSEC public après
application, puis la persistance au prochain reboot
restent à recevoir. La NTA runtime déjà validée n'a pas
été retirée ; aucun pfSense / TrueNAS modifié.

[Runbook opérateur](runbooks/workstation-split-dns-recovery.md) ;
[Ansible PR #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15).

## P0 — Gate Ansible rôle introuvable (28/10, réception suivante)

Depuis le **bon worktree** Ansible
(`f71c2f9`, branche Draft #15),
`test_homelab_dns_gate.py` **13/13 PASS** ;
`check_homelab_dns_gate.py --dry-run` a confirmé
garde DNS **8/8 PASS**, dispatcher **17/17 PASS**,
puis a **bloqué avant le dry-run** :
`Could not find specified file in role, its 'tasks/' is not usable`.
Cette fois l'échec précis provient de
`import_role: name: ../` dans
`playbooks/homelab-dns.yml`, pas d'un défaut DNS.
Le message `direnv .envrc is blocked` est
secondaire et n'appelle aucune approbation automatique.

**Fix versionné [skip ci] dans**
[ansible-workstation #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15) :
`import_tasks: ../tasks/network_split_dns.yml`
avec `vars_files: ../defaults/main.yml` ;
résolution explicite du fichier `src` du dispatcher
hors du contexte rôle ; désormais **14 tests
de la gate** (nouveau contrat des chemins).
**Restant :** nouvelle exécution locale des 14
tests, 8/8 garde, 17/17 dispatcher et
`ansible-playbook --list-tasks / --check --diff`
avec tâches DNS réellement sélectionnées ;
aucun Ansible apply encore réalisé.
[Runbook](runbooks/workstation-split-dns-recovery.md).

## P0 — Ansible preflight vide : correction du contrôle de découverte (28/10)

La dernière exécution opérateur a affiché **`Ran 0 tests`**,
`ansible-playbook --list-tasks --tags dns` **sans tâches**,
puis `--check` seulement `Gathering Facts`
(`ok=1 changed=0`). **Gate non validée** :
mauvais répertoire, branche obsolète ou filtrage
Ansible non vérifié. Aucun changement réseau effectué.

Dans [ansible-workstation #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15),
une nouvelle entrée `playbooks/homelab-dns.yml`
importe de façon statique **seulement** les tâches
split-DNS du rôle, sans autres tâches workstation.
`scripts/check_homelab_dns_gate.py` refuse le
mauvais dépôt, les suites `unittest` avec
zéro test découvert et `--list-tasks`
sans les marqueurs DNS/dispatcher.
`--dry-run` ajoute le mode Ansible
`--check --diff` et refuse un simple
`Gathering Facts` sans tâche DNS.

**État local confirmé :** 17/17 tests du
dispatcher **PASS**, 10/10 du NTA runtime
**PASS**. **Restants :** les 8 tests
`test_homelab_dns_guard_contract.py` sur HEAD
récent, 13 tests nouveaux de la gate et
validation réelle du `--list-tasks` et
`--check` de la cible. Le dispatcher
n'a **toujours pas été installé**.
La NTA private runtime `eno1` reste
acceptée ; ne pas modifier pfSense, Cloudflare
ni DNSSEC global.
[Runbook DNS](runbooks/workstation-split-dns-recovery.md).

## Réception dispatcher DNSSEC — 28 octobre 2026, 00:06 CET

**Ansible workstation : 17/17 tests offline PASS (0,907 s)**
sur `tests/test_homelab_dns_nta_dispatcher.py` : gestion
des événements NetworkManager, dérive du DNS/profil et
préservation des NTA tierces validées en simulation.
L'essai runtime préalable reste accepté :
DefectDojo privé **33,4 ms** sans bypass DNSSEC ;
`cloudflare.com` DNSSEC authentifié **43,1 ms**.

**P0 restant :** exécuter les **8 tests** de
`test_homelab_dns_guard_contract.py` sur le HEAD de
[ansible-workstation #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15),
puis inspecter `ansible-playbook ... --list-tasks --tags dns`
et `--check --diff --tags dns` avec opt-in dispatcher.
**Aucun Ansible apply, aucun reboot, aucune installation
du hook ni validation post-reboot**. L'option de NTA
persistante globale par `.negative` reste désactivée.
[Runbook](runbooks/workstation-split-dns-recovery.md).

## Réception DNSSEC privé — NTA runtime PASS, persistance par lien à valider

**Réception opérateur (27/10, workstation) :**
`just workstation-dnssec-nta-test` **10/10 PASS**.
Avant NTA, `validated_private=UNVERIFIED (5,0 s)`.
Après le `--apply` explicitement lancé :
`runtime_applied=true`, `validated_private=A_CONFIRMED (0,2 s)`,
`resolvectl query -4 defectdojo.int.albandrieu.com`
**33,4 ms** et `getent ahostsv4` retourne
`172.17.0.24`. `cloudflare.com` : **43,1 ms,
DNSSEC authenticated=yes**, attestant que la
validation publique reste active pour ce domaine.
`just workstation-nss-path` : **PASS**, mais NSS
par défaut **4,8 s** malgré les sondes DNS forcées
immédiates ; optimisation NSS toujours ouverte.

**Prochaine action P0 :** pérenniser la NTA uniquement
pour `eno1` et le profil `Wired eno1`, sans étendre
l'exception aux VPN. La [PR Ansible #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15)
contient désormais un dispatcher NetworkManager
**opt-in false par défaut**, avec rollback indépendant,
déclenché seulement pour `up`/`dhcp4-change`/`reapply`.
Il contrôle le DNS pfSense `172.17.0.1` et le
routage `~int.albandrieu.com`. La solution initiale
fichier `.negative` global est **déconseillée**
pour un poste avec VPN, car elle affecte toutes
les interfaces ; elle demeure inactive par défaut.

**Validation restante :** exécuter les
**17 tests offline** du dispatcher Ansible
(**17/17 PASS** le 28/10, 00:06 CET), vérifier la
liste des tâches tagguées `dns`, déployer
seulement après opt-in, réappliquer le lien
et vérifier DNS privé, DNSSEC public et
restauration après reboot. Aucun apply
Ansible ni restart pfSense/TrueNAS effectué.
[Runbook inter-dépôts](runbooks/workstation-split-dns-recovery.md).

## P0 — Private split-DNS DNSSEC NTA experiment (27/10)

**Diagnostic confirmé sur deux cycles (workstation) :**
`just workstation-dnssec-test` **13/13 PASS** ;
`private_validated=TIMEOUT 4s` deux fois,
`private_no_validation=A_CONFIRMED 0s` deux fois,
`public_validated=A_CONFIRMED`, pfSense
`RRSIG=yes, AD=yes` sur domaine public signé
et `dnssec-failed.org` SERVFAIL. Le chemin de
**validation DNSSEC de la zone privée** est
le défaut reproduit. Pas de preuve complète
d'une zone privée non signée ni de cause
des erreurs DNSSEC publiques.

**Implémentation préparée sans activation :**
`just workstation-dnssec-nta-test`,
`just workstation-dnssec-nta-check`,
`just workstation-dnssec-nta-try` et
`just workstation-dnssec-nta-rollback`.
`resolvectl nta eno1 int.albandrieu.com` uniquement
en opt-in, avec refus si le lien/profil ou les NTA
existantes sont incompatibles ; rollback des
seules NTA prévues, sans modification de
`DNSSEC=yes`, DoT, pfSense ou du DNS public.

**Persistence distincte dans**
[ansible-workstation PR #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15) :
fichier `.negative` pour `int.albandrieu.com`,
opt-in désactivé par défaut, rollback explicite,
handler seulement quand le fichier change.
**Attention :** le fichier scoped au domaine
est applicable sur *tous les liens*, à l'inverse
du test runtime `eno1`. Validation VPN
nécessaire avant activation.
Tests complémentaires **10 tests Compose et 1 test
Ansible** ajoutés mais pas encore exécutés.

[Runbook de reprise](runbooks/workstation-split-dns-recovery.md).
**Gate pour déclarer DONE :** NTA runtime,
réponses validées et NSS rapides, DNSSEC public
toujours OK, maintien après redémarrage avec
persistance Ansible explicitement autorisée.
Continuer à surveiller séparément les erreurs
DNSSEC sur les domaines publics.

## P0 — DNSSEC résolveur workstation (preuves 27/10 23:01 CET)

Le journal transmis par l'opérateur confirme
**1 141 erreurs `DNSSEC validation failed: no-signature`**
dans l'extrait (plusieurs domaines publics, notamment
`com DS`, `github.com`, `google.com`,
`chatgpt.com`). `resolvectl statistics`
montre **46 468 Bogus**, **5 077 timeouts**
et **716 115 transactions** cumulatives depuis
le démarrage de `systemd-resolved` du 24/10.
Le lien `eno1` est `DNSSEC=yes/supported`,
`DNSOverTLS=opportunistic`, amont
`172.17.0.1` et `~int.albandrieu.com`.
La validation DNSSEC locale est **une piste
prioritaire étayée** pour les timeouts
`resolved_native` et NSS, mais le défaut
de transmission des signatures ou d'authentification
n'est pas encore localisé.

**Code source [skip ci], PR #289 :**
`scripts/workstation/diagnose-dnssec-chain.py`,
`just workstation-dnssec-check` et
`just workstation-dnssec-test`.
Contraste entre requêtes normales et
`resolvectl query --validate=no` (désactivation
uniquement pour la requête, pas pour le réseau),
attestation `RRSIG` et `com DS` via pfSense
`dig +dnssec`, plus réponse `dnssec-failed.org`.
**13 contrats offline** ajoutés, pas encore
exécutés sur la workstation. Le diagnostic
effectue deux cycles courts et ne mute aucun
paramètre de sécurité.
[Runbook DNS inter-dépôts](runbooks/workstation-split-dns-recovery.md),
[Ansible owner #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15).

**Gate :** prouver le contraste de validation et
la présence/absence des signatures côté pfSense,
puis décider d'une correction **scopée** et
réversible déclarée dans `ansible-workstation`.
Pas de désactivation DNSSEC globale, de DNS public,
de restart Unbound ni de modification NSS sans preuve.

## Suite NSS / systemd-resolved — preuve du 27 octobre à 22:51 CET

L'opérateur a exécuté `just workstation-nss-path-test` :
**11/11 PASS** sur les contrats v1, puis
`just workstation-nss-path` : `resolved_native=TIMEOUT 6s`,
`stub_udp=NO_ANSWER 2s`, `nss_dns=A_CONFIRMED 3,4s`,
`nss_resolve=NO_ANSWER 0s`,
`nss_default=TIMEOUT 6s`. **Incident intermittent multi-couche** :
l'ancien diagnostic « NSS seul » n'est pas soutenu par ce
relevé. La sonde `stub_udp` v1 utilisait `dig +short`,
dont le statut ne distingue pas SERVFAIL/NODATA/timeout.

**Action versionnée dans Compose PR #289 :** diagnostic
`workstation-nss-path` v2 avec réponse stub et codes RCODE,
signaux individuels indépendants de la classification primaire,
plusieurs échantillons bornés
(`just workstation-nss-path-samples` :
`--samples 2 --timeout 3`) et tests de non-régression
complémentaires. **Nouvelle suite locale à exécuter** au HEAD ;
ne pas présenter les nouveaux tests comme PASS.
[Runbook DNS](runbooks/workstation-split-dns-recovery.md).

**Décision :** observer les journaux
`systemd-resolved` et le chemin stub. `DNSOverTLS=opportunistic`
et `DNSSEC=yes/supported` sont des paramètres relevés,
**pas des causes établies**. Aucun changement DNSSEC,
DoT, pfSense, `nsswitch.conf` ou système proposé tant
que les RCODE et les échantillons ne sont pas disponibles.

## Diagnostic NSS différentiel — 27 octobre

**Preuve opérateur la plus récente :** le profil NetworkManager
et la zone privée sont toujours conformes ; DNS pfSense UDP/TCP
`A_CONFIRMED (0.0s)`. Pourtant `getent` dans la sonde met
**12,4 s** et la commande interactive `getent ahostsv4`
met **25,030 s sans résultat**, tandis que `resolvectl query -4`
répond en **149 ms**. `nsswitch.conf` utilise
`files mdns4_minimal [NOTFOUND=return] dns mymachines` ;
la cible de `/etc/resolv.conf` est le stub systemd-resolved.
**Panne intermittente de la chaîne NSS/glibc**, origine précise
non prouvée. Ne pas remettre en cause Unbound sans données
supplémentaires ni changer les DNS de la workstation.

**Code [skip ci] dans PR #289 :** la recette
`just workstation-nss-path` compare les chemins
`resolvectl`, `dig @127.0.0.53`,
`getent -s hosts:dns`, `getent -s hosts:resolve`
et `getent` normal, avec délai individuel borné.
`just workstation-nss-path-test` contient les tests
hors ligne sans pytest. Tests **à exécuter localement**,
pas de statut PASS annoncé pour la nouvelle suite.
[Runbook canonique](runbooks/workstation-split-dns-recovery.md).
Une éventuelle mutation NSS doit être déclarative dans
[ansible-workstation](https://github.com/AlbanAndrieu/ansible-workstation),
seulement après confirmation du module responsable.

## Réception split-DNS — 27 octobre, 22:24 CET

**RUNTIME ACCEPTED (hors post-reboot) :** l'opérateur a exécuté
`just workstation-split-dns-test` **16/16 PASS** (deux fois).
Le premier `--check` a classé la résolution NSS
`UNRESOLVED (14.0s)`, malgré le DNS pfSense UDP/TCP confirmé.
Après l'exécution explicitement autorisée de
`just workstation-split-dns-repair`, le résultat est
`diagnosis=PASS` et `client_nss=A_CONFIRMED (2.0s)`.
Un contrôle supplémentaire est **PASS** avec NSS
`A_CONFIRMED (5.2s)` et avertissement de latence.
NetworkManager `MATCH`, route privée `PERSISTED`,
resolved `MATCH/ROUTED`, unités `hide-location` désactivées.
La requête DNS pfSense **TCP directe** a répondu en **27 ms**
à 22:24:07 CET ; les probes du script ont confirmé UDP et TCP
sur le même poste. L'ancienne expiration UDP n'est **pas
reproduite** à cet instant, mais les performances NSS
restent variables.

**Reste à terminer :** réception après redémarrage de la
workstation (persistance au démarrage), puis diagnostic de
latence `resolvectl` vs `getent` si elle reste supérieure
à 5 secondes. Aucun redémarrage pfSense, changement de
proxy ou redéploiement TrueNAS justifié.
[Runbook transverse](runbooks/workstation-split-dns-recovery.md)
et [propriétaire Ansible](https://github.com/AlbanAndrieu/ansible-workstation/pull/15).
La synchronisation des secrets DefectDojo/Vaultwarden est indépendante.

## Dernière réception runtime — 27 octobre 2026 (18:47–18:53 UTC)

Les preuves les plus récentes priment sur les descriptions historiques
`DEPLOYING` / `UNREACHABLE` du 26 et début 27 octobre.

| Priorité | Domaine | Preuve | Reste à terminer |
| --- | --- | --- | --- |
| H-03 | DefectDojo | **ACCEPTED runtime LAN** : TLS/Traefik/Chrome, workstation split-DNS persistent NM ; **NTA par lien `eno1` runtime appliquée avec succès**, nom privé validé sans bypass (33,4 ms), `getent` répond, DNSSEC public `cloudflare.com` authentifié (43,1 ms), **10/10 tests NTA PASS** | **Persistence de NTA après reboot NON VALIDÉE** : dispatcher NM opt-in dans [Ansible #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15), 17/17 dispatcher PASS, 8/8 garde PASS, 14/14 gate PASS ; Ansible `--list-tasks` et dry-run PASS ; **dispatcher installé et DNS privé/public validés**, reapply/reboot à confirmer ; NSS défaut encore **4,8s** malgré DNS forcé rapide ; synchronisation des secrets Django/Vaultwarden séparée |
| H-05 | Prometheus | Readiness + API targets HTTP 200, clé et secret monté ; sur 8 jobs nommés, 3 `scrape_up` (dont `fastapi_sample`), 5 `scrape_down` | 4 connexions `tcp_refused`, 1 `http_401` LiteLLM Hermes ; pas de restart global |
| H-06 | Akvorado | +6 flux en 20 s, +6 `metadata_missing`, +12 `metadata_provider_errors`, +0 batch ClickHouse | Mapping metadata `ifIndex` puis inserts SQL **NOT_VERIFIED** |
| H-07 | Catalogue / ressources | 143 RUNNING, 91 mappés, 52 non mappés, 151 entités déclaratives, GPU indisponible | Corriger les mappings, refaire le snapshot **après** redémarrage DefectDojo |
| H-08 | Vaultwarden | `code`/`openrag` absents du cache CLI ; DefectDojo : 5 secrets MATCH, `DD_ADMIN_USER=DRIFT`, mot de passe coffre absent/vide | `bw sync`, vérifier l'item source, puis rapprocher le mot de passe Django avec runtime et coffre sans journaliser de secret |
| H-09 | RAM TrueNAS | 61 Gio total, 7,3 Gio disponibles avant la reprise ; Netdata et Graylog arrêtés | Baseline PSI/mémoire/OOM sans attribuer causalement le pic à ces services |

**Prochaine étape prioritaire :** enregistrer la route DNS privée
`~int.albandrieu.com` dans le profil NetworkManager `Wired eno1`,
puis vérifier `nmcli device reapply eno1` sans reconnexion complète.
Le DNS `172.17.0.1` et `ipv4.ignore-auto-dns=yes` étaient déjà
persistés dans ce profil. Le contournement `resolvectl dns/domain`
n'est pas une configuration durable.

**Incident résolu côté accès utilisateur :** `hide-location.service`
écrivait périodiquement Quad9 ; l'opérateur a désactivé **service
et timer**, restauré le DNS pfSense, confirmé `getent` et
`just defectdojo-workstation-dns-check` PASS et ouvert
DefectDojo avec Chrome. `ansible-workstation` PR #15 contient
désormais la désactivation déclarative par défaut ;
**7/7 tests unitaires PASS** sur le commit d'avant l'ajout
de cette note de documentation, mais l'Ansible **n'a pas été appliqué**.

La résolution `resolvectl query` reste lente (22,5 s puis 10,7 s) :
comparer `dig +stats @172.17.0.1` au chemin `systemd-resolved`.
Ne pas modifier `/etc/resolv.conf`, les fichiers legacy
`/etc/resolvconf/resolv.conf.d`, pfSense/Unbound ni Traefik
sur la base de cet incident clos. Les secrets Django/runtime/
Vaultwarden restent un chantier séparé.
[Runbook de réception](runbooks/defectdojo-private-ingress-acceptance.md).

[Preuves et séquence de réception](runbooks/2026-10-27-defectdojo-resources-vault-observability.md).

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

## P0 — Échec du build FastAPI TrueNAS #380 (27 octobre 2026)

- **Incident historique :** le premier build FastAPI 0266f20d était bloqué
  par Docker Hub 429. **Déploiement ultérieur 6/6 réussi** sur TrueNAS :
  FastAPI 1.25.0, conteneur running, `/health` HTTP 200, santé 4/4.
  L'identité de l'image Docker est vérifiée, mais
  `build_revision=null` ne prouve pas le SHA compilé.
- **Journal privé :** /tmp/tmp.ngofCbFlgw (0600) ; ne pas imprimer,
  copier, annexer ni transmettre le contenu.
- **Analyse Git :** Dockerfile fa13c08d = Dockerfile 0266f20d,
  blob SHA 9c1e1da90c66612ec65001e01d9115956b18104a.
  **Cause immédiate prouvée :** Docker Hub HTTP 429 lors du HEAD
  sur les métadonnées de l'image officielle Python ; la nature pull quota
  ou limite anti-abus reste à distinguer.
- [x] PR Compose #289 : nouveau classifieur de journal privé à
  codes fixes, intégré au script de déploiement sur échec ;
  aucune lecture de secret dans les sorties.
- [x] Classifieur exécuté sur TrueNAS : journal privé vérifié
  `UID=1000`, `0600`, un lien ; `unsafe_log_owner` corrigé.
  La première analyse retourne `unclassified_build_failure`, aucun secret divulgué.
- [x] Classification rejouée : `buildkit_generic_failure`,
  `failure_stage=unknown`, `failure_operation=unknown`, journal entier
  de **1324 octets** ; cause racine toujours inconnue.
- [x] Empreinte terminale recueillie : `registry`, `python`,
  `unexpected`, `request` ; une erreur BuildKit numérotée et un marqueur
  de résolution. Suspicion de requête vers le registre de l'image Python.
- [x] Diagnostic complet : `internal/image_metadata`,
  `docker_hub/official_python`, méthode `HEAD`, HTTP `429`.
  Le premier test `cached=no_or_access_error` était ambigu.
- [x] Après `docker system prune`, préflight opérateur confirmé :
  `docker_daemon=accessible`, `python_cache=absent`,
  `build_client=sudo_candidate`, `sudo_docker_config=missing`.
  Le prune n'efface pas les limites Docker Hub ; certains conteneurs
  arrêtés et réseaux inutilisés ont aussi été supprimés.
- [x] PR Compose #289 : garde-fou avant build local sans cache et sans
  déclaration d'identifiants Docker Hub, délai local après 429,
  pas de retry automatique ni de fallback après un pull limité.
  La protection ne sera active sur TrueNAS qu'avec le checkout mis à jour.
- [x] Validation opérateur depuis TrueNAS dans un worktree détaché
  au SHA `3eb2d963` : `bash -n` PASS, **35/35 tests PASS**,
  nettoyage du worktree terminé, aucune CI ni build.
- [x] Authentification Docker Hub `sudo docker login` réussie ;
  le client privilégié dispose maintenant d'une session Docker Hub.
  Docker a averti que les identifiants sont stockés sans chiffrement
  dans `/root/.docker/config.json` ; protéger les droits et prévoir
  un gestionnaire d'identifiants compatible TrueNAS.
- [ ] Rejouer les tests locaux après les ajustements pour le login par
  navigateur (`identitytoken`) ; vérifier la santé réelle des services
  avant toute tentative d'upgrade. Ne pas supposer le HTTP 429 levé.
- [ ] Auditer les applications TrueNAS arrêtées et leurs réseaux après prune,
  sans redémarrage global.
- [x] Docker Hub : `sudo docker login` réussi, identité `root:root` / `0600`,
  `sudo docker pull python:3.13-slim-trixie` réussi. Le digest observé
  commence par `sha256:b3575dcf816c` ; cela ne valide pas les autres pulls du build.
- [x] Upgrade exécuté par l'opérateur avec `FASTAPI_SAMPLE_REF=0266f20d7ff1278bf7dd36ac15a22618d04b3742` :
  6/6 terminé, FastAPI 1.25.0, 4/4 healthy, digest image cohérent,
  observateur et allowlist OK ; sous-module gitlink parent encore sur
  `441d0a7e`, sans commit automatique.
- [x] Les **11 tests d'acceptation IA** passent sur TrueNAS.
  `litellm_proxy_liveness=http_200`, `litellm_key=present`,
  `litellm_key_format=sk_prefix`, mais `GET /v1/models` **HTTP 401**.
- [x] Auth upstream TrueNAS vérifiée : service `litellm` running,
  `LITELLM_FASTAPI_WORKSTATION_API_KEY=absent`,
  `LITELLM_IDE_API_KEY=present` et liveliness workstation HTTP 200.
  **Deux blocages indépendants** : clé consommateur refusée et clé de
  relais absente. Aucun appel de modèle n'a été envoyé.
- [x] Ajout dans la PR #289 de sondes lecture seule :
  `check-fastapi-litellm-runtime-keys.py` (présence, permissions et
  comparaison valeur-en-mémoire sans divulgation) et
  `check-fastapi-litellm-sample-source.py` (source Vaultwarden
  `nabla/prod/sample-litellm` sans lecture publiée).
- [ ] Exécuter les tests locaux des deux nouveaux diagnostics ;
  comparer la présence de chaque secret entre Vaultwarden, fichier canonique
  et conteneur. **Attention : l'item `sample-litellm` est distinct du
  fichier runtime `sample/.env.secrets` ; pas de remplacement aveugle.**
- [ ] Vérifier dans la base LiteLLM TrueNAS la clé dédiée
  `fastapi-sample-staging`, son scope `fastapi-qwen`, sa validité,
  expiration et son budget **8 USD à vie** avant tout re-provisionnement.
  Ne pas utiliser les clés master ou IDE comme contournement.
- [ ] Restaurer uniquement la clé dédiée upstream
  `LITELLM_FASTAPI_WORKSTATION_API_KEY` après vérification de sa source ;
  prévoir si nécessaire un redéploiement ciblé de LiteLLM TrueNAS
  **après** revue, sans toucher à FastAPI/Ollama/OpenRAG.
- [ ] Une fois les deux clés autorisées, un seul smoke d'inférence
  synthétique opt-in vers workstation `qwen`.
- [x] Connectivité observée depuis le conteneur FastAPI : Ollama
  HTTP 200 ; OpenRAG backend et frontend HTTP 200 ; MCP HTTP 406
  (transport, pas authentification). Prometheus/Gatus `gatus_up=1`,
  `synthetic_samples=85`, pfSense RBAC 7/7.
- [ ] OpenRAG : prévoir un client MCP et les ACL privées avant de
  déclarer l'intégration fonctionnelle ou de tester la recherche privée.
- [x] Ajouter dans #289 `accept-fastapi-ai-connectivity.py` et son test local
  pour produire uniquement des codes de transport/auth (sans secrets).
- [x] Réseaux `intranet` / `traefik_network` présents ; build complété ;
  déploiement 6/6 et santé FastAPI confirmés par l'opérateur.
- [x] Tests IA initiaux : 9 méthodes, 4 FAIL et 1 ERROR. Corrigé dans la
  PR #289 : contrôle du type JSON avant test d'appartenance à un set ;
  assertions de non-divulgation basées sur un rapport fixe, pas sur le
  mot générique `secret`.
- [ ] Rejouer les 9 tests d'acceptation IA corrigés depuis un worktree
  isolé **après la fin** de l'upgrade en cours ; ne pas relancer le
  déploiement et ne pas effacer les changements du sous-module.
- [x] Rapport final 6/6 reçu : FastAPI running HTTP 200, LiteLLM 401,
  Ollama 200, OpenRAG backend/frontend 200, OpenRAG MCP 406.
  La connexion MCP/ACL OpenRAG reste un chantier distinct. Voir
  [recette IA après déploiement](runbooks/fastapi-truenas-ai-acceptance-20261027.md).
- [ ] Vérifier l'état du conteneur précédent et son endpoint health.
- [ ] Une fois la cause identifiée, déployer un unique SHA
  immuable et exiger la recette 6/6.
- [ ] **UI :** comparer normal et safe seulement après activation
  réelle du commit 0266f20d ou ultérieur ; les deux tests
  main_thread_unresponsive ont précédé le build échoué.

[Runbook du build privé](runbooks/fastapi-truenas-build-failure-20261027.md).

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
| Diagnostics Prometheus | `credential_ready=true`, `METRICS_RUNTIME_PRESENT=true`, `METRICS_SECRET_MOUNT_PRESENT=true` ; `diagnose-failed-scrapes.py --check` échoue avec **`TimeoutError`** sur l’API cible | **SOURCE/RUNTIME/MOUNT PRESENT / SCRAPE UNVERIFIED** : lancer `sudo python3 scripts/truenas/diagnose-fastapi-prometheus-runtime.py --check` directement sur TrueNAS ; classifier readiness et cible sans exposer les secrets ni redémarrer Prometheus |

**Dernières preuves (26/10, suite) :** FastAPI confirme la
présence de `METRICS_SCRAPE_KEY` dans son processus ; Docker confirme
le bind `/run/secrets/fastapi-sample-metrics.key` dans Prometheus,
sans lecture de valeur. Cependant `/api/v1/targets` **expire après
5 secondes** : ni `scrape_up` ni un échec d'authentification ne sont
établis. La sonde SSH `--ssh-sudo`, auparavant HTTP 200 pour trois
composants IA, retourne ensuite `ssh_unavailable_or_unauthorized`.
Ne pas inférer l'état des services de ces échecs réseau intermittents.
Utiliser sur TrueNAS `sudo python3
scripts/truenas/diagnose-fastapi-ai-chain.py --check --runtime` pour
éviter l'étape SSH et `sudo python3
scripts/truenas/diagnose-fastapi-prometheus-runtime.py --check` pour
classer séparément Prometheus `/-/ready`, l'API cible et Docker.
Les deux outils ne modifient pas les services.

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

**H-03 / reprise du compte admin (27/10, PR #289) :** la preuve récente
`DEPLOYING` / uWSGI non disponible ne doit pas être effacée par
l'ancien HTTP 200 du 26/10. Le compte Django historique `admin` existe
au dernier inventaire, mais `DD_ADMIN_USER=DRIFT` et
`DD_ADMIN_PASSWORD=UNVERIFIED` dans la comparaison Vaultwarden.
**Voie courte retenue :** lorsque `defectdojo-uwsgi` est `running`,
utiliser `sudo docker exec -it defectdojo-uwsgi python manage.py changepassword admin`
dans un TTY privé, puis mettre à jour l'entrée Vaultwarden existante
et tester le login. Si uWSGI est absent, lancer les diagnostics
`diagnose-defectdojo-deploying.py` et
`diagnose-defectdojo-postgres-waits.py` ; pas de DROP DB ni de
redéploiement répété. **RUNTIME / LOGIN NOT_VERIFIED.**
[Procédure courte](runbooks/defectdojo-admin-access-recovery.md).

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
- [ ] **H-04 / CrowdSec P1 — nouvelle preuve runtime du 26/10 :**
  ancien audit du 25/10 `firewall_bouncer=stopped_or_unknown`
  **supplanté par une preuve directe**. Sur pfSense :
  moteur local **RUNNING**, bouncer **RUNNING**, API locale
  `http://172.17.0.1:8089` ; deux tables PF présentes avec
  **9399 + 22 = 9421 entrées**. Ces remédiations ne viennent
  **pas** du moteur TrueNAS (LAPI centrale : zéro décision,
  bouncer `PFSENSE_FIREWALL` enregistré mais `last_pull=<none>`).
  Ne pas arrêter le moteur pfSense tant que la connexion centrale
  n'est pas fonctionnelle : préserver les règles en vigueur.
  `service.pfb_filter=0` demeure une observation à revoir.
  TrueNAS CrowdSec 1.8.1 RUNNING/healthy ; LAPI `172.17.0.24:8084`
  et métriques `:6060` accessibles ; mauvais scénario désactivé.
  **Bloqueurs :** secret de cutover absent/illisible et mode Large
  toujours actif. La requête Loki `device=pfsense` a échoué dans
  le premier diagnostic puis réussi dans le second ; compteur
  `cs_lokisource_hits_total=940`. Correctif code PR #285 :
  **une relance bornée**, warning si récupérée, erreur si
  classification toujours absente. Ne pas changer Alloy sur la
  seule preuve du premier essai.
  **Preuve opérateur ultérieure :**
  `just crowdsec-loki-evidence-test` **5/5 PASS** ;
  `just nexus-private-ingress-test` **4/4 PASS**.
  Loki `sum by (device) (count_over_time({job="pfsense",app!="nabla-smoke"}[30m]))`
  retourne **1 247 événements, tous agrégés dans la série
  `device=pfsense`** sur la fenêtre observée. La classification
  canonique fonctionne dans ce relevé ; ne pas modifier Alloy.
  La cause de l'échec ponctuel précédent reste inconnue ; conserver
  la relance bornée et surveiller sa classe de résultat.
  Tests exécutés dans le checkout de l'opérateur, **pas
  automatiquement sur chaque nouveau HEAD concurrent**.
  [Runbook CrowdSec](../apps/crowdsec/README.md).

- [ ] **H-04 / CrowdSec central TrueNAS → pfSense Small :**
  architecture déjà déclarée dans `apps/crowdsec/compose.yml`
  (moteur central v1.8.1 + LAPI LAN `172.17.0.24:8084` ;
  scénario `firewallservices/pf-scan-multi_ports` désactivé).
  **Preuves runtime disponibles, cutover toujours bloqué :**
  TrueNAS app RUNNING/healthy, LAPI `:8084` OK, scénario risqué
  désactivé, Loki `device=pfsense` confirmé par 1 247 événements ;
  `--runtime` avait néanmoins échoué une fois lors de la vérification
  Loki. `--check` échoue sur le secret absent/illisible ; bouncer
  central inscrit sans `last_pull`. Côté pfSense, `--preflight`
  confirme moteur local encore actif, bouncer connecté à
  `172.17.0.1:8089` et tables PF actives. Rejouer `--runtime`
  après intégration de la relance bornée, sans modifier de service.
  Ne basculer qu'après confirmation de la clé existante
  `BOUNCER_KEY_PFSENSE_FIREWALL` (valeur non affichée), de l'identité
  du bouncer et de la connectivité LAPI depuis pfSense.
  **Ne pas arrêter le moteur ni le bouncer local actuellement
  actifs** avant d'avoir une API distante authentifiée et un rollback
  prêt. Une fenêtre de bascule explicite est requise. Réception : diagnostic TrueNAS `--accept` et
  workstation `--accept` (tables PF et `last_pull`), sans générer
  de nouvelle clé ni publier le port 8084 sur WAN.
  **Reprise 27/10 :** le relevé fourni concerne HAProxy et DNS,
  pas une nouvelle preuve CrowdSec. L'ancien moteur pfSense est
  désormais un **warning** dans le mode `--preflight` et reste
  une erreur en `--accept`. Recettes read-only :
  `just crowdsec-pfsense-preflight` et
  `just crowdsec-pfsense-accept`. Une authentification centrale
  `central_lapi_http=200`, une clé approuvée et `last_pull`
  central sont nécessaires avant de conclure au cutover.
  Si clé absente/incorrecte : **NO-GO**, sans rotation implicite.
  **Réception pfSense Small — 27/10, DERNIER ÉTAT :**
  `central_candidate_auth=ACCEPTED`, fichier bouncer
  TrueNAS présent avec droits `0600`, LAPI centrale healthy,
  `--check` TrueNAS **failures=0 warnings=2** ;
  enregistrement `PFSENSE_FIREWALL last_pull=2026-10-27T21:46:28Z`
  (provenance non attestée, un préflight peut l'actualiser).
  Workstation `just crowdsec-pfsense-accept`
  **failures=0 warnings=0**, moteur pfSense local absent,
  bouncer actif sur `http://172.17.0.24:8084`,
  tables PF 4033 IPv4 + 52 IPv6 = **4085** entrées.
  Probe pfSense `central_lapi_http=200`,
  `central_lapi_auth=ACCEPTED`.
  **SMALL_BOUNCER_CUTOVER_PASS** : ne plus réémettre la
  clé ni relancer `--apply` ; acceptation du bouncer acquis.
  Les entrées PF existantes ne prouvent cependant pas
  leur origine centrale, alors que LAPI annonce zéro
  décision active : reste à attester un polling pfSense
  post-bascule et l'application/retrait d'une décision.
  **Erreur GUI pfSense spécifique :**
  le paquet `crowdsec_validate_form` exige
  `remote_agent_user` et `remote_agent_password` dès que
  `enable_lapi` est OFF, **même avec Log Processor OFF**.
  Le besoin est administratif (validation de la GUI),
  indépendant du bouncer déjà authentifié. Vérifier
  `sudo docker exec crowdsec cscli machines list` ;
  si nécessaire, créer une machine dédiée `pfsense-small`
  sur TrueNAS (sans réutiliser le login machine `truenas`),
  renseigner ses credentials en GUI, garder Agent OFF.
  `CROWDSEC_REMOTE_API_USER/PASSWORD` dans le shell n'est
  pas une liaison automatique avec les champs pfSense.
  [Runbook CrowdSec](../apps/crowdsec/README.md).
  **Incident de clé 27/10 (NO-GO temporaire) :** ancien
  `PFSENSE_FIREWALL` supprimé par le premier provisionneur,
  `cscli bouncers add -o raw` a ensuite renvoyé un format
  rejeté (`unexpected key format`) : la clé nouvellement
  créée n'a pas été conservée, le fichier runtime reste absent
  et le bouncer pfSense continue à utiliser `:8089` (HTTP 403
  contre la LAPI centrale). Tests Small post-cutover :
  **2 échecs attendus**, moteur local actif et mauvaise URL ;
  PF local encore 8 582 entrées.
  Le script est corrigé : génération `openssl rand -hex 32`,
  stockage root:root 0600 **avant** de toucher l'inscription,
  puis `cscli bouncers add --key` sur l'entrée standard Docker.
  **Avant toute nouvelle émission**, tenter la récupération
  depuis les variables TrueNAS existantes :
  `CROWDSEC_BOUNCER_API_KEY` (bouncer candidat),
  `BOUNCER_KEY_TRAEFIK` (clé Traefik distincte),
  `CROWDSEC_LOCAL_API_PASSWORD` (compte machine, **pas**
  une clé de bouncer). Probe read-only :
  `bash scripts/truenas/check-crowdsec-candidate-bouncer.sh
  --env CROWDSEC_BOUNCER_API_KEY` avec variable exportée ;
  `central_candidate_auth=ACCEPTED` ne prouve pas l'identité
  du bouncer. Alias d'import Vaultwarden :
  `CROWDSEC_PFSENSE_BOUNCER_KEY` dans manifest.json.
  `just crowdsec-bouncer-config-test` étendu à **19 tests**
  (anciens 11 PASS, 8 nouveaux non relancés par l'opérateur).
  Les opérations restent locales/readonly tant que la clé
  et l'inscription centrale ne sont pas réconciliées.
  **Décision opérateur postérieure :** accepter la reconstruction
  progressive des remédiations PF à partir des décisions centrales
  (sans migration des 8 637 anciens blocages).
  Le bouncer central existant `PFSENSE_FIREWALL` est inscrit
  mais n'a jamais été sollicité (`last_pull=<none>`) et la clé
  de l'ancienne LAPI pfSense est rejetée par TrueNAS (403).
  **Chemin court :** réémettre cette inscription inutilisée
  depuis TrueNAS uniquement avec
  `sudo bash scripts/truenas/provision-crowdsec-pfsense-bouncer.sh --check`
  puis l'option explicite `--apply`; la nouvelle clé va
  dans `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`
  (root:root 0600, aucune sortie secret). Valider
  `central_candidate_auth=ACCEPTED`, puis configurer
  `Services → CrowdSec` sur pfSense : Remote LAPI
  `http://172.17.0.24:8084`, conserver Remediation Component,
  désactiver Log Processor et Local API. Valider
  `--accept` et `central_lapi_http=200`; tables PF vides
  tolérées pendant la reconstruction centrale.
  Aucun changement runtime n'a été effectué par la PR ;
  nouveau contrôle local `just crowdsec-bouncer-config-test`
  contient les tests d'émission de clé à exécuter.
  **Réception CrowdSec 27/10 21:53 :**
  sur TrueNAS, `--runtime` **0 erreur / 1 warning**,
  CrowdSec 1.8.1 RUNNING/healthy, LAPI :8084 et métriques :6060,
  Loki canonique confirmé (940 hits), scenario dangereux désactivé,
  **0 décision active**. `--check` : **1 erreur / 2 warnings**
  (fichier `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`
  absent/illisible, `PFSENSE_FIREWALL last_pull=<none>`).
  Workstation `just crowdsec-pfsense-preflight` :
  **0 erreur / 2 warnings**, moteur local actif, bouncer sur
  `http://172.17.0.1:8089`, TCP TrueNAS :8084 joignable,
  **8 620 IPv4 + 17 IPv6 = 8 637 remédiations PF locales**.
  Probe authentifiée de la clé pfSense actuelle vers
  TrueNAS : **`central_lapi_http=403`**.
  **NO-GO : ne pas désactiver l'ancien moteur ni changer
  la source du bouncer**, le serveur central n'offre encore
  aucune décision et sa clé dédiée n'est pas prouvée.
  Nouveau Gate candidat `sudo bash
  scripts/truenas/check-crowdsec-candidate-bouncer.sh` :
  lit seulement le fichier privé 0600, vérifie la clé centrale
  sans l'afficher ; sortie requise `central_candidate_auth=ACCEPTED`.
  Récupérer la clé centrale dans un coffre approuvé ou préparer
  une **réémission distincte autorisée**, avec sauvegarde et
  rollback. Prévoir la conservation des remédiations PF pendant
  le changement de LAPI (8 637 entrées locales vs 0 centrale).
  Gate offline `just crowdsec-bouncer-config-test` :
  tests URL pfSense et authentification candidate simulée.
  Réexécuter `--check`, `--accept` TrueNAS/workstation et
  attester `last_pull` et une décision centrale appliquée
  puis expirée dans PF avant de clôturer la migration.
  Ces nouveaux tests sont **NON EXÉCUTÉS** dans la sortie
  opérateur disponible ; aucune mutation de runtime.
  [Guide central CrowdSec](../apps/crowdsec/README.md).
- [x] **Nexus / DNS, rendu TrueNAS et runtime réconciliés (26/10) :**
  DNS privé **8/8 PASS** ; backend direct `172.17.0.24:8081`
  **HTTP 200** ; HTTPS privé **404 avec TLS vérifié**.
  TrueNAS Custom App `ix-nexus` inclut exactement
  `/mnt/cpool/compose/nabla-compose/apps/nexus/compose.yml` ;
  aucun changement local signalé dans `apps/nexus` ;
  `traefik_network` existe. Le rendu TrueNAS contient les labels
  `nexus-private` avec `traefik.enable="false"`.
  **Après redémarrage/réconciliation opérateur**, TrueNAS
  `nexus=RUNNING`, labels effectivement appliqués au conteneur
  (`enabled="false"`, règle Host et service `nexus-private`),
  backend toujours **200**, HTTPS privé toujours **404 / TLS 0**.
  L'écart de labels **est résolu** ; le 404 privé est le
  résultat attendu du routeur délibérément inactif.
- [ ] **Nexus P0 — refuser le Host privé au frontend WAN pfSense :**
  **Réception opérateur le 27/10 :** `just nexus-private-ingress-test`
  **15/15 PASS** (5 contrats Nexus + 10 inspecteur),
  HEAD `7300e891` ; frontend `main_Web_HTTPS`.
  ACL `nexus` ligne 89 ; route spécifique Nexus ligne 128
  `use_backend prod_front-traefik-https_ipvANY if nexus
  aclcrt_main_Web_HTTPS`. Backend Traefik déclaré ligne 311 :
  `backend_server=traefik-https target=172.17.0.24:443`,
  `backend_mode=http`. **Chaîne HAProxy → Traefik confirmée**
  dans la configuration générée. L'ancien backend
  `nexus-albandrieu_ipvANY` est absent ; ne pas le recréer.
  TrueNAS Nexus RUNNING, backend :8081 HTTP 200,
  routeur Traefik privé toujours `traefik.enable=false` ;
  HTTPS privé 404 avec TLS valide est attendu à ce stade.
  **Nouvelle règle signalée par l'opérateur (27/10) :**
  `acl nexus var(txn.txnhost) -m reg -i
  ^nexus\\.int\\.albandrieu\\.com(:[0-9]{1,5})?$`
  et `http-request deny deny_status 403 if nexus
  aclcrt_main_Web_HTTPS`.
  **Nouvelle réception opérateur :** le frontend généré
  `main_Web_HTTPS` contient l'ACL Nexus regex ligne **89**,
  `http-request set-var(txn.txnhost) hdr(host)` ligne **96**,
  puis `http-request deny deny_status 403 if nexus
  aclcrt_main_Web_HTTPS` ligne **117**. La workstation LAN
  vers l'IP publique `82.66.4.247:443` obtient
  **HTTP 403 et TLS vérifié (tls=0)**, alors que le relevé
  précédent était 404. **LAN_HAIRPIN_DENY_OBSERVED — PASS**
  pour le chemin testé. Les 15 tests du gate local restaient
  PASS au relevé précédent ; le statut WAN est distinct :
  **WAN_REJECTION_NOT_VERIFIED**.
  L'ACL `nexus` est réutilisée pour le routage ; une ACL
  autonome `nexus_private_wan` reste une amélioration possible,
  mais n'est pas un blocage immédiat puisque la condition
  présente correspond au Host attendu et le 403 est observé.
  Poursuivre : vérifier le rechargement effectif HAProxy,
  tester séparément `--resolve ...:443:172.17.0.24` vers
  Traefik LAN, confirmer l'absence de régression de
  `s3.int.albandrieu.com` et de `nexus.albandrieu.com`,
  et confirmer le rejet depuis une source WAN réelle ou preuve
  réseau équivalente (NAT reflection possible depuis le LAN).
  Garder `NEXUS_PRIVATE_INGRESS_ENABLED=false` jusqu'à
  réception de cette protection et rollback documenté.
  [Gate 12 du runbook](runbooks/nexus-private-dns-ingress.md).
  N'activer `NEXUS_PRIVATE_INGRESS_ENABLED=true` qu'après
  preuve acceptable du contrôle d'accès WAN et vérification
  du modèle Compose rendu ; déployer Nexus seul ensuite.

- [ ] **Ingress P0 — audit HAProxy/DNS/Tunnel/PF, refus privés :**
  Snapshot fourni `/var/etc/haproxy/haproxy.cfg` généré
  le **27/10 à 20:47**, conservé expurgé dans
  `docs/evidence/pfsense/haproxy-2026-10-27.generated.redacted.cfg`
  (non déployable, IP WAN/bureau et références certificats masquées).
  Référence déclarative : `config/ingress-access-policy.json`.
  `scripts/pfsense/audit-haproxy-ingress.py` compare l'état
  généré actuel au snapshot via SSH en lecture seule
  (`just pfsense-haproxy-policy-live`), classe
  séparément HAProxy / DNS public / Tunnel / PF et
  refuse d'inférer PASS de preuves absentes.
  `scripts/ingress/collect-public-dns-evidence.py` sonde
  deux résolveurs publics (A/AAAA/CNAME), distingue
  timeout/désaccord de l'absence DNS réelle.
  **Faits du snapshot :** Nexus 403 déclaré, refus
  HAProxy **absent pour `vault.int.albandrieu.com`** ;
  alias `vaultwarden.int.albandrieu.com` sans ACL dédiée ;
  `s3.int.albandrieu.com` sans refus. **Décision confirmée le
  27/10 : S3 reste privé LAN ; Garage WebUI public est un
  service distinct (Cloudflare Tunnel + Access).**
  Les anciennes descriptions publiques ont été corrigées.
  Backend HAProxy Traefik TLS `verify none` à durcir
  séparément. **Aucune règle WAN/DNS/Tunnel/Firewall
  n'a été modifiée par cet audit.**
  **Dernier diagnostic DNS : `s3.int.albandrieu.com=present`
  chez les résolveurs publics ; après correction du parseur
  HAProxy (tabulations), le gate doit signaler explicitement
  `VIOLATION_NO_EXPLICIT_DENY` pour S3/Vault et non un faux
  `VIOLATION_NO_EXACT_ACL` pour Nexus.**
  Prochaines actions : supprimer la publication S3 via un changement
  DNS revu avec clients OpenTofu ; ajouter un refus Host S3
  sur le frontend WAN ;
  refus explicite Vault/alias privé ; preuves Cloudflare
  Tunnel+Access, DNS externe, PF/NAT et test WAN indépendant.
  Suivi détaillé :
  [runbook d'exposition](runbooks/pfsense-ingress-exposure-policy.md).
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

## Réception opérateur du 27 octobre — ressources/DefectDojo/Vaultwarden

- **Ressources TrueNAS : collecte réellement exécutée.**
  Instantané privé horodaté `2026-10-26T23:37:27Z` :
  **144 conteneurs RUNNING**, **92 mappés** à l'identité
  Backstage, **52 non mappés**, `inventory_complete=true`,
  **151 entités Component/Resource** ; GPU
  `unavailable` sur TrueNAS. Le JSON est stocké sous
  `/mnt/cpool/var/nabla/service-resources/resources-20261026T233659Z.json`
  et **n'a pas été transmis à l'agent**. N'affirmer aucune
  consommation CPU/RAM/ZFS individuelle sans lire ce rapport.
  Le prochain collecteur inclut `compose_project`,
  `compose_service` et `mapping_issue` pour réconcilier
  les 52 non-mappés. Le flag `shared_by_services`
  tient désormais compte des consommateurs non mappés.
- **DefectDojo initializer :** la capture des logs prouve
  l'accès PostgreSQL dès 21:04:30, une connexion test réussie,
  les triggers pghistory à 22:25, **aucune migration
  restante**, et `Admin user already exists; skipping first-boot
  setup`. Dernière ligne transmise :
  `Initializing non-standard permissions`. Aucun code
  de sortie fourni : la fin réussie ou le blocage réel
  **non vérifié**. Contrôler Docker status/OOM/exit et
  `diagnose-defectdojo-postgres-waits.py --check`
  sans réinitialiser la base.
- **Vaultwarden CLI :** `code` et `openrag` retournent
  `VAULT_ITEM_NOT_UNIQUE`, ambigu (manquant/doublon).
  Nouveau classificateur différencie absent, déplacé et
  dupliqué ; `defectdojo` : **5 MATCH**,
  `DD_ADMIN_USER=DRIFT`,
  `DD_ADMIN_PASSWORD=UNVERIFIED`.
  Le complément `unverified_reasons` dit quel côté
  manque/est vide, sans dévoiler la valeur.
  Garder le compte Django `admin` historique.
- **FastAPI/observabilité :** `update-fastapi-sample.sh`
  a confirmé les deux fichiers d'environnement identiques,
  checkout du commit `fa13c08db05ce8ce086d2366e1f35706913f05be`
  et **démarrage de l'étape 3/6 de build Docker** ;
  aucun succès de build/déploiement encore prouvé.
  Les diagnostics Prometheus/Akvorado ont été lancés, mais
  leurs résultats sont **non fournis / en cours**.
  Éviter de paralléliser d'autres builds/redeploys sous
  pression mémoire.
- **Changements :** scripts/read-only + tests ajoutés dans
  PR #285 avec `[skip ci]`, **aucune quality gate
  exécutée**. [Runbook](runbooks/2026-10-27-defectdojo-resources-vault-observability.md).

## P0 — Dernière demande : CPU/RAM/stockage RUNNING + DefectDojo DEPLOYING (27 octobre)

- **État réel : pas de collecte runtime complète effectuée par l'agent.**
  Le catalogue v2 contient **154 entités / 151 Component/Resource**
  et **141 mappings Compose**, pas des consommations attestées.
  Le collecteur `collect-service-resource-evidence.py` capture
  maintenant dans une seule mesure `docker stats` CPU
  (% d'un cœur, peut dépasser 100), RAM, GPU attribuable,
  taille de couche Docker et datasets ZFS ; `coverage` signale
  les conteneurs RUNNING mappés/non mappés et l'exhaustivité.
  Il publie un JSON privé et daté, **pas une mesure figée
  dans le catalogue Git**. Les cartes OWNER du site PR #262
  acceptent le CPU en plus de la RAM/GPU/stockage.
- **DefectDojo actuellement DEPLOYING : HTTP origine :31085
  et HTTPS privé tous deux indisponibles** (réception opérateur).
  Nouveau `diagnose-defectdojo-deploying.py --check` :
  app.query, état/OOM/exit des cinq conteneurs, priorité au
  `defectdojo-initializer` avant uWSGI ; classes de logs
  optionnelles et privées. Éviter le reset DB, les redéploiements
  répétés et la rotation admin avant diagnostic.
- **Vaultwarden :** `compare_vaultwarden_runtime_readonly.py
  --check --app <code|openrag|defectdojo>` contrôle présence
  et égalité des valeurs du cache CLI contre les secrets
  runtime, sans les afficher. Pas de sync/rotation ; vraie
  parité du serveur et résolution des `DRIFT` restantes à
  vérifier depuis le LAN.
- **Prometheus / Akvorado :** diagnostic readiness distinct de
  l'inventaire des scrapes et des deltas NetFlow ; la dernière
  preuve de rejets actifs `metadata missing` n'est pas
  résolue et les insertions SQL restent à confirmer.
- **État de validation :** modifications et contrats versionnés,
  **aucun test ni quality gate exécuté dans cette passe**.
  [Runbook du 27 octobre](runbooks/2026-10-27-defectdojo-resources-vault-observability.md).

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

## Suites P1 sans quality gate — changements du 26 octobre

- **Vaultwarden** : appels `bw` limités à 60 s ;
  aucune sortie `stderr`/secret incluse dans les erreurs
  Python ; `BW_SESSION` réservé aux appels authentifiés.
  Parité du coffre avec les secrets runtime encore à contrôler
  depuis une session opérateur déverrouillée.
- **Prometheus/Akvorado** : `diagnose-akvorado-flow.py` ne suit
  plus les redirections ni les proxies, n'appelle que les
  endpoints LAN explicitement déclarés et refuse les compteurs
  historiques négatifs. Le défaut actif `metadata missing`
  reste ouvert ; les lignes SQL récentes sont non vérifiées.
- **OpenClaw** : le diagnostic systemd tolère les mises à jour
  de Node 24 sous `mise` lorsque le binaire et le module
  OpenClaw correspondent à la **même version**.
- **YubiKey** : la comparaison des deux fichiers `.age`
  refuse les permissions groupe/autres et les parents
  symboliques avant ouverture. Aucune preuve de restauration.
- Tests de non-régression ajoutés aux quatre thèmes mais
  **pas exécutés**, conformément à la demande « pas de
  quality gate ». Aucun service ou secret runtime modifié.

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
- [ ] **H-05 / rapprochement avec master #286 :** le job
  `fastapi_sample` a un contrat Bearer + `credentials_file`,
  et le provisionneur TrueNAS `reconcile-fastapi-metrics-credential.py`
  a été accepté côté code. L'opérateur a observé
  `credential_ready=true` ; vérifier encore que FastAPI a chargé la
  clé, que Prometheus monte le secret et que
  `fastapi_sample: state=scrape_up targets_up=1` est confirmé.
  [Procédure](runbooks/fastapi-prometheus-scrape-secret-20261026.md).
- [ ] **H-05 / autres cibles :** classer chaque échec `DNS`, `TLS`,
  `HTTP`, `TCP` ou `auth` sans exposer de secret.
  `postgres_exporter:9187` refusé ne prouve pas
  `PostgreSQL:5432` indisponible.
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
