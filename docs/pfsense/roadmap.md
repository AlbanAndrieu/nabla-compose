# pfSense — roadmap

> Extraite de la [roadmap Compose](../roadmap.md) le 17/11/2026 pour préparer le dépôt `nabla-pfsense` ([périmètre](README.md)). Mêmes règles de suivi : `CODED`, `TESTED`, `ACCEPTED (runtime)`, `NOT_VERIFIED`. Ordre du portefeuille inchangé ([H07](../roadmap-portfolio.md)). Les changements pfSense passent par un script versionné (`check` puis `apply`) ou de l'IaC, jamais par la GUI.

## Sécurité : ce qui l'améliorerait vraiment (17/11)

Recommandations du diagnostic du 17/11 ([fiche](incidents/2026-11-17-pfsense-userland-freeze.md)). Le gain vient surtout de la configuration, pas de la marque du pare-feu. Chaque point passe par un script versionné (`check` puis `apply`) ou de l'IaC, avec une réception datée.

- [ ] **Matériel x86 avec SSD** : Netgate 4200 MAX décidé le 17/11 (NVMe, 4 Go, ports indépendants) ; voir « Gels userland » dans H07b. **Avant commande** : trancher entre A et B dans l'[étude de décommissionnement](decommission-study.md). En A, pas de 4200. Supprime aussi le pont LAN/WAN des démarrages à froid.
- [ ] **Segmentation en VLAN** : LAN, serveurs (TrueNAS, Talos), IoT/Home Assistant, invités (`NETGEAR75`) et administration, avec refus par défaut entre segments et ouvertures explicites. Réception : matrice de flux testée (un client invité ne joint ni TrueNAS ni la GUI pfSense). Prérequis : le 4200 et un point d'accès Wi-Fi capable de VLAN (à vérifier).
- [ ] **Administration par VPN seulement** : fermer SSH 9922 côté WAN et passer par WireGuard. La garde WAN de la GUI 10443 reste en place. Réception : scan externe (port fermé), accès VPN testé, sshguard toujours actif.
- [ ] **Clés FIDO2** : remplacer la clé logicielle `ssh-ed25519` d'`admin` et `albandrieu` par des clés `sk-ssh-ed25519@openssh.com` (YubiKey), avec une clé de secours hors ligne. Réception : connexion par clé matérielle, refus de l'ancienne clé.
- [ ] **Plus d'entrée directe** : retirer l'« Easy Rule » WAN et les redirections NAT (items de H07b), les entrées passant par Cloudflare Tunnel. Réception : scan externe où seuls les ports publics décidés (HAProxy :443/:7000) restent ouverts, puis revue de leur passage par le tunnel.
- [ ] **Garder les protections actuelles** : Snort/CrowdSec, pfBlockerNG en IP seule, syslog distant vers Loki. Réception : `check-drift.sh` convergé sur le 4200.
- [ ] **Migration** : restaurer la copie de `config.xml` du 17/11, appliquer `stop-default-pass-logging.php`, puis `check-drift.sh` (étape 4 de « Gels userland »).

## Écarts et stabilisation

### H07 — pfSense : écarts à contrôler (ouverts, non réceptionnés)

- **DNSBL et ASN reporting — CODED, réception NOT_VERIFIED** : `scripts/pfsense/diagnose-recover.sh --check-posture` appelle désormais l'audit de capacité en lecture seule pour mesurer les entrées DNSBL chargées et préparées et vérifier le paramètre ASN reporting, sans imprimer de jeton. Confirmer les mesures sur l'appliance ; un champ absent doit rester `NOT_VERIFIED`.
- **Snort arrêté après OOM ou kill — CODED, réception NOT_VERIFIED** : l'audit ajouté à `--check-posture` examine maintenant le processus WAN (`service.snort`), en plus de la configuration ; un processus absent ne devient plus implicitement sain. Confirmer le nom/config de l'instance installée, son âge et le résultat après rebuild, sans redémarrage automatique en cas de pression mémoire.
- **PHP-FPM — DONE 15/11 17:46** : profil `4/30/1/2/500` (validé le 24/10) appliqué sur `default_clone` (26.03), générateur identique à celui d'octobre, smoke tests DNS et GUI réussis. Il remplace le relevé historique de 7 workers nginx PHP-FPM (environ 280 Mio RSS cumulés). Seuil du check `php_fpm.nginx_workers` **CODED 16/11** : 0 worker au repos (mode ondemand, inactivité 30 s) est `PASS` si le master PHP-FPM tourne, `WARN` sinon ; test comportemental sur `ps` simulé. Réception : relancer `--check-posture` sur l'appliance (NOT_RUN).
- **Critère de réception** : taille DNSBL + ASN reporting prouvés, Snort actif ou explicitement classé en panne avec horodatage, et PHP-FPM **≤ 4 workers** avec paramètres `4/30/1/2/500`, sans nouveaux OOM ; vérifier Unbound, pfREST et accès WebConfigurator après réglage.

