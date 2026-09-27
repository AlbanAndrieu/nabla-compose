# Incident DNS pfSense / Talos du 27 septembre 2026

## Résumé

Le reboot contrôlé de TrueNAS du 27 septembre 2026 a révélé une dépendance
circulaire entre le cluster Talos/Kubernetes et une application DNS hébergée sur
le même TrueNAS.

Les trois nœuds Talos utilisaient, via DHCP, `172.17.0.24` comme **unique
resolver DNS upstream**. Cette adresse est celle du host TrueNAS et expose
Pi-hole sur `TCP/UDP 53`.

La procédure de maintenance a correctement arrêté les applications TrueNAS,
dont Pi-hole. Talos a alors conservé `127.0.0.53` comme resolver local mais son
seul upstream, `172.17.0.24:53`, ne répondait plus. Les pulls d'images depuis
`ghcr.io` et `registry.k8s.io` ont échoué, ce qui a empêché le retour du
driver CSI TrueNAS/NFS.

Le défaut a été corrigé en restaurant le contrat DNS prévu par l'architecture :

```text
Talos / LAN clients
        |
        v
pfSense / Unbound 172.17.0.1:53
        |
        +-- DNS public ------------------------> résolution récursive
        |
        `-- int.albandrieu.com Domain Override
                    |
                    v
              Pi-hole 172.17.0.24:53
                    |
                    v
        FQDN privés -> 172.17.0.24 -> Traefik -> service
```

Le serveur DNS annoncé par le DHCP LAN pfSense a été changé de
`172.17.0.24` à `172.17.0.1`. Les machine configs Talos ont également été
patchées pour imposer `172.17.0.1` comme nameserver et ne plus dépendre d'un
resolver fourni uniquement par DHCP.

Après correction, les trois nœuds Talos ont exposé un
`DNSUpstream 172.17.0.1:53 healthy=true`, le controller et le DaemonSet CSI ont
convergé, puis le smoke test NFS cross-node a validé l'écriture sur
`taloswk01`, la lecture sur `taloswk02` et le reclaim du PV.

## Impact

Pendant l'incident :

- le cluster Kubernetes lui-même a pu être remis sur ses IP historiques
  `172.17.0.50/51/52`, mais certains workloads système ne pouvaient pas tirer
  leurs images ;
- le controller `truenas-csi-controller` et le DaemonSet
  `truenas-csi-node` ont été bloqués en `ErrImagePull/ImagePullBackOff` ;
- les `CSINode` des workers ne publiaient pas `csi.truenas.io` tant que les
  node plugins ne pouvaient pas démarrer ;
- les volumes existants n'ont pas été perdus et aucun VolumeAttachment stale
  n'a été trouvé sur les anciens objets Node ;
- les 97 Apps TrueNAS étaient volontairement `STOPPED` pendant la phase de
  recovery, conformément au runbook de reboot.

La panne DNS publique des Talos était donc un **blocage de restauration** et non
une perte de données CSI.

## Symptômes observés

### DNS Talos

Sur les trois nœuds :

```text
/etc/resolv.conf:
nameserver 127.0.0.53

ResolverStatus:
["172.17.0.24"]

