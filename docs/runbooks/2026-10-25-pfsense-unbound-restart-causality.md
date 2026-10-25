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

## Suivi qualité — extraction du heredoc SSH, 25 octobre

Le dernier retour opérateur sur `just pfsense-unbound-restart-test`
montre 17/19 PASS pour la suite Unbound précédente et deux défauts
de test : les deux scénarios attendaient `<<'REMOTE'` immédiatement
suivi d'un saut de ligne. L'appel réel est pourtant :

```bash
ssh ... '/bin/sh -s' <<'REMOTE' | pfsense_ui_render
```

Un extracteur commun `extract_remote_shell()` sélectionne maintenant
le corps jusqu'au marqueur de fermeture en ignorant le pipeline
local de rendu. Il échoue si le heredoc manque ou est tronqué.

Un second défaut est apparu pendant la reproduction locale :
l'ancienne injection `THIS TOKEN IS INVALID AWK;` était une expression
AWK grammaticalement valide. Le test utilise désormais `if ( {`
pour provoquer une véritable erreur de parsing. Sur la version
réelle du script fournie par l'opérateur, une reproduction isolée
a validé l'extraction, `/bin/sh -n`, la classification d'un OOM
et le **code de sortie 70** avec `ERROR: lifecycle_classifier_failed`
lors de l'injection. Aucun accès pfSense n'a été requis.

Le contrat est désormais **20 tests Unbound + 18 tests console = 38**.
Ces 38 tests doivent encore être exécutés localement sur le HEAD
de la PR. Le test de la nouvelle version n'a pas été déclaré PASS
à partir du seul résultat de la reproduction isolée.

Commande :

```bash
just pfsense-unbound-restart-test
```

Conserver l'absence d'exécution GitHub Actions payante et ne pas
modifier Unbound/pfBlockerNG pendant la validation.

## Contract local-first : DST et preuve partielle — 25 octobre

Le dernier retour opérateur passe **20/20** contrats Unbound et
**17/18** contrats console avant ce correctif. Le seul échec est
`test_typed_oom_during_dst_keeps_two_minutes_separate` : sa fixture
n'avait aucun en-tête `=== ... ===`, alors que la console marque
volontairement les flux sans section comme `EVIDENCE INCOMPLETE`.
Les événements étaient correctement séparés selon `+02:00` / `+01:00`.

Le test inclut désormais la section de collecteur réelle.
Un test négatif additionnel garantit qu'un OOM sans section
reste **incomplet**, même s'il est individuellement reconnaissable.
**Ne pas supprimer ce fail-closed du renderer pour satisfaire
une fixture tronquée.**

La suite attendue sur la nouvelle révision est maintenant
**20 tests Unbound + 19 tests console = 39 tests**.
Ces tests ne sont pas déclarés verts tant que la validation
sur le HEAD exact n'a pas été fournie.

Commande locale :

```bash
just pfsense-unbound-restart-test
```

## Verdict d'enquête — validation des 39 tests et arrêt/démarrage DNSBL

**Validation opérateur du 25 octobre :**
`just pfsense-unbound-restart-test` = **39/39 PASS**
(20 contrats de causalité Unbound, 19 contrats du formateur console).
La suite valide le rendu des deux minutes distinctes lors du changement
d'heure, les preuves partielles et la détection des erreurs de classifieur.
Elle ne valide pas une absence d'incident réseau à elle seule.

### Deux mécanismes indépendants de perturbation Unbound

**1. Cycle quotidien pfBlockerNG/DNSBL — stop/start journalisé.**
Le relevé pfSense du 25 octobre à 20:27 CET contient maintenant
des marqueurs directs **émis par pfBlockerNG** :

| Date et contexte local du bloc pfBlockerNG | Stop Unbound | Start Unbound |
| --- | --- | --- |
| 22 octobre 2026 | 00:04:01 | 00:04:18 |
| 23 octobre 2026 | 00:04:12 | 00:04:25 |
| 24 octobre 2026 | 00:04:38 | 00:04:59 |

