# Incident Vaultwarden : split-DNS public vers TrueNAS — 2026-10-10

Status: **cause racine et objet pfSense confirmés ; correction DNS toujours à appliquer ; secrets/cutover CrowdSec bloqués par cette dépendance**.

## Résumé

Le hostname public `vaultwarden.albandrieu.com` est correctement publié dans
Cloudflare Tunnel vers `http://172.17.0.24:30032`, et l'origine Vaultwarden
répond correctement en local. Pourtant, depuis TrueNAS, le même hostname
retournait `HTTP 404`.

La cause n'est ni Vaultwarden ni Cloudflare Tunnel : le resolver LAN
pfSense/Unbound répond `172.17.0.24` pour le hostname public. TrueNAS contourne
donc Cloudflare et contacte directement son propre port `:443`, qui n'est pas
le port Vaultwarden `:30032`.

La workstation suit la résolution publique Cloudflare et obtient bien
`HTTP 200`.

## Preuves

### Origine Vaultwarden saine

Depuis TrueNAS :

```text
curl http://127.0.0.1:30032/api/config
HTTP/1.1 200 OK

environment.api      = https://vaultwarden.albandrieu.com/api
environment.identity = https://vaultwarden.albandrieu.com/identity
server.name          = Vaultwarden
version              = 2026.6.0
```

### Tunnel Cloudflare sain

Le diagnostic read-only du Tunnel
`1d98bede-6fa0-42a8-971c-cd390d74d7f6` confirme :

```text
status=healthy
config_src=cloudflare
vaultwarden.albandrieu.com -> http://172.17.0.24:30032
expected hostname: present
Access application: present
```

Depuis la workstation, le chemin public fonctionne :

```text
curl https://vaultwarden.albandrieu.com/api/config
HTTP 200
```

### Divergence DNS sur TrueNAS

```text
getent ahostsv4 vaultwarden.albandrieu.com
172.17.0.24

dig +short A vaultwarden.albandrieu.com
172.17.0.24

dig +short A vaultwarden.albandrieu.com @172.17.0.1
172.17.0.24

dig +short A vaultwarden.albandrieu.com @1.1.1.1
188.114.96.2
188.114.97.2
```

Le resolver LAN réécrit donc le hostname public vers TrueNAS.

### Le 404 ne vient pas de Vaultwarden

```text
curl -sv https://vaultwarden.albandrieu.com/api/config
* Trying 172.17.0.24:443...
* Connected to vaultwarden.albandrieu.com (172.17.0.24) port 443
< HTTP/2 404
```

Le port public attendu de Vaultwarden est `30032`, pas `443`. Le client
atteint donc un autre frontend local.

En forçant une IP Cloudflare tout en conservant le hostname/SNI :

```text
curl --resolve vaultwarden.albandrieu.com:443:188.114.96.2 \
  https://vaultwarden.albandrieu.com/api/config
```

la réponse redevient `HTTP 200`. Cela prouve que TLS, SNI, Cloudflare Tunnel
et l'origine Vaultwarden sont fonctionnels.

## Terminologie : split-DNS, pas hairpin NAT

Le terme « hairpin local » a été utilisé pendant le diagnostic comme raccourci,
mais le mécanisme observé est plus précisément un **split-DNS / DNS override**.

Le vrai hairpin NAT / NAT reflection serait :

```text
client LAN -> IP publique WAN -> routeur/NAT -> service LAN
```

Ici le chemin est différent :

```text
TrueNAS
  -> DNS LAN répond 172.17.0.24
  -> connexion directe 172.17.0.24:443
  -> Cloudflare Tunnel entièrement bypassé
```

Il n'y a donc pas de traversée WAN suivie d'un retour sur le LAN.

## Impact

1. `bw login` sur TrueNAS échoue avant authentification avec
   `404 page not found`, car le CLI appelle le hostname public via le mauvais
   chemin local.
2. `configure-bitwarden-cli-local.sh --check` échoue de la même manière.
3. Un test effectué uniquement depuis une workstation peut être vert alors que
   TrueNAS voit une autre destination pour le même hostname.
