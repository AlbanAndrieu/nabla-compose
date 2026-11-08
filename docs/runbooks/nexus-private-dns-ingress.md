# Nexus — diagnostic DNS/HTTPS privé

**Référence de sécurité commune :**
[Politique d'exposition HAProxy, Tunnel, DNS et PF](pfsense-ingress-exposure-policy.md)
et [instantané HAProxy expurgé](../evidence/pfsense/haproxy-2026-10-27.generated.redacted.cfg).
Ce snapshot montre aussi `acl vault` et `acl s3` **sans refus**, avec une
route Traefik générique vers `*.int` : l'accès S3 public ou privé est
**contradictoire entre les sources** ; ne pas clore ce conflit sur le seul
fonctionnement DNS.

**Objet :** distinguer DNS, résolution du poste, Traefik et Nexus pour
`https://nexus.int.albandrieu.com/`. Le succès de
`https://nexus.albandrieu.com/` ne valide pas ce chemin privé.

**État au 27/10/2026 :**

| Couche | État |
| --- | --- |
| DNS privé (pfSense + Pi-hole, UDP + TCP) | `PRIVATE_DNS_CONFIRMED` : `NOERROR A 172.17.0.24` (8/8) |
| Backend `172.17.0.24:8081` | HTTP 200 |
| Labels Docker du conteneur | réconciliés avec le rendu TrueNAS (Gate 3–7) |
| Routeur Traefik `nexus-private` | **volontairement désactivé** (`traefik.enable=false`, HTTPS privé 404 / TLS OK) |
| HAProxy `main_Web_HTTPS` | refus 403 du Host Nexus observé depuis le LAN (Gate 12) |
| Rejet depuis Internet | **WAN_REJECTION_NOT_VERIFIED** |

Garder `NEXUS_PRIVATE_INGRESS_ENABLED=false` tant que le rejet WAN, la
configuration HAProxy chargée et le rollback ne sont pas prouvés. Ne pas
toucher au chemin public ni publier de DNS `*.int` sur Cloudflare.
**Aucun changement de runtime n'est exécuté par ce runbook.**

## Chaîne attendue

```text
client LAN -> Unbound 172.17.0.1:53
           -> Domain Override int.albandrieu.com
           -> Pi-hole 172.17.0.24:53 (pihole-dns-sync)
           -> 172.17.0.24:443 (Traefik, Host+SNI)
           -> nexus:8081 (traefik_network)
```

`apps/nexus/compose.yml` expose `172.17.0.24:8081` et déclare un routeur
`nexus-private` désactivé par défaut
(`traefik.enable: "${NEXUS_PRIVATE_INGRESS_ENABLED:-false}"`). Le
synchroniseur Pi-hole publie des noms depuis les routeurs Traefik
éligibles. **Un simple `dig` n'active pas un routeur ; un changement Git ne
déploie rien.**

## Préflight en lecture seule sur la workstation

Exécuter et garder les résultats séparés :

```bash
# 1. Autorité privée : DNS Pi-hole.
dig +tries=1 +time=2 @172.17.0.24 nexus.int.albandrieu.com A

# 2. Délégation LAN : pfSense / Unbound.
dig +tries=1 +time=2 @172.17.0.1 nexus.int.albandrieu.com A

# 3. Résolution effective du poste (risque de fallback Quad9).
getent ahostsv4 nexus.int.albandrieu.com || true

# 4. Service HTTP direct, indépendant de DNS et Traefik.
curl --noproxy '*' --silent --show-error --max-time 5 \
  -o /dev/null -w 'nexus_backend_http=%{http_code}\n' \
  http://172.17.0.24:8081/

# 5. Traefik SNI/Host forcés : contourne le DNS sans ignorer TLS.
curl --noproxy '*' --silent --show-error --max-time 8 \
  --resolve nexus.int.albandrieu.com:443:172.17.0.24 \
  -o /dev/null \
  -w 'nexus_ingress_http=%{http_code} tls_verify=%{ssl_verify_result}\n' \
  https://nexus.int.albandrieu.com/
```

Le résultat HTTP direct peut être `200`, `302` ou `401` selon
l'authentification : noter son code, ne pas le convertir en succès
fonctionnel. `curl` doit refuser un certificat incorrect ; ne jamais
désactiver la vérification TLS pour déclarer TLS conforme.

| Observation | Hypothèse prioritaire et contrôle |
| --- | --- |
| DNS TIMEOUT sur deux résolveurs et HTTP/TCP également TIMEOUT | **Transport LAN indéterminé** ; commencer par Gate 0, ne pas classer Nexus `NXDOMAIN` |
| Pi-hole NXDOMAIN | Nom absent de Pi-hole : vérifier `pihole-dns-sync`, labels Traefik actifs et source d'autorité |
| Pi-hole A=172.17.0.24, Unbound NXDOMAIN | Domain Override / cache / liaison pfSense → Pi-hole |
| Deux réponses A conformes, `getent` échoue | Résolveur workstation non relié à pfSense (ex. Quad9) |
| Backend HTTP accessible, Traefik HTTPS 404 | Routeur `nexus-private` absent/inactif ou règle Host non chargée |
| HTTPS 502/504 | Connexion Traefik → Nexus `traefik_network` / port 8081 |
| Échec TLS | Certificat wildcard / SNI / confiance ; ne pas désactiver la vérification |
| Tout passe | Valider ensuite l'accès navigateur sur LAN, sans conclure sur les identifiants utilisateurs |

## Gate 0 — transport LAN avant DNS et Nexus

Des timeouts `dig`/`curl` (`000`, curl 28) ne prouvent **pas** l'absence du
nom DNS Nexus. Un champ `tls=1` associé à un timeout n'est pas un échec de
vérification TLS : aucune négociation exploitable n'a eu lieu. Depuis **la
même workstation et dans la même session réseau**, avant toute analyse du
routeur ou des labels :

```bash
date -Is
ip -br -4 address
ip -4 route get 172.17.0.1
ip -4 route get 172.17.0.24

# ICMP est indicatif ; un firewall peut le bloquer sur un hôte sain.
ping -n -c 2 -W 1 172.17.0.1 || true
ping -n -c 2 -W 1 172.17.0.24 || true

# Preuve de connexion TCP avec budget court (netcat/OpenBSD nc).
for item in 172.17.0.1:10443 172.17.0.24:8081 172.17.0.24:443; do
  host=${item%:*}; port=${item##*:}
  echo "== tcp ${host}:${port} =="
  nc -z -v -w 2 "$host" "$port" || true
done

ip neigh show to 172.17.0.1
ip neigh show to 172.17.0.24
```

`ip route get` et `ip -br -4 address` détectent un changement
d'interface, de VLAN, de route ou de VPN. Une entrée ARP `FAILED` oriente
vers le transport sans en attribuer la cause ; une panne de plusieurs
ports peut concerner le client, la route, un pare-feu ou les hôtes : ne
pas présumer qu'Unbound ou Nexus est arrêté.

**Gate :** si aucune connexion TCP/IP n'est établie, classer
`LAN_TRANSPORT_UNVERIFIED`. **Suspendre l'investigation DNS autoritaire, le
TLS Nexus et l'activation Traefik.** Si des ports répondent, poursuivre par
couche (Gate 1). Aucune modification de route, NetworkManager, pfSense,
TrueNAS, Unbound, Pi-hole, Snort, pfBlockerNG ou CrowdSec ne fait partie du
diagnostic initial.

## Gate 1 — distinguer DNS UDP/TCP, HTTP et TLS

```bash
# Un DNS privé connu OK (s3) puis Nexus, sur chaque serveur.
for server in 172.17.0.24 172.17.0.1; do
  echo "== DNS UDP ${server} =="
  dig +tries=1 +time=2 @"$server" s3.int.albandrieu.com A
  dig +tries=1 +time=2 @"$server" nexus.int.albandrieu.com A

  echo "== DNS TCP ${server} =="
  dig +tcp +tries=1 +time=2 @"$server" s3.int.albandrieu.com A
  dig +tcp +tries=1 +time=2 @"$server" nexus.int.albandrieu.com A
done
```

Un `NXDOMAIN` sur les deux résolveurs **après** des réponses correctes pour
`s3.int.albandrieu.com` est compatible avec l'absence de publication de
Nexus. `TIMEOUT` UDP avec réponse TCP suggère un problème spécifique au
protocole. Si les deux protocoles expirent, contrôler la santé des services
DNS avant les labels Traefik. Une réponse `aa` de Pi-hole prouve la réponse
autoritative, pas le mécanisme de création (`pihole-dns-sync`, entrée
manuelle…) : ne pas créer d'enregistrement doublon ni changer le Domain
Override pfSense.

### Tests du dépôt — protection contre zéro test

```bash
pwd
git rev-parse --short HEAD
test -f tests/test_nexus_private_ingress_contract.py
just nexus-private-ingress-test
```

La recette vérifie le chemin et exécute **directement** le fichier de
tests : s'il manque, elle échoue. Un `Ran 0 tests` (`unittest discover`
depuis un mauvais checkout/répertoire) **n'est pas PASS**.

