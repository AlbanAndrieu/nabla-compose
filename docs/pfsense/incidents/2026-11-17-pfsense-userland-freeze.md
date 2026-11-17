# pfSense : l'eMMC du Netgate 1100 tombe en timeout et ZFS suspend le pool (GUI, SSH, syslog puis DHCP figés)

**Statut** : ouvert. **Cause établie** par la capture SSH du 17/11, entre 18:56 et 18:59 environ (heure réelle) : timeouts de l'eMMC `mmcsd0`, puis pool ZFS `pfSense` suspendu (`uncorrectable I/O failure`). Le matériel est probablement en fin de vie ; son remplacement reste à décider. Aucune modification de pfSense pendant le diagnostic.

## Cause

Dernier tour de la capture, au moment du gel :

```text
mmcsd0: Error indicated: 1 Timeout          (x4, après un vidage des registres sdhci_xenon1-slot0)
Solaris: WARNING: Pool 'pfSense' has encountered an uncorrectable I/O failure and has been suspended.
iostat mmcsd0 : 11 lectures/s à 618 ms, 0 écriture, occupation 144 %
```

Une fois le pool suspendu, tout processus qui lit ou écrit sur le disque reste bloqué en état `D` (`zio->io_`). La capture le montre pour `grep` (recherche GeoIP de pfBlockerNG), `acbupload.php` et `filterlog`. Ce qui vit en mémoire continue : le routage, Unbound, et Kea jusqu'à sa prochaine écriture de bail. Cela explique toute la signature observée :

- syslogd ne peut plus écrire `/var/log`, donc le flux distant s'arrête net ;
- sshd ne lance plus `sshd-session`, nginx et PHP ne servent plus de page ;
- Kea tombe plus tard, à sa première écriture de bail ;
- Unbound n'écrit rien et continue de répondre.

Aucune erreur eMMC n'a jamais atteint Loki, puisque syslogd est bloqué dès la suspension. Pour Netgate, ce message signale une défaillance du contrôleur ou de la puce eMMC, et non un bug logiciel ([forum Netgate](https://forum.netgate.com/post/1172391), [Redmine #14300](https://redmine.pfsense.org/issues/14300), [Redmine #14181](https://redmine.pfsense.org/issues/14181)). L'eMMC date de mars 2018. L'avertissement `DTB version is 6.4 while kernel expects 6.12` apparaît à chaque boot depuis le 13/11, avant les gels : il ne les explique pas.

**Déclencheur** : les rafales d'écriture.

- Sur la capture, la panne suit de 17 s une rafale de 299 écritures/s (3,9 Mo/s, file de 8, occupation 94 %). Cette rafale arrive environ 40 s après le redémarrage de haproxy, Snort, crowdsec et vnstatd, déclenché par le retour du WAN.
- Les boots, les rechargements de pfBlockerNG et le flot de `filterlog` produisent le même type de rafales.
- Depuis le 17/11, l'eMMC lâche dans les minutes qui suivent chaque boot : la dégradation s'accélère.

Date : 2026-11-17 (Netgate 1100, pfSense Plus, BE `default_clone_20261115_stable`, 26.03).
Point d'observation : workstation `172.17.0.57` (filaire, LAN), avec `AGENT_EXECUTION_MODE=workstation`. Les sondes sont en lecture seule et bornées dans le temps, de 15:55 à 17:30. TrueNAS a été lu par son master SSH, en lecture seule.
Preuves :

- Loki `{job="pfsense"}` : syslog distant de pfSense, 7 jours ;
- Prometheus (`pfsense_exporter`, pas de 5 min) ;
- sondes TCP, TLS, HTTP, SSH, DNS, DHCP et Zabbix depuis le LAN ;
- sauvegarde `config.xml` du 15/11 18:19 ;
- recherche web sur les bugs connus.

## Résumé

- **Cinq gels en 42 h**, sur deux BE :
  - 15/11 23:23 sur le 26.07 ;
  - 16/11 20:39, 17/11 07:48, ~13:40 et 15:52:54 sur le stable 26.03.

  Le cinquième a duré jusqu'au reboot de l'opérateur, à 18:03 ; un sixième survient dès 18:04:55. Les 7 jours de Loki ne montrent aucun gel avant le 15/11 à 23:23. Le gel n'est donc pas propre au 26.07.
