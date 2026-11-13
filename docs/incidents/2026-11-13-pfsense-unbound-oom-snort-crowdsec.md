# pfSense : Unbound tué par l'OOM de la mise à jour Snort, mode CrowdSec Small annulé

Date : 2026-11-13 (Netgate 1100, pfSense Plus 26.03.1 après l'upgrade du jour).
Preuves : `scripts/pfsense/diagnose-recover.sh --check`,
`scripts/pfsense/diagnose-unbound-restart-cause.sh --check` et lectures SSH
en lecture seule des journaux `system`, `resolver`, `snort` et `crowdsec`.
Précédent : [redémarrages d'Unbound du 2026-10-24](2026-10-24-pfsense-unbound-restarts.md).

## Résumé

- **Unbound** a été tué par l'OOM noyau à 02:12:21 pendant la reconstruction
  des règles Snort WAN. Le DNS est resté coupé environ 7 h, jusqu'au
  redémarrage manuel de 09:11 : le Service Watchdog ne l'a pas relancé.
- **CrowdSec** : l'absence de moteur local depuis le 27/10 est l'état voulu
  du mode pfSense Small (moteur et LAPI sur TrueNAS `172.17.0.24:8084`, voir
  [apps/crowdsec](../../apps/crowdsec/README.md)). Le 13/11, Log Processor et
  Local API ont été réactivés : le moteur local tourne de nouveau et le
  bouncer lit la LAPI locale `172.17.0.1:8089`. Cette **régression** a été
  annulée le soir même.
- Le crash report `pkg_mgr_install.php:447` (`gettext()` trop long, 14:40:32)
  est un bug de la page des paquets pendant l'upgrade, sans lien. « No FreeBSD
  crash data found » : pas de panic.

## Chronologie

| Quand (Paris) | Fait |
| --- | --- |
| 27/10 22:45:53 | `admin@172.17.0.57` enregistre la page du paquet CrowdSec : bascule en mode Small |
| 27/10 22:45:58 | `Crowdsec service shutting down` : le moteur local s'arrête, comme prévu |
| 13/11 00:05 | Cycle pfBlockerNG : Unbound arrêté puis relancé (pid 44747) |
| 13/11 02:09:39 | Tâche `snort_check_for_rule_updates` (`php` pid 45681) : nouvelles règles Subscriber, Community et ET Open |
| 13/11 02:11:12 | Même pid : `[Snort] Updating rules configuration for: WAN ...` |
| 13/11 02:12:15 → 02:12:21 | OOM `failed to reclaim memory` : `php` 45681, `php_pfb`, `netstat`, puis `unbound` 44747 |
| 13/11 09:11:43 | Unbound relancé (pid 70903) après une connexion admin à 09:10 |
| 13/11 13:41 → 14:26 | Flaps du lien WAN, redémarrages de paquets, `bind: address already in use` ; `service crowdsec.sh restart` ne fait qu'arrêter (Small) |
| 13/11 14:09 → 14:19 | Mise à jour Snort : toutes les résolutions DNS expirent |
| 13/11 14:27:12 → 14:34:24 | Dernier pull du bouncer sur la LAPI TrueNAS, puis reboot de l'upgrade (14:31) : Log Processor et Local API réactivés, moteur local démarré |
| 13/11 19:33 → 19:34 | Changements Snort ci-dessous, Snort régénéré et relancé |

## Cause racine

### Unbound

- Le premier processus tué par l'OOM est le plus gros : ici `php` 45681, la
  mise à jour Snort elle-même. La responsabilité de Snort, « non prouvée » le
  24/10, est établie pour cette nuit.
- La machine est à la limite : 964 Mio de RAM, **aucun swap**,
  `memory_limit` PHP CLI à 128 Mio, Unbound ~126 Mio (plus gros processus
  hors crise). Le cache ZFS (`arcstats.c_max`) peut atteindre 632 Mio ; c'est
  une piste pour le pic, **non prouvée**. Le moteur CrowdSec était arrêté
  cette nuit-là : il n'a pas contribué à cet OOM.
- La reconstruction a aussi tourné à 02:09 les 10, 11 et 12/11, en ~15 s et
  sans OOM. Celle du 13/11, avec un nouvel instantané Subscriber, a duré plus
  d'une minute avant l'OOM. Désactiver ET Open (republié chaque jour, aucune
  catégorie cochée sur la WAN) supprime ces reconstructions quotidiennes
  inutiles, **pas** le risque des nuits où les règles Subscriber changent.

### Pourquoi Unbound n'a pas été relancé

Unbound figure dans le Service Watchdog : c'était déjà le cas dans la
sauvegarde du 26/09, le `NOT_LISTED` du 24/10 était donc faux. Le Watchdog
teste `pkill -0 -x unbound` chaque minute, mais aucun message
`Detected service unbound stopped` n'apparaît entre 02:12 et 09:11, alors
qu'il a bien relancé haproxy à 14:23. Cause **non prouvée**.

### CrowdSec

En mode Small, `crowdsec.sh restart` enchaîne `onestop` puis, comme Log
Processor et Local API sont désactivés, un second `onestop` : la sortie
`crowdsec not running?` et le code `1` sont attendus, ce n'est pas un échec
de démarrage.

Sur la LAPI TrueNAS, le dernier pull de `PFSENSE_FIREWALL@172.17.0.1` date
de 14:27:12 ; le fichier du bouncer pfSense est réécrit à 14:34:24 vers
`http://172.17.0.1:8089`, avec `enable_agent` et `enable_lapi` à `on` et les
champs Remote LAPI vides. Cette fenêtre encadre le reboot de l'upgrade
(14:31) : la réinstallation du paquet a très probablement remis les réglages
par défaut. Non prouvé. Conséquences : les décisions de la
LAPI centrale TrueNAS ne sont plus lues par pfSense, et le moteur local
consomme ~87 Mio sur une machine qui fait des OOM.

L'exporter `pfsense_service_enabled{name="crowdsec"}` décrit l'activation,
pas l'architecture voulue : en Small, un moteur local absent est sain.

## Changements appliqués (UI Snort, opérateur, 13/11)

- **Global Settings** : ET Open, OpenAppID et AppID Open Text Rules
  désactivés. Snort Subscriber, GPLv2 Community et Feodo conservés.
  AppID est désactivé sur WAN et LAN (`appid_preproc=off`).
- **WAN Preprocs** : HTTP Inspect `Memory Cap` à `33554432`. La valeur de
  [pfsense-flow-observability-memory](../pfsense-flow-observability-memory.md)
  n'avait jamais été enregistrée dans `config.xml` (`150994944` dès le 26/09).
- **Alias de ports** `snort_http_inspect` = `80`, utilisé par le moteur
  HTTP Inspect `default` : le `snort.conf` régénéré contient `ports { 80 }`.

Vérifié après application : `config.xml` et `snort.conf` portent les nouvelles
valeurs, Snort tourne à ~50 Mio. Le diagnostic de 19:47 renvoie OK sur les
cinq contrôles Snort, et `34.200.20.162` (sortie FastAPI) n'est plus dans
`snort2c` (`block_match_count=0`).

CrowdSec repassé en mode Small le soir même (**Services → CrowdSec** : Log
Processor et Local API désactivés, Remote LAPI `http://172.17.0.24:8084`,
Remediation Component conservé, étape 2 de
[apps/crowdsec](../../apps/crowdsec/README.md)) :
`just crowdsec-pfsense-accept` renvoie `failures=0`, moteur local absent,
bouncer sur la LAPI centrale, 4 075 entrées PF. Avec Local API désactivé, le
formulaire n'affiche la section Remote LAPI qu'une fois la case décochée.

Non fait, à traiter à part :

- `SSL_PORTS` est la liste par défaut, sans 7000 ni 10443.
- Les fichiers `emerging*` et `openappid*` déjà téléchargés restent sur le
  disque, inutilisés.
- Les comptes API REST `fastapi_posture`, `fastapi_security` et
  `pfsense_exporter` n'existent plus (401 du diagnostic).

## Vérifier la prochaine fois

```bash
scripts/pfsense/diagnose-recover.sh --check
scripts/pfsense/diagnose-unbound-restart-cause.sh --check
```

- `diagnose-recover.sh` affiche en OK/WARN : `snort_http_memcap`,
  `snort_http_inspect_7000`, `snort_download_*`, `crowdsec_small_mode`
  (moteur et LAPI locaux coupés) et `crowdsec_bouncer` (bouncer actif sur la
  LAPI TrueNAS).
- `diagnose-unbound-restart-cause.sh` date `snort_rules_rebuild`, nomme la
  victime de chaque OOM (`victim=`) et relève la taille de l'ARC.
- Acceptation : aucun `kernel_oom_*` après la tâche Snort de 02:09 une nuit
  où les règles Subscriber changent. Pour mesurer le pic, lancer
  `just pfsense-memory-window` peu avant 02:09.

## Leçons

- Un réglage appliqué seulement dans un fichier généré (`snort.conf`) se perd :
  contrôler `config.xml`.
- La présence d'un service dans le Watchdog ne prouve pas qu'il sera relancé.
- Relire le contrat d'architecture avant de « réparer » un service arrêté :
  ce diagnostic a d'abord pris l'arrêt voulu du mode Small pour une panne.
