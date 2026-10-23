# 2026-10-23 — Sample / Chrome ECH : override public Pi-hole vers TrueNAS

## Statut
Cause racine **prouvée**. Pi-hole public override **supprimé par l'opérateur**
le 23 octobre dans l'interface Pi-hole, DNS public réparé. La restauration
**persistante du DNS workstation** n'est pas encore validée ; un profil
NetworkManager incorrect reste présent. Aucune correction réseau n'a été
appliquée automatiquement par l'agent.
L'accès Web est temporairement restauré sur la workstation via un choix
explicite de pfSense/Unbound. Aucun redémarrage, changement DNS/pare-feu
ou déploiement applicatif n'a été effectué lors du diagnostic.

## Symptôme et preuves

- Chrome sur le LAN : `ERR_ECH_FALLBACK_CERTIFICATE_INVALID` pour
  `https://sample.albandrieu.com/api`.
- FastAPI sur TrueNAS : `/health` local et LAN `200`, conteneur
  `fastapi-sample` `running (healthy)` sur `172.17.0.24:8091`.
- DNS explicite pfSense `dig @172.17.0.1 sample.albandrieu.com A` :
  IPv4 Cloudflare (`188.114.96.2`, `188.114.97.2`).
- DNS explicite Pi-hole `dig @172.17.0.24 sample.albandrieu.com A` :
  **`172.17.0.24`** ; le nom privé
  `sample.int.albandrieu.com` doit au contraire y aboutir.
- Pi-hole : `/etc/pihole/pihole.toml` contenait une ligne
  `"172.17.0.24 sample.albandrieu.com",` dans ses entrées DNS.
  La ligne n'a pas été modifiée automatiquement.
- Le resolver de la workstation utilisait initialement Pi-hole ; après
  `resolvectl dns eno1 172.17.0.1`, la résolution utilisait une IP
  Cloudflare et `curl` retournait `302`, `TLS=0`. Sans ce réglage,
  `curl` atteignait `172.17.0.24:443` et retournait `404`.
- **DHCP pfSense LAN est déjà correct** : `domain_name_servers =
  172.17.0.1`, `dhcp_server_identifier = 172.17.0.1`.
  Une lecture ultérieure de `resolvectl status eno1` affichait cependant
  `9.9.9.9` et `149.112.112.112` (Quad9), avec NetworkManager actif
  et systemd-networkd inactif. Ne pas attribuer ce second écart à DHCP
  sans vérifier le profil NetworkManager ou un override temporaire.

## Rapprochement avec incidents anciens

- [2026-09-27 — DNS DHCP TrueNAS/Talos](2026-09-27-pfsense-dns-truenas-dependency.md) :
  à l'époque, Kea annonçait `172.17.0.24`. **Ce n'est plus le cas**.
- [2026-10-10 — hostname Vaultwarden public vers TrueNAS](2026-10-10-vaultwarden-public-split-dns.md) :
  même symptôme de bypass Cloudflare et HTTP 404, mais origine de
  l'override différente (pfSense Unbound au lieu du Pi-hole de Sample).
- La règle LAN pflow `TEST-PFLOW-Workstation-HTTPS` concerne TCP 443
  et le suivi des flux ; aucune preuve n'indique qu'elle réécrit le DNS.

## Non-régression ajoutée au diagnostic Sample

Sur TrueNAS :

```bash
cd /mnt/cpool/compose/nabla-compose
just sample-dns-truenas
bash scripts/truenas/diagnose-fastapi-sample.sh --cycles 1 --color never
```

Sur la workstation avec `eno1` :

```bash
just sample-dns-workstation
# Diagnostic DNS portable, sans introspection du Docker local : just sample-dns
# équivalent portable :
bash scripts/ingress/diagnose-sample-dns.sh --workstation
```

Ces vérifications restent **en lecture seule**. Elles comparent les
résolveurs Pi-hole/pfSense/public, la vue NSS, la zone privée et les
références au nom public dans les seuls fichiers Pi-hole connus. La
provenance de l'enregistrement est affichée sous forme de **chemin seul**
(`pihole_override_source`) sans exposer le contenu de `pihole.toml`.
En mode workstation, elles indiquent NetworkManager, DHCP, DNS actif
et systemd-networkd sans modifier le profil.

## Contrôle opérateur du 23 octobre — tests du diagnostic

Résultats observés :
- `just sample-dns-test` : 4/4 tests initiaux **PASS**.
- `just sample-dns-workstation` : le hostname public résout correctement
  depuis pfSense, Cloudflare et le resolver système ; **Pi-hole répond
  toujours 172.17.0.24**, donc FAIL voulu et sortie 1.
- La workstation utilise `resolvectl dns eno1 = 9.9.9.9 149.112.112.112`
  alors que le bail DHCP porte `domain_name_servers=172.17.0.1`.
  NetworkManager actif, systemd-networkd inactif ; ce n'est pas une
  raison pour modifier DHCP.
- `just sample-dns` exécuté sur TrueNAS rapporte la même mauvaise
  réponse Pi-hole et sa provenance `/etc/pihole/pihole.toml`.
  Les échecs `just` sont **attendus tant que la mauvaise entrée persiste**.