Il s'agit d'**heures d'en-tête de bloc**, pas obligatoirement
de l'instant exact de l'appel. Cependant, les marqueurs explicites
`pfblocker_unbound_stop_marker` et
`pfblocker_unbound_start_marker` démontrent que les mises à jour
pfBlockerNG demandent bien des arrêts/démarrages du résolveur.
Ce n'est plus seulement une corrélation avec la sortie du module
`pfb_unbound.py`. La cause de l'utilisation de la voie
`pfb_stop_start_unbound` plutôt que d'un rechargement sans arrêt
n'est **pas établie** pour chaque mise à jour.

**2. OOM système — interruption forcée confirmée.**
Le noyau a tué explicitement Unbound les **17, 22 et 24 octobre**.
Les 16 enregistrements OOM distincts sur 7 minutes concernent
plusieurs processus, pas 16 redémarrages Unbound.
Le cron Snort à 02:09 est temporellement proche des kills vers
02:10, mais **le processus responsable du pic global RAM** reste
non prouvé. CrowdSec, PHP/pfBlockerNG et Snort doivent être
corrélés à leur RSS au moment du pic avant toute remédiation.

**Service Watchdog :** `watchdog_unbound_membership=NOT_LISTED`
lors du relevé. Ne pas l'attribuer aux cycles actuels.

### État des feeds au relevé

- pfBlockerNG principal : **5 erreurs 403/404** et **7 autres
  erreurs** dans la fenêtre conservée.
- Logs ASN/IPinfo : **1 941** signatures `extras` et **1 182**
  dans le journal d'erreur. Ces comptes peuvent inclure des
  événements redondants ; la rétention ne prouve pas un retry actif
  lors du relevé du 25 octobre.
- **64 fichiers DNSBL** et **147 fichiers Snort** inspectés :
  aucun n'atteint les seuils d'alerte du collecteur (16/64 Mio
  pour DNSBL, 64/128 Mio pour Snort).

**Ne pas conclure** que les téléchargements échoués provoquent
chaque restart ou OOM. Ne pas réactiver UT1 Adult, relever la
mémoire PHP, déplacer les crons ou désactiver DNSBL sans un
changement isolé et réversible.

### Priorités de diagnostic restantes

1. Déterminer pourquoi le traitement DNSBL choisit parfois un
   stop/start plutôt que le reload prévu par le code installé
   `pfSense-pkg-pfBlockerNG 3.2.17_1` ; conserver les journaux
   natifs et les marqueurs explicites.
2. Identifier le consommateur à l'origine des OOM vers 02:10 :
   obtenir un échantillon RSS et les événements de téléchargement
   Snort/pfBlockerNG immédiatement avant le pic, sans lancer de
   mise à jour artificielle.
3. Vérifier la **récence** des échecs IPinfo/ASN et HTTP
   plutôt que d'utiliser seulement leurs totaux historiques.

Pour le prochain incident : `just pfsense-feed-pressure-check`,
puis `PFSENSE_OUTPUT=verbose just pfsense-unbound-restart-check`
si les catégories justifient un approfondissement. Ces commandes
restent en lecture seule.

## Investigation suivante — fallback DNSBL et pression RAM Snort

**État observé (25 octobre) :** 39/39 tests locaux reçus comme PASS.
pfBlockerNG `3.2.17_1` émet des marqueurs stop/start Unbound autour
de 00:04 ; le noyau tue Unbound par OOM sur d'autres créneaux vers
02:10. Ces deux mécanismes doivent rester distincts.

### 1. Vérifier les capacités du code pfBlockerNG installé

Depuis un worktree à jour de la PR :

```bash
PFSENSE_OUTPUT=verbose just pfsense-unbound-restart-check
```

Le collecteur rapporte désormais :

