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

## P1 — réception des sondes HTTP et diagnostic **réel ACB**

### Résultats pfSense fournis le 1er novembre 2026

Deux requêtes **vers la racine `/`**, non authentifiées,
ont échoué depuis le shell pfSense :

| Méthode | Résultat | Lecture |
| --- | --- | --- |
| `HEAD /` via IPv4 | `curl (56)`, `http=000`, `ssl_verify_result=0` | Fermeture TLS inattendue avant réception d'une réponse HTTP |
| `GET /` via IPv4, HTTP/1.1 | `curl (56)`, `http=000`, `ssl_verify_result=0`, durée **0,627649 s** | Pas un problème limité à la méthode HEAD ; aucune réponse HTTP reçue |

Le `curl (28)` du **27 octobre 22:46:33** provenait
d'une **tentative réelle d'upload ACB**, tandis que
les `curl (56)` ci-dessus concernent **des sondes
HTTP vers une route différente**. Rien ne prouve une
cause commune. La valeur `ssl_verify_result=0`
signifie seulement qu'aucun échec de vérification
du certificat n'a été rapporté, pas que HTTP fonctionne.

### Pourquoi il ne faut plus sonder `GET /` comme preuve d'ACB

Dans le code source pfSense
[`src/etc/inc/acb.inc`](https://github.com/pfsense/pfsense/blob/master/src/etc/inc/acb.inc),
`acb_query_service()` utilise **POST** sur des
**routes API dédiées** :
`/list` pour les sauvegardes hébergées,
`/save` pour l'envoi chiffré et
`/getbkp` pour la récupération. Ces appels portent
des **paramètres d'identité/credentials ACB**.
Un `HEAD /` ou `GET /` en accès anonyme n'exerce
**aucun** de ces parcours. Ne jamais fabriquer de
`POST /list` ou `POST /save` à la main ou
transmettre Device Key, mot de passe, fichier XML
ou données privées dans un terminal partagé.

L'existence de **100 backups hébergés** dans
`Services > Auto Config Backup > Restore` prouve
qu'au moins 100 entrées sont présentes côté
Netgate pour la Device Key consultée ; elle ne
prouve **pas** la réussite d'un envoi récent.
Netgate conserve **au maximum 100 entrées** par
clé et évince automatiquement les plus anciennes.
La limite 100 **ne bloque donc pas** les nouveaux
uploads.

L'extrait de la liste partagé mentionne notamment
**27 octobre 20:48:04 (+0100)**, avant l'incident
d'upload du **27 octobre 22:46:33 (+0100)**.
**Si cette ligne est réellement la plus récente de
la liste**, il manque encore la preuve d'une
sauvegarde hébergée depuis l'incident. Vérifier
l'ordre d'affichage complet avant toute conclusion.

**Attention aux entrées staged :** le code amont
de `acb_backup_upload()` supprime les fichiers
`.form` et `.data` après la tentative d'envoi
**quelle que soit son issue**. Si ce comportement
est présent dans la version pfSense installée,
un compteur `staged=0` **ne prouve pas la réussite**.
Ne pas chercher à extraire ou reconstituer les
fichiers contenant la configuration.

### Test métier conseillé : un seul Backup Now via l'UI

**Avant toute opération**, sauvegarder séparément
la configuration actuelle dans un stockage
privé chiffré (`Diagnostics > Backup & Restore`).
Il s'agit d'une sauvegarde ; ne surtout pas
**restaurer** le pare-feu en production pour ce
diagnostic.

1. Dans `Services > Auto Config Backup > Restore`,
   noter la **date/heure de l'entrée la plus récente**
   et le nombre `Staged backups waiting to upload`
   s'il est affiché.
2. Dans `Services > Auto Config Backup > Backup Now`,
   créer **une seule entrée** avec une raison
   descriptive, par exemple :
   `ACB validation 2026-11-01 - test envoi post incident`.
   Conserver la Device Key et le mot de passe
   de chiffrement existants, sans les publier.
3. Après **au moins une minute**, actualiser
   `Restore` et vérifier que cette entrée
   apparaît **avec la date et la raison attendues**.
   Les 100 anciennes entrées peuvent rester au
   maximum 100 : le **nombre** ne constitue pas
   le critère de réussite.
4. Examiner seulement les lignes expurgées
   `Staging`, `Starting upload`,
   `Completed ... (success)` ou code d'échec
   dans `Status > System Logs > System > General`.
5. **Si l'entrée est présente et récupérable** :
   `ACB_UPLOAD_PASS` et épisode historique
   28 potentiellement transitoire.
   Si absente : `ACB_UPLOAD_NOT_VERIFIED`
   ou `ACB_UPLOAD_FAILED` en cas d'échec
   explicite dans les journaux ; effectuer
   **un diagnostic de l'API POST**, du proxy PHP,
   DNS et routage pfSense sans modifier les
   règles WAN ni TLS.

**Confidentialité :** le code amont
`acb_query_service()` peut enregistrer
`/tmp/acb_debug.txt` lorsqu'une erreur curl
survient. Ce fichier peut contenir des
paramètres de la requête ou métadonnées
sensibles. Ne **jamais** l'afficher, coller,
committer ou envoyer tel quel au support.
Ne pas utiliser `curl -v`, `--trace` ou
`-k` sur une requête ACB authentifiée.

Le statut des sauvegardes doit provenir de
`Restore` et des logs officiels de l'opération,
et **non** de la disponibilité de `GET /`.

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
