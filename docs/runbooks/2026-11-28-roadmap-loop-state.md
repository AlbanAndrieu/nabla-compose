# Boucle roadmap du 28/11/2026 : état

Mode sprint ([skill](../../.agents/skills/nabla-roadmap-loop/SKILL.md)). PR de
consolidation nabla-compose : [#454](https://github.com/AlbanAndrieu/nabla-compose/pull/454)
(branche `fix/nexus-enabled-formats-20261127`, aucune PR sur la branche du checkout).
D'autres sessions travaillent en parallèle (site-alban, OpenClaw coder, pfSense, Vercel WAF #450) :
leurs périmètres ne sont pas repris ici.

## Compteur

| Passe | Début | Fin | Réconciliation |
|---|---|---|---|
| 1 | 28/11 | en cours | après la passe 3 |

## Journal

| Item | Statut | Preuve |
|---|---|---|
| H08 Nexus : dépôts APT/npm/PyPI | DEPLOYED (27/11) | plan/apply par format, plan final `No changes` ; ab96054b, ec609b05 (défaut `enabled_formats` figé) |
| H08 Nexus : identifiants Vaultwarden | fait (27/11) | `nabla/prod/nexus-infrastructure` (rôle `nabla-opentofu`, `security/*` 403) ; AWS_* de la clé Garage `opentofu` dans `infrastructure-bootstrap` ; plan du README `No changes` |
| Commit `drop the workstation Grafana service` resté sans PR | replié | 277fff1b (cherry-pick de d1f89735) |
| Snapshots : tâches 17-19 de `cpool` doublent les 62 datasets classés | DEPLOYED (nexus3, bitcoind) | fe3e85eb (ligne `doubled` du plan, test) ; exclusion 17-19 + purge : nexus3 931 Mio → 36 Mio, bitcoind 39,1 Gio → 0, dernière `auto-` gardée |
| Dérive OpenTofu : racine `nexus` enrôlée | DEPLOYED | compte lecture seule `nabla-opentofu-drift` (rôle `nabla-opentofu-read`), `nexus.env` root 0600 ; verdict `DRIFT` (6 destructions) sur `origin/master` 8aab83f6, attendu `IN_SYNC` après fusion de #454 |
| Snapshots `databases` doublés par 17-19 (accord du propriétaire) | DEPLOYED | 7 datasets exclus, 37-40 `auto-` historiques purgées chacun par nom après dry-run : 42,9 → 10,8 Gio (ClickHouse −30,7 Gio) ; `wazuh` garde une `auto-` (aucun point de classe) |
| `cpool/dococd` : Doco-CD inutilisé (propriétaire, 28/11) | DEPLOYED | `noSnapshot` dans `config/truenas/snapshot-tasks.json`, tâches 62/63 supprimées, exclu de 17-19, 41 `auto-` purgées (1,83 Gio) ; dataset et `manual-2026-07-08` conservés |
| H03 : secrets runtime Keycloak, Joplin, Homarr, `postgres-exporter` | DEPLOYED | `--verify` OK pour les trois derniers ; Keycloak différait de Vaultwarden hors mot de passe DB (les deux valeurs ouvrent la base `keycloak`) : réinstallé depuis Vaultwarden, Compose et scripts passés au chemin runtime, entrée retirée du cliquet legacy et de `debt-baseline.json` |
| Fenêtre de nuit : 15 Apps `operational-schedule: night` démarrées en série à 01:00 (`nabla-night-window-start`, arrêt à 07:00) | constaté | conception voulue (`reconcile-night-window-cron.py`), pas un incident ; pendant les démarrages, PSI IO 86-90 % et un txg toutes les ~1-1,8 s (syncs forcés), worker de Sample 12 min en état D (session « LA roadmap ») ; à étudier : démarrages espacés ou paperless-ngx hors fenêtre |

## Questions parquées

- Fusion de #454 (propriétaire) : sans elle, `OpenTofuDrift` se déclenche chaque jour à 09:00.
- Mot de passe `admin` de Nexus à changer et à retirer de `~/.m2/settings.xml` (propriétaire).
- Doublons restants : `app-state` (≈ 1,3 Gio, 42 datasets) à traiter ou non ; `critical` gardé doublé volontairement.
- Après le 01/12 04:00 : supprimer la dernière `auto-` historique de nexus3 et bitcoind une fois le premier point mensuel de classe créé.
