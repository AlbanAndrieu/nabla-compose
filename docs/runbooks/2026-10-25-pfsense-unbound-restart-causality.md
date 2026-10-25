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

Dans l'échantillon borné, le journal resolver comporte **59 sorties
`pfb_unbound.py`** mais seulement **11 notices `Restart of unbound`**.
Les sorties autour de **00:02–00:05** apparaissent sur **22 dates
distinctes** dans les fichiers consultés (12–26 septembre et
19–25 octobre) ; les jours absents sont des trous de rétention et ne
prouvent pas l'absence d'événement. Ces nombres sont des **comptes
sur les journaux disponibles**, pas une fréquence exhaustive ni une
preuve qu'il y a eu 59 changements de PID.
Le motif quotidien coïncide avec le cron pfBlockerNG de
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


## Relevé du 25 octobre à 19:40 CET — branche PR #280

**Preuve opérateur** : `just pfsense-unbound-restart-test` est
**26/26 PASS** : 10 tests du collecteur Unbound et 16 du formateur
console, avant les évolutions de cette section. Le nouvel échantillon
`pfSense_time=2026-10-25T19:40:49+0100` donne Unbound **PID 2135**,
démarré **25/10 00:04:56**. `unbound_control=REACHABLE` et
RSS **142284 Kio**. La mémoire free+inactive vaut **138,4 Mio**
au moment de cet échantillon ; aucune mesure du pic nocturne n'est
disponible.

### Attribution affinée

- `watchdog_unbound_membership=NOT_LISTED` : la configuration
  installée ne liste pas Unbound dans Service Watchdog ; le cron
  générique toutes les minutes ne suffit pas à conclure que le
  watchdog le redémarre. Une configuration passée différente reste
  historiquement possible, sans preuve.
- `pfblocker_package=pfSense-pkg-pfBlockerNG version=3.2.17_1` :
  le paquet installé contient les **définitions** des fonctions
  `pfb_stop_start_unbound` et `pfb_reload_unbound`.
  Cela n'atteste aucune invocation effective à 00:04.
- Le nouveau résultat affiche **16 OOM historiques distincts sur
  7 minutes**, dont les kills d'Unbound prouvés les **17, 22 et
  24 octobre**. Ce nombre est celui des *lignes distinctes*
  disponibles ; il ne décrit pas 16 redémarrages d'Unbound.
- Le journal configd n'a produit aucun signal correspondant à notre
  filtre. Un fichier absent, un journal tronqué ou une autre manière
  d'invoquer le rechargement reste possible.

