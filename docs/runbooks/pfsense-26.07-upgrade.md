# pfSense Plus 26.07 sur le Netgate 1100 : environnements de boot et upgrade

Suite de l'[incident du 2026-11-13](../incidents/2026-11-13-pfsense-unbound-oom-snort-crowdsec.md).
Constats du 2026-11-14, en lecture seule (`bectl`, propriétés ZFS `pfsense:*`,
partition EFI et environnements montés en lecture seule).

## État des environnements de boot

| Environnement | Version | Taille | État | Ce qu'il porte d'unique | Décision |
| --- | --- | --- | --- | --- | --- |
| `default_clone_20261115_stable` | 26.03-RELEASE | 1,68 Go | **N R** ; revenu le 16/11 à 00:05 après le test du 26.07 | config du 15/11 21:21 : baux DHCP restaurés, pfBlockerNG IPv4 seul, pools `ntopng`/`graylog` supprimés, pflow vers Akvorado | garder : config en service |
| `default` | 26.03 (juin, ex-`default_20260604025536`) | 1,67 Go | démarre en 58 s | binaires de juin ; config en service recopiée le 15/11 (révision 21:21), copie de juin conservée en `config.xml.nabla-pre-sync-*` | garder comme repli ; resynchroniser après chaque changement |
| `default_20260824183037` | 26.07 (octobre) | 1,11 Go | boot unique réussi le 15/11 à 21:51 (`failed` levé, donc devenu **cible du repli** du stable) ; jeu de règles non chargé (`bogonsv6` + limite 400k), interface web et SSH bloqués vers 23:00 | config en service recopiée le 15/11 (révision 21:21, migrée par le boot à 21:56) ; config d'octobre gardée en `config.xml.nabla-pre-sync-*` et dans l'export `2026-11/` | réessayer avec la console série, après l'apply de la limite de tables |
| `default_20260824183037_20260926190038` | 26.03.1 | 987 Mo | échoue après `rc.bootup` depuis le 13/11 20:38 (cause inconnue, générateur intact) ; config en service recopiée le 15/11 20:31 | rien ; origine ZFS du BE 26.07 | supprimer en dernier, après un 26.07 stable |

L'ancien `default` (26.07 d'août, `pfsense:failed=yes` depuis le 27/08) a été
supprimé par l'opérateur le 15/11 à 18:37 ; `default_20260604025536` a alors
été renommé `default`.

**Repli** : `_be_recent_name` (`/etc/rc.be_functions.sh`) prend le premier
environnement de `bectl list -C creation`, donc **le plus ancien** non actif et
non marqué `pfsense:failed`. Aujourd'hui c'est `default` : le 15/11 à 19:17,
un boot raté est ainsi retombé sur sa config de juin. Depuis 20:2x, `default`
porte la config en service. Après chaque changement de config validé,
resynchroniser :

```bash
ssh -p 9922 admin@172.17.0.1 /bin/sh -s -- check default < scripts/pfsense/sync-fallback-be-config.sh
ssh -p 9922 admin@172.17.0.1 /bin/sh -s -- apply default < scripts/pfsense/sync-fallback-be-config.sh
```

`bash scripts/pfsense/check-drift.sh` (étape 6) rejoue en `check` chaque script correctif : cibles workstation, baux DHCP, pfBlockerNG IP seul, générateur PHP-FPM de tous les BE, config du BE de repli, FR absent de Top Spammers dans les BE inactifs (`be-drop-own-country.php`) et export pflow NetFlow v5 vers Akvorado (`reconcile-pflow.php`). Le check pfBlockerNG signale aussi une table pfB générée mais non chargée dans pf (`WARN: pf_tables_not_loaded`), car un rechargement raté garde l'ancien jeu de règles sans bruit. Tout `CHANGE` ou `WARN` compte comme dérive.

Au premier boot de repli, pfSense réinstalle les paquets absents de `default`
(RESTAPI, crowdsec) par Internet : API REST et bouncer CrowdSec manquent
quelques minutes.

N = en service, R = au prochain boot. Pool `pfSense` : 7 Go, 81 % utilisé,
réservation de 694 Mo, **397 Mo disponibles** : trop peu pour un upgrade
(nouvel environnement plus paquets). Pool sain (`zpool status` sans erreur).
Ne pas lancer `zpool upgrade` : les fonctions activées rendraient le pool
illisible pour un chargeur plus ancien.

## Config en service et sauvegardes

Sauvegardes dans `/media/backup/lab/infra/pfsense/<mois>/` (partage NFS
TrueNAS). Comparaison sans secret de mai à novembre :

