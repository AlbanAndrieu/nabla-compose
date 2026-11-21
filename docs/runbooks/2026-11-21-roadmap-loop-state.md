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
| ansible-workstation | [#38](https://github.com/AlbanAndrieu/ansible-workstation/pull/38) |

## Compteur

| Passe | Début | Fin | Réconciliation |
|---|---|---|---|
| 1 | 21/11 | 21/11 | après la passe 3 |
| 2 | 21/11 | 21/11 | après la passe 3 |
| 3 | 21/11 | 21/11 | fait : skill (e863e844), refactorisation (lot 3a), docs |
| 4 | 21/11 | en cours | après la passe 6 |

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
| H01 : NetworkPolicy appliquée par Cilium ; reclaim CSI prouvé le 21/11 | TESTED | `smoke-networkpolicy-enforcement.sh` et `smoke-kubernetes-network.sh` verts |
| scrutiny : bascule déjà faite, Q4 close | constaté | `deploy-scrutiny.sh --check` : convergé |
| Gatus | constaté | 68/68 verts à 01:40 |
| H02 / G1 : sauvegarde des 9 bases, restauration isolée vérifiée 3 fois, reçu écrit, cron quotidien `nabla-postgresbackup` activé | DEPLOYED (hors rotation `postgres_exporter`, V1) | fbe1d0ce (`pg_restore --list` lisait `-`), 1bd9200e (attente du serveur final après `initdb`) ; `ISOLATED_RESTORE_VERIFIED` ; `reconcile-postgresbackup-cron.py --enable --job daily` |
| Redéploiements : redis, crowdsec, traefik (limites mémoire), clamav, scanopy, ntopng (zombies) | DEPLOYED | `redeploy-impacted-apps.py --apply` / `app.redeploy`, conteneurs `healthy` |
| ntopng : `recordsize=16K` et réécriture unique des RRD | DEPLOYED | `rewrite-ntopng-records.sh --apply` : 595 fichiers |
| `opensearch-security` hors du démarrage par défaut (profil `security`) | DEPLOYED | ef00ccc9, `app.redeploy opensearch` ; ~1,6 Gio libérés |
| Scrape de l'exporter HAProxy (pfSense retiré) supprimé | DEPLOYED | ae39fc9a, Prometheus rechargé : 38 cibles, `haproxy` absent |
| Falco sur Talos | DEPLOYED (constaté) | DaemonSet `falco` 3/3 |
| Sample : `build_revision` = commit déployé sur TrueNAS | CODED | c7ce1981, effectif au prochain `update-fastapi-sample.sh` |
| Checkout TrueNAS avancé | fait | 1bd9200e |
| ntopng : séries RRD en tmpfs (`/var/lib/ntopng/0` et `-1`, chown par l'entrypoint) | DEPLOYED | 6ad96b8c, e6c64afa, `app.redeploy ntopng` ; RRD écrits sans `Permission denied` |
| Sondes TrueNAS de LiteLLM : `172.17.0.24:4000` au lieu de la boucle locale (faux `BLOCKED`) | DEPLOYED (checkout) | 25b78deb ; `/health/readiness` `healthy` |
| Tempête IO : `usermod` de `paperless-ngx` (copy-up overlay, une synchro txg par fichier) | App arrêtée | pool de 1 070 à 269 écritures/s, txg revenus à 5 s ; suite au point 12 du plan de performance |
| H10 : recette post-upgrade TrueNAS 27.0.0-RC.1 | PARTIAL | VMs Talos sur l'API `vm.*` ; readiness : seul Sample en WARN (`build_revision` absent jusqu'à la prochaine mise à jour) ; diagnostic FastAPI en 401 attendu ; smoke CSI `--apply` vert depuis TrueNAS (provision, RWX entre deux workers, reclaim ZFS/NFS prouvé) ; MCP `truenas-readonly` « Connection closed » : `TRUENAS_MCP_HOST` et la clé API ne sont pas exportés dans la session (`.mcp.json` les lit dans l'environnement), donc secret absent (V1) et non régression de TrueNAS 27 |
| Keycloak et Joplin : activation | bloqué (V1) | aucun fichier de secrets runtime (`/mnt/cpool/keycloak/.env.secrets`, `/mnt/cpool/secrets/runtime/joplin/`) ; source Vaultwarden verrouillée |
| H09 : TLS PostgreSQL côté serveur | constaté | `pg_hba_file_rules` : seul `hostssl`/`scram-sha-256` pour le réseau ; TLSv1.3 minimum ; `pg_stat_ssl` : 8 clients réseau tous en TLSv1.3 |
| H17 : réception du catalogue V2 dans Sample | ACCEPTED (critère du 16/11) | sonde à clé 6fb919e4 : un seul `binding_conflict` (`sentry-edge`), aucune App arrêtée en `declared_only` |
| Noms publics `keycloak` (403) et `joplin` (502 par le Tunnel, App absente) | constaté | à revoir à l'activation de Joplin |
| Tests SMART longs à 08:00 (hors fenêtre nocturne de bitcoind) | DEPLOYED | ansible-workstation a1916a5, `truenas-stabilize.yml` plan/apply/plan à 0 action |
| nabla-openclaw passe 2 : x-nabla `active` pour le Gateway et la devbox, affirmations périmées retirées | TESTED | PR #26, 2d41c45 (`just test` vert, rapport du sous-agent vérifié sur GitHub) |
| H19 : migration Home Assistant vers Compose | bloqué (V1) | `migrate-homeassistant-to-compose.sh --check` : secret `/mnt/cpool/secrets/runtime/homeassistant/.env.secrets` absent, rôle PostgreSQL `homeassistant` non prêt, recorder sur une autre base, `http.trusted_proxies` vide ; 0 mutation |
| H17 suite : profils Compose dans le catalogue | reporté (passe 3) | `DeclaredService` de Sample est en `extra="forbid"` : Sample doit d'abord accepter `composeProfiles` et être déployé, nabla-compose le génère ensuite |
| Passe 3 : re-test des blocages | fait | Vaultwarden toujours `locked` (`bw status`) ; nabla-openclaw : note de l'étape 10 (8f4c935) ; fastapi-sample : acceptation de `composeProfiles` demandée à la passe en cours de #452, la génération côté nabla-compose attend son déploiement |
| Mimir : rétention de 90 jours | DEPLOYED | 1a029c66 ; `docker restart mimir` ; `/config` → `compactor_blocks_retention_period: 90d`, `/ready`, erreurs « empty ring » éteintes en 15 s |
| Passe 4 : re-test | fait (03:25) | Gatus 68/68 ; Prometheus 38 cibles, aucune cible non `planned` en panne ; seule alerte `TrueNASHostIOPressureHigh` (test SMART de la nuit et build FastAPI) ; Vaultwarden `locked` |
| NetBox (H08) | constaté | App `RUNNING`, conteneurs `healthy` depuis 2 jours, statut `active` |

Leçons (à reporter dans le skill au cycle de réconciliation) :

- Ne jamais modifier le clone pendant que le gate tourne : il échoue sur « Working tree is not clean ».
- Toutes les sous-parties d'une même App TrueNAS déclarent le même `status` x-nabla ; un service optionnel passe par un profil Compose (précédent `dsomm-baseline`).
- `docker logs` doit montrer `init process complete` avant `pg_isready` : l'entrypoint PostgreSQL répond depuis un serveur `initdb` temporaire puis redémarre.

Refactorisation de la passe 3 (signalée par la passe 2 d'openclaw) : lot 3a fait (recettes `openclaw-429-attribution*`, sonde des cooldowns d'auth et son test), reste soumis à P3. Avant : l'étape 10 n'avait pas bougé depuis le 11/11. Restent 41 scripts OpenClaw sous `scripts/workstation/` et 13 fichiers sous `ops/` ; les recettes `openclaw-upgrade-local-*` et `openclaw-429-*` visent le Gateway Workstation, désactivé depuis le 3/11.

Leçon : `ansible-playbook` ouvre son propre socket SSH (YubiKey) ; `ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o BatchMode=yes"`, sans `ControlPersist`, réutilise le ControlMaster de `~/.ssh/config`.

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
- **P1 — pre-commit sur les 50 autres dépôts** : ajouter le workflow partout représente 50 nouvelles PR à relire. Inventaire GraphQL du 21/11 (56 dépôts non archivés) : 33 ont un `.pre-commit-config.yaml`, dont environ 24 sans workflow nommé pre-commit, lint ou quality ; 16 d'entre eux ont été poussés depuis septembre. 22 n'ont ni config ni workflow. Proposition : commencer par ces 16 dépôts actifs ; d'accord ?
- **P3 — étape 10, famille Workstation Gateway** : le lot 3a retire les recettes `openclaw-429-attribution*` et la sonde des cooldowns d'auth. Le reste (`repair-openclaw-429.py`, `upgrade-openclaw-mise.py` et environ 35 autres scripts sous `scripts/workstation/`, leurs tests, une trentaine de recettes et 13 fichiers sous `ops/`) s'appelle en chaîne (`backup-openclaw.sh`, `openclaw-route-metadata.py`, `openclaw-recovery-readonly.sh`) et ne peut partir qu'en un lot de plus de 20 fichiers, et le gate exige `QUALITY_ALLOW_LARGE_DELETION=1` après revue explicite pour les fichiers de plus de ~300 lignes : d'accord pour un commit unique, et pour ce drapeau ?
- **P2 — paperless-ngx** : `sync=disabled` sur `cpool/ix-apps/docker` (dataset géré par TrueNAS), ou migration en Custom App ? (point 12 du plan de performance)