- **Signature** :
  - le noyau route, filtre et accepte les connexions TCP ;
  - les démons qui doivent répondre restent muets : nginx (ni HTTP, puis plus de TLS), sshd (pas de bannière), l'agent Zabbix (aucune réponse), la REST API ;
  - le flux syslog distant s'arrête net, `filterlog` compris.
- **Le gel s'étend** : Kea a servi un échange DHCP complet à 15:58, mais ne répond plus à 17:23. Unbound répond toujours, récursion comprise.
- **Facteur aggravant mesuré** : depuis le 13/11 vers 21:00 (config de mai de `default_clone`), `filterlog` produit 630 à 3 400 lignes par minute, contre environ 30 avant. Ces lignes passent toutes par syslogd, par le pipe vers pfBlockerNG et sur l'eMMC : les RAM disks sont désactivés, et syslogd est rechargé chaque minute par `newsyslog`.
- Aucun précurseur côté ressources : mémoire 36 à 53 %, disque 46 %, swap 0, CPU normal. Aucune erreur noyau transmise. Pas de crash dump possible (`No suitable dump device`).

## Les gels

| Dernier log | BE | Activité juste avant | Reprise |
| --- | --- | --- | --- |
| 15/11 23:22:18 | 26.07 (boot unique) | tableau de bord GUI ouvert depuis un mobile (`172.17.0.14`) | cycle d'alimentation, 16/11 00:05:30 |
| 16/11 20:38:18 | stable 26.03 | tableau de bord GUI depuis la workstation ; FastAPI Sample lit `diagnostics/table?id=snort2c` ; changements HAProxy à 20:28 | boot 22:42:54 |
| 17/11 07:48:32 | stable 26.03 | rien de notable : tâches cron de la minute, REST API de l'exporter à 07:44 | boot 13:38:03 |
| 17/11 ~13:40 | stable 26.03 | 90 s après le boot ; démon `filterlog` de pfBlockerNG relancé à 13:39:15 ; connexion root sur `ttyu0` à 13:39:18 | boot 15:52:07 |
| 17/11 15:52:54 | stable 26.03 | 47 s après le boot ; démon `filterlog` de pfBlockerNG relancé à 15:52:42 ; Snort en démarrage | reboot par l'opérateur, boot 18:03:27 (gel d'environ 2 h 10) |
| 17/11 18:04:55 | stable 26.03 | 88 s après le boot ; `Bootup complete` à 18:04:40 ; démon `filterlog` de pfBlockerNG relancé à 18:04:41 ; connexion root sur `ttyu0` à 18:04:46 | en cours à 18:10 |

Les trois derniers boots gèlent tous en moins de 2 min, entre 12 et 45 s après le message « filterlog daemon started » de pfBlockerNG. Les boots précédents relançaient ce démon sans geler aussitôt.

**Version** : tous les boots du 13 au 17/11 démarrent 26.03-RELEASE (`plus-RELENG_26_03`). Seule exception : le boot unique du 15/11 à 21:56 sur `default_20260824183037`, en 26.07-RELEASE. La valeur 26.07 lue dans `check-drift.sh` est la version **visée** (`PFSENSE_DESIRED_VERSION`, 26.07 par défaut) ; elle produit un `DRIFT` de version attendu tant que l'upgrade n'est pas fait.

Les autres silences de Loki sur 7 jours s'expliquent :

- le 12/11, de 20:35 à 21:47, le problème venait du récepteur : `sendto: Connection refused`, pas de boot, et les logs Kea reprennent seuls ;
- le 13 et le 15/11, les silences correspondent à des boots et à des BE en échec, déjà documentés.

Le déclencheur des boots n'est pas journalisé, car un pfSense figé n'envoie plus rien. On ne sait donc pas s'il s'agissait d'un redémarrage à chaud ou d'une coupure de courant.

