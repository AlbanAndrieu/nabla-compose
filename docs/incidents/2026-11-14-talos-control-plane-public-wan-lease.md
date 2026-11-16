# taloscp01 sur l'adresse publique du WAN — 14 au 15 novembre 2026

**Statut** : cause probable identifiée (commutateur du Netgate 1100 au démarrage à froid, non prouvée par une capture). Correctif Talos `CODED`, non appliqué : les VMs sont arrêtées depuis le 16/11.

## Constat (16/11, `kubectl` en lecture seule)

- Un second nœud `talos-ib5-q5a` (control-plane, `NotReady,SchedulingDisabled`) existait depuis 39 h, avec l'`InternalIP` `82.66.4.247`, l'adresse publique Free de pfSense.
- C'est taloscp01 lui-même : même `machineID`, même `systemUUID`. `talos-ib5-q5a` est le nom stable que Talos avait généré au bootstrap du 6/09 (`docs/truenas-talos-bootstrap.md`). Le nom `taloscp01` venait du DHCP de pfSense, et rien dans la configuration Talos versionnée ne fixait l'adresse ni le nom.
- Fenêtre : du 14/11 vers 17:17 UTC (création du nœud) au 15/11 vers 17:33 UTC (retour sous `taloscp01` en `172.17.0.50`). Sur ce nœud, cilium a redémarré 239 fois en `Init:CrashLoopBackOff`.

## Analyse (lecture seule ; volet pfSense fourni par la session pfSense)

1. **Précondition : la VM ne recevait plus de bail du LAN.** La configuration de repli de pfSense (sauvegardes du 13/11 23:59 au 15/11 18:19) n'avait plus que 37 réservations DHCP sur 46, sans celle de taloscp01. Kea était presque inactif : aucun bail LAN distribué le 14/11 entre 06h et 12h. La MAC `02:00:00:00:10:01` est absente de `dhcpd.log` du 13/11 13:39 au 15/11 22:11 CET. La VM diffusait donc des DISCOVER.
2. **Déclencheur : un démarrage à froid du pfSense pile dans la fenêtre.** Les journaux pfSense (Loki) s'arrêtent vers 17:17 UTC sans ligne d'arrêt. Le noyau redémarre à 17:19:53 et le démarrage se termine à 17:25:03.
3. **Mécanisme connu du Netgate 1100.** Son commutateur Marvell 88E6141 relie tous les ports tant que le système n'a pas appliqué les groupes VLAN. La mitigation de Netgate (variables U-Boot `preboot`/`switch_disable`) n'existe que dans les firmwares récents ; le nôtre est en U-Boot `2018.03-devel-18.12.3`. Un DISCOVER du LAN peut alors atteindre la Freebox en bridge, qui répond avec l'IPv4 publique ([forum Netgate](https://forum.netgate.com/post/1079490)). Un redémarrage à chaud conserve la configuration du commutateur.
4. **La configuration pfSense n'est pas en cause.** Les groupes VLAN sont identiques dans les quatre sauvegardes `config.xml`, il n'y a aucun pont, et `etherswitchcfg` est conforme. Côté TrueNAS, `br0` n'a qu'un membre (`enp10s0`), et la MAC de la Freebox est absente de sa table FDB.

**Exposition** : une fois le commutateur configuré (vers 17:20 UTC), plus aucun chemin de niveau 2 ne relie le WAN à la VM, et `82.66.4.247` reste porté par le WAN de pfSense. L'exposition de l'API Kubernetes (6443) et de l'API Talos (50000) se limite donc aux secondes ou minutes du démarrage, et non aux 24 h. C'est un raisonnement, sans sonde externe. Ces API exigent de toute façon un certificat client (mTLS).

**WAN de pfSense** : il est en adresse statique, pas en DHCP, et sa passerelle était déjà injoignable à 17:14 UTC, avant le redémarrage. Le bail de la VM ne l'a donc pas privé de son WAN. Seul risque plausible, non vérifié : un ARP de la VM a pu fausser brièvement le cache de la Freebox.

**Fin à 17:33 UTC le 15/11** : expiration d'un bail Freebox d'environ 24 h, ou retour des 9 réservations (15/11, 18:14-18:33 CET). Non tranché.

**Récurrence** : chaque démarrage à froid du 1100 (comme la remise sous tension du 16/11 à 00:05 CET) rouvre la fenêtre pour tout client du LAN qui envoie un DISCOVER à ce moment.

## Actions du 16/11

- **CSI réparé** : le rôle du controller peut lire les Pods (csi-resizer v2). Smoke RWX réussi : écriture sur taloswk01, lecture sur taloswk02.
- **Talos arrêté** : snapshot etcd sur le poste, puis arrêt des trois VMs par le script versionné (`just talos-vms-stop`, autostart désactivé).
- **Adressage statique écrit** : `config/talos/nodes/*.yaml` fixe pour chaque nœud l'adresse, la passerelle `172.17.0.1`, `dhcp: false` et un `HostnameConfig`. Ce sont les valeurs des réservations pfSense. Validé hors ligne avec `talosctl validate --mode metal --strict` sur une configuration générée en v1.13.9 ; contrat dans `tests/test_talos_node_network_contract.py`.

## Reste à faire

1. Au prochain démarrage de Talos : `just talos-node-network-check` (diff à blanc), puis `just talos-node-network-apply`, puis `kubectl delete node talos-ib5-q5a`.
2. Netgate 1100 (opérateur, session pfSense) : mettre à jour le firmware U-Boot, après avoir vérifié `printenv preboot switch_disable` à la console série. D'ici là, préférer `reboot` à une coupure de courant.
3. pfSense : garder Kea et les 46 réservations dans les boot environments de repli.