Améliorations de non-régression : la version workstation évite désormais
l'inspection Docker du Pi-hole distant (SKIP, plutôt qu'un WARN trompeur).
Le rapport TrueNAS conserve le chemin de l'entrée mais ne double plus
le même incident DNS en deux échecs. Le profil NetworkManager actif est
lu uniquement pour ses champs IPv4 DNS (sans mot de passe ni secrets).
Le mode workstation contrôle aussi `getent` pour `sample.int.albandrieu.com`,
car un resolver exclusivement public comme Quad9 ne garantit pas
l'accessibilité des services privés.

### Pi-hole v6 : correction ciblée à appliquer hors du diagnostic

Pi-hole documente `dns.hosts` comme la liste des enregistrements locaux
de `/etc/pihole/pihole.toml`. **Préférer l'interface Web Pi-hole
Local DNS → DNS Records** ou l'API configurée : supprimer uniquement
`172.17.0.24 sample.albandrieu.com`, garder tous les autres noms,
notamment les noms `.int`. La commande `pihole-FTL --config dns.hosts`
sans filtre retourne potentiellement des noms privés ; ne pas publier sa
sortie intégrale. Un éventuel `--config dns.hosts '[...]'` remplacerait
la liste complète : ne jamais l'utiliser avec une liste tronquée.

Après correction de l'entrée, exiger :
```bash
dig +short @172.17.0.24 sample.albandrieu.com A
dig +short @172.17.0.24 sample.int.albandrieu.com A
dig +short @172.17.0.1 sample.albandrieu.com A
```
Le hostname public ne doit jamais pointer vers `172.17.0.24`.
Le nom `.int` doit conserver cette adresse.

### Workstation : déterminer la provenance de Quad9

Sur le poste (lecture seule) :
```bash
nmcli -g GENERAL.CONNECTION device show eno1
nmcli -f GENERAL.CONNECTION,IP4.DNS,IP6.DNS device show eno1
nmcli -f DHCP4.OPTION device show eno1 |
  grep -Ei 'domain_name_servers|dhcp_server_identifier'
resolvectl dns eno1
getent ahostsv4 sample.int.albandrieu.com
```
Puis inspecter **uniquement les champs DNS** du profil NetworkManager
affiché. `ipv4.ignore-auto-dns=yes` ou un `ipv4.dns` statique Quad9
peut expliquer la priorité donnée à un autre resolver malgré DHCP.
Si ces champs sont vides, examiner les paramètres globaux NetworkManager,
les profils VPN et les substitutions dans systemd-resolved. Ne pas
réinitialiser le réseau sans fenêtre de maintenance.

## Remédiation et critères d'acceptation

1. Identifier l'entrée DNS locale **exacte** dans Pi-hole v6 et la
   supprimer via l'interface/configuration gérée, après revue.
   Préserver `sample.int.albandrieu.com -> 172.17.0.24`. Ne pas
   éditer directement un fichier généré sans comprendre son propriétaire.
2. Vérifier que `pihole-dns-sync` utilise bien
   `DOMAIN_SUFFIX=int.albandrieu.com` (déclaré dans Compose).
   Ne pas désactiver Pi-hole ou Unbound globalement.
3. Examiner la connexion NetworkManager active (`nmcli connection
   show --active` et `nmcli connection show <profil>`) pour expliquer
   pourquoi Quad9 peut remplacer le DNS pfSense fourni par DHCP.
4. Exiger une réponse **Cloudflare publique** depuis Pi-hole et pfSense
   pour `sample.albandrieu.com` et **TrueNAS uniquement pour** le nom
   `sample.int.albandrieu.com`. `getent` ne doit plus détourner le
   nom public vers TrueNAS.
5. Vérifier TLS sans `-k` et l'absence d'erreur ECH. Une redirection
   `302` vers Cloudflare Access sans session est **attendue**, et ne
   prouve pas à elle seule la santé de l'origine.

La fermeture exige la preuve des résolutions correctes après
renouvellement réseau/redémarrage, et pas seulement une correction
temporaire via `resolvectl`.

## Suivi opérateur : validation du 23 octobre, deuxième passe

L'opérateur a relancé les 5 tests : **5/5 PASS** (0,244 s). Le DNS Pi-hole
reste incorrect (`172.17.0.24` pour le hostname public) et le contrôle
workstation confirme Quad9 actif malgré le DHCP correct. La résolution système
`sample.int.albandrieu.com` ne renvoie **aucune adresse**, ce qui confirme
que la chaîne DNS privée est dégradée sur ce poste malgré HTTPS public corrigé.

Le contrôle `--check` est désormais portable et n'inspecte pas Docker ;
le nouveau `--truenas` vérifie les fichiers locaux Pi-hole et est utilisé
par le diagnostic complet FastAPI. Le mode workstation avertit maintenant
si les champs DNS du profil NetworkManager sont **vides** (même si `nmcli`
retourne le statut succès) ; ce silence avait été observé pour `Wired eno1`.
Les 8 contrats mockés sont à exécuter sur le nouveau HEAD.

