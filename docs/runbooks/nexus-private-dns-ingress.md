# Nexus — diagnostic DNS/HTTPS privé (26 octobre 2026)

**Objet :** distinguer DNS, résolution du poste, Traefik et Nexus pour
`https://nexus.int.albandrieu.com/`. Le succès de
`https://nexus.albandrieu.com/` ne valide pas ce chemin privé.
**État au 27/10 :** DNS privé et backend OK ; TrueNAS a
réconcilié les labels Docker après redéploiement Nexus.
Le routeur privé est **volontairement désactivé**
(`traefik.enable=false`, HTTPS privé 404 / TLS OK).
**WAN_REJECTION_NOT_VERIFIED** : la revue de la règle HAProxy
bloquant exactement `nexus.int.albandrieu.com` est en cours.
Ne pas toucher au chemin public ni publier de DNS `*.int` sur Cloudflare.

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

**Relevé historique avant le Gate 2 :** les réponses HTTP/TLS
n'avaient pas encore été collectées. Elles sont désormais connues :
backend **HTTP 200** ; HTTPS privé **404 avec certificat valide**.
La variable `NEXUS_PRIVATE_INGRESS_ENABLED` reste `false`
par défaut ; le rendu TrueNAS confirme la désactivation et
les labels attendus, tandis que le conteneur actif ne les a
pas encore récupérés. La réponse DNS privée n'est pas une preuve
d'activation du routeur.

## Gate 2 — résultat opérateur : backend HTTP OK, route privée 404

Après les **8/8 réponses DNS** et les **4/4 contrats locaux** validés,
l'opérateur a confirmé, depuis la workstation :

| Vérification | Réponse | Conclusion limitée |
| --- | --- | --- |
| `curl http://172.17.0.24:8081/` | **HTTP 200**, `exit=0`, 2,097 s | Nexus répond directement |
| `curl --resolve nexus.int.albandrieu.com:443:172.17.0.24 https://nexus.int.albandrieu.com/` | **HTTP 404**, `exit=0`, `tls=0`, 14 ms | Connexion HTTPS vérifiée, **aucune route applicative correspondant au Host** ou réponse 404 de l'origine |

Le certificat est vérifié par `curl` (`ssl_verify_result=0`).
Le `404` ne provient **pas** de la résolution DNS. C'est très
probablement le routeur privé Traefik inactif ou non déployé,
mais la provenance exacte du `404` n'est pas encore démontrée.

Le fichier `apps/nexus/compose.yml` conserve une activation
**explicite** : `traefik.enable: "${NEXUS_PRIVATE_INGRESS_ENABLED:-false}"`.
La présence du label déclaratif n'est pas une preuve que l'application
TrueNAS l'a déployé. Vérifier d'abord les **labels effectifs** :

```bash
# Depuis TrueNAS : lecture seule, n'affiche que des labels de routage.
sudo docker inspect nexus --format '{{json .Config.Labels}}' |
  jq 'with_entries(select(.key | startswith("traefik.")))'

# Confirmer l'appartenance du conteneur au réseau partagé.
sudo docker inspect nexus --format '{{json .NetworkSettings.Networks}}' |
  jq 'keys'
```

Si `traefik.enable=false`, corriger le **rendu Compose de la seule
application Nexus** en déployant explicitement
`NEXUS_PRIVATE_INGRESS_ENABLED=true` depuis le propriétaire TrueNAS
de cette variable ; valider **avant** que le routeur ne puisse être
atteint depuis une interface WAN. Une URL `*.int` privée en DNS n'est
**pas à elle seule** une barrière d'accès à l'ingress partagé :
le filtrage public pfSense HAProxy/Traefik doit refuser les Host/SNI
privés depuis Internet. Ne pas considérer un middleware IPAllowList
seul comme protection suffisante si le proxy amont peut représenter
une source WAN comme `172.17.0.1`.

**Aucun changement de runtime n'est exécuté par ce runbook.**
Conserver le contrat du Nexus public et vérifier le rollback
avant tout redéploiement ciblé ; ne pas redémarrer Unbound,
Pi-hole ou Traefik pour réparer un simple routeur.

## Gate 3 — labels Traefik absents du conteneur TrueNAS

**Preuve opérateur du 26 octobre :** la commande `sudo docker inspect nexus`
retourne `null` pour les quatre labels : `traefik.enable`,
`traefik.http.routers.nexus-private.rule`, `entrypoints` et `service`.
Le conteneur actif ne contient donc **pas** le routeur préparé dans
la PR #285. Avec un backend `HTTP 200`, DNS `8/8 PASS` et HTTPS
`404`, `tls_verify=0`, la priorité est l'**écart Compose déclaré
vers runtime TrueNAS**. Un autre provider Traefik pourrait cependant
répondre au Host : le 404 n'identifie pas à lui seul son origine.

### Identifier le propriétaire du conteneur (lecture seule)