## Ce qui répond pendant le gel

| Couche | 15:55 → 16:00 | 17:15 → 17:30 | Preuve |
| --- | --- | --- | --- |
| L2/L3, routage, NAT | OK | OK | ping 0,3 ms (aussi depuis TrueNAS), ARP `REACHABLE`, Internet joignable |
| DNS (Unbound) | OK | OK | récursion d'un nom aléatoire : NXDOMAIN en 784 ms ; TCP 53 OK |
| DHCP (Kea) | OK | **muet** | 15:58 : offre de `.100`, puis `ACK` immédiat sur un échange complet. 17:23 et 17:24 : aucune offre (`nmap broadcast-dhcp-discover`, 8 s puis 12 s) |
| GUI `:10443` | bloqué | bloqué | TCP ouvert ; un seul TLS réussi, puis aucune réponse HTTP. Plus aucun TLS en 8 s ensuite |
| SSH `:9922` | bloqué | bloqué | `Connection timed out during banner exchange`, sur le LAN et sur l'IP WAN |
| Agent Zabbix `:10050` | non testé | bloqué | TCP accepté, aucune réponse en 6 s. Un agent sain qui refuse une IP ferme la connexion tout de suite |
| REST API | bloquée | bloquée | `scrape_samples_scraped` = 0 depuis 07:50, sauf vers 13:40 |
| Syslog distant | muet | muet | aucun log depuis 15:52:54 |
| HAProxy (IP WAN depuis le LAN) | non testé | indéterminé | TCP 443 et 7000 acceptés, TLS coupé par un reset. Pas de référence saine pour comparer ; la sonde FastAPI Cloud `/sickz` n'a pas répondu en 20 s (`UNVERIFIED`) |

## Ce qui est écarté ou mesuré

- **Ressources** : aucun précurseur à 5 min de résolution avant les 16/11 20:39, 17/11 07:48 et 15/11 23:23 (mémoire 36 à 53 %, disque 46 %, swap 0). Le seul relevé de 13:40 montre 53 % de mémoire et 71 % de CPU, en plein boot.
- **Erreurs noyau** : en 7 jours, aucune ligne `mmcsd`, `sdhci`, `zio`, `panic` ou `trap` dans Loki. Seuls apparaissent les OOM du 13/11 à 02:12, déjà documentés. Mais un message noyau émis après le blocage de syslogd n'atteint jamais Loki : seul `dmesg` sur la console peut le montrer.
- **Rechargement de syslogd** : `newsyslog` le recharge chaque minute (1 890 fois en 3 jours). C'est le cas avant deux des gels, mais aussi le reste du temps : ce n'est pas un déclencheur, seulement le signe qu'un log tourne chaque minute.
- **Démon `filterlog` de pfBlockerNG** : il est relancé 15 s avant les gels de 13:40 et de 15:52:54. Mais il a été relancé huit fois les 15 et 16/11 sans gel, et rien de tel n'apparaît avant 07:48 ni avant le 16/11 à 20:39.
- **Telegraf**, cause connue de gels du GUI et de SSH sur 26.03 (6100) : non installé ici.
- **Volume de `filterlog`** (lignes par minute, moyennes par tranche de 2 h) :

  | Période | Lignes par minute |
  | --- | --- |
  | 10 → 13/11 | 13 à 64 |
  | 14 → 15/11 | 770 à 3 400 |
  | 16 → 17/11 | 630 à 950 |

  Environ 92 % de ces lignes viennent des règles par défaut `pass out` : 30 min avant 07:48 comme 30 min après le reboot de 18:03, avec les trackers `1000005811` (57 à 59 %), `1000005715` et `1000005716`. Elles sont journalisées parce que la config contient `<nologdefaultpass>`, une clé inversée : sa présence **active** la journalisation des règles par défaut « pass ». La sauvegarde d'octobre (13/11 07:30, BE 26.07) ne l'a pas ; celle du 15/11 18:19 l'a. Le diff complet de `check-drift.sh` prend justement cette sauvegarde du 15/11 comme référence : il ne pouvait donc pas voir l'écart.
  Le volume a été 3 à 4 fois plus élevé les 14 et 15/11 qu'aujourd'hui, sans gel : il ne suffit pas à expliquer les gels.