DNSUpstream:
172.17.0.24:53
```

Les logs `dns-resolve-cache` ont montré des erreurs vers
`172.17.0.24:53` :

```text
read: connection refused
i/o timeout
```

Les erreurs touchaient notamment :

```text
registry.k8s.io
ghcr.io
discovery.talos.dev
```

### pfSense / Unbound

Depuis TrueNAS, pfSense/Unbound répondait correctement :

```bash
dig @172.17.0.1 ghcr.io A
dig @172.17.0.1 registry.k8s.io A
```

Les requêtes retournaient `NOERROR`, ce qui a isolé la panne sur le choix du
resolver Talos plutôt que sur Unbound ou l'accès WAN.

Les resolvers publics testés en diagnostic répondaient également.

### CSI

Avant correction DNS :

```text
truenas-csi-controller  -> ImagePullBackOff
truenas-csi-node        -> ImagePullBackOff
```

Après correction DNS et simple `rollout restart` :

```text
truenas-csi-controller  5/5 Running
truenas-csi-node wk01   3/3 Running
truenas-csi-node wk02   3/3 Running
```

Le smoke NFS a ensuite validé :

1. création et bind dynamique d'un PVC ;
2. dataset TrueNAS sous `cpool/k8s/csi` ;
3. `publishContext` NFS avec serveur `172.17.0.24` ;
4. écriture depuis `taloswk01` ;
5. remount et lecture depuis `taloswk02` ;
6. suppression du namespace et reclaim du PV.

Le fait que le serveur NFS reste `172.17.0.24` est normal : il s'agit ici du
**service de stockage TrueNAS**, pas du resolver DNS des nœuds.

## Cause racine

La cause racine est le contrat DHCP suivant :

```text
pfSense DHCP LAN
  DNS server = 172.17.0.24
```

Talos recevait donc Pi-hole/TrueNAS comme unique resolver upstream.

Cette configuration était incompatible avec le runbook de maintenance : le
reboot contrôlé arrête volontairement les Apps TrueNAS avant le reboot, et
Pi-hole fait partie de ces Apps.

Cela créait le cycle :

```text
reboot/recovery TrueNAS
        |
        v
Apps TrueNAS STOPPED
        |
        v
Pi-hole 172.17.0.24:53 indisponible
        |
        v
Talos Host DNS sans upstream fonctionnel
        |
        v
containerd ne résout plus les registries
        |
        v
CSI / autres pods à tirer -> ImagePullBackOff
        |
        v
recovery Kubernetes incomplet
```

`127.0.0.53` n'était pas la cause : il s'agit du resolver/cache local Talos.
Le défaut était son upstream unique `172.17.0.24`.

## Pourquoi 172.17.0.24 avait été utilisé

### Faits prouvés par le repository

`172.17.0.24` est l'adresse LAN stable de TrueNAS et sert de point d'exposition
à de nombreux services du homelab.

Pour le DNS privé, le repository décrit historiquement le flux suivant :

```text
Traefik Docker labels
        |
        v
pihole-dns-sync
  DOMAIN_SUFFIX=int.albandrieu.com
  TARGET_IP=172.17.0.24
        |
        v
Pi-hole
        |
        v
service.int.albandrieu.com -> 172.17.0.24
        |
        v
Traefik :443 -> container/service cible
```

La configuration actuelle de `apps/pihole/compose.yml` matérialise encore ce
contrat :

```text
TARGET_IP: 172.17.0.24
DOMAIN_SUFFIX: int.albandrieu.com
```

L'objectif de `TARGET_IP` n'est **pas** de publier les IP Docker éphémères des
containers.

Au contraire :

- le LAN reçoit un A record stable vers le host TrueNAS `.24` ;
- Traefik sélectionne ensuite le bon backend selon le hostname HTTP/TLS ;
- à l'intérieur des réseaux Docker, les containers utilisent le DNS embarqué
  Docker et leurs noms de service.

Ainsi, `.24` sert de **stable service ingress address** pour
`*.int.albandrieu.com`, pas de registre d'IP de containers.

### Évolution documentée de l'architecture

L'historique Git montre l'évolution suivante.

#### 6 septembre 2026 — publication privée centrée sur Pi-hole

Le commit `059d658e770fffd269353961ad144124a4c59f9c`
(`fix(ingress): align FastAPI Sample with Cloudflare Tunnel and internal DNS`)
documentait principalement :

```text
pihole-dns-sync
  TARGET_IP=172.17.0.24
  -> Pi-hole LAN DNS
  -> hello.int.albandrieu.com -> 172.17.0.24
  -> Traefik -> service container
