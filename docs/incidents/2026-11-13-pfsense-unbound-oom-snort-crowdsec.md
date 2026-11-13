# pfSense : Unbound tué par l'OOM Snort, puis retour arrière d'environnement de boot

Date : 2026-11-13 (Netgate 1100, pfSense Plus).
Preuves : `scripts/pfsense/diagnose-recover.sh`, `diagnose-unbound-restart-cause.sh`,
lectures SSH en lecture seule (`system.log` partagé entre environnements de
boot, `bectl`, propriétés ZFS `pfsense:*`, `config.xml` des environnements
montés en lecture seule) et Prometheus.
Précédent : [redémarrages d'Unbound du 2026-10-24](2026-10-24-pfsense-unbound-restarts.md).

## Résumé

- **02:12:21** : Unbound est tué par l'OOM noyau pendant la reconstruction des
  règles Snort WAN. Le DNS reste coupé environ 7 h : Unbound n'était **pas**
  dans le Service Watchdog de l'environnement en service (26.07).
- **14:27:15** : un reboot démarre le **point de restauration du 26/09**
  (26.03.1) au lieu de l'environnement 26.07 d'octobre. La config revient au
  26/09 : plus de comptes REST API (401 de l'exporter dès 14:34:41), CrowdSec
  quitte le mode Small, limite mémoire HTTP Inspect de Snort à 144 Mio.
- **Le soir** : le point de restauration refuse ensuite de démarrer
  (20:38, 21:20, 21:48) et l'environnement d'octobre ne monte même plus sa
  racine (22:20). Seul `default_clone` (26.03-RELEASE, config de mai)
  démarre ; tout a été remis en état dessus.
- Le crash report `pkg_mgr_install.php:447` (`gettext()` trop long, 14:40:32)
  est un bug de la page des paquets, sans lien. Pas de panic.

## Chronologie

| Quand (Paris) | Fait |
| --- | --- |
| 23/10 08:26 → 08:31 | Reboot en **boot unique** sur l'environnement 26.07 (`pfsense:lastbootonce`) : le point de restauration du 26/09 reste l'environnement par défaut |
| 27/10 22:45 | CrowdSec passe en mode Small (moteur et LAPI sur TrueNAS `172.17.0.24:8084`) |
| 13/11 02:09:39 | `snort_check_for_rule_updates` (`php` 45681) : nouvelles règles Subscriber, Community et ET Open |
| 13/11 02:12:15 → 02:12:21 | OOM `failed to reclaim memory` : `php` 45681, `php_pfb`, `netstat`, puis `unbound` |
| 13/11 09:11:43 | Unbound relancé à la main |
| 13/11 14:27:15 | Reboot : démarrage du point de restauration 26.03.1 (`default_20260824183037_20260926190038`) |
| 13/11 14:34:41 | Premiers 401 de l'exporter : comptes REST API absents de cette config |
| 13/11 19:33 | Réglages Snort réappliqués sur le point de restauration |
| 13/11 20:38, 21:20, 21:48 | Le point de restauration échoue au démarrage, repli automatique sur `default_clone` |
| 13/11 22:20 | Boot unique de l'environnement d'octobre (`default_20260824183037`) : racine jamais montée, repli sur `default_clone` |
| 13/11 22:08 → 22:34 | REST API 2.11 installée, comptes et empreintes de clés recopiés d'octobre : l'exporter collecte de nouveau (57 échantillons) |
| 13/11 22:53:13 | Fin de `install-crowdsec.sh` : sa config chargée au début écrase les réglages enregistrés pendant l'installation |
| 13/11 23:03:26 | Révision de 22:51:27 restaurée (Config History), réglages Snort et CrowdSec réenregistrés |

## Cause racine

### OOM de 02:12

- Le premier processus tué par l'OOM est le plus gros : `php` 45681, la mise à
  jour Snort elle-même.
- La machine est à la limite : 964 Mio de RAM, **aucun swap**, `memory_limit`
  PHP CLI à 128 Mio, Unbound ~126 Mio. Le cache ZFS (`arcstats.c_max`) peut
  atteindre 632 Mio : piste pour le pic, **non prouvée**.
- La reconstruction a aussi tourné les 10, 11 et 12/11 en ~15 s sans OOM ;
  celle du 13/11, avec un nouvel instantané Subscriber, a duré plus d'une
  minute. ET Open et OpenAppID étaient activés dans l'environnement d'octobre :
  les couper supprime les reconstructions quotidiennes inutiles, **pas** le
  risque des nuits où les règles Subscriber changent.

### Pourquoi Unbound n'a pas été relancé

Le Service Watchdog de l'environnement 26.07 en service cette nuit-là ne
contenait pas Unbound. Le `NOT_LISTED` du 24/10 était donc juste. La
sauvegarde du 26/09 (point de restauration), qui le liste, avait d'abord fait
croire le contraire : comparer une config de l'environnement qui tournait au
moment des faits.

### Retour arrière de 14:27

Le 23/10, l'environnement 26.07 a été démarré en boot unique depuis le point
de restauration, sans devenir l'environnement par défaut. Tout reboot ultérieur
revenait donc au 26/09. Le reboot de 14:27 a ramené la config du 26/09 :

- pas de comptes `fastapi_posture`, `fastapi_security`, `pfsense_exporter` ;
- CrowdSec avec moteur et LAPI locaux, bouncer sur `172.17.0.1:8089`
  (dernier pull sur la LAPI TrueNAS à 14:27:12) ;
- Snort WAN avec HTTP Inspect à `150994944` et tous les ports par défaut.

La limite de 32 Mio de
[pfsense-flow-observability-memory](../pfsense-flow-observability-memory.md)
était bien dans `config.xml` d'octobre ; le retour arrière l'a perdue.

### Démarrages refusés le soir

`/etc/pfSense-rc` exécute `rc.bootup` et la suite sous `set -e` avec un
`trap` : toute commande en échec affiche `*** SYSTEM BOOT FAILURE ***` sur la
**console série uniquement**, réactive l'environnement de repli et redémarre
60 s plus tard. Signature dans `system.log` : dernier `done.` de `rc.bootup`,
puis ~66 s après `reboot by root` et `Enter full pathname of shell`.

- Point de restauration : échec ~6 s après la fin de `rc.bootup`, trois fois.
  Il avait démarré à 14:27 ; depuis, System Patches 2.3.5_1, acme et la config
  de 20:15 ont changé. Commande en échec **non identifiée**.
- Environnement d'octobre : aucun log, racine jamais montée (échec au chargeur
  ou au tout début du noyau). Seule la console série peut le montrer.

### CrowdSec

En mode Small, `crowdsec.sh restart` ne fait qu'arrêter : `crowdsec not
running?` et le code `1` sont attendus. Le script rc.d lance le moteur sous
`daemon -r -R 10`. Quand Log Processor et Local API sont coupés, un
superviseur `daemon: crowdsec` resté vivant relance toutes les 10 s un moteur
qui sort aussitôt (`you must run at least the API Server or crowdsec`), et
bloque le `onestop` de la resynchronisation du paquet.

### Installation de paquet et écrasement de config

`install-crowdsec.sh` a tourné ~18 min, bloqué par ce `onestop`. Sa dernière
écriture (22:53:13, « Installed crowdsec package ») a repris la config chargée
au début et annulé l'alias, les réglages Snort, CrowdSec Small et le retrait du
Watchdog enregistrés entre-temps. Restauration : *Diagnostics → Backup &
Restore → Config History*, révision de 22:51:27, puis réenregistrement des
pages CrowdSec et Snort pour régénérer leurs fichiers.

## Remise en état sur `default_clone`

- **REST API** : paquet 2.11 installé (`pkg-static add` du `.pkg` pfrest pour
  26.03). Les trois comptes (uid 2001 à 2003), leurs privilèges, les quatre
  empreintes de clés et `KeyAuth` sont recopiés de la config d'octobre, montée
  en lecture seule ; aucune clé n'a donc changé côté FastAPI ni TrueNAS.
  `diagnose-recover.sh --check-identities` : `state=ok` ×3.
- **CrowdSec** : paquet `pfSense-pkg-crowdsec` 0.1.8 installé, mode Small.
  `just crowdsec-pfsense-accept` : `failures=0`, 4 073 entrées PF.
- **Snort** : ET Open, OpenAppID et AppID Open Text Rules coupés ; HTTP
  Inspect WAN à `33554432` ; alias de ports `snort_http_inspect` = `80` sur le
  moteur `default` (`ports { 80 }` dans `snort.conf`).
- **Service Watchdog** : `unbound` présent, `crowdsec` retiré.

## Automatisation

```bash
scripts/pfsense/diagnose-recover.sh --check-posture   # lecture seule
scripts/pfsense/diagnose-recover.sh --apply-posture   # réconciliation
```

`manage-posture.php` vérifie et réapplique les points ci-dessus (sauf la REST
API, couverte par `--check-identities`/`--apply-identities`) :

- régénère la config Snort (`sync_snort_package_config`) et relance la WAN ;
- rafraîchit la tâche du Watchdog ;
- arrête un superviseur CrowdSec en boucle, puis lance
  `crowdsec_resync_config` ;
- refuse de tourner pendant une installation de paquet ;
- n'écrit ni n'affiche jamais la clé du bouncer : elle vient de la LAPI
  TrueNAS et se saisit dans l'interface.

La REST API n'est pas utilisée pour ces écritures : pfREST 2.11 n'a aucun
endpoint Snort, CrowdSec ni Service Watchdog. Son endpoint d'alias exigerait
une clé avec droit d'écriture, alors que les trois identités sont volontairement
en lecture seule (`user-config-readonly`).

## Non fait

- Cause des échecs de démarrage du point de restauration et de
  l'environnement d'octobre : console série nécessaire. Nettoyage et upgrade
  26.07 planifiés dans le
  [runbook dédié](../runbooks/pfsense-26.07-upgrade.md).
- `default_clone` garde la config de mai pour le reste : règles WAN de
  l'ancien bureau, HAProxy, overrides Unbound et paquets d'octobre absents
  (détail dans le runbook).
- `SSL_PORTS` sans 7000 ni 10443 ; fichiers `emerging*` et `openappid*` encore
  sur le disque.
- Côté FastAPI, les appels avec les clés `posture` et `security` ne sont pas
  revérifiés.

## Vérifier la prochaine fois

```bash
scripts/pfsense/diagnose-recover.sh --check
scripts/pfsense/diagnose-recover.sh --check-posture
scripts/pfsense/diagnose-recover.sh --check-identities
scripts/pfsense/diagnose-unbound-restart-cause.sh --check
```

- Avant toute comparaison : `bectl list` (N = en service, R = au prochain
  boot). Un environnement démarré en boot unique n'est pas persistant.
- `diagnose-unbound-restart-cause.sh` date `snort_rules_rebuild`, nomme la
  victime de chaque OOM (`victim=`) et relève la taille de l'ARC.
- Acceptation : aucun `kernel_oom_*` après la tâche Snort de 02:09 une nuit
  où les règles Subscriber changent. Pour mesurer le pic, lancer
  `just pfsense-memory-window` peu avant 02:09.

## Leçons

- Après un upgrade pfSense Plus, vérifier que le nouvel environnement est
  **R** dans `bectl list`, pas seulement **N**.
- Une config se lit dans l'environnement qui tournait au moment des faits ; une
  sauvegarde d'un autre environnement a induit deux fausses conclusions ici.
- Ne rien enregistrer dans l'interface pendant une installation de paquet :
  sa dernière écriture repart de la config qu'elle a chargée au début.
- Relire le contrat d'architecture avant de « réparer » un service arrêté :
  l'arrêt du moteur CrowdSec est voulu en mode Small.
