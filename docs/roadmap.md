# Services Homelab — roadmap active

> Mise à jour : **14 novembre 2026** ([passe du 13/11](runbooks/2026-11-10-roadmap-pass-blockers.md#8-reprise-du-1311), [audit TrueNAS du 13/11](runbooks/2026-11-13-truenas-audit-ssd-coverage.md)). Source d'autorité des **travaux restant à réaliser**. Une PR fusionnée ou un script versionné ne constitue pas une réception runtime. Les procédures courantes sont dans les runbooks spécialisés ; les problèmes passés utiles aux diagnostics sont dans [les leçons de migration](incidents/2026-11-06-migrations-retour-experience.md) et dans l'[archive immuable au 24/10](archive/roadmap-through-2026-10-24.md). Ne pas réexécuter d'anciennes commandes d'incident.

**Actualisation du 15/11 — progrès IPv4 partiel :** les connexions
TCP `1.1.1.1:443` et `9.9.9.9:443` ont réussi lors des diagnostics
pfSense. **`PF_IPv4_TCP_EGRESS_PASS`**, mais LAN/NAT, DNS/Unbound,
IPv6 et identification de la cause initiale **non vérifiés**. Maintenir
le P0 ouvert jusqu'à test HTTPS IPv4 depuis le LAN et réactivation
contrôlée des protections arrêtées. Ne pas présenter la désactivation
de `Gateway Monitoring` comme la cause démontrée de la reprise.


**Nouvelle observation (15/11) :** CrowdSec, Snort et pfBlockerNG
ont tous les trois été arrêtés avant les deux succès TCP depuis
pfSense. Impossible d'identifier la protection responsable.
La workstation indique toujours « pas d'Internet »,
`ping cloudflare.com` échoue et le GUI pfSense est très lent.
La priorité P0 reste **LAN IPv4/DNS et charge pfSense**
avant IPv6 et avant réactivation progressive des IPS.
[Recette détaillée](pfsense-diagnose-recover.md).


**Évidence supplémentaire (15/11, workstation) :** passerelle
`172.17.0.1` routée et joignable (ping 3/3, SSH OK), pfSense
load < 1, mais `dig @172.17.0.1` timeout. Priorité P0 :
diagnostiquer l'écoute/état/ACL Unbound (UDP et TCP 53), puis
l'accès direct IPv4 depuis la workstation et le NAT LAN.
L'identification du bloqueur initial et IPv6 demeurent ouvertes.
[Commandes et observations](pfsense-diagnose-recover.md).

**P0 récupération pfSense (15/11) — CODED, runtime NOT_VERIFIED :**
le nouvel outil `scripts/pfsense/recover-access.sh`, accessible via
`just pfsense-check`, `pfsense-dns`, `pfsense-ui` et `pfsense-recover`,
permet la reprise manuelle ciblée en SSH direct sans GUI, pfREST,
WAN DNS ni changement de firewall. Le diagnostic compare la résolution
LAN UDP/TCP, Unbound loopback/LAN, DNS public, sockets, erreurs/OOM.
**DONE** : résolution DNS et NAT IPv4 fonctionnels depuis la workstation,
GUI rétablie, puis protections restaurées une par une sans régression.
[Runbook](pfsense-diagnose-recover.md).

**Evidence DNS du 15/11 :** `dig @9.9.9.9` réussit depuis la
workstation, alors que `dig @172.17.0.1` expire et
`drill @127.0.0.1` sur pfSense indique `could not send or receive`.
Deux PID `unbound` observés, sans preuve de service DNS effectif.
Prioriser l'identification des sockets :53, du binding localhost/LAN,
de la configuration générée et des logs Unbound, avant modification
du NAT ou de la passerelle.

**P0 split-DNS après reboot (15/11) — CODED, runtime NOT_VERIFIED** :
résolution publique à nouveau fonctionnelle, mais
`int.albandrieu.com` non délégué à Pi-hole par Unbound :
`list_forwards` vide, `Domain Overrides` vide, réponse Cloudflare
sans A alors que Pi-hole renvoie `172.17.0.24`.
`reconcile-split-dns.sh --check/--apply` corrige l'override
et `outgoing_interface=all` de façon ciblée ; `check-drift.sh`
agrège les contrôles de posture. **DONE** : même A privé via
Pi-hole et Unbound, récursion publique OK, pas de reboot involontaire,
inventaire des dérives Boot Environment/Snort/pfBlockerNG/CrowdSec.
[Architecture DNS](dns-ingress-ownership.md).

**P0 observabilité Unbound — 15/11** : enrichir
`diagnose-unbound-restart-cause.sh` et le renderer partagé
`console.sh` avec triage coloré P0/P1, statut actuel Unbound,
détection du forwarder DNS privé, alertes ASN/IPinfo et DNSBL,
et distinction entre les anciens marqueurs stop/start et une
cause démontrée. Préserver la sortie brute CI et la neutralité
`ROOT_CAUSE_NOT_PROVEN`.
[Runbook de récupération](pfsense-diagnose-recover.md).

## Ordre d’exécution validé — 14 novembre 2026


## Incident réseau P0 — IPv4 Freebox bridge et IPv6 pfSense (15/11/2026)

**Ouvert (NOT_VERIFIED en runtime).** Free confirme la fibre et
`82.66.4.247` ; la gateway IPv4 `82.66.4.254` est déclarée
mais ICMP échoue et le test TCP renvoie `Permission denied`.
L'opérateur a coché **Disable Gateway Monitoring** sur le WAN :
cela désactive `dpinger`, sans prouver le retour Internet.

- **P0 IPv4 :** diagnostiquer les règles PF et les refus locaux,
  capturer les paquets sortants/entrants sur `mvneta0.4090`,
  puis vérifier le chemin Freebox/Free et le SNAT LAN seulement
  après test direct sur pfSense. **DONE :** HTTPS IPv4 depuis
  pfSense et un client LAN, preuves horodatées.
- **P1 IPv6 :** obtenir une connectivité IPv6 complète sur pfSense
  et le LAN. Free communique `2a01:e0a:a17:3c00::/64`,
  route IPv6 par défaut via `fe80::8e97:eaff:fe39:b37b`.
  Vérifier la route et le next hop Freebox, la disponibilité du /64
  LAN, RA/SLAAC Assisted, Android, les règles IPv6 et
  Unbound (Outgoing Network Interfaces = All).
  **DONE :** IPv6 globale sur client LAN, accès par IP littérale,
  DNS AAAA et aucune exposition WAN imprévue.
- **Après rétablissement :** envisager `Disable Gateway Monitoring
  Action` afin de conserver la surveillance sans actions automatiques
  inutiles sur un WAN unique.

[Runbook de diagnostic pfSense](pfsense-diagnose-recover.md).
Ce P0 incident ne modifie pas l'ordre du portefeuille H01–H19.


**Décision opérateur : H01 → H02 → H04 → H05 → H12 → H13 → H16.** Cet ordre remplace l'arbitrage du 13/11 (H02/G1 → H01 → H05). Garder un seul [portefeuille H01–H19](roadmap-portfolio.md) ; les tâches non retenues restent suivies sans être supprimées.

1. **H01 — Talos / Kubernetes CSI** : établir le pilote réellement installé et sa compatibilité TrueNAS 27 ; vérifier controller/DaemonSet, PVC NFS RWX sur deux workers, persistance, reclaim ZFS et NetworkPolicy. Ne pas déplacer Keycloak/Hermes/Vault avant réception. [Préflight CSI](kubernetes-csi-preflight.md).
   - 16/11 : pilote installé `truenas-csi` v1.0.3. Le csi-resizer v2 ne pouvait pas lire les Pods : RBAC corrigé par `install-truenas-csi-nfs.sh --apply`. PVC RWX écrit sur taloswk01 et relu sur taloswk02 : `TESTED`. Restent le reclaim ZFS (suppression des namespaces de smoke), la NetworkPolicy et `auth.login_with_api_key`, retiré dans TrueNAS 28. Cluster arrêté depuis ; taloscp01 avait pris l'IP publique du WAN du 14 au 15/11 ([incident](incidents/2026-11-14-talos-control-plane-public-wan-lease.md)).
2. **H02 — Sauvegardes PostgreSQL** : rotation privée de `postgres_exporter`, sauvegarde TLS `verify-full` avec SHA-256, restauration Docker isolée sans réseau et comparaison des données ; activer la planification seulement après restauration prouvée. [Runbook G1](runbooks/postgres-g1-restore-and-secret-rotation.md).
3. **H04 — Cloudflare / sécurité WAN** : contrôler DNS publics, routes Tunnel, Access et Service Auth, refus de `/realms/master`, absence d'exposition des services privés ; `s3.int` uniquement après plan et approbation explicite. [IaC Cloudflare](../terraform/cloudflare/README.md).
4. **H05 — Gatus / Prometheus** : comparer `app.query`, Gatus, scrapes `up`, `entityRef` et `catalogRevision`, avec preuve horodatée ; `NOT_RUN`/`DENIED` ne signifient pas `DOWN`. [Runbook sondes](runbooks/2026-11-04-probe-remediation.md).
5. **H12 — OpenRAG / Docling / LiteLLM** : vérifier ingestion, embeddings via GPU workstation (LiteLLM TrueNAS proxy), clés applicatives et isolation du corpus privé ; tests de refus sans clé maître. [Runbook OpenRAG](runbooks/openrag-babou-ingestion-diagnostics.md).
   - **Capacité IA (17/11)**. Mesures : TrueNAS a 62 Gio, mais 5,5 Gio disponibles (ARC à 6,4 Gio), 16 threads et aucun GPU passé à Ollama ; la workstation a 62 Gio (38 disponibles), une RTX 2060 de 6 Go et 447 Go libres sur `/data`. **CODED** : l'Ollama de TrueNAS devient un repli CPU (`mem_limit: 6g`, `OLLAMA_KEEP_ALIVE=30m`, 2 modèles chargés, contexte 8k) ; LiteLLM ajoute `qwen-cpu` (`qwen3.5:4b` sur TrueNAS), vers lequel se replient `qwen`, `qwen-think` et `rr-json` quand la workstation est éteinte, et `auto` (`complexity_router` de LiteLLM, local, sans appel externe) : questions courtes vers `qwen`, code et raisonnement vers `qwen-think`. Vérifié dans un LiteLLM jetable (1.104.2, réponses simulées) : routage par complexité et repli, workstation coupée. TrueNAS tourne en 1.109.1. **NOT_RUN** : `ollama pull qwen3.5:4b` dans l'App `ollama`, redéploiement d'`ollama` puis de `litellm`, ajout de `qwen-cpu` et `auto` aux clés virtuelles (`/key/update`, `enforce_fallback_model_access`). Reste à décider : un palier payant dans `auto`, et le gros modèle MoE (`qwen3.5:35b-a3b`, 22 Go) sur la workstation avec les experts en RAM (proposition n° 8 d'ansible-workstation `docs/gpu-llm-workstation.md`).
6. **H13 — DefectDojo** : durcir l'import privé (RBAC de l'importeur, import asynchrone, déduplication) et prouver l'absence d'exposition WAN. [Runbook](defectdojo-private-scan-ingestion.md).
7. **H16 — Vault PKI / OAuth / OIDC** : pilote de PKI et de fédération PostgreSQL/Keycloak/FastAPI avec break-glass, révocation et tests RBAC négatifs ; aucune migration d'identité globale sans recette. [Plan sécurité](security/postgresql-fips-tls13-vault-oauth-20261110.md).

