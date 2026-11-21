# Boucle roadmap du 21/11/2026 : état

Mode sprint homelab approuvé par le propriétaire le 21/11/2026 : appliquer,
redéployer et créer sans accord pas à pas, une PR par dépôt, questions après
cinq passes, cycle de réconciliation toutes les trois passes
([skill](../../.agents/skills/nabla-roadmap-loop/SKILL.md)).

| Dépôt | PR de consolidation |
|---|---|
| nabla-compose | [#430](https://github.com/AlbanAndrieu/nabla-compose/pull/430) |
| fastapi-sample | [#452](https://github.com/AlbanAndrieu/fastapi-sample/pull/452) |
| nabla-openclaw | [#26](https://github.com/AlbanAndrieu/nabla-openclaw/pull/26) |
| nabla-site-alban | aucune PR ouverte : branche créée au premier changement |

## Compteur

| Passe | Début | Fin | Réconciliation |
|---|---|---|---|
| 1 | 21/11 | en cours | après la passe 3 |

## Journal

| Item | Statut | Preuve |
|---|---|---|
| Consolidation dans #430 : Pi-hole, honeypot, mail des 20 zones, route Tunnel `login` | TESTED | c9b061ae, gate `agent-pre-push` vert, poussé |
| Checkout TrueNAS `/mnt/cpool/compose/nabla-compose` sur la branche de #430 (le cron horaire saute tant qu'il n'est pas revenu sur `master` : à rebasculer après fusion) | fait | `git checkout -B … FETCH_HEAD`, c9b061ae |
| Pi-hole : `app.redeploy` (upstreams `172.17.0.24#553, 9.9.9.9`, limite 6000, `revServers` vide) | DEPLOYED | `redeploy-impacted-apps.py --apply`, `healthy` ; `hello.int` et `github.com` résolus via le R7000 |
| Honeypot : App créée | DEPLOYED (LAN) | `reconcile-custom-apps.py --apply`, plancher 5 Gio ; `/healthz` `ok`, `/wp-login.php` 404 |
| Keycloak : Custom App créée à l'arrêt (manifeste `stopped`) | fait | même apply |
| OpenClaw : heartbeat appliqué au Gateway (B1 du dépôt nabla-openclaw) | DEPLOYED | collecteur `0f52f1ea…` sur TrueNAS = `master` ; scratch révision 8 |
| nabla-openclaw passe 1 (docs, état, blocages) | CODED | PR #26, 400a644, gate vert |
| H01 : NetworkPolicy appliquée par Cilium | TESTED | `smoke-networkpolicy-enforcement.sh` et `smoke-kubernetes-network.sh` verts |
| scrutiny : bascule déjà faite, Q4 close | constaté | `deploy-scrutiny.sh --check` : convergé |
| Gatus | constaté | 68/68 verts à 01:40 |

Leçon : `systemd-run` en root fait refuser à git un checkout appartenant à `albandrieu` (« dubious ownership »). Passer `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=safe.directory` et `GIT_CONFIG_VALUE_0=<checkout>`.

## Questions en attente

Reprises du [runbook du 20/11](2026-11-20-roadmap-pass-blockers.md), à poser
après la cinquième passe : Q1 (CrowdSec et Tunnel), Q2 (Watchtower), Q5
(`talosconfig` dans Vaultwarden), Q6 (secours DNS et préfixe IPv6).

Nouvelles :

- **V1 — Vaultwarden verrouillé** : les plans et applies Cloudflare (`CLOUDFLARE_API_TOKEN`, clés S3 de l'état Garage), les secrets de Keycloak sur Talos et les rotations H02/H03 en dépendent. Il faut une session déverrouillée (`bw unlock`, `BW_SESSION` dans l'environnement de l'agent), ou les deux variables d'OpenTofu exportées.
- **O1 — Slack d'OpenClaw** (passe nabla-openclaw) : le canal OpenClaw porte-t-il les notifications du control plane FastAPI, en sortie seule ?
- **O2 — identité GitHub de la devbox** : App dédiée ou compte machine ?
- **O3 — Vercel FinOps** : export JSON du tableau *Usage*.
