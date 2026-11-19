# Passe de roadmap du 20/11/2026 : bloqueurs et questions

Passe lancée le 19/11 au soir depuis la workstation (lectures LAN, SSH TrueNAS
en lecture seule). Statuts : `CODED` et `TESTED` hors ligne, `NOT_RUN` pour
tout ce qui n'a pas été appliqué en runtime. H13 (#423) et H17/CTEM (#422)
sont tenus par d'autres sessions : pas touchés ici.

## Fait pendant la passe

| Sujet | Statut | Commit |
|---|---|---|
| `master` cassé depuis #418 : artefacts du catalogue V2 régénérés | TESTED | 221099c0 |
| Ollama LAN seulement aussi dans le catalogue legacy (audit de parité V2) | TESTED | e4f23328 |
| `mem_limit` sur Traefik, `dnsupdater`, `cloudflare-ddns`, Redis, `redis_exporter`, CrowdSec (pic de 25 h × 2), cliquet 59 → 53 | CODED | 51f39601 |
| `cron.sh` recharge les règles Prometheus même après un `git pull` manuel | TESTED | 9410ca8b |
| Roadmap : relevés du 19/11, items obsolètes, recommandations | fait | eda6f71b, c93c064e, 62288d54 |

Relevés en lecture seule du 19/11 à 23:52 : Gatus 68/68 ; Prometheus
`up == 0` limité aux 12 exporters `planned` ; `app.query` 96 Apps (66
`RUNNING`, 30 `STOPPED`) ; VMs Talos `RUNNING` ; pic de charge à 10,6 vers
04:20 le 19/11.

## Bloqués

| Item | Classe | Blocage | Question ou commande de réception |
|---|---|---|---|
| Alertes `pfSenseMetricsMissing`, `AkvoradoPfSenseExporterMissing` | RUNTIME | Prometheus n'a pas relu les règles de #419 (pull manuel à 23:42) | Q1 ; `ssh truenas 'sudo -n bash /mnt/cpool/compose/nabla-compose/scripts/truenas/reload-prometheus-rules.sh apply'` |
| Redéploiements en attente (Redis, Dozzle, Traefik, CrowdSec, `mem_limit`, dsomm, scrutiny, Sentry LAN) | DÉCISION | feu vert et ordre | Q2 ; `just truenas-impacted-apps-plan <sha> master` |
| H01 Talos : reclaim ZFS, NetworkPolicy, recette CSI | RUNTIME | `talosconfig` du poste vide, aucun kubeconfig Talos | Q3 |
| Pic d'IO de 04:00 | RUNTIME | la capture du 18/11 n'a rien laissé | Q4 |
| Contrôle du catalogue avant fusion | DÉCISION | le ruleset n'exige que GitGuardian, sans branche à jour | Q5 ; `terraform/github/main.tofu` (#420) |
| H05 : `entityRef`/`catalogRevision`, `declared_only` | RUNTIME | Sample répond 401 sans clé de diagnostic | lancer avec `NABLA_DIAGNOSTICS_KEY` ou depuis le conteneur `fastapi-sample` |
| H02 G1, H03 vagues B et C | RUNTIME | session Vaultwarden | [runbook G1](postgres-g1-restore-and-secret-rotation.md), [secrets](2026-11-10-secrets-migration-backlog.md) |
| H04 plan Cloudflare | RUNTIME | clés S3 de l'état Garage absentes du coffre | `terragrunt-safe.sh plan` après ajout des clés |
| H09 `verify-full` des 10 clients restants | RUNTIME | CA et SAN à vérifier client par client, puis redéploiement | inventaire du 18/11 dans la roadmap |
| H07 pfSense | — | suspendu : aucune appliance depuis le 18/11 | — |
| H08, H19 | DÉCISION | un `--apply` à la fois sur accord | `rollout-pending-apps.sh --check` |

## Questions

| # | Question |
|---|---|
| Q1 | Je recharge les règles Prometheus maintenant (promtool puis SIGHUP, sans redémarrage) pour éteindre les deux alertes pfSense ? |
| Q2 | Feu vert pour un lot de redéploiement de nuit, et dans quel ordre ? |
| Q3 | Où se trouve le `talosconfig` (Vaultwarden ?), pour le rendre au poste ? |
| Q4 | Je reprogramme la capture d'IO en lecture seule cette nuit, de 03:56 à 04:30 ? |
| Q5 | J'ajoute au ruleset « Protect master » le check pre-commit avec branche à jour obligatoire, au prix d'un rebase avant chaque fusion ? |
| Q6 | Reprises de la [passe du 18/11](2026-11-18-roadmap-pass-blockers.md) encore ouvertes : DNS distribué par le DHCP de la Freebox (Pi-hole d'abord ?), `ddns-updater` (IP Free fixe ?) et le préfixe IPv6 publié dans `docs/pfsense/roadmap.md`. |