## Gate 2 — HTTP direct, HTTPS et labels effectifs

```bash
curl --noproxy '*' --connect-timeout 2 --max-time 10 \
  --silent --show-error -o /dev/null \
  -w 'nexus_backend_http=%{http_code} connect=%{time_connect} total=%{time_total}\n' \
  http://172.17.0.24:8081/

curl --noproxy '*' --connect-timeout 2 --max-time 10 \
  --silent --show-error -o /dev/null \
  --resolve nexus.int.albandrieu.com:443:172.17.0.24 \
  -w 'nexus_ingress_http=%{http_code} tls=%{ssl_verify_result} connect=%{time_connect} total=%{time_total}\n' \
  https://nexus.int.albandrieu.com/
```

`000` = aucune réponse HTTP exploitable ; `200/302/401` s'interprètent
selon la route et l'authentification. Un `404` Traefik avec backend
fonctionnel oriente vers un routeur absent/inactif ou un mauvais `Host` (un
autre provider Traefik pourrait aussi répondre) ; `502/504` vers le chemin
reverse-proxy → Nexus.

Le label déclaratif dans Git ne prouve pas son déploiement. Sur TrueNAS, en
lecture seule (ne jamais imprimer `.Config.Env`, les secrets ou
l'intégralité de `app.query` / `app.config`) :

```bash
sudo docker inspect nexus --format '{{json .Config.Labels}}' |
  jq '{project: .["com.docker.compose.project"],
       service: .["com.docker.compose.service"],
       config_files: .["com.docker.compose.project.config_files"],
       enabled: .["traefik.enable"],
       rule: .["traefik.http.routers.nexus-private.rule"],
       service_ref: .["traefik.http.routers.nexus-private.service"]}'

sudo docker inspect nexus --format '{{json .NetworkSettings.Networks}}' | jq 'keys'
sudo midclt call app.query | jq -c '.[] | select(.name == "nexus") | {name, state}'
sudo midclt call app.config nexus | jq '{include_type: (.include | type), include_paths: .include}'
```

## Gate 3–7 — rendu TrueNAS et conteneur (résolu le 26/10)

Propriété établie :

- projet Docker `ix-nexus`, service `nexus`, créé par **TrueNAS Apps**
  depuis le rendu interne
  `/mnt/.ix-apps/app_configs/nexus/versions/1.0.0/templates/rendered/docker-compose.yaml` ;
- `app.config nexus` → `include` vers
  `/mnt/cpool/compose/nabla-compose/apps/nexus/compose.yml` (le fichier Git) ;
- réseau externe `traefik_network` présent.

**Ne jamais éditer ou remplacer le fichier `.ix-apps`** : il appartient au
cycle de vie TrueNAS. Ne pas recréer la Custom App. Contrôle du rendu,
sans secret :

```bash
set -o pipefail
CFG='/mnt/.ix-apps/app_configs/nexus/versions/1.0.0/templates/rendered/docker-compose.yaml'
sudo docker compose -f "$CFG" config --format json |
  jq -e '.services.nexus as $n |
    {enabled: $n.labels["traefik.enable"],
     host_rule: $n.labels["traefik.http.routers.nexus-private.rule"],
     networks: ($n.networks | keys)}'
git -C /mnt/cpool/compose/nabla-compose status --short -- apps/nexus
sudo docker network inspect traefik_network --format '{{.Name}}'
```

Un `docker compose config` en erreur n'est pas une preuve d'absence de
labels. `nexus_networks: {"traefik_network": null}` signifie « sans options
réseau », pas « réseau absent ».

Décision selon les résultats :

- labels présents dans le rendu mais absents du conteneur : écart de cycle
  de vie ; redéploiement TrueNAS de **Nexus seul**, après validation de
  l'impact, d'une fenêtre de maintenance, de la sauvegarde du dataset et du
  rollback. `docker restart nexus` n'applique **aucun nouveau label** ;
  `git pull` non plus. `app.redeploy nexus` est un **job** qui
  arrête/recrée et peut tirer des images : jamais comme simple contrôle de
  labels ;
- aucun `include` : migrer la Custom App vers un wrapper `include` approuvé,
  après revue et sauvegarde ;
- `include` correct : vérifier la version exacte du fichier sur TrueNAS et
  le rendu de l'opt-in (défaut `false`).

Un redéploiement avec `NEXUS_PRIVATE_INGRESS_ENABLED=false` laisse le
routeur désactivé et le `404` attendu. Un `env_file:` injecte des variables
**dans le conteneur**, pas forcément dans l'interpolation `${...}` du
rendu ; une variable exportée dans le shell d'appel à `midclt` ne prouve
pas qu'elle atteint le projet Compose. Confirmer l'effet sur le rendu
TrueNAS avant de redéployer.

Après opération, sans nouvelle mutation :

```bash
sudo midclt call app.query | jq '.[] | select(.name == "nexus") | {name, state}'

sudo docker inspect nexus --format '{{json .Config.Labels}}' |
  jq '{enabled: .["traefik.enable"],
       rule: .["traefik.http.routers.nexus-private.rule"],
       service: .["traefik.http.routers.nexus-private.service"]}'

curl --noproxy '*' --connect-timeout 3 --max-time 15 \
  -sS -o /dev/null -w 'backend=%{http_code}\n' \
  http://172.17.0.24:8081/

curl --noproxy '*' --connect-timeout 3 --max-time 15 \
  -sS -o /dev/null \
  --resolve nexus.int.albandrieu.com:443:172.17.0.24 \
  -w 'ingress=%{http_code} tls=%{ssl_verify_result}\n' \
  https://nexus.int.albandrieu.com/
```

Réception du 26/10 (Gate 7) : `state=RUNNING`, `traefik.enable="false"`,
règle `Host(\`nexus.int.albandrieu.com\`)`, service `nexus-private`,
backend **200**, HTTPS privé **404** avec `ssl_verify_result=0` (ATTENDU,
routeur désactivé). Ce `404` ne justifie **aucune** intervention sur le
DNS, Unbound, Pi-hole, TrueNAS Apps ou Traefik. Route publique non
retestée : **PUBLIC_ROUTE_NOT_VERIFIED**.

## Pourquoi le WAN bloque l'activation

Le frontal déclaré est `pfSense HAProxy -> TrueNAS Traefik websecure :443`
(ré-encryption TLS, Host conservé). Le même entrypoint sert des exceptions
`*.int` publiques, dont `s3.int.albandrieu.com`. Un DNS privé **n'empêche
pas** un client Internet d'envoyer le Host/SNI `nexus.int.albandrieu.com` à
l'adresse publique de pfSense. Un middleware Traefik IPAllowList seul ne
suffit pas si le proxy amont peut présenter une source WAN comme
`172.17.0.1`.

Un `curl --resolve nexus.int.albandrieu.com:443:82.66.4.247` lancé **depuis
le LAN** ne prouve pas un test WAN (NAT reflection possible). Un `404`
Traefik avec le routeur désactivé ne prouve **pas** qu'HAProxy bloque.
Sans poste externe, auditer la politique HAProxy (Gate 9) et noter
`WAN_REJECTION_NOT_VERIFIED`.

## Gate 9 — HAProxy réel : ACL, frontend et backend actifs

Inspecteur versionné, lecture seule via le SSH existant, sans transfert
persistant vers pfSense :

```bash
just nexus-private-ingress-test

# Frontend actif main_Web_HTTPS par défaut ; affiche nexus_declared_backend=…
bash scripts/workstation/inspect-nexus-haproxy-frontend.sh

# Cibles du backend Traefik actuellement déclaré.
bash scripts/workstation/inspect-nexus-haproxy-frontend.sh \
  --backend prod_front-traefik-https_ipvANY
```

Le script lit seulement `/var/etc/haproxy/haproxy.cfg` (AWK POSIX, une
condition par ligne) et n'expose que les ACL utiles (`int`, `aclcrt_*`,
Nexus), `http-request set-var(txn.txnhost)`, `deny/return`,
`tcp-request`, `use_backend` et `default_backend` du **frontend exact**,
sans binds, certificats, headers ni ligne serveur complète. Il échoue si le
frontend ou le backend demandé n'existe pas au lieu de conclure à une
politique absente. `wan_rejection=NOT_VERIFIED` est volontaire : un fichier
généré ne prouve ni le rechargement HAProxy, ni l'ordre effectif, ni
l'absence d'autres frontends WAN. Un Host routé vers un backend par défaut
ne constitue pas un refus. `--frontend fWeb_HTTPS` n'inspecte que l'ancien
nom. Ne pas partager d'ACL ou de domaines sensibles.

