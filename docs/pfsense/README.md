# pfSense : documentation, incidents et roadmap

Tout ce qui concerne le pare-feu pfSense (Netgate 1100, bientôt Netgate 4200 MAX) est regroupé ici depuis le 17/11/2026. Objectif : pouvoir extraire pfSense vers un dépôt GitHub `nabla-pfsense` sans tout retrier. L'étude D3 de H11 est dans la [roadmap Compose](../roadmap.md#h11--scission-des-scripts-opérateur-et-diagnostics-étude-d0d4), et la règle de propriété dans l'[ADR-0003](../adr/0003-repository-ownership-and-diagnostics.md).

## Contenu

- [Roadmap pfSense](roadmap.md) : sécurité, écarts H07, stabilisation H07b et remplacement du 1100, historique P0 du 15/11.
- [Étude de décommissionnement](decommission-study.md) : ce que la Freebox Ultra peut reprendre, scénarios et phases (17/11).
- Documentation :
  - [Diagnostic et reprise](pfsense-diagnose-recover.md)
  - [Upgrade 26.03.1 → 26.07](pfsense-upgrade-26-07.md)
  - [Observabilité des flux et mémoire](pfsense-flow-observability-memory.md)
  - [Durcissement PHP-FPM](pfsense-php-fpm-hardening.md)
- [Runbooks](runbooks/) :
  - [environnements de boot et 26.07](runbooks/pfsense-26.07-upgrade.md)
  - [politique d'exposition](runbooks/pfsense-ingress-exposure-policy.md)
  - [provenance des décisions CrowdSec](runbooks/crowdsec-pfsense-decision-provenance.md)
  - [cibles workstation obsolètes](runbooks/2026-11-14-pfsense-stale-workstation-targets.md)
  - [Freebox en mode routeur, et retour en bridge](runbooks/freebox-router-mode.md)
- [Incidents](incidents/), du 08/09 au 17/11/2026 (WebConfigurator 502, Unbound OOM, pont du démarrage à froid, eMMC défaillante).
- [Preuves](evidence/) : instantané HAProxy expurgé, lu par `config/ingress-access-policy.json` et les tests.

## Matériel

### Netgate 1100 (en service, à remplacer)

Relevé du 17/11/2026 à 21:24 (`dmesg.boot`, `gpart`, `zfs list`). Système : pfSense Plus 26.03-RELEASE, FreeBSD 16.0-CURRENT.

| Élément | Valeur |
|---|---|
| Processeur | ARM Cortex-A53 r0p4, 2 cœurs |
| Mémoire | 1 Go : 1023 Mo réels, 940 Mo disponibles, sans swap |
| Réseau | un seul contrôleur `mvneta0` derrière un switch Marvell 88E6341 (`e6000sw0`). WAN et LAN sont des VLAN du même switch, d'où le [pont du démarrage à froid](incidents/2026-11-14-netgate-1100-cold-boot-switch-bridge.md) |
| Stockage | eMMC soudée de 8 Go (`mmcsd0`, 7,3 Gio utiles), partitionnée en MBR : EFI 200 Mo, FAT32 64 Mo, FreeBSD 7 Go |
| Pool ZFS | `pfSense` : 5,17 Go utilisés, 1,61 Go libres |

Une eMMC est une mémoire flash avec son contrôleur, soudée sur la carte : un petit SSD qu'on ne peut pas remplacer. Quand elle est usée, il faut changer le boîtier.

### Usure de l'eMMC

Lue le 17/11 à 21:08 avec [`emmc-health.sh`](../../scripts/pfsense/emmc-health.sh) (`mmc-utils`, registre `EXT_CSD`) :

| Indicateur | Valeur | Lecture |
|---|---|---|
| Durée de vie A (cellules SLC ou pseudo-SLC) | `0x0b` | 100 à 110 % de la durée nominale consommée |
| Durée de vie B (cellules MLC) | `0x0b` | idem |
| Réserve de blocs (`PRE_EOL_INFO`) | `0x01` | normale |
| Maintenance interne (`BKOPS_STATUS`) | `0x03` | critique : la puce est en retard sur le ramasse-miettes, l'effacement et le nivellement d'usure, donc une rafale d'écritures peut la bloquer |

Mesures du même soir, après la cure d'écritures :

- 0 erreur `mmcsd0` depuis le boot ;
- pool ZFS `ONLINE`, 0 erreur ;
- lecture brute de 256 Mio à 25,7 Mo/s ;
- 385 Mio de RAM libres, pas d'OOM ;
- 29 min de fonctionnement à 21:24, contre environ 4 min aux boots précédents.

Le test matériel de la RAM n'est pas faisable à distance. Le lien avec les gels est dans la [fiche d'incident](incidents/2026-11-17-pfsense-userland-freeze.md) : prouvé pour le gel capturé (timeouts `mmcsd0`, puis pool suspendu), probable pour les autres.

### Netgate 4200 MAX (cible, décidée le 17/11)

Atom C1110, 4 Go de RAM, SSD NVMe de 128 Go à la place de l'eMMC, 4 ports 2,5 Gb indépendants : plus de switch partagé entre WAN et LAN. Comparatif et étapes de migration dans la [roadmap](roadmap.md), « Gels userland » de H07b.

## Périmètre d'une extraction vers `nabla-pfsense`

À déplacer ensemble, dans un même lot testé :

| Chemin | Volume au 17/11 |
|---|---|
| `docs/pfsense/` | ce dossier |
| `scripts/pfsense/` | 46 fichiers, dont l'outil API Freebox |
| `tests/test_pfsense_*.py` | 37 tests |
| Recettes `pfsense-*` du `justfile` | 31 |
| `.agents/skills/pfsense-api-debugging/` | 1 skill |

À trancher avant le déplacement, car ces fichiers lisent ou appellent `scripts/pfsense/` depuis le reste du dépôt :

- **Outils workstation** : `scripts/workstation/verify-crowdsec-pfsense.sh`, `diagnose-whatsapp-web-path.sh` et `inspect-nexus-haproxy-frontend.sh`.
- **Outils qualité** : `scripts/agent-quality-gate.sh`, `scripts/quality/code-hotspots.py` et `scripts/ops/plan-repository-split.py`.
- **Tests transverses** : `test_code_hotspots.py`, `test_nexus_haproxy_frontend_readonly.py` et `test_repository_split_plan.py`.
- **CI** : `.github/workflows/observability-ci.yml`.
- **Politique d'entrée** : `config/ingress-access-policy.json`, qui lit le relevé HAProxy de `evidence/`.

Restent dans `nabla-compose`, avec des liens vers le nouveau dépôt :

- les Apps TrueNAS liées : `apps/crowdsec` et `apps/akvorado` ;
- les cibles Prometheus, Gatus et Loki ;
- Cloudflare ;
- les secrets ;
- l'incident Talos du 14/11 (`docs/incidents/2026-11-14-talos-control-plane-public-wan-lease.md`) et les incidents split-DNS partagés avec Pi-hole.

Conditions préalables (H11, D3) :

- propriété validée ;
- sauvegarde chiffrée de `config.xml` ;
- CLI `plan/check/apply/rollback` ;
- historique conservé, par exemple `git filter-repo` avec les chemins ci-dessus ;
- wrappers temporaires tant qu'un consommateur appelle encore l'ancien chemin.
