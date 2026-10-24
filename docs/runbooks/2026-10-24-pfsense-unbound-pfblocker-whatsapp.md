# Incident — Unbound / pfBlockerNG / WhatsApp Wi-Fi (24 octobre 2026)

**Statut :** diagnostic en cours. Les 22 tests Akvorado fournis par l'opérateur passent.
Leur résultat ne prouve pas que les flux NetFlow sont écrits dans ClickHouse.
La nuit précédente, Unbound aurait de nouveau cessé de fonctionner. Le
diagnostic actuel n'a pas encore été exécuté sur le pare-feu.

## Worktree après redémarrage workstation

Le chemin `/tmp/nabla-pr274` est temporaire et peut disparaître après reboot.
Un `git -C /tmp/nabla-pr274 fetch` échoue alors immédiatement.
Ne pas coller `set -e` seul dans un terminal interactif : si Git retourne
une erreur, cette option peut fermer le shell courant.

Utiliser **une seule procédure encapsulée dans un enfant Bash**. Elle
récupère le script au SHA exact depuis la branche PR #274 ; le script
vérifie le commit, crée un worktree détaché unique sous
`~/.local/share/nabla/worktrees/pr274-XXXXXXXX`, exécute les tests locaux,
le diagnostic WhatsApp, puis le diagnostic pfSense en lecture seule.
Elle ne change ni le HEAD ni les fichiers locaux `n8n`, `sentry`
ou OpenClaw du checkout principal. La commande fonctionne depuis
n'importe quel répertoire, si `$HOME/w/nabla-compose` existe.

```bash
bash -euo pipefail -c '
  repo="${NABLA_COMPOSE_REPO:-$HOME/w/nabla-compose}"
  branch="fix/homelab-operator-diagnostics-followup-20261024"
  git -C "$repo" -c submodule.recurse=false fetch \
    --no-tags --no-recurse-submodules origin \
    "+refs/heads/$branch:refs/remotes/origin/$branch"
  sha="$(git -C "$repo" rev-parse --verify "refs/remotes/origin/$branch^{commit}")"
  git -C "$repo" show "$sha:scripts/workstation/run-pr274-after-reboot.sh" |
    NABLA_COMPOSE_REPO="$repo" NABLA_PR274_EXPECTED_SHA="$sha" \
      bash -s -- --check --with-pfsense
' || printf '%s\n' 'Échec de diagnostic : terminal conservé, aucun déploiement.'
```

Ne jamais effectuer `git reset --hard`, `git clean`, `git pull` dans
le checkout principal ou de suppression forcée d'un worktree modifié
pour résoudre une erreur `/tmp`. Le script utilise `flock` et un
SHA épinglé ; chaque exécution crée un worktree persistant distinct.
Il n'installe rien. Pour uniquement préparer le worktree, utiliser
`--prepare-only` à la place de `--check --with-pfsense` après le
bootstrap. Les tests Git simulés du script n'atteignent ni pfSense
ni GitHub.

## Reprise validée : le pin SHA ne doit pas contaminer les tests

L'opérateur a exécuté le bootstrap depuis la workstation après reboot.
Il a créé un worktree privé sur le HEAD `efa16afc`, puis les contrôles
Unbound/pfBlockerNG ont réussi (**11/11**) et les tests pflow/WhatsApp
ont réussi (**6/6**).

Les trois échecs de `test_pr274_worktree_recovery.py` provenaient
de l'environnement du bootstrap : `NABLA_PR274_EXPECTED_SHA` était
hérité dans les faux dépôts Git créés par les tests, dont les SHA sont
nécessairement différents. Le garde-fou refusait à juste titre ces SHA.

Le correctif comporte deux protections complémentaires :

1. Le script `run-pr274-after-reboot.sh` vérifie d'abord
   `NABLA_PR274_EXPECTED_SHA` face au HEAD de la PR, puis supprime
   cette variable de l'environnement **avant** d'exécuter `just`.
2. Les tests de récupération suppriment tout pin réel hérité dans
   l'environnement de leurs dépôts simulés. Les tests dédiés à la
   validation du pin restent actifs ; un mauvais SHA continue à
   déclencher `exit 2`.

**Validation locale :** 9/9 tests hors réseau réussis, même avec
`NABLA_PR274_EXPECTED_SHA` défini comme dans la session opérateur,
et `bash -n` réussi. La quality gate complète et le dernier
diagnostic sur pfSense restent à exécuter depuis la workstation.

