# Exposition WAN : HAProxy, Cloudflare Tunnel, DNS, PF

**Référence 27 octobre 2026.** Les intentions de sécurité sont dans
`config/ingress-access-policy.json`. Le fichier fourni par l'opérateur,
`/var/etc/haproxy/haproxy.cfg` (généré à 20:47), a été enregistré sous
`docs/evidence/pfsense/haproxy-2026-10-27.generated.redacted.cfg`,
**expurgé et non déployable**. Aucun certificat, secret, IP WAN ou
adresse source externe n'a été délibérément conservé dans cette preuve.
Ne jamais éditer le fichier généré sur pfSense ni enregistrer la version
brute dans Git.

## Matrice de décision

| Hôte | HAProxy attendu sur WAN | DNS public | Tunnel | PF/NAT | État connu |
| --- | --- | --- | --- | --- | --- |
| `nexus.int.albandrieu.com` | 403 | Absent | Absent | Bloquer origine directe | Refus 403 observé depuis le LAN vers IP WAN ; WAN réel inconnu |
| `vault.int.albandrieu.com` | Refus | Absent | Absent | Bloquer origine directe | ACL sans refus : dérive à traiter |
| `vaultwarden.int.albandrieu.com` | Refus | Absent | Absent | Bloquer origine directe | Alias historique non couvert par ACL explicite |
| `s3.int.albandrieu.com` | **Refus obligatoire** | **Absent attendu** | Absent | Bloquer origine directe | **Dérive : ACL sans deny ; DNS public présent au dernier relevé** |
| `hello.int.albandrieu.com` | Exception temporaire | Exception temporaire | Pas requis | WAN 443 selon politique | Exception dans `config/public-int-dns-exceptions.txt` |
| `nexus.albandrieu.com` | Ne pas impacter | À vérifier | À vérifier | À vérifier | Chemin public indépendant |
| `vaultwarden.albandrieu.com` | Non propriétaire | À vérifier | Tunnel + Access attendus | Origine directe non publiée | Access non attesté |

**S3 : décision définitive de l'opérateur le 27 octobre 2026.**
L'API `s3.int.albandrieu.com` est **LAN uniquement**, sans
exception WAN. Les anciennes descriptions publiques dans
`docs/dns-ingress-ownership.md` et `apps/garage/compose.yml`
étaient une confusion avec **l'interface Web Garage**
`garage.albandrieu.com`, distincte du service S3 :3900.
Le dernier collecteur DNS public a observé `present` pour S3
(deux résolveurs récursifs) ; vérifier l'autorité et la chaîne
DNS avant de supprimer une entrée. Le frontend HAProxy contient
`acl s3` sans action `deny`, et la route générique
`*.int` existe : bloquer le Host S3 **sur le frontend WAN**
en conservant la route Traefik directe LAN. Ne pas modifier
automatiquement les règles pfSense ou les clients OpenTofu.

L'interface Web Garage `garage.albandrieu.com` peut être
publiée via Cloudflare Tunnel, **avec vérification séparée
de la politique Access**. L'API d'administration Garage
`garage-admin.albandrieu.com` n'est pas assimilée à l'UI ;
elle nécessite une restriction spécifique.

**Vault :** la configuration fournie contient une ACL `vault`
mais aucun refus HTTP ciblé. Une ACL seule ne bloque rien.
Le frontend `main_Web_HTTPS` conserve une route générique
`if int aclcrt_main_Web_HTTPS` vers Traefik : accès potentiellement
possible selon les routes Traefik. Ceci n'est pas une preuve WAN.

**Autre chantier distinct :** `prod_front-traefik-https_ipvANY`
utilise `ssl verify none` ; la connexion backend est chiffrée
mais le certificat n'est pas authentifié. Prévoir une
vérification TLS séparée du contrôle d'accès.

## Remédiation à préparer dans pfSense (aucune règle appliquée ici)

