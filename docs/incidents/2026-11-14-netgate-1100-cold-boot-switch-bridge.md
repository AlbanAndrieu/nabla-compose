# Netgate 1100 : LAN et WAN reliés pendant un démarrage à froid

**Statut** : ouvert, en attente d'un correctif officiel. Contournement en place : redémarrer avec `reboot`, jamais par coupure de courant. Correctif U-Boot `NOT_RUN` (reporté par l'opérateur le 16/11).

## Résumé

Le 14/11 vers 17:17 UTC, le pfSense a démarré à froid : ses journaux s'arrêtent sans ligne d'arrêt. Pendant ce démarrage, le commutateur interne du Netgate 1100 (Marvell 88E6141) a transmis les trames entre ses ports LAN et WAN, car le système n'avait pas encore appliqué les groupes VLAN. La VM Talos `taloscp01` (`br0` de TrueNAS) diffusait alors des requêtes DHCP. Le DHCP du LAN ne lui répondait plus, car sa réservation manquait dans la config de repli et Kea était quasi inactif. La Freebox en bridge lui a donné l'adresse publique `82.66.4.247`. Conséquences et suites côté Talos : [incident du 14/11](2026-11-14-talos-control-plane-public-wan-lease.md).

## Preuves (16/11, lecture seule)

- Loki `{job="pfsense"}` : plus aucun journal entre 17:17Z et 17:20Z, pas de `reboot`/`shutdown`. Le noyau redémarre à 17:19:53Z, `Bootup complete` arrive à 17:25:03Z. Le nœud `talos-ib5-q5a` est créé vers 17:17Z.
- La config pfSense n'est pas en cause. Les groupes VLAN du commutateur sont identiques dans les 4 sauvegardes `config.xml` du 13 au 15/11 et dans `etherswitchcfg` : 4090 = `0t,3` (WAN), 4091 = `0t,2` (LAN), 4092 = `0t,1` (OPT). Aucun `<bridges>`.
- TrueNAS : `br0` n'a qu'un membre, `enp10s0`, et la MAC de la Freebox est absente de sa table FDB.
- Firmware : U-Boot `2018.03-devel-18.12.3` (`kenv smbios.bios.version`). Son environnement enregistré (`u-boot-env-read`, 56 variables) ne contient ni `preboot` ni `switch_disable`.

## Cause

Netgate isole les ports au démarrage par deux variables U-Boot, absentes des premiers 1100 :

```text
preboot=run switch_disable;
switch_disable=switch phy_write 1 0 0 0xffff; switch phy_write 2 0 0 0xffff; echo "Switch Ports Disabled";
```

Le paquet `pfSense-u-boot-1100` fournit `/usr/local/share/u-boot/1100/u-boot-update.sh`, qui doit les ajouter via `u-boot-env-update`. Mais le script s'arrête quand l'empreinte du U-Boot installé figure dans `u-boot-hash`, sa liste des versions les plus récentes. C'est le cas ici : les variables n'ont donc jamais été écrites. Selon le personnel Netgate, un redémarrage à chaud garde la configuration du commutateur ; seul un démarrage à froid ouvre la fenêtre.

Sources : forum Netgate, [1079490](https://forum.netgate.com/post/1079490) (un appareil du LAN prend une adresse amont pendant la fenêtre), [1078335](https://forum.netgate.com/post/1078335) et [1207710](https://forum.netgate.com/post/1207710) (réponses du personnel Netgate, variables et commande).

## Impact

- Tout client du LAN ou de l'OPT qui envoie un DHCPDISCOVER pendant les quelques secondes à minutes de la fenêtre peut recevoir l'adresse publique de la Freebox. Les diffusions du LAN atteignent aussi la Freebox.
- Exposition Internet limitée à la fenêtre : ensuite, plus aucun chemin de niveau 2 ne relie le WAN au LAN, et `82.66.4.247` reste porté par le WAN de pfSense (adresse statique).
- Démarrages à froid connus depuis : remise sous tension du 16/11 à 00:05 (sans effet observé).

## Contournement

- Redémarrer le pfSense avec `reboot` (GUI ou SSH), jamais par coupure de courant.
- Pas de DHCP pour l'infrastructure : adressage statique des nœuds Talos (`config/talos/nodes/*.yaml`, à appliquer au prochain démarrage des VMs).
- Après un repli d'environnement de boot, vérifier les réservations DHCP et Kea (`restore-dhcp-staticmaps.php check`).

## Correctif en attente

Lecture seule, sans console ni redémarrage :

```bash
ssh -p 9922 admin@172.17.0.1 't=$(mktemp); /usr/local/sbin/u-boot-env-read "$t" >/dev/null; tr "\0" "\n" <"$t" | grep -cE "^(preboot|switch_disable)="; rm -f "$t"'
```

`0` = non corrigé, `2` = variables présentes. Deux options, toutes deux avec la console série branchée :

1. **Recommandée par Netgate** : `u-boot-update.sh -f`, qui réécrit la mémoire SPI (U-Boot et variables). Une coupure pendant l'écriture rend le boîtier non démarrable sans récupération à la console.
2. **Plus légère** : ne réécrire que l'environnement (`u-boot-env-read`, `u-boot-env-update`, `u-boot-env-write`), par un script versionné `check`/`apply` à écrire. Ce chemin n'est pas documenté par Netgate.

Vérification : au démarrage à froid suivant, la console affiche `Switch Ports Disabled`.
