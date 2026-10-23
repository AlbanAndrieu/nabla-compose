# 2026-10-23 — Sample / Chrome ECH : override public Pi-hole vers TrueNAS

## Statut
Cause racine **prouvée** ; correction Pi-hole **non exécutée** par l'agent.
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
just sample-dns
bash scripts/truenas/diagnose-fastapi-sample.sh --cycles 1 --color never
```

Sur la workstation avec `eno1` :

```bash
just sample-dns-workstation
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