- `pfblocker_dnsbl_swap_ram_gate=PRESENT|ABSENT` selon la présence
  de `pfb_unbound_py_swap_fits_ram` dans le code PHP réellement
  installé. Le précédent audit indique ABSENT pour `3.2.17_1` ;
  **le nouvel appel doit le confirmer**.
- `pfblocker_dnsbl_live_reload_marker=PRESENT|ABSENT` selon la
  présence d'un mécanisme de génération/rechargement.
- `pfblocker_dnsbl_fallback_condition=NOT_OBSERVED_AT_RUNTIME` :
  présence de code et appels possibles ne démontrent **pas**
  pourquoi le restart a été choisi le 22, 23 ou 24 octobre.

Le code amont distingue les mises à jour de données pures, les
changements de module/configuration et les échecs de swap. Il n'est
pas garanti qu'il corresponde au code déployé :
<https://github.com/pfBlockerNG/pfBlockerNG/blob/devel/docs/research/unbound-reload-strategies.md>.
Ne pas exécuter `pfb_reload_unbound()` ni modifier les feeds pour
tester ce chemin.

### 2. Mesurer la pression mémoire avant le cron Snort

Le nouvel échantillonneur `scripts/pfsense/sample-oom-pressure.sh`
utilise **une seule session SSH read-only**, sans fichiers ni tâches
sur l'appliance. Il mesure `free + inactive` et des RSS/CPU
regroupés par nom de processus (Unbound, Snort, PHP CLI/PHP-FPM,
helpers pfBlockerNG, CrowdSec, HAProxy et lighttpd_pfb).
Il ne copie jamais les arguments des processus ou les journaux bruts.

**Étape A — vérifier la collecte immédiatement :**

```bash
just pfsense-memory-sample-test
```

```bash
just pfsense-memory-sample
```

**Étape B — mesurer pendant la prochaine fenêtre Snort 02:09**
(pfSense locale Europe/Paris, CET le 26 octobre 2026) :

```bash
just pfsense-memory-window
```

Démarrer cette dernière commande manuellement vers **02:08:30 CET**.
Elle prend **13 échantillons à 15 secondes d'intervalle**,
soit 180 secondes couvrant environ 02:08:30–02:11:30.
Le processus est au premier plan : il n'installe aucun cron, timer
ni service sur pfSense. Si le lancement est tardif, les heures
présentes dans la sortie font foi.

**Étape C — classer avec les OOM et les téléchargements :**

```bash
just pfsense-feed-pressure-check
```

L'analyse doit comparer les heures des RSS/CPU et de la mémoire
disponible aux kills du noyau, ainsi qu'aux échecs de téléchargement
Snort et pfBlockerNG. Un simple pic CPU ou RSS ne suffit pas à
attribuer la cause : les RSS peuvent partager des pages et ne
s'additionnent pas à la RAM physique utilisée.

### Contrats et limites

- Budget : **1 à 16 échantillons**, intervalle **5 à 30 s**,
  durée totale plafonnée à **240 s**. Valeurs invalides refusées
  avant ouverture SSH.
- Mémoire disponible **inférieure à 128 Mio** : avertissement ;
  **inférieure à 64 Mio** : avertissement critique.
- Échec de `sysctl` ou `ps` : code de sortie non nul, diagnostic
  marqué incomplet, pas de fausse classification saine.
- Les échantillons sont **instantanés**. Le script ne prétend pas
  retrouver le RSS exact d'un processus déjà tué.
- Les gardes RAM, budgets et tests ont été validés sur un
  **environnement local simulé (5/5 PASS)**, mais le comportement
  réel sur pfSense reste **NOT_VERIFIED** tant que la commande
  n'a pas été exécutée sur le Netgate.

La gate ciblée de la PR devient **21 contrats Unbound + 19 console
+ 5 échantillonneur = 45 tests**. Les 39 anciens PASS sont attestés
par l'opérateur ; le nouveau total reste NOT_RUN sur le HEAD exact.

