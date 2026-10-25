# pfSense / Netgate 1100 — établir la cause des redémarrages Unbound

> État au 25 octobre 2026. Éléments de preuve provenant des relevés opérateur du
> 24–25 octobre. **Lecture seule.** Aucun service, cron, règle ou DNSBL n'est
> modifié. La correction du split-DNS de la workstation est reportée.

## Trois incidents à ne pas confondre

| Fenêtre locale | Preuve conservée | Conclusion |
| --- | --- | --- |
| 17/10 02:11, 22/10 22:03, 24/10 02:10 | Messages noyau `(unbound) ... killed: failed to reclaim memory` | **Confirmé :** le noyau a tué Unbound sous pression mémoire globale |
| 24/10 23:38–23:40 | `pfb_unbound.py script exiting` 23:38:53 ; démarrage du PID Unbound à 23:38:57 ; notices de restart 23:39:23 et 23:40:04 ; bind conflict 23:39:55 | **Redémarrage/tentatives confirmés, initiateur inconnu.** Le conflit peut résulter d'une seconde tentative pendant qu'un listener existe |
| 25/10 00:04 | `pfb_unbound.py script exiting` 00:04:54 ; PID Unbound 2135 démarré à 00:04:56 | **Forte proximité temporelle DNSBL**, mais la fermeture du module Python peut être une *conséquence* de tout arrêt d'Unbound |

D'autres victimes OOM étaient `php`, `netstat` et `php_pfb`, ce qui
atteste une panne mémoire de **l'appliance entière**, pas seulement un cache
Unbound surdimensionné. Les échantillons nocturnes au moment du pic ne sont
toujours pas disponibles.

### Hypothèses par ordre de preuve

1. **OOM à 02:10 — prouvé pour les dates où le noyau nomme Unbound.**
   Snort est planifié à 02:09 et constitue le premier travail à corréler.
   Sa consommation RSS au moment précis et sa responsabilité **ne sont pas
   encore prouvées**.
2. **Cycle de vie de 00:04 — pfBlockerNG DNSBL probable, non démontré comme
   demandeur.** Le cron est planifié à 00:00 ; la sortie du module DNSBL
   précède de deux secondes le nouveau PID. Vérifier le journal pfBlockerNG
   d'origine et une commande explicite de restart avant toute conclusion.
3. **23:39 — restart concurrent ou listener déjà présent.** La trace
   `bind: address already in use` explique l'échec de la *nouvelle
   tentative d'ouverture du port*, sans expliquer qui l'a lancée.
4. **Service Watchdog, actions configd/UI, CrowdSec :** conserver dans
   l'enquête. Le cron Watchdog toutes les minutes ne prouve pas que le
   service Unbound est surveillé. CrowdSec (~75–85 Mio RSS dans les
   échantillons) peut réduire la marge mémoire, sans être une cause
   vérifiée de ces redémarrages.

Le 25 octobre comporte deux 02:09 (CEST `+02:00` et CET `+01:00`).
Conserver systématiquement le décalage horaire. Ne pas déduire qu'un job
Cron a tourné deux fois.

## Contrôle ciblé, sans action sur pfSense

Depuis un worktree **à jour de la PR en cours** :

1. Valider la collecte de manière hermétique :

```bash
just pfsense-unbound-restart-test
```

2. Collecter les catégories et dates réelles (lecture seule) :

```bash
just pfsense-unbound-restart-check
```

3. Pour afficher les événements détaillés (toujours **expurgés**), exécuter :

```bash
PFSENSE_OUTPUT=verbose bash scripts/pfsense/diagnose-unbound-restart-cause.sh --check
```

Le collecteur parcourt uniquement les dernières **4 000 lignes** par journal
disponible et conserve au plus **35 signaux classifiés** par fichier. Il
ne copie jamais les messages entiers, les feeds, les requêtes, les tokens
ou les arguments des processus. Les logs absents ou à rotation circulaire
peuvent laisser un trou ; l'absence de signal **n'exclut pas** un événement.
Un flux redirigé reste sans ANSI ; ne pas publier de fichiers de log bruts.

### Lire le résultat

| `event` | Ce que cela établit | Ce que cela ne prouve pas |
| --- | --- | --- |
| `kernel_oom_unbound` | Le noyau a tué Unbound sous pression mémoire | Le producteur responsable de la pression |
| `kernel_oom_other` | D'autres processus sont tués | Unbound arrêté au même instant |
| `dnsbl_python_exit` | Le module Python DNSBL s'est terminé | pfBlockerNG est l'initiateur |
| `dnsbl_service_restart_marker` | Le journal pfBlockerNG parle d'un restart DNSBL | PID Unbound tué/redémarré |
| `unbound_restart_notice` | Unbound a consigné un restart | Auteur de la demande |
| `unbound_bind_conflict` | Une tentative de bind a échoué | Cause du premier stop, cause OOM |
| `watchdog_unbound_restart` | Un journal associe Watchdog et restart Unbound | Couverture exhaustive de toutes les actions |
| `configd_unbound_action` | Action configd/Unbound détectée par motif | Utilisateur ou changement initial |
| `snort_cron_exec`, `pfblockerng_cron_exec` | Un log mentionne une exécution cron | Mesure CPU/RSS ou causalité |

Les tâches *scheduled_task* ne sont que la configuration, pas un journal
d'exécution. `watchdog_membership=NOT_VERIFIED` demande de vérifier
**Status → Services → Service Watchdog**, sans l'activer/désactiver.

Le journal pfBlockerNG peut ne pas porter une date ISO 8601 en préfixe ;
les événements qui en résultent affichent `timestamp=unknown`. Ne jamais
reconstituer une date en utilisant uniquement un numéro de ligne ou le
mtime global du fichier.

## Décisions après les nouvelles preuves

- Si un OOM Unbound est présent **au même timestamp**, classer
  `CONFIRMED_KERNEL_OOM` et mesurer le processus qui fait monter
  l'utilisation mémoire *avant* 02:09, sans relancer la mise à jour Snort.
- Si un appel explicite de pfBlockerNG, Watchdog ou configd est vu peu avant
  le nouveau PID et sans OOM, attribuer uniquement la **demande de restart**
  au composant observé ; vérifier séparément sa raison (changement de
  config, fallback DNSBL, crash/dégradation du service).
- Si une fermeture DNSBL est le seul événement disponible, laisser
  `restart_initiator=NOT_PROVEN`. Une simple proximité temporelle ne
  justifie pas de désactiver DNSBL.
- Si les preuves pointent vers une seconde instance et un port déjà utilisé,
  vérifier le processus qui détient TCP/UDP 53 avant toute intervention.
- **Ne pas modifier** service watchdog, cron Snort, schedules pfBlockerNG,
  memory limit PHP, Unbound, CrowdSec ni rebooter pendant l'enquête.

Les tests fournis précédemment par l'opérateur ont passé 19/19 pour le
diagnostic *workstation Wi-Fi/DNS*, mais **ne couvrent pas** le nouveau
collecteur de causalité Unbound. Les tests exact-SHA de celui-ci et la
quality gate globale restent à exécuter en local, sans CI payante.
