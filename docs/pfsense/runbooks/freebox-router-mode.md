# Freebox : passer du mode bridge au mode routeur, et revenir

**État au 17/11/2026 :** `CODED`, `NOT_RUN`. La Freebox Ultra (API 16.1) est en bridge, et le WAN de pfSense porte l'IP publique en statique (`WANGW`). Aucune bascule n'a été faite.

Outils, tous en lecture par défaut :

- [`freebox-edge.py`](../../../scripts/pfsense/freebox-edge.py) : API Freebox OS, en HTTPS épinglé sur les racines Freebox publiées ([`freebox-root-ca.pem`](../../../scripts/pfsense/freebox-root-ca.pem)) :
  - `check` lit le mode, le DHCP, les baux statiques, la DMZ et l'IPv6 ;
  - `set-mode`, `set-lan-ip` et `pin-wan` n'écrivent qu'avec `--yes` et la permission `settings`.
- [`wan-addressing.php`](../../../scripts/pfsense/wan-addressing.php) : WAN pfSense, avec les modes `check`, `dhcp`, `static <ip>/<préfixe>` et `renew`. `dhcp` désactive `WANGW` sans le supprimer, ce qui garde le retour possible, et repointe sur `WAN_DHCP` les règles épinglées sur `WANGW`.

## Ce que ça change

