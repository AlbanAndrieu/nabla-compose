# Boucle roadmap du 21/11/2026 : état

Mode sprint homelab approuvé par le propriétaire le 21/11/2026 : appliquer,
redéployer et créer sans accord pas à pas, une PR par dépôt, questions après
cinq passes, cycle de réconciliation toutes les trois passes
([skill](../../.agents/skills/nabla-roadmap-loop/SKILL.md)).

| Dépôt | PR de consolidation |
|---|---|
| nabla-compose | [#430](https://github.com/AlbanAndrieu/nabla-compose/pull/430) (fusionnée le 21/11), puis [#432](https://github.com/AlbanAndrieu/nabla-compose/pull/432) |
| fastapi-sample | [#452](https://github.com/AlbanAndrieu/fastapi-sample/pull/452) |
| nabla-openclaw | [#26](https://github.com/AlbanAndrieu/nabla-openclaw/pull/26) |
| nabla-site-alban | [#336](https://github.com/AlbanAndrieu/nabla-site-alban/pull/336) |
| ansible-workstation | [#38](https://github.com/AlbanAndrieu/ansible-workstation/pull/38) |

## Compteur

| Passe | Début | Fin | Réconciliation |
|---|---|---|---|
| 1 | 21/11 | 21/11 | après la passe 3 |
| 2 | 21/11 | 21/11 | après la passe 3 |
| 3 | 21/11 | 21/11 | fait : skill (e863e844), refactorisation (lot 3a), docs |
| 4 | 21/11 | 21/11 | après la passe 6 |
| 5 | 21/11 | 21/11 | après la passe 6 ; questions posées à l'issue de cette passe |
| 6 | 21/11 | 21/11 | à faire : réconciliation (skill, instructions, docs, refactorisation) |

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
| Sample : `build_revision` = commit déployé sur TrueNAS | DEPLOYED | c7ce1981 ; `BUILD_REVISION=da6ef747…` dans le conteneur |
| Checkout TrueNAS avancé | fait | 1bd9200e |
| ntopng : séries RRD en tmpfs (`/var/lib/ntopng/0` et `-1`, chown par l'entrypoint) | DEPLOYED | 6ad96b8c, e6c64afa, `app.redeploy ntopng` ; RRD écrits sans `Permission denied` |
| Sondes TrueNAS de LiteLLM : `172.17.0.24:4000` au lieu de la boucle locale (faux `BLOCKED`) | DEPLOYED (checkout) | 25b78deb ; `/health/readiness` `healthy` |
| Tempête IO : `usermod` de `paperless-ngx` (copy-up overlay, une synchro txg par fichier) | App arrêtée | pool de 1 070 à 269 écritures/s, txg revenus à 5 s ; suite au point 6 du plan de performance |
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
| Route Tunnel `login` → `http://172.17.0.24:31090` (honeypot) | DEPLOYED (22/11) | c4fc9da0 (245df0af de la session « DNS Cloudflare morts », gate vert là-bas puis ici) ; recette LAN `/` 200, `/wp-login.php` 404 ; plan attendu du second plan : 2 ajouts, 1 modification, 0 destruction ; appliqué le 22/11 avec la configuration du Tunnel (ligne « Applies OpenTofu du 22/11 ») |
| FastAPI Sample 1.39.0 (master da6ef747) sur TrueNAS | DEPLOYED | `update-fastapi-sample.sh` (`systemd-run`, `HOME=/root`), `Result=success`, observateur et Prometheus/Gatus OK ; build de 1 h, ralenti par le test SMART de la nuit |
| Readiness TrueNAS stricte | ACCEPTED | `diagnose-service-readiness.py --check --strict` : HEALTHY=8, WARN=0, BLOCKED=0 (LiteLLM 25b78deb, Sample attesté) |
| Smoke RBAC pfSense retiré de `update-fastapi-sample.sh` (pfSense retiré le 18/11) | CODED | il ne pouvait plus que lever un WARN |
| nabla-site-alban passe 1 : `master` rouge réparé (next 16.4.6), retrait pfSense affiché, garde H17 (aucun lecteur V1/legacy) | TESTED | c34eab0, 3d71fb8, da026a6, 79789e3 ; `quality:agent:publish` PASS (`QG_PUBLISH_PROOF_OK`) dans un clone propre ; poussé par l'utilisateur (YubiKey), PR Draft #336 |
| fastapi-sample passe 2 : `composeProfiles` accepté (état `on_demand`), jauge `nabla_startup_phase_duration_seconds` (F08) | TESTED | #452 à 8e710b42 (ded6e023, be256bd3) ; L2 et L3 verts (rapport du sous-agent, tête vérifiée sur GitHub) ; déploiement `NOT_RUN` |
| H17 suite : `composeProfiles` dans `entities.json` | CODED | dérivé de `profiles:` dans Compose, 9 entités ; le Sample déployé l'ignore (projection limitée à `provider/appId/containerService/networks`) ; `services.json` attend le déploiement de #452 |
| Passe 5 : re-test | fait (11:41) | 0 alerte active (`TrueNASHostIOPressureHigh` éteinte avec la fin du test SMART) ; Gatus 68/68 ; Prometheus 11 cibles DOWN sur 38 : 10 `planned`, plus `keycloak` (`active`, App `STOPPED` depuis au moins 14 h, activation bloquée par V1). La passe 4 aurait dû le relever : sa mention « aucune cible non `planned` en panne » était fausse ; Vaultwarden `locked` ; les 5 PR `MERGEABLE`, CI verte |
| F14 (1) Sample : un job `exited` n'est pas un échec | vérifié | middleware TrueNAS `ix_apps/query.py` l. 266 : `exited` avec `ExitCode != 0` → `crashed` (App `CRASHED`), donc `exited` = code 0 ; en direct `defectdojo-initializer` `exited`, App `RUNNING` ; mise en œuvre demandée sur fastapi-sample#452 |
| Réconciliation des roadmaps sur #432 | CODED | `roadmap.md` : doublons fusionnés (ordre H01→H16, H05, H12, Talos, Cloudflare, fastpool, H18) et éléments terminés retirés (H01 réceptionné, H02, fenêtre nocturne, SMART, redéploiements, rétention Mimir, ddns-updater, Terragrunt CD) ; portfolio : H01 `ACCEPTED`, H05/H08/H10/H17 au 21/11, addenda H13/H20 dupliqués retirés ; `check-roadmap-portfolio.py --check` PASS |
| Vaultwarden 1.37.3 au lieu de 1.37.5, `bitwarden-api` en boucle | constaté | `docker ps` : `vaultwarden/server:1.37.3` (App `ix-vaultwarden`, aucun conteneur `doco-cd`) alors que `master` déclare 1.37.5 ; `bitwarden-api` : 692 redémarrages, « Vault is locked » |
| NetBox (H08) | constaté | App `RUNNING`, conteneurs `healthy` depuis 2 jours, statut `active` |
| Passe 6 (décisions du propriétaire, 21/11 après-midi) : IP cliente publique derrière le Tunnel (Traefik `forwardedHeaders.trustedIPs` limité à `ix-cloudflared_default`, plugin CrowdSec sur `Cf-Connecting-Ip`, parseur `s02-enrich`) | DEPLOYED (22/11) | 482629ba ; Traefik redéployé sur `ix-cloudflared_default`, CrowdSec réconcilié (`deploy-crowdsec.sh --apply`) ; `NOT_RUN` : IP réelle dans `access.log`, aucune route du Tunnel ne passant encore par Traefik (`fastapi_sample_tunnel_via_traefik=false`). Défaut trouvé par la session « DNS Cloudflare morts » : la Managed Transform de zone `remove_visitor_ip_headers` retire `CF-Connecting-IP` avant toute origine (le honeypot voit la passerelle Docker 10.200.49.1) ; correctif d8473ab2 (`managed-transforms.tofu`, importé sans cette transform), apply bloqué par la permission ci-dessous |
| Bouncer Cloudflare Worker de CrowdSec (profil `cloudflare-bouncer`, jeton `nabla-crowdsec-cloudflare-bouncer` limité à albandrieu.com) | CODED | 69a08d34 ; `NOT_RUN` : apply du jeton, secrets, démarrage, passage manuel des routes en Fail Open |
| Watchtower retiré au profit de Renovate (Q2) | CODED | 06ecc705 ; réactivation de l'App Renovate : étape du propriétaire (navigateur de l'agent non connecté à GitHub) |
| Préfixe IPv6 masqué dans la doc réseau, DNS du R7000 décidé (Q6) | CODED | 627f0e58 ; le préfixe reste dans `scripts/truenas/ipv6-guard.nft` et l'historique Git ; réglage du R7000 : étape du propriétaire |
| P3 : famille Workstation Gateway supprimée (90 fichiers, 73 recettes) | TESTED | 61c11dcb (sous-agent vérifié : suite complète 3175 verts) ; gate avec `QUALITY_ALLOW_LARGE_DELETION=1` |
| Vaultwarden 1.37.5 (correctif sécurité) | DEPLOYED | snapshot `cpool/vaultwarden@pre-1.37.5-20261121`, `midclt call -j app.redeploy vaultwarden` ; `vaultwarden/server:1.37.5` `healthy`, `/alive` 200 |
| `bitwarden-api` en boucle : cause | DEPLOYED | Pi-hole gardait `172.17.0.24 vaultwarden.albandrieu.com` (et `garage.albandrieu.com`) sans routeur Traefik : tout client LAN relayé par le R7000 recevait le 404 de Traefik, apps Bitwarden mobiles en Wi-Fi comprises. Retirés par `scripts/truenas/pihole-public-host-override.sh` (c62cd8d5, `check` → `apply` → `check` `ABSENT`) ; le LAN suit désormais la route publique, Access garde `/admin`. Après `docker restart`, l'adaptateur est `healthy`, 0 redémarrage, « Syncing complete ». `hello.albandrieu.com` et `garage-admin.albandrieu.com` ont la même surcharge mais aucun enregistrement public : laissés |
| FinOps Vercel (O3, relevé par l'agent) | constaté | tableau *Usage* (navigateur intégré) : CPU actif Fluid 4 h 22 min sur 30 jours, soit 109 % du quota Hobby de 4 h ; une hausse temporaire ×3 jusqu'au 9/12 ramène l'usage à 36 %. API Billing FOCUS : 404 `costs_not_found` ; AI Gateway : vide ; la ventilation par projet ne s'affiche pas. Seuil `CRITICAL` (90 %) de `docs/vercel-finops.md` (nabla-openclaw) dépassé hors dérogation |
| fastapi-sample passe 2 (suite) : F14 (1), F01 `deployment_id`, F07 ZFS par service, master rouge réparé | TESTED | #452 fusionnée pendant la passe ; reprise en [#455](https://github.com/AlbanAndrieu/fastapi-sample/pull/455) (Draft, 25a05710), L2 et L3 verts |
| nabla-site-alban S1–S3 : 9 icônes (selfh.st CC BY 4.0, APISIX officiel, honeypot générique), graphe OWNER Freebox → R7000 → Pi-hole, registre Postgres des webhooks Stripe | TESTED | #336 à 6a0b17f2, `quality:agent:publish` vert ; `NOT_RUN` : provisionnement Neon et test Stripe |
| P1 : pre-commit sur ansible-synergy | CODED | #3 à 7ef08627 : hooks réparés, le check échoue désormais sur de vrais constats (ansible-lint 46, shellcheck `.envrc`, conflit pyupgrade/fix-encoding-pragma, `git-branches-check` sans `user.name` en CI) |
| Applies OpenTofu du 22/11 : unité `cloudflare` depuis `master` ad0ee85c | DEPLOYED | 28 imports, 7 ajouts (applications Access affine, famp, freshrss, ha, immich, plumber-api ; CNAME `truenas`), 3 modifications (configuration du Tunnel, Access joplin, CNAME plumber-api), 8 destructions (CNAME du Tunnel retirés). Sauvegarde d'état `20261122T125905Z-ad0ee85c`. Plan suivant depuis 249698f0 : 0 changement. Fumée publique : vaultwarden 200 ; truenas, immich, gatus et fastapi-sample en 302 vers Access ; adguardhome NXDOMAIN |
| Ressources `retired` à recréer après l'apply : cause | CODED | Un nom passé de `tunnel` à `retired` dans le même apply est importé en `retired` puis détruit par `tunnel` (même identifiant). L'enregistrement disparaît et le plan suivant veut le recréer ; Cloudflare refuse ce CNAME sans contenu (9007). Les 5 identifiants concernés (autoxpose, drawio, pihole, sentry, traefik) sont retirés de `dns-record-ids.auto.tfvars` ; plan : 0 changement |
| Bloc mail de `cloudflare` (SPF, DMARC, MTA-STS des zones albanandrieu.com, bababou.com, dr-alban.com) | bloqué | aucun jeton disponible ne couvre ces zones (403) ; plans lancés avec `-exclude` |
| Unité `cloudflaretokens` (jeton du bouncer) | bloqué | aucun jeton d'amorçage valide avec « Account API Tokens Write » (`CLOUDFLARE_ACCOUNT_API_TOKEN` : 401) |
| Managed Transforms de albandrieu.com (d8473ab2, 1a4a4afd) | CODED | `nabla-opentofu` reçoit « Zone Transform Rules Write » sur albandrieu.com seulement ; plan ciblé : 403 tant que `cloudflaretokens` n'est pas appliqué (même jeton d'amorçage). D'ici là, tout plan complet de `cloudflare` ajoute `-exclude=cloudflare_managed_transforms.albandrieu` (le bloc `import` n'est pas conditionnel) |
| Unité `github` (rulesets, pre-commit strict sur nabla-compose) | ACCEPTED (déjà convergée) | plan depuis 249698f0 : « No changes ». Le `TF_VAR_github_app_pem` exporté par l'environnement est illisible (401 « JSON web token could not be decoded ») : plan lancé avec `env -u TF_VAR_github_app_pem` et `GITHUB_TOKEN=$(gh auth token)` |
| H04 : WAF Vercel de Bababou (`vercel-waf`) | bloqué (forfait) | Inventaire conforme à la base du HCL (aucune règle, challenge anti-bot, gen/sqli/xss/rce en `log`). Import dans l'état Garage réussi ; plan revu : 1 modification (SQLi/XSS/RCE en `deny`, une règle de 300 req/60 s/IP sur les trois domaines). Apply refusé : `payment_required - OWASP Core Ruleset is not available for this plan`. WAF relu inchangé (version 1). Sauvegarde d'état `20261122T135556Z-249698f0`. Jeton : `VERCEL_API_TOKEN=$VERCEL_TOKEN` (item `nabla/prod/vercel`) |
| Unité `github-artifact-app` (App `nabla-github-app`) | bloqué | App enregistrée le 20/11 (id 5854763), mais `/mnt/cpool/secrets/runtime/nabla-github-app/` n'a ni `github-app.json` ni clé : ID d'installation inconnu, `discover-github-app-installation.py --apply` impossible |
| Redéploiements du 22/11 : homarr, nexus, prometheus, traefik ; CrowdSec | DEPLOYED | `redeploy-impacted-apps.py --apply` (`NABLA_IMPACTED_REDEPLOY_APPROVED=yes`), `deploy-crowdsec.sh --apply` ; le contrôle Loki pfSense de ce script est périmé (pfSense retiré le 18/11) |
| Home Assistant arrêté (Gatus en échec, port 30103 refusé) | DEPLOYED | `app.stop` du 21/11 14:50 d'origine inconnue ; `midclt call -j app.start home-assistant` le 22/11 : `RUNNING`, `/manifest.json` 200 en 10 s. Leçon : en mode sprint, redémarrer sans demander (skill, section « Decide, do not ask ») |
| MCP `truenas-readonly` (H10) | DEPLOYED | Cause : le serveur s'arrêtait au démarrage, l'app n'ayant ni `TRUENAS_MCP_HOST` ni `TRUENAS_MCP_API_KEY`. 00f0bc7c : lanceur `scripts/mcp/truenas-readonly.sh` (clé dans un fichier 600), nom TLS épinglé sur 172.17.0.24 pour ce seul processus (le certificat ne couvre que `truenas.albandrieu.com`, résolu vers le Tunnel), démarrage hors du `.env` du dépôt que le paquet chargerait. `mcp-readonly-identity.sh apply` (terminal du propriétaire, Vaultwarden déverrouillé) : utilisateur `mcp_readonly` dans `truenas_readonly_administrators`, clé, item `nabla/prod/truenas-mcp-readonly` ; `check` CONVERGED. Recette stdio : authentifié, 19 outils, `system_info` 27.0.0-RC.1, `app_list` 98 Apps |

Leçons (à reporter dans le skill au cycle de réconciliation) :

- Ne jamais modifier le clone pendant que le gate tourne : il échoue sur « Working tree is not clean ».
- Toutes les sous-parties d'une même App TrueNAS déclarent le même `status` x-nabla ; un service optionnel passe par un profil Compose (précédent `dsomm-baseline`).
- `docker logs` doit montrer `init process complete` avant `pg_isready` : l'entrypoint PostgreSQL répond depuis un serveur `initdb` temporaire puis redémarre.

Refactorisation de la passe 3 (signalée par la passe 2 d'openclaw) : lot 3a fait (recettes `openclaw-429-attribution*`, sonde des cooldowns d'auth et son test), puis P3 accordé et fait le 21/11 (61c11dcb). Avant : l'étape 10 n'avait pas bougé depuis le 11/11. Restent 41 scripts OpenClaw sous `scripts/workstation/` et 13 fichiers sous `ops/` ; les recettes `openclaw-upgrade-local-*` et `openclaw-429-*` visent le Gateway Workstation, désactivé depuis le 3/11.

Leçon : `ansible-playbook` ouvre son propre socket SSH (YubiKey) ; `ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o BatchMode=yes"`, sans `ControlPersist`, réutilise le ControlMaster de `~/.ssh/config`.

Leçon : `systemd-run` en root fait refuser à git un checkout appartenant à `albandrieu` (« dubious ownership »). Passer `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=safe.directory` et `GIT_CONFIG_VALUE_0=<checkout>`.

## Décisions du propriétaire (21/11)

Toutes les recommandations de la passe 5 sont acceptées.

| Question | Décision | Statut |
|---|---|---|
| Q1 | Bouncer Cloudflare en bordure ; Traefik et CrowdSec voient l'IP publique | CODED (482629ba, 69a08d34) |
| Q2 | Watchtower retiré, Renovate seule source | CODED (06ecc705) ; App Renovate à réactiver par le propriétaire |
| Q5 | `talosconfig` et `kubeconfig` en pièces jointes Vaultwarden | fait : note sécurisée `nabla/prod/talos-operator` (dossier TrueNAS) créée avec les deux pièces jointes, script idempotent lancé dans le terminal du propriétaire |
| Q6 | Pi-hole principal, Freebox secondaire sur le R7000 ; préfixe IPv6 retiré de la doc | CODED (627f0e58) ; réglage du R7000 par le propriétaire |
| V1 | Plans et applies OpenTofu dans le terminal du propriétaire (`bw` déverrouillé constaté à 13:45) | fait le 22/11 pour `cloudflare` (hors bloc mail) ; `cloudflaretokens` bloqué (jeton d'amorçage) |
| O1, O2 | Slack OpenClaw en sortie seule ; App GitHub dédiée à la devbox | consignés (nabla-openclaw aee76db) ; création de l'App `NOT_RUN` |
| O3 | FinOps relevé par l'agent | constaté (journal) |
| P1 | pre-commit, une PR par dépôt actif | ansible-synergy #3 ouvert ; 4 dépôts sautés car sales (nabla, nabla-projects-interview-visma, ansible-cpp, ansible-gcc) |
| P2 | paperless-ngx en Custom App sur `/mnt/cpool/paperless` | planifié : documents personnels, migration seulement avec export vérifié et chemin de retour testé |
| P3 | Commit unique, `QUALITY_ALLOW_LARGE_DELETION=1` | TESTED (61c11dcb) |
| S1–S3 | Icônes selfh.st, Postgres (Neon) pour Stripe, graphe OWNER recâblé | TESTED (#336) ; Neon `NOT_RUN` |
| F07a, F07b, F01 | netdata par App, ZFS par convention, corrélation par `FASTAPICLOUD_DEPLOYMENT_ID` | F07b et F01 TESTED (#455) ; F07a impossible tel quel (question ci-dessous) |

## Questions ouvertes (à poser après la cinquième passe suivante)

- **Gate des grosses suppressions** : #436 (fusionnée le 22/11) retire `check_destructive_diff` de `scripts/agent-quality-gate.sh` et `QUALITY_ALLOW_LARGE_DELETION` ; voulu, ou à rétablir ?
- **H04 WAF Vercel** : l'OWASP Core Ruleset est payant (forfait actuel refusé). Passer Bababou en Pro, ou réduire le HCL à la seule règle de rate limiting (gen/sqli/xss/rce laissés en `log`) ?
- **`nabla-github-app`** : déposer sa clé privée et `github-app.json` dans `/mnt/cpool/secrets/runtime/nabla-github-app/` (étape propriétaire), puis découverte de l'installation et apply de `github-artifact-app` ?
- **F07a** : TrueNAS 27.0.0-RC.1 n'a pas de graphe netdata par App (`reporting.netdata_get_data` ne sert que ses graphes fixes). La seule source par App est l'abonnement `app.stats`, par App et non par service Compose : remplace-t-il cAdvisor ?
- **ansible-synergy #3** : corriger les constats ansible-lint et shellcheck dans cette PR, ou d'abord fusionner #2 (`fix/ansible-core-2.21`) qui en couvre une partie ?
- **Surcharges Pi-hole sans route publique** : `hello.albandrieu.com` et `garage-admin.albandrieu.com` renvoient le 404 de Traefik en LAN ; les retirer (NXDOMAIN) ou leur donner un routeur ?
