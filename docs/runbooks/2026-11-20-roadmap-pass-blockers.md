# Passe de roadmap du 20/11/2026 : bloqueurs et questions

Passe lancée le 19/11 au soir depuis la workstation : lectures LAN, SSH vers
TrueNAS, puis redéploiements sur feu vert du propriétaire (20/11). Statuts :
`CODED` et `TESTED` hors ligne, `DEPLOYED` pour ce qui tourne, jamais
`ACCEPTED`. H13 (#423) et H17/CTEM (#422) sont tenus par d'autres sessions :
pas touchés ici.

## Fait pendant la passe

| Sujet | Statut | Preuve |
|---|---|---|
| `master` cassé depuis #416 + #418 : artefacts V2 régénérés, Ollama LAN dans le legacy, test `diagnose-stuck-apps.sh` | TESTED | 221099c0, e4f23328, 5c6c44cd |
| `mem_limit` sur Traefik, `dnsupdater`, `cloudflare-ddns`, Redis, `redis_exporter`, CrowdSec, cliquet 59 → 53 | CODED | 51f39601 |
| `cron.sh` recharge les règles Prometheus même après un `git pull` manuel | TESTED | 9410ca8b |
| Vaultwarden 1.37.3 → 1.37.5 (GHSA-69q9-v8p6-xvx3 High, GHSA-x9cq-f669-vrr4) | CODED | 78415e6e, déployé par Doco-CD à la fusion |
| `ddns-updater` retiré, l'IP Free étant fixe | CODED | f8dc2893 |
| Ruleset nabla-compose : `pre-commit` requis, branche à jour | CODED | 075b9a99, plan et apply OpenTofu `NOT_RUN` |
| Redéploiements : homarr, litellm, ollama, prometheus | DEPLOYED | `impacted-redeploy-20261120.log`, sains |
| dsomm avec sa limite de 128m ; Dozzle démarré, connexion exigée | DEPLOYED | `docker inspect`, `/` → 307 `/login`, API 401 |
| Alertes pfSense éteintes, Gatus 68/68 | constaté | Alertmanager vide, `ALERTS` vide |
| `talosconfig` et kubeconfig copiés sur le poste | fait | `~/.config/nabla/talos`, 0600, empreintes identiques |
| Talos : 3 nœuds `Ready`, CSI `Running`, aucun PV ni dataset enfant | constaté | `kubectl`, `zfs list` |
| Capture d'IO de 03:56 à 04:30 | programmée | timer `nabla-io-peak-20261120` |

## Bloqués

| Item | Classe | Blocage | Question ou commande de réception |
|---|---|---|---|
| CrowdSec avec Traefik | DÉCISION | le tunnel Cloudflare envoie le trafic public directement aux services : 361/361 requêtes vues par Traefik viennent d'IP privées, ignorées par CrowdSec | Q1 |
| Watchtower | DÉCISION | tags épinglés, `NO_PULL`, aucun conteneur labellisé, proxy en lecture seule : il ne mettrait rien à jour | Q2 |
| Renovate sur tous les dépôts | RUNTIME | l'installation de l'App GitHub est une action du propriétaire | Q3 |
| scrutiny | DÉCISION | `deploy-scrutiny.sh --apply` exige `SCRUTINY_CUTOVER_APPROVED=1` après revue du snapshot, de l'historique et du token | Q4 |
| `talosconfig` dans Vaultwarden | RUNTIME | session Vaultwarden du propriétaire | Q5 |
| H01 NetworkPolicy | CODE | aucune NetworkPolicy dans le cluster | prochaine passe |
| Pre-commit sur les 50 autres dépôts | CODE | aucun job pre-commit sur leurs PR | ajouter le workflow avant de l'exiger |
| H05 `entityRef`/`catalogRevision` | RUNTIME | Sample répond 401 sans clé de diagnostic | lancer avec `NABLA_DIAGNOSTICS_KEY` |
| H02, H03, H04, H09 | RUNTIME | session Vaultwarden, clés S3 de l'état Garage, CA/SAN client par client | inchangé depuis le 18/11 |

## Questions

| # | Question |
|---|---|
| Q1 | CrowdSec : faire passer le tunnel Cloudflare par Traefik (le bouncer voit alors l'IP réelle via `CF-Connecting-IP`), ou bloquer à la périphérie avec le bouncer Cloudflare de CrowdSec ? |
| Q2 | Watchtower : on le laisse de côté au profit de Renovate, ou tu veux une surveillance des seuls tags `latest` (il faut alors autoriser les `pull` au proxy du socket) ? |
| Q3 | Installer l'App Renovate sur tous les dépôts : https://github.com/apps/renovate, « All repositories ». Une PR d'onboarding arrivera par dépôt sans configuration. |
| Q4 | ~~Close le 21/11 : `deploy-scrutiny.sh --check` constate la bascule faite (InfluxDB, web et collecteur `RUNNING`, SMART visible, fichier de secrets canonique).~~ J'approuve la bascule scrutiny après avoir relu snapshot, historique et token ? |
| Q5 | Tu ranges `talosconfig` et kubeconfig dans Vaultwarden (pièces jointes d'un élément `nabla/prod/talos-operator`) ? |
| Q6 | Restent de la passe du 18/11 : DNS distribué par le DHCP du R7000, routeur du LAN (Pi-hole seul, ou Pi-hole puis un secours hors TrueNAS ?) et le préfixe IPv6 publié dans `docs/pfsense/roadmap.md`. |
