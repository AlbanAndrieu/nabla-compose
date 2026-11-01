# pfSense Plus — ACB timeout (28) et avertissement write_config (27 octobre 2026)

**Statut au 1er novembre : diagnostic historique, correction runtime non attestée.**
Cette procédure est **read-only** jusqu'à la création **manuelle et volontaire**
d'une sauvegarde ACB via l'interface pfSense. Aucune modification DNS, WAN,
pare-feu, certificats, Device Key, mot de passe de chiffrement ou ACL n'est
autorisée par ce document.

## Deux événements distincts

- **General — 27/10 22:45:52** :
  `WARNING: write_config() was called without description`.
  Le code pfSense `src/etc/inc/config.lib.inc` émet ce *notice*
  lorsqu'un appel à `write_config()` conserve la valeur
  `Unknown` faute de motif significatif. Cela ne démontre
  ni un `config.xml` non écrit ni un échec ACB.
- **AutoConfigBackup — 27/10 22:46:33** :
  échec d'upload du fichier de configuration **chiffré**
  vers `https://acb.netgate.com` avec code **(28)**.
  Le code libcurl 28 est `CURLE_OPERATION_TIMEDOUT`
  (délai dépassé) : la cause précise (DNS, IPv4/IPv6,
  routage/egress, TLS, proxy, serveur distant, timeout à
  l'envoi) **n'est pas identifiable par la seule alerte**.
  La proximité des deux événements **ne prouve pas une
  cause commune**. Vérifier la zone horaire des journaux.

Le diagnostic ne doit pas afficher l'ACB comme `DOWN` sur la
base de deux notices anciens : `ACB_UPLOAD_NOT_VERIFIED` tant
qu'une sauvegarde **ultérieure** n'est pas constatée côté
service Netgate.

## P0 — établir d'abord si la sauvegarde fonctionne aujourd'hui

Dans l'interface pfSense :

1. **Services > Auto Config Backup > Restore** : noter
   uniquement l'**horodatage de la dernière sauvegarde hébergée**
   et le **nombre de sauvegardes en attente de transfert**
   (*staged backups*), sans ouvrir ni copier le contenu XML.
2. **Status > System Logs > System > General** : rechercher les
   messages `acbupload.php` et `write_config` du 27 octobre et
   les dernières lignes plus récentes. Vérifier la séquence
   *staging → starting upload → completed (... success)*.
   Ne partager que date, succès/échec et code ; les journaux
   bruts peuvent contenir des chemins/IP ou identifiants.
3. Si une sauvegarde hébergée **après le 27/10 22:46:33**
   est visible et que les files d'attente se résorbent :
   classer le timeout historique comme **RÉSOLU** pour la
   transmission ; aucun changement de configuration réseau
   nécessaire. Vérifier néanmoins la capacité de **télécharger
   et déchiffrer** un backup en privé (pas de restauration sur
   le pare-feu en production).
4. Sinon, créer au préalable un **backup local chiffré**
   depuis **Diagnostics > Backup & Restore** et le placer
   sur un stockage privé et indépendant. Le fichier
   `config.xml` est extrêmement sensible, même chiffré.
   Ne jamais le publier sur GitHub ou dans un chat.

Netgate met en file les sauvegardes ACB et vérifie les
envois environ une fois par minute. L'absence immédiate d'une
entrée après déclenchement n'est pas une preuve d'échec.

## P1 — contrôler DNS / HTTPS **depuis pfSense**, pas depuis la workstation

Sur une **console shell pfSense autorisée**, une commande par ligne :

```sh
date -u
# DNS : alternative GUI Diagnostics > DNS Lookup, hôte acb.netgate.com
# Vérifier la disponibilité de curl avant les sondes.
command -v curl
curl -4 --head --silent --show-error \
  --connect-timeout 5 --max-time 12 \
  --output /dev/null \
  --write-out 'acb_ipv4_http=%{http_code} tls_verify=%{ssl_verify_result} total_seconds=%{time_total}\n' \
  https://acb.netgate.com/
```

**Uniquement si pfSense possède une connectivité IPv6 WAN
attendue**, comparer l'autre famille :

```sh
curl -6 --head --silent --show-error \
  --connect-timeout 5 --max-time 12 \
  --output /dev/null \
  --write-out 'acb_ipv6_http=%{http_code} tls_verify=%{ssl_verify_result} total_seconds=%{time_total}\n' \
  https://acb.netgate.com/
```

Ne pas ajouter `-k`/`--insecure`, ne pas forcer un
`--resolve` vers une IP inconnue, ne pas transmettre
de cookie, Device Key, mot de passe, `config.xml` ou
authentifiant dans curl.

Un code HTTP (y compris 403/404/405) **avec une session
TLS validée** indique seulement que le point d'entrée
HTTP répond : un `HEAD` **ne valide pas l'upload ACB
authentifié**. `http=000`, timeout ou erreur TLS exigent
l'inspection séparée des étapes DNS, gateway, date et
certificat. Un échec IPv6 n'indique pas une panne si
aucune sortie IPv6 n'est prévue.

Si nécessaire, utiliser :
- **Diagnostics > DNS Lookup** pour `acb.netgate.com` ;
- **Status > Gateways** et **Diagnostics > Routes** pour
  la route effective de pfSense (sans l'inférer de la
  route Workstation ni changer les passerelles) ;
- **System > General Setup**, statut NTP et CA système
  pour les erreurs de résolution ou de vérification TLS ;
- logs de **System > General** pour les uploads et
  erreurs d'accès réseau. Distinguer éventuel souci
  distant Netgate d'une erreur locale.

**Après** DNS et HTTPS corrects : si aucun backup récent
n'existe, déclencher **une** entrée manuelle via
**Services > Auto Config Backup > Backup Now**
avec une *Revision Reason* descriptive. Vérifier
sa présence côté **Restore** après plus d'une minute.
Aucune relance en boucle, aucun changement de clé ACB,
aucune restauration de production pour « tester ».

## P2 — retrouver le code qui appelle write_config sans motif

Rechercher le contexte exact de **27/10 22:45:52**
dans **Status > System Logs > System > General** et
**Diagnostics > Backup & Restore > Config History**.
Une extension ou un script tiers peut sauvegarder
la configuration sans passer de description. Le simple
message ne permet pas de lui attribuer une responsabilité.

Dans **le code public de nabla-compose**, le seul appel
`write_config(` identifié par recherche GitHub est dans
`scripts/pfsense/manage-api-identities.php`, et cet appel
fournit déjà une description explicite :
`Reconciled pfSense REST API service identities`.
Il n'y a **aucune preuve** qu'il soit à l'origine de la
notification. Si un autre appelant est démontré par
les journaux, corriger **son appel** en
`write_config("motif explicite")`, avec test et
rollback, plutôt que masquer le message globalement
ou patcher les fichiers système pfSense.

## Conditions de clôture

| Contrôle | Condition DONE | Si information absente |
| --- | --- | --- |
| ACB stockage distant | Nouvelle entrée visible dans `Restore`, datée après l'incident, déchiffrement vérifié en privé | `ACB_UPLOAD_NOT_VERIFIED` |
| ACB transport | DNS/HTTPS pfSense corrects et opération `Backup Now` passée côté service | `ACB_TRANSPORT_NOT_VERIFIED` |
| Avertissement config | Contexte du caller identifié ; absence de récurrence après correctif ciblé | `WRITE_CONFIG_PROVENANCE_UNKNOWN` |
| Intégrité runtime | pfSense UI, règles, passerelles et services inchangés | STOP, diagnostic séparé |

Ne jamais fermer le ticket en effaçant simplement la
notification GUI avant d'avoir vérifié l'état distant.

### Sources

- [Netgate — AutoConfigBackup Testing and Status](https://docs.netgate.com/pfsense/en/latest/backup/acb-status.html)
- [Netgate — How AutoConfigBackup Works](https://docs.netgate.com/pfsense/en/latest/backup/acb-info.html)
- [Netgate — Troubleshooting Network Connectivity](https://docs.netgate.com/pfsense/en/latest/troubleshooting/connectivity.html)
- [Netgate — DNS Lookup](https://docs.netgate.com/pfsense/en/latest/diagnostics/dns.html)
- [pfSense — `write_config` source](https://github.com/pfsense/pfsense/blob/master/src/etc/inc/config.lib.inc)
- [curl — libcurl error codes](https://curl.se/libcurl/c/libcurl-errors.html)
