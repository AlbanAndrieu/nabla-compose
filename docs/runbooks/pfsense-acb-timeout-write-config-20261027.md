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

### Nouvelle preuve opérateur du 1er novembre 2026

La sonde IPv4 précédente sur pfSense :
`curl -4 --head https://acb.netgate.com/` a retourné :

```text
curl: (56) OpenSSL SSL_read: OpenSSL/3.5.7:
error:0A000126:SSL routines::unexpected eof while reading, errno 0
http=000 tls=0
```

**Ce que cela signifie, sans extrapolation :**
- libcurl **56 = erreur de réception** ; la connexion s'est
  fermée avant qu'une réponse HTTP exploitable ne soit disponible.
  Un EOF peut provenir du serveur, d'un intermédiaire réseau ou
  d'un comportement dépendant de la méthode HTTP/protocole.
- `http=000` : **aucun statut HTTP enregistré** ;
  `tls=0` (valeur de `ssl_verify_result`) : pas d'échec de
  vérification du certificat signalé. **Ce n'est pas** un
  indicateur de réussite du transfert TLS ou HTTP.
- L'alerte **ACB 28** du 27 octobre et cette sonde
  **56** du 1er novembre sont **différentes** ; leur cause
  commune reste hypothétique. Une requête `HEAD /`
  n'est **pas l'API d'upload authentifiée ACB**.
  Elle ne permet pas de qualifier le statut global
  du service de sauvegarde à elle seule.

### Sonde suivante : GET simple, HTTP/1.1, sans authentification

Sur le shell pfSense, **une seule requête bornée** :

```sh
date -u
command -v curl
curl -4 --http1.1 --silent --show-error \
  --connect-timeout 5 --max-time 15 \
  --output /dev/null \
  --write-out 'acb_ipv4_get_http=%{http_code} tls_verify=%{ssl_verify_result} total_seconds=%{time_total}\n' \
  https://acb.netgate.com/
```

La commande utilise `GET` et impose HTTP/1.1 pour
limiter les variables possibles liées à `HEAD` et ALPN/HTTP2.
**Elle change deux paramètres à la fois** et ne permet
donc pas, en cas de réussite, d'attribuer la cause
spécifiquement à `HEAD`. Ne pas suivre les redirections,
ne pas transmettre Device Key, token ou configuration.

- **Si statut HTTP disponible** (y compris 3xx, 403,
  404 ou 405) et vérification TLS positive :
  la terminaison HTTP répond pour ce test ;
  **l'upload ACB n'est pas attesté**.
- **Si encore `http=000`, 56 ou 28** :
  classer `ACB_HTTPS_PROBE_NOT_VERIFIED`, vérifier
  DNS, gateways, date/certificats et logs de **pfSense**.
  Ne jamais classer le service ACB comme `DOWN`
  par simple inférence.
- **Si GET fonctionne et HEAD échoue**, le
  comportement peut être spécifique à la méthode,
  à HTTP/2, à un reverse proxy ou à un WAF ;
  inutile de forcer un changement de politique.
- **Vérification IPv6 facultative seulement si
  une connectivité IPv6 WAN est attendue** :
  utiliser la même sonde GET avec `-6`,
  sans conclure à une panne pour un réseau
  IPv6 non configuré.

Ni `-k`/`--insecure`, ni `--resolve` vers une IP
arbitraire, ni désactivation d'ACB, de CA, de WAF
ou de règles WAN pour « faire passer » un GET.

**Source d'autorité de la sauvegarde :**
`Services > Auto Config Backup > Restore`.
Une entrée **postérieure à l'incident, réellement
hébergée** et récupérable prouve davantage que
toute sonde HTTP publique. Netgate documente
le traitement différé des backups, qui peuvent
mettre au moins une minute à apparaître.

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
