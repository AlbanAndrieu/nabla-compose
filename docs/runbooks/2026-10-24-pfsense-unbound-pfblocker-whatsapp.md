# Incident — Unbound / pfBlockerNG / WhatsApp Wi-Fi (24 octobre 2026)

**Statut :** diagnostic en cours. Les 22 tests Akvorado fournis par l'opérateur passent.
Leur résultat ne prouve pas que les flux NetFlow sont écrits dans ClickHouse.
La nuit précédente, Unbound aurait de nouveau cessé de fonctionner. Le
diagnostic actuel n'a pas encore été exécuté sur le pare-feu.

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
