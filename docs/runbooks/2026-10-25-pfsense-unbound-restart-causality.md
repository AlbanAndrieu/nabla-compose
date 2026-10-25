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


## Relevé supplémentaire du 25 octobre à 19 h 23 CET

**Validation fournie :** les **7 tests** du collecteur précédent passent.
Le diagnostic daté `2026-10-25T19:23:30+0100` établit que
Unbound PID **2135** fonctionne toujours et que son démarrage local
remonte au **25/10 00:04:56**, donc avant le passage à l'heure CET.
Mémoire libre + inactive : **174,3 Mio au moment du relevé** ; pas
une mesure d'un pic à 02:09.

Les journaux remontent des sorties `pfb_unbound.py` autour de
**00:03–00:05** quasiment quotidiennement, du **12 septembre**
au **25 octobre**, alors que pfBlockerNG possède un cron de
mise à jour à minuit. Cela rend les travaux DNSBL périodiques
**fortement suspects pour la séquence de cycle de vie**.
Toutefois, ces sorties régulières ne prouvent pas que le
**PID d'Unbound change tous les jours**. Le nouveau PID à 00:04:56
le 25/10 est attesté ; une demande de redémarrage au même instant ne
l'est pas. Aucune nouvelle preuve d'OOM à 00:04 n'est présente.

Plusieurs épisodes de notifications Unbound accompagnent des sorties
du module Python, notamment **20/10 10:39**, **22/10 14:05**,
**22/10 21:41–21:42** et **24/10 23:39–23:40**.
Les conflits de bind de 21:42 le 22/10 et 23:39:55 le 24/10
renforcent la piste de tentatives de relance qui se chevauchent,
sans identifier qui exécute la deuxième action.

Les OOM enregistrés les 17, 22 et 24 octobre attestent des
kills d'Unbound par le noyau ; ils sont **indépendants des sorties
DNSBL observées à 00:04**, sauf nouvelle preuve commune.

### Défauts du diagnostic corrigés après ce relevé

- Le résumé `0 distinct historical OOM records` était faux : les
  événements `signal_source=system event=kernel_oom_unbound` n'étaient
  pas pris en compte par `console.sh`. Le formateur les agrège maintenant
  par minute et conserve un compteur `unbound kills`, sans dupliquer
  les événements des autres collecteurs.
- Les événements pfBlockerNG portaient `timestamp=unknown`.
  Le diagnostic **ne remplace pas** ce champ par le mtime du fichier,
  une date d'un événement adjacent ou une heure inventée. La corrélation
  à la seconde reste **bloquée par la forme du journal natif**.
- `Service Watchdog` : lecture limitée à
  `/conf/config.xml` dans la section
  `installedpackages/servicewatchdog/item/name`. Seul
  `watchdog_unbound_membership=LISTED|NOT_LISTED|...` est affiché.
  Un cron Watchdog toutes les minutes ne prouve pas qu'il surveille Unbound.
- `pfBlockerNG` : interrogation read-only de la version de paquet
  installée et de la **présence de fonctions**, sans charger ni exécuter
  son code. Cette présence n'est pas une preuve du chemin utilisé lors
  de l'événement. Les implémentations plus récentes peuvent appliquer
  les données DNSBL en mémoire, tandis qu'un changement de configuration
  peut nécessiter un stop/start :
  [documentation pfBlockerNG](https://github.com/pfBlockerNG/pfBlockerNG/blob/devel/docs/research/unbound-reload-strategies.md).
  Ne pas attribuer ce comportement au Netgate avant confirmation de version.
- Le collecteur recherche aussi les événements classifiés de
  `/var/log/configd.log` et de sa rotation si les fichiers existent ;
  aucun argument de commande ni message brut n'est recopié.

Le nouveau contrat local contient désormais les tests de parsing
Watchdog, de classification configd et du rendu OOM. Les **7 anciens
tests ont réussi chez l'opérateur**, pas ces nouvelles validations au
HEAD suivant. L'agent n'a pas exécuté la quality gate complète ;
aucune CI payante ne doit être déclenchée pendant cette enquête.

### Diagnostic suivant

Exécuter depuis le worktree de la PR sur la workstation :

```bash
just pfsense-console-test
```

```bash
just pfsense-unbound-restart-test
```

```bash
PFSENSE_OUTPUT=verbose just pfsense-unbound-restart-check
```

**Critère de décision :** si Watchdog ne liste pas Unbound et qu'un
`configd_unbound_action` ou un événement DNSBL daté est démontré au
voisinage immédiat du démarrage 00:04:56, préciser l'initiateur avec
la source et la date. Sinon conserver `restart_initiator=NOT_PROVEN`
et surveiller une prochaine fenêtre d'actualisation avec une
collecte strictement bornée. Ne pas modifier les horaires ni les services
sur la seule corrélation.