```

Cette étape explique pourquoi un client utilisant directement Pi-hole pouvait à
la fois bénéficier du filtrage DNS et résoudre les noms privés des services.

#### 6 septembre 2026 — identification du risque de dépendance

Le commit `45bc9c719582327b089f780a0233946c9816d6d8`
(`fix(security): keep internal DNS private and remove Docker proxy exposure debt`)
ajoutait déjà explicitement :

> Do not make general LAN DNS availability depend on Pi-hole running on TrueNAS.

La documentation indiquait que les clients devaient garder pfSense/Unbound
comme resolver normal.

Cela montre que l'utilisation directe de Pi-hole comme DNS général était déjà
identifiée comme dette/résilience insuffisante avant l'incident du 27 septembre.

#### 7 septembre 2026 — split DNS validé

Le commit `292246d11c24de7278b119d271a584a9f180ba5f`
(`feat(truenas): reconcile runtime health and service catalog`) documentait le
contrat validé :

```text
resolver #1: pfSense/Unbound 172.17.0.1
resolver #2: Quad9
resolver #3: Cloudflare

Unbound
  public names -> recursion
  int.albandrieu.com -> Pi-hole 172.17.0.24:53
```

La documentation précise également qu'un système hébergeant Pi-hole sur TrueNAS
ne doit pas utiliser ce Pi-hole comme resolver système primaire, afin d'éviter
une dépendance circulaire de boot/runtime.

### Ce que le repository ne prouve pas

Le repository ne versionne pas l'historique complet de la configuration runtime
pfSense DHCP.

Il n'est donc pas possible d'attribuer avec certitude le réglage
`DHCP DNS server = 172.17.0.24` à un commit précis.

L'explication la plus cohérente avec l'historique est qu'il s'agissait d'un
**reste de la topologie directe Pi-hole**, utile auparavant pour :

- filtrage réseau Pi-hole ;
- résolution simple de `*.int.albandrieu.com` ;
- accès stable aux services via `172.17.0.24 -> Traefik`.

Au 27 septembre, ce réglage était en revanche une **configuration drift** par
rapport au contrat split-DNS déjà documenté depuis le 6/7 septembre.

## Facteurs contributifs

1. La configuration DHCP pfSense est un état externe au repository et pouvait
   diverger sans quality gate Git.
2. Talos n'avait pas encore de nameserver recovery-safe imposé dans sa machine
   config et acceptait le resolver DHCP.
3. Pi-hole est correctement géré comme une App TrueNAS et est arrêté pendant un
   shutdown contrôlé.
4. Le retour CSI nécessitait de tirer des images publiques, ce qui a rendu la
   dépendance DNS immédiatement visible.
5. Les contrôles post-reboot validaient l'état VM/Talos/Kubernetes avant de
   valider explicitement le resolver host DNS de chaque nœud.

## Résolution appliquée

### pfSense

Dans **Services -> DHCP Server -> LAN** :

```text
avant: DNS server = 172.17.0.24
après: DNS server = 172.17.0.1
```

Le DHCP continue de fournir les réservations historiques :

```text
taloscp01  02:00:00:00:10:01 -> 172.17.0.50
taloswk01  02:00:00:00:20:01 -> 172.17.0.51
taloswk02  02:00:00:00:20:02 -> 172.17.0.52
```

### Talos

Les trois nœuds ont été patchés vers :

```yaml
machine:
  network:
    nameservers:
      - 172.17.0.1
```

Validation obtenue sur `.50/.51/.52` :

```text
ResolverStatus ["172.17.0.1"]
DNSUpstream    healthy=true address=172.17.0.1:53
```

### Kubernetes / CSI

Aucune réinstallation CSI n'a été nécessaire.

Un simple restart contrôlé des workloads a suffi après le retour DNS :

```bash
kubectl -n truenas-csi rollout restart deployment/truenas-csi-controller
kubectl -n truenas-csi rollout restart daemonset/truenas-csi-node
```

Le smoke NFS cross-node a ensuite passé tous ses gates.

## Contrat cible

Le contrat DNS doit désormais rester :

```text
Talos:
  resolver = 172.17.0.1