Topologie déclarée (relevé du 27/10, HEAD `7300e891`, 15/15 tests) :

| Composant | Relevé |
| --- | --- |
| Frontend | `main_Web_HTTPS` (renommé depuis `fWeb_HTTPS`) |
| ACL Nexus | `nexus.int.albandrieu.com` (ligne 89) |
| Initialisation | `http-request set-var(txn.txnhost) hdr(host)` (ligne 96) |
| Routage | `use_backend prod_front-traefik-https_ipvANY if nexus aclcrt_main_Web_HTTPS` (ligne 128), avant les routes génériques |
| Backend | `backend_server=traefik-https target=172.17.0.24:443` |
| Rejet WAN | `WAN_REJECTION_NOT_VERIFIED` |

**Distinction des noms :** la cible est `nexus.int.albandrieu.com`.
L'ACL historique `nexus-albandrieu.int.albandrieu.com` (et l'ancien backend
`nexus-albandrieu_ipvANY`, désormais absent) est un autre nom : sa présence
ne prouve ni refus ni routage du nom voulu ; ne pas la supprimer ni recréer
le backend sans identifier ses utilisateurs. Après toute modification du
frontend, relire `nexus_declared_backend` avant un contrôle ciblé.

**Restrictions de changement :**

- ne pas bloquer tout `*.int` : `s3.int.albandrieu.com` reste une exception
  publique ; conserver `nexus.albandrieu.com` et les autres backends publics ;
