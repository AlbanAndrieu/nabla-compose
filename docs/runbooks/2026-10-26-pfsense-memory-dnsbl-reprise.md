# pfSense Netgate 1100 — Reprise différée : DNSBL, OOM et mémoire

**État au 26 octobre 2026, 00:26 CET. PR :** https://github.com/AlbanAndrieu/nabla-compose/pull/280

## Décision de sécurité

Ne rien redémarrer ni reconfigurer pour cette reprise documentaire. Conserver PHP-FPM `4/30/1/2/500`, Snort WAN AC-BNFA et HTTP Inspect 32 Mio, et les blocages DNSBL utiles. Ne pas réappliquer le patch PHP-FPM. L'état du bouncer CrowdSec reste à confirmer : le moteur a continué de fonctionner après son arrêt manuel.

## Historique fiable et hypothèse « les changements ont créé l'incident »

| Quand (Paris) | Fait | Portée de causalité |
| --- | --- | --- |
| 16–24/10 | OOM noyau multiples, kills Unbound confirmés 17/22/24 | **Avant** le profil PHP-FPM à 4 workers |
| 22–25/10 ~00:04 | Journaux pfBlockerNG avec marqueurs stop/start d'Unbound | **Avant** l'intervention PHP-FPM du 25/10 |
| 24/10 23:39:55 CEST | `unbound.conf` mtime aligné sur conflit de bind | Initiateur encore inconnu |
| 25/10 22:12 CET | OOM tue Unbound et `php_pfb` | **Avant** l'intervention PHP-FPM |
| 25/10 22:46 | Unbound redémarré manuellement, PID `19252` | Modification du point de départ de l'enquête |
| 25/10 ~23:40 | Générateur et pool PHP-FPM `8/3600/2/7/5000` → `4/30/1/2/500` ; sortie native `[: NaN: bad number` | Bascule confirmée, moteur des warnings non identifié |
| 25/10 23:56 | 2 enfants nginx, mémoire disponible 247,0 Mio ; PID Unbound 19252 | Baseline *avant* cron DNSBL |
| 26/10 00:04 | pfBlockerNG rapporte stop puis start ; module DNSBL sort à 00:04:30 ; **nouveau PID 2611 à 00:04:32** | Cycle stop/start corrélé, pas OOM |
| 26/10 00:12 | Unbound Control REACHABLE ; hashes `unbound.conf` et INI legacy inchangés ; 167,1 Mio libres/inactifs | Aucune durée de coupure DNS mesurée |
| 26/10 | 65 tests initiaux puis 56 tests Unbound de la nouvelle suite PASS opérateur | Contrats offline, pas preuve runtime continue |

**Lecture causale :** les OOM et stop/start existaient déjà avant le changement PHP-FPM du 25 octobre. Il n'a donc pas créé leurs premiers épisodes. Cependant, l'optimisation PHP-FPM, les réglages pfBlockerNG/Snort précédents, le redémarrage manuel d'Unbound, l'arrêt du firewall bouncer CrowdSec ou des mises à jour de packages ont pu modifier la pression mémoire, la durée des interruptions et les alertes. Les dates précises et diffs des autres modifications restent à retrouver avant d'attribuer une régression.

**Hypothèses ouvertes :** (1) pfBlockerNG 3.2.17_1 choisit stop/start au lieu d'un data-swap sans interruption ; fonctions présentes mais condition runtime inconnue. (2) OOM 22:12 avec `php_pfb` victime après cron pfBlockerNG 22:00, causalité du cron non prouvée. (3) Snort cron 02:09 proche d'anciens OOM, consommation réelle au moment du kill inconnue. (4) CrowdSec bouncer arrêté : réduction potentielle de charge et de couverture non isolée. (5) Warning natif PHP-FPM NaN : origine non démontrée.

## Erreur du comparateur et correctif

Le runbook précédent présentait `/tmp/unbound-before.log` et `/tmp/unbound-after.log` comme **exemples**. `just pfsense-unbound-compare` ne les créait pas. L'échec `ERROR: unbound_comparison_incomplete: ValueError` ne donne pas la cause réelle : fichiers absents/vides, non conformes, identiques ou dates inversées sont possibles. Aucun de ces défauts ne prouve un problème pfSense.