## État actualisé après correction Pi-hole — 23 octobre 2026

L'opérateur a supprimé dans Pi-hole WebUI l'enregistrement
`172.17.0.24 sample.albandrieu.com`. Les vérifications ont confirmé
`just sample-dns` **failures=0 warnings=0** :

- `sample.albandrieu.com` via pfSense et Pi-hole : IPv4 publiques
  Cloudflare (adresses variant selon le resolver/la région) ;
- `sample.int.albandrieu.com` via Pi-hole et pfSense :
  `172.17.0.24` ;
- résolution NSS du nom public : Cloudflare et non TrueNAS ;
- `just sample-dns-test` : **8/8 PASS sur workstation**.

**Ne pas réintroduire l'enregistrement public dans Pi-hole.** Le
redirect Cloudflare Access HTTP 302 demeure attendu sans authentification.
La validation navigateur après renouvellement DHCP/reboot reste à faire.

### Problème subsistant : override NetworkManager vs Quad9

L'opérateur a identifié la configuration persistée **exacte** du profil
`Wired eno1` :

```text
ipv4.method: auto
ipv4.dns: 172.17.0.24
ipv4.ignore-auto-dns: yes
ipv4.dns-search: albandrieu.com
```

Alors que le **DHCP pfSense est correct** (`172.17.0.1`), le
profil ignore volontairement le DNS DHCP et conserve Pi-hole comme
DNS général. Dans un instantané distinct, `resolvectl dns eno1`
montrait pourtant `9.9.9.9 149.112.112.112` (Quad9) et
`getent ahostsv4 sample.int.albandrieu.com` ne donnait pas
`172.17.0.24` : rechercher un résolveur supplémentaire
(VPN, global resolved, override link, état NM non reappliqué).
**Ne pas attribuer l'origine de Quad9 au profil `Wired eno1` sans preuve.**

Pour retrouver le contrat de résilience du 27 septembre, la
configuration cible du **profil Wired** est :
`ipv4.method=auto`, `ipv4.ignore-auto-dns=no`, `ipv4.dns` vide ;
le DNS reçu sera celui de pfSense. Ne pas remplacer
`172.17.0.24` par un autre résolveur public : Quad9 ne fournit
pas le split-DNS `*.int.albandrieu.com`.

Sur la workstation **physiquement accessible et non via SSH**,
l'opérateur peut après sauvegarde locale du profil et en
connaissance du risque de brève coupure réseau :

```bash
# Configuration déclarée uniquement ; ne modifie pas la politique firewall.
sudo nmcli connection modify 'Wired eno1' ipv4.ignore-auto-dns no ipv4.dns ''
# Réappliquer sur le lien en cours ; peut affecter brièvement le réseau.
sudo nmcli device reapply eno1

# Validations à renouveler après reconnect / reboot :
nmcli -g ipv4.dns,ipv4.ignore-auto-dns connection show 'Wired eno1'
nmcli -f DHCP4.OPTION device show eno1 | grep domain_name_servers
resolvectl dns eno1
getent ahostsv4 sample.int.albandrieu.com
getent ahostsv4 sample.albandrieu.com
```

Si `reapply` échoue, **ne pas forcer `connection down/up`
depuis une session distante** ; identifier d'abord ce qui injecte
Quad9. Ne jamais corriger DHCP Kea ni les règles `TEST-PFLOW`
pour résoudre ce profil utilisateur.

### Validation locale du suivi post-merge

Le 23 octobre, les deux fichiers `scripts/ingress/diagnose-sample-dns.sh`
et `tests/test_sample_dns_diagnostic.py` ont été reconstitués dans
l'environnement local de l'agent depuis les contenus GitHub, avec
**identité vérifiée par git hash-object** (empreintes de blobs
correspondant à la branche post-merge). Résultats :

- `bash -n scripts/ingress/diagnose-sample-dns.sh` : **PASS** ;
- `python3 -m py_compile tests/test_sample_dns_diagnostic.py` : **PASS** ;
- `python3 -m unittest discover -s tests -p test_sample_dns_diagnostic.py -v` :
  **11/11 PASS, 0,420 s**, DNS, Docker et NetworkManager mockés ;
- le test du branchement vers `diagnose-fastapi-sample.sh` utilise
  un substitut local contenant sept sections ; il **ne prouve pas**
  l'intégration complète ni l'exécution du diagnostic TrueNAS réel ;
- `shellcheck` non installé dans l'environnement agent. La quality
  gate du dépôt entier et le test après reboot ne sont **pas exécutés**.

Aucun appel GitHub Actions, merge, déploiement ou modification réseau
n'a été effectué dans le suivi post-merge.

Le diagnostic `--workstation` relève désormais séparément le DNS
du **profil NetworkManager** (statique/ignore DHCP), le DNS effectif
dans **systemd-resolved**, le DHCP reçu et la résolution réelle des
noms public et privé. Une divergence profile↔resolved et le
contournement DHCP sont des avertissements distincts. Tests de ces
nouveaux contrats ajoutés au dépôt ; exécution à confirmer.