```bash
sudo docker inspect nexus --format \
  'container={{.Name}} image={{.Config.Image}} status={{.State.Status}}'

sudo docker inspect nexus --format '{{json .Config.Labels}}' |
  jq '{project: .["com.docker.compose.project"],
       service: .["com.docker.compose.service"],
       enabled: .["traefik.enable"],
       private_rule: .["traefik.http.routers.nexus-private.rule"]}'

sudo docker inspect nexus --format \
  '{{json .NetworkSettings.Networks}}' | jq 'keys'

sudo midclt call app.query |
  jq -c '.[] | select(.name == "nexus") | {name, state}'
```

Ne pas imprimer `.Config.Env`, les secrets ou l'intégralité du
résultat `app.query`. Un `git pull` n'ajoute pas de labels à un
conteneur déjà créé. Vérifier le modèle Compose effectivement utilisé
par la Custom App TrueNAS avant de proposer un redéploiement **Nexus seul**.

**Le défaut de la PR reste `NEXUS_PRIVATE_INGRESS_ENABLED=false`.**
Un redéploiement avec cette valeur laisse le routeur désactivé :
ne pas supposer que la variable du shell `midclt` se transmet au
rendu Compose TrueNAS.

**Sécurité :** un DNS privé n'empêche pas un client Internet d'envoyer
le même Host/SNI à l'ingress public. Avant d'activer la route,
vérifier depuis un réseau externe que pfSense/HAProxy bloque
`nexus.int.albandrieu.com`, sans toucher à
`nexus.albandrieu.com`. Aucune activation automatique ni restart.
## Gate 4 — provenance TrueNAS Apps confirmée par Docker

**Relevé opérateur (26 octobre 2026)** :

```json
{
  "project": "ix-nexus",
  "service": "nexus",
  "config_files": "/mnt/.ix-apps/app_configs/nexus/versions/1.0.0/templates/rendered/docker-compose.yaml"
}
```

Les labels `com.docker.compose.*` établissent que **TrueNAS Apps gère
le conteneur Nexus** et que Docker Compose l'a créé depuis un rendu
interne `.ix-apps`. Ce chemin n'est **pas** le Compose Git canonique
`/mnt/cpool/compose/nabla-compose/apps/nexus/compose.yml`.
Ne jamais éditer ou remplacer manuellement le fichier `.ix-apps` :
il appartient au cycle de vie TrueNAS.

Le chemin du rendu **ne prouve pas** si la Custom App stocke un
`include:` vers Git ou une définition YAML autonome. Il faut
consulter la configuration réelle, avant de choisir `app.update`
ou `app.redeploy`. Une opération sur le dépôt seule ne modifie pas
un conteneur existant.

### Contrôle ciblé de la configuration enregistrée

Sur TrueNAS, sans afficher les secrets :

```bash
# Montre uniquement les noms de propriétés de la configuration TrueNAS.
sudo midclt call app.config nexus | jq 'keys'

# Affiche uniquement les labels et réseaux du modèle Compose généré.
CFG="/mnt/.ix-apps/app_configs/nexus/versions/1.0.0/templates/rendered/docker-compose.yaml"
sudo docker compose -f "$CFG" config --format json |
  jq '{services: (.services | keys),
       nexus_labels: .services.nexus.labels,
       nexus_networks: .services.nexus.networks}'

# Vérifie le chemin Git sans écrire et sans afficher env_file.
git -C /mnt/cpool/compose/nabla-compose status --short -- apps/nexus/compose.yml
```

Utiliser `set -o pipefail` en session Bash si nécessaire : un
`docker compose config` en erreur ne doit pas être considéré
comme preuve d'absence de labels. La configuration rendue peut
intégrer des fichiers sensibles ; ne pas afficher son contenu
intégral, `.Config.Env`, les valeurs `env_file` ou l'intégralité
de `app.config`.

**Décision selon résultats :**

- `include` enregistré vers `apps/nexus/compose.yml` : vérifier
  d'abord la version exacte du fichier sur TrueNAS et le rendu
  de l'opt-in (défaut `false`), puis planifier une réconciliation
  **de l'application Nexus seule**.
- Aucun `include` enregistré : migrer la configuration **de la
  Custom App TrueNAS** vers un wrapper `include` approuvé, après
  revue de la configuration déployée et sauvegarde de retour arrière.
- Labels présents dans Compose rendu mais absents du conteneur :
  écart de cycle de vie ; un redéploiement ciblé peut être pertinent
  après validation de l'impact et du rollback.

Dans tous les cas, ne pas activer le routeur privé avant la preuve
que le frontal WAN refuse le Host/SNI `nexus.int.albandrieu.com`.
Ne pas modifier les routes de `nexus.albandrieu.com`.
## Gate 5 — Compose TrueNAS rendu avec routeur désactivé (relevé opérateur)

**Preuve opérateur complémentaire du 26 octobre :**

- `sudo midclt call app.config nexus | jq 'keys'` retourne **`["include"]`**.
  La configuration enregistrée utilise bien la fonction `include`
  d'une Custom App. Le chemin exact référencé reste à lire ; la
  présence de la clé ne prouve pas encore quel fichier elle inclut.
- `sudo docker compose -f "$CFG" config --format json` donne
  exactement un service `nexus`. Les labels du routeur privé sont
  présents dans le rendu, mais **`traefik.enable="false"`**.
  Routeur déclaré sur `websecure`, règle
  `Host(\`nexus.int.albandrieu.com\`)`, backend HTTP `:8081`,
  réseau `traefik_network`.