- configurer via **Services → HAProxy → Frontends** dans l'UI pfSense,
  jamais en éditant `/var/etc/haproxy/haproxy.cfg` à la main ;
- vérifier que `main_Web_HTTPS` est bien le frontend WAN `:443` et
  inventorier les autres frontends publics ;
- sauvegarder la configuration pfSense et disposer d'un rollback avant
  Apply. **Ne pas interpréter un HTTP 404 Traefik comme un 403 HAProxy.**

## Gate 12 — refus HAProxy observé sur le chemin LAN, preuve WAN restante

Règle appliquée par l'opérateur et confirmée dans la configuration générée
(27/10) :

```text
line=89  acl nexus var(txn.txnhost) -m reg -i ^nexus\.int\.albandrieu\.com(:[0-9]{1,5})?$
line=94  aclcrt_main_Web_HTTPS ... nom *.int.albandrieu.com
line=96  http-request set-var(txn.txnhost) hdr(host)
line=117 http-request deny deny_status 403 if nexus aclcrt_main_Web_HTTPS
edge_http=403 tls=0
```

**Réception : `LAN_HAIRPIN_DENY_OBSERVED / WAN_REJECTION_NOT_VERIFIED`.**
`set-var` précède le `deny` et le chemin `workstation LAN →
82.66.4.247:443` est passé de 404 à **403** : PASS pour ce chemin. Ni la
provenance du 403 par les logs, ni le rejet d'une source WAN indépendante
ne sont prouvés : ne pas activer `traefik.enable=true` sur cette base.

