# Nexus — diagnostic DNS/HTTPS privé (26 octobre 2026)

**Objet :** distinguer DNS, résolution du poste, Traefik et Nexus pour
`https://nexus.int.albandrieu.com/`. Le succès de
`https://nexus.albandrieu.com/` ne valide pas ce chemin privé.
**État : code préparé, runtime non vérifié.** Ne pas toucher au
chemin public ni publier de DNS `*.int` sur Cloudflare.

## Chaîne attendue

```text
client LAN -> Unbound 172.17.0.1:53
           -> Domain Override int.albandrieu.com
           -> Pi-hole 172.17.0.24:53 (pihole-dns-sync)
           -> 172.17.0.24:443 (Traefik, Host+SNI)
           -> nexus:8081 (traefik_network)
```

Le dépôt `apps/nexus/compose.yml` expose déjà `172.17.0.24:8081`.
Ses anciens labels Traefik privés étaient commentés. La PR #285 prépare
un routeur `nexus-private`, désactivé par défaut avec
`NEXUS_PRIVATE_INGRESS_ENABLED=false`. Le synchroniseur Pi-hole
publie des noms depuis les routeurs Traefik éligibles. **Un simple
`dig` n'active pas un routeur ; un changement Git ne déploie rien.**

## Gate 0 — transport LAN avant DNS et Nexus

**Preuve opérateur du 26/10 (heure exacte du relevé non fournie) :**
les deux requêtes `dig +tries=1 +time=2` pour
`nexus.int.albandrieu.com` vers `172.17.0.24:53` et
`172.17.0.1:53` ont expiré, sans `NXDOMAIN` ni `SERVFAIL`.
La connexion directe `http://172.17.0.24:8081/` a expiré
(`backend=000`, curl 28) ; la connexion à Traefik
`172.17.0.24:443` a expiré (`traefik=000`, curl 28).
Le champ `tls=1` associé à ce timeout n'est **pas** une preuve
d'échec de vérification TLS : aucune négociation exploitable n'a eu lieu.

**Interdiction de conclure à l'absence du nom DNS Nexus** à partir de
timeouts. Le relevé `s3.int.albandrieu.com` via pfSense/Pi-hole du
26/10 à 20:49 CET était `NOERROR → 172.17.0.24` pour les deux
résolveurs ; comparer les conditions réseau des deux observations.

Depuis **la même workstation et dans la même session réseau**, avant
toute analyse du routeur Traefik ou des labels, exécuter :

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

Les résultats `ip route get` et `ip -br -4 address` aident à détecter
un changement d'interface, de VLAN, de route ou de VPN. Une entrée ARP
`FAILED` sur le même réseau de niveau 2 oriente vers un problème
de transport, mais elle ne suffit pas seule à en attribuer la cause.
Une panne de plusieurs ports **peut** concerner le client, la route,
un pare-feu, les hôtes ou leurs services : ne pas présumer qu'Unbound
ou Nexus est arrêté.

**Gate :** si les contrôles TCP/IP ci-dessus n'établissent toujours
aucune connexion, classer `LAN_TRANSPORT_UNVERIFIED`. **Suspendre
l'investigation DNS autoritaire, le TLS Nexus et l'activation Traefik.**
Si des ports répondent, poursuivre par couche : DNS UDP/TCP explicitement
sur chaque résolveur, puis HTTP direct, puis HTTPS SNI. Tester
`dig +tcp +tries=1 +time=2 @172.17.0.1 s3.int.albandrieu.com A`
et son équivalent Pi-hole **seulement après** confirmation du transport.

Aucune modification de route, NetworkManager, pfSense, TrueNAS,
Unbound, Pi-hole, Snort, pfBlockerNG ou CrowdSec ne fait partie
du diagnostic initial.

## Gate 0 — relevé du 26 octobre à 21:18 CET

Depuis la workstation `eno1=172.17.0.57/24` :

- `ip -4 route get` sélectionne `eno1` pour les deux adresses ;
- pfSense `172.17.0.1` : ICMP 2/2, moyenne 0,498 ms ;
- TrueNAS `172.17.0.24` : ICMP 2/2, moyenne 0,166 ms ;
- TCP `172.17.0.1:10443`, `172.17.0.24:8081` et
  `172.17.0.24:443` : trois connexions réussies ;
- les deux voisins ARP sont `REACHABLE`.