Sur le frontend WAN `main_Web_HTTPS`, créer **de nouvelles ACL**
indépendantes des ACL de routage. Rendu HAProxy cible à valider
après configuration dans l'UI pfSense :

```haproxy
acl s3_private_wan req.hdr(host) -m reg -i ^([^.]+\.)*s3\.int\.albandrieu\.com(:[0-9]{1,5})?$
acl vault_private_wan req.hdr(host) -m reg -i ^vault\.int\.albandrieu\.com(:[0-9]{1,5})?$
acl vaultwarden_legacy_private_wan req.hdr(host) -m reg -i ^vaultwarden\.int\.albandrieu\.com(:[0-9]{1,5})?$
http-request deny deny_status 403 if s3_private_wan
http-request deny deny_status 403 if vault_private_wan
http-request deny deny_status 403 if vaultwarden_legacy_private_wan
```

Ces règles bloquent les Host privés sur le frontal WAN sans
bloquer les connexions LAN directes à TrueNAS Traefik. Le
motif S3 couvre aussi les hostnames bucket, puisque le routeur
Traefik Garage accepte `*.s3.int.albandrieu.com`.
Le frontal ne doit pas confondre ces noms avec
`garage.albandrieu.com` (WebUI publique sous Access).

**Avant Apply :** exporter la configuration pfSense, vérifier
l'ordre des règles et la syntaxe HAProxy, identifier les
utilisateurs actuels de S3/OpenTofu, préparer le rollback.
**Après Apply :** contrôler le chargement HAProxy, le 403 du
Host S3 et de ses sous-domaines depuis le chemin d'entrée WAN,
le 200/403 S3 applicatif attendu depuis le LAN, et l'absence
de régression de `garage.albandrieu.com`, Hello et Nexus public.
Un 403 depuis LAN via IP publique n'est pas une preuve
de protection depuis une source WAN externe. Vérifier les
enregistrements DNS publics avec l'autorité et les CNAME.
## Diagnostic depuis le snapshot (sans réseau)

```bash
just nexus-private-ingress-test

python3 scripts/pfsense/audit-haproxy-ingress.py

# Mode strict : code 2 attendu tant que Vault/S3 ne sont pas résolus.
just pfsense-haproxy-policy-check
```

Les états sont `DECLARED_DENY_NOT_WAN_PROOF`,
`VIOLATION_NO_EXPLICIT_DENY`, `VIOLATION_NO_EXACT_ACL`,
`VIOLATION_NO_EXPLICIT_DENY` ou `NOT_VERIFIED`. Les couches
Cloudflare/DNS/PF sont inconnues sans preuve externe.
Un échec du gate strict **n'est pas une panne de pfSense** :
il empêche de déclarer la conformité.

## Comparaison avec le fichier HAProxy généré actuel

```bash
# Depuis la workstation, en lecture seule par SSH vers pfSense.
just pfsense-haproxy-policy-live

# Ou, avec rapport d'écart des ACL/règles/serveurs pertinents :
python3 scripts/pfsense/audit-haproxy-ingress.py --live
```

Le script lit `/var/etc/haproxy/haproxy.cfg` en mémoire,
n'imprime pas la configuration brute et compare les directives
sensibles à la politique avec le snapshot. Il ne prétend pas
vérifier tous les champs HAProxy, ni la configuration effectivement
chargée en mémoire.

Capture revue, facultative, **toujours expurgée** :

```bash
python3 scripts/pfsense/audit-haproxy-ingress.py --live \
  --capture /tmp/haproxy-current.generated.redacted.cfg
```

Inspecter la capture, ses masquages et son diff avant toute mise
à jour de l'instantané Git. Ne pas publier `config.xml`, clés,
certificats ou dumps de jetons.

## Contrôles indépendants par couche

### DNS