**Pilote H16 / Entra ID Free (P0, non déployé)** : [module OpenTofu AzureAD avec état Azure Blob verrouillable](../terraform/entra-id-lab/README.md), [workflow GitHub OIDC](../.github/workflows/entra-id-lab.yml) et [threat model/YubiKey/runbook](security/entra-id-homelab-lab.md). Plus de seconde source d’état Garage ; groupes désactivés pour la CI afin d’éviter les permissions Graph tenant-wide. Utilisateur de test créé seulement par apply local, avec mot de passe initial Vaultwarden à usage unique, et lockfile du provider commité ([guide tenant + utilisateur](runbooks/entra-id-lab-tenant-and-test-user.md)) ; création du tenant et apply NOT_RUN. Apply manuel verrouillé par défaut : environnement GitHub, identité, backend, lockfile et approbation à configurer. CODED / TESTED NOT_RUN / DEPLOYED NOT_APPLIED / ACCEPTED NOT_VERIFIED. Ordre H01 → H02 → H04 → H05 → H12 → H13 → H16 inchangé.

**Mode d'exécution** : réutiliser une PR active lorsqu'elle couvre réellement le chantier ; sinon une PR Draft ciblée. Sur chaque chantier : (a) inventaire des prérequis et diff, (b) tests locaux sur SHA exact, (c) contrôle de sécurité négatif, (d) preuve runtime datée distincte. Les tests hors LAN ne valent pas réception. Les indisponibilités réversibles sont acceptées ; aucune destruction de données ni ouverture WAN implicite.


## Règles de suivi

- `CODED` : code présent dans Git ; `TESTED` : contrat local exécuté sur un SHA identifié ; `ACCEPTED (runtime)` : mesure fonctionnelle datée du service cible ; `NOT_VERIFIED` : preuve absente. Ne jamais déduire le dernier état du premier.
- Le catalogue `x-nabla` est l'autorité des identités ; `entityRef` et `catalogRevision` assurent le rapprochement entre Compose, FastAPI et sites. Les chemins `/mnt/cpool` et les secrets privés restent hors du dépôt.
- L'observation Cloudflare `DENIED`/`challenge`, un diagnostic non exécuté, ou une absence de télémétrie ne deviennent pas des services DOWN.
- Avant chaque mutation : identifier le risque de perte de données, les dépendances et une restauration proportionnée. **L'opérateur accepte la coupure de service et les redémarrages réversibles pour expérimenter ; pas d'accord supplémentaire pour la disponibilité.** Toute opération irréversible, destruction de données ou exposition non prévue exige une autorisation spécifique. La quality gate locale s'exécute sans CI payante.

## Vue inter-dépôts — choix des prochains chantiers (13 novembre 2026)