- `nexus_networks: {"traefik_network": null}` signifie que le
  service utilise ce réseau sans options réseau particulières
  dans le modèle normalisé, **pas que le réseau est absent**.
- Le précédent `sudo docker inspect nexus` retournait `null`
  pour ces labels dans le conteneur en cours d'exécution.
  Le rendu a donc **évolué sans être appliqué au conteneur**.

### Interprétation et séparation des opérations

1. **Réconciliation de runtime uniquement :** redéployer **Nexus seul**
   selon TrueNAS Apps ferait normalement reprendre au conteneur les
   labels du rendu, mais avec `traefik.enable=false`.
   Le routeur **resterait désactivé** et le `404` attendu.
2. **Activation privée séparée :** faire passer l'opt-in à `true`
   depuis le contexte d'interpolation **réel** du `include` et
   contrôler le rendu *avant* de redéployer. Un `env_file:` du service
   Nexus injecte des variables **dans le conteneur**, ce n'est pas
   nécessairement une source d'interpolation `${...}` pour Compose.
   Le `include` Compose peut charger un fichier `.env` du répertoire
   de son sous-projet ; confirmer son effet sur le rendu TrueNAS
   plutôt que de supposer qu'un export shell transmis à `midclt` agit.
3. **Contrôle réseau bloquant :** ne pas activer le routeur tant que
   le frontal public (pfSense/HAProxy) ne rejette pas le Host/SNI
   `nexus.int.albandrieu.com` depuis le WAN. Un A privé ne suffit
   pas à empêcher un client externe d'envoyer ce Host.

### Vérifications restantes, lecture seule sur TrueNAS

```bash
set -o pipefail

# Contrat du wrapper enregistré, sans exposer ses autres champs.
sudo midclt call app.config nexus |
  jq '{include_type: (.include | type),
       include_paths: .include}'

# État normalisé de la route privée : zéro valeur de secret.
CFG='/mnt/.ix-apps/app_configs/nexus/versions/1.0.0/templates/rendered/docker-compose.yaml'
sudo docker compose -f "$CFG" config --format json |
  jq -e '.services.nexus as $n |
    {enabled: $n.labels["traefik.enable"],
     host_rule: $n.labels["traefik.http.routers.nexus-private.rule"],
     networks: ($n.networks | keys)}'

# Compare uniquement les labels du conteneur actif.
sudo docker inspect nexus --format '{{json .Config.Labels}}' |
  jq '{enabled: .["traefik.enable"],
       host_rule: .["traefik.http.routers.nexus-private.rule"]}'

# Confirmer l'existence du réseau externe, sans le modifier.
sudo docker network inspect traefik_network --format '{{.Name}}'
```

**Choix de l'opérateur avant la première action mutante :**
vérifier la provenance réelle de `include`, l'état Git de la
workstation TrueNAS (plusieurs diagnostics ont montré `tree=dirty`),
la santé de Nexus, la sauvegarde de son dataset et la disponibilité
d'une fenêtre d'interruption. La commande officielle
`app.redeploy nexus` sur TrueNAS est un **job de redéploiement**
avec arrêt/recréation, qui peut tirer des images ; ne pas
l'exécuter comme simple contrôle de labels. Ne pas éditer `.ix-apps`
et ne pas recréer la Custom App.
## Gate 6 — include exact, checkout Nexus propre et réseau présent

**Nouveau relevé opérateur :**

- `sudo midclt call app.config nexus | jq '.include'` retourne
  `["/mnt/cpool/compose/nabla-compose/apps/nexus/compose.yml"]`.
  Le wrapper pointe bien vers le fichier Git attendu.
- `git -C /mnt/cpool/compose/nabla-compose status --short -- apps/nexus`
  ne retourne rien : aucun changement local signalé **dans ce scope**
  (pas une garantie de propreté du reste du checkout).
- `sudo docker network inspect traefik_network --format '{{.Name}}'`
  retourne `traefik_network` : le réseau existe.

**Décision :** il n'est pas nécessaire de recréer la Custom App ni
de corriger son `include`. Le rendu contient déjà la route privée
mais `traefik.enable=false`, alors que le conteneur actif ne
contient pas ces labels : réconciliation du runtime attendue.

L'opérateur **annonce le redémarrage de Nexus**, mais aucune sortie
du redémarrage/redéploiement n'est encore disponible. Ne pas marquer
la réconciliation `PASS` avant une nouvelle inspection. Un
`docker restart nexus` n'applique **aucun nouveau label** ; seul
le déploiement géré par TrueNAS avec recréation de conteneur peut
appliquer le nouveau modèle rendu. Cette opération peut interrompre
le service Nexus : fenêtre de maintenance et rollback requis.

### Gate après opération (sans nouvelle mutation)

