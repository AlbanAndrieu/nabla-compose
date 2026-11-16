# taloscp01 sur l'adresse publique du WAN — 14 au 15 novembre 2026

**Statut** : cause du bail non identifiée ; correctif `CODED`, non appliqué (VMs arrêtées le 16/11).

## Constat (16/11, `kubectl` en lecture seule)

- Un second nœud `talos-ib5-q5a` (control-plane, `NotReady,SchedulingDisabled`) existait depuis 39 h, avec l'`InternalIP` `82.66.4.247` : l'adresse publique Free de pfSense.
- C'est taloscp01 lui-même : même `machineID` et même `systemUUID`. `talos-ib5-q5a` est le nom stable généré par Talos, celui du bootstrap du 6/09 (`docs/truenas-talos-bootstrap.md`). Le nom `taloscp01` venait du DHCP de pfSense, et rien dans la configuration Talos versionnée ne fixait ni l'adresse ni le nom.
- Fenêtre : du 14/11 vers 17:17 UTC (création du nœud) au 15/11 vers 17:33 UTC (retour sous `taloscp01` en `172.17.0.50`). Pendant ce temps, cilium a redémarré 239 fois en `Init:CrashLoopBackOff` sur ce nœud.

## Analyse

- Le seul serveur DHCP qui distribue `82.66.4.247` est la Freebox en bridge. La requête DHCP de la VM, sur `br0` (LAN), a donc atteint le segment WAN. Le chemin de niveau 2 n'est pas identifié : il relève de pfSense et du câblage.
- Exposition possible : pendant la fenêtre, l'API Kubernetes (6443), l'API Talos (50000), etcd et le kubelet ont pu être joignables depuis Internet. Tous exigent un certificat client (mTLS). Aucune sonde externe n'a tourné pendant la fenêtre : exposition **non vérifiée**, ni prouvée ni exclue.
- Hypothèse non prouvée : la Freebox ne délivre qu'une IPv4 publique. Un bail pris par la VM a pu priver pfSense de son WAN. L'incident WAN du 15/11 a une cause établie différente (pfBlockerNG, [diagnostic pfSense](../pfsense-diagnose-recover.md)).

## Actions du 16/11

- CSI réparé : le rôle du controller peut lire les Pods (csi-resizer v2). Smoke RWX réussi, écriture sur taloswk01 et lecture sur taloswk02.
- Snapshot etcd sur le poste, puis arrêt des trois VMs Talos par le script versionné (`just talos-vms-stop`, autostart désactivé).
- `config/talos/nodes/*.yaml` : adresse statique, passerelle `172.17.0.1`, `dhcp: false` et `HostnameConfig` fixe pour chaque nœud. Ce sont les valeurs des réservations pfSense. Validé hors ligne (`talosctl validate --mode metal --strict` sur une configuration générée en v1.13.9). Le contrat est dans `tests/test_talos_node_network_contract.py`.

## Reste à faire (opérateur)

1. Au prochain démarrage de Talos (`just talos-stopped-vms-start`) : `just talos-node-network-check` (diff à blanc), puis `just talos-node-network-apply`.
2. `kubectl delete node talos-ib5-q5a`.
3. Identifier le chemin de niveau 2 entre `br0` et la Freebox, côté pfSense ou commutateur.