Le comparateur corrigé produit désormais un `reason=` explicite et un `hint=` sûr, **sans imprimer les chemins ni le contenu** : `before_file_missing`, `after_file_empty`, `reports_same_timestamp`, `reports_out_of_order`, `before_missing_pfSense_time`, `after_missing_unbound_pid`, `*_collector_incomplete`, etc.

## Procédure sûre pour un prochain cycle de minuit

Depuis la workstation, dans la branche actualisée :

1. Vérifier les tests offline : `just pfsense-unbound-restart-test`.
2. Avant le cron : `just pfsense-unbound-capture`. Relever le **chemin réel** imprimé `snapshot_saved=...`.
3. Après le cron (par exemple vers 00:10) : **relancer** `just pfsense-unbound-capture`. Relever le **deuxième chemin**, différent.
4. Comparer : `PFSENSE_BEFORE="<premier-chemin>" PFSENSE_AFTER="<deuxième-chemin>" just pfsense-unbound-compare` (remplacer les chevrons par les chemins fournis).
5. Reporter dans H-04 les changements PID, les empreintes et les OOM **postérieurs** à la première capture. Un match SHA-256 ne prouve pas que les listes chargées en mémoire sont restées identiques.
6. Supprimer manuellement les deux rapports lorsqu'ils ne sont plus utiles.

La capture SSH est read-only. Elle crée un fichier privé mode `0600` dans un dossier local `0700` sous `${XDG_STATE_HOME:-$HOME/.local/state}/nabla/pfsense-unbound` (personnalisable avec `PFSENSE_UNBOUND_SNAPSHOT_DIR`). Les captures incomplètes sont supprimées ; aucune collecte n'est lancée en arrière-plan.

Il est **impossible de reconstituer** la baseline réelle du 25/10 à 23:56 en lançant une capture aujourd'hui. Si les rapports complets n'ont pas été sauvegardés, conserver les faits prouvés dans ce runbook et comparer deux prochains relevés réels.

## Ordre des investigations à la reprise

1. **Préflight** : `just pfsense-php-fpm-postcheck`, lecture seule. Contrôler Unbound, profil PHP-FPM, CrowdSec moteur/bouncer, DNS public/privé, GUI HTTPS et pfREST depuis source LAN autorisée.
2. **Cycle DNSBL** : comparer les captures pré/post ; mesurer la disponibilité DNS depuis un client LAN durant ~00:04 sans sonde supplémentaire sur le Netgate ; rechercher le chemin effectif `pfb_reload_unbound` / `pfb_stop_start_unbound`, journal configd et changements de package.
3. **OOM** : `just pfsense-memory-window` lancé avant 02:09 pour relever RAM/RSS puis `just pfsense-feed-pressure-check` pour les erreurs de téléchargement. Distinguer le dernier OOM **historique** d'un kill **après** la baseline.
4. **Regressions de changements** : comparer version pfBlockerNG/Unbound/Snort, fichiers de sauvegarde et modifications DNSBL, pfSense, Cron, Snort, CrowdSec et PHP-FPM aux dates des premiers symptômes ; ne pas confondre corrélation et causalité.
5. **Correction isolée** : choisir une seule modification après preuve, avec test avant/après, acceptation DNS LAN et rollback documenté. Ne pas désactiver toutes les protections pour gagner de la RAM.

## Critères de clôture / rollback

État désiré : aucun nouvel OOM noyau d'Unbound sur des cycles documentés, interruption DNSBL mesurée et maîtrisée, marge RAM ordinaire ≥128 Mio (seuil opérationnel non garanti), profil PHP-FPM 4 workers, accès HTTPS/pfREST, DNS privé, Snort WAN et protections CrowdSec/pfBlockerNG vérifiées.