Sources : [incident pfSense du 13/11](incidents/2026-11-13-pfsense-unbound-oom-snort-crowdsec.md), [profil PHP-FPM](pfsense-php-fpm-hardening.md) et [plan d'upgrade pfSense](pfsense-upgrade-26-07.md). Ne pas confondre absence de mesure et service sain.

### H07b — pfSense : stabiliser `default_clone`, puis repasser en 26.07 (15/11)

Détail et preuves : [runbook 26.07](runbooks/pfsense-26.07-upgrade.md#stabilisation-du-1511-sur-default_clone).

- [x] **P1 GUI 10443 exposée à Internet** : garde WAN d'octobre restaurée (alias `PFSENSE_ADMIN_WAN`, pass, puis `Block untrusted pfSense GUI/API`, avant l'« Easy Rule »). Chargé dans PF le 15/11 à 18:14. Test depuis Internet NOT_RUN.
- [x] Unbound `All` et Domain Override `int` ; syslog `.57` retiré ; cibles workstation HAProxy/NAT retirées (revenues le 16/11, puis retirées à nouveau ; voir ci-dessous) ; règles `heimdall 443` et `ExternalOffice 7000` désactivées ; 9 réservations DHCP d'octobre restaurées (Talos `.50` à `.52`).
- [x] **Boots ratés de `default_clone` et du 26.07 d'octobre** : générateur PHP-FPM recopié en 600 par `harden-pfsense-php-fpm.sh` (`cp -p` d'un `mktemp`). Script corrigé, environnements réparés par `repair-be-php-generator-mode.sh` (37c39a3b). `default_clone_20261115_stable` est en service depuis le 15/11 19:48 (boot en 47 s), avec les baux DHCP restaurés par `restore-dhcp-staticmaps.php`. Diff complet contre la sauvegarde stabilisée de 18:19 : seuls les 9 baux DHCP diffèrent.
- [x] **Repli** : la cible est le BE le plus ancien non marqué `failed`, `default` (binaires de juin). Il porte la config en service depuis le 15/11 (`sync-fallback-be-config.sh`, révision 20:11) ; resynchroniser après chaque changement.
- [x] `check-drift.sh` étape 4 : diff complet de `config.xml` (`config-drift.py`, `PFSENSE_DRIFT_BASELINE`), qui couvre règles, NAT, alias, HAProxy, VPN, certificats, IPv6 et DNS.
- [x] **pfBlockerNG IP seul** réactivé le 15/11 à 20:36 sur le BE en service (`pfblocker-ip-only.php apply`, puis `updateip` 20:36 → 20:43). Le premier essai de 18:43 avait coupé tout l'IPv4 sortant : le groupe GeoIP Top Spammers contenait FR, et sa règle WAN flottante (`quick`, toutes directions) bloquait notre propre IP WAN. FR est retiré, `--check-posture` signale `pfblockerng_wan_self_block`. Pendant le chargement : WAN et DNS toujours OK, charge max 5,2, 37 Mo libres une fois, pas d'OOM. Le rechargement du filtre de 20:43 a pourtant échoué : pendant un rechargement, l'ancien et le nouveau jeu de tables coexistent, et les listes GeoIP IPv6 (190k entrées) dépassaient la limite pf de 400k. Top Spammers n'était donc pas chargé, et aucun rechargement ne passait. Depuis 21:12, les pays IPv6 sont retirés (le WAN n'a pas d'IPv6 publique) : 8 tables IPv4 (151 093 entrées), toutes chargées. Ni notre IP WAN ni les 15 plages Cloudflare ne sont bloquées. Le `check` signale toute table de `rules.debug` absente de pf. DNSBL reste coupé. Reste à observer : le cron quotidien `pfblockerng.php cron` de 00:00.
- [x] **pflow natif vers Akvorado** rétabli le 15/11 à 21:21 (`reconcile-pflow.php`) : NetFlow v5 domain 1, source LAN, vers `172.17.0.24:2055`, suivi sur toutes les règles. TrueNAS reçoit les paquets, et l'inlet Akvorado compte les flux de 172.17.0.1 sans erreur. `check-drift.sh` rejoue son check.
- [x] **REST API** : identités conformes (`--check-identities`), empreinte de la clé `posture` identique au hash stocké, `system/version` et `dns_resolver/settings` en 200 le 15/11 à 20:0x.
- [ ] **« Easy Rule » WAN** (`pass tcp all`, depuis 2022, présente aussi en octobre) : inventorier ce qui en dépend (HAProxy :443/:7000, NAT), puis la remplacer par des règles par port. SSH 9922 est ouvert sur le WAN (clé seule) ; la règle « Reject SSH » ne bloque que la source WAN.
- [ ] **Exposition WAN par NAT** (vault 8200, nomad 4646, consul 8500, traefik 9002, apps TrueNAS 300xx) : revue avec H04.
- [ ] **HAProxy : backend par défaut vers le honeypot, puis Heimdall refusé** (décision du 16/11). Le honeypot Project Honey Pot quitte l'Apache de la workstation pour l'App TrueNAS `honeypot` ([`apps/honeypot`](../../apps/honeypot/compose.yml), `172.17.0.24:31090`, CODED, NOT_DEPLOYED). Seuls `/` et `/honeypot/keywaspish.php` exécutent le script, et chaque exécution signale le visiteur à Project Honey Pot ; `/healthz` est statique.
  1. Déployer l'App (`reconcile-custom-apps.py --apply`), puis vérifier `/healthz` = `ok` et le rendu de `/` depuis le LAN.
  2. **CODED 16/11, décision confirmée par l'opérateur** : [`haproxy-honeypot-default.php`](../../scripts/pfsense/haproxy-honeypot-default.php) (`check` puis `apply`) crée le pool `honeypot` (`GET /healthz`, jamais `/`, champs clonés de `prod_back`), le met en backend par défaut de `Web_HTTPS`, `freenas` et `Web_HTTPS-8082` (dont le défaut `nabla-index` est vide) et active `forwardfor` sur ces trois frontends (Apache ne lit `X-Forwarded-For` que depuis `172.17.0.1` ; `freenas` ne l'avait pas). Noms des frontends et des champs relevés en lecture seule sur l'appliance le 16/11. Effet attendu : `apache`, `account` et tout hôte non routé servent le honeypot au lieu du login Heimdall. `check`/`apply` NOT_RUN : l'App doit d'abord tourner (étape 1).
  3. Une fois la bascule vérifiée, refuser Heimdall depuis le WAN : supprimer les règles `use_backend prod_back` (`manager`, `domain_api`, `alert_api`) et abandonner `prod-back-homarr-fallback.php`, jamais appliqué.
  4. `--check-posture` : `haproxy_default_backend=honeypot` **CODED 16/11** (`manage-posture.php`, WARN avec les frontends restants). Reste `haproxy_heimdall_routes=none`, à coder avec l'étape 3.
  5. L'ingress `honeypot-albandrieu` du tunnel workstation a été retiré sur `master` le 16/11 : conserver son retrait et surveiller le volume de signalements après la bascule du backend HAProxy. Si nécessaire, limiter le débit par IP.
