# Incident pfSense / Talos DNS après reboot TrueNAS — 2026-09-27

Status: **mitigé ; garde-fous implémentés, acceptation de maintenance encore à prouver**.

## Résumé

Le reboot contrôlé de TrueNAS a révélé une dépendance circulaire : le DHCP LAN
annonçait `172.17.0.24` (TrueNAS/Pi-hole) comme resolver général alors que les
Apps TrueNAS, dont Pi-hole, sont volontairement arrêtées pendant la maintenance.

Les clients LAN et les trois nœuds Talos pouvaient donc perdre leur résolution
publique au moment même où Kubernetes devait tirer des images pour restaurer ses
workloads. Le controller et les nodes du CSI TrueNAS/NFS ont été bloqués en
`ImagePullBackOff`. Il ne s'agissait pas d'une perte de données CSI.

Contrat corrigé :

```text
LAN / Talos
    |
    v
pfSense / Unbound 172.17.0.1:53
    |
    +--> DNS public indépendant de TrueNAS
    |
    +--> int.albandrieu.com (Domain Override)
              |
              v
        Pi-hole 172.17.0.24:53
              |
              v
       services privés / Traefik
```

## Symptômes et preuves

### LAN

- certains clients Android signalaient « connecté sans Internet » ;
- TrueNAS `172.17.0.24` restait joignable en ICMP mais aucun DNS n'écoutait
  sur `TCP/UDP 53` ;
- Kea distribuait `172.17.0.24` comme `domain-name-servers` ;
- pfSense/Unbound `172.17.0.1` résolvait correctement les noms publics.

```text
dig @172.17.0.24 google.com
;; no servers could be reached

nc -vz -w2 172.17.0.24 53
connection refused
```

### Talos / Kubernetes

Les trois nœuds utilisaient un resolver local `127.0.0.53`, mais son upstream
était `172.17.0.24:53`. Les logs `dns-resolve-cache` montraient
`connection refused` / `i/o timeout` pour notamment :

```text
registry.k8s.io
ghcr.io
discovery.talos.dev
```

Conséquence observée :

```text
truenas-csi-controller -> ImagePullBackOff
truenas-csi-node       -> ImagePullBackOff
```

Les volumes existants n'ont pas été perdus et aucun VolumeAttachment stale n'a
été identifié.

## Cause racine

Le contrat DHCP était :

```text
pfSense DHCP LAN
  DNS server = 172.17.0.24
```

Pi-hole/TrueNAS devenait ainsi le resolver upstream critique du LAN et de Talos,
alors que le runbook de reboot arrête volontairement cette App.

`127.0.0.53` n'était pas la cause : le défaut était son upstream unique dans
le domaine de panne en maintenance.

`172.17.0.24` reste légitime pour le stockage NFS, l'ingress privé stable et
l'autorité DNS privée Pi-hole ; elle ne doit plus être le resolver DNS général
indispensable au bootstrap.

## Correction appliquée

### pfSense

Le DHCP LAN a été corrigé :

```text
avant : DNS server = 172.17.0.24
après : DNS server = 172.17.0.1
```

`scripts/pfsense/audit-posture.sh` vérifie désormais :

- la résolution publique via `@172.17.0.1` ;
- FAIL si DHCP annonce `172.17.0.24` comme resolver général ;
- PASS si `172.17.0.1` est explicitement présent ou si le mode automatique
  pfSense/Unbound s'applique.

### Talos

`scripts/talos/generate-config.sh` impose par défaut :

```yaml
machine:
  network:
    nameservers:
      - 172.17.0.1
```

Un autre resolver recovery-safe peut être choisi avec
`TALOS_NAMESERVER=<ip>`.

Validation attendue sur `.50/.51/.52` :

```text
ResolverStatus ["172.17.0.1"]
DNSUpstream    healthy=true address=172.17.0.1:53
```

### Kubernetes / CSI

Après retour du DNS, aucune réinstallation CSI n'a été nécessaire. Un restart
contrôlé a suffi :

```bash
kubectl -n truenas-csi rollout restart deployment/truenas-csi-controller
kubectl -n truenas-csi rollout restart daemonset/truenas-csi-node
```

Le smoke NFS cross-node a ensuite validé provisioning, `publishContext`,
écriture sur `taloswk01`, lecture sur `taloswk02` et reclaim du PV.

## Contrat d'architecture

1. Le DHCP LAN distribue pfSense/Unbound `172.17.0.1` comme resolver général.
2. Le DNS public reste disponible sans TrueNAS/Pi-hole.
3. `int.albandrieu.com` peut être délégué conditionnellement vers Pi-hole.
4. Une panne Pi-hole peut rendre la zone privée indisponible mais ne doit pas
   empêcher un pull depuis un registry public.
5. Talos ne dépend pas uniquement du DNS reçu par DHCP.
6. Les probes distinguent resolver général, zone privée et resolver TrueNAS
   optionnel.

## Acceptance de fermeture

À la prochaine maintenance contrôlée :

```bash
for node in 172.17.0.50 172.17.0.51 172.17.0.52; do
  talosctl --endpoints 172.17.0.50 --nodes "$node" get resolvers
  talosctl --endpoints 172.17.0.50 --nodes "$node" get dnsupstream
done
```

Puis :

1. arrêter Pi-hole volontairement ;
2. vérifier `DNSUpstream 172.17.0.1:53 healthy=true` sur chaque nœud ;
3. prouver une résolution ou un pull depuis un registry public ;
4. accepter l'indisponibilité éventuelle de `*.int.albandrieu.com` ;
5. redémarrer Pi-hole et prouver le retour de la zone privée ;
6. rerun du smoke CSI NFS.

L'incident ne doit être marqué clos qu'après ce test.

## pfSense 26.07 : packages tiers après upgrade

Le même cycle de maintenance a montré qu'un package pouvait rester installé mais
ne plus être opérationnel.

### CrowdSec

```sh
pkg info | grep -i crowdsec
pgrep -laf 'crowdsec|crowdsec-firewall-bouncer'
```

Réinstaller via le mécanisme supporté du package pfSense si nécessaire, puis
revalider le daemon et le bouncer.

### REST API

```sh
pkg info | grep -i restapi
```

Puis valider :

```text
https://home.albandrieu.com:10443/api/v2/system/version
```

### Zabbix Agent 7

Après upgrade, le package pouvait rester présent alors que daemon, listener et
configuration runtime avaient disparu. Préférer la réinstallation du package
pfSense depuis l'UI afin de régénérer la configuration et le wrapper.

```sh
service zabbix_agentd status
pgrep -laf zabbix
sockstat -4 -6 -l | grep 10050
grep -E '^(Server|ServerActive|Hostname|ListenIP|ListenPort)='   /usr/local/etc/zabbix7/zabbix_agentd.conf
tail -50 /var/log/zabbix-agent/zabbix_agentd.log
```

État final observé le 2026-09-27 :

```text
Unbound / DNS        OK
Kea DHCP             OK
DNS DHCP LAN         172.17.0.1
WANGW / dpinger      Online
CrowdSec             running
pfSense REST API     reachable
Zabbix agent         running / TCP 10050
```

Le serveur Zabbix Docker sur TrueNAS étant arrêté à ce moment, les erreurs
d'active checks vers `172.17.0.24:10051` étaient attendues.

## Hors cause racine

À traiter séparément :

- PodSecurity warnings du CSI/smoke ;
- IPv6/RA isolés pendant le diagnostic ;
- exposition publique du WebConfigurator pfSense ;
- serveur Zabbix TrueNAS et reprise des active checks.

Ne pas utiliser ces dettes pour expliquer ou masquer la RCA DNS.
