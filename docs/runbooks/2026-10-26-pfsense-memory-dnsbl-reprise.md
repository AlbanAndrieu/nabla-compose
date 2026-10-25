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