- [x] **Service Watchdog** : `audit-posture.sh` est aligné sur la décision du 13/11 (238e1073). Certificats ACME renouvelés jusqu'au 11/02/2027, et `--check-posture` alerte à moins de 14 jours (3d7c663b).
- [ ] **Gels userland : l'eMMC du 1100 lâche** ([fiche du 17/11](incidents/2026-11-17-pfsense-userland-freeze.md)). L'enregistreur SSH (`freeze-capture.sh`) a capté `mmcsd0: Error indicated: 1 Timeout`, puis la suspension du pool ZFS `pfSense` (`uncorrectable I/O failure`), juste après une rafale d'écritures (redémarrage de CrowdSec et du `filterlog` de pfBlockerNG au retour du WAN). Cause établie. Copie de secours de `config.xml` faite le 17/11 à 19:47 (révision du 16/11 20:29). Historique : gels les 15/11 23:23 (26.07), 16/11 20:39, 17/11 07:48, ~13:40, 15:52:54 et 18:04:55 (stable 26.03), puis après chaque boot du soir. Le GUI, SSH, la REST API, l'agent Zabbix et le syslog distant sont bloqués, puis Kea à son tour. Le routage et Unbound continuent de marcher.

  **Décision opérateur (17/11) : remplacer le 1100 par un Netgate 4200 MAX** (Atom C1110, 4 Go, NVMe 128 Go, 4 ports 2,5 Gb indépendants, pfSense Plus inclus). Écartés : 2100 (même plateforme ARM et switch Marvell), versions BASE (eMMC), mini-PC N150 (Plus par abonnement non confirmé ; une config Plus 26.03 ne se restaure pas sûrement sur CE), OPNsense (13 scripts sur l'API PHP de pfSense à réécrire). Ports indépendants : le pont LAN/WAN du démarrage à froid disparaît avec le switch. Étapes :
  1. ~~capture pendant un gel~~ : faite le 17/11 (fiche) ;
  2. en attendant le boîtier, alléger les écritures (décision opérateur du 17/11 ; **DEPLOYED le 17/11 entre 21:00 et 21:06**, boot WAN débranché : les trois `check` sont convergés et le BE de repli `default` est resynchronisé. Le premier `apply` RRD avait écrit la config, puis échoué sur `read_altq_config()` ; corrigé, puis relancé). [`boot-window-apply.sh`](../../scripts/pfsense/boot-window-apply.sh), lancé dans le terminal de l'opérateur pendant un boot WAN débranché, enchaîne `apply` puis `check` de :
     - [`hold-packages-at-boot.php`](../../scripts/pfsense/hold-packages-at-boot.php) : pfBlockerNG et le bouncer CrowdSec ne démarrent plus au boot ni au retour du WAN (leur redémarrage accompagnait la rafale du 17/11). `start` les relance à la main et persiste jusqu'au prochain `apply`. **Risque accepté** : tant qu'ils sont arrêtés, les blocages pfBlockerNG et les décisions CrowdSec ne s'appliquent plus ; sshguard et la garde WAN de la GUI restent ;
     - [`stop-default-pass-logging.php`](../../scripts/pfsense/stop-default-pass-logging.php) : 92 % des lignes `filterlog`, branché sur l'étape 6 de `check-drift.sh` ;
     - [`disable-rrd-graphing.php`](../../scripts/pfsense/disable-rrd-graphing.php) : collecteur RRD réécrit chaque minute ; graphes déjà dans Prometheus et Zabbix ; `revert` sur le 4200 si voulu.

     Écartés : couper les logs locaux (pfSense ne démarre alors plus sshguard, qui protège le SSH exposé) et les RAM disks (~290 Mo libres le 17/11). Resynchroniser ensuite le BE de repli (`sync-fallback-be-config.sh`) ;
  3. ~~lire l'usure de l'eMMC~~ : faite le 17/11 avec [`emmc-health.sh`](../../scripts/pfsense/emmc-health.sh) : durée de vie consommée à 100-110 % (`0x0b`), opérations de fond critiques (`BKOPS_STATUS` `0x03`), réserve encore normale. Confirme le remplacement ;
  4. sur le 4200 : restaurer la copie de `config.xml`, réassigner les interfaces (`mvneta0.4090`/`.4091` → `igcN`), appliquer `stop-default-pass-logging.php`, puis `check-drift.sh`. Les contrôles Snort de `audit-posture.sh` et `diagnose-recover.sh` lisent déjà le WAN dans `config.xml` (CODED, testés). Retirer ensuite la ligne `fallback_exclusion` de `check-drift.sh` et mettre à jour les docs qui citent `mvneta0.4090`.
- [ ] **Démarrage à froid du 1100 : LAN et WAN reliés** ([fiche](incidents/2026-11-14-netgate-1100-cold-boot-switch-bridge.md)). Le U-Boot `18.12.3` n'a ni `preboot` ni `switch_disable` (vérifié le 16/11 sans console), et `u-boot-update.sh` ne les ajoute pas, car le U-Boot est déjà « latest ». Le 14/11, `taloscp01` a ainsi reçu l'IP publique de la Freebox. Suricata (TrueNAS, `br0`) a vu la Freebox (`82.66.4.254`) attribuer l'IP publique à trois MAC locales `02:00:00:00:xx:xx` de VM sur `br0`, le 13/11 à 20:42 et le 14/11 à 18:16, et plus depuis, boots du 17/11 compris. Le 17/11, le journal DHCP du Mac montre cinq offres de l'IP publique (13:34 → 18:00), toutes refusées parce qu'un **pont Philips Hue** (`.68`), puis la **TV Samsung** `tizen` (`.81`) la tenaient déjà : objets connectés exposés sans pare-feu pendant le pont ([fiche du 17/11](incidents/2026-11-17-pfsense-userland-freeze.md)). Couper puis rétablir leur réseau une fois pfSense stable. Le WAN de pfSense est en IP fixe, donc n'importe quel client DHCP du LAN peut prendre le bail pendant le pont. Disparaît avec le 4200. En attendant : `reboot` uniquement, jamais de coupure de courant. Correctif (`u-boot-update.sh -f` ou script d'environnement seul) `NOT_RUN`, reporté par l'opérateur, console série requise.
- [x] **Cibles workstation revenues dans HAProxy** (16/11) : le retour au BE stable du 16/11 à 00:05 avait remis la config d'avant le retrait du 15/11, avec 5 serveurs actifs vers `172.17.0.57` (`albandrieu-apache`, `nabla-index`, `prod_front` sur :8082 ; `nexus` sur :8081, où rien n'écoute ; `vault` sur :8200, qui est en fait minidlna). Depuis 19:31, Apache n'écoute plus que sur `127.0.0.1:8082` (ansible-workstation `ed7938d`, tunnel Cloudflare `famp-albandrieu` seul), d'où 3 backends DOWN. **DEPLOYED** le 16/11 à 20:17-20:18, à la demande de l'opérateur : `retire-workstation-targets.php apply` (5 serveurs inactifs), puis `prune-dead-haproxy-routes.php apply` (13 règles `use_backend`, 24 ACL). Les deux `check` sont convergés, plus aucune référence à `.57` dans `haproxy.cfg`, aucun backend DOWN ; BE de repli resynchronisé (révision 20:18).
  - [ ] DNS : `account.albandrieu.com` et `apache.albandrieu.com` (A vers le WAN, sans proxy) tombent maintenant sur le backend par défaut `prod_back`, comme tout nom inconnu. Supprimer ces enregistrements ou les publier par le tunnel workstation.
- [x] **Restes HAProxy retirés** le 16/11 vers 20:28, à la demande de l'opérateur : `retire-haproxy-leftovers.php apply`, puis `prune-dead-haproxy-routes.php apply`. Pools supprimés : `nexus`, `vault`, `albandrieu-apache` et `clamav-openvas` (avec ses deux règles `use_backend` et l'ACL `clamav`/`openvas`/`suricata`) ; serveurs `lamp` et `famp` retirés de `prod_front` ; frontend public `Web_HTTPS-8082` désactivé. HAProxy n'écoute plus que sur `82.66.4.247:443` et `:7000`, avec 3 backends UP (`prod_back`, `homeassistant`, `freenas`). Les `check` sont convergés et le BE de repli resynchronisé (révision 20:29).
  - [ ] Reste la redirection `login` de `Web_HTTPS` vers `http://albandrieu.albandrieu.com:8082/honeypot/keywaspish.php`, morte (pas de DNS, :8082 fermé) : à remplacer lors de la bascule du backend par défaut vers l'App `honeypot` (voir plus bas).
