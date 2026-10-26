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