Le rollback PHP-FPM existe : `PFSENSE_PHP_FPM_CHANGE_CONFIRM=RESTORE_BACKUP just pfsense-php-fpm-restore`. **Ne pas l'exécuter pour tester l'hypothèse DNSBL** : les cycles minuit préexistent à la réduction des workers et revenir à huit workers peut accroître le risque d'OOM. Exiger preuve de régression PHP-FPM, console de secours et fenêtre de maintenance.


## Validation réelle des captures — 26 octobre, 00:40 CET

**Retour opérateur :** `just pfsense-unbound-restart-test`
**64/64 PASS** : 21 Unbound, 23 console, 5 sampler,
10 comparateur et 5 capture. Les deux appels
`just pfsense-unbound-capture` ont également réussi :

| Capture | Heure locale dans le nom | Identifiant du fichier |
| --- | --- | --- |
| Premier `snapshot_saved` | 00:40:15 CET | `unbound-20261026T004015+0100.2oWbKT4w.log` |
| Second `snapshot_saved` | 00:40:22 CET | `unbound-20261026T004022+0100.C2Bxl2aQ.log` |

Ces deux fichiers existent sur la **workstation de l'opérateur**
dans `~/.local/state/nabla/pfsense-unbound/`.
Le code vérifie leurs permissions et leur structure ;
leur **comparaison a été exécutée avec succès** par l'opérateur.

**Important :** les deux snapshots ont été pris à 7 secondes
d'intervalle et **après** le cron DNSBL de 00:00 / restart
Unbound de 00:04. Ils peuvent détecter un changement sur
**00:40:15–00:40:22**, mais **ne mesurent pas une transition**
avant/après le cycle DNSBL précédent. Même si les journaux
retiennent les événements de 00:04, ce ne sont pas des
preuves d'une continuité PID sur cet intervalle antérieur.

L'erreur ultérieure `reason=before_file_missing` est **attendue**
avec le placeholder littéral `/chemin/reel/avant.log` :
le script refuse un chemin inexistant. Ce n'est pas une
panne SSH, Unbound ou pfBlockerNG.

### Comparaison des deux vrais rapports existants

Depuis la workstation, **sans relancer le collecteur** :

```bash
PFSENSE_BEFORE="$HOME/.local/state/nabla/pfsense-unbound/unbound-20261026T004015+0100.2oWbKT4w.log" \
PFSENSE_AFTER="$HOME/.local/state/nabla/pfsense-unbound/unbound-20261026T004022+0100.C2Bxl2aQ.log" \
just pfsense-unbound-compare
```

Si `unbound_pid_changed=no`, cela signifie **uniquement** que
le PID est inchangé pendant ces quelques secondes. Il ne
réfute pas le restart antérieur observé à 00:04.

**Prochaine vraie validation DNSBL :** enregistrer le
premier snapshot **avant** un futur cron et le deuxième
**après**, puis corréler les événements d'exécution
avec un contrôle DNS depuis le LAN. Ne pas forcer un
restart Unbound ou un rebuild DNSBL pour créer ce cas.

### Résultat du comparateur — 26 octobre 00:40:15–00:40:22 CET

Comparaison **réellement exécutée** entre les deux fichiers de capture
ci-dessus, sans nouvelle connexion SSH pendant la comparaison :

| Champ de preuve | Résultat opérateur |
| --- | --- |
| Baseline / observation | `2026-10-26T00:40:15+01:00` / `2026-10-26T00:40:22+01:00` |
| PID Unbound | **2611 → 2611** (`unbound_pid_changed=no`) |
| Processus lancé dans cette fenêtre | `unbound_start_in_window=unverified` |
| `unbound_control` final | **REACHABLE** |
| Marqueurs pfBlockerNG stop/start | `no_or_unverifiable` **pour cet intervalle seulement** |
| Sortie DNSBL Python | `no_or_unverifiable` **pour cet intervalle seulement** |
| OOM noyau depuis baseline | `NONE_IN_BOUNDED_VISIBLE_LOGS`, **0 visible**, Unbound 0 |
| `unbound.conf` SHA-256 | **MATCH** |
| INI DNSBL legacy SHA-256 | **MATCH** |
| INI DNSBL Python | **UNKNOWN_MISSING_EVIDENCE** |
| Synthèse | **`NO_PID_CHANGE_IN_THIS_INTERVAL`** |