- [x] **13 CA expirées** (ExpressVPN, importées en 2022, expirées le 01/04/2026, sans clé ni référence, aucun client OpenVPN) : notification nocturne « CA/Certificate entries are expiring ». `remove-unused-cas.php` (`check`/`apply`, test hors ligne) **DEPLOYED** le 16/11 à 20:08 : 25 → 12 CA, `check` convergé, BE de repli `default` resynchronisé (révision 20:08). La notification déjà affichée se ferme dans la GUI. Puis, à la demande de l'opérateur, le script (renommé `remove-unused-cas.php`) retire aussi les émetteurs ACME (`Acmecert:`) inutilisés, que le paquet ACME réimporte au besoin : 7 CA Let's Encrypt R10 à R13 et staging, le 16/11 à 20:28 (12 → 5). Restent YR1, YR2, Root YR et leurs équivalents staging, encore utilisés.
- [ ] **Upgrade 26.07** : boot unique testé le 15/11 à 21:51, après recopie de la config en service dans `default_20260824183037`. `26.07-RELEASE` démarre en 4,5 min et passe la vérification de boot (drapeau `failed` levé). WAN, DNS, HAProxy, Kea et pflow fonctionnent. Deux bloquants avant de le garder :
  1. Deux chargements du jeu de règles au boot ont échoué (21:56 et 21:57, `Cannot allocate memory` sur `bogonsv6`). L'état final n'a pas été établi. Le BE 26.07 a la vraie liste `bogonsv6` (158k entrées), alors que le stable a encore le fichier vide de mars : avec pfBlockerNG, un rechargement dépasse la limite de 400k. Le stable la dépassera aussi à son prochain rafraîchissement des bogons. `pfblocker-ip-only.php` monte la limite à 1M, appliqué sur le stable le 16/11 vers 00:37.
  2. Vers 23:00, l'interface web et SSH ont cessé de répondre (TCP accepté, ni TLS ni bannière), alors que le routage et le DNS marchaient. Retour au BE stable par cycle d'alimentation le 16/11 à 00:05. Cause inconnue sans console : Snort tournait sur 2 interfaces depuis 21:58, piste non vérifiée. Le BE stable 26.03 a fait trois gels de même signature le 17/11 : ce point n'est donc pas propre au 26.07 (voir la ligne « Gels userland » ci-dessous).

  Le boot réussi avait levé son drapeau `failed`, donc il était devenu la cible du repli du stable. Il en est de nouveau exclu depuis le 16/11 (`exclude-be-from-fallback.sh`, vérifié par `check-drift.sh`). Le repli est `default`, resynchronisé à la révision 00:36. Prochain essai seulement avec le câble console. Les cibles workstation sont déjà retirées dans sa config.
  - [ ] **Retester le 26.07 et son upgrade cette semaine (au plus tard le 22/11)**, console série branchée et master SSH ouvert (`sshp`) :
    1. recopier la config en service dans le BE 26.07 (`sync-fallback-be-config.sh`), puis vérifier `maximumtableentries` à 1M ;
    2. boot unique (`bectl activate -t`), puis `pfblocker-ip-only.php check` (aucun `pf_tables_not_loaded`) et 2 h d'observation (mémoire, Snort, interface, SSH) ;
    3. si le boot tient, tester l'upgrade depuis le stable 26.03 (`prepare-upgrade.sh`, puis `pfSense-upgrade` dans un nouveau BE), avec le même contrôle ;
    4. une fois le 26.07 en service, retirer la ligne `fallback_exclusion` de `check-drift.sh`. Sinon, remettre le stable et noter la cause vue sur la console.