Ne pas activer Service Watchdog pour Unbound, déclencher un
rechargement DNSBL, augmenter le PHP memory_limit ni modifier
les horaires Snort pendant l'investigation.

### 3. Comparer les empreintes de configuration avant et après DNSBL

Le collecteur `pfsense-unbound-restart-check` imprime maintenant les
empreintes SHA-256 et métadonnées `size_bytes` / `mtime_unix` de
`unbound.conf` et de deux candidats INI pfBlockerNG lorsqu'ils
existent. Il n'affiche pas leur contenu et ne hache pas les grands
fichiers de données DNSBL. Une absence donne `UNAVAILABLE` ou
`UNVERIFIED`, jamais une fausse empreinte.

Pour la prochaine maintenance DNSBL programmée à 00:00 :

1. Exécuter `PFSENSE_OUTPUT=verbose just pfsense-unbound-restart-check`
   **avant** les travaux (par exemple vers 23:55).
2. Exécuter la même commande **après** les travaux (par exemple
   vers 00:10). Ne pas faire tourner de sonde supplémentaire
   pendant le pic de traitement lui-même.
3. Comparer les champs `config_fingerprint=unbound_config` et
   `config_fingerprint=dnsbl_python_ini|dnsbl_legacy_ini`.
   Une empreinte différente atteste un changement de contenu
   entre ces deux relevés, pas nécessairement la raison exacte
   de la décision stop/start.
4. Si les empreintes restent identiques, considérer les autres
   hypothèses : montage, état du module Python, notification de
   génération ou échec d'un data-swap. **Ne pas conclure**
   à l'absence de changement de configuration hors fichiers
   inspectés.

Le jour 26 octobre 2026, l'échantillonnage Snort à 02:09 est une
investigation distincte ; il ne faut pas mélanger les deux fenêtres.

Les analyses de code sont statiques. Seuls les marqueurs émis par
pfBlockerNG confirment que des demandes de stop/start ont existé.

## Premières mesures réelles mémoire et corrélation configuration / bind

Le 25 octobre 2026, l'opérateur a exécuté la gate complète
`just pfsense-unbound-restart-test` : **45/45 tests PASS**
(21 Unbound, 19 console, 5 mémoire).

### Période mesurée : 21:23:57–21:26:58 CET (hors cron Snort)

Le test ponctuel à 21:23:08 donne 161 408 Kio disponibles.
Sur les 13 mesures suivantes, `free + inactive` varie de
**128 260 à 204 856 Kio (125,3–200,1 Mio)**. Une mesure
(21:24:42) descend **sous 128 Mio** ; aucun échantillon ne
descend sous 64 Mio. La fenêtre ne recouvre PAS le cron Snort
planifié à 02:09 et ne contient pas de journaux OOM du noyau.

| Groupe de processus | RSS min.–max. (Mio) | Interprétation |
| --- | ---: | --- |
| PHP-FPM (8 processus) | 265,5–315,8 | Charge résidente agrégée majeure, variable |
| Unbound | 142,1–144,2 | Stable pendant cette période |
| CrowdSec (2 processus) | 78,0–115,6 | Variations fréquentes |
| Snort | 75,1–85,0 | Généralement 1 processus, un 2e ponctuel |
| PHP pfBlockerNG | 51,5–53,6 | Stable |

Les RSS agrégés peuvent compter plusieurs fois de la mémoire
partagée. Ils ne représentent pas une décomposition de la RAM
physique totale. **Leur variation ne prouve pas qu'un processus
cause la baisse `free + inactive`**. Snort est stable en dehors
de son créneau de mise à jour ; on ne peut donc pas attribuer
l'OOM de 02:10 avec ce seul relevé.

### Nouvelle corrélation forte le 24 octobre à 23:39:55 CEST