**Verdict strict :** le résolveur a conservé son PID et répondait
au contrôle au terme des **sept secondes 00:40:15–00:40:22**.
Les empreintes des deux fichiers disponibles concordent.
Aucun nouvel OOM n'est trouvé par le comparateur dans les
**journaux bornés** pour ces sept secondes ; il ne peut
certifier l'exhaustivité de l'historique noyau.

Ce verdict **n'annule pas** le stop/start pfBlockerNG de
**00:04**, confirmé séparément par le passage du PID **19252**
au PID **2611**. Les deux captures ont été prises **36 minutes
après cet événement**. Les marqueurs `no_or_unverifiable`
signifient uniquement qu'ils ne sont pas corrélables à
cette **courte fenêtre**.

**Statut H-04 :** capture automatique, comparaison locale et
contrats (64/64 PASS) validés. L'indisponibilité éventuelle
du DNS pendant les stop/start DNSBL et la cause exacte
du chemin de rechargement restent à investiguer.

Ne pas relancer l'optimisation PHP-FPM et ne pas provoquer
un nouveau cycle pfBlockerNG pour obtenir cette mesure.

## Continuation PR #285 — sonde DNS LAN bornée (à exécuter au prochain cycle)

**Source** : la PR #280 est fusionnée ; le suivi s'effectue
dans [la PR #285](https://github.com/AlbanAndrieu/nabla-compose/pull/285).
Cette PR contient aussi un correctif indépendant du test de
secrets canonique du service Code : vérifier les deux périmètres
avant fusion.

### Pourquoi une sonde supplémentaire ?

Le comparateur local a établi la stabilité du PID 2611
**entre 00:40:15 et 00:40:22 le 26 octobre**.
Il n'a pas mesuré la disponibilité DNS du LAN pendant le
stop/start Unbound associé à pfBlockerNG vers **00:04**.
Les futurs relevés de PID, même encadrant le cron, ne
quantifieront pas seuls les requêtes DNS perdues.

Le nouveau script `scripts/pfsense/probe-unbound-lan-dns.py`
utilise `dig` directement contre l'IP DNS explicite
`172.17.0.1`, depuis un client autorisé sur le LAN.
Il **n'utilise pas** la résolution de la workstation
(`systemd-resolved`) pour rejoindre pfSense.
Il n'ouvre ni SSH, ni API pfSense, et n'installe aucun service.

### Validation locale initiale (hors réseau)

```bash
just pfsense-unbound-lan-dns-test
just pfsense-unbound-restart-test
```

La recette LAN contient maintenant **18 tests offline**,
incluant les scénarios d'IPv4 attendue, Pi-hole et échecs échantillonnés.
La gate Unbound inclut cette recette. Les résultats antérieurs
**73/73 PASS** concernent une version précédente, et ne
valident pas les derniers correctifs. Rejouer les deux recettes
localement ; ne pas annoncer de nouveau total PASS avant exécution.
Le correctif Code déjà présent dans cette PR possède une
gate distincte à valider avant fusion.

### Vérification d'une minute avant la prochaine fenêtre

Choisir un nom privé **réellement résolu en A par pfSense**.
La zone documentée est `int.albandrieu.com`, transmise par
Unbound à Pi-hole sur TrueNAS `172.17.0.24:53`.
Ne plus utiliser `nexus-albanandrieu.int` : ce nom issu d'un
ancien inventaire a renvoyé **45 NXDOMAIN/45** le 26 octobre,
alors que **45/45 requêtes publiques étaient OK**. Il n'avait
pas été vérifié avant la mesure.

Exemple **historique** plus conforme à la topologie :
`s3.int.albandrieu.com` (A `172.17.0.24` dans un diagnostic
antérieur). **Vérifier son état actuel** avant de le retenir :

```bash
dig +tries=1 +time=2 @172.17.0.1 s3.int.albandrieu.com A
dig +tries=1 +time=2 @172.17.0.24 s3.int.albandrieu.com A
```

Si les deux renvoient **l'IPv4 attendue**, depuis la workstation :

```bash
PFSENSE_PRIVATE_DNS_NAME=s3.int.albandrieu.com \
PFSENSE_PRIVATE_DNS_EXPECTED_IP=172.17.0.24 \
  just pfsense-unbound-lan-dns-watch
```

`172.17.0.24` est ici une **valeur historique candidate**.
La vérifier avec `dig` sur les deux résolveurs avant d'exécuter la
recette. Le script impose une IPv4 privée attendue, fournie explicitement,
et ne la déduit jamais de la réponse DNS à vérifier.

Si le premier renvoie `NXDOMAIN` et le second `NOERROR`
avec `172.17.0.24`, examiner le Domain Override Unbound de
`int.albandrieu.com` vers Pi-hole. Si les deux renvoient
`NXDOMAIN`, vérifier la publication du nom côté Pi-hole et
les politiques de filtrage. Ne rien modifier à ce stade.

La recette effectue **45 prélèvements**, espacés au
mieux de **2 secondes**, avec **2 requêtes A par prélèvement**
(une publique `example.com`, une privée fournie par l'opérateur).
Elle s'achève normalement en environ **90 secondes** hors
ralentissements/timeouts et émet `dns_watch_result=...`.
Elle est bornée à 60 prélèvements et à un délai de dig
configurable de 1 à 5 secondes, sans boucle infinie.
**Précontrôle obligatoire :** la résolution publique et la réponse A
privée de pfSense doivent être `OK` ; cette dernière doit contenir
**l'IPv4 explicitement attendue**. Si la réponse privée est invalide,
une troisième requête interroge directement Pi-hole `172.17.0.24` :
- Pi-hole `OK` et pfSense en échec (public `OK`) :
  `SPLIT_DNS_FAILURE` ; vérifier le Domain Override.
- Pi-hole et pfSense sans l'A attendu : `BASELINE_INVALID` ;
  vérifier le nom, la zone et l'IPv4 de référence.
- Échec du nom public au précontrôle : `BASELINE_INVALID` ;
  vérifier la connectivité sans conclure à une panne Unbound.

Dans chaque cas la sonde affiche
`dns_sampling=SKIPPED_INVALID_PREFLIGHT` et sort en **code 2**.
Les prélèvements ne commencent **jamais** sans précontrôle valide.
Un échec au précontrôle ne constitue pas une coupure mesurée
pendant le cron.

**Suivi du 26/10 20:49 CET :** l'opérateur a confirmé
`s3.int.albandrieu.com A=172.17.0.24` sur pfSense
(`NOERROR`, 55 ms) et Pi-hole (`NOERROR`, 0 ms).
La première requête `example.com` du précontrôle a cependant
retourné `TIMEOUT`, tandis que le nom privé était `OK` ;
le script a justement évité 45 mesures sur une baseline publique
non établie. Cet événement ne démontre **ni panne globale Unbound,
ni erreur DNS privée**.

Dans la PR #285, une **seule relance** de la requête publique est
autorisée pour `TIMEOUT`, `SERVFAIL` ou `QUERY_ERROR`.
Si la seconde réponse est `OK`, le script affiche
`dns_preflight_warning=PUBLIC_RECOVERED_AFTER_ONE_RETRY`
et poursuit avec une référence temporairement récupérée :
l'échec initial reste visible. Si les deux échouent alors que le
privé est `OK`, retour code 2 avec
`PUBLIC_DNS_BASELINE_UNAVAILABLE` (pas `BASELINE_INVALID`
du nom privé) et **aucun prélèvement**. Les erreurs
`NXDOMAIN` publiques ne font pas l'objet d'une relance.
Le budget normal est désormais **2 à 4 requêtes de préflight**
(public initial + éventuelle relance, privé pfSense,
éventuel Pi-hole), sans retry pendant les 45 prélèvements.
Les nouveaux tests sont à exécuter localement ; l'opérateur a
validé les **18/18 précédents** et la gate Unbound **82/82**
avant cet ajout.

Le programme effectue **2 à 4 requêtes de précontrôle + 90
requêtes maximum** pendant les 45 prélèvements par défaut.
Le résolveur Pi-hole est interrogé seulement si nécessaire.
Un code retour `1` **après un précontrôle réussi et un
bilan de prélèvements** indique qu'au moins une requête
DNS a échoué pendant la surveillance.

Pour couvrir le cron d'environ 00:04, démarrer la commande
vers **00:03:35–00:03:45**, heure locale du Netgate.
Si le chronogramme pfBlockerNG change, adapter la fenêtre.
Pendant la même fenêtre, ne pas modifier PHP-FPM, Snort,
pfBlockerNG, CrowdSec, Unbound ni les règles DNS.

### Interprétation du résultat

Le script produit pour chaque prélèvement un horodatage
avec offset local, les états `public_dns` et `private_dns`,
les durées de requête, puis des compteurs :
`public_fail`, `private_fail`, `both_fail` et les plus
longues **séquences d'échantillons défaillants**.
Il distingue `OK`, `TIMEOUT`, `NXDOMAIN`, `SERVFAIL`,
`REFUSED`, `NO_A_ANSWER`, `A_MISMATCH`, etc.
Après précontrôle valide : `SPLIT_DNS_FAILURE` signale un échec
privé seul, `DNS_OUTAGE_OBSERVED` signale au moins un prélèvement
où les **deux** requêtes séquentielles ont expiré, et
`DNS_FAILURE_OBSERVED` regroupe les autres échecs.
Cette catégorisation est une observation de prélèvements,
pas une preuve de durée de panne ni d'une cause particulière.

`dns_downtime_seconds=NOT_MEASURED_ONLY_SAMPLED` est
intentionnel. Si la sonde échoue à des instants successifs,
elle démontre des requêtes perdues pendant la fenêtre,
**pas** la durée exacte et continue de la panne. Une absence
d'échec ne prouve pas qu'une microcoupure n'a pas eu lieu
entre deux échantillons. Aucun nom, réponse A ou log
brut n'est imprimé, seuls les états agrégés sont conservés.

### Suite après la sonde

1. Capturer l'état Unbound **avant** le cron avec
   `just pfsense-unbound-capture`.
2. Exécuter la mesure LAN à l'heure approximative prévue.
3. Capturer **après** le cron avec la même recette.
4. Comparer les deux vrais `snapshot_saved` via
   `just pfsense-unbound-compare`.
5. Corréler les horodatages des éventuels échecs DNS
   avec les nouveaux PID, marqueurs pfBlockerNG et OOM.
6. En l'absence de coupure, conserver le stop/start comme
   dette de continuité à surveiller, sans le traiter
   d'office comme une panne utilisateur.

**Aucune action corrective sur l'appliance n'est nécessaire
pour exécuter ou valider ces scripts.**

### Correctif après la mesure du 26 octobre 20:09–20:10 CET

La mesure opérateur avec l'ancien nom `nexus-albanandrieu.int`
a observé **45/45 réponses publiques OK**, **45/45 NXDOMAIN
sur le nom privé**, **aucun timeout**, **aucun SERVFAIL** et
`both_fail=0`. Cela indique qu'Unbound répondait pendant
la fenêtre, mais ne trouvait pas le nom privé interrogé.
Ce test ne couvre pas le cron de **00:04** : la mesure
a eu lieu vers **20:09–20:10 CET**.

La version de la sonde dans la **PR #285** inclut désormais
une vérification préalable. Si le nom privé retourne `NXDOMAIN` dès le départ, la sonde
interroge aussi Pi-hole. Elle retourne `BASELINE_INVALID`
si le nom manque sur les deux résolveurs, ou
`SPLIT_DNS_FAILURE` si Pi-hole possède l'A attendu.
Dans les deux cas, elle **n'échantillonne pas** et ne conclut pas
à une panne temporelle d'Unbound.

L'ancien exemple `nexus-albanandrieu.int` ne doit plus
être proposé pour les contrôles de disponibilité DNS LAN.