```bash
sudo midclt call app.query |
  jq '.[] | select(.name == "nexus") | {name, state}'

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

Si les labels du rendu apparaissent avec `enabled=false`,
la synchronisation Compose → Docker a progressé, mais le routeur
privé **doit rester inactif** ; un `404` HTTPS ne suffit pas
à conclure à une nouvelle panne. La prochaine opération de
configuration, distincte du redéploiement, sera de décider
du `true` uniquement après le contrôle d'isolation WAN.
## Gate 7 — réception du redéploiement ciblé Nexus

**Résultats opérateur après redémarrage / réconciliation TrueNAS :**

| Sonde | Relevé | Statut |
| --- | --- | --- |
| `midclt app.query nexus` | `name=nexus`, `state=RUNNING` | PASS — état déclaré |
| `docker inspect nexus` | `traefik.enable="false"` | PASS — label appliqué et opt-in désactivé |
| `docker inspect nexus` | `rule=Host(\`nexus.int.albandrieu.com\`)` | PASS — règle présente |
| `docker inspect nexus` | `service=nexus-private` | PASS — service déclaré |
| Nexus direct `172.17.0.24:8081/` | HTTP **200** | PASS — backend répond |
| HTTPS privé via `--resolve` | HTTP **404**, `ssl_verify_result=0` | ATTENDU — routeur désactivé |

**Conclusion :** la désynchronisation labels entre Compose rendu
et conteneur actif est corrigée. Le `404` ne justifie **aucune**
intervention sur le DNS, Unbound, Pi-hole, TrueNAS Apps ou Traefik.
Le fonctionnement du site Nexus public n'a pas été retesté
dans ces commandes : **PUBLIC_ROUTE_NOT_VERIFIED**.

### Contrôle bloquant avant opt-in du routeur privé

Le Compose `apps/traefik/compose.yml` déclare un frontal
`pfSense HAProxy -> TrueNAS Traefik websecure :443`, avec
ré-encryption TLS et conservation du Host. Le même entrypoint
`websecure` sert des exceptions `*.int` publiques, dont
`s3.int.albandrieu.com`. Un enregistrement DNS privé **n'interdit
pas** un client WAN d'envoyer le Host/SNI
`nexus.int.albandrieu.com` à l'adresse publique de pfSense.

Avant tout passage de `NEXUS_PRIVATE_INGRESS_ENABLED` à `true` :

1. Lire la configuration HAProxy **effective** sur pfSense et
   confirmer une ACL WAN qui refuse **spécifiquement**
   `nexus.int.albandrieu.com` avant son backend Traefik,
   sans modifier l'exception publique `s3.int.albandrieu.com`.
2. Valider depuis un **réseau réellement externe**, sans VPN,
   que ce Host/SNI est rejeté au frontal HAProxy ; un HTTP `404`
   renvoyé par Traefik avec son routeur désactivé ne prouve
   **pas** qu'HAProxy bloque le trafic. Identifier le composant
   qui répond ou les règles ACL/compteurs correspondants.
3. Préparer le mécanisme d'interpolation `include` pour
   obtenir `traefik.enable="true"` dans le rendu, sans éditer
   le fichier généré `.ix-apps` ni exposer les secrets.
4. Prévoir un rollback du seul service Nexus et vérifier
   ensuite HTTP direct, HTTPS LAN, certificat, route publique
   et impossibilité de connexion via le frontal WAN.

**Aucune activation demandée ou réalisée pour cette réception.**
## Gate 8 — `--resolve` WAN depuis le LAN ne prouve pas une ACL externe

L'opérateur ne dispose pas de machine externe. Depuis la workstation
LAN, la commande `curl --resolve nexus.int.albandrieu.com:443:82.66.4.247`
renvoie **HTTP 404 / tls=0**. Ce test cible l'IP publique de pfSense
mais ne garantit **pas** qu'un paquet provient du WAN : pfSense peut
utiliser une redirection/NAT reflection ou un autre chemin local.
En l'état, `traefik.enable="false"` et `--resolve ...:172.17.0.24`
renvoient également 404 ; une réponse identique n'est pas la preuve
d'un `deny` HAProxy. Noter **WAN_REJECTION_NOT_VERIFIED**.

### Solution sans poste externe : examiner la politique HAProxy

L'architecture déclarative mentionne pfSense HAProxy en frontal
WAN et une ré-encryption TLS vers le Traefik partagé :443.
Une règle **sur le frontend WAN HAProxy** qui refuse le
`Host` privé `nexus.int.albandrieu.com` (et le SNI lorsque
pertinent) doit empêcher l'atteinte de Traefik depuis le WAN,
tout en autorisant un client LAN qui se connecte directement
à `172.17.0.24:443`. Ne pas rejeter tout `*.int` :
`s3.int.albandrieu.com` constitue une exception publique connue.

Sur la workstation, si l'accès SSH habituel à pfSense est autorisé,
afficher **uniquement les directives de routage et de refus** du
HAProxy généré, sans afficher les certificats ou le reste de
sa configuration :

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 home.albandrieu.com sh -s <<'PFSENSE_HAPROXY_READONLY'
set -eu
config=/var/etc/haproxy/haproxy.cfg
if [ ! -r "$config" ]; then
  echo "ERROR: HAProxy generated configuration unavailable" >&2
  exit 2
fi
awk '
  /^[[:space:]]*(frontend|listen)[[:space:]]+/ { section=$2 }
  /^[[:space:]]*bind[[:space:]]+/ && /:443/ {
    printf "section=%s listener_443=yes\n", section
  }
  /^[[:space:]]*acl[[:space:]]+/ &&
    /nexus|hdr\(host\)|ssl_fc_sni/ {
    printf "section=%s rule=%s\n", section, $0
  }
  /^[[:space:]]*http-request[[:space:]]+(deny|return)[[:space:]]+/ {
    printf "section=%s action=%s\n", section, $0
  }
  /^[[:space:]]*use_backend[[:space:]]+/ &&
    /traefik|front/ {
    printf "section=%s backend_route=%s\n", section, $0
  }
' "$config"
PFSENSE_HAPROXY_READONLY
```

Cette lecture n'affirme pas à elle seule que les règles sont
chargées dans le processus courant. Si des noms de domaines ou
d'ACL sont sensibles, masquer les valeurs avant partage.
Une règle `http-request deny` doit être reliée à une ACL
qui correspond réellement au Host/SNI privé dans le **frontend
WAN actif**, avant sa sélection de backend. Un simple Host routé
vers un backend par défaut ne constitue pas un refus.

### Gate d'activation

1. Auditer le **frontend WAN effectif** et sa règle de refus
   ciblée Nexus, sans changer les autres exceptions.
2. Si la règle manque, la préparer dans l'UI pfSense HAProxy
   puis vérifier la configuration générée et la syntaxe avant
   son application ; ne pas éditer `haproxy.cfg` à la main.
3. Une fois le refus en place, tester la voie LAN directe avec
   `--resolve ...:172.17.0.24`, puis éventuellement depuis
   un téléphone en données mobiles (Wi-Fi/VPN désactivés) avec
   un client permettant de forcer la résolution. Sans tel test,
   le refus WAN reste fondé sur une revue de configuration,
   et ne doit pas être déclaré validé par test externe.
4. Activer **uniquement Nexus** via une source Compose dont
   l'interpolation produit `traefik.enable="true"` ; vérifier
   le rendu, puis la réconciliation TrueNAS. Le Host doit alors
   être routable en LAN ; tester également le Nexus public.
## Gate 9 — HAProxy réel : ACL de l'ancien nom, routeur Traefik potentiellement générique

**Preuve opérateur du 27 octobre**, obtenue en SSH sur pfSense
depuis la workstation par filtrage de `/var/etc/haproxy/haproxy.cfg` :

```text
section=fWeb_HTTPS listener443=yes
section=fWeb_HTTPS acl=acl nexus-albandrieu var(txn.txnhost) -m str -i nexus-albandrieu.int.albandrieu.com
section=fWeb_HTTPS route=use_backend prod_front-traefik-https_ipvANY if int aclcrt_fWeb_HTTPS
section=fWeb_HTTPS route=use_backend prod_front-traefik-https_ipvANY if aclcrt_fWeb_HTTPS
```

Le précédent extrait contenait aussi des routes ciblées `hello`
et `dozzle`. Aucune directive `http-request deny` ou `return`
n'y a été imprimée. Le filtre utilisé **ne remontait pas**
la définition de l'ACL `int`, de `aclcrt_fWeb_HTTPS`, ni la
création de `var(txn.txnhost)` ; ce n'est pas une preuve exhaustive
de la politique du frontend ou de la configuration en mémoire.

**Distinction des noms :**

- **Cible voulue :** `nexus.int.albandrieu.com` (routeur Traefik
  déclaré et DNS privé conforme).
- **ACL historique observée :**
  `nexus-albandrieu.int.albandrieu.com` (nom différent).
  Sa seule présence ne prouve ni un refus ni un routage du nom
  voulu ; ne pas la supprimer sans identifier ses utilisateurs.
- **Routes possibles :** `if int aclcrt_fWeb_HTTPS` et
  `if aclcrt_fWeb_HTTPS` peuvent envoyer un Host privé à
  Traefik. Le résultat du test `curl --resolve` depuis le
  LAN sur l'IP publique était HTTP 404 / TLS 0, et Traefik
  répond déjà 404 sur LAN car `traefik.enable=false`.
  **WAN_REJECTION_NOT_VERIFIED** demeure bloquant.

### Compléter l'audit sans machine externe — frontend renommé

**Rectificatif du 27 octobre :** l'opérateur a renommé le frontend
HAProxy `fWeb_HTTPS` en **`main_Web_HTTPS`**. Le premier filtre
`awk` communiqué a échoué sur pfSense avec `syntax error at source
line 6` (condition multiligne coupée après `active && (`).
**Aucune preuve ACL n'a été collectée par cette commande** : ne pas
l'interpréter comme un frontend sans route ou sans refus.

Le script versionné utilise un programme AWK **POSIX** dont
chaque condition est sur une seule ligne, et cible
`main_Web_HTTPS` **par défaut**. Il s'exécute via le SSH existant
depuis la workstation, sans transfert persistant vers pfSense :

```bash
# Actualiser cette branche de la PR #289 au préalable.
bash scripts/workstation/inspect-nexus-haproxy-frontend.sh

# Contrat hermétique, aucun SSH :
just nexus-private-ingress-test
```

Le script lit seulement `/var/etc/haproxy/haproxy.cfg`.
Il expose les ACL utiles (`int`, `aclcrt_*`, Nexus), les
règles `http-request set-var(txn.txnhost)` et `deny/return`,
les éventuelles règles `tcp-request`, `use_backend` et
`default_backend` du **frontend exact**, sans imprimer les
binds/certificats, les headers ni les sections backend.
Il échoue avec un code non nul si le frontend demandé n'existe
pas, au lieu de conclure à une politique absente.

Le résultat `wan_rejection=NOT_VERIFIED` est volontaire :
l'inspection ciblée d'un fichier généré n'est pas la preuve
d'un refus WAN effectif. Vérifier la normalisation de Host,
l'ordre des directives, le rechargement HAProxy et les
frontends WAN supplémentaires, sans changer les services.

Pour examiner exceptionnellement l'ancien frontend, utiliser
`--frontend fWeb_HTTPS` (pas le défaut actuel).
Ne pas partager les noms d'ACL ou de domaines sensibles.

### Remédiation à préparer, pas à appliquer ici

Configurer depuis l'UI du paquet pfSense HAProxy **sur le
frontend WAN `main_Web_HTTPS`**, et non dans le fichier généré :

```haproxy
acl nexus_private_wan var(txn.txnhost) -m str -i nexus.int.albandrieu.com
http-request deny deny_status 403 if nexus_private_wan
```

**Exemple conceptuel**, à valider contre la ligne réelle qui
alimente `txn.txnhost`. Si cette variable n'est pas normalisée
(casse, `:443`), ajuster la règle avec l'expression adaptée
au runtime HAProxy. L'action de refus doit être effective
avant le routage vers le backend Traefik, et ne pas toucher
`s3.int.albandrieu.com` ni le domaine Nexus public. En
présence d'autres frontends publics, vérifier leur couverture
séparément. Conserver un export/rollback pfSense, tester
la syntaxe du HAProxy généré et vérifier son rechargement.
**Ne pas interpréter un HTTP 404 Traefik comme un 403 HAProxy.**

Après preuve de cette politique, seulement, préparer le
`traefik.enable=true` pour Nexus et son redéploiement TrueNAS
contrôlé ; l'accès LAN doit alors donner une réponse applicative
plutôt qu'un 404 de routeur. Un test hors LAN, s'il est
réalisable plus tard depuis un réseau mobile, restera
la meilleure preuve de bout en bout du refus WAN.
## Gate 10 — réception finale des routes HAProxy du 27 octobre

**Résultat de l'opérateur (frontend actif `main_Web_HTTPS`) :**

- `just nexus-private-ingress-test` : **14/14 PASS**
  (5 contrats Nexus et 9 tests de l'inspecteur).
- Ligne 89 : `acl nexus var(txn.txnhost) -m str -i
  nexus.int.albandrieu.com` : l'ACL du Host souhaité existe.
- Ligne 94 : l'ACL `aclcrt_main_Web_HTTPS` contient une
  expression pour un sous-domaine de `int.albandrieu.com`.
  La ligne 96 initialise `txn.txnhost` depuis `hdr(host)`.
- Ligne 128 **ACTUELLE** :
  `use_backend prod_front-traefik-https_ipvANY if nexus aclcrt_main_Web_HTTPS`.
  Le Host Nexus est donc explicitement associé au backend
  **Traefik**, avant les routes génériques des lignes 132–133.
- Aucun `http-request deny/return` n'est apparu dans
  l'extraction ciblée du frontend. Ceci **ne prouve pas**
  l'absence de toute politique pfSense/PF/NAT ailleurs.

Le relevé *antérieur* de la ligne 128 pointait vers
`nexus-albandrieu_ipvANY` ; il est **supplanté** par le relevé
ci-dessus. L'appel à l'inspecteur avec
`--backend nexus-albandrieu_ipvANY` a correctement échoué :
`ERROR: backend 'nexus-albandrieu_ipvANY' not found`.
Cet échec ne signale **pas** une panne de Nexus. Il signifie
que le backend demandé n'existe pas dans le fichier HAProxy
actuellement inspecté. Ne pas le recréer.

### Suivre le backend actif, pas un nom historique

Depuis la workstation, après mise à jour du worktree de la PR #289 :

```bash
just nexus-private-ingress-test

# Confirme le frontend et affiche nexus_declared_backend=…
bash scripts/workstation/inspect-nexus-haproxy-frontend.sh

# Vérifie seulement les cibles du backend Traefik actuellement déclaré.
bash scripts/workstation/inspect-nexus-haproxy-frontend.sh \
  --backend prod_front-traefik-https_ipvANY
```

Le script AWK ne divulgue pas la ligne serveur HAProxy complète,
les paramètres TLS ou les secrets. S'il ne trouve pas ce backend,
le diagnostic s'arrête sans inférer de cible. Une autre modification
du frontend impose de relire `nexus_declared_backend` avant
de renouveler le contrôle ciblé.

### Conséquences sécurité et opérationnelles

Le `404 / tls=0` obtenu en visant l'IP publique depuis le LAN
est maintenant **cohérent avec** le chaînage HAProxy → Traefik
et `traefik.enable=false` confirmé précédemment, mais il n'en
constitue pas une preuve de bout en bout. La source reste LAN
(éventuel NAT reflection) et un filtrage frontal WAN reste
**WAN_REJECTION_NOT_VERIFIED** ; aucune conclusion d'accès
extérieur autorisé ou refusé n'est possible sur ce seul test.

**Ne pas passer `NEXUS_PRIVATE_INGRESS_ENABLED=true` encore.**
Préparer dans l'UI pfSense une action de refus du Host exact
`nexus.int.albandrieu.com` au frontend WAN actif, sans bloquer
les exceptions publiques (`s3.int.albandrieu.com`) ni
`nexus.albandrieu.com`. Vérifier l'ordre des règles,
leur compilation/rechargement, le rollback et les autres
frontends exposés. Ensuite seulement, activer le routeur
Traefik privé pour les clients qui se connectent **directement**
au LAN `172.17.0.24:443` ; valider de nouveau Nexus HTTP,
HTTPS privé et Nexus public. Aucune mutation n'est effectuée ici.
## Gate 11 — chaîne HAProxy → Traefik confirmée, filtrage WAN à appliquer

**Relevé de la workstation, 27 octobre 2026 (HEAD `7300e891`) :**

| Test / composant | Résultat |
| --- | --- |
| `just nexus-private-ingress-test` | **15/15 PASS** (5 Nexus, 10 inspecteur) |
| Frontend HAProxy | `main_Web_HTTPS`, ligne 47 |
| ACL Nexus | `nexus.int.albandrieu.com`, ligne 89 |
| Routage spécifique | `use_backend prod_front-traefik-https_ipvANY if nexus aclcrt_main_Web_HTTPS`, ligne 128 |
| Backend déclaré | `nexus_declared_backend=prod_front-traefik-https_ipvANY` |
| Définition backend | `backend=prod_front-traefik-https_ipvANY`, ligne 311 |
| Cible effective déclarée | `backend_server=traefik-https target=172.17.0.24:443` |
| Règle de refus HTTP Nexus sur frontend | **NON OBSERVÉE dans cet extrait** |
| Rejet effectif WAN | `WAN_REJECTION_NOT_VERIFIED` |

Le relevé confirme la **topologie déclarée** depuis HAProxy jusqu'à
Traefik. Il ne prouve pas qu'une requête issue d'Internet
atteint réellement le frontend : une politique pfSense/PF/NAT
peut encore bloquer ce trafic. Il ne démontre pas non plus
la prise en compte de la configuration par le processus HAProxy
actif. Le précédent `404` envoyé depuis le LAN à l'adresse
WAN demeure **non concluant sur l'isolation WAN**.

### Changement à préparer dans pfSense (non appliqué)

Dans **Services → HAProxy → Frontends → `main_Web_HTTPS`**,
préparer une ACL **nouvelle et spécifique** au Host privé Nexus,
puis l'associer à une action **HTTP request deny** avant
la sélection du backend. L'exemple HAProxy attendu à vérifier
après rendu du paquet pfSense est :

```haproxy
acl nexus_private_wan req.hdr(host) -m reg -i ^nexus\.int\.albandrieu\.com(:[0-9]{1,5})?$
http-request deny deny_status 403 if nexus_private_wan
```

Le motif ignore la casse et tolère un port explicite dans
le Host. L'exemple doit être transposé aux champs ACL/action
de la version du paquet HAProxy réellement installée ;
**ne pas éditer `/var/etc/haproxy/haproxy.cfg` à la main**.
Si le paquet offre une action de refus standard mais pas
le champ `deny_status`, le code 403 est normalement la
réponse par défaut de `http-request deny`.

**Restrictions de changement :**

- Ne pas utiliser une règle générique bloquant `*.int` :
  `s3.int.albandrieu.com` reste une exception publique.
- Conserver `nexus.albandrieu.com` et les autres backends publics.
- Vérifier que `main_Web_HTTPS` est bien le frontend qui
  écoute sur WAN `:443`, et inventorier les autres frontends
  publics applicables avant d'accepter la protection.
- Sauvegarder la configuration pfSense et disposer d'un rollback
  avant Apply ; aucune action réseau n'est exécutée par ce runbook.

### Réception après application par l'opérateur

1. Vérifier la configuration HAProxy **générée** et la syntaxe
   selon le paquet installé ; confirmer `acl nexus_private_wan`
   et `http-request deny ... if nexus_private_wan` dans
   le frontend `main_Web_HTTPS`, dans le bon ordre.
2. Confirmer le rechargement du processus HAProxy et qu'il
   exécute la configuration courante.
3. Depuis la workstation, **LAN vers IP publique** :

   ```bash
   curl --noproxy '*' --connect-timeout 3 --max-time 10 -sS \
     --resolve nexus.int.albandrieu.com:443:82.66.4.247 \
     -o /dev/null -w 'edge_http=%{http_code} tls=%{ssl_verify_result}\n' \
     https://nexus.int.albandrieu.com/
   ```

   Un éventuel `403` cohérent avec la règle confirme une
   réponse du chemin local vers le frontal, **pas** une
   démonstration indépendante du rejet des clients WAN
   (NAT reflection possible). Conserver `WAN_REJECTION_NOT_VERIFIED`
   sans contrôle extérieur ou preuve réseau équivalente.
4. Confirmer que `s3.int.albandrieu.com` et
   `nexus.albandrieu.com` continuent à suivre leur chemin
   habituel ; distinguer réponses attendues 401/403 applicatives
   des erreurs d'acheminement.
5. **Seulement après les validations d'isolation**, envisager
   l'activation `NEXUS_PRIVATE_INGRESS_ENABLED=true` dans
   le rendu TrueNAS, puis un redéploiement **Nexus seul**.
   Vérifier l'HTTPS privé **directement sur** `172.17.0.24:443`
   par `--resolve` pour éviter le frontal WAN.

**État final de cette étape : `PENDING_WAN_DENY`**.
## Gate 12 — ACL de refus Nexus déclarée par l'opérateur, à réceptionner

**Nouveau relevé déclaratif de l'opérateur (27 octobre 2026) :**

```haproxy
acl nexus var(txn.txnhost) -m reg -i ^nexus\.int\.albandrieu\.com(:[0-9]{1,5})?$
http-request deny deny_status 403 if nexus aclcrt_main_Web_HTTPS
```

**Statut : `OPERATOR_RULE_REPORTED / EFFECTIVE_DENY_NOT_VERIFIED`.**
La règle est signalée comme ajoutée dans pfSense, mais nous n'avons
pas encore la preuve que le paquet l'a régénérée et chargée ni
l'ordre réel des directives HTTP. Ne pas considérer cette
déclaration comme une réception WAN.

La condition `if nexus aclcrt_main_Web_HTTPS` est une
**conjonction** : toutes les ACL doivent correspondre.
D'après le dernier relevé, l'ACL `aclcrt_main_Web_HTTPS`
compare aussi `txn.txnhost` avec une expression régulière de
nom de domaine. Elle est distincte de l'ACL Nexus et
pourrait évoluer ; son nom ne signifie pas qu'elle valide
le certificat TLS. Le nom `nexus` était déjà utilisé pour
le routage `use_backend ... if nexus ...` : modifier cette ACL
peut également modifier les critères de sélection du backend.
Une ACL indépendante est plus simple à auditer :

```haproxy
acl nexus_private_wan var(txn.txnhost) -m reg -i ^nexus\.int\.albandrieu\.com(:[0-9]{1,5})?$
http-request deny deny_status 403 if nexus_private_wan
```

Ce bloc est une **recommandation pour la configuration pfSense**
(pas une modification automatique). Avec `txn.txnhost`,
`http-request set-var(txn.txnhost) hdr(host)` **doit précéder**
la directive `http-request deny` dans le frontend généré.
Les actions `http-request` sont évaluées dans leur ordre de
déclaration : une ACL déclarée en amont n'initialise pas
la variable à elle seule. Si cette séquence ne peut être
garantie dans l'UI, évaluer une ACL qui lit directement
`req.hdr(host)` plutôt qu'une variable de transaction.

### Réception depuis la workstation (aucun changement réseau)

```bash
# Récupérer la PR #289 dans le worktree dédié.
just nexus-private-ingress-test

# Observer les lignes et leur ordre dans la configuration générée :
bash scripts/workstation/inspect-nexus-haproxy-frontend.sh \
  --backend prod_front-traefik-https_ipvANY

# Exercer le frontend HAProxy à l'IP publique depuis le LAN :
curl --noproxy '*' --connect-timeout 3 --max-time 10 \
  --resolve nexus.int.albandrieu.com:443:82.66.4.247 \
  -sS -o /dev/null \
  -w 'edge_http=%{http_code} tls=%{ssl_verify_result}\n' \
  https://nexus.int.albandrieu.com/

# Contrôle séparé de Traefik depuis le LAN, sans passer par pfSense :
curl --noproxy '*' --connect-timeout 3 --max-time 10 \
  --resolve nexus.int.albandrieu.com:443:172.17.0.24 \
  -sS -o /dev/null \
  -w 'lan_traefik_http=%{http_code} tls=%{ssl_verify_result}\n' \
  https://nexus.int.albandrieu.com/
```

**Réception attendue si le paquet a appliqué la règle :**
l'inspecteur doit montrer l'ACL adéquate et une ligne
`http-request set-var(txn.txnhost) hdr(host)` située
**avant** `http-request deny ... if ...` dans
`main_Web_HTTPS`. Un `403` sur l'IP publique depuis le LAN
serait compatible avec le refus frontal, tandis que
Traefik LAN peut encore répondre `404` avec
`traefik.enable=false`. En revanche, **un seul HTTP 403**
ne prouve ni quel composant a répondu, ni le rejet d'un
client Internet : corroborer la provenance HAProxy par
sa configuration/log ou un test extérieur indépendant.

Vérifier que `nexus.albandrieu.com` et l'exception publique
`s3.int.albandrieu.com` restent disponibles. Ne pas
activer le routeur Nexus privé avant confirmation du
frontend WAN, de sa configuration chargée et du rollback.
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