- **Stockage** : la config du 15/11 n'a pas `use_mfs_tmpvar`, donc `/var/log` est sur l'eMMC de 8 Go (`MFG 03/2018`). Compression des logs : `none`.

## Pistes examinées, tranchées par la capture

1. **syslogd bloqué en premier : écarté.** Jusqu'à la panne, la capture montre syslogd au repos (`kqread`), aucune file d'attente sur `/var/run/log` ou `logpriv` (`Recv-Q` 0), et le lecteur `php_pfb` en `pipe_read`, c'est-à-dire en attente de données et non bloqué. syslogd ne se fige qu'après la suspension du pool, comme tout ce qui écrit sur le disque.
2. **Blocage des écritures sur l'eMMC (ZFS) : confirmé** (voir « Cause »). Le bail écrit par Kea à 15:58 est cohérent : ZFS accepte encore des écritures en mémoire juste après la suspension, puis les bloque.
3. **Mémoire : écartée.** 74 000 à 82 000 pages libres (environ 300 Mo) pendant toute la capture.

## Capture sans console : enregistreur SSH

La console série n'est pas joignable : le pfSense est trop loin de la workstation, et les lignes `login on ttyu0 as root` sont la connexion automatique de chaque boot, le menu console n'étant pas protégé. SNMP ne peut pas servir non plus : `hostres` est configuré, mais le démon est désactivé.

Reste la fenêtre d'environ 25 s entre le moment où sshd répond et le gel (18:04:30 → 18:04:55). [`freeze-capture.sh`](../../../scripts/pfsense/freeze-capture.sh) fonctionne ainsi :

1. Il attend une vraie bannière SSH, et pas une simple connexion TCP.
2. Il s'authentifie aussitôt : PIN puis touche YubiKey.
3. Il envoie [`freeze-capture-remote.sh`](../../../scripts/pfsense/freeze-capture-remote.sh) dans la session. Toutes les ~8 s, pendant environ 25 min, ce script affiche `ps` avec `wchan`, `procstat -kk` des démons suspects et d'Unbound (témoin), les files de `/var/run/log`, la mémoire, l'activité de l'eMMC et la fin de `dmesg`.

Le flux part dans `logs/pfsense-freeze-<date>.log` sur la workstation ; il n'écrit rien sur pfSense et n'appelle jamais syslog. La session laisse aussi un master SSH, que d'autres sondes en lecture seule peuvent réutiliser.

```bash
bash scripts/pfsense/freeze-capture.sh
```

Lancer la commande **avant** de redémarrer pfSense, puis revenir à la workstation pour saisir le PIN dès que le message s'affiche. Le dernier horodatage `===` du fichier date la fin du flux. Si le flux continue pendant le gel, la capture contient l'état bloqué ; s'il s'arrête, c'est que la session elle-même s'est figée, ce qui est aussi une information.

Chaque coupure de courant est un démarrage à froid, qui relie brièvement le LAN et le WAN. Le DHCP est mort depuis des heures, donc beaucoup de clients émettent des requêtes DHCP : débrancher le câble WAN (Freebox) avant de remettre le courant évite qu'un client prenne l'IP publique. Le rebrancher une fois la capture lancée en fait une expérience utile : si pfSense ne gèle pas sans WAN mais gèle dès son retour, le trafic WAN (journalisation, Snort, pfBlockerNG) est en cause.

## Capture à faire au prochain gel, si la console est accessible

Sur la console série : se connecter, puis l'option 8 du menu pour avoir un shell (syntaxe tcsh).

```sh
dmesg | tail -40
ps -axo pid,state,wchan,%cpu,rss,etime,command | head -70
procstat -kk `pgrep -x syslogd`
procstat -kk `pgrep -x sshd` `pgrep -f kea-dhcp4` `pgrep -f zabbix_agentd`
pgrep -fl 'php_pfb|sshguard'
grep '|' /var/etc/syslog.conf
top -b -o res | head -25
zpool status -x
sysctl vm.stats.vm.v_free_count kstat.zfs.misc.arcstats.size
```