- [x] **Clé USB de réinstallation** : l'image du ticket TAC *Firmware Access* est l'installeur en ligne déjà sur la clé ; pas d'image hors ligne pour le 1100. La réinstallation passe par le WAN branché sur la Freebox (procédure dans le runbook).

## Décommissionnement de pfSense (étude du 17/11)

[Étude](decommission-study.md) : rôles relevés sur pfSense, ce que la Freebox Ultra peut reprendre, scénarios A (décommissionner), B (Freebox en routeur avec pfSense derrière) et C (statu quo). Chaque étape est réversible, et pfSense reste en place jusqu'à la phase 2.

**Phase 0, utile dans les trois scénarios** (Freebox en bridge, pfSense inchangé) :

- [x] **0.1 Inventaire versionné**, fait le 17/11 : [`inventory.php`](../../scripts/pfsense/inventory.php) exporte en lecture seule les interfaces, les baux fixes (sans MAC), les redirections et l'état de leur règle de passage, les alias (nombre d'entrées et usages, jamais leur contenu), HAProxy, ACME, DNS et VPN. Deux exécutions identiques ; la sortie reste dans `logs/`.
- [ ] **0.2 Supprimer les 13 redirections WAN obsolètes**, par script versionné. Constat de l'inventaire : 10 règles de passage désactivées, 3 orphelines, 0 état établi ; cibles mortes (Vault, Nomad et Consul vers `127.17.0.55`, ancien FreeNAS) ou non exposées. Supprimer aussi les 9 alias inutilisés. Toute ouverture future passe par Cloudflare Access/Tunnel ou Tailscale. Réception : 0 redirection, sondes extérieures inchangées.
- [ ] **0.3 Ingress hors de pfSense** : les 2 frontends HAProxy actifs (`Web_HTTPS` 443 et `freenas` 7000) vont vers le tunnel Cloudflare et Traefik sur TrueNAS, avec les certificats en DNS-01 ; les 5 désactivés sont supprimés. Réception : plus rien n'écoute sur le WAN de pfSense.
- [ ] **0.4 DNS par Pi-hole** : le DHCP de pfSense distribue Pi-hole (`172.17.0.24`) en principal et un secondaire hors TrueNAS ; DNSSEC activé dans Pi-hole. TrueNAS garde un résolveur qui n'est pas Pi-hole. Réception : `int.albandrieu.com` et les noms publics résolus par Pi-hole ; Pi-hole arrêté, les noms publics résolus quand même.
- [ ] **0.5 Services annexes** : DynDNS vers ddns-updater ; WireGuard vers Tailscale ou le WireGuard de la Freebox ; bouncer CrowdSec dans Traefik.
- [ ] **0.6 App Freebox au moindre privilège** : décocher les droits par défaut (Explorateur, VM, Appels, Contacts, Téléchargements, TV, PVR). « Modification des réglages » seulement pour la bascule.