## Risques et précédents

Le Netgate 1100 est limité en mémoire. L'incident du 8 octobre
(`docs/incidents/2026-10-08-pfsense-unbound-oom-wan-exposure.md`) montre
plusieurs OOM du noyau touchant Unbound/PHP et un job pfBlockerNG ASN/IPinfo.
La stabilisation précédente était autour de **190 804 entrées DNSBL** et
**108–111 Mio RSS pour Unbound**, contre ~923 534 entrées et 330–340 Mio
avant réduction. Ces nombres sont des références historiques, pas une mesure
du 24 octobre ni une limite universelle.

Politique à préserver : pfBlockerNG DNSBL **Python**, ASN Reporting désactivé
sans contrat IPinfo, TLD désactivé, catégories UT1 et feed cassés désactivés,
PHP `memory_limit=128M`, absence de Service Watchdog sur Unbound, CrowdSec
engine non redémarré sans justification, aucune opération de collecte
lourde sur Netgate. Conserver pfSense/Unbound comme DNS principal Talos ;
Pi-hole est une dépendance optionnelle.

## Preuves réelles du 24 octobre — diagnostic opérateur à 19:31 CEST

Le noyau a tué `php` à **02:10:47**, `netstat` à **02:10:49**,
`unbound` à **02:10:50** et `php_pfb` à **02:10:51** :
`failed to reclaim memory`. La récurrence autour de 02:10
est documentée les 17, 21, 22, 23 et 24 octobre. La dernière mise à jour
pfBlockerNG était terminée vers **00:09** : elle ne coïncide pas directement
avec l'OOM de 02:10. Corréler d'abord les tâches cron (Snort, pfBlockerNG,
autres scripts) à **02:10**, avant d'accuser le reload DNSBL de minuit.

Le moteur **CrowdSec est de nouveau actif** (RSS environ 79 676 KiB), en
contradiction avec la politique de stabilisation du 08/10. Le bouncer est
distinct. Examiner qui a redémarré le moteur et si ses événements
`pf-scan-multi_ports` présentent encore une boucle CPU ; arrêter
le moteur uniquement après revue et autorisation, sans arrêter le bouncer
par association automatique.

État lors du diagnostic : Unbound **1.26.1**, RSS ~129 Mio,
fonctionne depuis 09:36 ; l'appliance dispose d'environ 234 Mio libres +
inactifs dans l'échantillon. Ces mesures ne démontrent pas une marge
suffisante lors des jobs nocturnes. L'historique inclut aussi des
`bind: address already in use` le 22 octobre, qui peuvent signaler
des redémarrages concurrents.

**pflow :** `pflowctl` a confirmé `version 5 domain 1 src
172.17.0.1 dst 172.17.0.24:2055`. L'audit exigeait à tort v10 et
un deuxième exporteur Cloudflare. Il accepte à présent la configuration
v5 unique pendant la stabilisation. Cela ne prouve pas de lignes Akvorado.

**Akvorado :** relevé 30 s : `delta_received_flows=6`,
`delta_metadata_missing=6`, `delta_clickhouse_batches=0` ;
le pipeline est `BLOCKED_METADATA_MISSING`.
Corriger les métadonnées de l'exporteur dans la configuration Akvorado
effective après stabilisation pfSense, puis vérifier les insertions SQL.

**WhatsApp :** lenteur sur Wi-Fi rapportée, mais **aucune preuve de
DNSBL WhatsApp bloqué** à ce stade. Utiliser
`scripts/workstation/diagnose-whatsapp-web-path.sh --check` sur
la workstation affectée ; comparer avec un second réseau. Ce script
n'extrait ni cookies, ni contenu WhatsApp, ni HAR authentifié.

## Preuves complémentaires du 24 octobre à 20:01

Le diagnostic opérateur montre une tâche cron **Snort à la minute 09
des heures 02 et 14** (`cron_minute=9 cron_hour=2,14`). Le premier
processus tué par manque de mémoire le 24/10 apparaît à **02:10:47**.
Cette proximité temporelle rend la tâche Snort prioritaire pour l'enquête,
mais ne prouve ni la consommation mémoire de ce processus ni la
responsabilité de Snort. Vérifier ses journaux et sa commande exacte
en privé avant toute désactivation ou modification de l'horaire.