LAN clients:
  normal resolver = pfSense/Unbound 172.17.0.1

pfSense/Unbound:
  public DNS = indépendant de TrueNAS/Pi-hole
  int.albandrieu.com = Domain Override vers 172.17.0.24:53

Pi-hole:
  autorité/synchronisation de la zone privée
  filtrage DNS optionnel selon le client
  ne doit pas être un prérequis au bootstrap/recovery Talos

Docker:
  container-to-container = embedded Docker DNS
  *.int LAN = stable TrueNAS/Traefik address 172.17.0.24
```

La disponibilité de Pi-hole peut donc affecter la zone privée
`*.int.albandrieu.com`, mais **ne doit jamais empêcher Talos de résoudre un
registry public**.

## Prévention

### Gates obligatoires après reboot

Avant de considérer le cluster restauré :

```bash
for node in 172.17.0.50 172.17.0.51 172.17.0.52; do
  talosctl --endpoints 172.17.0.50 --nodes "$node" get resolvers
  talosctl --endpoints 172.17.0.50 --nodes "$node" get dnsupstream
done
```

Attendu :

```text
ResolverStatus = ["172.17.0.1"]
DNSUpstream    = healthy=true 172.17.0.1:53
```

Puis seulement :

1. Kubernetes Nodes Ready avec les identités/IP attendues ;
2. CSI controller/node plugins Ready ;
3. smoke NFS cross-node ;
4. restauration progressive des Apps TrueNAS.

### Source de vérité Talos

Les futures générations Talos doivent contenir explicitement le nameserver
recovery-safe `172.17.0.1` et ne pas dépendre du DNS reçu par DHCP.

### Audit pfSense à ajouter

Le quality gate pfSense devrait vérifier au minimum :

- DHCP LAN DNS n'annonce pas `172.17.0.24` comme resolver général ;
- Unbound écoute sur `172.17.0.1:53` ;
- le Domain Override `int.albandrieu.com -> 172.17.0.24` existe ;
- une résolution publique via `@172.17.0.1` fonctionne même lorsque Pi-hole
  est arrêté ;
- une résolution privée via `@172.17.0.1` suit correctement le Domain Override
  lorsque Pi-hole est disponible.

## Vérification de résilience recommandée

Un prochain test de maintenance doit explicitement prouver ce scénario :

1. cluster Talos sain ;
2. arrêter Pi-hole volontairement ;
3. vérifier que chaque Talos conserve `172.17.0.1` comme DNS healthy ;
4. vérifier qu'un pull d'image publique ou une résolution
   `registry.k8s.io` fonctionne ;
5. accepter que `*.int.albandrieu.com` soit indisponible si son autorité
   Pi-hole est arrêtée ;
6. redémarrer Pi-hole et vérifier le retour automatique de la zone privée.

Ce test valide la séparation entre **DNS général critique** et
**autorité privée hébergée sur TrueNAS**.

## Follow-up hors cause racine

Les warnings PodSecurity vus pendant le rollout CSI et le smoke sont distincts
de cet incident DNS :

- le node plugin CSI nécessite des privilèges/host paths propres à son rôle ;
- les Pods writer/reader du smoke peuvent être durcis pour satisfaire le profil
  `restricted` lorsque cela ne casse pas le test NFS.

Ils doivent être traités comme dette de hardening séparée et ne doivent pas être
confondus avec la RCA DNS.

## Références repository

- `docs/dns-ingress-ownership.md`
- `apps/pihole/compose.yml`
- `apps/pihole/README.md`
- `docs/truenas-talos-bootstrap.md`
- `scripts/talos/generate-config.sh`
- commit `059d658e770fffd269353961ad144124a4c59f9c`
- commit `45bc9c719582327b089f780a0233946c9816d6d8`
- commit `292246d11c24de7278b119d271a584a9f180ba5f`