`if nexus aclcrt_main_Web_HTTPS` est une **conjonction** ; l'ACL `nexus`
sert aussi au routage `use_backend`, donc la modifier change la sélection
du backend, et `aclcrt_*` ne valide pas le certificat malgré son nom. Une
ACL indépendante est plus simple à auditer (recommandation, pas une
modification automatique) :

```haproxy
acl nexus_private_wan var(txn.txnhost) -m reg -i ^nexus\.int\.albandrieu\.com(:[0-9]{1,5})?$
http-request deny deny_status 403 if nexus_private_wan
```

Les actions `http-request` sont évaluées dans l'ordre :
`set-var(txn.txnhost)` **doit précéder** le `deny`. Si l'UI ne le garantit
pas, utiliser `req.hdr(host) -m reg -i ^nexus\.int\.albandrieu\.com(:[0-9]{1,5})?$`.
Sans champ `deny_status`, `http-request deny` répond 403 par défaut.

Réception depuis la workstation (aucun changement réseau) :

```bash
just nexus-private-ingress-test
bash scripts/workstation/inspect-nexus-haproxy-frontend.sh \
  --backend prod_front-traefik-https_ipvANY

# Frontend HAProxy à l'IP publique depuis le LAN (hairpin) :
curl --noproxy '*' --connect-timeout 3 --max-time 10 \
  --resolve nexus.int.albandrieu.com:443:82.66.4.247 \
  -sS -o /dev/null \
  -w 'edge_http=%{http_code} tls=%{ssl_verify_result}\n' \
  https://nexus.int.albandrieu.com/

# Traefik LAN directement, sans passer par pfSense :
curl --noproxy '*' --connect-timeout 3 --max-time 10 \
  --resolve nexus.int.albandrieu.com:443:172.17.0.24 \
  -sS -o /dev/null \
  -w 'lan_traefik_http=%{http_code} tls=%{ssl_verify_result}\n' \
  https://nexus.int.albandrieu.com/
```