La dernière mise à jour pfBlockerNG s'est terminée à 00:09:08, environ
deux heures avant le nouveau groupe OOM. DNSBL Python fonctionne et
`pfb_unbound.py` est chargé. Les entrées DNSBL affichées sont 225631
sur le marqueur `PASSED`. La sortie précédente
`pfb_py_count=0` ne démontre pas que la base DNSBL est vide.

Le diagnostic CrowdSec comportait une erreur de syntaxe `awk`,
à présent corrigée dans la branche. Le relevé des processus
montre néanmoins **CrowdSec engine RSS 81872 KiB**, tandis que
le bouncer utilise environ 9316 KiB. Ces deux services ne doivent
pas être confondus.

Le premier script imprimait aussi les caractères littéraux `\\n`
au lieu de séparateurs de lignes pour les crons et les feeds, et
imprimait `\\1` pour `python-script:`. Ces problèmes de
présentation sont corrigés. La liste des feeds enregistrée avant
correction ne doit pas être considérée comme un classement `top 10`.

**WhatsApp DNS :** `whatsapp.com`, `web.whatsapp.com`,
`static.whatsapp.net` et `mmg.whatsapp.net` produisent des
réponses `NOERROR` sur Unbound et sur le résolveur de contrôle.
Leurs adresses peuvent varier selon le CDN. Cela n'exclut pas
un blocage d'un autre domaine, un problème IPv6 ou UDP, ni
la saturation transitoire d'Unbound à 02:10.

## Relevé workstation du 24 octobre — tests et comparaison réseau

L'opérateur a exécuté `just pfsense-unbound-wifi-test` sur le
checkout `da07b8a7` : **15/15 tests réussis**, et les trois validations
`bash -n` sont passées. Ces résultats ne couvrent pas les modifications
du HEAD suivantes.

`just whatsapp-web-path-check` a fourni deux réponses DNS
`NOERROR` avec `a_records=1` pour `web.whatsapp.com` et
`static.whatsapp.net`, aussi bien sur **pfSense `172.17.0.1`**
que sur **Quad9 `9.9.9.9`**. HTTPS fonctionne en IPv4
(HTTP 200 sur WhatsApp Web, HTTP 404 sur la racine du site statique).
L'IPv6 n'est pas utilisable depuis cette workstation.
Le résolveur annoncé par la workstation est Quad9, pas pfSense.
Ne pas attribuer automatiquement ces observations au téléphone : le
mobile peut avoir un DNS, un VLAN, une adresse IPv6 et un trajet
réseau distincts.