**[Portefeuille unique H01–H19](roadmap-portfolio.md)**. Les groupes G1–G7 antérieurs sont conservés dans [l'archive datée](archive/2026-11-13-roadmap-before-compaction.md), et non comme seconde source de priorités. **Ordre validé le 14/11 : H01 → H02 → H04 → H05 → H12 → H13 → H16.**

### Responsabilités canoniques (ne pas dupliquer les checklists)

- **Compose** : réseau, sécurité edge, TrueNAS/Talos/pfSense, catalogue infra, secrets, Gatus et Prometheus ; scripts opérateur sous [scripts/README.md](../scripts/README.md).
- **[FastAPI engineering](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md)** : API, collecte et preuve exposée, cache, front FastAPI Cloud, qualité et budget Nano ; aucune réimplémentation dans Compose.
- **[Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/quality-roadmap.md)** : SSR/SSG, sécurité Vercel, a11y et [interfaces homelab Next.js](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/homelab-roadmap.md).
- **[Site Bababou](https://github.com/AlbanAndrieu/nabla-site-bababou/blob/master/docs/roadmap.md)** : pages, preuves documentaires, NRE, contrôle de diffusion ; [#270](https://github.com/AlbanAndrieu/nabla-site-bababou/pull/270) encore Draft.
- **[OpenClaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md)** : Gateway, heartbeat et FinOps Vercel ; intégration Compose limitée au runtime et à l’observabilité, le code de collecte appartient à OpenClaw.

**Politique de nettoyage :** les migrations OpenClaw/YubiKey déjà réceptionnées ne sont pas rouvertes ; conserver les wrappers de rollback qui ont encore des consommateurs. Déplacer une procédure datée en archive uniquement après mise à jour de ses références et des tests de contrat. Les documents historiques ne réintroduisent pas de tâches clôturées.

## Suivi consolidé — état du code et réception (8 novembre 2026)

Le tableau de déploiements/sondes/versions **daté du 8–13 novembre** est [archivé intégralement](archive/2026-11-13-roadmap-before-compaction.md) : ne pas le confondre avec la situation runtime actuelle. Pour l'état `CODED` vs `ACCEPTED (runtime)`, consulter [H01–H19](roadmap-portfolio.md).

## P0 — Réception du catalogue et des sondes (PR #326)

- **H05** : fraîcheur des résultats Gatus, jobs Prometheus, contrôle direct, `app.query`, `entityRef` et `catalogRevision` ; respecter `NOT_RUN`/`DENIED`/`planned`. [Runbook](runbooks/2026-11-04-probe-remediation.md).
- **H17** : [#365 Compose](https://github.com/AlbanAndrieu/nabla-compose/pull/365) fusionnée, [#424 FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/pull/424) et [#432 FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/pull/432) fusionnées ; réception runtime et migration Site Alban en attente avant suppression de l'inventaire legacy. [Contrat](service-catalog-v2-normalization.md).
- **H03/H08** : matérialisation Homarr/secret `0600`, puis NetBox, Dependency-Track, Joplin. [Secrets](runbooks/2026-11-10-secrets-migration-backlog.md) et [Apps](runbooks/2026-11-06-catalog-apps-to-compose.md).
- Anciennes instructions Kibana/Graylog/AIStor et Apps déjà déployées : [archive du 13/11](archive/2026-11-13-roadmap-before-compaction.md), **ne pas relancer**.
- **Diagnostic des états du 16/11 00:41 CET** (lecture seule ; sources : Sample TrueNAS et Cloud, `app.query`, Gatus, Prometheus, DNS et HTTP). 100 cartes sur 147 sont cohérentes, et aucune carte `ok` ne correspond à une App arrêtée. Ce qui revient à nabla-compose, par priorité :
  - **Sécurité** : l'ingress `joplin` vers :22300 n'a aucune App derrière lui et son application Access est en « Everyone bypass ». Tout service qui se lierait à ce port deviendrait public sans authentification.
  - **Panne** : Uptime Kuma n'a ni App ni données (`custom-apps.yml` la déclare `running` ; `autokuma` et Gatus sont en échec). 16/11 : aucune donnée à retrouver (ni dataset, ni volume, ni `kuma.db`), l'App n'a jamais été déployée. Décision à prendre : la déployer, ou la passer en `planned` avec `autokuma` (Q3 de la [passe du 16/11](runbooks/2026-11-16-roadmap-pass-blockers.md)).
  - **Cloudflare** :
    - Error 1050 (Default-Deny, aucune application Access) sur `freshrss`, `immich`, `ha`, `affine`, `adguardhome` et 13 noms `*-albandrieu`.
    - L'application Access `motion-albandrieu` est déclarée sur un domaine mal orthographié.
    - Un doublon `nexus` n'a aucune policy.
    - Ingress orphelins : `keycloak` et `drawio` ; `ddns-updater` vise :8000 au lieu de :30007.
    - Le token Cloudflare de FastAPI Cloud renvoie `AuthenticationError`, ce qui produit 23 `warn`.
  - **Catalogue** (**CODED 16/11**, [passe du 16/11](runbooks/2026-11-16-roadmap-pass-blockers.md)) :
    - [x] `runtime.appId` ajouté à redis, nginx, dockhand, dozzle, drawio, ddns-updater et openhands, et `x-nabla.runtime` aux descripteurs statiques adguardhome, ittools, stirling, postgresql et openclaw.
    - [ ] `homeassistant` garde l'identité `homeassistant` de sa future Custom App (contrat H19). Tant que la migration n'est pas faite, Sample ne peut pas le relier à l'App native `home-assistant`. lidarr reste sans `appId` : le contrat de la pile média `planned` l'interdit.
    - [x] Entités créées : `immich` et `glances` (actives), `emby`, `memos` et `tailscale` (`disabled`). BIA provisoire, à relire.
    - [x] Les 9 entités non déployées passent en `planned`.
    - [x] `plumber` passe en `active` : son App tourne depuis au moins 3 jours.
    - [x] `languagetool` sonde `/v2/languages`.
    - [ ] `openclaw` : la gateway n'écoute qu'en boucle locale, la route LAN :30325 ne peut pas répondre (Q5).
    - [ ] Réception : Sample doit montrer `redis` sans `binding_conflict` et les Apps arrêtées sans `declared_only`, après fusion (catalogue lu sur `master`).
  - **`custom-apps.yml`** (**CODED 16/11**) : bitcoind, docker-socket-proxy, graylog et plumber déclarées ; Apps fantômes et Custom Apps retirées de `catalog_native`. Restent `cartography`, `scorecard`, `uptimekuma` (absentes, Q3 et Q4) et `keycloak` (arrêtée par décision). `--apply` les créerait toutes les quatre en une fois.
  - **Prometheus** : les 13 cibles à `up=0` sont des exporters `planned` jamais déployés (dont OpenSearch :9114 et :9115, `haproxy` :9101), exclus de `NablaExporterTargetDown` depuis e5a4c165. Aucune règle à ajouter : déployer un exporter suppose d'abord de passer son job en `active`.
  - **pfSense** : le WAN `*.int` renvoie 503 depuis Cloud, à diagnostiquer par script versionné.
  - La logique d'état côté Sample est suivie dans fastapi-sample (F14).

## P0 — Keycloak, Home Assistant, PostgreSQL et Apps en attente (#330)

- **H01** : ne pas déplacer Keycloak/Hermes/Vault sur Talos sans preuve CSI RWX, reclaim et NetworkPolicy. [Préflight CSI](kubernetes-csi-preflight.md).
- **H02** : `postgresbackup` dump signé par SHA-256 puis **restore isolé** avant d'activer le cron. [Runbook sauvegarde](runbooks/production-app-operations.md).
- **H19** : migration de Home Assistant vers une App Compose, recorder sur PostgreSQL et rollback prouvés. [Runbook Apps](runbooks/2026-11-06-catalog-apps-to-compose.md).
- **H08** : NetBox, Dependency-Track, Joplin, `rollout-pending-apps.sh --check` et un seul `--apply` à la fois après la séquence P0.
  - 16/11 : `rollout-pending-apps.sh --check` donne READY pour netbox, dependency-track et joplin (Apps absentes), ainsi que plumber, scanopy et ntopng (redéploiement). 0 bloqué, 0 mutation. Un `--apply` à la fois, sur accord de l'opérateur.
- L'ancien ordre de déploiement et le retrait de Databasus restent dans [l'archive](archive/2026-11-13-roadmap-before-compaction.md), sans autoriser de suppression de données.

## P0 — Cloudflare, secrets et frontières d'accès

1. **Cloudflare Tunnel / Access** (10/11 : `fastapi-sample.albandrieu.com` n'a **aucun** enregistrement DNS — le code bascule déclaration, catalogue, scripts et sondes, mais rien n'est servi tant que le plan suivant n'est pas appliqué ; l'ancien nom reste servi derrière Access) : valider le plan OpenTofu de retrait des routes `external=false`, le renommage public FastAPI Sample, et la précédence du refus `/realms/master` avant les routes Keycloak publiques ; n'appliquer qu'avec approbation et comparaison exacte des effets. Aucune exception WAF/Bot pour Keycloak/LiteLLM ; l'observateur TrueNAS fournit la preuve LAN. [Module IaC](../terraform/cloudflare/README.md). Inclut les sept noms média publics observés le 7/11 (`radarr`, `sonarr`, `prowlarr`, `lidarr`, `transmission`, `sabnzbd`, `emby` : `403` Cloudflare sans Access, [§2.3](arr-media-library-roadmap.md)). **10/11** : apply OpenTofu (2 ajouts dont l'application Access `postgres`, 4 modifications, 0 suppression, re-plan vide) avec le jeton dédié `nabla-opentofu` géré par l'unité `cloudflaretokens` (état chiffré) ; puis applications en contournement `keycloakoidc` (`/realms/nabla`, `/resources` seulement) et `joplin`. `fastapi-sample` et `postgres` répondent 302 Access ; `/realms/master`, `/admin` et la racine Keycloak restent refusés au bord (403). Phase `retire` du DNS appliquée le 10/11 : 26 CNAME détruits (sept noms média, kibana et 18 routes retirées du Tunnel), NXDOMAIN au serveur autoritaire, re-plan vide. Restent deux enregistrements publics `hello` et `s3` sous `.int.albandrieu.com` signalés par le contrôle `no_public_private_namespace_records` ; 12/11 : `hello` est le canari approuvé (`config/public-int-dns-exceptions.txt`), `s3` part au troisième tour de retrait (plan d'adoption : 1 import, apply en attente d'accord, Q16).
2. **Service Auth observateur** : aligner les politiques des applications concernées sans `Bypass` général ; protéger le coffre web et `/admin` Vaultwarden en limitant les exceptions aux chemins clients. Recetter depuis un client externe avant retrait d'une ancienne politique.
3. **Secrets** : prouver la concordance Vaultwarden → fichier canonique 0600 → environnement conteneur, sans afficher de valeur. Une ancienne session `BW_SESSION` exposée ne doit jamais être réutilisée. [Roadmap secrets](secrets-migration-roadmap.md). **10/11** : bichon, clickhouse, graylog, langflow, mongo, nexus, ollama, pihole, redis et sentry-clickhouse déclarés dans le manifeste ; leurs copies runtime sont identiques aux anciens fichiers `/mnt/cpool/<service>/` encore lus par le Compose (contrôle par empreinte), importés dans Vaultwarden le 10/11 (parité vérifiée) ; bascule vers les chemins canoniques **CODED le 12/11** pour neuf d'entre eux (`env_file` obligatoire sur `/mnt/cpool/secrets/runtime/<app>/`), redéploiement un par un à faire ; Redis reste sur son `.env`, son mot de passe étant interpolé dans `command:` (Q18). Redis, MinIO et Open WebUI refusent désormais de démarrer sans leur mot de passe au lieu d'utiliser une valeur publique (aucun conteneur ne l'utilisait). **Wazuh : rotation APPLIED le 12/11** : `rotate-wazuh-internal-users.sh --apply` a chargé dans l'index de sécurité les hashes de `admin` et `kibanaserver` (mots de passe de `nabla/prod/wazuh`, différents des valeurs d'exemple), puis redéploiement. Le manager parle à l'indexer en TLS 1.3 sans 401 (114 refus entre 21:35 et la rotation). Aucune route Tunnel publique.
4. **OVH / FastAPI Cloud** : vérifier la nouvelle identité de lecture seule et les scopes ; `pfSense` y reste `transport_only` (contrat accepté) et la sonde Tavily `GET /usage` ne nécessite plus de migration. Au 6/11, FastAPI Cloud répond mais reste `degraded` : le contrôle `openstack_me` échoue (identifiant OVH « does not exist »). **10/11** : `livez`, `readyz` et `healthz` sains.
5. **Suites edge du diagnostic du 16/11** (passe du 16/11, workstation, sondes LAN en lecture seule). Tout est **CODED, plan et apply NOT_RUN** : le plan en lecture seule n'a pas pu tourner, faute des clés S3 de l'état Garage (absentes de `nabla/prod/infrastructure-bootstrap`, qui ne porte que `GARAGE_ADMIN_TOKEN` et `TRUENAS_INFRA_API_KEY`). Réception : plan `adopt` relu, apply approuvé, puis plan `retire` ; tests externes négatifs.
   - **joplin et keycloak** : leurs applications Access sont en « Everyone bypass » et rien n'écoute derrière (:22300, :30238). Leurs routes Tunnel répondent `http_status:404` jusqu'au déploiement (H08 Joplin, H01 Keycloak), dont la PR rétablit l'origine. Contrats : `test_bypassed_joplin_route_is_refused_until_its_app_runs`, `test_master_realm_is_refused_before_production_paths`.
   - **Error 1050** : applications Access `immich` et `ha` ajoutées (politique `nabla` et jeton moniteur, comme `affine`). `freshrss` et `affine` ont déjà la leur dans le module, jamais appliquée. `adguardhome` a un CNAME connu (`dns_tunnel_record_ids`) mais aucune route : à classer au plan (`orphan-tunnel` → `retired_hostnames`). `affine` est passée `planned` (aucune App, PR #399) : route orpheline derrière `nabla`, à décider.
   - **Tunnel workstation** : 12 des 13 routes `*-albandrieu` retirées (aucune application Access, refus 1050 partout). `famp-albandrieu` reste, la branche honeypot lui ajoute son application Access. Les 11 CNAME publiés passent au 4ᵉ tour de retrait (`dns-policy.yaml`). Le catalogue référence encore `anythingllm`, `plumber`, `portracker` et `stirling` en `*-albandrieu` : URL à corriger côté catalogue (signalé à la passe PR #399).
   - `motion-albandrieu` (domaine mal orthographié) et le doublon `nexus` sans policy restent des applications Access du tableau de bord, hors module, désormais sans route : les importer puis les supprimer par plan, pas de clic GUI.
   - **Sentry et LiteLLM LAN seulement** (décision de l'opérateur, soir du 16/11). Sentry : route Tunnel `sentry.albandrieu.com` retirée, CNAME au 5ᵉ tour de retrait, UI servie par Traefik en `https://sentry.int.albandrieu.com` (`SENTRY_SYSTEM_URL_PREFIX`, `CSRF_TRUSTED_ORIGINS`), audit `audit-app-lifecycle.sh` qui exige que le nom public ne réponde plus : **CODED**, plan, apply et redéploiement de l'App **NOT_RUN**. LiteLLM n'a plus ni route ni DNS depuis le 05/11 (NXDOMAIN le 16/11) ; FastAPI le classe encore « At risk » à cause de son application Access orpheline.
   - **6ᵉ tour (17/11, décision de l'opérateur)** : routes Tunnel `traefik`, `drawio`, `pihole` et `autoxpose` retirées, CNAME au 6ᵉ tour de retrait ; ces services restent sur le LAN. `immich` et `nexus` gardent leur route publique derrière Access : leur catalogue passe en `visibility: public` avec `access.required` (`nexus` aussi `external: true` dans `homelab-services.json`). **CODED**, plan, apply et tour DNS **NOT_RUN**. Réception : ces six lignes absentes de `health=at-risk` (immich y reste tant que son application Access n'est pas appliquée).
   - **Applications Access orphelines** (aucune route Tunnel, relevé FastAPI du 16/11 19:35 UTC) : `litellm`, `sentry`, `traefik`, `drawio`, `pihole` et `autoxpose` (ces cinq après l'apply), `bichon`, `clamav`, `garage-admin`, `kibana`, `test`, plus `motion-albandrieu` et `nexus` ci-dessus. À importer puis supprimer par plan, comme le tour DNS : relever d'abord leurs identifiants avec le jeton de lecture Access (aucun identifiant n'est exposé par FastAPI). Garder `manager` (route HAProxy WAN), `int` (`*.int`, garde-fou) et les applications système. Réception : `/api?operator=1&ui_full=1&health=at-risk` sans ces lignes.
   - `ddns-updater` : ni :8000 ni :30007 n'écoutent le 16/11 ; vérifier l'App avant de changer le port.
   - Jeton Cloudflare de FastAPI Cloud (`AuthenticationError`, 23 `warn`) : rotation par l'opérateur, sans afficher la valeur.

**Clôture** : règles Access du moindre privilège et sondes de bord expurgées, sans régression du DNS ni création d'une exposition WAN.

## P0 — Accepter les services critiques

- **TrueNAS 27** : hôte passé de 26.0.0-BETA.3 à 27.0.0-RC.1 les 5–6/11 (TrueNAS 26 renommé 27 ; API REST supprimée, aucun client du dépôt ne l'utilise). Contrôles post-upgrade encore à exécuter **sur l'hôte TrueNAS via SSH** : `midclt call system.version`, `just talos-stopped-vms-check`, `just truenas-readiness-check`, `just truenas-fastapi-check`, MCP `truenas-readonly`, données TrueNAS de portracker, provision/bind d'un PVC CSI, 2FA. Conserver l'environnement de boot précédent tant qu'ils ne passent pas. [Upgrade coupling](truenas-operator-tools.md#upgrade-coupling).
  - 16/11, en SSH sur le checkout `c97eaadf` : `system.version` = `TrueNAS-27.0.0-RC.1`. `diagnose-service-readiness.py --check --strict` : 6 HEALTHY, 2 WARN, rien de dégradé. Gatus a un moniteur en échec, Uptime Kuma, jamais déployée. Sample n'atteste pas son SHA (`build_revision` absent). `diagnose-fastapi-integrations.py` en `warning`, sans échec critique une fois lancé avec sudo ; la recette `just truenas-fastapi-check` passe donc par `sudo -n`. Les trois VMs Talos sont `STOPPED`, autostart désactivé. Restent : MCP `truenas-readonly` (connexion fermée côté poste), portracker, PVC CSI au redémarrage de Talos, 2FA.
- TrueNAS : prouver la disponibilité réelle (et non le seul état du conteneur), les ACL NFS, les secrets et les dépendances Postgres/ClickHouse.
- **FastAPI Sample** : base `fastapisample` en `verify-full` (TLS 1.3), `healthy` le 13/11 ; ses erreurs arrivent dans Sentry (événement de test `083754a9`, issue 3), lisibles par le MCP Sentry de nabla-compose. Démarrage de 3 min 40 (trois pauses d'environ 1 min avant Unleash, Logfire et Sentry) à corriger dans fastapi-sample. [Diagnostic TrueNAS](runbooks/fastapi-sample-truenas-diagnostics.md). FastAPI Cloud `degraded` : voir le point 4 OVH ci-dessus.
- FastAPI Sample : vérifier la parité API/UI et le mode OWNER, les cibles Prometheus, le routeur LiteLLM et la sélection du corpus OpenRAG privé ; test navigateur Chromium uniquement si disponible. [Diagnostic consolidé](runbooks/fastapi-consolidated-diagnostics-20261030.md).
- Talos / Kubernetes : valider le retained smoke `democratic-csi` NFS, les trois nœuds Ready et les politiques NetworkPolicy avant nouveaux workloads. 10/11 : trois nœuds `Ready`, mais `truenas-csi-controller` en `Error` depuis 18 jours, aucun PVC ni NetworkPolicy ([passe du 10/11](runbooks/2026-11-10-roadmap-pass-blockers.md), Q7). [Préflight](kubernetes-csi-preflight.md).
- pfSense / CrowdSec : conserver la preuve que PF charge les règles, puis démontrer le rattachement WAN exact sans bloquer une IP d'administration ; ne pas prendre une ancre chargée pour une preuve de filtrage effectif.
- Authentification et monitoring : réparer les exporters sans confondre un `401` Prometheus avec un `401` OpenClaw ; Gatus/Prometheus sont des preuves indépendantes.

**Clôture** : `ACCEPTED (runtime)` sur le SHA déployé, avec date, source et un test négatif pour chaque frontière sensible ; sinon `NOT_VERIFIED`.

### H07 — pfSense : écarts à contrôler (ouverts, non réceptionnés)

- **DNSBL et ASN reporting — CODED, réception NOT_VERIFIED** : `scripts/pfsense/diagnose-recover.sh --check-posture` appelle désormais l'audit de capacité en lecture seule pour mesurer les entrées DNSBL chargées et préparées et vérifier le paramètre ASN reporting, sans imprimer de jeton. Confirmer les mesures sur l'appliance ; un champ absent doit rester `NOT_VERIFIED`.
- **Snort arrêté après OOM ou kill — CODED, réception NOT_VERIFIED** : l'audit ajouté à `--check-posture` examine maintenant le processus WAN (`service.snort`), en plus de la configuration ; un processus absent ne devient plus implicitement sain. Confirmer le nom/config de l'instance installée, son âge et le résultat après rebuild, sans redémarrage automatique en cas de pression mémoire.
- **PHP-FPM — DONE 15/11 17:46** : profil `4/30/1/2/500` (validé le 24/10) appliqué sur `default_clone` (26.03), générateur identique à celui d'octobre, smoke tests DNS et GUI réussis. Il remplace le relevé historique de 7 workers nginx PHP-FPM (environ 280 Mio RSS cumulés). Seuil du check `php_fpm.nginx_workers` **CODED 16/11** : 0 worker au repos (mode ondemand, inactivité 30 s) est `PASS` si le master PHP-FPM tourne, `WARN` sinon ; test comportemental sur `ps` simulé. Réception : relancer `--check-posture` sur l'appliance (NOT_RUN).
- **Critère de réception** : taille DNSBL + ASN reporting prouvés, Snort actif ou explicitement classé en panne avec horodatage, et PHP-FPM **≤ 4 workers** avec paramètres `4/30/1/2/500`, sans nouveaux OOM ; vérifier Unbound, pfREST et accès WebConfigurator après réglage.

Sources : [incident pfSense du 13/11](incidents/2026-11-13-pfsense-unbound-oom-snort-crowdsec.md), [profil PHP-FPM](pfsense-php-fpm-hardening.md) et [plan d'upgrade pfSense](pfsense-upgrade-26-07.md). Ne pas confondre absence de mesure et service sain.

### H07b — pfSense : stabiliser `default_clone`, puis repasser en 26.07 (15/11)

Détail et preuves : [runbook 26.07](runbooks/pfsense-26.07-upgrade.md#stabilisation-du-1511-sur-default_clone).

- [x] **P1 GUI 10443 exposée à Internet** : garde WAN d'octobre restaurée (alias `PFSENSE_ADMIN_WAN`, pass, puis `Block untrusted pfSense GUI/API`, avant l'« Easy Rule »). Chargé dans PF le 15/11 à 18:14. Test depuis Internet NOT_RUN.
- [x] Unbound `All` et Domain Override `int` ; syslog `.57` retiré ; cibles workstation HAProxy/NAT retirées (revenues le 16/11, puis retirées à nouveau ; voir ci-dessous) ; règles `heimdall 443` et `ExternalOffice 7000` désactivées ; 9 réservations DHCP d'octobre restaurées (Talos `.50` à `.52`).
- [x] **Boots ratés de `default_clone` et du 26.07 d'octobre** : générateur PHP-FPM recopié en 600 par `harden-pfsense-php-fpm.sh` (`cp -p` d'un `mktemp`). Script corrigé, environnements réparés par `repair-be-php-generator-mode.sh` (37c39a3b). `default_clone_20261115_stable` est en service depuis le 15/11 19:48 (boot en 47 s), avec les baux DHCP restaurés par `restore-dhcp-staticmaps.php`. Diff complet contre la sauvegarde stabilisée de 18:19 : seuls les 9 baux DHCP diffèrent.
- [x] **Repli** : la cible est le BE le plus ancien non marqué `failed`, `default` (binaires de juin). Il porte la config en service depuis le 15/11 (`sync-fallback-be-config.sh`, révision 20:11) ; resynchroniser après chaque changement.
- [x] `check-drift.sh` étape 4 : diff complet de `config.xml` (`config-drift.py`, `PFSENSE_DRIFT_BASELINE`), qui couvre règles, NAT, alias, HAProxy, VPN, certificats, IPv6 et DNS.
- [x] **pfBlockerNG IP seul** réactivé le 15/11 à 20:36 sur le BE en service (`pfblocker-ip-only.php apply`, puis `updateip` 20:36 → 20:43). Le premier essai de 18:43 avait coupé tout l'IPv4 sortant : le groupe GeoIP Top Spammers contenait FR, et sa règle WAN flottante (`quick`, toutes directions) bloquait notre propre IP WAN. FR est retiré, `--check-posture` signale `pfblockerng_wan_self_block`. Pendant le chargement : WAN et DNS toujours OK, charge max 5,2, 37 Mo libres une fois, pas d'OOM. Le rechargement du filtre de 20:43 a pourtant échoué : pendant un rechargement, l'ancien et le nouveau jeu de tables coexistent, et les listes GeoIP IPv6 (190k entrées) dépassaient la limite pf de 400k. Top Spammers n'était donc pas chargé, et aucun rechargement ne passait. Depuis 21:12, les pays IPv6 sont retirés (le WAN n'a pas d'IPv6 publique) : 8 tables IPv4 (151 093 entrées), toutes chargées. Ni notre IP WAN ni les 15 plages Cloudflare ne sont bloquées. Le `check` signale toute table de `rules.debug` absente de pf. DNSBL reste coupé. Reste à observer : le cron quotidien `pfblockerng.php cron` de 00:00.
- [x] **pflow natif vers Akvorado** rétabli le 15/11 à 21:21 (`reconcile-pflow.php`) : NetFlow v5 domain 1, source LAN, vers `172.17.0.24:2055`, suivi sur toutes les règles. TrueNAS reçoit les paquets, et l'inlet Akvorado compte les flux de 172.17.0.1 sans erreur. `check-drift.sh` rejoue son check.
- [x] **REST API** : identités conformes (`--check-identities`), empreinte de la clé `posture` identique au hash stocké, `system/version` et `dns_resolver/settings` en 200 le 15/11 à 20:0x.
- [ ] **« Easy Rule » WAN** (`pass tcp all`, depuis 2022, présente aussi en octobre) : inventorier ce qui en dépend (HAProxy :443/:7000, NAT), puis la remplacer par des règles par port. SSH 9922 est ouvert sur le WAN (clé seule) ; la règle « Reject SSH » ne bloque que la source WAN.
- [ ] **Exposition WAN par NAT** (vault 8200, nomad 4646, consul 8500, traefik 9002, apps TrueNAS 300xx) : revue avec H04.
- [ ] **HAProxy : backend par défaut vers le honeypot, puis Heimdall refusé** (décision du 16/11). Le honeypot Project Honey Pot quitte l'Apache de la workstation pour l'App TrueNAS `honeypot` ([`apps/honeypot`](../apps/honeypot/compose.yml), `172.17.0.24:31090`, CODED, NOT_DEPLOYED). Seuls `/` et `/honeypot/keywaspish.php` exécutent le script, et chaque exécution signale le visiteur à Project Honey Pot ; `/healthz` est statique.
  1. Déployer l'App (`reconcile-custom-apps.py --apply`), puis vérifier `/healthz` = `ok` et le rendu de `/` depuis le LAN.
  2. **CODED 16/11, décision confirmée par l'opérateur** : [`haproxy-honeypot-default.php`](../scripts/pfsense/haproxy-honeypot-default.php) (`check` puis `apply`) crée le pool `honeypot` (`GET /healthz`, jamais `/`, champs clonés de `prod_back`), le met en backend par défaut de `Web_HTTPS`, `freenas` et `Web_HTTPS-8082` (dont le défaut `nabla-index` est vide) et active `forwardfor` sur ces trois frontends (Apache ne lit `X-Forwarded-For` que depuis `172.17.0.1` ; `freenas` ne l'avait pas). Noms des frontends et des champs relevés en lecture seule sur l'appliance le 16/11. Effet attendu : `apache`, `account` et tout hôte non routé servent le honeypot au lieu du login Heimdall. `check`/`apply` NOT_RUN : l'App doit d'abord tourner (étape 1).
  3. Une fois la bascule vérifiée, refuser Heimdall depuis le WAN : supprimer les règles `use_backend prod_back` (`manager`, `domain_api`, `alert_api`) et abandonner `prod-back-homarr-fallback.php`, jamais appliqué.
  4. `--check-posture` : `haproxy_default_backend=honeypot` **CODED 16/11** (`manage-posture.php`, WARN avec les frontends restants). Reste `haproxy_heimdall_routes=none`, à coder avec l'étape 3.
  5. L'ingress `honeypot-albandrieu` du tunnel workstation a été retiré sur `master` le 16/11 : conserver son retrait et surveiller le volume de signalements après la bascule du backend HAProxy. Si nécessaire, limiter le débit par IP.
- [x] **Service Watchdog** : `audit-posture.sh` est aligné sur la décision du 13/11 (238e1073). Certificats ACME renouvelés jusqu'au 11/02/2027, et `--check-posture` alerte à moins de 14 jours (3d7c663b).
- [ ] **Démarrage à froid du 1100 : LAN et WAN reliés** ([fiche](incidents/2026-11-14-netgate-1100-cold-boot-switch-bridge.md)). Le U-Boot `18.12.3` n'a ni `preboot` ni `switch_disable` (vérifié le 16/11 sans console), et `u-boot-update.sh` ne les ajoute pas, car le U-Boot est déjà « latest ». Le 14/11, `taloscp01` a ainsi reçu l'IP publique de la Freebox. En attendant : `reboot` uniquement, jamais de coupure de courant. Correctif (`u-boot-update.sh -f` ou script d'environnement seul) `NOT_RUN`, reporté par l'opérateur, console série requise.
- [x] **Cibles workstation revenues dans HAProxy** (16/11) : le retour au BE stable du 16/11 à 00:05 avait remis la config d'avant le retrait du 15/11, avec 5 serveurs actifs vers `172.17.0.57` (`albandrieu-apache`, `nabla-index`, `prod_front` sur :8082 ; `nexus` sur :8081, où rien n'écoute ; `vault` sur :8200, qui est en fait minidlna). Depuis 19:31, Apache n'écoute plus que sur `127.0.0.1:8082` (ansible-workstation `ed7938d`, tunnel Cloudflare `famp-albandrieu` seul), d'où 3 backends DOWN. **DEPLOYED** le 16/11 à 20:17-20:18, à la demande de l'opérateur : `retire-workstation-targets.php apply` (5 serveurs inactifs), puis `prune-dead-haproxy-routes.php apply` (13 règles `use_backend`, 24 ACL). Les deux `check` sont convergés, plus aucune référence à `.57` dans `haproxy.cfg`, aucun backend DOWN ; BE de repli resynchronisé (révision 20:18).
  - [ ] DNS : `account.albandrieu.com` et `apache.albandrieu.com` (A vers le WAN, sans proxy) tombent maintenant sur le backend par défaut `prod_back`, comme tout nom inconnu. Supprimer ces enregistrements ou les publier par le tunnel workstation.
- [x] **Restes HAProxy retirés** le 16/11 vers 20:28, à la demande de l'opérateur : `retire-haproxy-leftovers.php apply`, puis `prune-dead-haproxy-routes.php apply`. Pools supprimés : `nexus`, `vault`, `albandrieu-apache` et `clamav-openvas` (avec ses deux règles `use_backend` et l'ACL `clamav`/`openvas`/`suricata`) ; serveurs `lamp` et `famp` retirés de `prod_front` ; frontend public `Web_HTTPS-8082` désactivé. HAProxy n'écoute plus que sur `82.66.4.247:443` et `:7000`, avec 3 backends UP (`prod_back`, `homeassistant`, `freenas`). Les `check` sont convergés et le BE de repli resynchronisé (révision 20:29).
  - [ ] Reste la redirection `login` de `Web_HTTPS` vers `http://albandrieu.albandrieu.com:8082/honeypot/keywaspish.php`, morte (pas de DNS, :8082 fermé) : à remplacer lors de la bascule du backend par défaut vers l'App `honeypot` (voir plus bas).
- [x] **13 CA expirées** (ExpressVPN, importées en 2022, expirées le 01/04/2026, sans clé ni référence, aucun client OpenVPN) : notification nocturne « CA/Certificate entries are expiring ». `remove-unused-cas.php` (`check`/`apply`, test hors ligne) **DEPLOYED** le 16/11 à 20:08 : 25 → 12 CA, `check` convergé, BE de repli `default` resynchronisé (révision 20:08). La notification déjà affichée se ferme dans la GUI. Puis, à la demande de l'opérateur, le script (renommé `remove-unused-cas.php`) retire aussi les émetteurs ACME (`Acmecert:`) inutilisés, que le paquet ACME réimporte au besoin : 7 CA Let's Encrypt R10 à R13 et staging, le 16/11 à 20:28 (12 → 5). Restent YR1, YR2, Root YR et leurs équivalents staging, encore utilisés.
- [ ] **Upgrade 26.07** : boot unique testé le 15/11 à 21:51, après recopie de la config en service dans `default_20260824183037`. `26.07-RELEASE` démarre en 4,5 min et passe la vérification de boot (drapeau `failed` levé). WAN, DNS, HAProxy, Kea et pflow fonctionnent. Deux bloquants avant de le garder :
  1. Deux chargements du jeu de règles au boot ont échoué (21:56 et 21:57, `Cannot allocate memory` sur `bogonsv6`). L'état final n'a pas été établi. Le BE 26.07 a la vraie liste `bogonsv6` (158k entrées), alors que le stable a encore le fichier vide de mars : avec pfBlockerNG, un rechargement dépasse la limite de 400k. Le stable la dépassera aussi à son prochain rafraîchissement des bogons. `pfblocker-ip-only.php` monte la limite à 1M, appliqué sur le stable le 16/11 vers 00:37.
  2. Vers 23:00, l'interface web et SSH ont cessé de répondre (TCP accepté, ni TLS ni bannière), alors que le routage et le DNS marchaient. Retour au BE stable par cycle d'alimentation le 16/11 à 00:05. Cause inconnue sans console : Snort tournait sur 2 interfaces depuis 21:58, piste non vérifiée.

  Le boot réussi avait levé son drapeau `failed`, donc il était devenu la cible du repli du stable. Il en est de nouveau exclu depuis le 16/11 (`exclude-be-from-fallback.sh`, vérifié par `check-drift.sh`). Le repli est `default`, resynchronisé à la révision 00:36. Prochain essai seulement avec le câble console. Les cibles workstation sont déjà retirées dans sa config.
  - [ ] **Retester le 26.07 et son upgrade cette semaine (au plus tard le 22/11)**, console série branchée et master SSH ouvert (`sshp`) :
    1. recopier la config en service dans le BE 26.07 (`sync-fallback-be-config.sh`), puis vérifier `maximumtableentries` à 1M ;
    2. boot unique (`bectl activate -t`), puis `pfblocker-ip-only.php check` (aucun `pf_tables_not_loaded`) et 2 h d'observation (mémoire, Snort, interface, SSH) ;
    3. si le boot tient, tester l'upgrade depuis le stable 26.03 (`prepare-upgrade.sh`, puis `pfSense-upgrade` dans un nouveau BE), avec le même contrôle ;
    4. une fois le 26.07 en service, retirer la ligne `fallback_exclusion` de `check-drift.sh`. Sinon, remettre le stable et noter la cause vue sur la console.
- [x] **Clé USB de réinstallation** : l'image du ticket TAC *Firmware Access* est l'installeur en ligne déjà sur la clé ; pas d'image hors ligne pour le 1100. La réinstallation passe par le WAN branché sur la Freebox (procédure dans le runbook).

## P1 — Performance, stockage et restauration TrueNAS

- Mesurer mémoire/PSI/ARC, OOM, zombies, limites de conteneurs et descripteurs containerd, puis appliquer les limites mesurées à partir du pic cgroup `memory.peak` (4/11 : nexus 1,9 Gio, opensearch-security 1,8, docling 1,5, kafka 1,2, keycloak 0,9, litellm 0,7). L'arrêt de certains services par décision opérateur n'est pas une réparation définitive. 13/11 : 61 Gio, conteneurs ~35 Gio, ARC 11,7 Gio (plancher 1,9), PSI mémoire < 1 % ; Sentry et sa ClickHouse (~5,9 Gio, 18 conteneurs) repassent `running` par décision opérateur ; `bitcoind` plafonne à sa limite (1,36/1,5 Gio, CPU 100 % en synchronisation initiale). 15/11 : `TrueNASHostOutOfMemory` actif à 6 % de `MemAvailable`, mais PSI mémoire 0,2 %, aucun OOM sur 7 jours, ARC 11,3 Gio récupérable jusqu'à 1,9 : fausse alerte, les deux règles mémoire comptent désormais l'ARC au-dessus de `c_min` (**DEPLOYED** le 16/11 à 12:54 : Prometheus n'avait pas rechargé ses règles depuis le 13/11 23:00, voir ci-dessous). Le vrai goulot est l'IO : PSI IO `full` 33 % sur 5 min, entre 4 et 26 % par jour depuis le 1/11, latence de lecture HDD 33 ms ; Sample a mis ~6 min à démarrer lors de sa mise à jour de 19:40 UTC. Restent, après la pause de `bitcoind`, ~170 écritures/s (ntopng ~400 petites écritures logiques/s, ClickHouse). Alertes ajoutées le 15/11 : `TrueNASHostIOPressureHigh` (PSI IO `full` > 30 % pendant 30 min) et `TrueNASZpoolNotOnline` ; `PiHoleAdsBlockedTooLow` (toujours active, `rate()` sur une jauge) et `PiHoleQueryCountHigh` (jamais active) corrigées. Les échecs Slack d'Alertmanager du 14/11 17h au 15/11 17h UTC venaient de la panne DNS/WAN de pfSense, pas d'Alertmanager : aucune alerte ne peut sortir quand le WAN tombe.
- Après le reboot de la mise à niveau 27 : vérifier avec `diagnose-performance.sh` que le thread noyau de l'ancienne JVM `wazuh-indexer` a disparu, que les zombies restants sont purgés et que l'ARC remonte ; confirmer le redéploiement `deploy-wazuh.sh` du 4/11 (non vérifié). 16/11 01:47 (`--quick`, uptime 3 jours) : PSI IO `full` 7 % sur 5 min (33 % le 15/11), PSI mémoire nulle, ARC 9,5 Gio, 5,7 Gio disponibles, pools sains ; la partie Docker demande `--full` avec `sudo`.
- **Surveillance du 16/11, 01:15 → 09:15** (lecture seule, contrôle horaire, `diagnose-recover.sh --check` toutes les 2 h : 4 passages propres, 220-252 s). pfSense et TrueNAS stables, aucun OOM, aucune fuite mémoire.
  - [x] **Prometheus ne relisait pas ses règles** : le cron fait avancer le checkout, mais rien n'envoyait SIGHUP. `PiHoleAdsBlockedTooLow` restait active depuis le 13/11 (ancienne règle en `rate()`), et `TrueNASHostOomKill`, `TrueNASHostIOPressureHigh` et `WorkstationHost` étaient inactives. `reload-prometheus-rules.sh` (`check`/`apply`, promtool avant le signal, test hors ligne) est appelé par `cron.sh` quand `apps/prometheus` change (cba8016b). Appliqué le 16/11 à 12:54, `check` convergé. `TrueNASHostIOPressureHigh` aurait sonné le 15/11 de 15:32 à 18:47 (PSI IO `full` ≥ 30 %).
  - [ ] **Pic d'IO TrueNAS chaque nuit vers 04h** (charge jusqu'à 9,6, sda à sdd occupés à 31-34 %, lectures aléatoires de 3 Mo/s, sous le seuil d'alerte) : candidat principal, la tâche de snapshot de 04:00 sur `cpool/backup/gdrive/officiel` (conservation 1 an). Classement des processus par IO prévu le 17/11 à 03:58.
  - [ ] **Marge RAM du Netgate 1100** : libre entre 224 et 270 Mo toute la nuit, ARC à 31-39 Mo, mais `arc_max` vaut 602 Mo sur 1 Go sans swap. Mesure de la mise à jour pfBlockerNG de 00:00 prévue le 16/11 ; un script `check`/`apply` qui plafonne l'ARC à 128 Mo seulement si le libre passe sous 100 Mo. `php_pfb filterlog` (62 Mo) ne sert qu'aux rapports pfBlockerNG : à couper si la mesure le justifie.
  - [ ] Un onglet du tableau de bord pfSense resté ouvert dans Chrome était le seul client de :10443 de la nuit et gardait PHP-FPM à 2-3 % de CPU : le fermer, ou espacer le rafraîchissement.
  - Les 13 cibles Prometheus down sont des exporters `operational_state=planned`, exclus exprès par `NablaExporterTargetDown` : pas d'alerte `TargetDown` à ajouter.
- Zombies : `init: true` (4/11, sur master le 9/11) **effectif le 10/11** sur 9 Apps redéployées une par une (bichon, clickhouse, kafka, minio, mongo, ollama, openwebui, sentry-clickhouse, suricata) : 306 zombies → 3, dont 267 sous la JVM kafka ([preuve](incidents/2026-11-10-truenas-docker-orphan-volumes-purge.md)). Restent drawio (App STOPPED, `init` au prochain démarrage), `kafka-exporter` (`init` ajouté le 10/11, effectif au prochain redéploiement de `kafka`) et `reactive-resume` (App catalogue) non versionné. 16/11 : 17 zombies, tous sous scanopy (13), litellm (2) et ntopng (2) ; `init: true` **CODED** sur ces quatre services, effectif à leur redéploiement (Q9 de la [passe du 16/11](runbooks/2026-11-16-roadmap-pass-blockers.md)).
- Réconcilier le proxy Docker Socket versionné avec les consommateurs avant de retirer l'ancien réseau `intranet` ; `POST=0` doit rester la valeur par défaut. Choisir explicitement le sort de Doco-CD.
- Appliquer les tâches ZFS de rétention **après `--plan`**, vérifier par dataset les snapshots, puis tester une restauration hors du TrueNAS. Ne jamais effectuer `docker volume prune` ou un nettoyage global de snapshots. 16/11 `--plan` : il manque une seule tâche, la mensuelle de `cpool/bitcoind` (Q7). 5 datasets de la politique sont absents, car leurs Apps ne sont pas déployées (ddns-updater, neo4j, opencre, recyclarr, uptimekuma). 0 dérive.
- Prendre en compte la mémoire du `wazuh-indexer` et la politique de rétention des bases selon le dernier audit read-only. Volumes Docker orphelins : **purgés le 10/11** ([preuve](incidents/2026-11-10-truenas-docker-orphan-volumes-purge.md)), 760 volumes dont 725 dangling → 100 dont 65 ; 660 `candidate:*` supprimés (~853 Mo, 0 échec), `app.query` 1,2 s → 0,3 s. Reste à décider volume par volume : 41 `review:recent`, 8 `review:unsized`, 2 `review:large` (195 et 122 Mo), 2 `nabla-compose_*` et 2 nouveaux `candidate:anonymous` ; relancer [`reconcile-docker-orphan-volumes.sh`](../scripts/truenas/reconcile-docker-orphan-volumes.sh) `--plan` (`just docker-orphan-volumes-plan`) car la dérive reprend (+67 dangling entre le 4/11 et le 10/11). 16/11 `--plan` : 59 `candidate:anonymous` (48,6 Mo, Q8), 33 `review:recent`, 8 `review:unsized`, 2 `review:large` (les mêmes 195 et 122 Mo) et 2 `review:foreign-project`.
- [`bitcoind`](../apps/bitcoind/README.md) : **Custom App déployée le 12/11** (App catalogue et ses `ix-volumes` de 885 Go supprimés, `cpool/bitcoind` créé, nœud `healthy` en synchronisation initiale). 13/11 : partage NFS 17 et montage `/media/bitcoin` de la workstation retirés (aussi dans ansible-workstation, PR #24), `cpool/bitcoin` (712 Go) encore présent, car l'appel `pool.dataset.delete` est resté bloqué sans créer de job (runbook du 10/11, section 8) ; reprendre hors charge la purge du cache de build Docker (~10 Go) ; décider la consolidation des moteurs de recherche (2 OpenSearch + indexer Wazuh). **15/11 20:57 CET : App arrêtée** (décision opérateur, `NABLA_OPTIONAL_APPS_FILE=<liste réduite à bitcoind> restore-optional-apps.sh --stop`, journal `/mnt/cpool/var/nabla/ops-logs/bitcoind-pause-20261115T195700Z.log`). Synchronisation initiale à 67 % (bloc 833 613, ~6 blocs/min) : limitée par les lectures aléatoires du chainstate sur les HDD avec `dbcache=300`, il restait ~2 semaines. Effet de la pause : PSI IO `full` 33 % → ~15 %, lectures disque 108 → 59/s et 4,3 → 0,3 Mio/s, latence de lecture 33 → 17 ms. À décider avant `--start` : reprise de nuit ou `dbcache` relevé (~4 Gio, `mem_limit` à 5 Gio) le temps de la synchronisation. **Fenêtre nocturne CODED** (`reconcile-night-window-cron.py`, 01:00-07:00 du lundi au samedi) : après fusion et mise à jour du checkout, lancer `--check` puis `sudo ... --apply` sur TrueNAS ; au rythme du 15/11 (~2 000 blocs par nuit), la synchronisation (~140 000 blocs restants) durerait plus de 2 mois sans `dbcache` relevé ni pool NVMe. 16/11 : la fenêtre couvre aussi clamav, cleanuparr, domain-watchdog, freshrss, lidarr, netdata, open-speed-test, paperless-ai, paperless-ngx, speedtest-tracker, three-proxy, tracearr, wizarr et zabbix (décision opérateur). La liste vient du catalogue : label Backstage `albandrieu.com/operational-schedule: night` (entités créées pour cleanuparr, netdata, three-proxy, tracearr, wizarr et zabbix, BIA provisoire, icône générique ; `speedtest` porte `x-nabla.runtime.appId: speedtest-tracker`) ; `night-window-apps.txt` est supprimé et les tâches cron appellent `reconcile-night-window-cron.py --start|--stop`. Statut violet `scheduled` hors fenêtre dans FastAPI Sample et Site Alban : CODED dans leurs dépôts. n8n et Scrutiny restent 24/7 (sondés, OpenClaw appelle n8n) ; Graylog et Kasm restent arrêtés. À reprendre : la tâche cron TrueNAS manuelle `clamav-scan` (06:00 le 1er du mois) est coupée par l'arrêt de 07:00 et échoue quand le 1er tombe un dimanche ; le MCP FreshRSS et les audits FreshRSS ne répondent plus en journée. 16/11 : `clamav-scan` appartient à ansible-workstation (`truenas-stabilize.yml`). Ses journaux du 1/09 et du 1/11 s'arrêtent après quelques secondes, sans résumé : le scan mensuel ne va pas au bout depuis au moins septembre (Q6). Les tests SMART longs de 02:00 (les 7, 14, 21 et 28) tombent aussi dans la fenêtre. Les tâches cron de la fenêtre ne sont pas créées (Q2) ; le plan de redéploiement du checkout `64f5c767` donne clamav puis prometheus (Q1).
- **Pool NVMe « fastpool »** (déjà prévu sur la page TrueNAS de Site Alban : 2 × WD Red SN700 1 To en miroir) : confirmé par la mesure du 15/11. Lectures servies à 99,8 % par l'ARC, il reste les écritures et les lectures aléatoires de bitcoind ; ni L2ARC ni RAM ne les corrigent. La carte B650I EDGE a 2 slots M.2 PCIe 4.0 x4 libres (2280/2260, l'un relié au CPU, l'autre au chipset). Données chaudes < 300 Gio (VM Talos 3 × 32 Gio, ClickHouse 14 Gio, bitcoind 23 Gio, bases, stockage Docker) : 1 To suffit. Alternative avec protection contre les coupures (PLP), meilleure pour les écritures synchrones des bases : Kingston DC2000B 960 Go. Migration (pool des Apps, datasets chauds, zvols) = changement d'architecture à planifier dans une PR dédiée, avec relecture.
- Vérifier les alertes Restic `workstation_restic` et configurer au moins un récepteur Alertmanager, puis une restauration hors site. 10/11 : le récepteur `default` est vide, aucune alerte ne part ; `NablaExporterTargetDown` depuis le 07/11 pour quatre exporters jamais déployés (Q11, Q12 de la [passe du 10/11](runbooks/2026-11-10-roadmap-pass-blockers.md)). 12/11 : ces jobs sont `planned` et exclus de l'alerte depuis e5a4c165 ; récepteur Slack actif (`api_url_file`, Prometheus redéployé). 13/11 : `postgres_exporter` déployé, Prometheus rechargé. Reste la restauration Restic hors site.
- **Plan de performance validé par l'opérateur le 16/11**. Mesures du 16/11, 3 jours après le reboot du 12/11 : raidz2 de 4 HDD, IOPS aléatoires d'un seul disque ; PSI IO `full` à 7–10 % même avec bitcoind arrêté ; écritures depuis le reboot : bitcoind 1,66 To, ntopng 564 Go pour 160 Mo de données, Docker 235 Go, ClickHouse 100 Go, PostgreSQL HA 31 Go, Gatus 12 Go ; 90 conteneurs sur 133 sans limite mémoire ; 5,7 Gio disponibles. Les lectures sont servies à 99,9 % par l'ARC, un L2ARC n'apporterait rien.
  1. [ ] **ntopng** : `recordsize=16K` sur `cpool/ntopng` puis recopie des fichiers, car chaque mise à jour RRD réécrit un bloc de 128 Ko. `CODED` : profil dans `config/truenas/dataset-profiles.json`, appliqué par `bootstrap-repository-storage.sh --apply ntopng`. Mesurer les écritures physiques du pool (`zpool iostat`) : `nwritten` compte les écritures logiques, que `recordsize` ne change pas. Réécriture unique des fichiers existants : `scripts/truenas/rewrite-ntopng-records.sh` (`--check`/`--apply`).
  2. [x] **Abandonné le 16/11 (décision opérateur)** — **Bases de données** : `recordsize=16K` et `logbias=throughput` sur `cpool/ha/postgres` et sur la base `postgres` partagée. App arrêtée, snapshot avant. Script versionné `--check`/`--apply`. 16/11 : non fait, gain faible. Ces datasets écrivent 2,8 et 0,2 écritures/s, contre 395 pour ntopng, et appartiennent à des Apps du catalogue, hors du bootstrap de stockage. Abandon validé par l'opérateur.
  3. [ ] **Appliquer ce qui attend** : fenêtre nocturne, redéploiement de Prometheus et clamav, redéploiement de scanopy, litellm et ntopng (zombies) après fusion.
  4. [x] **VMs Talos arrêtées** le 16/11 (`just talos-vms-stop`, autostart désactivé) : `MemAvailable` passe de 5,7 à 13 Gio. Le CSI est réparé (RBAC du csi-resizer, smoke RWX réussi). Au redémarrage, appliquer l'adressage statique des nœuds ([incident du 14/11](incidents/2026-11-14-talos-control-plane-public-wan-lease.md)).
  5. [ ] **Tests SMART longs** sortis des nuits de bitcoind (ansible-workstation).
  6. [ ] **Limites mémoire** à partir de `memory.peak` × 1,5 sur les conteneurs qui n'en ont pas. Relevé cgroup du 16/11 : openclaw-gateway, nexus, les OpenSearch, clamav et kafka avaient déjà une limite, mais 90 conteneurs n'en ont pas (32 Gio de pics cumulés). `CODED` : `mem_limit` sur sentry-web, sentry-taskworker, clickhouse, langfuse-web, langflow, suricata, mongo, litellm, languagetool, openwebui et fastapi-sample. Le test cliquet `tests/test_compose_resource_ratchet.py` empêche le nombre de services sans limite d'augmenter. Prise d'effet au redéploiement de chaque App.
  7. [ ] **Moteurs de recherche** : un seul OpenSearch pour OpenRAG plus l'indexeur de Wazuh ; vérifier l'usage d'`opensearch-security` (environ 1,7 Gio).
  8. [ ] **Journaux Docker** : `logging.options.max-size` commun à tous les Compose, avec test de contrat (aucune rotation aujourd'hui). 16/11 : le plus gros journal fait 101 Mio (docker-socket-proxy, désormais en rotation). Le même test cliquet bloque tout nouveau service sans rotation. Généralisé le 16/11 : chaque Compose définit l'ancre `x-logging: &nabla-logging` (10m × 3), et le test exige la rotation partout. Effet à la recréation de chaque App.
  9. [ ] **Pool NVMe « fastpool »** : achat validé ; Docker, bases, ntopng, Gatus, zvols Talos et chainstate bitcoind (moins de 300 Gio). PR dédiée et relecture.
  10. [ ] **bitcoind** : fenêtre nocturne ou pause jusqu'au NVMe ; `dbcache` à 4 Gio seulement une fois la RAM libérée ; `assumeutxo` selon la version.
  11. [ ] **À investiguer** : `bitwarden-api` (`bw serve`) a lu 312 Go sur `cpool/vaultwarden` en 3 jours (servis par l'ARC, donc coût CPU) ; écritures de `ix-apps/docker` non attribuées par conteneur.

Références : [performance](../scripts/truenas/diagnose-performance.sh), [snapshots ZFS](truenas-zfs-snapshot-policy.md), [cycle de vie des Apps](truenas-app-lifecycle.md).

## P1 — Janvier 2027 : mise à niveau TrueNAS 27.0 finale

La 27.0 finale est annoncée début décembre 2026 (hôte en 27.0.0-RC.1, profil Early Adopter, aucune RC.2). Planifier la mise à niveau en **janvier 2027**, une fois les premiers retours publiés, avec la transaction du [runbook de reboot](homelab-reboot-runbook.md) : bundle régénéré depuis `master`, `--check`, `--prepare`, mise à niveau, puis `--post-reboot-check`, `--resume` et `--verify`. Avant : relire les [notes de version 27](https://www.truenas.com/docs/scale/27/gettingstarted/versionnotes/) et les reboots bloqués après un échec du script de mise à niveau signalés sur le forum. Ne pas lancer `zpool upgrade` (le flag `dynamic_gang_header` empêche le retour arrière en lecture seule) et garder l'environnement de boot précédent. **Clôture** : 27.0 installée, transaction `VERIFIED`, contrôles post-upgrade du P0 TrueNAS 27 passés.

## P1 — Avant TrueNAS 28 : sortir de `auth.login_with_api_key`

`auth.login_with_api_key` est déprécié en 27 et supprimé en 28. TrueNAS CSI `v1.0.3` (encore en `v1.3.0`), `@profanter-dev/truenas-mcp` `1.0.6` et portracker (ancien `/websocket`) l'utilisent : les migrer vers `auth.login_ex` (`API_KEY_PLAIN` ou SCRAM), puis rejouer provision/persistance/reclaim CSI. **Clôture** : aucun client sur l'ancienne méthode avant toute mise à niveau en 28. [Upgrade coupling](truenas-operator-tools.md#upgrade-coupling).

## P1 — Séparation OpenClaw / Workstation / YubiKey

Migration de dépôt **historiquement réceptionnée**. Les futurs travaux Gateway/heartbeat relèvent de [nabla-openclaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md), les mutations matérielles et certificats de [nabla-yubikey](https://github.com/AlbanAndrieu/nabla-yubikey). [Bilan figé](roadmap-openclaw-yubikey-extraction-20261030.md).

## P1 — Bibliothèque média \*arr (acquisition anonymisée)

- [Roadmap canonique](arr-media-library-roadmap.md) : Gluetun + qBittorrent seuls dans un namespace VPN (kill switch, DoT Quad9 dans le tunnel), Prowlarr via le proxy HTTP Gluetun, reste du homelab et DNS pfSense/Unbound inchangés ; schéma réseau et tableau des flux au §4.1.
- Décisions du 7/11 : ProtonVPN (à souscrire), Jellyfin cible, Emby seulement si la Samsung Frame l'exige, aucun accès distant, Usenet différé. Les Apps \*arr natives sont des PoC : suppression sans migration (Transmission et Readarr d'abord) ; le diagnostic `lidarr` est remplacé par cette suppression.
- Ordre : P0 suppression des sept noms publics, test de la TV, suppression des PoC, souscription → stockage `cpool/media` avec quota → frontière VPN → Prowlarr → Radarr/Sonarr/Lidarr/Recyclarr → Jellyfin/Bazarr/Seerr.
- IaC et télémétrie `CODED` le 8/11 : DNS public en OpenTofu (CNAME des routes du tunnel, retrait en deux plans des 7 noms média), profil déclaratif `cpool/media` dans le bootstrap de stockage, câblage \*arr en OpenTofu (`terraform/media`) et réconciliateur `config/media/settings.yml`, exporters + règles + tableau Grafana + journaux Loki ([§10.1](arr-media-library-roadmap.md)).
- `CODED` le 8/11 (non déployé, `status: planned`) : `apps/media-acquisition`, `prowlarr`, `radarr`, `sonarr`, `lidarr`, `bazarr`, `recyclarr`, `jellyfin`, `seerr`, `scripts/truenas/deploy-media-stack.sh` et `tests/test_media_stack_contract.py` ; route Tunnel `emby` retirée du code. Suppression de Plex et Whisparr confirmée.

**Clôture** : batterie de tests d'anonymat (§9) verte et datée sur le SHA déployé ; aucun service média joignable depuis l'extérieur.

## P1 — Assistants IA, IaC et observabilité (11 novembre 2026)

- **H12** : OpenRAG/LiteLLM/Docling, embeddings workstation, clés virtuelles non maîtresses, corpus privé. [Runbook](runbooks/openrag-babou-ingestion-diagnostics.md).
- **H05** : vérifier les exports `postgres-exporter`/`pg_up`, jobs Gatus/Prometheus et la fraîcheur ; aucun succès supposé à partir des chiffres du 11/11. [Remédiation](runbooks/2026-11-04-probe-remediation.md).
  - 16/11 : `pg_up` = 1 (`postgres_exporter`, 172.17.0.24:9187). Les 13 cibles à `up=0` sont toutes `operational_state=planned`. Gatus : 66 moniteurs sur 67 en succès ; l'échec est Uptime Kuma (non déployée).
- États de livraison des assistants, clés LiteLLM, Slack et exporters : [archive datée](archive/2026-11-13-roadmap-before-compaction.md).

## H11 — scission des scripts opérateur et diagnostics (étude D0–D4)

Référence normative : [ADR-0003 existante](adr/0003-repository-ownership-and-diagnostics.md).
[Inventaire détaillé](runbooks/operator-script-ownership-inventory.md) issu de
la PR #386 ; ne pas créer une deuxième ADR-0003.

- **D0** cartographier les consommateurs avec `python3 scripts/ops/plan-repository-split.py --openclaw-consumers` (références textuelles seulement), puis comparer arguments/exit codes
  avant d'attribuer une propriété aux scripts. Les cinq homonymes OpenClaw
  restent des contrats potentiellement différents ; contrôler leurs usages.
  **16/11** : outil corrigé (il ignorait les dépendances croisées entre
  scripts partagés : `reconcile-openclaw-digest-cron.py` charge
  `diagnose-openclaw-digest-top.py` et `openclaw-host-context.py`, à migrer
  ensemble). Options `argparse` identiques 5/5 avec OpenClaw `1bf9857` ;
  codes retour et sorties encore à recetter sur fixtures.
  [Relevé](runbooks/operator-script-ownership-inventory.md).
- **D1–D2** converger les outils Gateway dans `nabla-openclaw` et les audits
  OS dans `ansible-workstation`, avec wrappers temporaires et rollback.
  Conserver la logique inter-hôtes de LiteLLM/TrueNAS dans Compose.
- **D3 / H07** étudier `nabla-pfsense` uniquement après validation de
  l'ownership, sauvegarde et CLI `plan/check/apply/rollback` ; sous-module
  seulement si un consommateur exige le SHA d'un arbre Git.
- **D4 / H05** unifier les transports redondants après tests négatifs ;
  FastAPI/Gatus/Prometheus fournissent les preuves continues, Compose garde
  les smokes CSI, restauration, OTLP et les actions de reprise autonomes.

**NO-GO :** pas de suppression de scripts privilégiés, de service redémarré
ou de faux `PASS` runtime sur un simple document. L'ordre opérationnel
**H01 → H02 → H04 → H05 → H12 → H13 → H16** reste prioritaire sur ce refactoring H11.

## P1 — Fiabilité des scripts et documentation

- **Inventaire H11 du 14/11 — [hotspots de code](code-hotspots.md)** : quantifier les fichiers par domaine (tests, TrueNAS, pfSense, catalogue V2, FastAPI/sondes/UI). Priorité au découpage ciblé des gros scripts seulement après preuve d'un risque de maintenance, avec mêmes exit codes, sorties expurgées et tests négatifs. Le scanner Git local est offline, sans secrets ni LAN : `just code-hotspots`.

- Redéploiement ciblé des Apps TrueNAS : **CODE ADDED 7/11** — [`redeploy-impacted-apps.py`](../scripts/truenas/redeploy-impacted-apps.py) planifie, à partir des fichiers modifiés et des `dependsOn` du catalogue, les `app.redeploy` (fournisseurs d'abord) et ne redémarre un dépendant que s'il devient malsain ; le cron horaire n'affiche que le plan. À faire : lire le premier plan réel (Apps non liées au checkout par `include`), puis un premier `--apply` validé ; décider ensuite d'un apply automatique dans le cron. [Contrat](truenas-deployment-automation.md#redeploying-only-the-apps-a-change-touches).
- **CODED dans #330** : extractions `scripts/lib/postgres.sh` et `scripts/lib/app-deploy.sh`, wrappers historiques conservés, `rollout-pending-apps.sh` plan/check/apply avec sortie expurgée et code de retour réel. La réception runtime reste ouverte. Contrôler ensuite `deploy-autokuma.sh`, `deploy-docling.sh` et `deploy-bitcoind.sh` pour les réconciliations inline ; `ntopng` nécessite licence Enterprise et interface réseau explicitement approuvées.
- Terragrunt CD : **retiré le 12/11** (Q17). Aucun runner `infra-runners` (0 runner enregistré, environnement `TrueNAS` sans secret, exécutions d'août annulées après 24 h d'attente) et le backend Garage n'est joignable que du LAN. Plan et apply restent sur la workstation via `terragrunt-safe.sh` ; la CI garde la validation statique (`terragrunt-ci.yaml`). Un contrat refuse tout `terragrunt init/plan/apply` ou `tofu plan/apply` dans un workflow.
- Factoriser les primitives de diagnostic Docker/HTTP seulement si les scénarios d'erreur, le journal expurgé et le refus des opérations mixtes sont couverts par tests.
- Exécuter `just agent-skills-check`, `just quality` et `mise run agent-pre-push` sur un worktree non root au HEAD exact. Des échecs identiques à `master` dus au DNS ou à un utilisateur root ne valent pas une gate PASS.
- `Ask the user` avant d'installer des skills externes. Aucun nouveau skill Talos ou Docker n'est installé implicitement.

## P2 — Étude : EnOcean (NodOn) dans Home Assistant

**H18 · PLANNED** — [Étude EnOcean/Somfy et radio Flexom](roadmap-homeassistant-integrations.md), sans configuration ni achat implicite.

## P2 — Étude : volets et alarme Somfy dans Home Assistant

**H18 · PLANNED** — [Même étude](roadmap-homeassistant-integrations.md) ; protocole des moteurs et modèle d'alarme à identifier.

## Historique minimal : problèmes à ne pas reproduire

Les leçons d'exploitation sont dans [les incidents](incidents/2026-11-06-migrations-retour-experience.md) ; le tableau original est dans [l'archive datée](archive/2026-11-13-roadmap-before-compaction.md). Aucune ancienne procédure n'autorise une mutation actuelle.

## Gouvernance et clôture

`nabla-compose` : infrastructure déclarative ; `fastapi-sample` : sondes et statuts ; `nabla-site-alban` : rendu utilisateur. Le contrat `entityRef`/`catalogRevision` est partagé, mais aucune logique de déploiement ne doit se déplacer vers les sites.

**DONE global** : catalogue et topology générés sans dérive, politiques d'accès conformes, services obligatoires prouvés `ACCEPTED (runtime)`, migrations de dépôts sans doublons et récupération testée. Toute ligne sans preuve demeure ouverte.


## P0/P1/P2 — Cible cryptographique FIPS, PostgreSQL 16 → 18, TLS 1.3, Vault et OAuth (10 novembre 2026)

**H09** : durcir les clients PostgreSQL restants en `verify-full` avec CA/SAN contrôlés. PostgreSQL 18.6, SCRAM et `hostssl` ont été préparés, mais cela n'atteste pas la conformité de tous les clients.

**H16** : pilote Vault PKI/OAuth SQL/OIDC Keycloak, révocation et break-glass. L'objectif FIPS 140-3 est un **alignement technique**, non une certification.

[Runbook détaillé FIPS, TLS 1.3, Vault et OAuth](security/postgresql-fips-tls13-vault-oauth-20261110.md). La matrice datée initiale est [archivée](archive/2026-11-13-roadmap-before-compaction.md).