```bash
for host in nexus.int.albandrieu.com vault.int.albandrieu.com \
            vaultwarden.int.albandrieu.com s3.int.albandrieu.com \
            hello.int.albandrieu.com; do
  echo "== $host =="
  dig +time=2 +tries=1 @172.17.0.1 "$host" A +short
  dig +time=2 +tries=1 @1.1.1.1 "$host" A +short
  dig +time=2 +tries=1 @1.1.1.1 "$host" AAAA +short
  dig +time=2 +tries=1 @1.1.1.1 "$host" CNAME +short
done
```

Le DNS privé correct **n'est pas une règle de pare-feu**.
L'absence de DNS public ne prouve pas que l'on ne peut pas
atteindre HAProxy par IP publique en forçant Host/SNI.

### Collecteur DNS public versionné

```bash
# Depuis la workstation : lecture de deux résolveurs publics.
just ingress-public-dns-evidence

# Conserver seulement les observations DNS dans un fichier temporaire.
python3 scripts/ingress/collect-public-dns-evidence.py \
  > /tmp/ingress-public-dns-evidence.json

# Injecter l'observation DNS dans l'audit multi-couche.
python3 scripts/pfsense/audit-haproxy-ingress.py \
  --evidence /tmp/ingress-public-dns-evidence.json
```

Le collecteur vérifie A, AAAA et CNAME via 1.1.1.1 et 9.9.9.9 ;
une erreur réseau, une réponse SERVFAIL ou une divergence entre
résolveurs est classée **unknown**, pas « absent ». Il n'affirme
rien sur les règles HAProxy, PF, Tunnel ou Access.

### Cloudflare Tunnel + Access

Réutiliser l'outil existant `scripts/cloudflare/diagnose-cloudflare-api.py`
avec ses identifiants en environnement privé ; contrôler l'inventaire
des `ingress[].hostname` et les politiques Access associées.
**Tunnel sain ≠ autorisation correcte**. Un Tunnel absent
n'empêche pas le routage WAN direct HAProxy. Un hostname public
Vaultwarden par Tunnel doit être audité séparément de
`vault.int.albandrieu.com`.

### pfSense PF/NAT

Sur pfSense, avec accès autorisé, les lectures sont :

```sh
pfctl -sr
pfctl -sn
```

Ne pas publier ces sorties intégrales (topologie privée).
PF protège des **IP/ports/flux**, pas le Host HTTP ici.
Le refus du Host se fait dans HAProxy ; PF/NAT doit empêcher
les contournements directs de l'origine Nexus :8081, Vault,
Traefik :443 et services privés, en tenant compte des exceptions
publiques. Une règle WAN 443 peut rester nécessaire à Hello.

### Test HAProxy / Traefik indépendant

```bash
curl --noproxy '*' --connect-timeout 3 --max-time 10 \
  --resolve nexus.int.albandrieu.com:443:82.66.4.247 \
  -o /dev/null -sS \
  -w 'hairpin=%{http_code} tls=%{ssl_verify_result}\n' \
  https://nexus.int.albandrieu.com/

curl --noproxy '*' --connect-timeout 3 --max-time 10 \
  --resolve nexus.int.albandrieu.com:443:172.17.0.24 \
  -o /dev/null -sS \
  -w 'lan_direct=%{http_code} tls=%{ssl_verify_result}\n' \
  https://nexus.int.albandrieu.com/
```

Le 27/10, `hairpin=403` et `tls=0` ont été observés
depuis la workstation **dans le LAN**. NAT reflection possible :
cela ne valide pas un client Internet. La nouvelle règle HAProxy
a été retrouvée dans le frontend généré, avec capture Host
avant le deny. Son chargement effectif et le rejet WAN indépendant
doivent être vérifiés avant l'activation du routeur Nexus.

## Clôture

Appliquer et vérifier la politique S3 privée, corriger Vault et l'alias legacy,
valider les routes publiques conservées, collecter les preuves
Cloudflare Tunnel/Access, DNS public et PF/NAT, puis vérifier
l'isolation effective depuis une source WAN indépendante.
**Un diagnostic non exécuté = NOT_VERIFIED, jamais PASS.**