Comment lire le résultat :

- **syslogd en `pipe_write`** ou `pipewr` : le lecteur du pipe est bloqué. Regarder son `wchan` (`php_pfb` ou sshguard). Pour confirmer sans redémarrer, `kill` ce seul lecteur : si le GUI, SSH et le flux syslog reviennent, la cause est établie. Noter l'heure, puis redémarrer proprement.
- **syslogd en `zio`, `tx->tx` ou `zfs`**, ou `dmesg` qui montre des erreurs `mmcsd0` ou `sdhci` : stockage, piste 2.
- **sshd, Kea ou Zabbix en `sbwait`, `uipc` ou `nanslp`** (boucle de réessai de syslog) : piste 1.
- **`vmwait` ou `pfault`** : mémoire, piste 3.
- **La connexion à la console se fige** (`login` journalise par syslog) : indice en faveur de la piste 1.

Ensuite, redémarrer avec `reboot` depuis la console, **jamais par coupure de courant** : un démarrage à froid relie brièvement le LAN et le WAN sur le 1100 ([fiche du 14/11](2026-11-14-netgate-1100-cold-boot-switch-bridge.md)).

## Wi-Fi `NETGEAR75`

La radio n'a pas pu être testée : la workstation n'a pas de carte Wi-Fi. Le point d'accès `172.17.0.12` est en ligne : il répond au ping et sa page d'administration demande un identifiant.

**Depuis 17:23, pfSense ne répond plus au DHCP.** Conséquences :

- un appareil Wi-Fi ou filaire qui se reconnecte, ou dont le bail expire (2 h), n'obtient plus d'adresse ;
- un appareil qui a encore un bail valide garde Internet et le DNS.

C'est probablement ce que tu constates sur `NETGEAR75`. Ça ne vient pas du Netgear.

## Non fait

- Cause : établie par l'enregistreur SSH (`logs/pfsense-freeze-20261117-185455.log`, hors Git, 30 tours). L'horloge de pfSense, sans NTP puisque le WAN était débranché, retardait d'environ 50 min : les horodatages 18:05 → 18:09 du fichier correspondent à environ 18:56 → 18:59 en heure réelle.
- Santé de l'eMMC, **lue le 17/11 à 21:08** après installation de `mmc-utils` (décision opérateur) : durée de vie estimée A et B à `0x0b`, soit 100 à 110 % de la durée nominale consommée ; `PRE_EOL_INFO` à `0x01` (réserve normale) ; **`BKOPS_STATUS` à `0x03` (critique)** : la puce est en retard sur sa maintenance interne, ce qui explique les blocages sous rafale d'écritures. Le même jour à 21:12 : aucune erreur `mmcsd0` depuis le boot, pool `pfSense` `ONLINE` sans erreur, lecture brute de 256 Mio à 25,7 Mo/s sans erreur, 385 Mio de RAM libres, pas de swap ni d'OOM. Un test matériel de la RAM est impossible à distance (pas d'ECC, pas de memtest sur le 1100).
- Copie de secours de `config.xml` : **faite le 17/11 à 19:47:17**, dans la fenêtre d'un boot WAN débranché. Fichier `config-pfsense.albandrieu.com-20261117194717-be-default_clone_20261115_stable-26.03-emmc-failing.xml` (527 Ko, `600`) dans `/media/backup/lab/infra/pfsense/2026-11/`. Le XML est valide ; dernière révision le 16/11 à 20:29 (« remove 7 unused CA(s) »). pfSense a regelé vers 19:51.
- Accès SSH : `admin` et `albandrieu` n'ont qu'une clé `ssh-ed25519` logicielle (déjà le cas en octobre), en mode clé seule, sur le port 9922 ouvert au WAN. Aucune clé matérielle `sk-ssh-ed25519@openssh.com` n'est autorisée.
- Radio Wi-Fi et configuration du Netgear : `NOT_RUN`.
- Pont LAN/WAN des démarrages à froid : Suricata (TrueNAS, `br0`, `eve.json` dans Loki) a vu la Freebox (`82.66.4.254`) donner l'IP publique `82.66.4.247` à des MAC locales `02:00:00:00:20:01`, `:20:02` (13/11 20:42) et `:10:01` (14/11 18:16), soit des VM sur `br0`. Rien depuis, boots du 17/11 compris, et aucun conflit ARP dans les logs pfSense depuis le 10/11. Le WAN de pfSense est en IP fixe : tout client DHCP du LAN peut prendre ce bail pendant le pont. Le journal `configd` du Mac (interface `en7`, relevé par l'opérateur) montre que le pont était bien ouvert le 17/11 : la Freebox lui a proposé `82.66.4.247` à 13:34, 13:35, 15:48, 15:49 et 18:00. Le Mac l'a refusée à chaque fois (`dhcp_decline`), car l'adresse répondait déjà en ARP depuis un autre appareil. Ce n'était pas pfSense :
  - à 13:34, un **pont Philips Hue** (réservation `172.17.0.68`) ;
  - ensuite, la **TV Samsung** `tizen` (réservation `172.17.0.81`).

  Ces deux objets connectés ont donc tenu l'IP publique, exposés directement à Internet sans pare-feu pendant les fenêtres de pont, et en concurrence ARP avec le WAN de pfSense. Le Mac ne l'a jamais utilisée. À faire : couper puis rétablir le réseau de la TV et du pont Hue une fois pfSense stable, pour qu'ils reprennent un bail Kea ; ne jamais démarrer le 1100 à froid avec le WAN branché. Le 4200, avec ses ports indépendants, supprime ce chemin.