**Phase 1, décision de l'opérateur** :

- [ ] A ou B, et donc commande du 4200 ou non. Critères : accepter ou non un réseau à plat (IoT, Wi-Fi, Talos et TrueNAS sur le même `/24`), sans IDS ni journal pare-feu.

**Phase 2, bascule de la Freebox en routeur** :

- [ ] **B** : [procédure Freebox](runbooks/freebox-router-mode.md), WAN de pfSense en DHCP puis épinglé, avec la DMZ.
- [ ] **A** :
  - en routeur, tester si la Freebox accepte `172.17.0.1/24` comme adresse LAN, ce qui évite de renuméroter ;
  - régler la plage `.100`–`.200` et le DNS Pi-hole ;
  - créer les 39 baux fixes avec un script `plan`/`apply` (Kea vers l'API Freebox) ;
  - fusionner les 7 hôtes du VLAN OPT dans le LAN ;
  - recâbler le switch du LAN sur la Freebox.

  Retour arrière : recâbler pfSense et repasser la Freebox en bridge.

**Phase 3, décommissionnement (A seulement)** :

- [ ] export chiffré de `config.xml` ;
- [ ] révoquer le nœud Tailscale, le pair WireGuard, les comptes ACME et les clés RESTAPI ;
- [ ] retirer les cibles Prometheus, Gatus, Loki et Zabbix, ainsi que la source Akvorado ;
- [ ] archiver `scripts/pfsense` et `docs/pfsense` (dépôt `nabla-pfsense` en archive) ;
- [ ] effacer l'eMMC du 1100 avant de s'en séparer.

## Autres suivis pfSense

- [ ] **Freebox en mode routeur** ([procédure](runbooks/freebox-router-mode.md)), `CODED` le 17/11, `NOT_RUN`. Le WAN de pfSense passe en DHCP, la Freebox en routeur par son API, puis le WAN est épinglé avec la DMZ. Gains : fin de l'IP publique distribuée pendant les démarrages à froid du 1100, et secours Wi-Fi possible. Préparation faite le 17/11 (voir la procédure) : app enregistrée, inventaire, DynDNS prêt, alias et redirections sans impact. Reste le jour J : permission `settings`, MAC du WAN, adresse du WAN. Réception : `check` des deux outils à 0 changement, entrées 443 et 7000 vues de l'extérieur, DynDNS à jour.
- [ ] **IPv6 sur le LAN** : la Freebox route déjà 2 préfixes `/64` vers le WAN de pfSense, mais le LAN est en `track6` (il attend du DHCPv6-PD) et n'a aucun préfixe. Passer le LAN en IPv6 statique sur l'une des délégations, avec RA, par script versionné. Indépendant de la bascule.
- [ ] **Clé USB du 1100** : relue le 17/11. C'est la clé d'installation de pfSense (SanDisk Cruzer 16 Go en USB 2.0, 21,6 Mo/s en lecture contre 27,4 Mo/s pour l'eMMC). On la garde comme clé de réinstallation, pas comme stockage : voir « Gels userland » de H07b.

- pfSense / CrowdSec : conserver la preuve que PF charge les règles, puis démontrer le rattachement WAN exact sans bloquer une IP d'administration ; ne pas prendre une ancre chargée pour une preuve de filtrage effectif.
- **Sonde Cloud** : le WAN `*.int` renvoie 503 depuis Cloud, à diagnostiquer par script versionné (relevé de la réception du catalogue, PR #326).
- [ ] Un onglet du tableau de bord pfSense resté ouvert dans Chrome était le seul client de :10443 de la nuit et gardait PHP-FPM à 2-3 % de CPU : le fermer, ou espacer le rafraîchissement.

## Incident réseau P0 — IPv4 Freebox bridge et IPv6 pfSense (15/11/2026)

**Ouvert (NOT_VERIFIED en runtime).** Free confirme la fibre et
`82.66.4.247` ; la gateway IPv4 `82.66.4.254` est déclarée
mais ICMP échoue et le test TCP renvoie `Permission denied`.
L'opérateur a coché **Disable Gateway Monitoring** sur le WAN :
cela désactive `dpinger`, sans prouver le retour Internet.

- **P0 IPv4 :** diagnostiquer les règles PF et les refus locaux,
  capturer les paquets sortants/entrants sur `mvneta0.4090`,
  puis vérifier le chemin Freebox/Free et le SNAT LAN seulement
  après test direct sur pfSense. **DONE :** HTTPS IPv4 depuis
  pfSense et un client LAN, preuves horodatées.
- **P1 IPv6 :** obtenir une connectivité IPv6 complète sur pfSense
  et le LAN. Free communique `2a01:e0a:a17:3c00::/64`,
  route IPv6 par défaut via `fe80::8e97:eaff:fe39:b37b`.
  Vérifier la route et le next hop Freebox, la disponibilité du /64
  LAN, RA/SLAAC Assisted, Android, les règles IPv6 et
  Unbound (Outgoing Network Interfaces = All).
  **DONE :** IPv6 globale sur client LAN, accès par IP littérale,
  DNS AAAA et aucune exposition WAN imprévue.
- **Après rétablissement :** envisager `Disable Gateway Monitoring
  Action` afin de conserver la surveillance sans actions automatiques
  inutiles sur un WAN unique.

[Runbook de diagnostic pfSense](pfsense-diagnose-recover.md).
Ce P0 incident ne modifie pas l'ordre du portefeuille H01–H19.

## Historique P0 du 15/11 : récupération IPv4, DNS et split-DNS

**Actualisation du 15/11 — progrès IPv4 partiel :** les connexions
TCP `1.1.1.1:443` et `9.9.9.9:443` ont réussi lors des diagnostics
pfSense. **`PF_IPv4_TCP_EGRESS_PASS`**, mais LAN/NAT, DNS/Unbound,
IPv6 et identification de la cause initiale **non vérifiés**. Maintenir
le P0 ouvert jusqu'à test HTTPS IPv4 depuis le LAN et réactivation
contrôlée des protections arrêtées. Ne pas présenter la désactivation
de `Gateway Monitoring` comme la cause démontrée de la reprise.

**Nouvelle observation (15/11) :** CrowdSec, Snort et pfBlockerNG
ont tous les trois été arrêtés avant les deux succès TCP depuis
pfSense. Impossible d'identifier la protection responsable.
La workstation indique toujours « pas d'Internet »,
`ping cloudflare.com` échoue et le GUI pfSense est très lent.
La priorité P0 reste **LAN IPv4/DNS et charge pfSense**
avant IPv6 et avant réactivation progressive des IPS.
[Recette détaillée](pfsense-diagnose-recover.md).

**Évidence supplémentaire (15/11, workstation) :** passerelle
`172.17.0.1` routée et joignable (ping 3/3, SSH OK), pfSense
load < 1, mais `dig @172.17.0.1` timeout. Priorité P0 :
diagnostiquer l'écoute/état/ACL Unbound (UDP et TCP 53), puis
l'accès direct IPv4 depuis la workstation et le NAT LAN.
L'identification du bloqueur initial et IPv6 demeurent ouvertes.
[Commandes et observations](pfsense-diagnose-recover.md).

**P0 récupération pfSense (15/11) — CODED, runtime NOT_VERIFIED :**
le nouvel outil `scripts/pfsense/recover-access.sh`, accessible via
`just pfsense-check`, `pfsense-dns`, `pfsense-ui` et `pfsense-recover`,
permet la reprise manuelle ciblée en SSH direct sans GUI, pfREST,
WAN DNS ni changement de firewall. Le diagnostic compare la résolution
LAN UDP/TCP, Unbound loopback/LAN, DNS public, sockets, erreurs/OOM.
**DONE** : résolution DNS et NAT IPv4 fonctionnels depuis la workstation,
GUI rétablie, puis protections restaurées une par une sans régression.
[Runbook](pfsense-diagnose-recover.md).

**Evidence DNS du 15/11 :** `dig @9.9.9.9` réussit depuis la
workstation, alors que `dig @172.17.0.1` expire et
`drill @127.0.0.1` sur pfSense indique `could not send or receive`.
Deux PID `unbound` observés, sans preuve de service DNS effectif.
Prioriser l'identification des sockets :53, du binding localhost/LAN,
de la configuration générée et des logs Unbound, avant modification
du NAT ou de la passerelle.

**P0 split-DNS après reboot (15/11) — CODED, runtime NOT_VERIFIED** :
résolution publique à nouveau fonctionnelle, mais
`int.albandrieu.com` non délégué à Pi-hole par Unbound :
`list_forwards` vide, `Domain Overrides` vide, réponse Cloudflare
sans A alors que Pi-hole renvoie `172.17.0.24`.
`reconcile-split-dns.sh --check/--apply` corrige l'override
et `outgoing_interface=all` de façon ciblée ; `check-drift.sh`
agrège les contrôles de posture. **DONE** : même A privé via
Pi-hole et Unbound, récursion publique OK, pas de reboot involontaire,
inventaire des dérives Boot Environment/Snort/pfBlockerNG/CrowdSec.
[Architecture DNS](../dns-ingress-ownership.md).

**P0 observabilité Unbound — 15/11** : enrichir
`diagnose-unbound-restart-cause.sh` et le renderer partagé
`console.sh` avec triage coloré P0/P1, statut actuel Unbound,
détection du forwarder DNS privé, alertes ASN/IPinfo et DNSBL,
et distinction entre les anciens marqueurs stop/start et une
cause démontrée. Préserver la sortie brute CI et la neutralité
`ROOT_CAUSE_NOT_PROVEN`.
[Runbook de récupération](pfsense-diagnose-recover.md).
