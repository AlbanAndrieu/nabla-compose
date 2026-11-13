# pfSense : redémarrages d'Unbound, OOM de 02:10 et cycle DNSBL de minuit

Date : 2026-10-17 → 2026-10-26 (Netgate 1100). Preuves : relevés opérateur
en lecture seule (`just pfsense-unbound-restart-check`, captures avant/après
cron, journaux noyau et pfBlockerNG). Précédent :
[OOM du 2026-10-08](2026-10-08-pfsense-unbound-oom-wan-exposure.md).

> Mise à jour 13/11 : la reconstruction des règles Snort est le premier
> processus tué par l'OOM, et Unbound figurait déjà dans le Service Watchdog.
> Voir [l'incident du 2026-11-13](2026-11-13-pfsense-unbound-oom-snort-crowdsec.md).

## Résumé

Lenteurs WhatsApp sur le Wi-Fi et coupures DNS intermittentes. Deux
mécanismes **indépendants** interrompent Unbound ; il ne faut pas les
confondre :

1. **OOM noyau vers 02:10** : l'appliance entière manque de mémoire et le
   noyau tue `unbound`, `php`, `netstat` et `php_pfb`
   (`failed to reclaim memory`).
2. **Stop/start pfBlockerNG vers 00:04** : la mise à jour DNSBL nocturne
   arrête puis redémarre Unbound au lieu d'échanger les données en
   mémoire.

Aucun blocage DNSBL de WhatsApp n'a été prouvé : `whatsapp.com`,
`web.whatsapp.com`, `static.whatsapp.net` et `mmg.whatsapp.net` répondent
`NOERROR` sur Unbound.

## Chronologie

| Quand (Paris) | Fait |
| --- | --- |
| 17, 21, 22, 23, 24/10 vers 02:10 | Groupes OOM noyau ; Unbound tué les 17, 22 et 24/10 (24/10 : `php` 02:10:47, `unbound` 02:10:50, `php_pfb` 02:10:51) |
| 22/10 22:03, 25/10 22:12 | OOM hors fenêtre 02:10 ; `php_pfb` victime le 25/10, après le cron pfBlockerNG de 22:00 |
| 22–24/10 vers 00:04 | Marqueurs pfBlockerNG `pfblocker_unbound_stop_marker` puis `pfblocker_unbound_start_marker` |
| 24/10 23:39:55 CEST | mtime de `unbound.conf` égal à la seconde près à un `bind: address already in use` |
| 25/10 ~23:40 | Profil PHP-FPM réduit de `8/3600/2/7/5000` à `4/30/1/2/500` |
| 26/10 00:04:25 → 00:04:37 | Stop pfBlockerNG, sortie du module Python DNSBL, nouveau PID Unbound (19252 → 2611), start pfBlockerNG ; hashes de `unbound.conf` inchangés ; aucun OOM |

Les OOM et les cycles de minuit **précèdent** la réduction PHP-FPM du
25/10 : elle n'a pas créé l'incident.

## Cause racine

- **OOM** : pression mémoire globale du Netgate 1100 (RAM limitée).
  Le cron Snort `snort_rules_update` tourne à 02:09 et 14:09 : forte
  corrélation avec les OOM de 02:10, **responsabilité non prouvée**. Hors
  cron, `free + inactive` oscille entre 125 et 200 Mio ; RSS observés :
  PHP-FPM 265–316 Mio agrégés (pages partagées comptées plusieurs fois),
  Unbound ~142 Mio, CrowdSec 78–116 Mio, Snort 75–85 Mio.
- **Cycle de minuit** : pfBlockerNG `3.2.17_1` emprunte la voie
  `pfb_stop_start_unbound` plutôt que le rechargement sans arrêt documenté
  en amont
  ([unbound-reload-strategies](https://github.com/pfBlockerNG/pfBlockerNG/blob/devel/docs/research/unbound-reload-strategies.md)).
  La condition qui déclenche ce repli reste `NOT_PROVEN`.
- Service Watchdog ne surveille pas Unbound
  (`watchdog_unbound_membership=NOT_LISTED`) : il n'explique pas les
  redémarrages.

## Décisions

- Conserver PHP-FPM `4/30/1/2/500`, Snort WAN AC-BNFA avec HTTP Inspect
  32 Mio, DNSBL Python, ASN/IPinfo et TLD désactivés, sans Service
  Watchdog sur Unbound. Ne pas restaurer les 8 workers PHP-FPM pour
  tester l'hypothèse DNSBL.
- Ne modifier ni cron Snort, ni planning pfBlockerNG, ni `memory_limit`
  PHP, ni CrowdSec pendant l'enquête ; une seule correction isolée et
  réversible, après preuve, avec sauvegarde de `config.xml` et rollback.
- WhatsApp : ne lever que la règle DNSBL qui bloque un domaine nécessaire
  et confirmé ; jamais d'autorisation globale `*.whatsapp.net`.
- Ne pas lancer `Force Reload` ni redémarrer Unbound pendant la collecte.

## Leçons

- Un `pfb_unbound.py script exiting` est une **conséquence** de tout arrêt
  d'Unbound, pas une preuve de l'initiateur. Il faut un marqueur stop puis
  start explicite dans le même passage du journal pfBlockerNG.
- Garder le décalage horaire (`+02:00`/`+01:00`) : le 25/10 contient deux
  02:09 au changement d'heure, sans double exécution du cron.
- Une absence de trace dans `cron.log` ne prouve pas l'absence
  d'exécution ; une sonde DNS sans échec ne prouve pas l'absence de
  micro-coupure entre deux échantillons.
- Des fichiers `*.orig` sur disque ne prouvent pas qu'un feed est actif ;
  ne rien supprimer sur la seule base de la taille.

## Diagnostic (lecture seule)

- `just pfsense-unbound-restart-check` : OOM, marqueurs pfBlockerNG,
  PID et empreintes de configuration
  (`scripts/pfsense/diagnose-unbound-restart-cause.sh`).
- `just pfsense-unbound-capture` avant et après le cron, puis
  `PFSENSE_BEFORE=… PFSENSE_AFTER=… just pfsense-unbound-compare` avec les
  deux chemins `snapshot_saved=` réellement affichés.
- `just pfsense-memory-window` lancé avant 02:09
  (`scripts/pfsense/sample-oom-pressure.sh`), puis
  `just pfsense-feed-pressure-check`.
- `just pfsense-unbound-lan-dns-watch` depuis un client LAN pendant la
  fenêtre de 00:04 : `dns_downtime_seconds=NOT_MEASURED_ONLY_SAMPLED`.
- `just whatsapp-web-path-check` sur la workstation affectée.

## Suites

- Mesurer depuis le LAN la coupure DNS réelle pendant le stop/start de
  00:04 ; sans coupure, la garder comme dette de continuité.
- Identifier le consommateur mémoire du pic de 02:10 par un échantillon
  RSS pris juste avant, sans déclencher de mise à jour artificielle.
- Clôture : aucun nouvel OOM d'Unbound sur plusieurs cycles, marge
  `free + inactive` ordinaire ≥ 128 Mio, DNS privé et public, HTTPS/pfREST,
  Snort WAN et protections CrowdSec/pfBlockerNG vérifiés. Procédures
  courantes : [pfsense-diagnose-recover.md](../pfsense-diagnose-recover.md)
  et [pfsense-php-fpm-hardening.md](../pfsense-php-fpm-hardening.md).
