# DefectDojo private ingress — acceptance after PR #257

**DNS privé workstation (référence inter-dépôts pour les agents) :**
[workstation-split-dns-recovery.md](workstation-split-dns-recovery.md),
[ansible-workstation PR #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15).
Le split-DNS persistant est possédé par ansible-workstation ;
ce dépôt possède seulement le diagnostic/rattrapage local
(`just workstation-split-dns-check`, `-test`, `-repair`).
Après réparation du drift Quad9, une requête DNS directe
vers pfSense en UDP/53 a également expiré, malgré
un `resolvectl query` réussi en 11,5 s : mesurer UDP et TCP
séparément, ne pas classer cette latence comme une panne Traefik.


This runbook follows merged PR #257. DefectDojo's Nginx frontend is configured for the internal hostname `defectdojo.int.albandrieu.com` on Traefik `websecure`; public Cloudflare DNS, AutoXpose and WAN HAProxy are **not** part of the intended path.

## Nouvelle régression DNS observée — 27 octobre, 21:27 CET

Dernière preuve de l'opérateur après la validation initiale :

- `just defectdojo-workstation-dns-test` : **2/2 PASS**, bibliothèque
  standard `unittest`, sans `pytest`.
- `just defectdojo-workstation-dns-check` : **FAIL attendu**,
  `CLIENT_PRIVATE_SPLIT_DNS_PATH` : `dig @pfSense` retourne bien
  `172.17.0.24`, mais le résolveur NSS de la workstation ne répond plus.
- `resolvectl dns eno1` est **redevenu Quad9**
  (`9.9.9.9 149.112.112.112`) alors que le device
  NetworkManager est toujours `172.17.0.1`.
- `resolvectl domain eno1` conserve `~int.albandrieu.com` ;
  le domaine est donc correct, mais transmis au mauvais serveur.
- Chrome : `DNS_PROBE_FINISHED_NXDOMAIN` pour l'URL HTTPS privée.
- `hide-location.service` inactive (oneshot), enabled,
  `ExecMainStartTimestamp=2026-10-27 21:27:01 CET`,
  et `hide-location.timer` enabled.
  **Corrélation temporelle, pas encore preuve que ce service écrit Quad9.**
  Le rapport du script installé disait `sets_quad9=False` ;
  conserver cette réserve.

**Ownership et correction future :**
[ansible-workstation PR #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15)
prépare une protection du hook `hide-location` lorsqu'il opère sur le LAN
pfSense et une réconciliation de `network_split_dns.yml` qui réapplique
le profil lorsqu'il est correct mais que `systemd-resolved` a dérivé.
La PR est Draft, opt-in Ansible désactivé par défaut, et **aucune correction
Ansible n'a été appliquée à cette workstation**.

Pour restaurer **temporairement** le poste, sans modification pfSense :

```bash
sudo resolvectl dns eno1 172.17.0.1
sudo resolvectl domain eno1 '~int.albandrieu.com'
sudo resolvectl flush-caches
getent ahostsv4 defectdojo.int.albandrieu.com
```

Pour rechercher l'écrivain DNS avant tout arrêt de timer, en lecture seule :

```bash
systemctl --user list-timers --all hide-location.timer
journalctl --user -u hide-location.service \
  --since '2026-10-27 21:20:00' --until '2026-10-27 21:35:00' \
  --no-pager -o short-iso
nmcli -g IP4.DNS device show eno1
resolvectl dns eno1
```

Un échec du navigateur après `getent` rétabli doit être vérifié
séparément côté **Secure DNS / DoH de Chrome**, notamment si un
fournisseur DNS public personnalisé contourne le résolveur système.
Ne pas retoucher Traefik, HAProxy, pfSense ou les identifiants Django.

## Réception workstation — 27 octobre, résolution DNS rétablie temporairement

**Avant correction (workstation `eno1`) :**

- DHCP DNS, DNS du profil NetworkManager et DNS du device :
  **`172.17.0.1`**.
- `resolvectl dns eno1` : **`9.9.9.9 149.112.112.112`** ;
  `resolvectl domain eno1` : `int.albandrieu.com` (domaine
  de recherche, pas `~int.albandrieu.com`).
- `dig @172.17.0.1 defectdojo.int.albandrieu.com A` :
  **`172.17.0.24`** ; résolution système / `getent` : échec.
- `just pfsense-wifi-path` : **`CLIENT_PRIVATE_SPLIT_DNS_PATH`**
  et **`runtime_dns_drift=NETWORKMANAGER_VS_RESOLVED`**.
  Le retour `exit 1` de Just est attendu quand le diagnostic détecte
  une anomalie, ce n'est pas une panne du script.
- `hide-location.service` : `loaded`, `enabled`,
  `started_recorded=True`, hook `resolvectl_dns=True`,
  `targets_interface=True`, **`sets_quad9=False`**.
  Cela prouve un risque de modification locale, pas **quel service**
  a effectivement remplacé le DNS par Quad9.

**Correction opérateur temporaire déjà appliquée :**

```bash
sudo resolvectl dns eno1 172.17.0.1
sudo resolvectl domain eno1 '~int.albandrieu.com'
sudo resolvectl flush-caches
getent ahostsv4 defectdojo.int.albandrieu.com
```

`getent` a ensuite retourné **`172.17.0.24`**.
`bash scripts/workstation/diagnose-defectdojo-lan.sh --check`
a confirmé `PASS` sur DNS pfSense, résolution système,
réponse HTTPS 302, certificat TLS vérifié, et redirection
sur la même origine. Son test `curl --resolve` contourne
le DNS du client ; la preuve DNS du client provient de `getent`
séparément. **Le login Web HTTPS authentifié n'a pas encore été
confirmé par l'opérateur.**

**Résolution permanente : en attente.** Les modifications manuelles
`resolvectl` peuvent être écrasées par la prochaine
réactivation NetworkManager, un VPN, une commande `resolvectl`
externe ou une automatisation comme `hide-location`.
Sur la workstation, inspecter sans mutation :

```bash
nmcli -g GENERAL.CONNECTION device show eno1
nmcli -g IP4.DNS device show eno1
resolvectl dns eno1
resolvectl domain eno1
systemctl --user show hide-location.service \
  --property=LoadState,UnitFileState,ActiveState,ExecMainStartTimestamp \
  --no-pager
systemctl --user is-enabled hide-location.timer
```

Sur le profil NetworkManager **réellement actif**, préserver
`ipv4.dns=172.17.0.1`, `ipv4.ignore-auto-dns=yes`, et prévoir
la route DNS de domaine `ipv4.dns-search=~int.albandrieu.com`
sans écraser les autres domaines légitimes, **après identification
de l'auteur de l'override**. NetworkManager sait distinguer
un domaine de routage `~...` d'un domaine de recherche ;
une modification du profil seule ne neutralise pas un script
qui réécrit ensuite `systemd-resolved`.
Éviter un `nmcli connection up` non planifié sur la liaison utilisée
pour la session SSH/remote.

**Quality gate :** la nouvelle suite `test_defectdojo_workstation_lan_dns.py`
était d'abord écrite pour `pytest`, absent du Python
`mise` 3.14.9 (`No module named pytest`).
Elle a été portée vers **`unittest` de la bibliothèque standard**
dans la PR #289. Vérifier cette version au HEAD Git :

```bash
python3 -m unittest discover -s tests \
  -p 'test_defectdojo_workstation_lan_dns.py' -v
```

Aucun package n'a besoin d'être installé et la CI GitHub reste
désactivée. **Ce nouveau contrat stdlib n'est pas encore validé
sur la workstation.**

## Réception complémentaire du 27 octobre — HTTPS TrueNAS OK, client workstation DNS KO

L'opérateur a exécuté `diagnose-defectdojo-https-route.py --check` depuis
TrueNAS avec résultat :

- `dns_pfsense=PRIVATE_A_CONFIRMED`, `dns_pihole=PRIVATE_A_CONFIRMED` ;
- `origin=LOGIN_HTML_READY`, `https=LOGIN_HTML_READY` avec certificat
  validé par `curl --resolve` (pas de `-k`) ;
- `traefik_container=running`, `traefik_host_https=PUBLISHED_443`,
  `shared_proxy_network=SHARED`, `router_labels=DECLARED`.

**Acceptation :** le routage TLS/SNI Traefik et la page de login sont
fonctionnels **depuis TrueNAS**. La workstation retourne toutefois
`ping: ... Name or service not known`. Cela localise le problème
résiduel sur le **chemin de résolution du client**, sous réserve de
confirmer `dig @pfSense` depuis cette même machine.

Le PTR affiché par `ping` sur TrueNAS (`bitwarden.albandrieu.com`)
est une résolution inverse de `172.17.0.24` ; il ne change
pas la réponse A ni la route DefectDojo.

Le **runbook du 25 octobre**
[`2026-10-25-pfsense-wifi-dns-root-cause.md`](2026-10-25-pfsense-wifi-dns-root-cause.md)
documente déjà une divergence sur `eno1` : DHCP/profil NetworkManager
`172.17.0.1`, mais `systemd-resolved` indiquait Quad9 et
`getent` ne résolvait pas `*.int.albandrieu.com`.
Une automatisation ancienne d'`ansible-workstation`
(`hide-location.sh`, `hide-location.service`) peut modifier
`resolvectl dns`, **sans preuve de causalité à ce jour**.

### Workstation — comparaison sur le même client (lecture seule)

```bash
cd ~/w/nabla-compose
just pfsense-wifi-path

dig +time=2 +tries=1 +short @172.17.0.1 defectdojo.int.albandrieu.com A
dig +time=2 +tries=1 +short @172.17.0.24 defectdojo.int.albandrieu.com A

resolvectl dns eno1
resolvectl domain eno1
getent ahostsv4 defectdojo.int.albandrieu.com

# TLS/SNI sans recours au résolveur système ; aucune session utilisateur.
curl --noproxy '*' --connect-timeout 3 --max-time 10 \
  --resolve defectdojo.int.albandrieu.com:443:172.17.0.24 \
  -sS -o /dev/null \
  -w 'https=%{http_code} tls=%{ssl_verify_result}\\n' \
  https://defectdojo.int.albandrieu.com/login
```

Le diagnostic workstation `bash scripts/workstation/diagnose-defectdojo-lan.sh --check`
compare désormais aussi `getent ahostsv4` à l'adresse attendue.
Même si `dig @pfSense` et `curl --resolve` sont verts, un échec
NSS retourne `CLIENT_PRIVATE_SPLIT_DNS_PATH` et exit 1 :
**ne plus annoncer un PASS du navigateur quand le nom échoue sur le client.**

### Remédiation : couche locale seulement

- Si `dig @172.17.0.1` échoue **depuis workstation**, examiner LAN,
  pare-feu/VPN, UDP/TCP port 53 et la réponse de ce même résolveur.
- Si `dig @172.17.0.1` retourne `172.17.0.24` mais `getent`
  échoue, inspecter `resolvectl`, NetworkManager, NSS,
  VPN/DoH et éventuel override `hide-location` ; **ne pas
  reconfigurer pfSense DNS Forwarder (dnsmasq)**. Cette architecture
  utilise DNS Resolver (Unbound) + Domain Override vers Pi-hole.
- `/etc/hosts` peut servir uniquement de contournement temporaire.
  Pour prouver le HTTPS sans mutation, **préférer `curl --resolve`**.
- Corriger durablement la **source de la configuration DNS locale**
  (profil NetworkManager/automation) seulement après avoir prouvé
  l'auteur de la divergence. Aucun changement automatique pfSense,
  Pi-hole, Traefik, DefectDojo, ni `/etc/hosts`.

**Tests opérateur :** suite HTTPS TrueNAS `31 passed in 0.20s`
sur la branche actuelle au moment de l'exécution. Cela ne valide pas
encore le nouveau contrat workstation, dont les tests synthétiques
restent à exécuter après mise à jour de cette PR.

## Réception 27 octobre — login HTTP validé, HTTPS privé non validé

Le compte `admin` a été **authentifié avec succès** par l'opérateur
sur `http://172.17.0.24:31085/dashboard`.
La vérification en shell Django a retourné `password_matches=True`,
`active=True`, `staff=True` et `superuser=True` ; le helper
`--interactive-check` retourne aussi `PASSWORD_MATCH`.
La tentative de connexion antérieure utilisait une valeur
obsolète enregistrée dans LastPass. **Ne pas changer à nouveau le mot
de passe, ni recréer l'utilisateur.**

Le nom `https://defectdojo.int.albandrieu.com/` reste non disponible
dans le navigateur. Le HTTPS **n'est pas considéré comme DOWN**
sans classification de DNS, TCP, TLS, Host/SNI et Traefik.
Dans la topologie actuelle, le DNS interne `*.int.albandrieu.com`
doit résoudre `172.17.0.24` et une connexion LAN au port 443 rejoint
**Traefik directement**, pas HAProxy pfSense.
pfSense/HAProxy concerne le frontal WAN/rechiffrement et les
exceptions publiques ; n'ajouter aucune ACL/route publique pour
débloquer DefectDojo.

### Étape unique de diagnostic (lecture seule)

```bash
cd /mnt/cpool/compose/nabla-compose
git pull --ff-only
sudo python3 scripts/truenas/diagnose-defectdojo-https-route.py --check
```

Le script teste maintenant :
- l'origine HTTP Nginx `:31085` et le HTTPS direct
  `--resolve defectdojo.int.albandrieu.com:443:172.17.0.24`
  (TLS vérifié, sans `-k`, sans suivre les redirections) ;
- le DNS privé Pi-hole `172.17.0.24` et pfSense/Unbound `172.17.0.1` ;
- l'état Traefik, sa publication `:443`, le réseau `traefik_network`
  partagé avec DefectDojo, et les **labels réellement déployés**
  (pas seulement ceux dans Git) ;
- la classification des erreurs curl : refus TCP, timeout,
  handshake TLS et certificat non fiable sont distincts.

### Décider selon `next_layer`

| Résultat | Action ciblée |
| --- | --- |
| `SPLIT_DNS` | Corriger le nom privé dans Pi-hole/Unbound uniquement après preuve du resolver fautif |
| `TRAEFIK_CONTAINER` ou `TRAEFIK_443_BINDING` | Comparer TrueNAS App Traefik, écoute `:443` et bindings, sans redémarrage général |
| `TRAEFIK_NETWORK` | Comparer les réseaux actifs des deux conteneurs et le rendu Compose TrueNAS ; ne pas créer un nouveau réseau |
| `TRAEFIK_RUNTIME_LABELS` | Contrôler l'include TrueNAS, le modèle rendu et les labels Docker ; un `git pull` ne change pas les labels d'un conteneur déjà créé |
| `TRAEFIK_TLS_ROUTER` | Distinguer erreur de certificat, 404 Host/router, 502 upstream ou timeout ; corriger seulement la couche attestée |
| `DJANGO_LOGIN_AUTHENTICATION` et HTTPS login 200/30x | Transport serveur HTTPS accessible depuis TrueNAS ; si le navigateur échoue, examiner le résolveur et le proxy **du client** |

En cas de `TRAEFIK_RUNTIME_LABELS`, ne pas lancer automatiquement
`app.redeploy defectdojo` : la réconciliation TrueNAS peut recréer
la stack et relancer l'initializer. Commencer par les métadonnées
en lecture seule :

```bash
sudo docker inspect defectdojo --format '{{json .Config.Labels}}' |
  jq 'with_entries(select(.key | startswith("traefik.")))'

sudo docker inspect defectdojo --format '{{json .NetworkSettings.Networks}}' |
  jq 'keys'

sudo midclt call app.config defectdojo |
  jq '{include: .include}'
```

L'App déclare dans `apps/defectdojo/compose.yml` les labels
`traefik.enable=true`, Host exact, `websecure`, TLS et
`loadbalancer.server.port=8080` sur `traefik_network`.
Leur **présence au runtime n'est pas encore attestée** par le
relevé opérateur. La correction doit éviter d'exposer une route
privée sur le WAN ou d'affaiblir TLS.

**Travail séparé :** le coffre Vaultwarden et `.env.secrets`
restent non alignés sur le nouveau mot de passe Django.
Synchroniser uniquement après avoir conservé la valeur qui
fonctionne (LastPass ne constitue pas la source canonique).
Ne pas écraser le hash Django par l'ancien secret runtime.

## Évidence LAN à 20:51 CET le 26 octobre 2026

Les deux requêtes DNS ont réussi :
`dig @172.17.0.1` et `dig @172.17.0.24` pour
`defectdojo.int.albandrieu.com` renvoient toutes deux
`NOERROR A 172.17.0.24`. Le serveur Nginx direct
`http://172.17.0.24:31085/` répond. En revanche,
`https://defectdojo.int.albandrieu.com/` reste inaccessible
depuis la workstation. **Ne pas corriger le DNS** sur cette preuve.

Le nouveau script
`sudo python3 scripts/truenas/diagnose-defectdojo-https-route.py --check`
sépare l'origine HTTP et HTTPS TLS/SNI vers l'adresse LAN, l'état
du conteneur Traefik, les labels de routage et le réseau Docker
`traefik_network`. Il catégorise `TLS_CERTIFICATE_UNTRUSTED`,
`ROUTER_OR_PATH_NOT_FOUND`, `TRAEFIK_UPSTREAM_UNAVAILABLE`
ou `TCP_TLS_UNREACHABLE` sans divulguer le certificat ou des
en-têtes privés. Le résultat nécessite une exécution LAN ;
le seul DNS OK n'atteste pas le port 443 ni un certificat valable.

Le mot de passe `admin` est indépendant : modifier
`DD_ADMIN_PASSWORD` dans `.env.secrets` ne met pas à jour le
hash PostgreSQL. Voir le [runbook du compte Django](defectdojo-admin-access-recovery.md)
pour vérifier/synchroniser le compte existant, puis contrôler
Vaultwarden.

## Vérification du login privé (26 octobre 2026)

L'ancienne preuve de transport était HTTP 200 après redirection avec
vérification TLS, mais le login exact n'a pas été revérifié de façon
contemporaine. Depuis TrueNAS ou la workstation LAN :

```bash
bash scripts/workstation/check-defectdojo-login-lan.sh --check
```

La nouvelle sonde utilise `--resolve` pour conserver l'origine
HTTPS/SNI, vérifie le certificat, exige 200 + `text/html`,
et ne suit aucune redirection. Un PASS vérifie l'affichage
de la page de connexion, **pas l'authentification Django**.

## Régression du 25 octobre 2026 — URL privée inaccessible

L'opérateur signale que `https://defectdojo.int.albandrieu.com/`
ne répond plus. **La cause actuelle n'est pas vérifiée** et l'ancien
HTTP 302 du 17 octobre ne suffit pas à déclarer le service sain.
Les sondes de préflight antérieures peuvent être PASS alors que le
navigateur échoue sur DNS ou HTTPS.

### TrueNAS — diagnostic lecture seule

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/preflight-defectdojo.sh
sudo bash scripts/truenas/diagnose-defectdojo.sh --check

# Comparer le backend HTTP et Traefik HTTPS sans utiliser -k.
curl --noproxy '*' -sS -o /dev/null --max-time 8 \
  -w 'origin HTTP %{http_code}\n' http://172.17.0.24:31085/
curl --noproxy '*' -sS -o /dev/null --max-time 10 \
  --resolve defectdojo.int.albandrieu.com:443:172.17.0.24 \
  -w 'edge HTTP %{http_code} TLS_verify=%{ssl_verify_result}\n' \
  https://defectdojo.int.albandrieu.com/
```

Le diagnostic classifie les échecs indépendants et donne plusieurs
étapes `NEXT origin`, `NEXT proxy`, `NEXT DNS` et `NEXT HTTPS` si
nécessaire. Il imprime uniquement les codes HTTP, états de conteneurs,
réseaux, DNS RCODE et réponses A ; aucun cookie, password, body ni clé API.

### Workstation — tester le résolveur réellement utilisé

```bash
dig +time=2 +tries=1 @172.17.0.24 defectdojo.int.albandrieu.com A
dig +time=2 +tries=1 @172.17.0.1 defectdojo.int.albandrieu.com A
bash scripts/workstation/diagnose-defectdojo-lan.sh --check
```

### Branches de résolution, une cause à la fois

- **Origine LAN 000/502/503, conteneur arrêté :** vérifier le front
  `defectdojo`, le serveur `defectdojo-uwsgi` et PostgreSQL partagé.
  L'App est la seule cible admissible d'une éventuelle réconciliation,
  avec `sudo bash scripts/truenas/deploy-security-tooling.sh --check defectdojo`
  **avant** de considérer `--apply defectdojo`. Ce dernier peut
  recréer/relancer des conteneurs : ne pas le lancer sur la seule panne DNS.
- **LAN HTML 200/302 mais HTTPS 404/502/503 :** vérifier l'attachement
  `traefik_network`, le router et la destination port `8080`.
  Ne pas changer les secrets Django.
- **LAN et HTTPS SNI 200/302, mais nom DNS en échec :** remettre en
  cohérence Pi-hole → pfSense/Unbound. Les preuves du 17 octobre montraient
  **Pi-hole OK et forwarding Unbound SERVFAIL/RTO élevé**, notamment avec
  une interface sortante Unbound WAN-only. Vérifier la configuration
  *Outgoing Network Interfaces* et les ACL pfSense via le runbook DNS,
  sans changer pfSense à l'aveugle ni créer un enregistrement public.
- **TLS invalide (HTTP 000, curl erreur certificat) :** vérifier le
  certificat privé et le router Traefik avec SNI. Ne pas utiliser
  `curl -k` comme preuve d'acceptation.
- **Toutes les sondes serveur OK mais navigateur KO :** vérifier le
  DNS réel du poste, le VPN, le proxy navigateur et le cache. Une
  IP cliente fixe dans le VLAN ne garantit pas que ce navigateur résolve
  la zone `.int` par Pi-hole/Unbound.

**Conserver impérativement** les données DefectDojo/PostgreSQL,
`DD_SECRET_KEY`, `DD_CREDENTIAL_AES_256_KEY` et le compte admin :
aucun réinitialiseur, aucune migration DB ou redéploiement massif.
Ne pas exposer `.int` dans le DNS public pour contourner la panne.

## Mise à jour de sécurité du diagnostic DNS (25 octobre 2026)

La PR #276 corrige les faux positifs de `diagnose-defectdojo.sh --check` :
une réponse DNS vide ne prouve **pas** que le nom privé reste confidentiel
si le serveur a expiré, retourne `SERVFAIL` ou `REFUSED`, ou réutilise
une réponse périmée `EDE: 3 (Stale Answer)`. Les seules réponses de DNS
acceptables pour qualifier un résultat A sont `NOERROR` et `NXDOMAIN`
avec un transport valide. Les tests utilisent des réponses DNS factices
et n'exécutent **aucune mutation du serveur**.

Cette validation du DNS ne constitue pas une garantie de confidentialité
sur toutes les familles d'enregistrements ou les chemins WAN. La
configuration DNS et HTTPS privée doit encore être attestée sur TrueNAS.

## Priorité runtime — interface privée indisponible (24 octobre 2026)

L'opérateur constate que `https://defectdojo.int.albandrieu.com/`
ne répond pas. La cause n'est **pas encore établie** : navigateur/DNS privé,
TLS de Traefik, service Nginx, Django/uWSGI ou PostgreSQL.
Le dernier HTTP 403 observé historiquement sur `/api/v2/` prouve
uniquement que l'API refusait une requête anonyme ; cela ne garantit pas
la page HTML de connexion.

Sur un shell **TrueNAS**, depuis le checkout canonique contenant le
diagnostic actuel (ou après revue de la PR Draft #274) :

```bash
sudo bash scripts/truenas/preflight-defectdojo.sh
sudo bash scripts/truenas/diagnose-defectdojo.sh --check
```

Le diagnostic est strictement en lecture seule et sépare :

| Couche | Observation | Interprétation |
| --- | --- | --- |
| Docker | `defectdojo`, `defectdojo-uwsgi`, `traefik` en cours d'exécution | Présence, sans garantir la réponse Django |
| TCP/HTTP LAN | `http://172.17.0.24:31085/api/v2/` | HTTP 403 attendu pour API anonyme |
| UI locale | `http://172.17.0.24:31085/` | HTTP 200 **avec `Content-Type: text/html`** ou redirection 30x = frontend accessible ; 000/401/403/404/5xx, 200 non-HTML = échec |
| DNS interne | Pi-hole `172.17.0.24` et pfSense `172.17.0.1` | doivent résoudre la cible privée |
| DNS public | `1.1.1.1` | aucune publication publique voulue |
| HTTPS privé | `curl --resolve` avec vérification TLS/SNI | doit joindre le routeur Traefik correspondant |

Un résultat `ui_origin_http=000` avec `api_http=403` signale
`api_reachable_but_ui_origin_unavailable`. Si l'UI LAN fonctionne mais
`https_http=000`, vérifier DNS/SNI et le certificat Traefik plutôt que
de modifier Django. Un 404 sur Traefik peut indiquer un routeur absent.
Aucune hypothèse ne justifie un reset de la base.

La route privée ne doit pas être exposée publiquement. Conserver
PostgreSQL, Redis, les données d'audit et les secrets de chiffrement.
Le compte Django `admin` était le seul utilisateur observé dans
l'inventaire du 23 octobre ; la rotation de son mot de passe est un
**chantier séparé**, à effectuer uniquement en mode TTY interactif
et avec synchronisation Vaultwarden, une fois l'interface joignable.

## Execution order

1. Ensure the branch is based on the current `master`. Preserve any dirty working tree; do not reset unrelated changes.
2. Regenerate `catalog/service-topology.json` with `python3 scripts/generate-service-topology.py`, inspect the diff, and commit generated outputs through the local-first quality gate.
3. Run `sudo docker compose -f apps/defectdojo/compose.yml config --quiet --no-interpolate --no-env-resolution` and `sudo bash scripts/truenas/deploy-security-tooling.sh --check defectdojo`; do not deploy while either fails.
4. In a controlled runtime window, deploy using `sudo bash scripts/truenas/deploy-security-tooling.sh --apply defectdojo`.
5. Verify DNS independently at Pi-hole and Unbound, then HTTPS directly to Traefik with SNI. Check that the hostname has **no public DNS record**.

## Read-only verification

```bash
dig +noall +comments +answer +authority @172.17.0.24 defectdojo.int.albandrieu.com A
dig +noall +comments +answer +authority @172.17.0.1 defectdojo.int.albandrieu.com A
dig +short @172.17.0.24 hello.int.albandrieu.com A
dig +short @172.17.0.1 hello.int.albandrieu.com A
sudo bash scripts/truenas/diagnose-defectdojo.sh --check
sudo docker inspect defectdojo --format '{{json .NetworkSettings.Networks}}' | jq 'keys'
curl -sS -D - -o /dev/null --max-time 10 \
  --resolve defectdojo.int.albandrieu.com:443:172.17.0.24 \
  https://defectdojo.int.albandrieu.com/
dig +short @1.1.1.1 defectdojo.int.albandrieu.com A
```

Expected: Pi-hole and Unbound both resolve the private name to `172.17.0.24`; the public resolver has no A record; Traefik returns a valid TLS response and a login redirect. A `404` from direct Traefik without Host/SNI is expected and does not test the intended router.

## Known observations

On October 17, 2026, Pi-hole returned `172.17.0.24` for Hello but no A answer for DefectDojo; pfSense/Unbound returned the public `82.66.4.247` for Hello; `pihole-dns-sync` was healthy (historical restart count 1); DefectDojo's frontend was on the `intranet` network prior to applying the merged Traefik change. The `--check` gate failed because `catalog/service-topology.json` was stale.

The DNS discrepancy requires independent diagnosis. Do not introduce a per-service pfSense Host Override unless the documented delegated-zone architecture is deliberately changed. Do not expose DefectDojo as a Hello-style public canary. No runtime acceptance is claimed by this document.

## LAN API bind and importer contract (follow-up to PR #258)

Operator observations: Docker publishes `172.17.0.24:31085` (not `127.0.0.1:31085`); unauthenticated `GET http://172.17.0.24:31085/api/v2/` returned HTTP 403; `defectdojo.int.albandrieu.com` was unresolved through the default resolver. HTTP 403 confirms a reachable HTTP endpoint, **not** a successful authenticated API call. No public exposure has been validated.

The scan importer now uses the fixed TrueNAS LAN binding `http://172.17.0.24:31085/api/v2/reimport-scan/`. The existing host checkout requirement is supplemented by a local-interface check for `172.17.0.24` prior to reading credentials or sending the scan. The endpoint is not configurable, the importer disables proxies, redirects and HTTPS downgrade/fallback, and the apply path still requires root, explicit approval and the protected token file.

Read-only checks before first import:

```bash
sudo ss -ltnp | grep ':31085'
curl --noproxy '*' --max-time 5 -sS -o /dev/null -w 'HTTP %{http_code}\n' http://172.17.0.24:31085/api/v2/
dig +short @172.17.0.24 defectdojo.int.albandrieu.com A
dig +short @172.17.0.1 defectdojo.int.albandrieu.com A
dig +short @1.1.1.1 defectdojo.int.albandrieu.com A
```

Resolve the private DNS via the canonical Pi-hole sync -> Unbound pathway; do not create an unreviewed public DNS or Cloudflare Tunnel route. Validate LAN firewall and inter-VLAN restrictions separately, as binding to an RFC1918 address does not constitute an access-control policy. Do not perform `--apply` until the authenticated endpoint, parser and engagement are approved.

## TrueNAS preflight accepted, DNS still pending (operator evidence)

On the current PR branch, `bash scripts/agent-quality-gate.sh --preflight` passed all Git-only checks including the destructive-diff guard. `br0` owns `172.17.0.24/24`, Docker publishes `8080/tcp -> 172.17.0.24:31085`, and unauthenticated `GET /api/v2/` returned HTTP 403. Queries against Pi-hole `172.17.0.24`, Unbound `172.17.0.1`, and public `1.1.1.1` produced no A records for the private DefectDojo name. These observations do **not** establish HTTPS, API authorization or firewall policy acceptance.

Next perform read-only diagnostics, preserving DNS server response codes (NXDOMAIN versus NOERROR/NODATA) and Traefik router status:

```bash
for dns in 172.17.0.24 172.17.0.1 1.1.1.1; do
  echo "== DNS ${dns} =="
  dig +time=2 +tries=1 +noall +comments +answer +authority @"${dns}" defectdojo.int.albandrieu.com A
done
sudo docker inspect defectdojo --format '{{json .NetworkSettings.Networks}}' | jq 'keys'
sudo docker inspect traefik --format '{{json .NetworkSettings.Networks}}' | jq 'keys'
curl --noproxy '*' -sS -D - -o /dev/null --max-time 10 \
  --resolve defectdojo.int.albandrieu.com:443:172.17.0.24 \
  https://defectdojo.int.albandrieu.com/
```

Do not use `curl -k` for acceptance. A missing DNS A record should be corrected in the existing label-driven Pi-hole sync path, after confirming the sync's container selection, labels and successful reconciliation. Do not create an unrelated pfSense override or public record. The `--apply` importer remains gated on approved authenticated API validation and a reviewed scan report.

## Unified read-only diagnostic

Run `sudo bash scripts/truenas/diagnose-defectdojo.sh --check` on TrueNAS. It checks the local interface, Docker networks and published port, unauthenticated HTTP reachability, internal/public DNS A answers, and verified HTTPS with SNI. It does not query API tokens, retrieve application logs, modify containers or create DNS records. Nonzero exit means at least one acceptance failure. No restart or deployment is performed automatically.

Observed failure baseline: `defectdojo` has only `intranet`, while `traefik` has `traefik_network`; both internal DNS resolvers returned NOERROR/NODATA and public DNS had no A record; HTTPS SNI returned 404. Reconcile the declared `traefik_network` attachment through an approved TrueNAS app deployment and fix Pi-hole sync before considering the service accepted. Preserve LAN-only publication and do not create a public route.

## Runtime acceptance update — October 17, 2026

The operator ran `sudo bash scripts/truenas/deploy-security-tooling.sh --apply defectdojo` successfully. TrueNAS reconciled the custom app, shared PostgreSQL and stable containers. The frontend is now attached to both `intranet` and `traefik_network` with the intended Traefik labels. HTTPS with verified TLS and SNI returns HTTP 302 to `/login?next=/`; Pi-hole `172.17.0.24` resolves the private hostname to `172.17.0.24`, and `pihole-dns-sync` logs `Added DNS: defectdojo.int.albandrieu.com -> 172.17.0.24`. Public `1.1.1.1` returns no A record. **Only pfSense/Unbound `172.17.0.1` still fails to resolve the private A record**. No authenticated API import has been tested.

The previously referenced `scripts/truenas/verify-pihole-dns-sync.sh` is not available in the operator's checkout; use the existing `diagnose-defectdojo.sh` and DNS queries below. The diagnostic's expected nonzero exit is currently attributable to Unbound only. Do not restart pfSense or alter public DNS to repair this.

```bash
# Distinguish a missing forwarder/delegation from stale cache without changing DNS.
for name in defectdojo.int.albandrieu.com hello.int.albandrieu.com; do
  for resolver in 172.17.0.24 172.17.0.1; do
    echo "=== $resolver $name ==="
    dig +time=2 +tries=1 +noall +comments +answer +authority @"$resolver" "$name" A
  done
done
# Inspect existing Unbound domain override / forwarding for int.albandrieu.com
# in pfSense UI or its read-only configuration audit; preserve canonical ownership.
```

A successful pfSense query must return `172.17.0.24` for DefectDojo without exposing the name publicly. Investigate Unbound forwarding/delegation and DNSSEC validation behavior before considering cache flushes or configuration changes.

## DNS split-view investigation — operator evidence

The operator observed `defectdojo.int.albandrieu.com` at Pi-hole `172.17.0.24` as A `172.17.0.24` with TTL 0 and `EDE: 3 (Stale Answer)` (no AA), while Unbound `172.17.0.1` returned NOERROR/NODATA with Cloudflare SOA. For `hello.int.albandrieu.com`, Pi-hole returned authoritative (`aa`) A `172.17.0.24`, whereas Unbound returned public A `82.66.4.247`. This is a **split-view DNS configuration issue**, not a DefectDojo routing issue; Traefik HTTPS already returned 302 with verified TLS. Do not assert Pi-hole DefectDojo authoritative health solely from its stale answer.

Read-only follow-up on TrueNAS:

```bash
# Compare uncached-looking query types and full flags; do not flush caches yet.
for dns in 172.17.0.24 172.17.0.1; do
  for name in defectdojo.int.albandrieu.com hello.int.albandrieu.com; do
    echo "=== $dns $name ==="
    dig +time=2 +tries=1 +noall +comments +answer +authority @"$dns" "$name" A
  done
done
sudo docker logs --since 30m pihole-dns-sync 2>&1 | grep -Ei 'defectdojo|sync|error|warn' | tail -40
```

Review pfSense DNS Resolver domain overrides / forwarding for `int.albandrieu.com`, DNSSEC behavior and Pi-hole local DNS record materialization in read-only mode. Avoid a single-name Host Override, public DNS changes, or disabling DNSSEC as a workaround. Only after confirming canonical private-zone ownership should forwarding to Pi-hole be proposed; take care to avoid a Pi-hole → Unbound → Pi-hole forwarding loop.

## Unbound incident correlation and missing private forward — 2026-10-17

The operator's `unbound-control -c /var/unbound/unbound.conf lookup defectdojo.int.albandrieu.com` selected Cloudflare authoritative nameservers (`poppy`, `vasilii`) instead of the expected Pi-hole forwarder. This is strong evidence that the active Unbound view is **not** applying the documented `int.albandrieu.com -> 172.17.0.24` Domain Override; verify effective generated config, view selection, and whether the override survived yesterday's Unbound outage before editing. The public DNS records `hello.int.albandrieu.com`, `int.albandrieu.com`, `home.albandrieu.com` point to WAN `82.66.4.247` (operator Cloudflare inventory); Hello is a documented temporary public canary, not a model for DefectDojo.

Historical precedent: `docs/incidents/2026-10-08-pfsense-unbound-oom-wan-exposure.md` records Unbound being killed by kernel memory reclaim on Netgate 1100, with CrowdSec failed-send busy-spin and pfBlockerNG ASN retries as contributors. **Do not assume yesterday's failure had the same cause without logs.** Capture current-boot and previous-day kernel/service evidence before restarting or flushing DNS.

On pfSense interactive tcsh (read-only, one command per line):

```text
unbound-control -c /var/unbound/unbound.conf status
unbound-control -c /var/unbound/unbound.conf lookup defectdojo.int.albandrieu.com
grep -nE 'int[.]albandrieu[.]com|172[.]17[.]0[.]24|forward-zone|forward-addr|domain-insecure|private-domain' /var/unbound/unbound.conf
dmesg | egrep -i 'unbound|killed|failed to reclaim|out of swap' | tail -60
ps axo pid,rss,vsz,pcpu,pmem,command | sort -nr -k2 | head -20
unbound-control -c /var/unbound/unbound.conf stats_noreset | egrep '^mem[.]'
```

From workstation run the existing read-only `scripts/pfsense/diagnose-recover.sh --check` and `scripts/pfsense/audit-posture.sh --ssh home.albandrieu.com` with existing SSH configuration. Redact secrets and avoid pasting `/conf/config.xml` wholesale. Do not add HAProxy WAN routing for private DefectDojo; DNS must be fixed first. No appliance mutation or recovery action is approved by this runbook.

## Confirmed pfSense OOM and absent generated override — operator evidence, October 17

The operator reports Unbound 1.26.1 currently running (PID 87675, uptime 45004 seconds), Python/validator/iterator modules. The generated `/var/unbound/unbound.conf` produced **no matches** for the expected `int.albandrieu.com`, Pi-hole address, forward-zone/forward-addr or split-domain directives. Combined with `unbound-control lookup` selecting Cloudflare nameservers, the active private-zone forwarding contract is absent. Verify whether the persisted pfSense Domain Override exists and why the generated config differs before modifying it. Do not add a DefectDojo-specific HAProxy route or Cloudflare record.

The current kernel ring buffer explicitly contains `pid 84666 (unbound) ... was killed: failed to reclaim memory`, alongside two PHP processes and netstat killed for the same reason. This **confirms a global memory-reclaim failure** during the observed incident, though the precise timestamp and trigger require logs. Current Unbound RSS was 131704 KiB (~129 MiB); Snort ~59 MiB, php_pfb ~50 MiB, and multiple PHP-FPM workers ~45–50 MiB each. Do not conflate process RSS totals with unique physical memory. Capture memory headroom, OOM log timestamps and pfBlockerNG/CrowdSec states before recovery. See `docs/incidents/2026-10-08-pfsense-unbound-oom-wan-exposure.md` for a prior confirmed OOM and mitigations; do not assume the same trigger.

The operator executed `scripts/pfsense/diagnose-recover.sh --check` from the TrueNAS checkout. HTTPS/API probes passed, but SSH on default port 22 timed out (exit 255), so deep evidence was **not collected**. `audit-posture.sh --ssh home.albandrieu.com` likewise timed out on port 22. Do not report the partial API diagnosis as a complete pfSense audit. The suggested workstation path `~/w/nabla-compose` did not exist on TrueNAS; on TrueNAS use `/mnt/cpool/compose/nabla-compose` and on the workstation use its actual checkout path.

New bounded read-only script (run from a host with working pfSense SSH alias/port):

```bash
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check --target home.albandrieu.com
# If the SSH service uses a nonstandard port:
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check --target home.albandrieu.com --port YOUR_SSH_PORT
```

This script collects Unbound status, effective forward directives, lookup selection, kernel OOM evidence, top memory processes and Unbound counters without dumping credentials or modifying pfSense. If SSH remains blocked, use the already available pfSense console to run the documented individual read-only commands. Do not attempt brute-force port discovery or enable WAN SSH for this audit.

## Correction of execution host and SSH preflight — 2026-10-17

Correction to the preceding incident narrative: the operator executed `scripts/pfsense/diagnose-recover.sh --check` and `audit-posture.sh --ssh home.albandrieu.com` **from the workstation**, not TrueNAS. The `cd ~/w/nabla-compose` command had failed in the particular shell, but the subsequent commands ran from an existing checkout; do not infer execution host from the failed `cd` alone. The workstation's `ssh -G home.albandrieu.com` reports user `albandrieu`, hostname `home.albandrieu.com`, port `22`. A TCP timeout on port 22 is a connectivity/filtering/listener problem, **not** proof of missing SSH credentials. The operator's `--port PORT_SSH` invocation was rejected by the script's numeric-port validation; `PORT_SSH` was documentation placeholder text, not a real port.

Workstation read-only checks (run from the actual checkout):

```bash
ssh -G home.albandrieu.com | grep -E '^(hostname|user|port|identityfile) '
ssh -o BatchMode=yes -o ConnectTimeout=5 -o ConnectionAttempts=1 -vv home.albandrieu.com true
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check --target home.albandrieu.com
```

Use the **actual** SSH port if known; never paste `PORT_SSH` literally. For local workstation-to-pfSense testing, prefer the LAN IP `172.17.0.1` if reachable and explicitly authorized, as the public hostname can follow different WAN/firewall policy. On TrueNAS, inspect the SSH configuration and key availability **separately**, without copying workstation private keys or enabling new WAN access. A TCP timeout occurs before public-key authentication and cannot establish whether a key exists. Do not paste private keys, complete verbose logs containing sensitive identifiers, or modify pfSense SSH exposure as a workaround.

## Workstation SSH access and Unbound audit accepted — 2026-10-17

The workstation's effective `ssh -G home.albandrieu.com` resolves to `user admin`, `port 9922`, `identityfile ~/.ssh/id_ed25519`. `ssh-add -l` lists agent identities; **no private key should be copied to TrueNAS**. SSH to `172.17.0.1:22` times out, which is consistent with the wrong port, not proof of missing keys. The earlier `user albandrieu, port 22` output was from a different SSH configuration/context; the later workstation result is the successful configuration. The read-only SSH diagnostic completed against the hostname with no explicit port, proving remote access through the workstation alias.

The diagnostic returned Unbound 1.26.1, running PID 87675, uptime 45597 seconds; no generated `int.albandrieu.com` forwarding directive; public Cloudflare authoritative lookup; and kernel OOM kills for Unbound PID 84666, two PHP processes and netstat. Current Unbound RSS 131148 KiB (~128 MiB), Snort 60644 KiB, php_pfb 51172 KiB, with multiple PHP-FPM workers around 48–55 MiB RSS each. The reported Unbound cache/module counters are far below total RSS; RSS includes other allocations and shared memory, so these numbers alone do not identify the culprit. Collect dated kernel/system logs and pfSense config persistence before any change.

The SSH diagnostic can be run on the workstation using its alias:

```bash
cd ~/w/nabla-compose
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check --target home.albandrieu.com
bash scripts/pfsense/audit-posture.sh --ssh home.albandrieu.com
```

Do not use `172.17.0.1:22` as the SSH target. On TrueNAS, validate a separate authorized SSH identity and port before any remote automation; do not infer that workstation SSH credentials exist there. Before restoring a Domain Override, verify Pi-hole's upstream DNS path is not Unbound for `int.albandrieu.com`, to avoid a forwarding loop. Prefer a reviewed, persistent pfSense UI/API change with read-only pre/post checks; do not edit generated `/var/unbound/unbound.conf` manually.

## Domain Override applied: forwarding timeout, Hello public fallback — 2026-10-17 23:25 CEST

After adding the `int.albandrieu.com` Domain Override, Unbound restarted (PID 55374, uptime 110 seconds). `unbound-control lookup defectdojo.int.albandrieu.com` now reports `forwarding request` to `172.17.0.24`, but with `rto 24064 msec`; direct `dig @172.17.0.1` returns SERVFAIL for DefectDojo and Hello, while the existing Vaultwarden Host Override returns authoritative A `172.17.0.24`. Pi-hole directly returns private A records for DefectDojo and Hello; verified Traefik HTTPS for DefectDojo returns 302. Therefore the remaining fault is **Unbound-to-Pi-hole forwarding reachability/behavior**, not missing domain configuration or Traefik routing.

Hello still resolves via public Cloudflare DNS `82.66.4.247` and may work through that WAN ingress or client DNS cache/fallback despite Unbound SERVFAIL; its success is **not** proof that split DNS works. DefectDojo has no public A record and must stay private. Authenticated Cloudflare inventory reports one unexpected public `.int` DNS record: inspect the detailed audit report and its exact hostname before any deletion; the public Hello exception is intentional and may not be the unexpected record.

Read-only, run from workstation and TrueNAS to isolate source-specific DNS behavior:

```bash
# On workstation: check effective LAN and public answers separately.
dig +time=2 +tries=1 @172.17.0.1 hello.int.albandrieu.com A
dig +time=2 +tries=1 @172.17.0.24 hello.int.albandrieu.com A
dig +time=2 +tries=1 @1.1.1.1 hello.int.albandrieu.com A
# On pfSense via the configured SSH alias: check LAN routing and interface policy.
ssh home.albandrieu.com 'netstat -rn -f inet | grep 172.17; grep -nE "outgoing-interface|interface:|forward-addr|private-domain|domain-insecure" /var/unbound/unbound.conf'
# On TrueNAS: inspect Pi-hole DNS listener and direct query.
sudo ss -lunpt | grep ':53 '
dig +time=2 +tries=1 @172.17.0.24 defectdojo.int.albandrieu.com A
```

Check pfSense DNS Resolver **Outgoing Network Interfaces**; previous incidents showed a WAN-only setting causing exactly this forwarding failure, whereas `All` allowed reaching the LAN Pi-hole. Do not change settings, flush cache, restart Unbound, or publish DefectDojo until source-specific reachability and the Pi-hole upstream path have been verified. Check for a Pi-hole→Unbound→Pi-hole forwarding loop. The existing `scripts/security/diagnose-private-int-dns.sh --check` correctly reports the DNS failure, but its simple A-value check does not prove Pi-hole's answer is authoritative rather than stale (EDE 3).