- HAProxy pendant le gel : indéterminé. L'exporter HAProxy est à `up=0` depuis au moins 48 h, un écart séparé.
- Aucune modification sur pfSense. Le seul effet de bord du diagnostic est le renouvellement du bail DHCP de la workstation à 15:58 (même adresse).

## Suites

1. ~~**Sauver la config**~~ : fait le 17/11 à 19:47 (voir « Non fait »).
2. **Remplacer le stockage, donc le boîtier** : l'eMMC du 1100 est soudée. Deux possibilités :
   - un nouvel appareil (Netgate ou x86 avec SSD), sur lequel on restaure `config.xml` puis on rejoue `check-drift.sh` ;
   - la Freebox repassée en mode routeur, en solution d'attente pour retrouver DHCP et Wi-Fi. Le plan d'adressage `172.17.0.0/24`, les réservations et les overrides DNS sont alors perdus.

   **Décidé le 17/11 : Netgate 4200 MAX** (NVMe, 4 ports indépendants, pfSense Plus inclus ; comparatif et étapes dans la [roadmap H07b](../../roadmap.md)).
3. **D'ici là, limiter les écritures** si une fenêtre stable revient. Cela prolonge peut-être l'eMMC, sans réparer une puce qui lâche en quelques minutes :
   - **fait le 17/11 entre 21:00 et 21:06** (boot WAN débranché) : attente de pfBlockerNG et CrowdSec, arrêt de la journalisation des règles par défaut et des graphes RRD ; trois `check` convergés, BE de repli resynchronisé. pfSense tenait encore 11 min après le boot, contre environ 4 min aux boots précédents ;
   - tout passer en une fois avec [`boot-window-apply.sh`](../../../scripts/pfsense/boot-window-apply.sh), pendant un boot WAN débranché (décision opérateur du 17/11) ;
   - garder pfBlockerNG et le bouncer CrowdSec arrêtés au boot : [`hold-packages-at-boot.php`](../../../scripts/pfsense/hold-packages-at-boot.php) (`check`/`apply`/`start`). Tant qu'ils sont arrêtés, leurs blocages ne s'appliquent plus ;
   - appliquer le script ci-dessous ;
   - couper les graphes RRD : [`disable-rrd-graphing.php`](../../../scripts/pfsense/disable-rrd-graphing.php) (`check`/`apply`/`revert`), CODED et testé hors ligne, NOT_RUN ;
   - ne pas couper la journalisation locale : `system_syslogd_start()` ne démarre alors plus sshguard ([`syslog.inc`](https://github.com/pfsense/pfsense/blob/master/src/etc/inc/syslog.inc)), ce qui retirerait la protection du SSH ouvert au WAN ;
   - pas de RAM disk : ~290 Mo libres au plus bas pendant la capture, et `/var` contient les données de pfBlockerNG, Snort et CrowdSec.
- **Réduire le flot de `filterlog` au niveau d'octobre** : [`stop-default-pass-logging.php`](../../../scripts/pfsense/stop-default-pass-logging.php), CODED et testé hors ligne ; `check` et `apply` NOT_RUN.
  - Ce que fait le script : il retire `syslog/nologdefaultpass`, écrit la config (une révision dans Config History), puis met en file un rechargement du filtre. Il compte aussi, dans `/tmp/rules.debug`, les règles par défaut « pass » encore journalisées : un `WARN` signale un rechargement en attente ou en échec.
  - Ce qu'il ne touche pas : les règles par défaut « block » et les règles utilisateur gardent leur journalisation.
  - `check-drift.sh` l'exécute en mode `check` à l'étape 6.
  - Mise en œuvre :

    ```bash
    ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/stop-default-pass-logging.php
    ssh -p 9922 admin@172.17.0.1 "php -- apply" < scripts/pfsense/stop-default-pass-logging.php
    ```

    Puis relancer `check` une minute plus tard, resynchroniser le BE de repli (`sync-fallback-be-config.sh`) et vérifier dans Loki que `filterlog` redescend vers 30 à 60 lignes/min.
  - Effet attendu : moins de rotations et moins d'écritures sur l'eMMC. C'est un allègement, pas un remède. Les RAM disks restent exclus sans mesure mémoire préalable (1 Go, Snort).
- Surveillance : aucune alerte dédiée au silence syslog (`sum(count_over_time({job="pfsense"}[10m]))` = 0) ni à l'arrêt du DHCP. Seule `pfSenseMetricsMissing` a donné un signal indirect.
- Le retest du 26.07 ([roadmap H07b](../roadmap.md#h07b--pfsense--stabiliser-default_clone-puis-repasser-en-2607-1511)) ne peut plus imputer ce gel au 26.07.

## Leçons

- `up` = 1 côté Prometheus ne prouve pas que la REST API répond. `scrape_samples_scraped` = 0 est le vrai signal.
- Le flux syslog dans Loki date les gels sans SSH : arrêts nets, `---<<BOOT>>---` et l'activité des dernières minutes.
- Un service qui accepte TCP mais ne parle jamais n'est ni `DOWN` ni sain : il faut tester jusqu'à la réponse applicative (bannière, HTTP, offre DHCP), et refaire le test plus tard, car le gel s'étend.

## Sources externes

- [Retry sans fin de `syslog(3)` sur `/var/run/log`, discussion freebsd-current](https://lists.freebsd.org/pipermail/freebsd-current/2017-April/065664.html)
- [syslogd bloqué en `pipe_write`, bug FreeBSD 259084](https://bugs.freebsd.org/bugzilla/show_bug.cgi?id=259084)
- [Tampon des sockets datagram Unix trop petit, bug FreeBSD 260126](https://bugs.freebsd.org/260126)
- [Netgate 6100 instable depuis 26.03 (telegraf)](https://forum.netgate.com/topic/200547/netgate-6100-unstable-since-upgrade-to-26.03/1?page=1)
- [syslogd qui démarre mal en 26.03](https://forum.netgate.com/topic/200546/syslog-service-doesn-t-start-correctly-in-26.03-release)
- [Timeouts `mmcsd0` sur SG-1100, diagnostic Netgate](https://forum.netgate.com/post/1172391)
- [SG-1100 : échec d'upgrade et eMMC](https://forum.netgate.com/topic/198633/sg-1100-failed-pfsense-upgrade/20)
- [Redmine #14300](https://redmine.pfsense.org/issues/14300) et [Redmine #14181](https://redmine.pfsense.org/issues/14181)
