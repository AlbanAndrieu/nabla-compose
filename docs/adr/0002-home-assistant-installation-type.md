# ADR-0002 — Home Assistant : rester en HA Container (Compose) plutôt que Home Assistant OS

- **Statut :** proposed (décision du propriétaire attendue ; aucun changement runtime)
- **Date :** 2026-11-10
- **Propriétaire de la décision :** propriétaire du homelab
- **Liens :** [roadmap — études EnOcean et Somfy](../roadmap.md), `scripts/truenas/migrate-homeassistant-to-compose.sh`, `scripts/truenas/diagnose-homeassistant*.sh`

## Contexte

Home Assistant tourne aujourd'hui dans l'App native TrueNAS `home-assistant`.
Cette App **est déjà une installation « HA Container »** : l'image officielle
`ghcr.io/home-assistant/home-assistant` dans Docker, sans Supervisor ni
add-ons. La bascule vers la Custom App versionnée `apps/homeassistant` est
prête (même image, mêmes données `/mnt/cpool/ha`, même port 30103).

Besoins identifiés au 10/11 :

- un dongle USB branché sur TrueNAS (type à confirmer par
  `diagnose-homeassistant-usb.sh`, EnOcean probable pour l'installation Flexom) ;
- les volets io : passerelle joignable en TCP (Overkiz local 8443 ou KLF 200 51200) ;
- l'alarme Somfy Protect : cloud uniquement, via SomfyProtect2MQTT et un broker MQTT ;
- des intégrations communautaires (HACS aujourd'hui ; Marketplace intégré à partir de 2026.11).

Contraintes : réseau bridge sans multicast (décision du 6/11), domotique sur
OPT, configuration versionnée dans ce dépôt, rétention ZFS `cpool/ha`, accès
distant par Cloudflare Tunnel.

Depuis la version 2025.12, seules **Home Assistant OS** et **Home Assistant
Container** restent supportées ; Core et Supervised sont abandonnées
([annonce du 22/05/2025](https://www.home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/)).

## Options

| Critère | A. HA Container (Compose, actuel) | B. HAOS en VM TrueNAS, carte réseau sur OPT | C. HAOS sur matériel dédié sur OPT |
| --- | --- | --- | --- |
| Support éditeur | supporté | supporté | supporté (méthode recommandée sur matériel dédié) |
| Add-ons | non : conteneurs Compose équivalents (Mosquitto, SomfyProtect2MQTT, Zigbee2MQTT) | oui | oui |
| HACS / intégrations tierces | identique (HACS ne dépend pas du type d'installation) | identique | identique |
| Dongle USB | `devices:` par chemin `by-id` ; redémarrer l'App après rebranchement | passthrough USB de la VM (fragile selon les contrôleurs) | natif |
| Découverte mDNS / Matter / HomeKit | non (bridge) : équipements déclarés par IP | oui sur OPT | oui sur OPT |
| Infrastructure as Code | complète (Compose, digest épinglé, catalogue, Gatus, tests) | faible (appliance, configuration hors Git) | faible |
| Sauvegarde | snapshots ZFS `cpool/ha` + PostgreSQL partagé | sauvegardes HAOS + snapshot du zvol | sauvegardes HAOS vers le NAS |
| Isolation | conteneur non privilégié, `no-new-privileges`, LAN | VM isolée dans la zone IoT | machine dans la zone IoT |
| Disponibilité de la domotique | liée à TrueNAS | liée à TrueNAS | indépendante du NAS |
| Coût | aucun | 2–4 Go de RAM, VM à maintenir | matériel à acheter |

## Décision proposée

**Option A : rester en HA Container et terminer la migration Compose.**

- Passer à HAOS ne résout aucun des blocages réels : la passerelle Flexom
  fermée, le réappairage io et l'alarme cloud restent identiques.
- Les besoins actuels (USB, TCP vers OPT, MQTT) sont couverts par Compose sans
  `privileged`, `network_mode: host` ni montage de `/dev`.
- La configuration reste versionnée, revue et testée comme le reste du homelab.

## Conditions de réexamen

Revoir l'option C (puis B) si l'un de ces besoins devient réel :

- Matter ou Thread, HomeKit Controller (Somfy Connectivity Kit), ou autre
  intégration qui exige la découverte multicast ;
- un add-on sans équivalent conteneur maintenu ;
- l'exigence que volets et alarme fonctionnent pendant la maintenance de TrueNAS.

Une migration éventuelle passera par une sauvegarde HA restaurée sur la cible,
la règle pfSense minimale vers OPT et la mise à jour du catalogue.

## Conséquences

- Les services complémentaires (broker MQTT, SomfyProtect2MQTT) seront des
  conteneurs Compose dédiés, jamais dans le conteneur HA.
- Les intégrations à découverte multicast restent hors périmètre tant que
  l'option A est retenue.