**État : `LAN_TRANSPORT_REACHABILITY_OBSERVED` au seul instant testé.**
Les anciens timeouts sur DNS/HTTP/HTTPS ne peuvent plus être présentés
comme une indisponibilité persistante du LAN. Les connexions TCP établies
ne démontrent cependant ni réponse DNS UDP/TCP 53, ni HTTP 200, ni TLS
correct, ni stabilité de la connectivité dans le temps.

### Gate 1 — distinguer DNS UDP/TCP, HTTP et TLS

Depuis la workstation, en lecture seule :

```bash
# Refaire un DNS privé connu OK puis Nexus, sur chaque serveur.
for server in 172.17.0.24 172.17.0.1; do
  echo "== DNS UDP ${server} =="
  dig +tries=1 +time=2 @"$server" s3.int.albandrieu.com A
  dig +tries=1 +time=2 @"$server" nexus.int.albandrieu.com A

  echo "== DNS TCP ${server} =="
  dig +tcp +tries=1 +time=2 @"$server" s3.int.albandrieu.com A
  dig +tcp +tries=1 +time=2 @"$server" nexus.int.albandrieu.com A
done

# HTTP direct. TCP SYN/ACK ne suffit pas.
curl --noproxy '*' --connect-timeout 2 --max-time 8 \
  -sS -o /dev/null \
  -w 'backend_http=%{http_code} total=%{time_total}\n' \
  http://172.17.0.24:8081/

# TLS + routage applicatif, toujours sans modifier le DNS.
curl --noproxy '*' --connect-timeout 2 --max-time 8 \
  -sS -o /dev/null \
  --resolve nexus.int.albandrieu.com:443:172.17.0.24 \
  -w 'ingress_http=%{http_code} tls=%{ssl_verify_result} total=%{time_total}\n' \
  https://nexus.int.albandrieu.com/
```

Un `NXDOMAIN` sur les deux résolveurs **après** confirmation
des réponses DNS pour `s3.int.albandrieu.com` est compatible avec
l'absence de publication de Nexus. `TIMEOUT` sur UDP et réponse TCP
suggèrent un problème de transport/politique DNS spécifique au
protocole ; cela ne prouve pas automatiquement la cause. Si les deux
protocoles expirent, contrôler la santé des services DNS avant les
labels Traefik. Si les deux DNS renvoient un A correct mais TLS/HTTP
échoue, investiguer le reverse proxy.

### Gate de tests du dépôt — protection contre zéro test

Le test existe dans la branche de la PR #285, mais l'opérateur
a obtenu `Ran 0 tests` avec `unittest discover`. Cela peut
signaler un ancien checkout ou un mauvais répertoire courant ;
ce résultat **n'est pas PASS**.

```bash
pwd
git rev-parse --short HEAD
test -f tests/test_nexus_private_ingress_contract.py
just nexus-private-ingress-test
```

La nouvelle recette vérifie le chemin, compile et exécute
**directement** le fichier de tests : si le fichier manque,
elle échoue au lieu de retourner zéro test. Le résultat initial
`Ran 0 tests` a été corrigé en utilisant un worktree neuf :
**4/4 PASS opérateur** sur `ebbacf8a`.

## Gate 1 — acceptation DNS et contrats locaux (26 octobre)

L'opérateur a rejoué les vérifications dans un **worktree neuf** au
commit `ebbacf8a` de la PR #285.

- `just nexus-private-ingress-test` : **4 tests exécutés, 4 PASS**.
  L'ancien résultat `Ran 0 tests` venait d'un autre contexte de
  checkout ou de découverte ; le mécanisme précis n'a pas été établi.
- `s3.int.albandrieu.com` (nom témoin) :
  `NOERROR`, A `172.17.0.24` via **pfSense et Pi-hole**,
  en **UDP et TCP**.
- `nexus.int.albandrieu.com` (nom cible) :
  `NOERROR`, A `172.17.0.24` via **pfSense et Pi-hole**,
  en **UDP et TCP**.
- **8/8 contrôles DNS réussis**, sans `NXDOMAIN`, `SERVFAIL`
  ou `TIMEOUT` dans cette observation.

**Statut : `PRIVATE_DNS_CONFIRMED`.** Le nom privé Nexus existe
déjà. Sa provenance exacte dans Pi-hole
(`pihole-dns-sync`, entrée locale manuelle, autre automatisation)
reste **non vérifiée** : la réponse `aa` de Pi-hole prouve
la réponse autoritative, pas le mécanisme de création.
Ne pas créer un enregistrement doublon ni changer le Domain
Override pfSense. Un routeur Traefik et le service Nexus
peuvent rester en échec **malgré DNS conforme**.

