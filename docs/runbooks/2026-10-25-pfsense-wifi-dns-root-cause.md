# Diagnostic Wi-Fi / DNS — workstation, 25 octobre 2026

> **Historique au 25 octobre. Preuves plus récentes du 27 octobre :**
> l'exécuteur `hide-location.service` a **effectivement appelé**
> `resolvectl dns eno1 9.9.9.9 149.112.112.112` à répétition,
> attesté par sudo/journalctl. L'opérateur a désactivé le service
> **et** le timer ; DefectDojo est désormais accessible via Chrome.
> Une autre panne reste **non résolue** : `dig` UDP vers pfSense
> `172.17.0.1:53` a expiré, tandis que `resolvectl query`
> a répondu en 11,5 s. Ne pas confondre ces deux incidents.
> **Référence à suivre :**
> [workstation-split-dns-recovery.md](workstation-split-dns-recovery.md),
> [ansible-workstation PR #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15).


## P0 — Constat et niveau de preuve

Le message « le Wi-Fi semble avoir des soucis » ne permet pas encore de conclure
à une défaillance radio. La workstation documentée utilise normalement
`eno1` en Ethernet ; son état **ne prouve pas** la qualité radio d'un
téléphone ou de la borne Wi-Fi. Les tests `just pfsense-console-test`
échouaient indépendamment du réseau parce qu'une assertion RFC5424 attendait
une seconde complète en vue `compact` après regroupement par minute.
La correction compare la minute en `compact` et conserve le timestamp
complet en `verbose`, avec expurgation dans les deux cas.

Faits des derniers relevés pfSense :
- Unbound PID 12710 démarré le 24/10 à 23:38:57, puis PID 2135 le
  25/10 à 00:04:56. Les journaux mentionnent une sortie du module DNSBL
  Python à 00:04:54, mais **pas de nouveau OOM à cette minute**.
- Unbound a rencontré un conflit de bind à 23:39:55 et des notices de
  redémarrage autour de 23:39 et 23:40. Cela étaye une piste de
  discontinuité DNS lors d'une reconfiguration/reload, sans démontrer
  quel service a déclenché l'action.
- Mémoire libre + inactive à 00:12 : environ 119,4 Mio. Les OOM noyau
  historiques autour de 02:10 et 22:03 restent distincts de ces
  redémarrages ; la causalité de Snort/pfBlockerNG est encore inconnue.
- Le DHCP LAN pfSense annonce `172.17.0.1`, alors que la workstation a
  déjà utilisé Quad9 au niveau `resolvectl`/NetworkManager. Un resolver
  public ne sait pas résoudre `sample.int.albandrieu.com` sans
  délégation privée. Un autre incident a établi une entrée Pi-hole
  incorrecte `sample.albandrieu.com -> 172.17.0.24`. Ces deux
  anomalies sont des **preuves historiques de chemins DNS concurrents**,
  et non des preuves que la borne Wi-Fi est en panne aujourd'hui.

## Séparer les quatre couches

| Observation reproductible | Cause à vérifier | Ne pas conclure |
| --- | --- | --- |
| Le client perd l'association au SSID | Borne, signal RSSI, roaming, alimentation, canal | Ce n'est pas une preuve contre Unbound |
| L'association reste active mais IP/route disparaît | DHCP, VLAN, passerelle, AP bridge | Ne pas changer DNSBL |
| TCP/443 externe par IP fonctionne, Quad9 DNS répond, pfSense DNS ne répond pas | Unbound, port 53 ou règle/ACL VLAN Wi-Fi | Ne pas supposer OOM |
| DNS pfSense fonctionne mais résolution système échoue | DNS actif local, DNS privé du téléphone, VPN/DoH/IPv6 | Ne pas attribuer à la borne |
| Tout fonctionne pendant un échantillon | Incident intermittent non capturé | Ce n'est pas une preuve de stabilité durable |

Le diagnostic local capture uniquement les noms d'interfaces, l'état Wi-Fi,
la fréquence et la puissance du signal si `iw` est disponible, les IPv4
de DNS actifs et DHCP, les résultats booléens des requêtes publiques via
pfSense/Quad9 et un TCP/443 vers 1.1.1.1. Les identifiants de réseaux
Wi-Fi, BSSID, profils NM complets, cookies, requêtes client privées et
journaux bruts ne sont jamais affichés. Il ne lance ni scan Wi-Fi,
ni reconfiguration, ni capture des paquets.

## Contrôles — workstation

1. Tester les contrats sans réseau :

```bash
just pfsense-wifi-path-test
```

2. Diagnostiquer le chemin de la workstation en lecture seule :

```bash
just pfsense-wifi-path
```

3. Capturer une perturbation intermittente (six échantillons espacés de
30 secondes, uniquement si nécessaire) :

```bash
python3 scripts/workstation/diagnose-wifi-path.py --check --samples 6 --interval 30
```

4. Sur un **client Linux connecté au Wi-Fi affecté**, exécuter la même
commande depuis le dépôt installé sur ce client. Sur un téléphone, contrôler
manuellement l'association, le DNS privé/DoH/VPN, l'adresse reçue, la
passerelle et la résolution de noms sans partager les identifiants.
Un résultat provenant d'`eno1` Ethernet doit toujours indiquer
`wifi_client_not_tested=true`.

5. En cas de dégradation DNS observée, vérifier pfSense en lecture seule :

```bash
bash scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh --check
```

6. Pour les noms privés et l'override Pi-hole existant :

```bash
just sample-dns-workstation
```

**Attention** : une réponse d'un résolveur public ne prouve pas qu'une règle
VLAN laisse toujours passer DNS/53. Un TCP/443 vers l'IP d'un serveur externe
peut être filtré ; son échec isolé est `INCONCLUSIVE` et ne prouve pas
une perte WAN. `NO_FAILURE_DURING_SAMPLE` n'est pas une certification
du Wi-Fi ni une validation du téléphone.

## Décision de récupération

**Aucun changement pfSense, Pi-hole, DNSBL, DHCP, Snort, CrowdSec ou AP
n'est autorisé sur ces seules preuves.** Si le DNS pfSense décroche,
corréler précisément le PID et l'heure de démarrage d'Unbound, les
événements `pfblocker_event=... timestamp=...`, les changements de
réseau/port 53, et les messages OOM. Si l'association Wi-Fi décroche
pendant que les services câblés restent joignables, collecter plutôt
les événements de la borne et le contexte RSSI/roaming.

### Préservation CI

La PR de correction reste en Draft, commits `[skip ci]`. Vérifier
`just pfsense-console-test`, `just pfsense-unbound-wifi-test` et
`just pfsense-wifi-path-test` dans un worktree SHA-épinglé avant
Ready/merge. Ne pas lancer volontairement de CI GitHub payante.


## Validation workstation du 25 octobre — défaut confirmé de split-DNS local

**Preuve fournie par l'opérateur** : `just pfsense-console-test` **14/14
PASS**, `just pfsense-wifi-path-test` **9/9 PASS** sur le checkout testé
avant ce correctif. Il s'agit de tests de contrat ; ils ne mesurent pas
la disponibilité continue du Wi-Fi.

Le diagnostic `pfsense-wifi-path` sur `eno1` (Ethernet, pas Wi-Fi) a
confirmé la connectivité IPv4, TCP/53 pfSense, TCP/443 public et les
résolutions publiques pfSense/Quad9/système. Le diagnostic séparé
`sample-dns-workstation` a confirmé les deux serveurs pour la zone
privée, mais **pas la résolution NSS système** de
`sample.int.albandrieu.com`. C'est une anomalie actuelle du **client
Linux**, et non une panne de résolution sur pfSense.

Comparaison essentielle :

| Source | DNS / résultat | Preuve |
| --- | --- | --- |
| DHCP LAN Kea | `172.17.0.1` | Bail observé, correct |
| Profil NetworkManager `Wired eno1` | `ipv4.dns=172.17.0.1` et `ipv4.ignore-auto-dns=yes` | Config du profil |
| `resolvectl dns eno1` | `9.9.9.9`, `149.112.112.112` | Valeurs **actives** différentes du profil |
| `dig @172.17.0.1 sample.int.albandrieu.com` | `172.17.0.24` | DNS privé pfSense OK |
| `dig @172.17.0.24 sample.int.albandrieu.com` | `172.17.0.24` | Pi-hole OK |
| `getent ahostsv4 sample.int.albandrieu.com` | Pas d'adresse | Résolution **système KO** |

La valeur affichée précédemment par le collecteur
`DHCP DNS=172.17.0.1,172.17.0.57,255.255.255.0` était un **bug
d'extraction**. L'adresse client et le masque ne sont pas des DNS.
Le parseur lit à présent **uniquement l'option
`domain_name_servers`** et dispose d'un test négatif.

### Nouveau contrat de diagnostic

Lorsque les DNS publics fonctionnent, que la zone privée est résolue
directement depuis pfSense mais pas via `getent`, le diagnostic retourne
`CLIENT_PRIVATE_SPLIT_DNS_PATH`, **exit 1**. Il ne doit plus afficher
`NO_FAILURE_DURING_SAMPLE`. Cette erreur est indépendante du lien Wi-Fi
et peut expliquer des dysfonctionnements des services `*.int`. Elle
**n'explique pas à elle seule les perturbations WhatsApp**.

Le rapport inclut trois catégories distinctes :
`dhcp_advertised_dns`, `configured_profile_dns` et
`active_link_dns`, puis `profile_dns_runtime_drift`. Il lit
`nmcli -f ipv4.dns,ipv4.ignore-auto-dns connection show <profil>`
en lecture seule et n'affiche pas l'identifiant du profil.
`ipv4.ignore-auto-dns=yes` n'explique pas **à lui seul** pourquoi
`resolvectl` indique Quad9 si `ipv4.dns=172.17.0.1` : inspecter
sans modification les substitutions `systemd-resolved`, les profils
VPN, les DNS globaux NetworkManager et un éventuel état périmé.
Ne pas changer DHCP ni désactiver Quad9 arbitrairement.

### Validation local-first après correction

Exécuter successivement sur le HEAD exact de la PR :

```bash
just pfsense-console-test
```

```bash
just pfsense-wifi-path-test
```

```bash
just pfsense-wifi-path
```

```bash
just sample-dns-workstation
```

Résultat visé : DHCP DNS **seulement** `172.17.0.1`,
`diagnosis=CLIENT_PRIVATE_SPLIT_DNS_PATH` tant que l'incident est
présent, et sortie 1 dans ce cas. Une éventuelle future restauration
du DNS privé devra être confirmée par `getent` et non par le seul
`dig @pfSense`. Aucune commande ne modifie l'interface ou les DNS.

**À distinguer du problème radio** : l'interface `eno1` ne permet pas
de diagnostiquer RSSI, roaming ou déconnexion d'un téléphone. Il faut
observer le client directement connecté au SSID affecté.



### Isoler l'écart entre NetworkManager et systemd-resolved

Le diagnostic lit désormais trois états **distincts** sans révéler le nom
du profil ou ses autres paramètres : DNS déclarés dans le profil,
DNS effectifs de l'interface selon `nmcli -g IP4.DNS`, DNS de la même
interface selon `resolvectl dns`.

La variable `runtime_dns_drift` distingue :

- `NETWORKMANAGER_VS_RESOLVED` : NetworkManager indique un DNS
  différent de systemd-resolved ; inspecter le propriétaire de la
  configuration resolved, les VPN et les paramètres DNS globaux.
- `PROFILE_VS_NETWORKMANAGER_DEVICE` : profil enregistré différent de
  la configuration NetworkManager active ; vérifier l'activation du
  profil, les changements runtime et les politiques DNS.
- `PROFILE_VS_ACTIVE_RESOLVER` : écart profil/résolveur confirmé,
  mais pas assez de données pour trancher l'étage intermédiaire.
- `NONE_CONFIRMED` : aucun écart prouvé dans cet échantillon ;
  ce résultat ne garantit pas l'absence d'incident intermittent.

Les noms ci-dessus localisent un **écart de valeurs**, pas l'auteur
d'une mutation. Aucune modification via `nmcli` ou `resolvectl` ne
doit être appliquée sans détenir la preuve de l'étage responsable.

Commandes complémentaires pour interpréter le diagnostic :

```bash
nmcli -g IP4.DNS device show eno1
```

```bash
resolvectl dns eno1
```

```bash
nmcli -f ipv4.dns,ipv4.ignore-auto-dns connection show 'Wired eno1'
```

Exécuter `just pfsense-wifi-path-test` avant le test runtime sur la
nouvelle révision. Les tests ajoutés simulent séparément les deux types
d'écarts. Les résultats de l'opérateur (**14 + 9 PASS**) portent sur
la version **antérieure** à ces corrections ; les 15 contrats Wi-Fi
mis à jour sont à exécuter au HEAD exact.



### Source Ansible retrouvée — hypothèse de modification `resolvectl`

Le 25 octobre, la recherche des sources `AlbanAndrieu/ansible-workstation`
a identifié un mécanisme de **mutation DNS intentionnelle** :

- `tasks/services.yml` configure `dns_new="9.9.9.9 149.112.112.112"`,
  `dns_default="172.17.0.24"` et `net_interface="wlp0s20f3"`.
- `templates/hide-location.sh-Ubuntu.j2` installe un script qui vérifie
  si `resolvectl status` contient `dns_default`, puis appelle
  `sudo resolvectl dns $net_interface $dns_new`.
- `tasks/services.yml` installe `/opt/script/hide-location.sh`, la
  **service systemd user** `hide-location.service` et le fichier
  `hide-location.timer`, conditionnés par `macchanger_enabled`.
  Le rôle active `hide-location.service` en mode utilisateur si les
  conditions Ansible sont satisfaites.
- Le template de timer prévoit `OnBootSec=1m` et
  `OnUnitActiveSec=1m`. La création de son fichier **ne prouve pas son
  activation** et la configuration effective doit être contrôlée sur
  la workstation.

**Limite décisive :** le modèle versionné cible **`wlp0s20f3`** alors
que l'écart observé concerne **`eno1`**. De plus, le template déclenche
l'override seulement si `dns_default` est trouvé. Les fichiers source
sont compatibles avec le choix de Quad9 constaté, mais **ils ne prouvent
pas que le script local a été généré avec ces paramètres, ni exécuté, ni
qu'il a modifié `eno1`**. Ne pas désactiver le service à l'aveugle.

Le diagnostic `just pfsense-wifi-path` inspecte maintenant le fichier
rendu `/opt/script/hide-location.sh` s'il existe, sans le lancer, et
la métadonnée systemd de `hide-location.service`. Il indique
`hook_sets_quad9`, `hook_targets_current_interface`,
`hook_contains_resolvectl_dns`, `unit_state` et
`unit_has_start_timestamp`. Le statut `causality=NOT_PROVEN`
reste volontairement explicite. Aucun identifiant, argument ni contenu
de script n'est imprimé. Ces mesures ne remplacent pas la preuve du
moment de la modification DNS.

Contrôles complémentaires, **une seule commande à la fois**, en lecture seule :

```bash
systemctl --user show hide-location.service --property=LoadState,UnitFileState,ActiveState,ExecMainStartTimestamp --no-pager
```

```bash
systemctl --user is-enabled hide-location.timer
```

```bash
nmcli -g IP4.DNS device show eno1
```

```bash
resolvectl dns eno1
```

Ne pas supprimer le script Ansible ni modifier le profil réseau depuis
cette PR. Une remédiation **dans `ansible-workstation`** serait de rendre
le changement DNS explicite et réversible, protéger les noms privés par
split-DNS et s'assurer que les scripts de confidentialité ne remplacent
pas le résolveur propriétaire du LAN. Elle reste conditionnée à la
confirmation du service réellement exécuté et à l'intention de
l'utilisateur de garder Quad9.