| | Bridge (aujourd'hui) | Routeur (cible) |
|---|---|---|
| IP publique | sur le WAN de pfSense | sur la Freebox, pfSense en DMZ derrière elle (double NAT) |
| Démarrage à froid du 1100 | un appareil du LAN peut prendre l'IP publique ([incident](../incidents/2026-11-14-netgate-1100-cold-boot-switch-bridge.md)) | il reçoit au pire une IP privée de la Freebox |
| Wi-Fi Freebox (`AndroidRadin`) | dans le pont : un client peut recevoir l'IP publique | isolé derrière le NAT de la Freebox |
| Entrées (HAProxy, NAT) | directes | par la DMZ, IP source conservée ; HAProxy écoute sur `wan_ipv4`, qui suit la nouvelle adresse |
| DynDNS Cloudflare | lit l'IP du WAN | doit lire l'IP publique via un service « check IP » |
| IPv6 | `dhcp6` sur le WAN, `track6` sur le LAN | délégation Freebox avec next hop, à valider (voir la fin) |

Le 4200 MAX supprime aussi le pont du démarrage à froid : le mode routeur reste un choix, pas un prérequis.

## Prérequis (une fois)

1. Enregistrer l'app « Nabla edge » depuis le LAN :

   ```bash
   python3 scripts/pfsense/freebox-edge.py --token-file "$XDG_RUNTIME_DIR/freebox-token" register
   ```

   - accepter la demande sur l'écran du Freebox Server ;
   - ranger le token dans Vaultwarden (élément `FREEBOX_APP_TOKEN`), puis `shred -u "$XDG_RUNTIME_DIR/freebox-token"`.
2. Dans Freebox OS (Paramètres de la Freebox > Gestion des accès > Applications > « Nabla edge ») :
   - décocher les droits que la Freebox donne par défaut et dont l'outil n'a pas besoin : Explorateur, VM, Appels, Contacts, Téléchargements, TV, PVR ;
   - cocher « Modification des réglages » seulement juste avant la bascule, et le retirer après. L'API ne peut pas se l'accorder elle-même.

   Fait le 17/11 : app enregistrée, token dans Vaultwarden (`FREEBOX_APP_TOKEN`). Les droits n'ont pas encore été réduits.
3. Relever l'état, sans rien changer :

   ```bash
   export FREEBOX_APP_TOKEN="$(bw get password FREEBOX_APP_TOKEN)"
   python3 scripts/pfsense/freebox-edge.py check --expect-mode bridge
   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/wan-addressing.php
   ```

4. Si `check` signale un alias qui contient l'IP publique en dur, vérifier qu'il est inutilisé (champ `used_by` de [`inventory.php`](../../../scripts/pfsense/inventory.php)). Derrière la Freebox, le trafic entrant arrive sur l'IP privée du WAN. Le seul alias signalé le 17/11 est inutilisé : aucun impact.
   Relevé du 17/11 en bridge : firmware 4.13.6, Wi-Fi actif, IPv6 avec 8 délégations dont 2 avec next hop. Le DHCP, les baux, les redirections, la DMZ et le VPN répondent « disponible qu'en mode routeur » : rien ne se prépare côté Freebox avant l'étape 2.
5. Choisir l'adresse privée fixe du WAN pfSense, hors de la plage DHCP que `check` affiche une fois la Freebox en routeur, par exemple `192.168.1.2`. Relever l'adresse MAC du WAN depuis pfSense, sans la commiter (dépôt public) :

   ```bash
   ssh -p 9922 admin@172.17.0.1 "ifconfig mvneta0.4090" | awk '/ether/{print $2}'
   ```

6. Prévoir quelques minutes de coupure Internet. Le LAN et le SSH de pfSense restent joignables pendant toute la bascule.

## Préparation faite le 17/11 (lecture seule)

- **Inventaire** : [`inventory.php`](../../../scripts/pfsense/inventory.php), deux exécutions identiques, sortie dans `logs/` (hors dépôt).
- **Redirections WAN** : les 13 sont obsolètes. Aucune n'a de règle de passage active et aucun état n'est établi ; elles ne jouent aucun rôle dans la bascule. Restent servis sur le WAN : HAProxy `Web_HTTPS` (443) et `freenas` (7000), que la DMZ continuera d'amener à pfSense.
- **DynDNS Cloudflare** : en mode « check IP » par défaut, avec le service d'usine actif. Il lira l'IP publique derrière la Freebox sans changement.
- **IPv6** : la Freebox route 2 préfixes `/64` vers le WAN link-local de pfSense, mais le LAN, en `track6`, n'a reçu aucun préfixe. L'IPv6 n'est donc pas en service sur le LAN, et la bascule n'y change rien. Le passage du LAN en IPv6 statique sur l'une de ces délégations est suivi dans la roadmap.
- **TrueNAS et Talos** : pfSense garde le DHCP (baux fixes, dont Talos `.50`–`.52`) et Unbound (`172.17.0.1`, `int.*` délégué à Pi-hole). Ils ne voient pas la bascule.
- **App Freebox** : enregistrée, token dans Vaultwarden.
- **Reste à faire le jour J** : cocher « Modification des réglages », relever la MAC du WAN, et choisir l'adresse du WAN une fois la plage DHCP du mode routeur lisible.
- **Secours Wi-Fi de TrueNAS sur le Wi-Fi Freebox** : en routeur, il reçoit une adresse privée de la Freebox, et l'accès sortant à Internet suffit pour travailler. Les noms publiés par Cloudflare Tunnel restent joignables, car `cloudflared` se connecte vers l'extérieur. Les entrées directes sur l'IP publique (443, 7000) ne le sont plus si pfSense est arrêté. Le filtrage de l'interface Wi-Fi reste à faire avant de l'activer.

## Bascule bridge → routeur

L'ordre compte : en bridge, la Freebox distribue aussi l'IP publique en DHCP. Le WAN passe donc en DHCP d'abord, sans coupure, et la Freebox bascule ensuite.

1. **WAN pfSense en DHCP** (Freebox encore en bridge) :

   ```bash
   ssh -p 9922 admin@172.17.0.1 "php -- dhcp" < scripts/pfsense/wan-addressing.php
   ```

   La sortie doit finir par `address 82.66.4.247`. Sans adresse après un `renew`, un autre client tient peut-être le bail public : revenir avec `static 82.66.4.247/24` et inverser les étapes 1 et 2, au prix d'une coupure plus longue.
2. **Freebox en routeur** : `freebox-edge.py set-mode router` affiche le plan, puis la même commande avec `--yes` l'applique. L'API devient injoignable tant que pfSense n'a pas renouvelé son WAN, c'est attendu. La doc du SDK ne dit pas si la Freebox redémarre à ce moment.
3. **Renouveler le WAN** : `ssh -p 9922 admin@172.17.0.1 "php -- renew" < scripts/pfsense/wan-addressing.php`. Le WAN reçoit une adresse `192.168.1.x`.
4. **Épingler le WAN et ouvrir la DMZ** : `freebox-edge.py pin-wan --wan-mac <MAC> --wan-ip 192.168.1.2 --dmz`, puis la même commande avec `--yes`. Relancer ensuite `renew` pour prendre l'adresse épinglée.
5. **Resynchroniser le BE de repli**, sinon un repli au boot ramènerait l'ancienne configuration WAN :

   ```bash
   ssh -p 9922 admin@172.17.0.1 /bin/sh -s -- check auto < scripts/pfsense/sync-fallback-be-config.sh
   ```

   Puis la même commande avec `apply`.
6. **Contrôles** :
   - `freebox-edge.py check --expect-mode router --wan-mac <MAC> --wan-ip 192.168.1.2` et `wan-addressing.php check` : 0 changement ;
   - `check-drift.sh` convergé ;
   - Internet depuis le LAN ;
   - entrées vues de l'extérieur : sonde FastAPI Cloud `/sickz` et HAProxy ;
   - enregistrement DynDNS toujours sur l'IP publique ;
   - Gatus et Prometheus au vert.

## Sans pfSense : adresse LAN de la Freebox (18/11/2026)

Le 1100 a été retiré le 18/11 et la Freebox réinitialisée en routeur (`192.168.1.254`, DHCP `.2-.200`). L'idée était qu'elle reprenne `172.17.0.1/24`, l'adresse de pfSense, pour que TrueNAS (`172.17.0.24`) et les autres IP fixes retrouvent leur passerelle sans changement. **Freebox OS le refuse** : `PUT /lan/config/` répond `invalid_gateway_ip`, « L'IP doit être de type 192.168.x.x » (API 16.1). `set-lan-ip` refuse donc toute adresse hors de `192.168.0.0/16` avant la première écriture.

`set-lan-ip <adresse>` reste utile pour changer d'adresse dans `192.168.0.0/16` :

1. Sans `--yes`, la commande affiche le plan : d'abord réduire le pool DHCP à `.100-.199` dans le sous-réseau actuel, puis changer l'adresse de la Freebox. Le pool réduit d'abord évite que la Freebox distribue une adresse fixe si elle reporte les numéros d'hôte dans le nouveau sous-réseau. `--dhcp-first` et `--dhcp-last` changent le pool.
2. Avec `--yes` et la permission `settings`, elle applique et annonce chaque écriture réussie (`OK: ...`). Si l'API ne répond plus après le changement d'adresse, le script l'annonce en `WARN`, comme attendu.
3. Ensuite, renouveler les baux du LAN, puis relancer `check` et la même commande : la seconde passe corrige le pool si la Freebox ne l'a pas reporté.

Fait le 18/11 : app « Nabla edge » réenregistrée après la réinitialisation usine (jeton dans un fichier 0600 hors du dépôt, à ranger dans Vaultwarden `FREEBOX_APP_TOKEN`) ; pool DHCP réduit à `192.168.1.100-192.168.1.199` (appliqué) ; changement d'adresse vers `172.17.0.1` refusé par la Freebox, rien d'autre n'a changé. TrueNAS reste en `172.17.0.24` sans passerelle joignable : voir la roadmap pfSense pour la suite.

## Le Netgear R7000 devient le routeur `172.17.0.1` (18/11/2026)

La Freebox ne pouvant pas prendre `172.17.0.1`, le Netgear Nighthawk R7000 (point d'accès Wi-Fi en `172.17.0.12` jusque-là, firmware V1.0.12.216) a repris ce rôle, derrière la Freebox. TrueNAS, Pi-hole et les autres IP fixes du homelab retrouvent leur passerelle sans changement.

| Élément | Réglage |
| --- | --- |
| Câblage | Port Internet du R7000 → port 2,5 Gbit/s de la Freebox ; switch du homelab sur un port LAN du R7000 |
| Mini switch IoT et domotique | Port 1 Gbit/s de la Freebox, donc en `192.168.1.x` devant le R7000 : isolé du homelab, sans découverte mDNS ni SSDP vers Home Assistant |
| Mode | Point d'accès désactivé : en mode routeur, le R7000 prend d'abord `10.0.0.1`, car la Freebox occupe déjà `192.168.1.0/24` |
| LAN | `172.17.0.1/24`, DHCP de `172.17.0.100` à `172.17.0.199`. La réservation de la workstation (`.57`) a suivi le changement d'adresse |
| Côté Internet | Adresse en `192.168.1.x` donnée par le DHCP de la Freebox. Double NAT, sans DMZ : rien n'est ouvert depuis Internet vers le homelab |
| Sauvegarde | `NETGEAR_R7000.cfg`, dans les Documents de l'opérateur, hors dépôt : elle contient les mots de passe |

**Administration** : la racine `https://172.17.0.1/` (ou `10.0.0.1` avant le changement de LAN) ne fonctionne pas. Elle redirige vers `www.routerlogin.com`, qu'un poste résolvant avec Pi-hole ou Quad9 n'envoie pas vers le routeur. Ouvrir directement **`https://172.17.0.1/start.htm`**. LAN Setup se trouve dans l'onglet ADVANCED, menu Setup.

Vérifié le 18/11 depuis la workstation : bail `172.17.0.57` avec la passerelle `172.17.0.1`, Internet joignable ; Pi-hole sur TrueNAS résout de nouveau `example.org`, donc TrueNAS sort par le R7000.

Reste à vérifier (`NOT_VERIFIED`) :

- DNS que le R7000 distribue par DHCP et qu'il utilise lui-même (cible : Pi-hole `172.17.0.24`, puis Quad9 en secours) ;
- Remote Management, UPnP et WPS désactivés ;
- statut de support du R7000, modèle ancien : il reste derrière le NAT de la Freebox ;
- adresse Internet du R7000 fixée sur la Freebox (`freebox-edge.py pin-wan --wan-mac <MAC> --wan-ip <ip>`, sans `--dmz`) ;
- IPv6 absent du LAN.

## Retour routeur → bridge

1. `freebox-edge.py set-mode bridge --yes`. Le bail et la DMZ restent enregistrés sur la Freebox, sans effet en bridge.
2. `wan-addressing.php renew` reprend l'IP publique en DHCP. Pour retrouver exactement l'état d'aujourd'hui, utiliser `wan-addressing.php static 82.66.4.247/24` à la place.
3. Resynchroniser le BE de repli, puis refaire les contrôles de l'étape 6.

Si l'API Freebox ne répond plus et que le WAN est perdu : `wan-addressing.php static 82.66.4.247/24` depuis le LAN rétablit le côté pfSense. Sinon, ouvrir Freebox OS depuis un appareil sur le Wi-Fi de la Freebox, quand elle est en routeur. L'historique de configuration de pfSense garde aussi la révision précédente.

## Reste à valider (`NOT_RUN`)

- **IPv6** : en routeur, la Freebox délègue jusqu'à 8 préfixes, chacun routé vers un next hop link-local (`connection/ipv6/config`). Il faut vérifier si le WAN `dhcp6` de pfSense reçoit encore une délégation. Sinon, renseigner le next hop sur l'adresse link-local du WAN et passer le LAN en IPv6 statique. `check` affiche les délégations, mais rien n'est scripté en écriture.
- **Durée de la coupure** et redémarrage éventuel de la Freebox au changement de mode.
- **DHCP en bridge** : la Freebox doit bien donner l'IP publique à pfSense (étape 1).
- **Secours Wi-Fi TrueNAS** : une fois la Freebox en routeur, le Wi-Fi de la Freebox ne donne plus l'IP publique, ce qui levait le refus. Mais TrueNAS aurait alors une route vers Internet qui contourne pfSense : il faudra un filtrage sur l'interface Wi-Fi avant de l'activer.