4. Un `curl` direct sur `:30032` prouve seulement l'origine, pas le chemin
   du hostname public.
5. Le `404` est trompeur : il ressemble à une route Cloudflare/Vaultwarden
   manquante alors qu'il provient d'un frontend local atteint à cause du DNS.

## Symptômes secondaires observés

### Bitwarden CLI sur workstation

La workstation atteint correctement le endpoint public, mais une session CLI
existante a produit :

```text
UserKeyIdBackfillMigration ... User key is not available in key store
invalid_grant
ERR_UNHANDLED_REJECTION
```

Ce symptôme est distinct de la RCA DNS TrueNAS. Il peut correspondre à un état
de session CLI ancien/incompatible et doit être diagnostiqué séparément avant
toute migration de secrets.

### Renderer Python sur workstation

`render_from_bitwarden.py` a échoué avec :

```text
ModuleNotFoundError: No module named 'jsonschema'
```

C'est une dette d'environnement Python local, pas une panne Vaultwarden. Elle
n'est pas prioritaire pour le cutover CrowdSec actuel.

### `BW_SESSION`

Après un `bw unlock --raw` en erreur, ne considérer `BW_SESSION` comme valide
que si `bw status` confirme explicitement `status=unlocked`. La simple
présence de la variable d'environnement n'est pas une preuve suffisante.

## Contrat d'architecture attendu

Pour un service exposé par Cloudflare Tunnel sous un hostname public
`*.albandrieu.com` :

```text
LAN / TrueNAS
  -> pfSense/Unbound
  -> résolution publique Cloudflare
  -> edge Cloudflare
  -> Tunnel
  -> origine LAN explicite
```

Ne pas créer de host override LAN du même hostname public vers
`172.17.0.24` sauf si le service possède un contrat d'ingress local équivalent
sur le même port/protocole et que le bypass de Cloudflare est intentionnel.

Pour l'accès privé direct, préférer un hostname distinct sous
`*.int.albandrieu.com`.

## Vérifications de non-régression

```bash
getent ahostsv4 vaultwarden.albandrieu.com
dig +short A vaultwarden.albandrieu.com @172.17.0.1
dig +short A vaultwarden.albandrieu.com @1.1.1.1
curl -sv https://vaultwarden.albandrieu.com/api/config \
  -o /dev/null 2>&1 |
  grep -E 'Trying |Connected to|< HTTP|server:|cf-ray:'
curl -fsS http://127.0.0.1:30032/api/config | jq .
```

Pour un hostname tunnelé, la vue LAN ne doit plus pointer directement vers
`172.17.0.24` sans exception documentée.

## Actions ouvertes

- [x] source exacte confirmée : DNS Resolver Host Override pfSense
  `host=vaultwarden`, `domain=albandrieu.com`, `ip=172.17.0.24` ;
- [ ] supprimer/corriger cet override public sans affecter
  `vaultwarden.int.albandrieu.com` ;
- ajouter un contrôle automatisé détectant les hostnames publics tunnelés qui
  résolvent vers une IP LAN depuis le resolver pfSense ;
- seulement ensuite revalider le Bitwarden CLI sur TrueNAS ;
- traiter séparément la session CLI workstation et la dépendance Python
  `jsonschema` ;
- ne pas utiliser ces dettes pour bloquer inutilement la stabilisation du moteur
  CrowdSec central déjà sain.


## RCA affinée — source runtime pfSense

Le diagnostic du 10 octobre 2026 a localisé l'entrée fautive dans :

```text
/var/unbound/host_entries.conf
```

Ce fichier est généré par pfSense lors de la génération Unbound. Le code pfSense
`unbound_add_host_entries()` appelle `system_hosts_entries()`, qui agrège les
entrées locales système, les DNS Resolver Host Overrides et, lorsque
l'enregistrement des mappings statiques est actif, les mappings DHCP statiques.

Conséquence opératoire : **ne jamais éditer `host_entries.conf` directement**.
Il faut identifier l'objet de configuration source (Host Override, mapping DHCP
statique ou entrée locale système), le corriger, puis laisser pfSense régénérer
Unbound.