La première empreinte jointe à 21:23:27 CET rapporte
`unbound_config mtime_unix=1792877995`, soit **2026-10-24
23:39:55 +02:00**. Le journal système enregistre au **même
second** `unbound_bind_conflict` à
`2026-10-24T23:39:55.370768+02:00`.

Ce rapprochement implique une opération de modification (ou de
mise à jour de mtime) du fichier de configuration au moment
d'une tentative de bind. Il soutient une piste de génération
de configuration et/ou de démarrages concurrents. Il **ne prouve
pas** que pfBlockerNG, configd, l'UI ou un autre composant
ait initié cette modification : l'horodatage et le message
du noyau ne portent pas l'identité du déclencheur.

Le collecteur inclut maintenant `mtime_local` avec son offset
UTC en complément de `mtime_unix`, pour éviter les erreurs de
corrélation autour du changement d'heure. Les empreintes
avant/après la mise à jour de minuit restent nécessaires.

### Rendu du sampler — protection de preuve

Le rendu console fournit désormais un **bilan min/max de la
fenêtre, le nombre de mesures sous 128 et 64 Mio**, et
affiche `Historical OOM events NOT_EVALUATED` : le sampler
n'interroge pas les journaux OOM. Il ne doit jamais afficher
`0 distinct historical OOM records` comme conclusion.

Si une collecte `ps` ou `sysctl` échoue, ou si un nombre de
mesures inférieur au budget est reçu, le résumé indique
`EVIDENCE INCOMPLETE` au lieu de déclarer un résultat sain.

**Prochaine preuve :** un prélèvement encadrant réellement
**02:09–02:11**, plus une comparaison des empreintes vers
23:55/00:10. Ne pas provoquer ces événements par un update
forcé ou un reload manuel.

La gate courante regroupe **21 tests Unbound + 22 tests console
+ 5 tests échantillonneur = 48 tests**. Les 45 tests précédents
sont PASS selon l'opérateur ; les trois nouveaux cas console
restent à valider sur le HEAD actuel.

## Baseline avant minuit du 25/10 — reçue à 23:56 CET

La réception opérateur `just pfsense-php-fpm-postcheck`
à **23:56 CET** a confirmé **Unbound PID 19252** et
`unbound_control=REACHABLE`, avec DNS local/LAN PASS.
Le profil PHP-FPM `4/30/1/2/500` est conservé à
**2 travailleurs nginx**, et `free+inactive=252948 KiB`
(**247,0 Mio**) dans le prélèvement à 23:56:19.

**Empreinte pré-maintenance DNSBL** à conserver pour comparaison
après le cron de 00:00 :

```text
unbound_config size_bytes=2289 mtime_local=2026-10-25T22:46:17+0100
unbound_config sha256=3745a4109d7d9a42cba12a3d0abd77013a3971890e838f9905566a8b94482b44
dnsbl_python_ini=UNAVAILABLE
dnsbl_legacy_ini size_bytes=355 mtime_local=2026-05-18T14:18:05+0200
dnsbl_legacy_ini sha256=b856d9aab131f2796c7e993d6039a3b24cad4a0c5faa0bbd0241582943d403a3
```

Ces valeurs sont des empreintes du **système de fichiers**,
pas de la configuration effective Python résidant en mémoire.
Le compteur `pfblocker.dnsbl_loaded_entries=0` reste **inconnu**
faute de métrique du module, et non preuve que DNSBL est vide.

Le dernier OOM visible dans les journaux collectés reste celui
du **25/10 à 22:12 CET**, avec `php_pfb` à 22:12:38 et
Unbound tué pendant la même minute : il précède le cutover
PHP-FPM. Ne pas utiliser le résumé du sampler (`OOM NOT_EVALUATED`)
pour affirmer qu'aucun OOM plus récent n'existe.

**Étape suivante (lecture seule)** : comparer ces deux
empreintes dans le `pfsense-unbound-restart-check` post-minuit
et vérifier les stop/start réellement journalisés. Aucun
rebuild DNSBL ou restart provoqué artificiellement.