### Gate 2 — HTTP direct, HTTPS et routeur Traefik

Depuis la workstation, exécuter séparément, sans `-k` et sans
redémarrer les services :

```bash
getent ahostsv4 nexus.int.albandrieu.com || true

curl --noproxy '*' --connect-timeout 2 --max-time 10 \
  --silent --show-error -o /dev/null \
  -w 'nexus_backend_http=%{http_code} connect=%{time_connect} total=%{time_total}\n' \
  http://172.17.0.24:8081/
echo "backend_exit=${PIPESTATUS[0]}"

curl --noproxy '*' --connect-timeout 2 --max-time 10 \
  --silent --show-error -o /dev/null \
  --resolve nexus.int.albandrieu.com:443:172.17.0.24 \
  -w 'nexus_ingress_http=%{http_code} tls=%{ssl_verify_result} connect=%{time_connect} total=%{time_total}\n' \
  https://nexus.int.albandrieu.com/
echo "ingress_exit=${PIPESTATUS[0]}"
```

Le `getent` vérifie **le résolveur effectif de la workstation**,
pas la résolution directe de pfSense/Pi-hole déjà validée.
Les codes de retour `curl` et HTTP sont distincts :
`000` signifie qu'aucune réponse HTTP exploitable n'a été reçue ;
`200/302/401` exigent une interprétation selon la route et
l'authentification. Un `404` sur Traefik avec backend fonctionnel
oriente vers un routeur absent/inactif ou un mauvais `Host`.
Un `502/504` oriente vers le chemin reverse-proxy → Nexus.
Un échec TLS doit être analysé sans supprimer la vérification
du certificat.

**Bloquant actuel :** aucune nouvelle réponse HTTP/TLS exploitable
n'a été fournie depuis la confirmation DNS. La variable
`NEXUS_PRIVATE_INGRESS_ENABLED` reste `false` par défaut dans
la configuration déclarative ; il faut vérifier les **labels réellement
déployés** avant d'en déduire que le routeur privé est actif.
Le fait que Pi-hole réponde déjà pour Nexus **n'est pas une preuve**
d'activation de ce routeur.

## Préflight en lecture seule sur la workstation

Exécuter et garder les résultats séparés :

```bash
# 1. Autorité privée : DNS Pi-hole.
dig +tries=1 +time=2 @172.17.0.24 nexus.int.albandrieu.com A

# 2. Délegation LAN : pfSense / Unbound.
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
fonctionnel de Nexus. `curl` doit refuser un certificat incorrect ;
ne pas utiliser `-k` pour déclarer TLS conforme.

### Interprétation

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

## Contrôle de la configuration déployée (TrueNAS, lecture seule)

```bash
sudo docker inspect nexus --format \
  '{{json .Config.Labels}}' | jq 'with_entries(select(.key | startswith("traefik.")))'
sudo docker inspect nexus --format \
  '{{json .NetworkSettings.Networks}}' | jq 'keys'
sudo docker ps --filter name=pihole-dns-sync --format '{{.Names}} {{.Status}}'
```

Ne pas publier de jetons, de configuration Pi-hole intégrale ou de
variables d'environnement. **Activer la route privée seulement après**
avoir confirmé que Traefik est le propriétaire voulu, que la valeur
`NEXUS_PRIVATE_INGRESS_ENABLED=true` atteint réellement le moteur de
rendu Compose TrueNAS, et que le DNS sync peut créer cet unique A privé.
Une variable placée dans le shell d'appel à `midclt` ne prouve pas
qu'elle sera transmise au projet Compose.

Si l'activation est approuvée, relire le rendu effectif avant
un redéploiement ciblé Nexus. Ne pas redémarrer Unbound, Pi-hole,
Traefik, pfBlockerNG, ni modifier Cloudflare pour ce diagnostic.
Rollback : remettre `NEXUS_PRIVATE_INGRESS_ENABLED=false`, redéployer
uniquement Nexus selon son propriétaire de cycle de vie, puis contrôler
la disparition du routeur et de l'A privé par `pihole-dns-sync`.

[Architecture DNS](../dns-ingress-ownership.md) ·
[Runbook H-04](2026-10-26-pfsense-memory-dnsbl-reprise.md)