Le diagnostic pfSense de la PR classe désormais les crons Snort
**`snort_rules_update`** et **`snort_housekeeping`** séparément.
Il ne publie que le type de tâche, l'heure planifiée et les
métadonnées de fichiers journaux d'update. Il ne lit ni les règles
Snort ni les paramètres de téléchargement. La documentation Netgate
prévoit un horaire de vérification configurable des règles Snort :
[Snort Global Settings](https://docs.netgate.com/pfsense/en/latest/packages/snort/setup.html).
Contrôler si la tâche à 02:09 est une mise à jour de règles
avant d'envisager un changement.

Comparer, en lecture seule, les exécutions **02:09** et **14:09**
aux horodatages de fin des mises à jour et aux OOM. Une proximité
d'une minute ne suffit pas à établir le processus responsable.
Ne pas lancer une mise à jour Snort en direct comme test sur ce Netgate
contraint en mémoire.

## P0 — Collecter avant toute réparation

Depuis la workstation autorisée et son alias SSH **déjà configuré** :

```bash
bash scripts/pfsense/diagnose-unbound-crash-memory.sh --check
```

```bash
bash scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh --check
```

```bash
bash scripts/pfsense/audit-posture.sh --ssh home.albandrieu.com --strict
```

```bash
bash scripts/pfsense/diagnose-recover.sh --check
```

Enregistrer les résultats dans un emplacement privé, **pas** dans la description
de PR. Ne pas transmettre les contenus de `config.xml`, les domaines consultés
par les clients, les tokens ni les captures de paquets. Chaque commande est
une action indépendante.

### Interpréter les résultats

| Preuve | Diagnostic plausible | Action différée |
| --- | --- | --- |
| Kernel `failed to reclaim memory` peu avant la mort d'Unbound | OOM global, pas un crash applicatif ordinaire | Réduire les contributeurs RSS et jobs simultanés avant relance contrôlée |
| pfBlockerNG DNSBL update + pic PHP/Unbound au même moment | Rebuild DNSBL trop coûteux | Comparer tailles de sources et planification ; ne pas forcer un reload complet |
| Tentatives IPinfo sans base ASN/token | Boucle ASN réapparue | Vérifier si `asn_reporting` a été réactivé ; corriger via UI/backup seulement après preuve |
| Erreur `address already in use` après plusieurs starts | Course au démarrage, possible watchdog | Vérifier watchdog avant correction |
| Unbound actif, mais `whatsapp.net` échoue uniquement via @127.0.0.1 | Résolution DNSBL ou configuration Unbound suspecte | Lire rapports DNSBL de l'hôte précis, revoir la règle/source correspondante |
| DNS public et Unbound résolvent ; WhatsApp lent en Wi-Fi seulement | PF IPv6/UDP, AP, roaming, MTU, DHCP ou application | Comparer Wi-Fi et 4G/5G avec le même message, puis firewall states |
| DNS Unbound et externe échouent tous les deux | Résolution WAN ou routage | Vérifier pfSense WAN/DNS et connectivité amont avant pfBlockerNG |
| Métriques DNS normales mais problème en appel/vidéo seulement | Voie temps réel UDP, QoS ou Wi-Fi | Diagnostiquer les flux autorisés, sans ouvrir tous les ports |

Les réponses `NXDOMAIN`, `0.0.0.0`, une IP de blocage DNSBL ou un timeout
n'ont pas la même signification. Comparer `whatsapp.com`,
`web.whatsapp.com`, `static.whatsapp.net` et `mmg.whatsapp.net` ;
certaines réponses négatives peuvent être normales selon le nom testé.
Une requête `@1.1.1.1` qui échoue n'est pas une preuve de blocage : le WAN
peut interdire le DNS externe.

## Décisions correctives proposées après le relevé de 22:30 — 24 octobre 2026

**Preuve opérateur, pas reproduction en laboratoire :** le noyau a tué
Unbound, PHP et `php_pfb` avec `failed to reclaim memory` plusieurs
nuits. Les pannes sont proches de `02:10` les 17, 21, 22, 23 et 24
octobre ; une autre s'est produite le **22 octobre à 22:03**.
Le cron existant prévoit :

| Tâche déclarée | Horaire | Correspondance aux incidents |
| --- | --- | --- |
| Snort `snort_rules_update` | 02:09 et 14:09 | Cinq événements autour de 02:10 : **forte corrélation temporelle**, pas causalité prouvée |
| pfBlockerNG | 00:00, 04:00 et 22:00 | OOM du 22/10 à 22:03 : seconde corrélation à confirmer |
| pfBlockerNG mise à jour terminée | 24/10 00:09:08 | Pas de chevauchement direct avec l'OOM de 02:10 |

Le fichier `snort_rules_update.log` était modifié à **14:09:09** le
24 octobre, cohérent avec le passage de la tâche à 14:09. Cela
ne démontre pas son pic RSS à 02:09.

**Photographie mémoire à 22:30, KiB RSS** : Unbound 132 708,
CrowdSec engine 77 368, Snort 59 692 ; bouncer CrowdSec 9 300.
Au moins sept workers `php-fpm: pool nginx` étaient visibles
(29 936 à 43 576 KiB chacun). Leur RSS ne doit pas être additionné
comme de la RAM physique unique : les pages peuvent être partagées.
L'échantillon affichait `v_free_count=51316` et
`v_inactive_count=7707` (pages de 4096 octets, environ 230 Mio
libres + inactifs). Il ne représente pas le creux de 02:09.

**pfBlockerNG** : DNSBL Python chargé, TLD désactivé, test DNS
WhatsApp `NOERROR`. Le marqueur DNSBL `225631 | PASSED` et
`pfb_unbound.py` environ 11,8 Mo sont des faits historiques du
24 octobre. Les fichiers `Gambling.orig` ou `EasyList.orig` présents
sur disque **ne prouvent pas qu'un feed est activé**.
Ne supprimer aucun fichier de cache sur la seule base de sa taille.

### Plan d'atténuation ordonné, sans mutation automatique

1. **P0 — Enquêter sur la mise à jour Snort à 02:09.**
   Comparer les horodatages de début/fin de mise à jour, les
   ressources de processus enfants, les erreurs et les éventuels
   rechargements de règles au moment exact de l'OOM.
   L'interface pfSense classique expose le réglage dans
   `Services > Snort > Global Settings > Rules Update Settings`
   (Update Interval / Update Start Time). Après sauvegarde, et
   **seulement sur autorisation**, proposer une fenêtre supervisée
   ou un passage temporaire à une mise à jour quotidienne. Cela
   modifie la fraîcheur des signatures et ne garantit pas
   qu'un pic mémoire sera résolu.

2. **P0 — Revoir CrowdSec engine séparément du bouncer.**
   Vérifier pourquoi le moteur s'est réactivé et le coût de son
   traitement. L'arrêt ou le déplacement du moteur pourrait
   libérer une partie du RSS observé, mais peut interrompre la
   production de nouvelles décisions. Vérifier d'abord la source
   des décisions du bouncer et les protections de remplacement.
   Ne pas arrêter les deux services ensemble, ni créer une règle
   firewall large pour compenser.

3. **P0 — Vérifier la tâche pfBlockerNG de 22:00.**
   Corréler le `22:03` du 22 octobre, contrôler durée et taille de
   chaque reconstruction, et confirmer la configuration
   `DNSBL Python`, `TLD OFF`, et l'état réel `ASN/IPinfo`
   (un champ absent dans le diagnostic n'est pas une confirmation
   de désactivation). Préserver les protections utiles.
   Replanifier ou espacer les jobs coûteux **après** les observations
   et avec approbation. Ne pas lancer un `Force Reload` pendant
   l'investigation.

4. **P1 — Contrôler la concurrence PHP-FPM et la mémoire temporaire.**
   Lire les compteurs agrégés `php_fpm_workers`,
   `php_fpm_max_worker_rss_kb`, `df -k /tmp /var`,
   la configuration actuelle du pool et les événements PHP
   autour de 02:09. Conserver le `memory_limit=128M` déjà
   défini : l'augmenter risquerait d'aggraver le manque de RAM.
   Ne pas redimensionner les RAM disks sans mesure et budget.

5. **P1 — Conserver Unbound stable.**
   Les caches `msg-cache-size: 4m` et `rrset-cache-size: 8m`
   sont déjà bornés. Ne pas augmenter `kern.ipc.maxsockbuf` sur
   la base d'un avertissement isolé, ni démarrer plusieurs Unbound
   en parallèle à cause de `address already in use`.
   Conserver `Service Watchdog` absent, sans redémarrage
   automatique pendant la collecte de preuves.

**Conditions d'acceptation :** une sauvegarde `config.xml` validée,
une seule modification à la fois, possibilité de rollback et suivi des
prochaines exécutions aux mêmes horaires. Le succès nécessite l'absence
de nouveaux `failed to reclaim memory`, la disponibilité d'Unbound
et les protections Snort/pfBlockerNG toujours effectives.

Références Netgate :
[Snort Global Settings](https://docs.netgate.com/pfsense/en/latest/packages/snort/interfaces-global.html),
[PHP Memory Limit et RAM disks](https://docs.netgate.com/pfsense/en/latest/config/advanced-misc.html),
[Memory Management](https://docs.netgate.com/pfsense/en/latest/hardware/memory.html).

## P0 — Optimisations pfBlockerNG conditionnelles

1. Mesurer le nombre d'entrées DNSBL réellement chargées et les plus grosses
   sources, sans lire ni publier les entrées.
2. Comparer la planification des jobs de pfBlockerNG, Snort et CrowdSec aux
   horodatages exacts de l'OOM.
3. Vérifier que DNSBL Python est toujours le mode effectif dans le
   `/var/unbound/unbound.conf` **généré**.
4. Conserver désactivés ASN/IPinfo sans source valide, UT1 adult/malware/
   gambling/games/dating/phishing si leur remplacement était approuvé,
   les feeds Cisco Talos 403 et les catégories sources disproportionnées.
5. Réduire un feed **seulement** si son coût ou ses faux positifs sont
   démontrés. Garder les catégories de protection utiles.
6. Pour WhatsApp, corriger **seulement** la règle DNSBL qui bloque un domaine
   nécessaire et confirmé, avec entrée de suppression ou permit list
   minimale. Ne pas autoriser globalement `*.whatsapp.net` par défaut,
   et ne jamais désactiver tous les filtres de sécurité en première intention.
7. Confirmer l'absence de nouveau OOM, la stabilité du RSS Unbound et la
   résolution DNS pendant au moins une plage incluant l'horaire nocturne
   incriminé avant de fermer l'incident.

Ne pas lancer `Force Reload` ou redémarrer Unbound pendant la collecte des
preuves. Si le service reste indisponible, prévoir une intervention séparée
avec sauvegarde de `config.xml`, seuil mémoire, approbation et rollback.
Ne pas modifier les fichiers générés à la main.

## Workstation WhatsApp Web : comparaison Quad9 / pfSense (24 octobre)

L'opérateur a constaté depuis la workstation :
- DNS système : Quad9 `9.9.9.9` / `149.112.112.112`, et non Unbound sur l'interface observée.
- `web.whatsapp.com` : IPv4 HTTP 200, TLS ~16 ms, réponse totale ~168 ms.
- `static.whatsapp.net` : IPv4 HTTP 404 sur `/` ; transport TLS accessible.
- IPv6 : `000`/échec immédiat sur les deux domaines. Ne pas en conclure
  un dysfonctionnement WhatsApp : vérifier l'IPv6 réellement déployé.

**Le script workstation compare désormais les réponses DNS** sur
`172.17.0.1` et `9.9.9.9` pour les deux hôtes Web.
Il imprime seulement le code DNS et le nombre d'adresses IPv4.
La comparaison est en lecture seule, bornée et facultative quand `dig`
n'est pas disponible. Elle ne change pas le DNS de la workstation.

```bash
just whatsapp-web-path-check
```

Les essais HTTPS réussis ne valident pas l'envoi des messages, la
connexion WebSocket authentifiée, ni le DNS configuré sur le mobile.
Comparer Wi-Fi / données mobiles sans exporter de HAR contenant
cookies ou tokens. Si la comparaison DNS est `unknown` uniquement
avec pfSense, vérifier le chemin DNS et la politique de firewall
avant de modifier une liste pfBlockerNG.

## Vérifications côté téléphone

- Vérifier si **le même message WhatsApp** part rapidement en 4G/5G et
  lentement sur le Wi-Fi domestique, à quelques minutes d'écart.
- Vérifier si le mobile reçoit bien pfSense/Unbound comme DNS, ou Pi-hole,
  DoH/Private DNS, le résolveur d'un VPN ou un relais IPv6.
- Vérifier si seules les pièces jointes/appels ralentissent (UDP, MTU)
  ou si les simples messages texte sont touchés (DNS/connectivité).
- Vérifier le SSID, le VLAN, la bande 2,4/5 GHz et le RSSI près de la borne
  sans changer en même temps DHCP, filtrage et Wi-Fi.
- Ne pas comparer des horodatages sans vérifier les horloges du mobile,
  de l'AP et de pfSense.

## P1 — Akvorado après stabilité du pare-feu

```bash
python3 scripts/truenas/diagnose-akvorado-flow.py --strict --fail-on-blocked --observe-seconds 30
```

```bash
python3 scripts/truenas/diagnose-akvorado-flow.py --strict --require-inserts --observe-seconds 30
```

Le script vérifie de nouvelles insertions par compteur et ne prouve pas
à lui seul de lignes ClickHouse. Valider les lots via une requête bornée,
en lecture seule et avec une identité SQL dédiée. Conserver la configuration
statique de l'exporteur `172.17.0.1/32`, `ifIndex=11` jusqu'à vérification
du mapping exact et de la version de l'image. Ne pas élargir les règles
`Always Track Flow Data` pendant un incident de mémoire pfSense.

## Critères de fermeture

**pfSense :** aucun OOM récent, RSS et mémoire suffisants, Unbound
répond normalement, pfBlockerNG a terminé sa mise à jour nocturne sans
répétition ASN/IPinfo.

**Wi-Fi :** messages texte, médias et appels passent normalement sur le
même téléphone avec le DNS attendu, sans autorisation large.

**Akvorado :** nouveaux lots ClickHouse, lignes récentes vérifiées en SQL
et données visibles dans la Console ; aucune métrique cumulée prise comme
preuve d'un flux récent.
