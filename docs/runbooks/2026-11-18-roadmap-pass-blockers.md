# Passe de roadmap du 18/11/2026 : bloqueurs et questions

Chaque item ouvert des roadmaps a d'abord été trié (A : faisable hors ligne, B : lecture runtime d'abord, C : mutation live, D : décision ou achat), puis tenté. Ne restent ici que les items qui attendent une décision, une action physique ou une autorisation. Les questions sont posées une seule fois, à la fin de la passe. Statuts : `CODED` et `TESTED` (hors ligne), `NOT_RUN` (rien d'appliqué en runtime).

Rédigé le 17/11 à 23:43, avant le retrait de pfSense. Ce lot a été reconstruit le 18/11 après la perte du clone de travail : les constats, scripts et questions propres à l'appliance en ont été retirés.

## Fait pendant la passe

| Sujet | Statut | Où |
|---|---|---|
| Dozzle derrière `docker-socket-proxy`, actions et shell coupés | CODED | `apps/dozzle` |
| Redis : mot de passe lu depuis l'`env_file` canonique (Q18) | CODED | `apps/redis` |
| Bouncer CrowdSec dans Traefik (opt-in) et journaux d'accès vers CrowdSec | CODED | `apps/traefik`, `apps/crowdsec` |
| `mem_limit` sur 71 services d'après `memory.peak` × 1,5 | CODED | 33 `compose.yml`, ratchet 132 → 59 |
| Ratchet : aucun nouveau `/mnt/cpool/<app>/.env*` | TESTED | `tests/test_compose_legacy_env_ratchet.py` |
| Inventaires : consommateurs Doco-CD et `external_secrets`, socket Docker et `intranet` | fait | [secrets](2026-11-18-secrets-consumers-inventory.md), [socket](2026-11-18-docker-socket-intranet-consumers.md) |
| Catalogue : `tunnelUrl` périmés de `litellm-albandrieu` et `reactive-albandrieu` | CODED | `catalog/` |
| Alloy validé avec l'image déployée v1.18.0 | TESTED | `apps/grafana/config/alloy.alloy` |
| Déploiement de docling et bitcoind sur `lib/app-deploy.sh` | TESTED | `scripts/truenas/` |

Relevés en lecture seule du 18/11 (détail dans les roadmaps) : Gatus 69/69, Prometheus sans cible en panne hors `planned`, `app.query` (66 Apps actives, 30 arrêtées), `memory.peak` de 88 conteneurs, tâches de snapshot de 04:00, diagnostics Home Assistant, inventaire statique des clients PostgreSQL (H09). Une capture du pic d'IO de 04:00 est programmée.

## Constats qui changent une priorité

- **pfSense retiré** : le Netgate 1100 a gelé une septième fois le 18/11 vers 02:53 et n'est pas revenu après trois redémarrages. La Freebox fait routeur (cible LAN `172.17.0.1/24`, pour que les adresses fixes comme TrueNAS restent valables). Les scripts et sondes pfSense sont sans objet tant qu'aucun remplaçant n'est installé.
- **Pi-hole contourné** : il ne voit plus que 5 clients et 4 à 5 000 requêtes par jour (80 000 avant le 16/11), parce que le DHCP de pfSense ne le distribuait pas ; c'est désormais au DHCP de la Freebox de le faire. L'alerte `PiHoleAdsBlockedTooLow`, active depuis le 16/11, en est le symptôme et non une règle fausse.
- **Home Assistant** : le dongle USB branché est un Zigbee (ZHA), pas un EnOcean.

## Questions

| # | Sujet | Préparé | Question |
|---|---|---|---|
| Q1 | Remplacement de pfSense | étude de décommissionnement, outils Freebox | pfSense est retiré de fait : commander le 4200 (scénario B, derrière la Freebox) ou rester sur la Freebox en routeur (scénario A) ? |
| Q2 | App Freebox au moindre privilège | — | Peux-tu décocher ses droits par défaut dans Freebox OS ? |
| Q3 | Révision de la description de #409 qui citait un alias | description corrigée | Peux-tu supprimer cette révision dans l'interface GitHub ? |
| Q4 | DNS distribué par le DHCP de la Freebox | — | Pi-hole en premier, et quel résolveur secondaire ? |
| Q5 | `ddns-updater` | App arrêtée ; le DynDNS Cloudflare passait par pfSense | La relancer, ou l'IP publique Free est-elle fixe ? |
| Q6 | Redéploiements Compose | tout est `CODED` | Feu vert et ordre : Redis (installer d'abord le runtime), Dozzle (App arrêtée), Traefik puis CrowdSec (clé du bouncer à créer), puis les `mem_limit` par lots ? |
| Q7 | `X-Forwarded-For` sans HAProxy | bouncer Traefik opt-in | Par quel chemin le trafic Internet atteint-il Traefik maintenant, et quel proxy amont peut-on croire pour la vraie IP client ? |
| Q8 | « met les en production » du 16/11 | seules les étapes Git ont été faites | Cela couvrait-il aussi les étapes runtime de la passe du 16/11 (Q1, Q2, Q9 de cette passe-là) ? |
| Q9 | EnOcean pour Flexom | dongle actuel Zigbee | Acheter une clé USB300 ? |
| Q10 | Dépôt public | — | `docs/pfsense/roadmap.md` publie le préfixe IPv6 et l'adresse link-local de la Freebox (dérivée de sa MAC) : les remplacer par des exemples ? |

## Restent bloqués sans question nouvelle

- Identifiants requis : identifiants des applications Access orphelines (jeton Access en lecture), vagues de secrets B et C (session Vaultwarden), usage d'`opensearch-security` (identifiants admin), identité OVH en lecture.
- Fichiers OpenClaw de la workstation : encore utilisés par une vingtaine de recettes `justfile`, 7 scripts et environ 14 tests ; suppression reportée.
- Questions encore ouvertes de la [passe du 16/11](2026-11-16-roadmap-pass-blockers.md) : Q1, Q2, Q6 à Q10, Q14 (Talos arrêté), Q15, Q16, Q17.