**Reste à recevoir :** rechargement effectif du processus HAProxy ;
politiques PF/NAT du frontal WAN ; non-régression de
`s3.int.albandrieu.com` et `nexus.albandrieu.com` (distinguer 401/403
applicatifs des erreurs d'acheminement) ; contrôle direct Traefik LAN après
la règle ; rejet depuis une vraie source WAN (par exemple téléphone en
données mobiles, Wi-Fi/VPN coupés, client forçant la résolution). Sans
cette preuve, garder `WAN_REJECTION_NOT_VERIFIED` même si le `403` est
stable depuis la workstation.

## Activation future et rollback

Seulement après les preuves ci-dessus :

1. obtenir `traefik.enable="true"` dans le rendu via le contexte
   d'interpolation **réel** du `include` (sans éditer `.ix-apps` ni exposer
   de secrets), relire le rendu ;
2. confirmer que Traefik est le propriétaire voulu et que `pihole-dns-sync`
   peut créer cet unique A privé ;
3. redéployer **Nexus seul** selon son cycle de vie TrueNAS ;
4. vérifier HTTP direct, HTTPS privé **directement sur** `172.17.0.24:443`
   (`--resolve`), certificat, Nexus public et rejet au frontal WAN.

Ne pas redémarrer Unbound, Pi-hole, Traefik, pfBlockerNG, ni modifier
Cloudflare pour ce diagnostic. Ne pas publier de jetons, de configuration
Pi-hole intégrale ou de variables d'environnement.

**Rollback :** remettre `NEXUS_PRIVATE_INGRESS_ENABLED=false`, redéployer
uniquement Nexus selon son propriétaire de cycle de vie, puis contrôler la
disparition du routeur et de l'A privé par `pihole-dns-sync`.

## Historique et leçons

- **26/10** — timeouts DNS/HTTP/HTTPS d'abord lus comme une absence du nom ;
  à 21:18 le même poste joignait tout (ICMP, TCP, ARP `REACHABLE`) :
  Gate 0 classe désormais `LAN_TRANSPORT_UNVERIFIED` avant toute conclusion.
- **26/10** — `Ran 0 tests` avec `unittest discover` : la recette
  `just nexus-private-ingress-test` échoue désormais si le fichier manque.
- **26/10** — DNS 8/8 OK mais labels `null` dans le conteneur alors que le
  rendu TrueNAS les contenait : écart de cycle de vie corrigé par un
  redéploiement de Nexus seul (pas un problème DNS).
- **27/10** — filtre `awk` multiligne en erreur sur pfSense
  (`syntax error at source line 6`) : aucune preuve collectée. Remplacé
  par l'inspecteur POSIX versionné.
- **27/10** — `--backend nexus-albandrieu_ipvANY` → `not found` : backend
  historique supplanté, pas une panne Nexus. Suivre le backend déclaré.
- **27/10** — règle `deny 403` ajoutée sur `main_Web_HTTPS` : 404 → 403 sur
  le chemin LAN hairpin ; preuve WAN toujours manquante.

[Architecture DNS](../dns-ingress-ownership.md) ·
[Incident pfSense Unbound / DNSBL (H-04)](../incidents/2026-10-24-pfsense-unbound-restarts.md)