La présence de l'entrée dans `host_entries.conf` avec absence du FQDN complet
dans `/conf/config.xml` n'est pas contradictoire : pfSense peut stocker
`host=vaultwarden` et `domain=albandrieu.com` dans des champs distincts.


## Objet de configuration source confirmé

Le diagnostic SSH a ensuite identifié l'objet source exact dans
`/conf/config.xml` :

```xml
<hosts>
  <host>vaultwarden</host>
  <domain>albandrieu.com</domain>
  <ip>172.17.0.24</ip>
  <descr><![CDATA[For bitwarden api intenal acces]]></descr>
  <aliases></aliases>
</hosts>
```

Cet objet Unbound génère les lignes suivantes dans
`/var/unbound/host_entries.conf` :

```text
local-data-ptr: "172.17.0.24 vaultwarden.albandrieu.com"
local-data: "vaultwarden.albandrieu.com. A 172.17.0.24"
```

La cause racine du split-DNS est donc un **DNS Resolver Host Override pfSense
historique**, créé pour l'accès interne à l'API Bitwarden/Vaultwarden.

Correction attendue :

1. supprimer l'override public `vaultwarden.albandrieu.com -> 172.17.0.24` ;
2. si un nom LAN direct est encore utile, utiliser
   `vaultwarden.int.albandrieu.com -> 172.17.0.24` ;
3. laisser pfSense régénérer `host_entries.conf` ;
4. vérifier que `dig @172.17.0.1 vaultwarden.albandrieu.com` retourne ensuite
   les IP Cloudflare publiques et que le hostname `.int` reste privé.

Ne pas éditer `host_entries.conf` directement : il est dérivé de
`/conf/config.xml`.


## Incident réobservé — CrowdSec cutover, 2026-10-10

Le rendu du secret `crowdsec` a remis ce défaut sur le chemin critique :

```text
bw login
Unable to fetch ServerConfig from https://vaultwarden.albandrieu.com/api
404 page not found
```

Le comportement est identique à la RCA ci-dessus : le CLI n'atteint pas
Cloudflare depuis TrueNAS tant que le Host Override public reste actif. Le
CrowdSec central et la connectivité pfSense -> LAPI `172.17.0.24:8084` sont
déjà sains ; **ne pas contourner** cette dette en copiant le secret depuis un
autre hôte ou en donnant à TrueNAS un accès administratif pfSense.

Ordre de reprise :

1. supprimer le Host Override public dans pfSense DNS Resolver ;
2. conserver/créer séparément `vaultwarden.int.albandrieu.com -> 172.17.0.24`
   si l'accès LAN direct est requis ;
3. laisser pfSense régénérer Unbound ;
4. depuis TrueNAS, exiger que le resolver LAN et le chemin HTTPS public ne
   pointent plus vers `172.17.0.24:443` ;
5. seulement ensuite relancer `configure-bitwarden-cli-local.sh --apply`,
   `bw login`, `bw unlock` et le renderer CrowdSec.


### After pfSense override rename — residual TrueNAS NSS override

The operator renamed the pfSense Host Override from `vaultwarden` to
`bitwarden`. After that change, direct DNS queries were corrected:

```text
dig @172.17.0.1 vaultwarden.albandrieu.com -> 188.114.96.2 / 188.114.97.2
dig @1.1.1.1 vaultwarden.albandrieu.com   -> 188.114.96.2 / 188.114.97.2
```

However, the TrueNAS system resolver still returned:

```text
getent ahostsv4 vaultwarden.albandrieu.com -> 172.17.0.24
curl https://vaultwarden.albandrieu.com/... -> Trying 172.17.0.24:443 -> HTTP 404
```

Therefore the pfSense public override is no longer the active source of the
remaining wrong answer. The residual mapping is now local to the TrueNAS NSS /
resolver path (for example `/etc/hosts`, `hosts:` ordering, or a local cache).
Do not change pfSense again until that local source is identified.

The local Vaultwarden origin remains healthy:
`http://127.0.0.1:30032/api/config` returns the expected Vaultwarden config.
