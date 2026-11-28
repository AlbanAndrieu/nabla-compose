# PoC purple team ARTEX dans une VM jetable

> Statut : `CODED` (runbook seul). VM, attaque, mesures et acceptation :
> `NOT_RUN`. Décision du propriétaire du 28/11/2026 : « PoC purple team
> isolé » plutôt qu'une App permanente.

## Objectif

Mesurer si la chaîne Traefik → CrowdSec AppSec arrête une attaque web pilotée
par un agent IA, et transformer chaque attaque passée en correctif ou en règle.
ARTEX n'est **jamais** une App TrueNAS : il tourne quelques heures dans une VM
de la Workstation, puis il est détruit.

## Version retenue

| Choix | Valeur | Pourquoi |
| --- | --- | --- |
| Dépôt | [`BaaRai/ARTEX`](https://github.com/BaaRai/ARTEX) | continuation active de l'amont `Autumn-27/ARTEX`, aujourd'hui injoignable ; contrôles intégrés (approbations, périmètre, budgets) |
| Version | `v0.7.0` (21/11/2026), commit `22ae88afabf66e47e73644a0528d8b427c4c80b8` | le tag n'est pas signé (`verified=false`) : on épingle le commit, pas le tag |
| Image | construite dans la VM depuis ce commit | l'image GHCR n'est pas publiée pour `v0.7.0` ; jamais `latest` |
| Licence | AGPL-3.0 | usage interne, sans redistribution |
| Écarté | `jiwoochris/artex-global` | dernière release le 13/10, image en `latest` |

Le `Dockerfile` de ce commit vérifie le SHA-256 des outils qu'il télécharge
(nuclei, httpx, subfinder, katana, ffuf, dalfox), mais ses images de base
(`node:22`, `golang:1.26`, `python:3.12`, `debian:bookworm`) sont en tags, pas
en digests. ARTEX est l'outil de la campagne Storm-0940 signalée par Microsoft
en octobre 2026. Sa provenance reste celle d'un fork communautaire : la VM est
la frontière de confiance, pas l'outil.

## Règles d'engagement

- **Cible unique** : `https://fastapi-sample.albandrieu.com`, résolue vers
  Traefik `172.17.0.24:443`, routeur `fastapi-sample-public` (middleware
  `crowdsec-appsec@file`, puis FastAPI Sample sur TrueNAS).
- **Interdit** : pfSense, Vaultwarden, Keycloak, l'UI et le SSH de TrueNAS,
  Nexus, toute autre App, Internet, la Workstation elle-même.
- Pas de brute force de comptes, pas de déni de service (profil de bruit
  `quiet`), aucune donnée réelle. Fenêtre de 2 h au plus, propriétaire
  présent.

## 0. Go / no-go, sur TrueNAS

L'AppSec n'est pas prouvée active : le diagnostic du 21/11 s'est arrêté à
`appsec_collections=NOT_VERIFIED` ([README CrowdSec](../../apps/crowdsec/README.md)).
Sans un `403` sur le canari, il n'y a rien à mesurer : on s'arrête.

```bash
sudo bash scripts/truenas/diagnose-crowdsec-appsec.sh --runtime
curl -sk -o /dev/null -w '%{http_code}\n' \
  --connect-to fastapi-sample.albandrieu.com:443:172.17.0.24:443 \
  https://fastapi-sample.albandrieu.com/__nabla_appsec_canary_7de17a3fb1134292   # 403 attendu
curl -sk -o /dev/null -w '%{http_code}\n' \
  --connect-to fastapi-sample.albandrieu.com:443:172.17.0.24:443 \
  https://fastapi-sample.albandrieu.com/livez                                    # 200 attendu
```

Puis, à faire par le propriétaire :

- une clé virtuelle LiteLLM `artex-poc` sur le LiteLLM de TrueNAS, avec un
  seul modèle, `max_budget` de 5 USD et `duration` de `7d` : elle expire seule.
  Elle n'entre pas dans `config/litellm/app-keys.json`, qui ne liste que les
  clés permanentes ;
- un engagement DefectDojo `purple-team-artex-<AAAAMMJJ>`.

## 1. VM jetable sur la Workstation

Debian 13 en image cloud, 4 vCPU, 8 Go, 40 Go, réseau libvirt `default`
(NAT). Traefik voit donc l'IP de la Workstation, `172.17.0.57` : ne jamais
ajouter de décision CrowdSec sur cette IP.

Dans la VM, Docker doit allouer hors du LAN `172.17.0.0/24`, sinon le pont
`docker0` capte la route vers TrueNAS ([IPAM](../homelab-network-topology.md#ipam-rules)) :

```bash
echo '{"bip":"10.251.0.1/24","default-address-pools":[{"base":"10.251.0.0/16","size":24}]}' \
  | sudo tee /etc/docker/daemon.json && sudo systemctl restart docker
ip route get 172.17.0.24   # doit sortir par l'interface libvirt, pas par docker0
```

## 2. Construction, Internet encore ouvert

```bash
git clone https://github.com/BaaRai/ARTEX.git && cd ARTEX
git checkout --detach 22ae88afabf66e47e73644a0528d8b427c4c80b8
test "$(git rev-parse HEAD)" = 22ae88afabf66e47e73644a0528d8b427c4c80b8
docker compose build && docker compose pull postgres
```

`.env`, saisi dans la VM et jamais versionné. La clé est tapée par le
propriétaire :

```dotenv
POSTGRES_PASSWORD=<aléatoire, openssl rand -hex 24>
ARTEX_LLM_PROVIDER=openai
ARTEX_LLM_BASE_URL=http://172.17.0.24:4000/v1
ARTEX_LLM_MODEL=<modèle de la clé artex-poc>
OPENAI_API_KEY=<clé artex-poc>
ARTEX_LLM_PRIVATE_ENDPOINTS=172.17.0.24:4000
ARTEX_NOISE_PROFILE=quiet
ARTEX_TASK_BUDGET_TOKENS=2000000
ARTEX_TASK_BUDGET_TURNS=200
ARTEX_INTENT_BUDGET_TURNS=40
```

`ARTEX_UPDATE_CHECK` reste vide : ARTEX ne contacte alors pas GitHub.
`docker-compose.override.yml` fait trois choses :

- il monte `skills/` en lecture seule, pour qu'aucun binaire rechargé à chaud
  ne puisse être réécrit ;
- il fixe la résolution de la cible ;
- il retire le redémarrage automatique, car les règles de l'étape 3 ne
  survivent pas à un reboot de la VM.

```yaml
services:
  artex:
    restart: "no"
    extra_hosts:
      - "fastapi-sample.albandrieu.com:172.17.0.24"
    volumes:
      - ./skills:/app/skills:ro
```

## 3. Verrouillage, avant le premier démarrage

Les conteneurs sortent par la chaîne `FORWARD`, que Docker ouvre à
`DOCKER-USER`. Les règles ci-dessous n'y laissent passer que Traefik et
LiteLLM, sans couper le trafic entre `artex` et `postgres`. L'agent n'a pas
`NET_ADMIN` : il ne peut pas les retirer. L'`egress-guard` du projet n'est pas
utilisé : c'est un conteneur `NET_ADMIN` du projet lui-même.

```bash
sudo iptables -I DOCKER-USER 1 -i br-+ ! -o br-+ -j DROP
sudo iptables -I DOCKER-USER 1 -i br-+ -d 172.17.0.24 -p tcp -m multiport --dports 443,4000 -j ACCEPT
sudo iptables -I DOCKER-USER 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
docker compose up -d
docker compose exec artex curl -sS -m 5 -o /dev/null https://github.com && echo FUITE   # doit échouer
docker compose exec artex curl -sk -m 5 -o /dev/null -w '%{http_code}\n' https://fastapi-sample.albandrieu.com/livez   # 200
docker compose exec artex curl -s -m 5 -o /dev/null -w '%{http_code}\n' http://172.17.0.24:4000/health/liveliness     # 200
```

Une fuite vers GitHub arrête le PoC.

## 4. Configuration d'ARTEX

- UI joignable seulement par tunnel : `ssh -L 8787:127.0.0.1:8787 <vm>`.
  Jeton d'installation : `docker compose logs artex`.
- Une seule ligne de périmètre : `fastapi-sample.albandrieu.com`.
- Interception : approbation humaine de chaque appel d'outil pendant le PoC.
  Le *target gate* (API seulement) est activé s'il est documenté, sinon
  `NOT_RUN` : le pare-feu de la VM reste la vraie frontière.

## 5. Exécution et observation

Une seule tâche : « Évaluer https://fastapi-sample.albandrieu.com, OWASP
Top 10 web, sans brute force ni déni de service ». Pendant ce temps, sur
TrueNAS :

```bash
sudo docker exec crowdsec cscli metrics show appsec
sudo docker exec crowdsec cscli alerts list --since 2h
```

## 6. Mesures

| # | Mesure | Attendu |
| --- | --- | --- |
| M1 | canari avant et après | `403` les deux fois |
| M2 | requêtes d'attaque de la fenêtre vues par Traefik (IP `172.17.0.57`), par code | part des `403` AppSec, avec chiffres |
| M3 | constats ARTEX confirmés | un constat DefectDojo chacun, puis correctif FastAPI Sample ou règle AppSec |
| M4 | charges malveillantes arrivées à FastAPI (`2xx`/`5xx`) | liste des trous AppSec, une règle candidate par trou |
| M5 | bannissements par scénario | **aucun attendu** : `crowdsecurity/whitelists` ignore les IP privées |
| M6 | dépense de la clé `artex-poc` | ≤ 5 USD |

M5 est une limite connue, pas un échec. La mesurer demanderait une IP de lab
dédiée et une exception ciblée à la liste blanche : décision du propriétaire.

## 7. Fin et rollback

```bash
docker compose down -v                    # dans la VM
virsh destroy <vm> && virsh undefine <vm> --remove-all-storage   # sur la Workstation
```

Ensuite : révoquer la clé `artex-poc` sans attendre son expiration, vérifier
`/livez` de FastAPI Sample et rejouer le canari. Rien n'est installé sur
TrueNAS. Si FastAPI Sample est dégradé, le propriétaire le redéploie avec
`update-fastapi-sample.sh`, une action réservée.