| Point | 17/10 (26.07, config 24.6) | 13/11 23:59 (`default_clone`, 24.5) |
| --- | --- | --- |
| Accès WAN à l'interface pfSense (10443) | alias `PFSENSE_ADMIN_WAN` + règle `Block untrusted pfSense GUI/API` | anciennes règles de l'alias `ExternalOffice` vers 10443 et 7000, pas de blocage explicite |
| Règle WAN `heimdall / truenas to wan https` | absente | active |
| HAProxy | 17 backends (`prod_front-traefik-https`, `prod_front-npm-https`...) | 15 backends, noms de mai |
| Unbound host overrides | `bitwarden`, `vaultwarden.int` | absents |
| Paquets | Telegraf, sudo | absents |
| Alias | `NABLA_HTTP_PORTS`, `NABLA_SSL_PORTS`, `PFSENSE_ADMIN_WAN` | absents |
| Service Watchdog | sans `unbound` depuis le 08/09 | `unbound` présent |

La config de l'environnement d'octobre (révision du 13/11 07:30, la plus
récente en 26.07, avec CrowdSec Small et l'ACME du 26/10) est exportée dans
`2026-11/config-pfsense.albandrieu.com-20261113073000-be-default_20260824183037-26.07.xml`
(mode 600). Elle ne peut pas être restaurée sur 26.03 (config 24.6 contre
24.5) : c'est la raison principale de passer en 26.07 rapidement.

En attendant l'upgrade, désactiver dans *Firewall → Rules → WAN* les deux
règles de l'alias `ExternalOffice` et `heimdall / truenas to wan https`
(fait le 15/11, voir plus bas).

## Stabilisation du 15/11 sur `default_clone`

Corrections appliquées par SSH, une révision Config History chacune :

| Heure | Correction | Pourquoi |
| --- | --- | --- |
| 17:22 | Unbound `Outgoing Network Interfaces = All` et Domain Override `int.albandrieu.com` | `*.int` en SERVFAIL : la config de mai sortait par le WAN |
| 17:45 | Syslog distant : `172.17.0.24:1514` seul | `.57:1514` (retiré le 14/11) revenu avec le repli |
| 17:46 | PHP-FPM `4/30/1/2/500` | profil d'origine 8 workers sur 26.03 |
| 18:14 | Alias `PFSENSE_ADMIN_WAN`, pass puis `Block untrusted pfSense GUI/API` sur 10443, avant l'« Easy Rule » | **GUI 10443 joignable depuis Internet** : l'« Easy Rule » WAN se charge en `pass in quick proto tcp all` |
| 18:16 | Règles WAN `heimdall / truenas to wan https` et `ExternalOffice` → 7000 désactivées | consigne intérimaire ci-dessus |
| 18:17 | `retire-workstation-targets.php apply` : serveurs HAProxy `.57` inactifs, NAT `:8081` supprimé | retrait du 14/11 perdu avec le repli |
| 18:33 | 9 réservations DHCP d'octobre (dont Talos `.50` à `.52`) | absentes de la config de mai ; les nœuds auraient changé d'IP |

### Ne plus perdre la config au prochain reboot

- Un reboot normal garde la config : `default_clone` est **N R**
  (`zpool get bootfs pfSense`).
- La perte du 13/11 vient du **repli** après un échec de boot.
  `_be_recent_name` (`/etc/rc.be_functions.sh`) choisit alors
  l'environnement non `failed` **le plus récemment créé**. Avant le 15/11,
  c'était `default_20260604025536`, avec une config de juin.
- Point de reprise créé le 15/11 18:19 : `default_clone_20261115_stable`,
  protégé, clone de la config stabilisée. C'est désormais la cible de repli.
  Le recréer (*System → Boot Environments*, clone de `default_clone`) après
  une série de changements, puis supprimer l'ancien.
- Sauvegardes hors boîtier, mode 600 :
  `2026-11/config-pfsense.albandrieu.com-20261115181916-be-default_clone-26.03-stabilized.xml`.
- Contrôle après un reboot ou un repli :

  ```bash
  PFSENSE_DRIFT_BASELINE=/media/backup/lab/infra/pfsense/2026-11/config-pfsense.albandrieu.com-20261115181916-be-default_clone-26.03-stabilized.xml just pfsense-drift
  ```

  `config-drift.py` compare toute la config live à cette sauvegarde,
  y compris les règles, le NAT, HAProxy, les VPN, les certificats et l'IPv6.
  Le 15/11 à 18:20, le résultat était `CONVERGED`.

### Drift restant par rapport à octobre

Comparée à l'export d'octobre, la config live diffère encore sur 3 094
chemins : HAProxy 1 333, DHCP 436, règles 363, listes pfBlockerNG 307,
certificats et CA 203, ACME 91, alias 76, Unbound 22, IPv6 23. Ne pas les
reporter à la main : ils reviennent avec la restauration de la config
d'octobre après l'upgrade (étape 5 du déroulé).

## Pourquoi 26.07 n'est jamais resté

**Cause trouvée le 15/11** : `harden-pfsense-php-fpm.sh` recopiait son fichier
`mktemp` (mode 600) sur `/etc/rc.php_ini_setup` avec `cp -p`. `pfSense-rc`
(ligne 748) exécute ce générateur directement : sans bit d'exécution, le boot
cale 4 à 6 min après « Default gateway » (PHP-FPM mal configuré, file
`check_reload_status` bloquée), puis échoue et bascule. Touchés :
`default_20260824183037` (profil appliqué le 24/10, reboot raté le 13/11
14:27), `default_clone` et son point de reprise (profil appliqué le 15/11 à
17:46). Corrigé dans le script (réécriture en place, contrôle `-x`) et dans
les environnements inactifs :

```bash
ssh -p 9922 admin@172.17.0.1 /bin/sh -s -- check default_clone default_20260824183037 < scripts/pfsense/repair-be-php-generator-mode.sh
```

Avant tout reboot : `harden-pfsense-php-fpm.sh --check` ne doit pas afficher
`GENERATOR_NOT_EXECUTABLE`. Historique antérieur :

- **Août** (`default`) : la vérification de boot a échoué ; journaux tournés,
  cause perdue.
- **Septembre-octobre** (`default_20260824183037`) : upgrade du 26/09, démarré
  le 23/10 en **boot unique** avec `pfsense:noautoverify=yes` (vérification
  manuelle jamais confirmée). Il n'est jamais devenu R : le reboot du 13/11
  14:27 est retombé sur 26.03.1. Depuis le soir du 13/11, il ne monte plus sa
  racine.
- Écarté pour ce dernier échec : la partition EFI (`mmcsd0s1`, 200 Mo) porte
  le chargeur 26.07 du 26/09, identique (md5) à celui de l'environnement ;
  noyau présent ; pool sans erreur ; le chargeur Lua n'ignore pas un
  environnement marqué `failed`. Cause **inconnue** sans console série.
- Une clé USB Kingston (installeur UFS, chargeur EFI de décembre 2023) est
  branchée depuis au moins le 13/11 21:21. Le 1100 ne démarre pas sur USB sans
  intervention dans U-Boot, mais la retirer supprime toute ambiguïté.
- Côté Netgate : le 1100 est le pire cas pour les upgrades à cause de sa RAM ;
  le guide de dépannage conseille de couper les services non essentiels avant
  l'upgrade. Des rapports de forum décrivent des upgrades 26.07 sur 1100
  rattrapés par le retour arrière d'environnement de boot.

## Nettoyage des environnements

Dans *System → Boot Environments* (ou `bectl destroy -o <nom>`), après accord
sur chaque suppression, irréversible :

1. Supprimer `default` (août) : libère ~1,2 Go, prérequis de l'upgrade.
2. Config d'octobre : exportée le 14/11 (voir plus haut). L'AutoConfigBackup
   n'a, pour cet environnement, qu'une entrée du 04/11 19:53.
3. Après l'essai console série (voir plus bas) : supprimer
   `default_20260824183037` et `default_20260604025536` (retirer d'abord la
   protection).
4. Une semaine après un 26.07 stable : supprimer le point de restauration
   26.03.1, puis `default_clone_20261115_stable`, le point de reprise protégé
   du 15/11.

## Upgrade vers 26.07

### Prérequis

- Câble console sur le port console du 1100 (115200 8N1), par exemple
  `sudo screen /dev/ttyUSB0 115200`. Sans lui, un nouvel échec reste muet.
- Clés USB retirées (Kingston et SanDisk, fait le 15/11), fenêtre de
  maintenance de 30 min (le DNS et Internet coupent).
- `default` supprimé ; vérifier `zfs get available pfSense/ROOT` (> 1,5 Go).
- Sauvegarde de la config courante (*Diagnostics → Backup & Restore*), à
  ranger avec les autres dans `/media/backup/lab/infra/pfsense/<mois>/`.
- Mémoire : arrêter Snort et ntopng le temps de l'upgrade.
- Référence avant upgrade :

  ```bash
  scripts/pfsense/diagnose-recover.sh --check-posture
  scripts/pfsense/diagnose-recover.sh --check-identities
  just crowdsec-pfsense-accept
  ```

### Déroulé

1. *System → Update* : branche 26.07, vérification de boot **automatique**
   (ne pas cocher la vérification manuelle, cause de la non-persistance
   d'octobre). Ne rien modifier dans l'interface pendant l'upgrade.
2. Suivre le premier boot sur la console série.
3. Si `*** SYSTEM BOOT FAILURE ***` s'affiche : taper `R` dans les 60 s, puis
   relever `tail -n 40 /tmp/PHP_errors.log` et `dmesg -a | tail -n 80`, et
   noter la commande en échec. `exit` laisse ensuite pfSense revenir sur
   `default_clone`.
4. Si le boot réussit : `bectl list` doit montrer **N R** sur le nouvel
   environnement, et `pfsense:failed` doit avoir disparu.
5. Restaurer la config d'octobre exportée (même version de config, 24.6) via
   *Diagnostics → Backup & Restore*. Elle ramène le blocage WAN de
   l'interface, HAProxy, les overrides Unbound, Telegraf et les identités
   REST API. Ses certificats ACME datent du 26/10 (renouvelés à 30 jours).
   Attendre la fin de la réinstallation des paquets sans toucher à
   l'interface.
6. Réconcilier et vérifier :

   ```bash
   scripts/pfsense/diagnose-recover.sh --apply-posture
   scripts/pfsense/diagnose-recover.sh --check-identities
   just crowdsec-pfsense-accept
   ```

   La config d'octobre a ET Open et OpenAppID actifs et pas d'Unbound dans le
   Watchdog : `--apply-posture` corrige les deux. Contrôler aussi que
   l'exporter Prometheus collecte de nouveau.
7. La config d'octobre précède le retrait du 14/11 : relancer
   `retire-workstation-targets.php` et vérifier le syslog distant. Comparer
   ensuite avec `config-drift.py` contre la sauvegarde stabilisée du 15/11 :
   seuls les écarts voulus d'octobre doivent rester.

### Plan B

Si 26.07 échoue encore, avec ou sans cause visible : rester sur
`default_clone`, puis réinstaller 26.07 proprement depuis l'image
d'installation du 1100 fournie par Netgate et restaurer la config. Un fil du
forum Netgate rapporte cette sortie pour une boucle d'upgrade 26.07 sur 1100.

### Clé USB de réinstallation

La clé Kingston DataTraveler (29 Go, étiquette `DTBFAT0`) porte le
**Netgate Installer de décembre 2023**. C'est un installeur en ligne : il
télécharge pfSense Plus depuis les serveurs Netgate.

- **Internet pendant la réinstallation** : l'installeur configure lui-même le
  port WAN du 1100, en DHCP, statique ou PPPoE, éventuellement avec un VLAN.
  Il n'a pas besoin de pfSense. Câble WAN du 1100 sur la Freebox en bridge :
  le bail DHCP donne l'IP publique. Sinon, partage de connexion de la
  workstation ou d'un téléphone vers le port WAN.
- **Image hors ligne** : le ticket TAC *Firmware Access* de l'opérateur a
  fourni cet installeur en ligne, déjà sur la clé. Il n'existe donc pas
  d'image hors ligne pour le 1100 : la réinstallation passe par le WAN branché
  sur la Freebox, qui donne Internet sans pfSense.
- **Rafraîchir l'installeur** : télécharger `netgate-installer-aarch64.img.gz`
  depuis le compte Netgate Store, puis l'écrire (cela efface la clé) :

  ```bash
  gunzip -c netgate-installer-aarch64.img.gz | sudo dd of=/dev/<clé> bs=4M conv=fsync status=progress
  ```
- **Démarrage sur la clé** : console série 115200, appuyer sur une touche pour
  arrêter l'autoboot U-Boot, puis `run usbboot`. En cas d'échec, `usb reset`
  puis `run usbboot`. En dernier recours, `run usbrecovery`, qui efface
  l'eMMC.
- Après réinstallation : restaurer la dernière sauvegarde de
  `/media/backup/lab/infra/pfsense/<mois>/`, puis suivre les étapes 6 et 7.

## Sources

- [Troubleshooting Upgrades on Netgate 1100 and Netgate 2100 Devices](https://docs.netgate.com/pfsense/en/latest/troubleshooting/upgrades-1100-2100.html)
- [Netgate releases pfSense Plus 26.07](https://www.netgate.com/blog/netgate-releases-pfsense-plus-software-version-26.07)
- Forum Netgate : [post 1249539](https://forum.netgate.com/post/1249539), [post 1247075](https://forum.netgate.com/post/1247075)
- [Reinstalling pfSense Plus Software (Netgate 1100)](https://docs.netgate.com/pfsense/en/latest/solutions/sg-1100/reinstall-pfsense.html)
- [Perform the Installation](https://docs.netgate.com/pfsense/en/latest/install/install-pfsense.html) : l'installeur exige Internet (DHCP, statique ou PPPoE).