Le chemin de code documenté par
[pfBlockerNG / Unbound reload behavior](https://github.com/pfBlockerNG/pfBlockerNG/blob/devel/docs/research/unbound-reload-strategies.md)
distingue une **actualisation des seules données DNSBL** (swap en
mémoire, pas de redémarrage Unbound) d'une **modification de
configuration, d'inclusion de module, de montage ou d'un échec de
swap** (fallback stop/start). Le document a été vérifié par son auteur
le 22 juillet 2026, mais ne constitue **pas** une preuve du chemin
choisi par la version exacte installée sur ce Netgate.

L'[incident amont #546](https://github.com/pfBlockerNG/pfBlockerNG/issues/546)
a documenté une boucle de redémarrages lorsqu'il n'existait **aucun
feed DNSBL actif** ; le bogue a été corrigé en juin 2026.
**Ne pas appliquer** cette cause à ce Netgate : les relevés précédents
montrent plusieurs feeds DNSBL peuplés et actifs, et l'état exact de
l'application installée n'a pas été comparé à la correction amont.

### Nouveau diagnostic d'attribution source et journal

Le collecteur reconnaît les marqueurs expurgés suivants :

| Événement | Portée |
| --- | --- |
| `pfblocker_unbound_stop_marker` | pfBlockerNG a journalisé une demande d'arrêt du résolveur |
| `pfblocker_unbound_start_marker` | pfBlockerNG a journalisé une demande de démarrage |
| `pfblocker_unbound_restart_marker` | pfBlockerNG a journalisé un redémarrage/reload |
| `dnsbl_service_restart_marker` | Redémarrage du service DNSBL, **pas** forcément Unbound |
| `pfblocker_possible_call_target=...` | Appel **possible** dans le PHP installé, jamais une trace d'exécution |

Le dernier en-tête horodaté `[ MM/DD/YY H:MM:SS ]` du journal natif
est affiché seulement lorsqu'il précède l'événement d'au plus **80
lignes**. Les champs `preceding_header_local` et
`header_gap_lines` désignent un **contexte** : ne pas les
rebaptiser `timestamp` ni leur attribuer un décalage UTC inventé.
En l'absence de marqueur fiable, `timestamp=unknown` reste exact.
Le collecteur n'affiche aucun message brut, URL, feed ou credential,
et n'exécute pas les fonctions PHP inspectées.

### Décision

**Cause immédiatement prouvée des interruptions OOM** : pression
mémoire globale du Netgate. **Hypothèse principale des cycles à
minuit** : apply/update pfBlockerNG associé au DNSBL Python.
Le niveau de preuve requis pour attribuer un stop/start est un
`pfblocker_unbound_stop_marker` suivi d'un
`pfblocker_unbound_start_marker` dans un même passage du journal,
et une chronologie compatible avec le nouveau PID, sans OOM
concomitant. L'existence de fonctions dans le paquet ne suffit pas.

Après synchronisation du HEAD de la PR #280 :

```bash
just pfsense-unbound-restart-test
```

```bash
PFSENSE_OUTPUT=verbose just pfsense-unbound-restart-check
```

**Ces nouveaux tests ne sont pas encore exécutés sur le HEAD publié**.
Ne pas déclencher de CI GitHub payante. Aucune modification des services
ou de pfSense n'est justifiée à ce stade.


## Erreur du collecteur et durcissement — 25 octobre, 19:57 CET

**Preuve opérateur :** 30/30 tests PASS (14 Unbound, 16 console) avant
cette correction, mais le diagnostic réel pfSense échouait sur toutes les
sections de journaux : `awk: syntax error at source line 69` (mot `block`).
Il affichait ensuite à tort `0 distinct historical OOM records`.

### Cause du défaut de diagnostic

Un commentaire AWK contenait une apostrophe dans `block's header` alors
que le programme AWK était délimité par des apostrophes dans le shell
FreeBSD. La chaîne était coupée prématurément. Le test `bash -n`
vérifiait le script workstation mais pas le **heredoc distant**.
Le suffixe `| tail -35 || true` masquait ensuite le code de sortie AWK.

**Correctifs persistants :** commentaire corrigé, vérification du heredoc
par `/bin/sh -n` dans les tests hors réseau, stockage borné des
35 derniers événements directement dans AWK, et sortie **non nulle (70)**
avec `ERROR: lifecycle_classifier_failed` si l'analyse échoue.
Un échec de parsing ne doit jamais être présenté comme zéro événement.

### Détection systématique des erreurs de feeds

Le même script inspecte désormais les dernières 2 500 lignes disponibles
des journaux pfBlockerNG (principal, extras, error) et Snort (updater et
rotations prévues), sans téléchargement ni émission d'URL, tokens
ou lignes de journaux brutes. Les catégories sont :
`http_403_or_404`, `http_429_rate_limited`, `http_5xx`,
`download_transport_timeout`, `download_failed_other`,
`asn_ipinfo_retry_signature`, `php_memory_exhausted` et
`download_oversize_or_allocation`. Ce sont des **signaux historiques**
sur une fenêtre bornée : ils ne prouvent pas une panne courante.

### Seuils d'alerte sur les fichiers téléchargés

| Groupe | Warning | Critique | Précaution |
| --- | ---: | ---: | --- |
| DNSBL `.orig` | 16 Mio | 64 Mio | Ancien feed UT1 Adult d'environ 124,5 Mo ; PHP plafonné à 128M |
| Snort règles/archives | 64 Mio | 128 Mio | Inspecter avant d'attribuer un OOM au job de 02:09 |

Les contrôles utilisent uniquement `stat` FreeBSD sur les chemins
connus. Ils affichent un **nom de fichier expurgé** et la taille, pas
les données. Les seuils indiquent un risque à examiner, **pas une
corruption ni une causalité confirmée**. Le nombre de fichiers
inspectés est affiché ; un fichier situé ailleurs peut échapper au scan.
Ne pas augmenter durablement le `memory_limit=128M` du Netgate 1100.

### Validation rapide (aucune mutation pfSense ni CI payante)

```bash
just pfsense-unbound-restart-test
```

```bash
PFSENSE_OUTPUT=compact just pfsense-unbound-restart-check
```

Le rapport unique contient la provenance Unbound, les OOM historiques,
les erreurs de téléchargement et les tailles de fichiers suspects.
Pour détailler, remplacer `compact` par `verbose` ; l'expurgation
reste effective. Si le classifieur échoue, la commande doit échouer.

**Qualité :** les 30 tests de l'ancienne version passent selon
l'opérateur. Les 19 tests Unbound et 18 tests console de la version
en cours restent à revalider sur le SHA exact.

### Commande opérateur ciblée sur les downloads et fichiers volumineux

```bash
just pfsense-feed-pressure-check
```

Cette recette réutilise le même collecteur SSH **read-only** avec
`PFSENSE_OUTPUT=compact`, sans multiplier les commandes de collecte.
Vérifier les catégories `feed_download_signal`, les champs
`log=pfblockerng_extras|pfblockerng_main|snort_updates|snort_rules_update`,
puis `feed_artifact_summary` et `feed_artifact_scope`.
Une erreur du classifieur rend désormais le rapport **incomplet** et
le script sort avec un code d'échec, plutôt que de déclarer zéro OOM.
### Régression de bout en bout du shell distant

Le local-first gate dispose aussi d'un test qui extrait la **boucle
POSIX sh réelle** du heredoc distant et l'exécute sur une fixture
historique isolée. Contrairement au test AWK seul, celui-ci détecte
les apostrophes accidentelles qui cassent l'imbrication shell/AWK.
Le test injecte ensuite une erreur de syntaxe AWK et exige une
sortie non nulle avec `ERROR: lifecycle_classifier_failed`.

Suite de référence : **19 contrats Unbound + 18 contrats console =
37 tests** (nouveau HEAD non validé par l'opérateur à ce stade).