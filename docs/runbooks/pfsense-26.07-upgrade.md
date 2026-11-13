# pfSense Plus 26.07 sur le Netgate 1100 : environnements de boot et upgrade

Suite de l'[incident du 2026-11-13](../incidents/2026-11-13-pfsense-unbound-oom-snort-crowdsec.md).
Constats du 2026-11-14, en lecture seule (`bectl`, propriétés ZFS `pfsense:*`,
partition EFI et environnements montés en lecture seule).

## État des environnements de boot

| Environnement | Version | Taille | État | Ce qu'il porte d'unique | Décision |
| --- | --- | --- | --- | --- | --- |
| `default_clone` | 26.03-RELEASE (mai) | 1,68 Go | **N R**, démarre | config de mai + correctifs du 13/11 | garder : seul repli fiable |
| `default_20260824183037_20260926190038` | 26.03.1 | 1,40 Go | échoue après `rc.bootup` depuis le 13/11 20:38 | rien (config du 13/11 20:15, réappliquée) ; origine ZFS des trois autres | supprimer en dernier, après un 26.07 stable |
| `default_20260824183037` | 26.07 (octobre) | 1,11 Go | ne monte plus sa racine, aucun log | **seule copie** de la config du 13/11 07:30 (certificats ACME du 26/10, HAProxy, REST API) | exporter `config.xml`, un essai console série, puis supprimer |
| `default` | 26.07 (août) | 1,21 Go | `pfsense:failed=yes` depuis le 27/08 | rien | supprimer avant l'upgrade |
| `default_20260604025536` | 26.03 (juin) | 0,5 Mo | protégé (`pfsense:protect`) | rien | sans enjeu, à supprimer avec le reste |

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
règles de l'alias `ExternalOffice` et `heimdall / truenas to wan https`.

## Pourquoi 26.07 n'est jamais resté

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
   26.03.1.

## Upgrade vers 26.07

### Prérequis

- Câble console sur le port console du 1100 (115200 8N1), par exemple
  `sudo screen /dev/ttyUSB0 115200`. Sans lui, un nouvel échec reste muet.
- Clé USB retirée, fenêtre de maintenance de 30 min (le DNS et Internet
  coupent).
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

### Plan B

Si 26.07 échoue encore, avec ou sans cause visible : rester sur
`default_clone`, puis réinstaller 26.07 proprement depuis l'image
d'installation du 1100 fournie par Netgate et restaurer la config. Un fil du
forum Netgate rapporte cette sortie pour une boucle d'upgrade 26.07 sur 1100.

## Sources

- [Troubleshooting Upgrades on Netgate 1100 and Netgate 2100 Devices](https://docs.netgate.com/pfsense/en/latest/troubleshooting/upgrades-1100-2100.html)
- [Netgate releases pfSense Plus 26.07](https://www.netgate.com/blog/netgate-releases-pfsense-plus-software-version-26.07)
- Forum Netgate : [post 1249539](https://forum.netgate.com/post/1249539), [post 1247075](https://forum.netgate.com/post/1247075)
