## P0 — Reprise Site #236 / Compose #263 : artefacts ZAP et frontière privée (19 octobre 2026)

## P1 — FastAPI staging → TrueNAS LiteLLM → workstation Qwen (2026-10-20)
- [x] Declare dedicated `fastapi-qwen` relay (no IDE token reuse), sample staging URL/model, model-allowlisted keys, lifetime budget and Vaultwarden metadata. [Runbook](runbooks/fastapi-sample-litellm.md).
- [ ] Provision two separate private virtual keys via loopback/SSH tunnel, store in separate Vaultwarden items, materialize without replacing existing sample secrets. Never store a key in Git.
- [ ] Validate effective proxies/DB, internal Qwen token accounting, no costly fallback, tool calling, model allowlists, 2-stage `/v1`, and staged `/run` authorization before deployment. Cloud production not routed into LAN.


**Autorité du contrat** : [collecteur privé](defectdojo-artifact-poller.md),
[Site #236](https://github.com/AlbanAndrieu/nabla-site-alban/pull/236)
et [Compose #263](https://github.com/AlbanAndrieu/nabla-compose/pull/263).
Sans nouvelle PR, merge, activation, mutation de compte ou import.

| Gate | Statut | Preuve / suite |
| --- | --- | --- |
| Site Quality + Trivy au HEAD initial `8a19211` | **PASS** | Runs Site #39325632157 (job quality) et #39325632138 |
| Site ZAP Preview / Vercel au HEAD initial | **PASS** | Statuses exact SHA ; **ancien workflow uniquement** |
| Site Playwright au HEAD initial | **FAIL** | Run #39326142907 : 1 échec dû à deux scripts d'initialisation de thème concurrents |
| Corrections Preview et sortie ZAP brute côté Site | **INCOMPLETE** | CI des nouveaux commits et scanner effectif après fusion non encore validés |
| Compose fail-closed ZAP JSON → XML | **INCOMPLETE** | Filtrage strict préécriture ajouté, tests adaptés ; exécution de validation exact HEAD à attester |
| Ancien ZAP brut (Alban/Bababou) | **FAIL** (refus intentionnel) | Instances, preuves, titres reflétés et entêtes sont interdits ; Bababou attend sa propre minimisation source |
| GitHub App Actions:read, clés Vaultwarden, cron, import DefectDojo | **NOT_RUN** | Nécessite consentement GitHub, RBAC/Engagement, parser `ZAP Scan`, retour Celery et déduplication |
| Tests opérationnels `ops.albandrieu.com` / Access / origine | **NOT_RUN** | Suite de tests privés Site, activée seulement avec réseau et identité autorisés ; aucune réexposition publique |
| Audits de refus public CDN/DNS/Tunnel | **INCOMPLETE** | Vérifier négativement les routes, en-têtes, artefacts historiques et exposition WAN avant clôture |

Décisions : **GitHub App → TrueNAS → DefectDojo** reste l'unique voie
d'ingestion, `--check` sans mutation, `--pull` explicite,
`--pull-and-import` soumis à autorisation indépendante et engagement
préexistant. BetterLeaks, Semgrep, Trivy Critical et ZAP/Nuclei bornés
restent des gates autonomes ; aucune campagne DAST complète sur PR.
`INCOMPLETE` et `NOT_RUN` ne sont jamais équivalents à `PASS`.

## P0 — Quatre dépôts, une GitHub App, Vaultwarden et Cron (2026-10-19)

- [x] Définir `nabla-github-app` unique pour nabla-compose,
  fastapi-sample, nabla-site-alban et nabla-site-bababou, avec
  `Actions:read` et jetons éphémères restreints par dépôt.
- [x] Préparer `defectdojo-compose-handoff.yml` : rapport minimal Trivy
  HIGH/CRITICAL sur lockfiles, manifest SHA-256 sur master chaque semaine,
  sans DAST supplémentaire et sans consommation de CI PR.
- [x] Étendre le collecteur aux quatre dépôts et la validation Trivy
  universelle avant import ; les workflows amont non encore présents dans
  master doivent être signalés `NOT_OBSERVED`.
- [x] Ajouter le bootstrap Vaultwarden `nabla/prod/nabla-github-app`,
  PEM root-only, `.env.secrets` Cron à références et launcher contrôlé.
- [x] Documenter l'amélioration des agents/skills : inspection bornée,
  commits groupés, logs d'échec ciblés et contrôle HEAD concurrent.
- [ ] Approbation GitHub, installation sur quatre repos, import PEM en
  Vaultwarden, matérialisation TrueNAS et acceptation des quatre Product/
  Engagement DefectDojo. La création effective de l'App et du Cron
  ne peut être affirmée depuis la PR seule.

## P0/P1 — Clôture du contrat collecteur DefectDojo inter-dépôts (2026-10-19)

Réconciliation [Site Alban #236](https://github.com/AlbanAndrieu/nabla-site-alban/pull/236)
et [Compose #263](https://github.com/AlbanAndrieu/nabla-compose/pull/263).
La source autoritative de la procédure reste
[docs/defectdojo-artifact-poller.md](defectdojo-artifact-poller.md).

- [x] GitHub App partagée, permissions de lecture `Actions:read` limitées
  à un dépôt sélectionné par jeton ; pas de PAT statique ou runner
  GitHub auto-hébergé, pas d'API DefectDojo exposée.
- [x] Recherche bornée par **workflow identifié + dépôt + master** ;
  le dernier run en échec, annulé ou non terminé bloque le retour à
  un ancien scan réussi. Filtrage par `head_sha`, état, événement,
  identité et nom exact d'artefact.
- [x] Correctif poll multi-dépôts : transmettre `--source` au collecteur
  pour éviter un téléchargement involontaire depuis Site Alban lorsqu'on
  demande Bababou ; ajouter test de non-régression.
- [x] Formats de stage minimaux : Trivy vuln High/Critical
  (`package-lock.json` uniquement pour Site Alban), Nuclei JSONL
  High/Critical origin-only et titre fondé sur le template-ID, ZAP
  JSON → XML expurgé High uniquement. API parser officiel
  **`ZAP Scan`** (et non `Zed Attack Proxy`) ; importer le XML
  avec `application/xml`. Ne jamais importer les captures HTTP
  complètes, secrets, SBOM, licences ou SARIF arbitraires.
- [x] Tests source ajoutés pour la minimisation des rapports, le
  rejet des origines non autorisées et des secrets HTTP, les runs obsolètes
  et le contrat de provenance. Le statut de leur exécution dépend
  du dernier HEAD CI : ce n'est pas une preuve runtime.
- [ ] Faire accepter par le **parser installé** sur TrueNAS un exemple
  XML expurgé réel et vérifier la déduplication et l'état asynchrone
  du reimport dans l'engagement isolé.
- [ ] Créer/installer la GitHub App (owner consent), stocker la PEM dans
  Vaultwarden, matérialiser la clé sur TrueNAS et vérifier Cron `--check`.
  Le cron reste désactivé ; `--pull` puis `--pull-and-import`
  nécessitent des autorisations distinctes.
- [x] **Correctif de code source Site #236** : suppression de l'action
  auto-upload ZAP ; production ne dépose qu'un JSON HIGH minimal,
  Preview ne dépose aucun rapport ZAP. Le collecteur #263 refuse à
  présent les JSON bruts préexistants, y compris Bababou.
- [ ] **INCOMPLETE** : prouver la première exécution du nouveau producteur
  après merge, la conversion XML et son acceptation par le parser Dojo ;
  inventorier les anciens artefacts encore accessibles. Aucun import
  ZAP autorisé jusque-là. Les DAST plus profonds restent privés.
- [ ] Vérifier les quality gates exact-HEAD dans les deux PR,
  l'absence d'exposition `.int`, le produit/RBAC DefectDojo
  et les règles de rétention/rotation avant activation.

## P0/P1 — GitOps single GitHub App / Site Bababou convergence (2026-10-19)

- [x] Unifier `nabla-github-app` pour quatre dépôts Nabla,
  installation GitHub à dépôts sélectionnés, jeton à durée courte
  `Actions:read` limité à **un seul dépôt par appel**, sans PAT.
- [x] Ajouter le bootstrap Python stdlib du GitHub App Manifest Flow
  (boucle locale 127.0.0.1, code CSRF, échange de code, PEM privé 0600
  hors Git) et le contrôle d'installation via API.
- [x] Préparer le collecteur Bababou : workflow `production-dast.yml`
  existant sur `master`, ZAP HIGH uniquement, XML minimal sans preuves
  HTTP sensibles, hôtes `bababou.com` explicitement autorisés.
- [ ] Recette GitHub App owner consent/installation, transfert PEM
  Vaultwarden, matérialisation TrueNAS, tests de JWT et un import
  DefectDojo réel sur un engagement Bababou isolé.
- [ ] Évaluer Nuclei SARIF minimisé après publication d'un artefact
  vérifiable sur `master`. Ne pas créer de nouveau scan DAST en PR.
  [Runbook](github-app-defectdojo.md).

## P0/P1 — DefectDojo `nabla` et GitHub App à durée courte (2026-10-19)

- [x] Remplacer le compte UI initial `admin` par **`nabla`** dans le
  bootstrap Vaultwarden, le template d'environnement, les contrats et le
  runbook. Ne pas modifier les mots de passe existants : un item `admin`
  déjà initialisé reste une **migration de compte Django distincte**.
- [x] Décrire la GitHub App `nabla-defectdojo-artifacts` avec accès
  `Actions:read` au seul dépôt `nabla-site-alban` et zéro webhook ;
  [manifest](../config/github-apps/defectdojo-artifacts.manifest.json) et
  [runbook](github-app-defectdojo.md). Le provider GitHub Terraform peut
  *consommer* une App existante, pas enregistrer cette App.
- [x] Préparer le jeton d'installation **éphémère** (JWT signé par PEM
  root-only, POST GitHub installation access token, permissions et dépôt
  explicitement réduits, expiration ≤1 h) pour le collecteur Cron TrueNAS.
  Suppression de l'obligation d'un PAT GitHub permanent.
- [ ] Enregistrer/installer l'App sous contrôle du propriétaire, puis
  importer sa clé PEM en tant que pièce jointe dans Vaultwarden et
  matérialiser les fichiers runtime `github-app.json` et
  `github-app-private-key.pem` avec permissions `0600`.
- [ ] Accepter compte `nabla`, JWT GitHub App, collecte d'artefacts
  `master`, import DefectDojo et déduplication ; **aucun apply en CI**.

## P1 — Declarative TrueNAS Cron (2026-10-19)

- [x] Add `scripts/truenas/reconcile-defectdojo-artifact-cron.py`
  (`--check|--apply|--enable|--disable`) with a disabled-by-default
  native TrueNAS cron task at 06:50 appliance local time. No GitHub runner,
  external inbound port or hosted PR DAST scan.
- [x] Test TrueNAS Cron ownership/schedule drift and approval gating offline.
- [ ] Runtime: register disabled task, validate GitHub App Actions:read installation and
  allowlisted master artifact, then enable `--pull` only. Add optional
  DefectDojo import **after** existing engagement and parser acceptance.

## P0/P1 — DefectDojo GitHub Actions artifact polling without a runner (2026-10-19)

[Execution/runbook](defectdojo-artifact-poller.md) · source-only in PR #263.

- [x] Make the existing `bootstrap_defectdojo_admin.py` create a missing
  Vaultwarden login for first-run `nabla` with a CSPRNG password,
  preserving DB/Redis fields and refusing overwrites, without checking
  DefectDojo's DB. `.env.secrets` remains Vaultwarden materialized.
- [x] Prepare GitHub Actions **pull** by native TrueNAS cron, not
  self-hosted runner. Standard-library HTTPS client, short-lived GitHub App Actions:read
  token, exact repo/workflow/master/SHA provenance, restricted signed-URL
  downloads, small ZIP/report size ceilings and root-only inbox.
- [x] Add `poll-defectdojo-gh-artifacts.py` to discover recent successful
  master scans for Site Alban and stage them without rerunning ZAP/Nuclei.
  Optional import is separately gated and limited to an existing engagement;
  default mode is offline and no network/no secrets.
- [ ] Operator acceptance: Vaultwarden login created and materialized,
  TrueNAS scoped GitHub App private key installed, disabled native cron job registered,
  artifact retention/ACL checked, ZAP/Nuclei report sanitization reviewed,
  and Product RBAC + async reimport/deduplication proven.
- [ ] Enable the 06:50 daily local TrueNAS cron only after the above gates.
  No public DefectDojo API, no raw GitHub secret findings, no new DAST CI jobs.

## P0–P2 — DefectDojo/Vaultwarden, Trivy licence, SBOM et scans multi-repos (2026-10-18)

- [x] DefectDojo Compose charge les deux fichiers runtime
  `/mnt/cpool/secrets/runtime/defectdojo/.env` (non secret)
  et `.env.secrets` (Vaultwarden). Identifiants UI dans le manifeste
  Vaultwarden, **aucun mot de passe en Git**.
- [x] Préparer la génération d'un mot de passe UI aléatoire directement
  dans l'item Vaultwarden avant le premier initializer. Ne **jamais**
  traiter une génération comme une rotation effective d'une instance existante.
- [ ] Vérifier l'utilisateur courant, récupérer ou réinitialiser la
  session administrateur existante; ensuite synchroniser Vaultwarden,
  matérialiser et vérifier l'authentification après reboot.
- [x] Générer en local privé des rapports Trivy vulnérabilités compatibles
  DefectDojo, audit séparé misconfig/licence et CycloneDX SBOM.
- [ ] Étendre la provenance d'import au dépôt canonique, à CodeQL SARIF,
  Semgrep, Nuclei et ZAP sur allowlist stricte sans ingérer les secrets BetterLeaks,
  les données PII ou tous les rapports indistinctement.
- [ ] Préparer la réception des scans `nabla-site-alban` sur `master`
  uniquement, depuis un runner interne de confiance et dans des engagements
  DefectDojo isolés, avec quota CI DAST (ZAP production existant, Nuclei hebdomadaire).

## P0/P1 — DefectDojo : bootstrap credentials Vaultwarden et collecte de scans (2026-10-18)

**Owner** : `nabla-compose` pour utilisateur/secret/UI/permissions LAN ; `fastapi-sample` PR #353 pour production locale des rapports et client d'import ; `nabla-site-alban` pour DAST de son propre domaine. DefectDojo doit rester `defectdojo.int.albandrieu.com` strictement interne (DNS/TLS/Traefik/RBAC), sans tunnel ou scrape public.

- [ ] **P0 Génération utilisateur UI** : vérifier le bootstrap DefectDojo installé, créer un utilisateur opérateur nominatif **non-superuser**, mot de passe cryptographiquement aléatoire ≥32 caractères et secret de récupération ; ne jamais générer ou stocker ces secrets dans le Git, les logs, les outputs CI, Docker image ou stdout. Contrôler l'accès direct à `https://defectdojo.int.albandrieu.com` et sa non-exposition publique avant création.
- [ ] **P0 Coffre Vaultwarden** : créer/mettre à jour un item `defectdojo/operator-ui` (username/password/URL) via la CLI `bw` locale avec `BW_SESSION` disponible en mémoire, permissions restreintes, aucun doublon et vérification après import sans afficher le mot de passe. Réutiliser `scripts/truenas/prepare-security-tooling-secrets.sh` et la logique `scripts/secrets/import_env_to_bitwarden.py`, mais **ne pas exporter le mot de passe UI dans un .env de conteneur**.
- [ ] **P0 Service API séparé** : créer un compte importeur DefectDojo limité aux Products/Engagements précréés `fastapi-sample` et `nabla-site-alban`; stocker **son jeton distinct** dans Vaultwarden (item `defectdojo/security-importer`), le matérialiser au runtime en lecture limitée ; pas d'admin, pas d'énumération globale, pas de tokens dans URLs ni dans artifacts.
- [ ] **P1 Scan bundles private-only** : sur `master` produire en interne Trivy JSON (vuln/misconfig/secret/license, inclure `uv.lock`), CycloneDX, Semgrep, ZAP/Nuclei low-rate selon scope. Utiliser `fastapi-sample/scripts/security/import_defectdojo.py` en `--apply` seulement après validation TLS, Product RBAC et identifiants d'Engagement. Imports via `/api/v2/reimport-scan/` depuis client LAN approuvé ; **Dojo ne scrape pas GitHub Actions**, ni stockage public, ni OpenAPI, ni les rapports secrets Betterleaks. Aucun `auto_create_context`.
- [ ] **P1 Validation** : audit des deux Products, tests TLS/SNI, refus anonyme 401/403, refus WAN, token importeur refusé hors son engagement, rapport importé asynchrone traité et dédupliqué, retention/purge et rollback. Les scans non exécutés ou incomplets restent `NOT_RUN`, pas zéro findings.
- [ ] **P2 Sans dépense Actions excessive** : conserver les hooks GitGuardian/Betterleaks, CodeQL déjà présents et le Trivy Critical PR ; ZAP/Nuclei approfondis uniquement sur `master` ou déclenchement manuel autorisé, et préférer le runner LAN local-first. Comparer `nabla-site-alban/.github/workflows/master-dast.yml` et `nuclei-public.yml` avant d'ajouter de nouvelles fréquences.

## Cloudflare ops OpenTofu GitOps + DefectDojo import staging (2026-10-18)

- [x] Add opt-in Cloudflare v5 module for dedicated Tunnel, remote ingress
  and proxied `ops.albandrieu.com` CNAME with **all mutation flags false**,
  protected destroy, Access/JWT/TLS/website-redaction prerequisites and no
  embedded token. [Runbook](cloudflare-ops-execution-2026-10-18.md).
- [ ] Validate HCL format/provider schema and lock v5.28.0 in CI (offline state).
- [ ] Import only an independently verified dedicated Tunnel/record; inspect
  actual Access policies, certificate, private origin, Garage state and rollback.
- [ ] Activate ingress/DNS only once public site, origin JWT and MFA gates pass.
- [ ] Capture an actual private Trivy JSON report from this repository or an
  immutable image; validate DefectDojo authenticated API and existing engagement,
  then import from a LAN-trusted host with the existing fail-closed importer.
  GitHub CodeQL success alone is **not** an importable private report.

## P0–P2 — Seven controlled migrations (2026-10-18, PR #263)

**Read-only GitOps preparation, not runtime acceptance.**
[Execution contract](migration-batch-execution-2026-10-18.md) ·
[Offline manifest](../config/migrations/workstreams.json).
Priority: secrets/Vaultwarden → DefectDojo LAN → Backstage v2;
in parallel, prepare OpenClaw/LiteLLM and OpenRAG/Docling/Bababou,
reconcile Gatus/Prometheus/FastAPI probes, and enable FreshRSS GitOps/MCP
only after secrets acceptance. Validate with
`python3 scripts/security/check-migration-readiness.py --check`;
no deployment, secret read, mutation, reindex or automatic merge.

## P1/P2 — DefectDojo : pull sélectif des artefacts de sécurité de Site Alban (2026-10-18)

- [x] Préparer `scripts/security/pull-site-alban-security-report.py` et
  les tests de provenance `master` réussie, allowlist workflow/artifact,
  extraction ZIP bornée et filtrage Trivy HIGH/CRITICAL, Nuclei HIGH/CRITICAL
  et ZAP HIGH; **aucun import automatique**.
- [x] Restreindre `config/security/defectdojo-allowed-imports.json` pour
  `nabla-site-alban` à ces trois parsers seulement. BetterLeaks/GitGuardian,
  SARIF et SBOM ne sont jamais ingérés par ce parcours.
- [ ] Vérifier le parsing dans l'instance DefectDojo privée, la séparation
  du jeton GH Actions:read et du jeton import DefectDojo, les artefacts
  `master` par run/SHA, les ACL sur TrueNAS et le filtrage des hôtes.
- [ ] Les rapports DAST exhaustifs **ne doivent pas être publiés en clair**
  comme artifacts d'un repo GitHub public : préférer scan depuis TrueNAS
  ou chiffrement age vers clé de réception privée avant automatisation.
- [ ] Tester import/reimport `--check` puis `--apply` explicitement
  approuvé sur engagement dédié, valider absence de doublons et
  `close_old_findings=false`; ne pas présenter les rapports non ingérés
  comme réussis. Voir [runbook](defectdojo-private-scan-ingestion.md) et
  [Site PR #236](https://github.com/AlbanAndrieu/nabla-site-alban/pull/236).

## P0/P1/P3 — Déploiement ops.albandrieu.com privé (2026-10-18)

Épopée [#262](https://github.com/AlbanAndrieu/nabla-compose/issues/262),
[architecture Access/Tunnel](private-homelab-access-architecture.md) ;
[Site Alban #233](https://github.com/AlbanAndrieu/nabla-site-alban/issues/233)
et [FastAPI #352](https://github.com/AlbanAndrieu/fastapi-sample/issues/352).

- [ ] **P0** Inventorier exposition réelle (DNS, Cloudflare, HAProxy, Traefik,
  NAT), fermer les bypass de l'API privée et définir policy Access deny-by-default.
- [ ] **P1** Préparer Terraform/OpenTofu import-first pour **`ops.albandrieu.com`**
  (FQDN confirmé, non déployé) : Access application hostname entier, policy
  deny-by-default, MFA indépendant vérifié ou IdP MFA attestée, session courte,
  origine FastAPI isolée, Tunnel dédié si faisable, DNS proxied CNAME et
  catch-all 404. Service tokens serveur uniquement, TLS origine vérifié.
- [ ] **Gates 0–5** : absence de fuites site, JWT origine et DTO FastAPI,
  inventaire/réconciliation Cloudflare/NAT, policy Access avant DNS, tests
  anonyme/autorisé/bypass, décommissionnement caches + rollback.
  Références : [Compose #263](https://github.com/AlbanAndrieu/nabla-compose/pull/263),
  [FastAPI #353](https://github.com/AlbanAndrieu/fastapi-sample/pull/353),
  [Site #234](https://github.com/AlbanAndrieu/nabla-site-alban/pull/234).
- [ ] **P1** Router seulement FastAPI opérateur read-only, vérifier JWT à
  l'origine, tests négatifs et santé Access vs origine indépendantes ;
  interfaces management et métriques LAN-only.
- [ ] **P3** Évaluer Keycloak existant `apps/keycloak/compose.yml` **planned**
  comme IdP OIDC futur après DB/secrets/backup et audit; pas de dépendance P0.
- [ ] Ne jamais interpréter la présence des documents ou de la route déclarée
  comme une activation live ; pas de merge ni de déploiement implicite.


## Homarr GitOps declarative migration (2026-10-18)

- [x] Pin Homarr v2.6.0 (upstream release dated 2026-10-15) in Compose; deployment on TrueNAS remains to be verified.
- [x] Introduce versioned board definitions under apps/homarr/config/boards.json; service catalog remains the canonical app inventory.
- [x] Remove dependency on a persisted reconciler mapping file; resolve apps and boards from remote API on each run.
- [ ] Validate Homarr v2.6.0 API contracts for board item listing, updates and widget layout, and add contract tests before enabling production reconciliation.
- [ ] Add declarative sections, widgets, integrations and drift reports; fail closed on ambiguous IDs or unsupported endpoints.
- [ ] Verify live upgrade and reconciliation on TrueNAS; no backup or preservation of user-defined dashboard state required by operator, but retain non-destructive behavior until full declarative convergence is proven.
- [ ] Review least-privilege MCP/API permissions, secret injection, observability, rollback via declarative redeploy, and CI quality gates.

## CURRENT · Prometheus correlation → pfSense stabilization → DefectDojo LAN (2026-10-18)

**Execution order: pfSense safety gate first; DefectDojo only after pfSense DNS and memory remain stable.** Evidence is operator-provided, not a live deployment validation.

### P1 — pfSense memory, DNSBL and observability

- [x] Read-only memory sampling `scripts/pfsense/diagnose-memory-pressure.sh --check --samples 10 --interval 30`: 00:22–00:26 CEST, available free+inactive 223.8–234.4 MiB, Unbound PID 75160 stable, pfBlockerNG cron absent; this does **not** explain earlier transient 24.2 MiB at 00:16.
- [x] pfBlockerNG latest DNSBL `225631 PASSED` and latest update END marker complete; localhost and LAN Unbound DNS checks PASS. Historical OOM at 2026-10-17 02:11 is not a new incident.
- [x] Existing Prometheus multi-target pfSense exporter `172.17.0.24:9945/metrics?target=172.17.0.1`, `up=1`; scrape duration ~5.13–5.22 s. `pfsense_system_memory_usage_ratio=0.31`, recorded `nabla:core:pfsense_memory_available_ratio=0.69`. **Do not equate** exporter ratio with FreeBSD `free+inactive` MiB; compare semantics and sample timestamps before alert thresholds.
- [x] Existing pfSense `pfsense_service_up` confirms unbound, snort, haproxy, kea-dhcp4, pfb_dnsbl, pfb_filter running; ntopng, softflowd, zabbix intentionally off. `pfsense_gateway_up{name="WANGW"}=1`. CrowdSec service=0 but firewall bouncer=1: diagnose before claiming full CrowdSec health.
- [x] Read-only cross-platform `scripts/pfsense/diagnose-prometheus-telemetry.sh --check` executed on workstation: pfSense, TrueNAS node, Akvorado inlet/outlet scrapes UP; FastAPI Sample metrics scrape DOWN.
- [ ] **Next pfSense closure:** capture 24 h trend around cron windows (minimum, duration below 128 MiB, process/UMA snapshot on recurrence), compare Prometheus memory ratio to SSH sampling, check Unbound PID/response and OOM event *deltas*, confirm DNSBL update completes without sustained memory pressure. No proactive reboot, package patch or DNSBL rebuild; pflow activation explicitly operator-approved on 2026-10-18, subject to preflight and rollback.
- [ ] Investigate `dnsbl_ram_swap_gate=missing` and legacy `dnsbl_loaded_entries=0` semantics without mutating pfSense. pflow kernel module not loaded and zero exporters at last observation; operator approved starting pflow for TrueNAS Akvorado only. Require supported persistent configuration, preflight memory/DNS, baseline, limited collector, post-activation verification and rollback. Cloudflare exporter remains disabled. Cloudflare IPFIX exporter must be justified before enabling.
- [ ] Add conditional read-only capture under 128 MiB with rate limiting, retention and secrets redaction; only after validating no resource amplification on 1 GiB Netgate.
- [ ] Close pfSense incident only after 24 h stable DNS, no *new* OOM, pfBlockerNG completion and verified rollback. Treat exporter `up` as telemetry evidence, not DNS/application proof.

### P1 — Operator-approved pflow trial (2026-10-18; review tomorrow)

- [x] Operator authorized enabling pflow now, with review tomorrow; **approval is not evidence that it has been activated**.
- [x] Preflight evidence at 2026-10-18 00:44 CEST: pflow.ko exists (not loaded), pflowctl usage `[-lc] [-d id] [-s id ...] [-v]`, no pflow interfaces; free+inactive 232244 KiB (~226.8 MiB), no active pfBlockerNG cron, Unbound and internal DNS healthy; historical OOM in dmesg. Integration found in `/etc/inc/filter.inc` (also `.orig`). Still inspect relevant function and persistence semantics before activation.
- [ ] Review `/etc/inc/filter.inc` pflow integration and associated pfSense configuration (redact secrets); establish supported persistence and rollback, then enable **only** the TrueNAS Akvorado collector `172.17.0.24:2055/udp` via supported persistent pfSense configuration. Avoid manual kernel/module hacks or unreviewed boot config; Cloudflare flow collector remains off. Capture configuration backup and exact rollback before mutation.
- [ ] Verify pflow interface/exporter status and actual UDP flow ingestion via Akvorado metrics (counter deltas, not just `up`), plus pfSense memory/CPU, Unbound, DNS and pfBlockerNG after activation; stop and revert for memory below 128 MiB, fresh OOM, DNS failure or sustained CPU pressure.
- [ ] Tomorrow: compare 24h before/after resource trends, collector packet deltas, dropped flows and gateway health. Decide keep/revert, document outcome. Do not call the trial complete without observed traffic and stability.

### P1 — OpenRAG/OpenClaw shared embeddings and safe fallback (planned)

- [x] OpenRAG 0.7.1 already targets the workstation LiteLLM `embedding` alias through its OpenAI-compatible backend and shared Langflow. OpenClaw `main`/`cron` migration is still pending.
- [ ] Reconcile both consumers on a stable `embedding` alias and identical embedding model revision/configuration. Keep application-specific LiteLLM virtual keys, budgets and audit trails; **do not** reuse the OpenClaw file token as OpenRAG's chat credential.
- [ ] Test TrueNAS LiteLLM/Ollama as fallback from both consumers, including upstream model identity, sentinel-vector compatibility, retrieval correctness, observability and bounded retry. Never auto-failover across distinct vector spaces, even if dimensions match.
- [ ] If incompatible fallback is desired, use explicit collection/index versioning and a controlled re-embedding cutover. Fail closed on retrieval rather than mixing vectors.
- [ ] Keep OpenRAG 0.7.1 `LITELLM_IDE_API_KEY` until separate chat/embedding credentials are supported; determine supported upgrade or restricted per-consumer proxy before changing secrets.
- [ ] Accept staged OpenRAG ingestion/query and OpenClaw memory smoke, then enable failover with rollback. Do not redeploy TrueNAS or rebuild indexes from documentation-only changes.

Design/acceptance: `apps/openrag/README.md#shared-embedding-contract-with-openclaw-planned-not-deployed`.

### OpenClaw backup and gateway restoration — operator, 2026-10-18

- [x] Gateway quiesced before backup; archive `openclaw-20261017T223508Z-121931.tar.gz` verified (106934 files, SHA-256 recorded in operator output), temporary restore test successful.
- [x] Gateway restarted and `systemctl --user is-active` returned active; control UI WebSocket requests succeeded.
- [ ] Investigate gateway systemd cgroup memory ~5.8 GiB (peak 6.3 GiB), Codex app-server child processes, and one delayed heartbeat (overdue 2852ms; elapsed 32852ms); measure trend before changing limits. No restart warranted by current evidence.

### DefectDojo LAN runtime evidence — operator, 2026-10-18

- [x] pfSense Unbound resolves `defectdojo.int.albandrieu.com` to `172.17.0.24`; HTTPS returns 302 via nginx; previous strict workstation TLS check passed.
- [x] TrueNAS `app.query`: defectdojo RUNNING. Docker: `defectdojo` frontend, `defectdojo-uwsgi`, `defectdojo-celeryworker`, `defectdojo-celerybeat` Up ~2h; `defectdojo-initializer` Exited (0). Frontend binds `172.17.0.24:31085->8080/tcp`.
- [ ] Confirm 302 Location safely (do not publish token/query), verify app readiness and authenticated API, Celery worker responsiveness, database/migrations, synthetic test import and retention/rollback. Container Up and initializer exit 0 alone do not prove these.
- [ ] No change to pfSense DNS, Traefik, firewall or Cloudflare until a specific failure is demonstrated.

### P1 — TrueNAS / Prometheus target quality

- [x] `node_memory_MemAvailable_bytes=6732337152` (~6.27 GiB) and `nabla:core:truenas_memory_available_ratio=0.1011855` at sampled time; `node_vmstat_oom_kill=5` is a cumulative counter, not five recent OOMs. Use `increase(...[1h])` with counter-reset awareness.
- [ ] Investigate scrape failures separately from application health: `pihole_exporter`, `haproxy`, `opensearch-security`, `postgres_exporter`, `fastapi_sample`, `opensearch`, `docling`. Inspect `/api/v1/targets` lastError, expected metric path/port/auth and intended service lifecycle; do not restart blindly.
- [ ] Confirm scrape timeout configured for pfSense (observed ~5.2 s); `scrape_timeout_seconds` series absent in sample. Inspect Prometheus scrape configuration rather than treating absent metric as zero.
- [ ] Reuse Prometheus, Alertmanager, Grafana, Loki and Alloy; no new pfSense daemon by default. Keep Cloudflare Access on public Prometheus; use LAN API or least-privilege service token for automation.

### P1 — FastAPI Sample probes and DefectDojo LAN

- [ ] Explain `up{job="fastapi_sample"}=0`: inspect Prometheus target `lastError`, `metrics_path`, scrape port, and independent `http://172.17.0.24:8091` HTTP/health checks. Never classify app DOWN solely because metrics scrape fails.
- [ ] In FastAPI Sample's own PR, add Prometheus corroboration with explicit `healthy / degraded / unknown` evidence and timestamps: scrape missing/stale/timeout → telemetry warning, not service DOWN. Preserve TrueNAS-primary, direct HTTP/HTTPS/TCP, pfSense and Cloudflare probe precedence; no silent fallback to fabricated values.
- [ ] **DefectDojo LAN gate:** validate `defectdojo.int.albandrieu.com` via pfSense Unbound → Pi-hole → Traefik → DefectDojo with DNS, TLS/Host/SNI, HTTP response and authentication checks. No public `.int` DNS, no external ingress, no unreviewed deployment changes.
- [ ] Verify DefectDojo containers/DB/migrations/worker readiness and authorized API endpoint using secrets from private runtime store; perform synthetic import in an isolated test product, confirm ingestion and rollback. Document exact errors before changes.
- [ ] Add read-only repeatable DefectDojo LAN smoke/runbook and local quality gate; finish validation before marking complete. Do not merge PR automatically.

---

## P1 · pfSense memory stability and pflow recovery — active (2026-10-17)

- [x] Restore Unbound outgoing interfaces `WAN -> All`, verify DefectDojo/Vaultwarden/Hello/S3 private DNS, and document pfSense XML backup paths.
- [x] Add read-only `scripts/pfsense/diagnose-memory-pflow.sh --check` for resident memory, swap, Unbound status, OOM history and pflow interfaces.
- [ ] Execute new diagnostic and `scripts/pfsense/audit-posture.sh` from workstation; record timestamped memory baseline and compare with 2026-10-17 pre-change Unbound RSS ~125–131 MiB and historical OOM. Do not infer new OOM from old dmesg lines.
- [ ] Investigate pfBlockerNG `dnsbl_ram_swap_gate missing` and `dnsbl_loaded_entries 0` without changing package files on pfSense or triggering DNSBL rebuild on memory-constrained Netgate 1100.
- [ ] Diagnose `pflow.truenas missing` (domain 1, 172.17.0.24:2055), `pflow.cloudflare missing` (domain 2, 162.159.65.1:2055), and `pflow.connected_exporters 0`; validate actual desired collectors and routing before any exporter changes.
- [ ] After 24h of stable memory and DNS, close pfSense regression acceptance; retain historical incident evidence and avoid disruptive service restarts.


## P2 · Cloudflare DNS OpenTofu GitOps — preparation (2026-10-17)

- [x] Restore pfSense private DNS forwarding to Pi-hole and validate three internal services; retain local pfSense XML backup inventory in `docs/dns-ingress-ownership.md`.
- [x] Inventory Cloudflare public `.int` records; remove unexpected `s3.int.albandrieu.com` CNAME, retain approved Hello exception; audit exit=0, warnings=1.
- [ ] Build a dedicated OpenTofu/Terraform Cloudflare DNS module with pinned provider, explicit public DNS allowlist and no `*.int.albandrieu.com` wildcard. Import pre-existing records into state before planning changes; do not recreate or delete unmanaged resources.
- [ ] Configure protected remote state, least-privilege API token via secret injection (never checked into Git), `fmt`/`validate`/`plan` and reviewed manual-only `apply`. Never publish state, secrets or full API payloads in CI artifacts.
- [ ] Add read-only drift detection and tests that reject publication of private names (including DefectDojo), preserving intentional public Hello exception until separately approved.

## P1 · YubiKey age / AES256 PIV management-key compatibility — BLOCKED (2026-10-17)

- [x] Validate both YubiKeys PIV82 empty (read-only), OTP2/KeePassXC and historical PIV9A preserved. Main serial `23501671`, backup serial `22916048`.
- [x] Verify software SOPS age recovery using encrypted TrueNAS backup and LUKS2 SanDisk escrow: synthetic SOPS fixture PASS; 18/18 targeted Python unittest PASS.
- [x] Identify blocker: `age-plugin-yubikey 0.5.1 --generate --slot 1` fails on backup key because PIN-protected management key uses **AES256**; the plugin reports no AES support. PIN/PUK retries remain 3/3; PIV82 remains empty. Do **not** interpret this as evidence of incorrect PIN.
- [x] Add isolated synthetic X.509 unittest scenarios: EC P-256 with expected organization, RSA rejection, EC P-256 without organization warning. No card access or hardware mutation; OpenSSL fixture generation verified locally, workstation unittest execution pending.
- [x] Prepare a read-only offline X.509 metadata inspector `scripts/workstation/inspect-age-yubikey-certificate.sh` (public EC P-256 and `O=age-plugin-yubikey` hint, exits 3 because it cannot prove PIN/touch or decrypt). Add a unittest contract; run workstation validation next.
- [ ] **P1 compatible provisioner research:** evaluate upstream [issue #92](https://github.com/str4d/age-plugin-yubikey/issues/92), upstream dependency status and safe external ECC P-256 PIV82 generation/certificate import via `ykman` without overwrites; confirm exact certificate metadata and plugin `--list-all` + actual synthetic decrypt interoperability **before** documenting an executable apply path.
- [ ] **Security gate:** do not downgrade existing AES256 management keys to TDES, reset PIV, import/overwrite PIV9A, touch OTP2, use `--force`, or retry PINs without a verified need. Keep hardware operations manual and single-card, fail closed on occupied/unknown slots.
- [ ] **P1 offsite resilience:** add separately protected offline copy of USB `recovery-identity.txt`, LUKS header backup and recovery validation. LastPass stores only references `yubikey-5-nabla principal`, `yubikey-5-nabla backup`, `USB SANDISK LUKS2`; no values in repository.
- [ ] Generate **distinct** hardware age identities for secondary and main only after compatible method is demonstrated, test each decryption independently, and then assess SOPS multi-recipient rollout including noninteractive CI paths.
- [ ] Preserve rollback: existing software X25519 age recipient and SanDisk/TrueNAS escrow remain in service until all dependent SOPS files and automation are successfully re-encrypted and restored.

Owner runbook: `docs/workstation-yubikey-gpg-vault-roadmap.md` and `docs/runbooks/sops-age-usb-disaster-recovery.md`. Keep all work in current PR #259, no automatic merge.

## OpenClaw embeddings — operator-approved fresh index strategy (2026-10-17)

- [x] Operator strict secrets audit returned exit 1 with valid object JSON; category and cause unknown.
- [x] Preflight `--audit` now emits allowlisted category counts only for recognized top-level fields and reports unknown schemas explicitly; raw findings suppressed.
- [x] Added offline classification regression tests; execution pending.
- [ ] If audit schema is unknown, inspect only structural key names/types with a reviewed sanitizer; never dump raw JSON or values. Fix findings before migration.


- [x] Operator reran strict audit: `secret_audit=findings_or_error`, `secret_audit_strict_check=true`, no configuration change. Root cause unknown because raw findings intentionally suppressed; do not label as unresolved ref without evidence.
- [x] Diagnostic preflight now reports numeric exit code and top-level JSON type only (never paths, IDs, values, or finding bodies), allowing safe first-stage triage.
- [ ] Inspect sanitized audit exit code; if JSON is valid and findings persist, implement allowlisted aggregate classification only after verifying exact audit JSON schema. No active secret/config/index changes.


- [x] Operator ran initial `check-openclaw-litellm-memory-config.py --audit`: `secret_audit=completed`, raw output suppressed, no configuration change. Initial mode did **not** pass OpenClaw's `--check`, so no claim of zero findings.
- [x] Updated reusable `--audit` to invoke `openclaw secrets audit --check --json` (no `--allow-exec`), report `secret_audit=clean` only on strict success and otherwise `findings_or_error`; no raw findings exposed.
- [ ] Rerun strict audit locally; resolve any findings through a separately reviewed diagnostic. Runtime LiteLLM file-secret resolution and source isolation remain pending.


- [x] Operator confirmed OpenClaw 2026.9.5 supports `openclaw secrets audit --json` and `--check`; `--allow-exec` is opt-in (default false). `configure`, `apply`, `reload` are potentially mutating and remain out of scope.
- [x] Reusable preflight now offers `--audit`, invoking read-only audit without `--allow-exec` and suppressing raw JSON/finding details. An audit of existing config does **not** prove a not-yet-configured LiteLLM file SecretRef resolves.
- [ ] Run `check-openclaw-litellm-memory-config.py --audit` locally and interpret outcome; test file SecretRef runtime resolution with a synthetic secret/provider in an isolated configuration before touching active config.


- [x] Operator reran updated `check-openclaw-litellm-memory-config.py --check`: `file_secret_provider_schema=compatible`, `memory_search_schema=compatible`, `virtual_key_file=private`, `target_provider=openai-compatible`, `target_model=embedding`, `target_endpoint=loopback`, `configuration_changed=false`.
- [ ] Runtime file secret reference remains `file_secret_resolution=unverified`; do not claim the `singleValue` reference ID works until tested without disclosing the key.
- [ ] Historical source isolation remains `source_reindex_guard=pending`; no index reset or source removal until proven.


- [x] Operator inspected `secrets.providers` schema: a named provider may use `source=file`, `path`, `mode=singleValue`; `memory.search.remote.apiKey` may reference `{source:file,provider,id}`. These are schema declarations, not proof of runtime secret resolution.
- [x] Extended reusable `check-openclaw-litellm-memory-config.py --check` to validate the `secrets.providers` file/singleValue shape; rerun workstation acceptance pending.
- [ ] Verify OpenClaw's documented/runtime `singleValue` secret-ref ID semantics (do not assume `id=value` works); avoid writing untested configuration or exposing key values.


- [x] Operator confirmed schema `memory.search.remote.apiKey` supports `file` secret reference with required `source`, `provider`, `id`. This validates schema shape **only**; provider identifier, file path resolution, and runtime secret-provider configuration remain unverified.
- [x] Added reusable read-only workstation preflight `python3 scripts/workstation/check-openclaw-litellm-memory-config.py --check`: checks installed schema and private key permissions, reports no secret values; does not modify OpenClaw configuration or reset indexes.
- [x] Operator ran `check-openclaw-litellm-memory-config.py --check`: `memory_search_schema=compatible`, `virtual_key_file=private`, `target_provider=openai-compatible`, `target_model=embedding`, `target_endpoint=loopback`, `configuration_changed=false`.
- [ ] Resolve `file_secret_resolution=unverified`: inspect `secrets.providers` schema and effective provider names **without displaying values**; `source_reindex_guard=pending` until source discovery is controlled. Do not assume secret `id` is a direct filesystem path.


- [x] Operator inspected installed `openclaw config schema --json`: top-level `memory.search` exists and exposes `provider`, `model`, `remote`, `outputDimensionality`, `sources`, `extraPaths`, `store`, `enabled`; this confirms property names only, not permitted values or effective runtime configuration.
- [x] Operator inspected installed schema: `memory.search.provider` supports `openai-compatible`; `remote.baseUrl`, `remote.apiKey` (string or secret ref via env/file/exec/store), `remote.batch.enabled`, `sources` (`memory`/`sessions`), `extraPaths`, and `outputDimensionality` are declared. No runtime configuration changed.
- [ ] Prepare `memory.search` target provider=`openai-compatible`, model=`embedding`, baseUrl=`http://127.0.0.1:4000/v1`, dedicated private virtual-key secret reference, sources=`["memory"]`, extraPaths=`[]`, remote.batch.enabled=false; confirm `file` secret-ref provider/id semantics and validate config locally before applying. Do not persist key material in config or git.
- [ ] To ensure a truly clean index, quarantine original `MEMORY.md` and `memory/*.md` sources in a private directory **outside indexed paths** (after verified backup) or otherwise suppress their discovery; merely setting sources=`["memory"]` does not prevent reindex. No automatic source deletion.
- [ ] Do not set `outputDimensionality=768` without verifying Ollama backend compatibility; LiteLLM local smoke already returned 768-dimensional vectors.


- [x] Operator executed `backup-openclaw-memory-markdown.py --check` and `--apply`: 2 workspaces, 617 Markdown files, `backup_verified=true`, `source_files_modified=false`. Archive checksums were verified locally; backup remains unencrypted and should be kept on encrypted private storage.
- [x] Operator ran `python3 scripts/workstation/backup-openclaw-memory-markdown.py --verify-restore`: `isolated_restore_verified=true markdown_files=617` and `active_workspaces_modified=false`; isolated archive restoration and SHA-256 verification succeeded.
- [ ] Confirm OpenClaw memory-source auto-indexing is disabled or isolated before any reset; do not delete source files or active indexes yet.

- [x] Operator permits abandoning existing and pending **index entries**: latest runtime reports main 15 files/57 chunks, vector index unverified, dirty=true; cron 0 files/0 chunks, index empty, dirty=true. Prior deep scan reported additional candidate source files (main 105, cron 63); do not assume these source files were deleted.
- [ ] Preserve existing verified private SQLite backups and source memory files. No automatic deletion of workspaces, Markdown memory, chat history or secrets.
- [ ] Confirm the effective OpenClaw 2026.9.5 embedding configuration path from local schema/package (do not use invalid `agents.defaults.memorySearch`); validate LiteLLM virtual key, model alias, budget and TLS/private routing before any reset.
- [ ] Explicit operator-controlled stop/quiesce of memory writers, then replace only agent-specific generated SQLite vector indexes after validating backup restore and target provider configuration. Avoid deleting unrelated state.
- [ ] Start with clean empty indexes, verify both agents report target provider/model and expected 768 dimensions, then run a minimal **synthetic, non-sensitive** indexing/retrieval smoke test; do not automatically ingest historical or pending documents.
- [ ] Keep rollback instructions and do not auto-merge. Full quality gate remains deferred, not waived.

- [ ] **OpenClaw memory root cause confirmed (2026-10-17)**: `memory status --deep` shows both agents requesting provider `openai` / `text-embedding-3-small`, with direct HTTP 401 `invalid_api_key` (redacted credential); main 15/105 files and 57 cached embeddings, cron 0/63. `agents.defaults.memorySearch` is an invalid config path in OpenClaw 2026.9.5. Determine valid configuration through installed `openclaw config schema`/local package, verify LiteLLM OpenAI-compatible embeddings alias and a dedicated virtual key/budget, then migrate safely without exposing API keys or forcing paid indexing. Existing FTS remains available; preserve caches and SQLite.\n- [ ] **OpenClaw embedding routing and budgets (2026-10-17)**: explain main 15/105 files (57 chunks) and cron 0/63; enumerate effective workspace memory sources without printing file content, confirm OpenClaw 2026.9.5 remote OpenAI-compatible embedding configuration, then route embeddings via LiteLLM with a dedicated virtual key, dedicated budget and model alias. Do not assume memorySearch exists under agents.defaults, do not index until auth and limits verified.\n- [ ] **OpenClaw LiteLLM budget matrix**: map actual main, cron, memory/embedding and auxiliary model routes to hashed key IDs and read-only spend/max_budget/TPM/RPM, distinguish key/team/model budgets. Observed main $10.016404/$10 reset 2026-10-19T00:00Z, openclaw $0.25612/$2, cron hashed key ID unknown, embedding key absent. No automatic budget changes or key disclosure.\n

## OpenClaw embeddings — post-PR #258 controlled handoff (2026-10-17)

- [x] Operator preflight: OpenClaw memory schema compatible; active `main` and `cron` SQLite indexes found; private embedding virtual-key file confirmed.
- [x] Workstation LiteLLM `embedding` probe returned one 768-dimensional vector. This validates API reachability and vector shape, **not** existing index/vector-space compatibility or TrueNAS LiteLLM routing.
- [x] Operator ran `prepare-openclaw-embedding-migration.py --apply`: two SQLite backups passed integrity checks; `migration_applied=false`.
- [x] Operator ran `python3 scripts/workstation/prepare-openclaw-embedding-migration.py --verify-backup`: `backup_snapshot=verified`, `sqlite_backups_verified=2`, `migration_applied=false`. This establishes private-file and SQLite integrity checks, **not** a completed isolated restore.
- [ ] Restore a copy of each backup in an isolated temporary directory, test representative read-only queries and compare schema/metadata without disclosing memory content. Do not overwrite active indexes.
- [x] Operator confirmed both `main` and `cron` currently report `provider=openai`, `model=text-embedding-3-small` via `openclaw memory status --json`; reported dimensions and indexedFiles are `null`. Slack state-migration warnings are unrelated and should not trigger configuration changes.
- [x] Operator vector status: `main` database 30384128 bytes, `vector.enabled=true`, `vector.dims=768`, `vector.index.state=unverified`; `cron` database 1748992 bytes, `vector.enabled=true`, `vector.index.state=empty`, no `dims` reported. These are runtime declarations, not independent SQLite vector verification.
- [ ] Investigate `main` unverified vector index read-only before rebuilding; determine whether `cron` has source files to index and whether empty is expected. Keep agent-specific acceptance and rollback criteria.
- [ ] Inspect actual SQLite vector dimensions, embedding metadata and any model fingerprint for **both** agents without printing indexed content; a `null` status dimension does not establish the stored dimension. `text-embedding-3-small` defaults to 1536 dimensions but supports reduced dimensions.
- [ ] Plan a **controlled reindex** for any switch from `text-embedding-3-small` to Ollama `nomic-embed-text`, even if vector dimensions match: the vector spaces are not interchangeable. Require isolated restore, model consistency and explicit operator approval before changing OpenClaw runtime.
- [ ] Establish authenticated private TrueNAS LiteLLM route with explicit trust/TLS policy, least-privilege virtual key, RPM/TPM and budget controls. Do not reuse master key; do not expose embeddings publicly.
- [ ] Test end-to-end model output and verify retrieval quality using non-sensitive fixtures before altering active OpenClaw memory configuration. Keep workload and backup rollback plans per agent.
- [ ] Perform any OpenClaw config change and reindex only with explicit operator approval; never silently discard or mix previous SQLite vectors.
- [ ] Local-first targeted validation; full repository quality gate deliberately deferred, not considered passed. No automated merge.

## P1 — Cutover catalogue historique et secrets runtime (2026-10-17)

- [x] Corriger la syntaxe du réconciliateur Gatus après introduction accidentelle de séquences littérales `\\n` dans le code Python (PR #257). Rejouer le script sur TrueNAS et ne jamais réutiliser un ancien JSON après échec de génération.
- [ ] **Décommissionner `catalog/homelab-services.json`** : identifier tous ses consommateurs, migrer les entrées/alias/URLs et intentions d'exposition utiles vers Backstage + Compose + `x-nabla` minimal et les projections générées. Ne pas supprimer physiquement le fichier tant que la parité des consommateurs, des IDs et des sondes n'est pas vérifiée. Les écarts non critiques peuvent rester suivis dans un rapport versionné ; aucun service critique ne doit disparaître silencieusement.
- [ ] **Gatus acceptation différée, non bloquante** : service HTTP/API opérationnel au dernier contrôle ; conserver la vérification des 85 moniteurs, de la stabilité des redémarrages, des 25 sondes précédemment négatives et des correspondances v2. Ne pas redémarrer ni modifier Gatus pour forcer un résultat vert.
- [ ] **Secrets runtime, prochaine vague** : appliquer `docs/secrets-migration-roadmap.md` et `config/secrets/manifest.json` comme contrat ; inventorier les sources historiques et les fichiers canoniques `/mnt/cpool/secrets/runtime/<app>/.env.secrets` sans lire les valeurs dans les logs. Prioriser Scanopy, AutoKuma, Joplin, puis Sentry/ClickHouse, FastAPI Sample et les autres services selon leurs prérequis et dépendances.
- [ ] **Acceptation secrets par service** : inventaire → staging byte-identique → contrôle permissions root-only → `env_file` canonique → test Compose → redéploiement contrôlé → smoke fonctionnel → validation de persistance après redémarrage → retrait du fichier historique seulement après backup et preuve de rollback. Préserver séparément le bootstrap Vaultwarden, ne pas lancer de rotation implicite et ne jamais supprimer les sources avant acceptation.
- [ ] **Qualité** : exécuter les tests et quality gate complète après la vague de migrations demandée ; ne pas annoncer PASS sans preuve.

- [ ] **OpenClaw memory search (17 Oct)**: main 15/105 files, cron 0/63, both dirty/vector paused; inspect resolved embedding provider, endpoint and 401 without printing credentials or forcing indexing. Do not infer the LiteLLM generic loopback provider is used for embeddings. After auth is repaired, perform bounded, operator-approved indexing and verify status.\n- [ ] **LiteLLM audit**: operator has exported `LITELLM_MASTER_KEY` for current shell; run read-only `openclaw-ops.sh --litellm-audit` and inspect budget metadata without exposing key. Avoid persisting master key or changing budgets.\n
## OpenClaw workstation P0 — heartbeat and backup hardening (2026-10-17)

- [x] Copy two historical archives, main/cron/global SQLite snapshots and private heartbeat scratch to `/media/backup/lab/infra/openclaw`; operator confirmed matching SHA-256 and NFSv4.2 source `nabla:/mnt/cpool/backup/lab`.
- [x] Keep only sanitized heartbeat scratch policy in Git; original scratch is private under NFS `recovery/`.
- [ ] Apply sanitized scratch to native `heartbeat:main` with `--expected-revision 1` after a fresh revision check; monitor subsequent heartbeat skip/error state without forcing a billable run. Do not change LiteLLM budget or disable other cron jobs.
- [ ] Review and isolate mail/CalDAV/WhatsApp/workboard operations into explicit, bounded schedules; prevent unapproved self-healing actions.
- [ ] Add native NFS backup periodic systemd timer only after runtime backup verification and security acceptance; no silent fallback to local disk.
- [ ] **TrueNAS WORM/immutability:** design retention-enforced, separately authorized immutable backup manifests and backup snapshots (ZFS snapshot holds or Object Lock where appropriate), define retention, audit deletion rights and validate independent restore path. Current SHA-256 manifests are NOT WORM.
- [ ] Validate NFS `sec=sys` exposure, access permissions and backup encryption before scheduled confidential backups.
- [ ] Isolated restore drill **deferred explicitly by operator**; do not represent backup as restore-tested.

## P1 — Diagnostics TrueNAS : présentation commune (2026-10-17)

- [x] Centraliser la présentation terminal (ANSI/NO_COLOR, icônes UTF-8, niveaux OK/WARN/FAIL/UNKNOWN) dans `scripts/lib/diagnostic-ui.sh` ; refactoriser `diagnose-fastapi-sample.sh`, `diagnose-gatus.sh` et `diagnose-resource-usage.sh` sans modifier leurs opérations de diagnostic en lecture seule.
- [x] Ajouter au diagnostic FastAPI la vérification optionnelle du SHA attendu, un résumé de sévérité, les warnings d'expiration des sondes publiques et de couverture LAN Garage et les preuves Prometheus absentes au statut UNKNOWN. Différencier catalogue LanguageTool local (doublon disparu) et consommateurs réellement synchronisés.
- [ ] Exécuter les tests ciblés `tests/test_fastapi_sample_diagnostics.py`, `tests/test_gatus_diagnostic_contract.py`, `bash -n`, ShellCheck, shfmt et la quality gate complète sur le HEAD exact de #257 ; ne pas engager de CI GitHub coûteuse ni annoncer PASS sans preuve.
- [ ] Rejouer le diagnostic coloré sur TrueNAS, comparer 3 cycles et vérifier les temps hôte/conteneur, `public.completed=2`/`timed_out=10` historiques et les preuves Gatus/Prometheus. Les 302 Cloudflare Access ne confirment pas l'origine.
- [ ] Déployer explicitement fastapi-sample PR #342 en staging avant de déclarer ses 3 sondes Garage acceptées : le relevé d'octobre 17 est encore basé sur `master` `8c4492d1`, pas la PR.

## P1 — Diagnostic FastAPI Sample TrueNAS (2026-10-17)

- [x] Rendre `scripts/truenas/update-fastapi-sample.sh` lisible (étapes numérotées, stdout Git/TrueNAS regroupés, état API/Prometheus/pfSense, avertissement `REF=master` et gitlink distinct, `build_revision=null` explicite) sans éluder les erreurs ni retirer les contrôles de sécurité.
- [x] Ajouter `scripts/truenas/diagnose-fastapi-sample.sh --cycles 3` : inventaire version SHA, trois domaines publics mesurés depuis hôte et conteneur, DNS, sondes Garage, métriques Gatus, statistiques Docker ; lecture seule et sorties assainies. Runbook : `docs/runbooks/fastapi-sample-truenas-diagnostics.md`.
- [ ] Valider sur TrueNAS le nouvel affichage avec un déploiement explicitement approuvé (le dernier `update-fastapi-sample.sh` sans REF a installé `master` `8c4492d1`, **pas** fastapi-sample #342) ; ne pas déclencher de redéploiement pour tester la présentation.
- [ ] Recueillir trois cycles du health-board avant/après installation volontaire de #342 ; corréler le budget de 4 s des 12 sondes aux temps réseau, au taux `completed/timed_out`, au CPU et aux réponses Cloudflare Access. Les mesures récentes de 0,44–0,64 s depuis le conteneur n'établissent pas de panne DNS.
- [ ] Confirmer la publication des rangs `probePriority` et la correction du doublon `languagetool` dans le catalogue canonique ; ne pas supprimer le fallback bootstrap avant acceptation complète.
- [ ] Rejouer `bash -n`, les tests ciblés et les quality gates local-first sur le HEAD intégral de #257. Ne pas merger automatiquement.

## P0 — OpenClaw workstation GitOps and recoverable backups (2026-10-17)

- [x] Inventory historical dotfiles under private `AlbanAndrieu/nabla/env/home/dotfiles/.openclaw/`: versioned heartbeat, OpenClaw configuration, gateway unit, `.env`, environment and approval material are present; old heartbeat blob could not be decoded via the connector. **No content migration or Git history scrubbing yet.**
- [x] Add canonical reviewed, comment-only workstation heartbeat at `apps/openclaw/workstation/HEARTBEAT.md`, explicit `--check|--backup|--apply` script with local private copies and hermetic unit tests. No Git push of runtime state; runtime unchanged until operator opt-in.
- [x] Document three backup tiers and restore responsibilities at `apps/openclaw/workstation/BACKUP.md`: Git for allowlisted, reviewed configuration only; encrypted offline/offsite backups for sessions, SQLite, memory and secrets; Compose service source retained separately.
- [x] Operator validated 8 targeted tests; `--apply` synchronized generic heartbeat policy and subsequent `--check` returned matching SHA-256.
- [ ] Verify actual monitor cron scratch vs main workspace and `empty-heartbeat-file` skip on installed OpenClaw 2026.9.5. Latest 3 heartbeat executions **still failed** with ~279–284 s duration despite applied policy; app logs continue to show budget 429, context pressure, embedding 401 and timeouts. Do not raise budget or infer causation from aggregate logs.
- [x] Fix idempotent backup collision when `--backup` and `--apply` run within the same second (same content hash): reuse identical snapshot, refuse unequal content; add targeted regression.
- [x] Add `scripts/workstation/audit-legacy-openclaw-git.py` to list historical tracked dotfiles without printing contents or deleting them.
- [x] Ownership decision (operator): keep private/encrypted `.env`, `gateway.systemd.env`, `USER.md`, `SOUL.md`, identities and other sensitive/personal dotfiles in `AlbanAndrieu/nabla`. **No migration/deletion/cleanup PR** for these files; `nabla-compose` owns only the sanitized generic heartbeat policy and automation.
- [ ] Audit encryption at rest and commit history for `nabla` without disclosing private content; rotate only credentials verified exposed. Do not rewrite history or retire private files by default.
- [ ] Preserve per-agent `openclaw-agent.sqlite` (main and cron) via consistent SQLite snapshot while running: test installed `openclaw backup sqlite` / `openclaw backup create`, otherwise SQLite online-backup API. Never Git-commit live SQLite/WAL/SHM; encrypt with scoped Restic retention, integrity checks and scratch restore.
- [ ] Collect sanitized LiteLLM per-key/model token and cost metrics for the OpenClaw heartbeat, fix runner/context/embedding faults, keep the current monetary budget ceiling and no unlimited fallback.
- [ ] Run local-first targeted regression, security scan and full quality gate; do not merge PR #257 automatically.

## P1 — Catalogue de criticité, sondes par unité et Watchtower (2026-10-17)

- [x] **Préparation hors homelab / PR #257** : audit read-only `scripts/security/audit-deployment-units.py --json`, schéma `catalog/deployment-unit-preview.schema.json`, unités déclaratives `truenas:garage` et `truenas:homarr`, ordre topologique de sondes, vérifications de cycles et `maxConcurrentPerUnit=1`. Sortie **préliminaire**, distincte du catalogue v2 publié ; aucune modification runtime FastAPI.
- [x] **Sécurité POC Watchtower** : remplacer le socket Docker direct par `DOCKER_HOST=tcp://docker-socket-proxy:2375`, conserver `POST=0`, autoriser seulement `IMAGES=1` en lecture, `WATCHTOWER_MONITOR_ONLY=true`, `WATCHTOWER_NO_PULL=true`, `manual-audit`. Sans image pull, la détection des nouvelles versions distantes est incomplète ; aucune mise à jour automatique possible. Tester la stratégie DIUN/HEAD registry sans Docker mutation avant activation.
- [x] **Contrats d'autorisation** : différencier `watchtowerAutoCandidate` (faible criticité opérationnelle + métier, stateless, mono-conteneur) de `watchtowerAutoEligible=false` tant qu'aucune approbation de déploiement versionnée, smoke et rollback n'existent. Gardes statiques de proxy et de labels renforcées ; tests de fixtures Python en lecture seule.
- [x] **Diagnostic ressources TrueNAS restauré dans la PR #257** : `scripts/truenas/diagnose-resource-usage.sh --all|--host|--docker` en lecture seule, sans journalisation des arguments ni secrets ; `virsh` indisponible n'est pas assimilé à l'arrêt des VM. Les PID QEMU sont rattachés aux scopes `machine-qemu-*`, les JVM et le Python observés appartiennent à des cgroups Docker ; corréler les identifiants au runtime avant de limiter la mémoire.
- [x] **Gatus runtime restauré le 17 octobre (preuve TrueNAS)** : permissions corrigées (`config` 0750, `config.yml` 0640, GID 568) ; conteneur running, exit=0, OOM=false, HTTP `/` et API statuses 200, 85 entrées. `RestartCount=7905` historique, à surveiller sans reset. Base `/mnt/cpool/gatus/gatus.db` préservée.
- [x] **Préparation migration sondes (PR #257)** : outil read-only `scripts/truenas/reconcile-gatus-catalog.py`, tests hermétiques `tests/test_reconcile_gatus_catalog.py`, runbook `docs/runbooks/gatus-catalog-reconciliation.md` ; rapprochement par `nabla_monitor_id`/`nabla_service_id`, doublons et résultats négatifs classés `investigate_probe_not_service_down`. Aucun changement de configuration Gatus ni d'état runtime. Tests et quality gate encore à exécuter.
- [ ] **Acceptation Gatus restante** : comparer les 85 identités API aux moniteurs attendus, observer stabilité/restart delta, qualifier les sondes `success=false` sans assimiler le service à DOWN ; préserver SQLite.
- [ ] **Audit transverse des sondes (17 octobre)** : classer les `success=false` Gatus par service volontairement arrêté / erreur de sonde / dépendance / incident ; examiner d'abord OpenSearch Exporter, OpenSearch Security Exporter, PostgreSQL Exporter, Home Assistant, Scanopy, SonarQube, puis les composants optionnels (Plumber, Graylog, NetBox, NPMplus). Pour chacun comparer déclaration `x-nabla`, conteneur Docker/TrueNAS, réseau, endpoint et statut attendu ; ne pas relancer ni exposer automatiquement les services.
- [x] **Relevé Docker TrueNAS du 17 octobre** : 142 conteneurs, 120 running, 22 stopped ; Gatus `Up 43 minutes`, Home Assistant et PostgreSQL healthy, OpenSearch principal et Security healthy, Dashboards running. Les jobs `postgres_upgrade` Exited(0) sont attendus. Les noms Scanopy/SonarQube/NetBox/Graylog/Plumber/NPMplus ne figurent pas dans le filtrage fourni : absence de correspondance nominale, pas preuve définitive de non-déploiement.
- [ ] **Triage runtime/Gatus par preuve (17 octobre, 85 sondes : 60 positives / 25 négatives)** : joindre le snapshot Docker complet au JSON Gatus par identifiant canonique ; ne jamais convertir automatiquement `success=false` en panne applicative. Home Assistant, PostgreSQL, OpenSearch et OpenSearch Security sont healthy au niveau Docker : investiguer d'abord les URLs, routes, authentification, codes attendus et la fraîcheur de leurs sondes. Les conteneurs d'upgrade `Exited (0)` et `homarr-sync` terminé ne constituent pas des incidents. `docker-socket-proxy` historique arrêté est distinct de `ix-docker-socket-proxy-docker-socket-proxy-1` healthy ; vérifier le DNS et le réseau effectifs de Watchtower avant tout essai manuel. Classer les services non trouvés par nom comme `not_observed`, jamais `down` sans preuve d'un service attendu.
- [ ] **Migration contrôlée des sondes vers catalogue v2** : définir pour chaque service `expectedRunning`, `deploymentUnitId`, environnement, source de vérité, `probeType`, `probeTarget`, auth attendue (sans valeur de secret), `criticality` et règle de dégradation ; couvrir d'abord Home Assistant, exporters PostgreSQL/OpenSearch, Scanopy, SonarQube, NetBox, Graylog, Plumber, NPMplus. Valider le mapping sur les 85 entrées Gatus et les jobs Prometheus avant de retirer les copies de relations v1 ou de changer les statuts FastAPI Sample.
- [ ] **Réconciliation multi-services priorisée** : pour Home Assistant (`Gatus success=false` mais Docker healthy), inspecter type/URL/méthode/authentification de sonde sans afficher les secrets ; pour OpenSearch/PostgreSQL exporters, distinguer absence de conteneur, job Prometheus et endpoint de métriques ; pour services optionnels, documenter `expectedRunning`/`monitoringPolicy` sans masquer une panne critique.
- [ ] **CI existante** : régénérer et vérifier `catalog/service-topology.json` et `catalog/services.json` sur un checkout exact pour réparer le `Pre-commit` de la PR #257 ; inspecter les autres échecs et exécuter la quality gate complète **sans suppression de vérifications**. Environnement local isolé : seulement syntaxe/tests hermétiques (L1), pas de L3.

- [x] Ajouter `apps/watchtower/compose.yml` en allowlist explicite (`WATCHTOWER_LABEL_ENABLE=true`) et `WATCHTOWER_MONITOR_ONLY=true` initialement ; **aucune mise à jour ni déploiement appliqué**.
- [x] Documenter l'unité de déploiement Garage, la séparation des trois endpoints et le plan dans [docs/watchtower-service-units.md](watchtower-service-units.md).
- [x] Remplacer Watchtower archivé par le fork maintenu `nickfedor/watchtower:1.23.1` ; isoler l'activation dans le profil `manual-audit`, mode observation globale, sans auto-update et sans déploiement TrueNAS.
- [x] Déclarer les unités `garage` (High/Stateful/Controlled) et `homarr` (Medium/Stateful/Observe) dans leurs Compose ; Homarr observé uniquement, Homarr Sync et Garage exclus ; éliminer le doublon Watchtower dans `truenas-file-structure.sh`.
- [x] Ajouter la validation locale `scripts/security/check-watchtower-unit-policy.py --check` et les tests des interdictions d'upgrade partiel, critique et stateful (tests fixtures : 7 PASS ; test intégration dépôt + gate complète encore à exécuter).
- [ ] **2026-10-17 — priorité P1 (accès runtime différé)** : auditer/réconcilier le catalogue canonique `x-nabla`, la topologie TrueNAS réelle et la roadmap FastAPI #342. Vérifier si `it-tools` et `karakeep` sont des Apps TrueNAS non gérées par Compose (ne pas inventer des définitions). Préparer `deploymentUnitId`, `operationalCriticality` (depuis `x-nabla.criticality`), `businessCriticality` BIA, `stateful`, `upgradePolicy`, `probePolicy` et l'ordre des dépendances ; ne pas substituer le catalogue v1 transitoire au canonique.
- [ ] Exporter les nouvelles métadonnées des blocs `x-nabla.deploymentUnit` par le générateur `scripts/generate-service-topology.py` et les schémas JSON, recalculer le catalogRevision ; synchroniser FastAPI Sample #342 par un cutover v2 **coordonné** et versionné, sans shim v1/v2 permanent. Grouper `garage`, `garage-admin`, `garage-webui` dans **une unité de budget/ordonnancement**, garder trois résultats par endpoint, un cache TTL/singleflight, une file équitable et des dépendances ; préserver les 2 slots de rotation anti-famine et les contraintes locales 12 sondes.
- [ ] Tester la règle d'upgrade « une unité Compose = une décision » ; autoriser l'auto-update uniquement si la **criticité opérationnelle ET métier** sont Low, `stateful=false`, déploiement monocomposant et backup/smoke/rollback validés. Examiner `it-tools` comme candidat après preuve de propriété runtime, `karakeep` en observation jusqu'à audit des données, `homarr` en observation seulement et `homarr-sync` exclu.
- [ ] Évaluer les risques du socket Docker et la maintenance du projet Watchtower archivé, puis ajouter préflight/backup/smoke/rollback manuel avant toute activation de l'automatisation.
- [ ] Exécuter quality gate locale et contrats FastAPI/Nabla sur le schéma partagé, puis tests runtime en lecture seule ; pas de merge ni redéploiement sans approbation.

## P1 — Catalogue homelab v1 : identité unique et `probePriority` (2026-10-17)

Contexte : fastapi-sample [#342](https://github.com/AlbanAndrieu/fastapi-sample/pull/342) (HEAD `748497d6`) rejette le catalogue distant pour l'identifiant dupliqué `languagetool` ; FastAPI Cloud, TrueNAS et la workstation retombent sur le catalogue embarqué.

- [x] **Source du doublon** : `catalog/homelab-services.json` est édité à la main (aucun générateur). L'entrée `id: languagetool` (#232) a été ajoutée sans retirer « Language Tool » (#64, id dérivé `languagetool`). Fusion en une seule entrée `languagetool` : identité/sonde `x-nabla`, route publique `https://languagetool.albandrieu.com` conservée car observée le 17/10 (302 vers Cloudflare Access).
- [x] **Identifiants explicites** : les 59 autres entrées sans `id` reçoivent l'identifiant que fastapi-sample dérivait déjà (`_derive_service_id`), donc sans changement d'identité côté consommateurs. Test `tests/test_homelab_catalog_identity_contract.py` : `id` explicite obligatoire, `id` et `name` uniques sans tenir compte de la casse.
- [x] **Preuve d'acceptation** : `HomelabCatalog.model_validate(_apply_exposure_overrides(...))` depuis un checkout local de fastapi-sample `748497d6` → master : `duplicate homelab service id: languagetool` ; branche : 89 services, `priority_source=catalog`.
- [x] **`probePriority`** publié dans `catalog/homelab-exposure-overrides.json` (schéma `catalog/homelab-exposure-overrides.schema.json`, entier 0–1000, rangs uniques), ordre embarqué de fastapi-sample conservé : garage 0, garage-admin 1, garage-webui 2, postgresql 3, vaultwarden 6, sentry 7, prometheus 8, grafana 9, n8n 10. Non dérivé de `criticality`. Disposition v2 : intégré au `probePolicy` des unités de déploiement (PR #257), qui ne porte qu'un `probeOrder` interne à l'unité, cohérent avec ces rangs (test).
- [ ] **Rangs réservés sans entrée catalogue** : `redis` (4), `cloudflared` (5), `pyroscope` (11) sont absents de `homelab-services.json` et n'ont pas été ajoutés. Acceptation : entrée réelle avec `id` explicite (ou cutover v2), rang publié, `EXPECTED_PRIORITIES` mis à jour.
- [ ] **Adoption runtime après merge** : acceptation = `priority_source=catalog` et catalogue distant (pas de repli embarqué) sur FastAPI Cloud, TrueNAS `:8091` et la workstation ; ensuite seulement, retrait de `_PRIORITY_SERVICE_ORDER` dans fastapi-sample.
- [ ] **Intention d'accès LanguageTool** : Access est observé mais `cloudflareAccessRequired` n'est pas déclaré. Acceptation : intention déclarée et vérifiée par une preuve Access côté edge, sans modifier la règle Cloudflare.
- [ ] **Identités legacy divergentes** : les `id` figés (ex. `ittools`, `adguardhome`, `hello-int`) reprennent la dérivation v1 et peuvent différer des `x-nabla.id`. Acceptation : réconciliation dans le cutover v2 (`audit-service-catalog-v2-parity.py`), sans renommage isolé côté v1.
- [ ] **Tests déjà en échec sur master** (inchangés par ce lot) : `test_public_ingress_contract` (Garage `Garage S3` contre `Garage S3 API`, audit DNS `.int`) et `test_synthetic_open_schema_generation` (24 contre 26 expositions publiques, 24 contre 25 contrôles Access). Acceptation : suite verte, avec correction de la cause et non des seuils.
- [ ] **Egress lent du conteneur fastapi-sample (TrueNAS)**, diagnostic en lecture seule : 12/12 sondes publiques en `deadline` sur 4 s, posture pfSense 6 s, alors que la cible pfSense est sur le LAN. Hypothèse principale (non prouvée) : délai du résolveur DNS (embedded Docker → `172.17.0.1`, puis `9.9.9.9`/`1.1.1.1`) plutôt que le chemin WAN. Le conteneur n'a pas de `dns:` explicite, route par défaut sur `sample-observer` (`gw_priority: 1`). Acceptation : mesure de l'étape 4 de la PR #342 (`dns`/`connect`/`tls` + `/etc/resolv.conf`) ; correctif dans une PR séparée seulement si une phase est prouvée lente ; sondes publiques terminées sous 4 s.
- [ ] **`cloudflare_tunnels_observed=0` avec `cloudflare_configured=true`** : `configured` ne prouve que la présence des variables `CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN`. L'observateur coupe à 4 s (`_OBSERVER_TIMEOUT_SEC`) et renvoie une liste vide sur timeout ; la lecture Cloudflare mesurée dépasse ce budget, donc cause probable = même lenteur réseau/DNS. Acceptation : lire `tunnel_observer_state`/`tunnel_error` (sans secret) ; `TimeoutError` → item egress ; `403`/authentification → permission `Account > Cloudflare Tunnel: Read` ou compte du token ; cible `tunnels_observed ≥ 1`, `tunnel_error=null`.

## P0/P1 — YubiKey / GnuPG / Vault PKI (2026-10-16)

- [x] Diagnostiquer les deux clés KeePassXC sur slot OTP 2, réponses HMAC identiques.
- [x] Préparer un diagnostic GnuPG/PCSC en lecture seule : `scripts/workstation/diagnose-gpg-smartcard.sh --check`.
- [ ] **P0** Corriger `gpg --card-status: No such device` sur GnuPG 2.4.8 malgré `disable-ccid`, avec tests sur les deux clés et retour arrière.
- [ ] **P0** Protéger la clé de signature Git / git-crypt et les sous-clés de déchiffrement PostgreSQL; valider une restauration isolée avant toute migration de clés sur carte.
- [ ] **P1** Créer une nouvelle CA racine hors ligne compatible Vault PKI intermédiaire; l'ancienne CA slot 9A est expirée, `CA:TRUE,pathlen:0`, à préserver pendant l'audit.
- [ ] **P2** Étudier SSH FIDO2, PAM U2F dual-key, age-plugin-yubikey et GNOME Keyring.
- **Détails et critères d'acceptation :** [roadmap YubiKey / GPG / Vault](workstation-yubikey-gpg-vault-roadmap.md).

## P0/P1 — Reprise PR #255 : Gatus, diagnostics ressources et import FreshRSS sûr (mise à jour 2026-10-15)

- [x] Préserver le script de récupération Gatus et son test de formatage ; ne pas confondre le préflight avec une acceptation runtime (App précédemment STOPPED, HTTP 8085 indisponible).
- [ ] **P0 Gatus runtime** : les commandes de diagnostic récentes ont été exécutées dans un environnement qui n'est pas le TrueNAS attendu : `/mnt/cpool/compose/nabla-compose` absent, `docker inspect gatus` sans conteneur et `midclt` absent. Ne pas appliquer de chmod dans ce contexte. Se connecter au shell TrueNAS, découvrir le vrai chemin du dépôt/app et identifier le conteneur via `docker ps -a`/`midclt`; vérifier `GroupAdd=568` et le montage exact `/config` avant toute réparation. Préserver `/mnt/cpool/gatus/gatus.db`. Accepter HTTP, endpoints et Prometheus après rétablissement.
- [x] **P1 garde-fou FreshRSS** : interdire `--apply` et `--import-opml` lorsque l'OPML épinglé ne compte pas exactement dix sources ; corriger le chemin temporaire d'import. Les 78 flux du site ne doivent pas entrer accidentellement dans les comptes `securitypublic` et `securityagent`.
- [ ] **P1 implémentation suivante** : produire un OPML filtré par les dix URLs explicitement approuvées (et tester l'égalité des ensembles URL, pas uniquement la cardinalité), sauvegarder FreshRSS, vérifier l'idempotence de l'import puis accepter via GReader avant autorisation runtime. **Ne pas importer les 78 flux sans arbitrage explicite**.
- [ ] **P0/P1 télémétrie et CrowdSec** : l'audit Prometheus fourni le 15 octobre confirme `scrape_down` pour Gatus, FastAPI Sample et PostgreSQL exporter ; Redis, pfSense et CrowdSec sont `scrape_up` ; Cloudflare `not_declared`. Exécuter l'audit depuis un réseau qui atteint réellement Prometheus, puis diagnostiquer sans régénération de secrets ni faux statut DOWN applicatif. Le script CrowdSec exige `midclt` et doit être exécuté sur TrueNAS, pas la workstation.
- [x] **P0 CI GitHub** : Pre-commit et CodeQL de la PR #255 réussis sur le commit `641f090857cfadbd84701b135ff6cc3e62880aee` (14/10/2026).
- [ ] **P0 quality gate locale** : exécuter les contrats concernés dans un checkout complet avec dépendances installées ; CI verte ne remplace pas les preuves runtime, aucun merge automatique.
- [x] **P0 diagnostic ressources** : ajouter `scripts/truenas/diagnose-resource-usage.sh` — snapshot en lecture seule des processus CPU/RSS, mémoire, disques, `docker stats` et états des conteneurs ; il tolère l'absence de Docker/midclt sur la workstation.
- [ ] **P0 resource baseline** : exécuter le script sur TrueNAS et conserver les sorties CPU/mémoire/IO sans environnement ni secrets ; corréler avec les cibles Prometheus indisponibles avant de redémarrer quoi que ce soit.

## P1 — Cloudflare DNS/Tunnel as code et réconciliation Garage (2026-10-13)

- [x] Marquer **Garage Admin API :3903** comme strictement `external=false` dans le catalogue canonique et les overrides ; **Garage Web UI :3909** demeure temporairement accessible à distance.
- [ ] Migrer les zones/records DNS Cloudflare approuvés et les routes `cloudflare_zero_trust_tunnel_cloudflared_config` pertinentes vers Terraform/OpenTofu sous contrôle de version, avec import des ressources existantes, `plan` sans destruction et gestion des secrets hors Git. Vérifier les noms et ressources selon la version exacte du provider Cloudflare.
- [ ] Rapprocher `terraform plan -refresh-only` / état API Cloudflare avec le catalogue : hostname, type DNS, cible Tunnel, `service` origin URL/port, règle Access et propriétaire de la route. Un plan sans changement n'établit pas à lui seul l'absence de drift hors périmètre géré.
- [ ] Comparer séparément Cloudflare Tunnel, HAProxy pfSense, NAT, Traefik et sondes externes réelles ; Terraform Cloudflare ne découvre pas les routes pfSense non gérées.
- [ ] Identifier quel hostname sert réellement la **WebUI** (image `garage-webui`, port :3909) et lequel cible les **API** (:3903 Admin, :3900 S3). Retirer toute exposition publique de l'Admin API et de S3 sans retirer par erreur l'accès distant temporaire à la WebUI.
- [ ] Valider l'accès LAN des API privées depuis FastAPI sur TrueNAS/workstation et détecter toute exposition Internet inattendue avec une sonde outside-in distincte. Le badge bleu indique la politique déclarée, pas une isolation prouvée.

- [x] **FreshRSS OPML canonique épinglé (sources)** : `scripts/truenas/freshrss-ops.sh` référence directement `apps/nabla-site-alban/data/security/security-feeds.opml` (gitlink vérifié, sans fetch). La sélection de 10 flux est un vestige du POC, **pas** une politique de filtrage ; import manuel futur des 78 flux uniquement après préflight et validation. Les OPML/JSON de 10 sources dans `config/freshrss/` sont historiques et ne pilotent plus le script d'import.
- [ ] **Acceptance FreshRSS** : contrôler l'existence du submodule sur TrueNAS, confirmer le comportement d'import incrémental de la version installée, sauvegarder la base, inventorier les abonnements actuels des deux comptes, puis exécuter un import approuvé et vérifier le résultat via GReader ; ne supprimer aucun abonnement silencieusement.
- [ ] **P1 — FreshRSS et OPML Site Alban canonique** : les 10 sources `config/freshrss/security-sources.json` sont déjà incluses dans les 78 flux de `nabla-site-alban/data/security/security-feeds.opml` (comparaison vérifiée). Après validation/merge de la PR Site Alban #221, mettre à jour le gitlink `apps/nabla-site-alban`, rendre bloquant `python3 scripts/security/audit-freshrss-opml-source.py --strict` et générer l'OPML FreshRSS par filtrage explicite des dix URL ; interdire un import automatique des 78 sources et préserver les comptes `securitypublic`/`securityagent`.
## P1 — Clarifier les rôles Garage et préparer un accès privé à la WebUI (2026-10-13)

- [x] Distinguer explicitement **Garage S3 API :3900**, **Garage Admin API :3903** et **Garage Web UI :3909** dans le catalogue et le Compose source, sans fusionner les identités de composants.
- [ ] Auditer les hostnames publics et les origines réelles du tunnel Cloudflare : la WebUI est déclarée sur `garage.albandrieu.com` mais ce nom a répondu comme une API S3 ; `garage-admin.albandrieu.com` affiche une UI selon un test navigateur utilisateur alors que sa destination déclarée est l'API Admin :3903. Confirmer les routes effectives avant de modifier les hostnames ou leurs permissions.
- [ ] Corriger l'association entre UI et hostname *après* inspection des origines, puis ajouter un contrôle de non-régression refusant une réponse XML S3 sur l'URL WebUI.
- [ ] Conserver provisoirement une **WebUI Garage accessible depuis l'extérieur**, protégée par authentification/Cloudflare Access ; sa cible à terme est **LAN/VPN uniquement**. Évaluer Tailscale/WireGuard ou un autre accès distant privé avec ACL, MFA et traçabilité ; documenter une bascule réversible pour publier/dépublier les services.
- [ ] Ne jamais exposer volontairement l'API S3 `s3.int.albandrieu.com` sur le WAN ; distinguer la politique privée de la preuve réseau réelle, tout en validant les consommateurs OpenTofu.
- [ ] Contrôler les liaisons entre noms dans les overrides, le catalogue FastAPI distant et le fallback `nabla-site-alban` ; ne pas supposer qu'une API admin est une interface utilisateur.

## P1 — Lever l'ambiguïté Garage Web UI / Admin API (2026-10-13)

- [x] Normaliser les libellés de catalogue : `Garage Web UI` (:3909), `Garage Admin API` (:3903), `Garage S3 API` (:3900), sans renommer les identifiants de services.
- [ ] Auditer les origines *actives* Cloudflare Tunnel pour `garage.albandrieu.com` et `garage-admin.albandrieu.com`. Selon le constat utilisateur, le premier présente actuellement une réponse XML S3, le second une UI ; identifier le conteneur/port réellement desservi sans supposer que le hostname décrit l'origine.
- [ ] Faire correspondre les URL publiques aux fonctions réelles après validation, puis aligner le catalogue et les liens du site. Documenter l'authentification, les ACL et les preuves d'absence d'accès anonyme à l'administration et aux données S3.
- [ ] Politique cible : Garage Web UI privée (LAN ou réseau overlay). Exception transitoire validée : garder un accès extérieur à l'UI tant qu'un accès distant ergonomique et sécurisé (par exemple Tailscale/WireGuard avec SSO/MFA et ACL) n'est pas disponible ; ne pas rendre les API S3/Admin publiques par simple commodité.
- [ ] Comparer les options de bascule rapide exposition publique / accès privé dans le catalogue, Cloudflare Access/Tunnel et Tailscale, avec rollback et contrôles outside-in.
- [ ] Exécuter les tests de catalogue, réconciliation et publication locaux avant merge ; préserver les identités historiques `garage`, `garage-admin`, `garage-webui` pour les consommateurs existants.

## P1 — Audit de dérive DNS public, HAProxy et Garage (2026-10-12)

- [ ] Auditer en lecture seule les enregistrements publics A/AAAA/CNAME de `*.int.albandrieu.com` contre `config/public-int-dns-exceptions.txt`, sans assimiler l'absence de DNS à l'absence d'exposition par IP/Host/SNI.
- [ ] Croiser la configuration *active* des frontends, backends, ACL Host/SNI et NAT pfSense/HAProxy avec Traefik, Cloudflare Tunnel et la topologie canonique ; marquer tout écart non autorisé comme drift.
- [ ] Réutiliser/améliorer les contrôles existants `tests/test_public_ingress_contract.py`, `scripts/truenas/check-homelab-services.sh` et les scripts d'audit ingress existants ; produire un rapport JSON stable avec `declared`, `observed`, `reason`, `evidence`, sans secrets ni corrections automatiques.
- [ ] Confirmer la suppression effective des DNS publics et accès WAN de `s3.int.albandrieu.com` et `vaultwarden.int.albandrieu.com`, tout en conservant la résolution LAN et en validant OpenTofu avant retrait des routes actives.
- [ ] Auditer les deux hostnames `garage.albandrieu.com` et `garage-admin.albandrieu.com` : le premier renvoie actuellement une erreur XML S3 selon l'observation utilisateur, signe d'une mauvaise destination possible ; le second fournit une UI, mais le port réel du backend Cloudflare est à vérifier. Comparer les origines attendues : S3 `:3900`, Admin API `:3903`, WebUI `:3909`. Ne pas exposer l'API S3 ni conclure à une UI sur la seule base du nom DNS.
- [ ] Conserver `hello.int.albandrieu.com` comme canari public intentionnel HAProxy → Traefik ; contrôler son périmètre sans lui appliquer la politique des services privés.
- [ ] Faire fonctionner des sondes LAN sur TrueNAS et workstation pour les services `external=false` et une vérification outside-in indépendante depuis FastAPI Cloud ; affichage bleu « Interne » pour la *politique*, vert pour la *santé*, warning pour l'exposition inattendue.

## P1 — DefectDojo : ingestion locale, sans proxy (2026-10-12)

- [x] L'importeur `scripts/security/import-scan-defectdojo.sh` cible
  `http://127.0.0.1:31085/api/v2/reimport-scan/` **depuis TrueNAS**,
  avec `curl --noproxy '*'`, interdiction de redirection et garde
  de présence du checkout TrueNAS. Ni failover LAN ni WAN.
- [ ] Valider en lecture seule le bind réel du port, la configuration
  NAT/ACL pfSense, Traefik et Cloudflare; ne pas inférer l'absence
  d'exposition Internet de l'adresse interne déclarée.
- [ ] Premier import : utiliser produit/engagement existants,
  scan non sensible et jeton dédié; vérifier le traitement final
  de l'import et la déduplication avant toute planification cron.

## P1 — Bootstrap de jetons FreshRSS sans exposition CLI (2026-10-12)

- [x] Ajouter `scripts/security/freshrss-greader-auth.py` pour
  récupérer `Auth` via `ClientLogin` **dans le corps HTTPS POST**,
  en forçant TLS, origine fixe, refus des redirections et bornes de taille.
  Aucune valeur de secret n'est imprimée ni passée sur `argv`.
- [x] Autoriser uniquement `securitypublic` (Vercel) et
  `securityagent` (MCP privé) ; comparer **exactement** dix abonnements
  GReader à `config/freshrss/security-sources.json` avant d'écrire
  atomiquement les tokens `root:root 0600` dans le pool secret 0700.
- [x] Fournir `--check` sans lecture de secret ni réseau, `--verify`
  lecture seule, `--apply` explicitement approuvé, et tests offline
  `tests/test_freshrss_greader_auth_contract.py`.
  **État des tests : à exécuter** lors de la quality gate ; ne pas
  confondre code livré et acceptation runtime.
- [ ] Après sauvegarde TrueNAS et création des utilisateurs via
  `freshrss-ops.sh`, exécuter `--apply` pour les deux comptes,
  puis `--verify`, avec preuve de zéro abonnement non approuvé.
- [ ] Injecter par canal protégé des jetons **distincts** :
  `securitypublic.greader-auth` vers Vercel serveur uniquement,
  `securityagent.greader-auth` vers le MCP local. Aucun token
  dans des Terraform states, PR, console ou dossiers publics.
- [ ] Activer la publication du site **seulement** après le test
  fonctionnel des flux, Playwright/ZAP, approbation privacy, et
  validation du profil Cloudflare Access. Ne jamais ouvrir DefectDojo
  pour cette opération.

## P1–P3 — Site Alban Helm, Cloudflare IaC et secrets (décisions du 12 octobre 2026)

- [ ] **P1 — Build OCI Site Alban** : créer un Dockerfile Next.js standalone multi-stage, utilisateur non-root, FS en lecture seule avec volumes temporaires si nécessaires ; construire linux/amd64, SBOM CycloneDX, provenance SLSA, signature d'image, scans Trivy/grype ; publier sur GHCR uniquement après quality gates avec digest immutable `@sha256:` ; **Vercel reste la production principale**, pas de bascule DNS implicite.
- [ ] **P1 — Helm chart et Helmfile pour Talos/K8s** : chart versionné `nabla-site-alban`, values `homelab` sans secret, helmfile avec image épinglée, Ingress Traefik **interne uniquement**, PodSecurity restricted, non-root, seccomp RuntimeDefault, drop ALL, ServiceAccount token off, NetworkPolicy egress contrôlé, probes, resources, rollout et rollback ; finaliser runtime de Next.js et TLS interne avant apply. Le script expérimental `scripts/talos/deploy-site-alban.sh` reste une maquette jusqu'au remplacement par le chart.
- [ ] **P1 — Gate Helm sécurisée local-first** : `helm lint --strict`, `helm template` déterministe, `helmfile template`, validation kubeconform sur version du cluster Talos, schema values, chart-testing (`ct lint`), Checkov ou Trivy config/misconfig avec exceptions tracées, tests helm-unittest des securityContexts/NetworkPolicies ; tester rendu offline en CI **avant** tout pipeline de déploiement, sans contournement des gates SAST/ZAP existantes.
- [ ] **P1 — Cloudflare Terraform/OpenTofu** : créer `terraform/cloudflare/` (versions verrouillées, variables non sensibles, import/découverte des objets existants) ; gestion déclarative des **tunnels existants** et des public hostnames, DNS et politiques Access ; **attendre la liste des applications Access et leurs IDs fournie par l'opérateur** avant import ou changement ; `plan` seul par défaut, `apply` à approbation manuelle et état chiffré externalisé ; aucun tunnel/route créé par supposition.
- [ ] **P1 — Accès CI DefectDojo via Cloudflare Access** : après import des ressources existantes, ajouter la route autorisée `defectdojo.albandrieu.com` (si validée) via tunnel existant ; politique distincte UI humaine / API service, avec contrôle des chevauchements de chemins, Service Token dédié ; provisionner `CF_ACCESS_CLIENT_ID` et `CF_ACCESS_CLIENT_SECRET` dans environnement GitHub protégé seulement après création et validation ; ne pas les présumer existants.
- [ ] **P2 — MCP Cloudflare local** : `.mcp.json` déclare le MCP officiel `https://mcp.cloudflare.com/mcp`, OAuth interactif et moindre privilège ; activer en lecture seule en première phase, laisser les changements de configuration à Terraform et à la revue de plan ; pas de token Cloudflare commité.
- [ ] **P2 — DefectDojo simple** : conserver un **jeton API dédié DefectDojo** dans les secrets d'environnement GitHub pour ingestion/lecture selon RBAC ; rotation manuelle documentée avec test avant révocation, sans ajouter une GitHub App ou un moteur de rotation Vaultwarden à ce stade.
- [ ] **P3 — Flux RSS sécurité et OPML** : clarifier les deux sources actuelles : `nabla-site-alban/public/ciso-rss-feeds.json` pour la page historique, `nabla-compose/config/freshrss/security-sources.json` et OPML à 10 sources pour la nouvelle chaîne FreshRSS ; ne remplacer le JSON du site qu'après migration, tests de contrat, sans dépendance directe navigateur à une API privée.

### Architecture cible

`GitHub (build/gates) → GHCR (image signée/digest) → Helmfile → Talos/Kubernetes (Ingress interne)` ; **Vercel conserve le service public de référence**.
`Terraform/OpenTofu → Cloudflare Tunnel existant + Access + DNS` après import, approbation et validation de la liste des applications.
`GitHub Actions master (secrets protégés) → Cloudflare Access Service Auth → Tunnel existant → DefectDojo API` ; aucun accès DefectDojo anonyme ni port LAN ouvert sur WAN.

## P1/P2 — FreshRSS/SBOM/DefectDojo : reprise après merge (2026-10-12)

- [x] **Sources préparées** : scripts `scripts/truenas/freshrss-ops.sh`
  (`--check` lecture seule, `--apply` explicite, `--import-opml`
  séparé), compte FreshRSS `securitypublic` + `securityagent`,
  copies du manifeste `config/freshrss/security-sources.json`
  et de l'OPML à dix sources. **Compte/instance non modifiés**.
- [x] **MCP local préparé** : `.mcp.json` →
  `scripts/mcp/freshrss_readonly.py`, stdio sans HTTP entrant,
  deux outils de lecture, filtrage des sources par ID/URL, jeton
  propre au compte `securityagent` ; tests unitaires hors-ligne.
  À distinguer d'un serveur upstream HTTP avec outils d'écriture.
- [x] **Scan privé préparé** :
  `scripts/security/generate-homelab-sbom.sh` produit CycloneDX
  et rapport SCA Trivy sur image **@sha256 immuable**, non-root,
  sortie privée 0700/0600, sans Docker socket brut ;
  `scripts/security/import-scan-defectdojo.sh` ingère via
  `/api/v2/reimport-scan/` interne TrueNAS, identité ingestion
  distincte, engagement existant, réponse non journalisée,
  `auto_create_context=false`, `verified=false`,
  `close_old_findings=false`. **Aucun import effectué**.
- [x] **Runbooks et passation** :
  `docs/freshrss-security-runbook.md`,
  `docs/defectdojo-private-scan-ingestion.md`,
  `docs/roadmap.md`. Les deux PR #254 et site-alban #220
  peuvent être mergées **uniquement selon leurs quality gates** ;
  merge de source ≠ activation runtime.
- [ ] **P1 runtime** : confirmer conteneur FreshRSS réel/UID, état
  API/stockage, sauvegarde et secret paths 0600; préflight sans
  modification puis activation CLI opt-in. Les usernames FreshRSS
  doivent être **alphanumériques** : remplacer tout ancien
  `security-public` par `securitypublic`.
- [ ] **P1 acceptance** : activer API GReader de manière contrôlée,
  compter 10 sources publiques par identité, tester authentification
  Cloudflare Access si pertinente ; aucun compte personnel exposé ;
  connecter MCP par stdio aux seuls agents approuvés.
- [ ] **P1 Next.js** : passer la CI incluant
  Playwright/ZAP/CodeQL/Semgrep ; activer Vercel avec les secrets de
  `securitypublic` après recette, vérifier `/security-feed.xml`
  et `/api/ciso/threat-feed`; garder la publication désactivée
  jusqu'alors.
- [ ] **P2 scan et ingestion** : épingler et vérifier versions
  Syft/Trivy à l'exécution ; préflight sur une image non critique ;
  scanner localement et importer après approbation sous produit et
  engagement DefectDojo réel, vérifier parsing/déduplication finale.
  Aucun endpoint DefectDojo WAN nécessaire.
- [ ] **P3 CTID/DefectDojo** : construire un export privé
  read-only filtré/agrégé et revu, jamais exposer les findings bruts,
  noms/versions des actifs, PII et API DefectDojo au navigateur.
- [ ] **Qualité restantes** : bash -n, ShellCheck, unittest MCP,
  contrats JSON/OPML, protection des secrets, CI et acceptation
  homelab *NOT RUN* tant que non constatées.

**Ordre de reprise :** stabilité & sauvegardes → FreshRSS CLI →
abonnements API → MCP → site en preview → publication publique
approuvée → SBOM/SCA/DefectDojo privé → CTID authentifié.
Ne pas laisser les nouveautés FreshRSS devenir un bloqueur des
priorités P0 existantes. Les scripts n'effectuent rien sans opt-in.

## P1/P2 — FreshRSS, SBOM et CTI/DefectDojo pour la veille CISO (2026-10-12)

**Chaîne cible :** services déclarés/réellement déployés → inventaire privé et
SBOM → SCA / vulnérabilités vérifiées → DefectDojo → projection publique
approuvée → Next.js CTID/CISO. En parallèle : sources CERT/KEV/CVE →
FreshRSS → actualités classées mais **non présentées comme findings confirmés**.

### P1 — Activer FreshRSS et qualifier les flux publics

- [ ] Diagnostiquer l'App TrueNAS FreshRSS (status, uid/gid, volumes,
  health, TLS/Cloudflare Access, réseau, backups) **en lecture seule**,
  sans redémarrage prématuré ni exposition WAN supplémentaire.
- [ ] Après acceptation, activer le compte FreshRSS `securitypublic` dédié
  exclusivement aux **10 abonnements publics** de
  `nabla-site-alban/public/ciso-security-sources.json`. Import OPML
  à proposer; ne jamais mélanger le compte personnel et un compte publiable.
- [ ] Valider API Google Reader `/api/greader.php/reader/api/0/stream/contents/reading-list`
  sur compte dédié, lecture seule par convention, secret API runtime
  séparé (pas de `NEXT_PUBLIC_`, ni dans le catalogue), politique
  Cloudflare Access *service token* et redirections interdites.
- [ ] Autoriser l'appel sortant Vercel→FreshRSS uniquement après revue
  de la frontière réseau, de la rétention et de l'anonymisation.
  Contrôler la publication **zéro PII/hostname/IP/version**, cache,
  réponse 503 si non configuré, refus 5xx sans fuite de secret.
- [ ] Vérifier FreshRSS en tant qu'agrégateur RSS/Atom, catégories,
  filtres, marquage/favoris, OPML import-export, partage natif HTML/RSS/OPML,
  et API mobile ; choisir **une seule surface de publication contrôlée**.
  MCP communautaire non requis pour le site; ne pas exposer MCP public.
- [ ] Synchroniser la sélection de flux avec les deux pages Next.js
  `/ciso`, `/ctid` et `/security-feed.xml`, en conservant
  `/feed.xml` historique intact. Valider Playwright, ZAP et accessibilité.

### P2 — SBOM automatisés et findings DefectDojo

- [ ] Construire un job `inventory-sbom` non privilégié, sans
  `/var/run/docker.sock` brut : syft/trivy (versions épinglées),
  SBOM **CycloneDX JSON** (plus SPDX si utile), hash, timestamp,
  propriétaire/service ID, provenance SHA/image digest,
  environnement (planned ≠ running). Exclure caches, secrets et PII.
- [ ] Collecter aussi npm/pip/Go/container digests des repos et
  TrueNAS/Talos/K8s via API read-only approuvées et snapshots,
  sans scan agressif de LAN ; réconcilier aux entités Backstage et
  `catalog/services.json`, avec CPE/purl, versions et criticité
  **seulement dans le catalogue privé**.
- [ ] Scanner les artefacts avec Trivy/Grype et/ou Dependency-Track,
  enrichir par OSV, NVD et CISA KEV. Dédupliquer par
  `service + purl/CPE + CVE + version + environnement` et gérer les
  corrections, VEX et faux positifs.
- [ ] **Déterminer l'édition DefectDojo installée** avant de choisir l'API SBOM.
  L'API OSS `/api/v2/import-scan/` accepte notamment les parsers
  `Syft`, `CycloneDX`, `Trivy`, `Anchore Grype` et `Generic Findings Import`.
  Le parseur SBOM peut créer des entrées d'inventaire **Info** sans
  vulnérabilités. L'endpoint Asset/Locations `/api/v2/sbom-import/`
  est documenté pour **DefectDojo Pro** et ne doit pas être présumé
  disponible sur l'instance OSS. Vérifier en sandbox les types de scan
  réellement installés et préférer un flux SBOM + résultats scanner
  séparés, sans dépendre des fonctions Pro non autorisées.
  Docs : https://docs.defectdojo.com/supported_tools/parsers/
  et https://docs.defectdojo.com/supported_tools/parsers/file/syft/
- [ ] Ingérer vers l'API **DefectDojo /api/v2/import-scan/** via
  compte/token ingestion *scoped* dédié, TLS vérifié, egress restreint,
  secrets pool ZFS runtime 0600, suppression des payloads logs, imports
  idempotents et `close_old_findings` validé avant activation;
  tests sur environnement de démonstration avant la production.
  **Un SBOM seul n'est pas un scan de vulnérabilités** : vérifier
  les parsers/formats effectivement disponibles, ne pas le déclarer
  importable sans test.
- [ ] Enrichir les findings avec preuves et confiance :
  `verified / potential / informational`, sévérité du scanner,
  EPSS/KEV, exploitabilité et statut correction, sans
  requalifier une *headline* RSS en vulnérabilité confirmée.
- [ ] Publier vers Next.js **uniquement un agrégat allowlisté**
  (approuvé, horodaté, sans identifiants internes, détails
  d'attaque, données personnelles ou CVE contextuels sensibles).
  Préférer CTID interne authentifié pour les vrais findings :
  **aucun accès navigateur direct à DefectDojo**.
- [ ] Tests de contrat d'export, fuite de secrets, RBAC, revue STRIDE,
  rollback de job, dashboards Prometheus/Grafana (couverture SBOM,
  âge, taux de mapping, ingestion, faux positifs), puis acceptance.

**DORA :** règlement UE 2022/2554, art. 5-16/10 (gestion/détection des
risques TIC) et art. 45 (dispositifs volontaires de partage CTI).
Un site de veille public n'établit pas à lui seul la conformité DORA;
le champ d'application dépend de la qualité d'entité financière concernée.
Référence : https://eur-lex.europa.eu/eli/reg/2022/2554/oj

**Dépendances et ordre :** phase FreshRSS P1 après stabilité des services
socles et secrets; inventaire/SBOM/DefectDojo P2 seulement après
acceptation DSOMM/DefectDojo. Publication CTID authentifiée P3 après
privacy review; ne pas déployer automatiquement par cette PR.

## POC Hermes DevSecOps Zero Trust — implémentation isolée (2026-10-11)

- [x] **POC source publié, pas de déploiement** : [Compose profil `hermes-poc`](../poc/hermes/compose.yml), [config readonly](../config/hermes/poc-config.yaml) et [runbook](../poc/hermes/README.md). Distinct de l'App TrueNAS native `hermes-agent` ; aucun port hôte, dashboard, socket Docker, root shell ni API administrative.
- [x] **MCP observation read-only codé** : `scripts/hermes/readonly_mcp.py` via stdio, seulement `up` Prometheus pour jobs connus, vue globale et coût LiteLLM par alias. Pas de logs bruts ni HTTP/PromQL arbitraire ; SSRF/redirect rejetés, erreurs non détaillées, aucune valeur de secret renvoyée. Tests offline ajoutés.
- [x] **LiteLLM coût** : politique key `hermes-poc`, modèle `qwen`, budget souhaité **2 USD / 30 jours**, 5 RPM, 1 requête parallèle et 10k TPM ; job `litellm_hermes` 60 s et règles de coûts dans Prometheus. Les métriques réelles et la création de la virtual key sont **non vérifiées/non effectuées**.
- [x] **Interopérabilité contrôlée préparée** : overlay privé `poc/hermes/compose.api.yml` pour OpenWebUI/FastAPI/n8n via `intranet`, clé API dédiée. **Désactivé par défaut** ; aucune exposition Internet, modèle ou permission ajoutée aux consommateurs existants.
- [x] **Préflight fail closed codé** : `scripts/hermes/poc_preflight.py` bloque digest non épinglé, secrets trop permissifs, UID/dataset incohérent, `ALLOW_ALL`, manque d'allowlist, clé maître et API sans secret. Ne remplace pas un contrôle effectif des droits Unix/egress.
- [ ] **P0 runtime/security** : inspecter le TrueNAS App et l'image/digest réels ; installer seulement après test de conformité YAML Hermes, s6 UID10000/CapEff, snapshot/rollback, bot tokens exclusifs et véritable filtrage egress DNS/IPv4/IPv6. Ne pas supposer la protection d'un simple Docker bridge.
- [ ] **P0 confidentialité LiteLLM** : protéger les contenus Hermes contre le `store_prompts_in_spend_logs`, le `turn_off_message_logging: false`, Langfuse et le cache Redis du proxy partagé. Activer guardrails/PII et vérifier le fail-closed avant incidents/logs sensibles, sans casser OpenWebUI/OpenRAG.
- [ ] **P1 intégrations** : tester SearXNG derrière proxy de recherche, connecteurs Loki agrégés, Gatus, Docker states limités et GitHub PR avec identité propre ; ne pas connecter directement l'OpenTerminal existant sans worker non privilégié et API fortement limitée.
- [ ] **P2 opérabilité** : tester sous TrueNAS Telegram/Discord ID allowlists, API interne, Grafana/Mimir coût et consommation token, reprise reboot, révocation, tests adversariaux et canaris secrets ; autoriser ensuite un POC d'édition GitHub en PR sans merge.
- [ ] **Validation** : tests pytest ciblés + qualité L3 HEAD, `docker compose config --quiet`, exécution sur TrueNAS et mesures réelles restent à effectuer. Aucun déploiement/redémarrage/secret/merge automatique.

## P0/P1/P2 — Hermes Secure by Design : barrières à l'activation (2026-10-11)

- [x] ADR [Hermes Secure by Design](./security/hermes-secure-by-design.md) : frontières de confiance, STRIDE/OWASP Agentic, PII, secrets, réseaux, skills, exécuteurs et tests de non-exfiltration ; **étude uniquement**.
- [x] Profil de référence `config/hermes/secure-profile.example.yaml` + contrats statiques : approbations manual/deny, skills et mémoire avec revue, non-root worker SSH, SearXNG fixé, **pas de keyless fallback ni rescue**. Profil non appliqué sur TrueNAS.
- [ ] **P0 : corriger avant raccordement** le risque de confidentialité de LiteLLM : `store_prompts_in_spend_logs: true`, `turn_off_message_logging: false`, `langfuse_otel`, identifiants forwardés et Redis cache. Séparer la route Hermes/virtual key et imposer guardrails/quotas/fail closed **sans modifier aveuglément les autres consommateurs**.
- [ ] **P0 : valider l'authentification et les secrets** : UID effectif non-root, aucun socket Docker/root/sudo, aucune lecture des secrets globaux, politique d'egress réellement imposée, bot IDs allowlistés, mode pairing désactivé ou contrôlé ; distinguer Vaultwarden de Bitwarden Secrets Manager.
- [ ] **P1 : évaluer LLM Guard/Presidio local** aux frontières chat, LLM, outils et réponse ; mesurer PII français/anglais/allemand, faux négatifs et latence ; interdiction de désanonymiser vers Telegram/Discord.
- [ ] **P1 : SearXNG et web** : vérifier runtime JSON, requêtes publiquement admissibles, proxy de redaction, extraction isolée, aucun appel implicite vers fournisseurs gratuits tiers, SSRF/redirect/DNS rebinding bloqués.
- [ ] **P1 : skills/MCP/mémoire** : source privée revue/signée/épinglée, `skills.guard_agent_created`, `skills.write_approval`, `memory.write_approval`, pas d'installation depuis messages ni auto-update, least-privileged tools.
- [ ] **P2 : preuves d'exploitation** : exercices non autorisé/PII/secrets/prompt injection via Docker/Loki/SearXNG/README, fail-closed d'un guardrail indisponible, coupure des permissions, alertes Loki/Prometheus et continuité après reboot.
- [ ] Pas de nouveau service/port/exposition/secret/déploiement Hermes, LiteLLM ou SearXNG tant que ces gates ne sont pas fermés. Préserver la priorité stabilité/Gatus/pfSense du chemin critique et ne pas merger automatiquement.

## P1/P2 — Hermes TrueNAS : agent DevSecOps via Telegram/Discord (2026-10-11)

- [x] Étudier la faisabilité : gateway Hermes natif Telegram/Discord, Loki déjà déclaré sur TrueNAS, commandes shell possibles mais trop privilégiées sans frontière externe.
- [x] Ajouter le runbook de sécurité `docs/runbooks/hermes-homelab-gateway-feasibility.md` et un diagnostic read-only `scripts/truenas/diagnose-hermes-agent.sh --check`.
- [ ] **P1**, après les incidents prioritaires : auditer l'App TrueNAS `hermes-agent` réellement déployée (image/digest, gateway, UID/GID, mounts, stockage, ACL, secrets et canaux). Aucune migration/redéploiement avant preuve runtime.
- [ ] **P2** : DM Telegram puis Discord, allowlist d'identité, aucun ingress, aucun accès root ou Docker socket ; réutiliser LiteLLM et secrets runtime uniquement après contrôle des identités.
- [ ] **P2** : connecteurs de diagnostic indépendants et bornés pour Gatus/Prometheus, Loki et logs Docker ; vérifier la présence réelle des logs d'applications dans Loki, l'absence d'exfiltration et le filtrage côté API.
- [ ] **P2/P3** : PR GitHub avec tests local-first et non-merge, puis actions correctives via exécuteur distinct allowlisté et validation opérateur hors canal du bot. Aucun shell root via Telegram/Discord.
- [ ] Vérifier sur TrueNAS les tests fonctionnels, la prévention prompt injection, le compte non autorisé, la révocation des accès, la récupération après redémarrage ; laisser les changements runtime non appliqués d'ici là.


## P0 — Migration des secrets CrowdSec vers le pool runtime (2026-10-11)

- [x] Confirmer le contrat Compose : `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` est lu localement, `required: false` pour le bootstrap moteur ; aucune connexion Vaultwarden au démarrage.
- [x] Corriger README, politique globale et description de la PR : **source opérationnelle = pool ZFS runtime**, Vaultwarden = coffre/copie de récupération facultative et non SPOF.
- [ ] Vérifier sans afficher les valeurs la présence de `BOUNCER_KEY_PFSENSE_FIREWALL`, les droits du répertoire 0700 et du fichier 0600, les propriétaires et le backup chiffré indépendamment du coffre.
- [ ] Si absent, restaurer la clé existante via une opération approuvée ; ne pas inventer/faire tourner la clé automatiquement et ne pas dépendre d'un item Vaultwarden non existant.
- [ ] Valider le LAPI central, `PFSENSE_FIREWALL` enregistré, puis les checks TrueNAS `--check` et `--accept` une fois le bouncer pfSense reconfiguré depuis la workstation ; ne jamais administrer pfSense depuis TrueNAS.
- [ ] Tester un redémarrage/recovery de l'App sans Vaultwarden joignable, puis éventuellement synchroniser une copie dans le coffre. Ne retirer aucun secret legacy avant acceptance.
- [ ] Appliquer progressivement la même séparation coffre optionnel / runtime local aux autres Apps, avec tests et contrôles de dette existants.

## P1/P2 — Shell UX, shared primitives, and OpenClaw hourly heartbeat (2026-10-11)

- [x] Introduce a shared TTY-only status presentation helper (colors and icons)
  and document its use for agents in `.agents/skills/local-first-quality/SKILL.md`.
  Keep `NO_COLOR`, non-TTY output, exit codes and machine-readable data stable.
- [x] Start replacing duplicated inline ANSI terminal setup in
  `scripts/truenas/check-homelab-services.sh`.
- [ ] Inventory repeated Shell function signatures and callers; rank by reuse,
  mutation risks and tests. Candidate owners:
  `scripts/lib/truenas.sh` (app lifecycle, job and Git provenance),
  `scripts/lib/probe.sh` (bounded network checks),
  `scripts/lib/diagnostic.sh` (compact output), and
  `scripts/agent-quality-gate.sh` (local-first summary/formatters).
- [ ] Refactor repeated error reporting, command preflights, safe temp-file
  handling and bounded log summaries only after preserving CLI/exit contracts.
- [ ] Add TTY, piped output, NO_COLOR, TERM=dumb and ASCII-mode unit contracts
  for shared status output; avoid forcing ANSI codes into CI logs.
- [ ] Correlate hourly `Agent couldn't generate a response. Please try again.`
  reports with OpenClaw cron/heartbeat run IDs, start times, duration,
  gateway logs and LiteLLM HTTP status. User-visible message by itself does
  **not** prove a heartbeat failure.
- [ ] Distinguish queue concurrency/timeouts, LiteLLM upstream errors,
  missing API credentials, cron delivery failures and context/memory payload
  before adjusting timeouts or provider routing; no automatic paid smokes.
- [ ] Keep unrelated FastAPI/Gatus/CSI runtime work and CI gates intact.
  Do not merge the active PR automatically.

## P1 — TrueNAS resource-heavy services audit (2026-10-11)

- [x] Implement a read-only, bounded `docker stats --no-stream` collector with
  top CPU, resident/container-accounted memory and percentage-of-limit ranking.
  Integrate into `check-homelab-services.sh --deep` without restarting Apps.
- [x] Define snapshot interpretation: CPU percentages can exceed 100% on
  multicore hosts; memory limit percentages depend on configured cgroup limits.
  A single snapshot is not proof of sustained pressure or of service failure.
- [ ] Capture real TrueNAS evidence and correlate top consumers to canonical
  App IDs and x-nabla criticality. Capture host memory/swap and storage
  pressure alongside container peaks without leaking runtime credentials.
- [ ] Add repeated samples / time-series evidence through existing Prometheus
  node-exporter/cAdvisor where available; avoid inventing a ranking from
  currently unobserved workloads.
- [ ] Define workload-specific SLOs and remediation thresholds for the
  observed heaviest consumers; prioritize database (Postgres/ClickHouse),
  search (OpenSearch), observability (Sentry/Prometheus) and AI workloads
  only when actual measurements confirm resource pressure.
- [ ] Address remaining probe coverage, PostgreSQL exporter isolation and
  missing ingress audit as separate gaps; do not conflate pressure with DOWN.
- [ ] Preserve local-first static tests and CI blocking controls, and keep
  the PR unmerged pending acceptance.

## P0/P2 — OpenClaw cron et audit différé des coûts LiteLLM (11/10/2026)

**Autorité :** [runbook coûts LiteLLM](runbooks/litellm-cost-governance-audit.md) ; conserver la PR #253 ouverte.

### P0 — Stabilisation prioritaire

- [ ] Corréler les heartbeats `main` en échec autour de 68 s avec le runner / logs applicatifs / contexte; génération isolée `litellm-main/gpt-4.1` déjà validée, mais heartbeat non rétabli.
- [ ] Confirmer la route et l'authentification réelles de `openclaw-cron` (`litellm-cron/gpt-4.1-mini`), auditer son propre budget virtuel de 2 et ses quotas TPM/RPM sans exposer de clés.
- [ ] Préserver la séparation `litellm-main` / `litellm-cron`; aucun reset, hausse de budget ou smoke facturable automatique.
- [ ] Corriger/valider la CI PR #253 : ShellCheck et smoke de production 404; garder les contrôles sécurité bloquants.

### P2 — Audit des coûts plus tard

- [ ] Consolider coûts, plafonds et taux d'usage des clés workstation/TrueNAS avec déduplication, budget effectif et hiérarchie clé/équipe/modèle.
- [ ] Valider la collecte Prometheus réelle (callback défini dans `apps/litellm/config.yaml`, scrape non vérifié), concevoir dashboard Grafana, alertes 50/80/95 % et attribution par modèle.
- [ ] Revoir `ide` (100/7d), modèles, tarifs, fallbacks, stockage des prompts/logs et rétention; vérifier le diff config Git/DB TrueNAS.
- [ ] Reporter l'audit des budgets `n8n` tant que n8n n'est pas consommateur OpenClaw; ne pas en faire un blocage P0.

## Production smoke evidence classification (2026-10-11)

- [x] Source review of `AlbanAndrieu/fastapi-sample`: the application
  declares `/health` in `nabla/api/demo/sensor.py` and
  `/v2/version` in `nabla/api/v2.py`; its deployment workflow itself
  validates both paths. Code inspection has not established intentional
  public 404 concealment.
- [x] Keep Production Security CI fail-closed on HTTP 404, but report
  `unverified_route` and distinguish possible authentication concealment
  from deployment/ingress mismatch. Do not misinterpret 404 as JSON failure.
- [ ] Correlate FastAPI Cloud deployment/revision, edge routing and
  authentication/WAF policy; fix wrong upstream or document deliberate
  public concealment with an authenticated alternate proof, before
  changing the acceptance policy.
- [ ] Continue independent Gatus / monitoring / catalog repairs in PR #253
  even while the externally owned production route contract is unresolved.
  Do not disable the production smoke, CodeQL, ShellCheck or other gates.

## Acceptance update — Gatus / PostgreSQL monitoring (2026-10-11)

- [x] Gatus TrueNAS App RUNNING; container running, exit 0, no restarts,
  config 0640 uid 1000/gid 568, SQLite data present. Recent error category
  counts: 0 permission, 0 database, 0 config, 0 fatal.
- [x] Gatus UI / and /api/v1/endpoints/statuses HTTP 200 from TrueNAS.
  This confirms transport and basic API availability, **not** completeness
  of expected endpoint monitoring or FastAPI observer evidence.
- [x] Extend read-only Gatus diagnostics with API JSON shape and entry counts
  without leaking monitored URLs. Do not infer UP for all endpoints.
- [ ] Compare concrete API endpoint IDs to generated Gatus YAML, report
  absent IDs and reconcile missing 11 external evidence checks.
- [ ] Validate Gatus synthetic checks from actual outcomes and timestamps,
  not from UI 200 alone; integrate into FastAPI evidence contract.
- [x] PostgreSQL running, exporter absent and no eligible materialized
  POSTGRES_EXPORTER_DSN secret found. Keep separate from database health.
- [ ] Materialize a dedicated read-only exporter DSN at the runtime path
  after operator approval; do not print existing postgres credentials.
- [ ] Deploy isolated PostgreSQL exporter and verify pg_up=1 and Prometheus
  scrape success. No postgres app recreation or secret guesses.
- [ ] Reconcile Portracker :30233 actual runtime with generated catalog and
  Gatus/AutoKuma/Homarr before runtime smoke acceptance.
- [ ] Investigate ingress-audit script location/owner; missing audit code is
  a coverage gap, not runtime service failure.

## FastAPI external evidence and Gatus / PostgreSQL exporter alignment — 2026-10-11

- [x] TrueNAS local audit: 62 running accepted, zero runtime failures,
  2 catalog monitoring warnings (postgres-exporter and Portracker) and
  80 probe gaps. Separate internal health from external observer evidence.
- [ ] FastAPI observer may report `evidence_incomplete` for pfSense, Sentry,
  Gatus and PostgreSQL/Redis despite healthy local services. Map each to
  an explicit collection failure / missing observer permissions / missing
  external evidence; do not mark the internal service DOWN on absence alone.
- [ ] Gatus: inspect TrueNAS App lifecycle, effective supplemental group
  access to config (0640/apps GID 568), HTTP homepage, API/status evidence,
  and generated endpoint parity. HTTP 200 or Prometheus `up=1` alone does
  not prove successful monitoring of the expected services.
- [ ] Cross-check FastAPI's claimed 11 missing Gatus checks against
  generated Gatus config and the canonical topology; reconcile via source
  generators rather than manual generated-file editing.
- [x] PostgreSQL exporter: discover centrally materialized runtime secret
  candidate paths; require `POSTGRES_EXPORTER_DSN` key without logging value.
- [ ] If the runtime file exists, validate exporter-only identity and
  separately deploy exporter; never redeploy the healthy PostgreSQL App.
- [ ] Audit Portracker's previously reconciled :30233 target against
  regenerated topology/consumers before claiming the warning fixed.
- [ ] Finish runtime migrations and acceptance before revisiting the full
  quality gate, without disabling the latter.

## PostgreSQL exporter restoration — runtime evidence (2026-10-11)

- [x] PostgreSQL TrueNAS App RUNNING; primary container running and :5432 published.
- [x] PostgreSQL exporter is absent from `docker ps -a`; :9187 refuses connections; expected `/mnt/cpool/postgres/.env.secrets` is missing.
- [x] Add read-only `scripts/truenas/diagnose-postgres-exporter.sh` preflight with no DSN disclosure.
- [ ] Isolate the exporter as its own TrueNAS custom App or explicitly scoped Compose project; do **not** update/redeploy shared PostgreSQL just to add monitoring.
- [ ] Provision a dedicated read-only monitoring SQL role and exporter DSN via established secrets management, without logging or committing credentials.
- [ ] Verify exporter container, HTTP /metrics with `pg_up=1`, Prometheus target health and queryable PostgreSQL metrics.
- [ ] Reconcile its service-topology monitoring ownership and remove false warnings only after functional acceptance.

## Runtime/catalog reconciliation — Portracker and PostgreSQL exporter (2026-10-11)

- [x] Correlate Portracker active Docker bindings and direct HTTP probe:
  container exposes 4999/tcp without a host binding, and publishes
  30233/tcp on 0.0.0.0 and ::. The operator received HTTP 200 from
  `http://172.17.0.24:30233/metrics`, while :4999 was unreachable.
- [x] Correct the canonical `apps/portracker/compose.yml` declaration:
  published target/host port 30233 and HTTP /metrics monitoring. Regenerate
  catalog/service-topology, Gatus, AutoKuma and Homarr via canonical
  generators and inspect their diffs before publishing.
- [ ] Verify Portracker still responds on 30233 after any future redeploy.
  This change reconciles source declarations; it does not claim a runtime
  redeployment took place.
- [ ] PostgreSQL exporter: primary PostgreSQL remains healthy on :5432,
  while no exporter container was shown in the operator's Docker inventory
  and :9187 refused connections. Check its active TrueNAS App version/rendered
  Compose, DSN secret presence without printing values, exporter logs, and
  Prometheus scrape targets. Restore only the exporter, not PostgreSQL.
- [ ] Improve service dependency audits to distinguish an optional/absent
  exporter from a broken required database, without masking missing metrics.
  Follow up on 80 observed probe gaps and 16 unmapped TrueNAS Apps.

## Runtime update — Bichon accepted, OpenArchiver removed, Pyroscope blocked (2026-10-11)

- [x] Operator removed the OpenArchiver TrueNAS application. Do not attempt
  OpenArchiver startup or continue classifying its absence as a runtime fault.
- [x] Bichon is RUNNING, Docker healthy for seven days and HTTP / returns 200.
  IMAP import/search and recovery acceptance remain separate outstanding checks.
- [ ] Reconcile and retire residual OpenArchiver canonical declarations,
  DNS/Traefik/Gatus/Homarr/AutoKuma references after reviewing active
  consumers; preserve or separately inventory any remaining datasets/backups.
- [ ] **P0 Pyroscope:** collect TrueNAS state, current container ID/status,
  bounded redacted logs, actual effective command/mounts/user, host dataset
  owner and mode, and HTTP / + /metrics. Determine whether the failure is
  mount access, OOM, port collision or v2 Raft/metastore before any change.
- [ ] Pyroscope fix is accepted only when runtime is stable, / and /metrics
  work, and fresh FastAPI profiles are queryable in Grafana/Pyroscope.
- [ ] Keep quality-gate cleanup after service stabilization; do not disable
  security or lint checks.

## P1 — Email archiving consolidation: Bichon replaces OpenArchiver (2026-10-11)

**Decision:** use Bichon as the canonical email-archive service. Keep
OpenArchiver STOPPED; do not attempt further runtime repair unless migration
evidence reveals a missing capability. Operator explicitly stopped the
OpenArchiver TrueNAS App; Docker containers were then absent. This is expected,
not a fresh container failure.

- [x] Mark OpenArchiver for **planned decommission**, not active recovery.
- [ ] Validate Bichon IMAP sync, indexed message/attachment search, restore or
  export, and authentication using representative accounts; confirm backup and
  recovery against actual archived data.
- [ ] Inventory OpenArchiver source accounts, archived message counts, unique
  messages, attachments, export formats and any retained eDiscovery requirements;
  compare with Bichon coverage before signing off the migration.
- [ ] Preserve OpenArchiver application metadata, TrueNAS datasets, PostgreSQL,
  Redis, Meilisearch and Tika data/configuration until backups and required
  exports are verified. No `app.delete`, data removal or volume prune yet.
- [ ] Identify OpenArchiver consumers and remove its ingress, DNS, monitoring,
  Homarr, Gatus, AutoKuma and service-topology projections through canonical
  source declarations/generators **only after** consumer-free evidence; avoid
  touching Bichon and shared services.
- [ ] After backup, restore and consumer checks, retire the TrueNAS App and
  document the reversible rollback window and final data-retention decision.
- [ ] Do not classify deliberately STOPPED OpenArchiver as an active P0 incident
  in the service-stabilization queue; keep it visible as decommission pending.

**Scope distinction:** both products support IMAP mail archiving and search,
but OpenArchiver may cover dedicated Google Workspace / Microsoft 365
connectors, PST/MBOX ingestion and commercial compliance/eDiscovery workflows
that Bichon does not necessarily replace. Treat feature equivalence as
conditional on the actual homelab use cases.

# Homelab roadmap

Last updated: 2026-10-10.

This file is the **concise execution index and conversation restart point**.
Detailed procedures, rollback instructions and historical evidence stay in their
canonical runbooks/incidents; see [`docs/README.md`](./README.md).

Primary references:

- reboot/recovery: [`homelab-reboot-runbook.md`](./homelab-reboot-runbook.md);
- runtime/storage layout: [`truenas-runtime-layout.md`](./truenas-runtime-layout.md);
- secret migration: [`secrets-migration-roadmap.md`](./secrets-migration-roadmap.md);
- platform migration: [`homelab-platform-migration-roadmap.md`](./homelab-platform-migration-roadmap.md);
- security tooling: [`security-inventory-tooling-roadmap.md`](./security-inventory-tooling-roadmap.md);
- AI stack upgrades, integrations and consolidation:
  [`ai-stack-upgrade-consolidation-plan.md`](./ai-stack-upgrade-consolidation-plan.md);
- service catalog v2: [`service-catalog-v2-normalization.md`](./service-catalog-v2-normalization.md);
- incidents/evidence: [`incidents/`](./incidents/).

## Roadmap contract

- **declared / repository-ready** means code/config exists; it does not imply
  deployment or runtime acceptance;
- **runtime accepted** requires functional health/evidence appropriate to the
  service;
- **reboot accepted** additionally proves recovery from canonical persisted state;
- migrations are one service at a time and remain rollback-safe until acceptance;
- warning/unknown external dependencies stay distinguishable from application DOWN;
- roadmap = status/order/next action; runbook = procedure; incident = evidence.

## P1 — Prometheus telemetry evidence before FastAPI consumers (2026-10-11)

- [x] Inventory declared Prometheus targets for Gatus, FastAPI Sample,
  PostgreSQL, Redis, pfSense, CrowdSec and Cloudflare; do not confuse job
  configuration with live scrape success.
- [x] Add bounded read-only static/live audit
  `scripts/prometheus/audit-telemetry-coverage.py` and offline contracts.
- [x] Record exporter scrape availability and functional Postgres/Redis
  signals, preserving an absent/unknown state instead of synthesizing zero.
- [ ] In the deferred batch, confirm Prometheus target `up`, sample series,
  scrape errors, Gatus monitor cardinality and PostgreSQL/Redis authentication
  using only trusted internal Prometheus access.
- [ ] Deploy the missing dedicated PostgreSQL exporter only after runtime
  secret migration and least-privilege identity acceptance.
- [ ] Determine whether Cloudflare telemetry should use a bounded exporter
  or API sampling; no new broad API token and no Cloudflare polling from
  pfSense.
- [ ] Add Postgres/Redis/CrowdSec exporter-state **blind-spot** fields to the
  FastAPI Sample platform telemetry consumer in its own repository, followed
  by consumer-contract tests; do not mark services DOWN for absent metrics.
- [ ] Establish cAdvisor/host resource availability before activating
  topology CPU/RAM overlays or resource saturation alerts.

## CURRENT FOCUS — stabilize and finish migrations (2026-10-11)

**Operator reprioritization:** deliver service recovery, runtime migrations and
cross-repository catalog adoption first. Quality-gate optimization, agent-output
tuning and speculative Dagger work are **deferred** until these finish. Existing
security checks remain mandatory **before merge**: no bypass of BetterLeaks,
SAST, pytest, Playwright/ZAP or pre-commit, and no automatic merge.

Execution sequence (observed service state must be reconfirmed before action):

1. **Gatus:** read-only root-cause diagnosis (exit 2 / HTTP 8085 unavailable
   in last evidence); inspect effective UID/GID, actual config and SQLite mount
   without exposing secrets. Preserve `/mnt/cpool/gatus/gatus.db`. Only apply a
   minimal correction when supported by runtime evidence; require HTTP 8085,
   monitoring history persistence, and recovery after restart/reboot.
2. **pfSense / CrowdSec:** confirm Unbound DNS, WebGUI/API auth, memory and
   CrowdSec stability with bounded read-only probes. Avoid broad restart,
   firewall-policy edits or extra request fan-out. A successful API/TCP check is
   not equivalent to a recovered security function.
3. **Close service acceptances:** retain already proven DSOMM, Sentry,
   Scrutiny and Pi-hole evidence; collect only missing fresh-event,
   SMART /dev/sde classification and reboot acceptance where required.
   Include Pyroscope readiness and actual profile ingestion in the service
   acceptance batch; inspect UID/GID 568 migration compatibility only after
   verifying actual dataset ACLs. Do not blanket-chown services.
4. **Migrate secrets transactionally:** one active app at a time under
   `/mnt/cpool/secrets/runtime/<app>/`; match manifest, Vaultwarden recovery,
   least-privilege consumer, Backstage descriptor, and rollback proof.
5. **Prepare catalog v2** using `nabla-compose` as sole author for identity,
   relations, desired exposure and BIA criticality. Verify `fastapi-sample`
   and `nabla-site-alban` projections against the same revision.
6. **Coordinated direct cutover:** migrate the three consumers as one reviewed
   transaction, then validate outside-in FastAPI Cloud and inside-out Gatus/
   Prometheus independently. Retire legacy JSON only after runtime, health,
   security, rollback and reboot evidence.

**Deferred, not deleted:** Dagger, quality-gate ergonomics, broad dependency
and image upgrades, speculative new probes, optional AI features, P2 RAG
expansion and destructive service cleanup. Fix introduced regressions promptly,
but do not loop on unrelated known environmental gate failures. Report exact
`PASS/FAIL/NOT RUN`; never claim an L3 pass without executing it.
Operator-only appliance changes require reviewed acceptance, not remote
guesswork.

## CURRENT AUTHORITATIVE EXECUTION ORDER — operator-approved (2026-10-10)

**Use this section rather than superseded chronological entries below.**
Compact new-chat handoff with complete decisions, dependencies and proofs:
[`roadmap-execution-handoff-2026-10-10.md`](./roadmap-execution-handoff-2026-10-10.md).
Historic PR #251 notes and the older `Current execution order` remain
as evidence/context only; if they disagree, **this section wins**.

**Decisions approved:** (1) stability/Gatus/pfSense before new features;
(2) secret migration **one service at a time**, bundled with its Backstage
descriptor; (3) prepare catalog v2 gradually but perform a **coordinated
three-repository cutover**, no permanent dual schema; (4) Cyberbro before
Docling when choosing between equal-priority feature work, while read-only
Docling diagnostics may run earlier; (5) finalize already operational
DSOMM/Sentry/Scrutiny/Pi-hole statuses and acceptance evidence instead
of redeploying them.

### P1 Pyroscope recovery and TrueNAS apps UID/GID normalization — 2026-10-11

- [ ] **Pyroscope runtime acceptance after storage/identity change:** the
  Compose manifest now declares `user: "568:568"`, but deployment and
  recovery remain **UNVERIFIED**. Verify the effective container UID/GID and
  ownership/ACL of `/mnt/cpool/pyroscope/data`; confirm that Raft WAL and
  metastore state persist at the configured path, that the leader stays stable,
  `/ready` returns HTTP 200, and a real FastAPI profile can be ingested and
  queried. Current operator evidence: UID 10001 could write to the bind mount
  inside Docker, but the directory stayed empty; `/ready` remained HTTP 503
  with recurring `node is not the leader` / Raft write timeout errors.
  **Do not mark recovered based on HTTP / or /metrics alone.**
- [ ] **Post-reboot Pyroscope acceptance:** exercise
  `scripts/truenas/diagnose-pyroscope.sh` and
  `reboot-homelab.sh --post-reboot-check`; validate permissions,
  declared-versus-effective mounts, persistent Raft files, leader stability,
  readiness, and ingestion. Read-only diagnosis; no automatic Raft reset.
- [ ] **Evaluate and migrate LiteLLM to `568:568`:** determine current
  effective UID, container writable paths, runtime secrets and config mounts,
  then provision storage ACL/ownership, stage the Compose `user` change,
  verify startup, proxy/API completion and persistence, and retain rollback.
  Existing LiteLLM `568:568` line is commented, not deployed.
- [ ] **Evaluate and migrate Ollama to `568:568`:** audit model-cache
  ownership and the `/root/.ollama` mount, writable `HOME`/`OLLAMA_MODELS`,
  optional GPU device access and group permissions; only then deploy as
  `apps`, prove model discovery, generation and persistence after recreation.
- [ ] **Audit remaining TrueNAS services for `568:568` suitability:**
  compare actual image/process UID/GID with ZFS mount ACLs and writable
  paths; classify already compatible, migration candidates, and image-native
  identities to preserve (e.g. MinIO `473:473`). Never apply global
  `chown -R` or bulk UID replacements.
- [ ] **Acceptance gate:** validate each migration independently with
  local-first checks and rollback evidence before marking any runtime
  accepted or merging; avoid GitHub Actions credit consumption.

### Runtime migration and service stabilization — 2026-10-11 operator evidence

- **P0 Obsidian:** TrueNAS App `CRASHED`; collect `midclt app.query`,
  stopped-container states, bounded logs and mounts before redeployment.
- **P0 OpenArchiver:** TrueNAS App `DEPLOYING`; inspect actual
  service health, Postgres/Redis dependencies and the running TrueNAS job
  before any restart. Do not conflate a transient deploy with a crash.
- **P0 FastAPI staging:** container check was running while the host
  `/api/health-board` probe became unreachable. Validate published 8091,
  local `/health`, healthcheck evidence and origin routing separately.
- **Accepted Vaultwarden migration:** `vaultwarden` and
  `bitwarden-api` both healthy, one adapter restart,
  active `BW_HOST=https://vaultwarden.albandrieu.com`; no further
  redispatch of the old HTTP configuration fix.
- **P1 monitoring:** Kafka `kafka:9092` and Sentry ClickHouse
  `sentry-clickhouse:9000` are Docker DNS-only endpoints; do not probe
  from the TrueNAS host. In-network readiness probes remain to be
  implemented. `portracker` is published on 30233, not 4999;
  PostgreSQL exporter :9187 is not present in the Docker published
  ports snapshot. Reconcile the deployment before editing monitors.
- **P2** Complete monitoring mappings and retire pending migrations.
- **P3 quality gate** follows runtime fixes, without disabling
  security checks; the last local gate had 220 passed / 1 failed
  (`test_gatus_diagnostic_contract.py::test_diagnostic_does_not_leak_raw_logs`).

### P0 health audit evidence — 2026-10-11

- [x] Operator confirmed DSOMM accepted; 4,170-byte progress and
  18,108-byte evidence YAML correctly served.
- [ ] Investigate `sample` TrueNAS DEPLOYING, `fastapi-sample`
  Docker unhealthy, FastAPI Redis unreachable and HTTP unreachable;
  diagnose independently before any restart. `vaultwarden` was
  transiently DEPLOYING and `bitwarden-api` health was starting
  in successive snapshots, requiring follow-up state checks.
- [x] Split declared-monitoring coverage gaps from failed network
  probes: missing host/port and unmapped catalog entries now count
  as `probe_gaps`, not operational warnings. Keep real connection
  refusals/DNS failures and non-RUNNING app states visible.
- [ ] Reconcile erroneous hostname-only monitor targets
  (Kafka, sentry-clickhouse) and port probes (postgres-exporter,
  portracker) against actual runtime topology without hiding failures.
- [ ] Verify exact-head CI and full runtime report; do not merge.

### P0 service health audit: dependency-order operator acceptance

- [x] Read-only TrueNAS operator audit: DSOMM accepts 22 activities
  and 22 evidence records; seven focused pytest checks passed.
  Runtime found Docker `bitwarden-api` restarting, FastAPI Redis probe
  unreachable, and strict ingress audit missing from its earlier
  expected path. These are separate failures; other TrueNAS Apps
  reporting RUNNING does not prove individual endpoints healthy.
- [x] Introduced colored `check-homelab-services.sh` summary and
  opt-in `--deep` mode using existing
  `plan-app-lifecycle-order.py` and declared required dependencies
  from `catalog/service-topology.json` to order checks by lifecycle
  waves. Per-service HTTP/TCP probes are bounded and only performed
  where `monitoring` declares a supported host/port. Missing probe
  metadata is **not** treated as functional success.
- [ ] Next: reconcile the real ingress-audit script location, inspect
  `bitwarden-api` restarting logs without exposing secrets, and
  diagnose FastAPI → Redis reachability from the observer network.
- [ ] Gradually extend declared service readiness checks with
  authenticated/application semantics; avoid treating all RUNNING
  apps or a bare TCP open as complete service acceptance.
- [ ] Validate new exact-HEAD Python/style tests and deep-mode live
  output before making deep checks blocking in reboot gate.

### P0 DSOMM model and independent all-service checks — 2026-10-11

- [x] Regression fixture fixed: former `b"...\\n..."` test used literal escaped
  newlines, not YAML line breaks. DSOMM upstream `model.yaml` begins
  with `meta.version: 5.0.2` followed by a separate activity document;
  HTTP acceptance now requires that structure rather than root
  `version`. Exact-head tests/runtime execution pending.
- [x] Added `scripts/truenas/check-homelab-services.sh` to run
  read-only app states, Docker health, DSOMM HTTP/YAML, FastAPI
  integration and strict ingress audit **without a reboot manifest**.
  Failure counters preserve gate failures; never restart services.
- [ ] Old 2026-10-03 reboot manifest remains stale. Archive only
  following operator review of its `phase`, boot IDs and evidence;
  do not delete `latest`, fudge mtime or bypass freshness to
  claim a historical reboot accepted. A future genuine reboot
  requires `--prepare` and fresh state.
- [ ] Run targeted pytest and standalone cross-service check on
  TrueNAS; classify genuine failures and keep PR open.

### P0 DSOMM live post-reboot test — multi-document YAML and stale manifest

- [x] Operator targeted tests: 4 passed, but standalone HTTP check
  failed on `default/model.yaml`: PyYAML `safe_load` raised
  `expected a single document in the stream`, because upstream
  DSOMM model includes `meta:` plus a `---` document separator.
  Parser now uses `safe_load_all` with exactly one matching model
  document; added positive and ambiguous-document regression tests.
- [x] `reboot-homelab.sh --post-reboot-check` correctly refused a
  stale 2026-10-03 reboot manifest (age 622843 s > permitted
  172800 s). Do not increase age limit, forge a new manifest,
  or bypass boot-ID attestation merely to run functional checks.
- [ ] Re-run standalone `python3 scripts/truenas/check-dsomm-post-reboot.py`
  after checkout update; expect four successful YAML assets and
  populated Nabla contexts. Only execute full --post-reboot-check
  on a **new genuine reboot** with a fresh prepared manifest.

### P0 DSOMM post-reboot functional acceptance

- [x] Add read-only `scripts/truenas/check-dsomm-post-reboot.py` to
  `reboot-homelab.sh --post-reboot-check`, preserving FastAPI,
  ingress and Talos checks. It rejects SPA HTML fallback on
  `/assets/YAML/`, empty assessment YAML, or missing Nabla contexts.
- [x] Add synthetic HTTP regression coverage, including a 200/HTML
  fallback, and document the independent standalone command.
- [ ] Run the standalone check on TrueNAS with the updated checkout,
  then confirm browser-level circular-heatmap rendering on an
  approved Playwright runner. Full orchestrated `--post-reboot-check`
  requires a valid manifest and a genuine reboot, and is **not**
  equivalent to the standalone check.
- [ ] Exact-HEAD local gate remains unverified in this agent sandbox
  (GitHub DNS unreachable); do not claim all services checked or
  the PR ready to merge.

### P0 DSOMM mounted-data acceptance and frontend rendering investigation

- [x] Operator confirmed `app.redeploy dsomm` complete, TrueNAS
  `RUNNING`, Docker `healthy`, UI HTTP 200, and mounted
  progress/evidence YAML sizes 4170 and 18108 bytes respectively.
  Thus runtime files are populated but the browser still displays
  empty `Nabla Platform` and `Nabla Applications`.
- [x] Added browser-facing `/YAML/{meta.yaml,default/model.yaml,team-progress.yaml,team-evidence.yaml}`
  HTTP status/length/content-type probes to read-only diagnostic.
  Investigate wrong asset URLs, stale browser localStorage and
  frontend/model compatibility **from measured output**, not guessed
  scores. Do not delete localStorage or overwrite YAML without backup.
- [x] The previous Pre-commit failure on `9b3f196` was
  `trailing-whitespace`; removed the offending trailing space
  in `docs/roadmap.md`. An exact-new-HEAD green CI run has
  not yet been observed.
- [ ] Confirm YAML asset responses and console/network errors in
  browser. Then address confirmed frontend failure and run
  exact-HEAD local quality gate.

### P0 DSOMM empty persisted YAML — runtime root cause

- [x] TrueNAS operator ran new diagnostic: the checked-in DSOMM
  5.0.2 seed validates (22 activities and 22 evidence records);
  runtime `model.yaml` exists (614262 bytes) but
  `team-progress.yaml` and `team-evidence.yaml` are each
  10 bytes, reporting invalid/no activity mapping. DSOMM root
  HTTP 200 does not establish populated UI.
- [x] `nabla-site-alban` repository producer validated and its
  partial 1/4-source portfolio report was written to
  `/mnt/cpool/dsomm/reports/site-alban.repository-assessment.aggregate.json`.
  Do not interpret 1/4 as a complete portfolio maturity score.
- [x] Added explicit `--check|--apply` backup-first empty-state
  recovery script and focused regression tests. It refuses
  populated assessments rather than overwriting them.
- [ ] Operator acceptance: run `--check`, guarded `--apply`,
  validate runtime seed, then explicitly remount the file bind
  mounts through controlled DSOMM app redeploy; verify UI context
  displays 22 seeded activities and evidence. No automatic restart.
- [ ] Repo-level portfolio synthesis remains separate from the
  UI seed and requires reviewed provenance and coverage.

### P0 CI and DSOMM UI investigation — 2026-10-10

- [x] GitHub Actions PR #253 pre-commit failure at
  `499ea482` was `QG_EXEC_BIT` (five shebang scripts committed
  `100644`). Committed their exact blobs with executable mode
  `100755` (commit `3d56031`); new DSOMM diagnostic is also
  `100755`. CodeQL previously succeeded. Exact-new-HEAD full
  local/remote quality gate remains **unverified**; do not label CI green.
- [x] pfSense `sh` central CrowdSec key probe returned HTTP
  **403**, therefore current pfSense key has **not** been
  authenticated on central LAPI. Keep cutover blocked and do not
  treat historical `pfsense-firewall` pull as current matching-key proof.
- [x] DSOMM frontend HTTP 200 previously observed, but the
  operator reports an empty UI. Added
  `scripts/truenas/diagnose-dsomm-assessment.sh` and a
  targeted test to distinguish persisted progress/evidence
  and repository JSON producers from browser presentation.
- [x] `nabla-site-alban` publishes a `nabla.dsomm.repository-assessment/v1`
  JSON producer. `nabla-compose` has reviewed DSOMM 5.0.2
  runtime YAML seed but no confirmed repository producer JSON.
  Existing aggregator writes a separate review report; it does **not**
  mutate `team-progress.yaml` or browser localStorage.
- [ ] Validate DSOMM source via `--check`, produce a separate
  aggregation report, inspect mounted runtime YAML and browser asset
  requests, then review a **backup-first non-destructive** UI
  import procedure; never silently inflate portfolio scores.

### P0 pfSense tcsh interoperability correction

- [x] Operator confirmed pfSense 26.07 admin shell interprets direct
  POSIX `CONFIG=...` / `$(...)` snippets as tcsh syntax errors.
  The earlier interactive snippet was invalid; no authentication proof
  resulted from those errors.
- [x] Added `scripts/pfsense/check-central-crowdsec-bouncer.sh`
  with `#!/bin/sh`, delivered from workstation using
  `ssh home.albandrieu.com /bin/sh -s < scripts/pfsense/check-central-crowdsec-bouncer.sh`.
  This keeps the key on pfSense and off command arguments; the GET
  may update LAPI pull metadata but does not change pfSense rules.
- [x] Added POSIX shell and nonmutating behavior contract tests and
  usage in `apps/crowdsec/README.md`.
- [ ] Await operator HTTP result before concluding that pfSense's
  current key matches a central LAPI bouncer registration. No
  key rotation or cutover authorized by this diagnostic.

### P0 CrowdSec central bouncer history — 2026-10-10

- [x] `pfsense-firewall` created 2026-09-08, last pulled
  2026-09-25T22:55:08Z from 172.17.0.1, with type
  `crowdsec-firewall-bouncer`. This is historical evidence of
  central LAPI communication, not proof that pfSense's **current**
  local key matches this registration.
- [x] `PFSENSE_FIREWALL` created 2026-09-11, never pulled,
  no recorded IP/type. Keep both registrations pending attribution.
- [x] Last 24h CrowdSec Docker logs showed zero lines matching
  the operator's limited unauthorized/forbidden/invalid-key filter.
  This is **not** evidence of successful authentication.
- [ ] Perform an operator-approved credential authentication probe
  from pfSense to central LAPI without exposing keys in logs,
  arguments, shell history or chat; use only read/poll endpoints
  with understood side effects. Preserve rollback and never
  disrupt current firewall tables as part of diagnostic work.

### P0 CrowdSec bouncer credential provenance — operator checks

- [x] pfSense firewall bouncer YAML contains a nonempty `api_key`
  (presence only; never print or export the value).
- [x] TrueNAS CrowdSec LAPI lists `PFSENSE_FIREWALL` registered
  with `last_pull=null`. This confirms registration only, not
  that the legacy pfSense key is accepted by the central LAPI.
- [ ] Locate approved original central bouncer key, or perform
  separately approved explicit central key rotation with
  rollback. Do not compare or print raw secrets and do not assume
  keys match based on name alone. Keep legacy pfSense bouncer
  untouched until central authentication is proven.
- [ ] Continue exact Vaultwarden item reconciliation;
  `nabla/prod/crowdsec` is still missing.

### P0 Vaultwarden unlocked acceptance — latest operator evidence

- [x] On TrueNAS, pinned Bitwarden CLI `2026.8.0` successfully
  unlocked with `bw unlock --raw`; exact manifest inventory completed
  and returned `crowdsec: missing`. CLI state `unlocked`,
  canonical HTTPS base URL, NTP synchronized and
  Vaultwarden `1.37.3` running/healthy.
- [x] Read-only compatibility diagnostic reports failures=0,
  warnings=1 with five historical user-key-id requests and five
  HTTP 404 lines in a two-hour window, plus one TOTP drift warning.
  Do not interpret these historical counters as a failed 2026.8.0
  unlock or as correlated request/response pairs.
- [ ] CrowdSec remains blocked on locating the **existing** approved
  pfSense bouncer key, adding its exact manifest item and then
  securely rendering the runtime secret. No automatic key issuance,
  pfSense config change or Vaultwarden upgrade.
- [x] **CrowdSec candidate discovery prepared:** metadata-only Vaultwarden
  inventory can now list candidate item names and classify only
  `expected` / `other` / `unfiled` folder scope. No IDs, fields,
  usernames, URLs, notes or values are emitted. The migration runbook no
  longer instructs generation of a new key; recovery of the existing approved
  bouncer key remains mandatory unless rotation is separately authorized.

### P0 Vaultwarden read-only diagnostic operator acceptance

- [x] On TrueNAS, `git pull --ff-only` succeeded, Bash syntax passed
  and targeted Vaultwarden diagnostic/inventory contracts **5 passed**.
- [x] `diagnose-vaultwarden-cli.sh` reported active CLI
  `2026.8.0`, canonical HTTPS URL, NTP synchronized,
  `vaultwarden/server:1.37.3` running/healthy, Docker logs
  accessible.
- [x] Historic 2h log counts: `user_key_id_requests=5`,
  `http_404_lines=5`, `totp_drift_warnings=1`.
  These counters are not a current CLI 2026.8.0 login failure,
  and do not correlate individual requests/responses.
- [ ] The CLI status at check time was `locked`; a prior
  successful `bw unlock --raw` on 2026.8.0 proves the
  version can unlock, but this run does not prove an active
  unlocked session. Inventory still reports `crowdsec: missing`.
- [ ] No CrowdSec pfSense cutover until the existing bouncer
  key is accounted for. No Vaultwarden upgrade necessary
  solely on historical 404 evidence.

### P0 Vaultwarden CLI 2026.8.0 — TrueNAS acceptance (2026-10-10)

- [x] Operator installed checksum-pinned `bw 2026.8.0` using
  `scripts/truenas/bootstrap-bitwarden-cli.sh --apply` and
  rechecked the exact version with `--check`; canonical HTTPS server
  persisted.
- [x] CLI initially `locked`, then `bw unlock --raw` successfully
  produced an unlocked session and the manifest inventory executed:
  `crowdsec: missing`. This is a proven successful unlock on 2026.8.0,
  unlike the 2026.9.0 `KeyIdBackfillError/HTTP 404` observed previously.
- [x] Diagnostic enhanced with active `bw` binary path and explicit
  `logs_unavailable` if Docker permission/log retrieval fails;
  unavailable logs must not be interpreted as zero HTTP 404.
- [ ] Validate the amended diagnostic and targeted contracts on
  TrueNAS. Full local quality gate still not evidenced.
- [ ] CrowdSec bouncer key remains absent from exact Vaultwarden
  TrueNAS folder inventory. Do not create/rotate secrets as a
  side effect of successful CLI compatibility recovery.

### P0 Vaultwarden inventory acceptance — workstation and TrueNAS

- [x] Workstation and TrueNAS returned the same manifest inventory: only
  `n8n` and `cyberbro` present in the specified Vaultwarden folder;
  all other declared items, including `crowdsec`, marked missing.
  Missing means *exact item/folder mismatch*, not proven absence of a
  credential anywhere.
- [x] TrueNAS local validation: `python3 -m compileall -q
  scripts/secrets/inventory_vaultwarden.py` succeeded and
  `pytest -q tests/test_vaultwarden_inventory_contract.py`
  reported 2 passed.
- [ ] Next: metadata-only reconciliation with existing vault item names,
  without copying credential values, creating placeholders, or rotating
  keys. Prioritize CrowdSec's existing bouncer key before any pfSense
  configuration change.
- [ ] The TrueNAS absolute repository path is not portable to the
  workstation; use its existing checkout directory rather than
  `/mnt/cpool/compose/nabla-compose`.

### P0 Vaultwarden operational inventory tooling (2026-10-10)

- [x] Added `scripts/secrets/inventory_vaultwarden.py` to verify
  canonical CLI base URL, unlocked operator session, expected folder,
  and exact manifest item names/folder membership. Default output only
  includes app and presence status; `--json` is metadata-only.
- [x] Added unit contracts for wrong-folder items, missing items, and
  suppression of mock secret values.
- [ ] **Operator test required:** `python3 scripts/secrets/inventory_vaultwarden.py --app crowdsec`
  should report `crowdsec: missing` until the existing approved
  bouncer key is **safely imported** as `nabla/prod/crowdsec` in
  folder TrueNAS with field `CROWDSEC_PFSENSE_BOUNCER_KEY`.
  Do not copy unrelated pfSense account password or generate key
  implicitly. After inventory succeeds, run the existing renderer;
  do not print generated .env contents.
- [ ] Audit Bitwarden CLI 2026.9.0 / Vaultwarden 2026.6.0
  `KeyIdBackfillError` HTTP 404 separately; successful unlocked
  list operations are not proof that crypto migration succeeded.

### P0 Vaultwarden inventory evidence — CrowdSec (2026-10-10)

- [x] Vaultwarden unlocked; expected `TrueNAS` folder exists and its
  ID matches `config/secrets/manifest.json`.
- [x] Search for `crowdsec` returned three unrelated entries,
  but **not** `nabla/prod/crowdsec`; no available proof that the
  existing pfSense bouncer key is stored there.
- [ ] Perform metadata-only exact inventory search in the TrueNAS
  folder; if no matching item exists, stop automated rendering and
  locate existing key through an approved operator-controlled source.
  Do not reuse unrelated CrowdSec account passwords or implicitly
  create/rotate a bouncer registration.
- [ ] CLI `KeyIdBackfillError` HTTP 404 remains a separate
  compatibility issue despite some `bw list` commands working.

### P0 blocker — Bitwarden CLI endpoint and crypto compatibility (2026-10-10)

- [x] **CLI 2026.8.0 runtime accepted:** operator A/B test proved login with YubiKey OTP, unlock, `bw status=unlocked`, and metadata-only Vaultwarden inventory all succeed. CLI 2026.9.0 reproduces `KeyIdBackfillError`/HTTP 404 against the current Vaultwarden. The TrueNAS bootstrap therefore defaults to checksum-pinned 2026.8.0; 2026.9.0 is retained only for controlled compatibility retesting after a future Vaultwarden/client upgrade.

- [x] TrueNAS Vaultwarden local `http://127.0.0.1:30032/api/config`
  and canonical public `https://vaultwarden.albandrieu.com/api/config`
  pass the repository read-only check; pfSense and system resolver returned
  the same Cloudflare IPv4 addresses. External `1.1.1.1` DNS timed out,
  but the canonical HTTPS endpoint worked.
- [ ] `bw config server` still returned `https://bitwarden.com`
  after `configure-bitwarden-cli-local.sh --apply` reported success.
  Diagnose CLI profile/config persistence and endpoint overrides before
  any secret materialization; `bw status=unlocked` alone is insufficient.
- [ ] Vaultwarden login with current CLI fails `KeyIdBackfillError`
  (server HTTP 404 during user key-id backfill). A bounded A/B test is now
  prepared: keep CLI 2026.9.0 as default, but allow official checksum-pinned
  CLI 2026.8.0 (`NABLA_BITWARDEN_CLI_VERSION=2026.8.0`) to test whether the
  regression is client-side. Compare login/unlock + metadata-only inventory;
  do not alter vault data or disable cryptography. Restore 2026.9.0 after the
  test unless 2026.8.0 is proven necessary as a temporary compatibility pin.
- [x] Cron #8 sanitized executable is `bash` following the
  `env NABLA_DOCKER_IMAGE_PRUNE_MIN_AGE_HOURS=168` prefix.
  Its script path and child Git use remain unverified.

### P0 follow-up — cron identity and CrowdSec secrets (2026-10-10)

- [x] Cron #8 starts with `env NABLA_DOCKER_IMAGE_PRUNE_MIN_AGE_HOURS=168`.
  This resembles an image-pruning task, but its executed binary/script and
  any nested Git calls remain **unverified**. Inspect sanitized executable
  identity before modifying it; do not infer cron caused earlier `sudo git status`.
- [x] `render_from_bitwarden.py --check` validated only
  `config/secrets/manifest.json`; it did not unlock Vaultwarden,
  retrieve the bouncer key or materialize any runtime file.
- [ ] CrowdSec canonical secret file remains absent; legacy source
  `/mnt/cpool/crowdsec/.env.secrets` is an empty placeholder.
  Perform user-context `--app crowdsec --output-file` only with an
  unlocked `BW_SESSION`, install with owner root and mode 0600,
  and test the strict LAPI check before pfSense changes.
- [x] CrowdSec central runtime healthy, Loki hits=10431,
  `PFSENSE_FIREWALL last_pull=<none>` and no active decisions.
  pfSense preflight previously passed with legacy URL still configured.

### P0 operator evidence — Git and CrowdSec (2026-10-10 late)

- [x] Privileged Git calls on the appliance were specifically
  `sudo git status` at 12:09:16 and 12:21:52; `git status` can
  refresh `.git/index`. These are evidenced unsafe invocations,
  not proof that a particular cron was their parent.
- [ ] TrueNAS cron ID **8** is `enabled=true user=root` and its
  command references Git or the repository. Audit its *script identity
  and effective child UID* without printing command secrets; do not
  disable or rewrite it without identifying its purpose.
- [x] Workstation pfSense CrowdSec `--preflight` completed with
  failures=0 warnings=1: engine absent, bouncer running, central
  LAPI TCP 172.17.0.24:8084 reachable, PF tables 31513 IPv4
  and 586 IPv6 entries. The only warning is the legacy
  `http://172.17.0.1:8089` bouncer target.
- [x] TrueNAS CrowdSec central engine is healthy; Loki datasource
  hits=10323, fresh events present, scenario disabled, LAN-only
  listeners healthy, active decisions=0 (not an error).
- [ ] **Cutover blocked:** canonical runtime
  `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` is missing;
  legacy source is an empty placeholder; registered
  `PFSENSE_FIREWALL` bouncer has no `last_pull`. Obtain the
  *existing approved key* from Vaultwarden separately at both
  trust boundaries, confirm secret delivery and strict
  `--check`, then configure pfSense and run `--accept`.
  Do not create a fresh key or rotate implicitly.

### P0 Git evidence — targeted sudo timeline (2026-10-10)

- [x] Appliance evidence: root Git sudo journal entries at **12:09:16**
  and **12:21:52** on 2026-10-10; precise subcommands not yet
  identified. The current index was subsequently observed owned by
  `albandrieu:apps` and writable, with no root-owned index.
- [x] Secret-safe audit operator-validated:
  `sudo_events=199 direct_git=2 root_script_candidates=57`.
  Candidate counts are not evidence of Git index writes.
- [ ] Recover only sanitized Git subcommand names from those
  timestamped sudo events, inspect TrueNAS cron job 8 metadata
  without displaying command arguments, and correlate with index
  ownership changes. Do not alter cron or recursively chown checkout
  without attribution.
- [ ] CrowdSec remains runtime healthy, but cutover requires the
  existing bouncer secret from Vaultwarden and workstation pfSense
  preflight; do not redeploy or change firewall until accepted.

### P0 follow-up — redacted TrueNAS Git audit (2026-10-10)

- [x] `scripts/truenas/diagnose-git-index-ownership.sh` now prints
  aggregate sudo Git/root-script counters rather than raw privileged
  command arguments. Default `--check` remains read-only and scoped
  `--repair` does not run Git as root.
- [ ] Confirm the compact output and correctness on TrueNAS, then identify
  any remaining *actual* root Git callers before changing scheduled tasks.
  Do not equate a `root_script_candidates` count with proven root Git writes.

### Execution checkpoint — 2026-10-10, operator evidence on PR #253

- [x] **YubiKey Manager CLI accepted on workstation:** Ubuntu-packaged `ykman` 5.8.0 is functional and the YubiKey 5 NFC is detected with OTP/FIDO/CCID enabled. The stale `/usr/local/bin/ykman` is bypassed through `~/.local/bin/ykman -> /usr/bin/ykman`. **TrueNAS ykman is intentionally abandoned/not required:** the YubiKey remains on the workstation and OTP can be entered through the SSH terminal for `bw login`; no TrueNAS USB passthrough, container, host Python or package mutation is justified.
- [x] **Git recovered (observed):** main index `albandrieu:apps 0600`,
  `git ls-files` succeeded; root-owned index scan clear after scoped repair.
  The unprivileged ownership diagnostic is working.
- [ ] **Git recurrence prevention:** eliminate remaining root-context Git
  operations in other TrueNAS scripts. A successful repair is not proof that
  all root Git writers have disappeared. Cron ID 6 runs as albandrieu;
  root cron ID 8 remains to be audited by command/child process, without
  printing secret-bearing arguments.
- [x] **Gatus runtime accepted:** TrueNAS `app.update` plus explicit
  `app.redeploy` recreated the container with `GroupAdd=["568"]`;
  `RUNNING`, exit 0, restarts 0, HTTP /health OK, zero recent
  config/permission/database/fatal errors. Existing SQLite inode
  `139:2` preserved; file size 2260992 bytes at acceptance.
- [ ] **Gatus long-term acceptance:** verify stored monitoring history
  via application/API and recovery after a later planned reboot.
  Do not modify or recreate `/mnt/cpool/gatus/gatus.db`.
- [x] **DSOMM/Sentry/Scrutiny runtime checks:** DSOMM HTTP 200,
  22 assessment activities/evidence records; Sentry 14 diagnostics OK;
  Scrutiny web/InfluxDB/collector healthy, four SMART devices accessible.
  Remaining: DSOMM reboot, Sentry fresh end-to-end event,
  Scrutiny `/dev/sde` EPERM classification, Pi-hole reboot.
- [x] **Cyberbro transport baseline:** HTTP 5100 ready; MCP endpoint
  responds HTTP 400 (transport reachable, *not* MCP authentication/tool
  acceptance).
- [ ] **CrowdSec pfSense cutover:** engine and LAPI healthy, Loki
  hits=9124, no active decisions (not a failure); canonical bouncer
  secret absent/empty, `PFSENSE_FIREWALL last_pull=<none>`.
  Render existing key directly from approved Vaultwarden source and
  validate on TrueNAS before workstation-only pfSense cutover;
  do not generate/rotate credentials implicitly.
- [x] **Catalog generators:** operator confirmed declared catalog and
  topology synchronized after Git-index recovery. The separately invoked
  consumer `--check` did not print an acceptance result; recheck in a
  consolidated gate before marking its validation complete.
- [ ] **Quality gate:** full exact-HEAD L3 remains unproven. No bypass
  and no automatic merge.

### P0 — Git index ownership: evidence of root Git access, not proven cron (2026-10-10)

- [x] **Scoped Git-index repair implemented and operator-proven:** the main
  `.git/index` was observed as `root:apps 0600`; targeted ownership repair
  restored access without recursive checkout mutation. The helper
  `scripts/truenas/diagnose-git-index-ownership.sh --repair` now repairs every
  root-owned `index` file under the canonical `.git` tree only, preserves each
  existing mode, reuses the `.git` group, and is protected by a contract test.
- [ ] **Git index recurrence remains open:** journal timestamps correlate one
  recurrence with the Gatus apply window, but that is not yet proof of cause.
  Current `deploy-gatus.sh` already runs Git provenance/diff through `runuser`
  as `albandrieu` when invoked as root. Continue correlating exact index mtime
  with cron/timers/sudo/appliance operations; never use `sudo git`.
- [ ] **Vaultwarden residual resolver drift:** pfSense/Unbound now returns
  Cloudflare IPv4, `/etc/hosts` has no matching override and NSS order is
  `hosts: files dns`. TrueNAS remains internally inconsistent: `getent hosts`
  returns Cloudflare IPv6 and Python `socket.getaddrinfo(AF_INET)` returns
  Cloudflare IPv4, while `getent ahostsv4` and curl still use `172.17.0.24`.
  `nscd` is running and is now the primary suspected stale-cache layer.
  `configure-bitwarden-cli-local.sh --flush-host-cache` invalidates only the
  `hosts` cache through `nscd -i hosts`, then reruns the HTTPS/DNS checks.
  Do not change pfSense again unless post-flush evidence points back to it.

- [x] Source investigation: `docs/truenas-deployment-automation.md`
  records TrueNAS cron **ID 6**, hourly at minute 0, user
  `albandrieu`, running `scripts/cron.sh`.
  The script checks the current branch and only fetches/
  fast-forwards the configured `master` checkout; on PR
  branches it is a no-op. This documented cron is **not**
  evidence of root-origin Git metadata writes.
- [x] Earlier incident
  `docs/incidents/2026-10-10-post-reboot-git-dsomm-gatus-vaultwarden.md`
  explicitly records `sudo git status` followed by a new
  `.git/index` owned by `root:apps 0600` at 12:16.
  Git `status` can refresh and rewrite the index.
  Therefore **root Git invocation is an evidenced cause**
  of the recurring symptom, but attribution of every later
  occurrence to a specific cron/service is still unproven.
- [ ] Verify **actual** TrueNAS cron schedule, root/user
  crontabs, systemd timers and `sudo` journal entries
  around the affected index timestamps. Avoid dumping
  secret-bearing command lines or changing cron jobs
  without evidence. Do not run `sudo git`, repository
  generators or quality gates as root. TrueNAS middleware
  or dataset-specific commands may still need sudo.
- [x] Operator explicitly elected to **discard** staged
  modifications to `scripts/quality/check-compose-config.sh`
  and `scripts/workstation/openclaw-auth-presence.py`.
  Recommended exact restore is `git restore --source=HEAD
  --staged --worktree -- <both paths>`; no stash,
  no repository reset/clean, no submodule overwrite.
- [x] Gatus `repair-gatus-config-access.sh --check`
  rejected the running container because it lacks
  `HostConfig.GroupAdd` GID 568. This is **runtime
  TrueNAS Custom App Compose drift**. Correct/redeploy
  the Custom App definition before the isolated config
  permission `--apply`; do not widen YAML readability
  or mutate SQLite as a substitute.

### P0 A2 — Gatus root cause confirmed, follow-up branch (2026-10-10)

- [x] **Definitive failure evidence:** Gatus container `restarting`,
  exit 2, 564 restarts, no HTTP :8085. Log panic is
  `open config/config.yml: permission denied`. This is a
  generated **configuration read** failure, not a proven SQLite
  problem. File `apps/gatus/config/config.yml` is
  `albandrieu:apps 0640`; Gatus dataset/database are
  `root:root 0770` and remain untouched.
- [x] Added `scripts/truenas/repair-gatus-config-access.sh`
  with `--check` (metadata/read-only) and opt-in
  `--apply` that adjusts only generated `config` directory
  group/mode (apps/0750) and `config.yml` (apps/0640).
  It rejects unsafe paths, incorrect host GID and absent
  Docker `HostConfig.GroupAdd`; no broad chmod, new
  privileges, container restart, SQLite change or data reset.
  Added an offline contract test for these safety constraints.
- [ ] **Appliance-only acceptance:** inspect
  `stat apps/gatus/config`, `docker inspect gatus`
  for `HostConfig.GroupAdd` and actual bind-mount destinations;
  run `--check` and *only if scoped preconditions are met*
  `--apply`. Docker restart policy may retry naturally.
  Validate HTTP 8085, a steady healthy process, SQLite
  history and an eventual reboot. If no supplemental apps
  group is effective, repair the TrueNAS Custom App definition,
  not the dataset permissions.
- [ ] **Parallel work:** preserve P0 pfSense/CrowdSec stability;
  continue value-blind `config/secrets/manifest.json`
  coverage and Backstage v2 service parity. Do not
  materialize new credentials, mutate private state or
  switch the multi-repository catalog without rollback proof.
- [ ] **Validation:** targeted agent tests where tools exist;
  required full L3 remains a before-merge gate rather than a
  demand for repeated user-side ShellCheck/pytest invocations.
  Historical #251 was merged; the recovery is on a follow-up PR.

### P0 A1/A2 evidence — 2026-10-10, PR #251

- [x] Added `scripts/truenas/diagnose-gatus.sh`: bounded **read-only** container status, UID/GID and mount destination metadata, SQLite/config path metadata, and **aggregate log error categories only**. No raw log text, environment, secret value, chmod/chown, restart or database mutation.
- [x] Added `tests/test_gatus_diagnostic_contract.py`; isolated agent fixture: **2 passed** (Bash parse and fake Docker log with canary secret). These are **targeted** tests, not full-HEAD L3 proof.
- [ ] **Runtime root cause remains unknown:** the previous Gatus `exit 2`, missing HTTP 8085 and root-owned 770 dataset are observations, not proof of an ACL defect. Classify the bounded evidence before any UID/permission correction. Check the container's effective user and actual log failure without publishing raw logs.
- [ ] Full local `just pre-push`, pre-commit, Compose config, BetterLeaks, SAST and generated topology on exact PR HEAD: **UNAVAILABLE/NOT RUN in this isolated agent environment** (GitHub archive DNS blocked, no complete repository checkout). Mandatory pre-merge gate unchanged. No automatic merge or runtime change.
- [ ] After verified root cause, implement the smallest Gatus config/identity fix, preserve `/mnt/cpool/gatus/gatus.db`, then separately accept HTTP :8085, persistence/history and reboot recovery.

### Validation policy — agent local first, operator only for runtime acceptance

- [ ] **Agent responsibility:** run and correct `shellcheck`,
  `bash -n`, targeted/full `pytest`, YAML validation, Ruff,
  pre-commit, Compose config, generators, BetterLeaks, SAST and
  Playwright/ZAP **in the agent's own environment wherever feasible**.
  Retrieve exact HEAD source if clone/DNS is blocked, use hermetic
  fixtures for relevant isolated tests, and state precisely what
  ran and what did not. Never claim the full gate is green based on
  partial checks.
- [ ] **Avoid operator-test ping-pong:** do **not** repeatedly require
  `just pre-push`, ShellCheck, pytest or all quality gates on
  workstation/TrueNAS between each small roadmap change. Batch
  operator-only appliance evidence or final acceptance in a single
  bounded checkpoint. An unrelated, known failing gate may remain
  explicit debt while safe independent work continues; agent fixes
  introduced regressions and prioritizes the root blocking issue.
- [ ] **Never bypass safety/quality controls:** do not disable,
  silently skip or weaken pytest, ShellCheck, Ruff, pre-commit,
  BetterLeaks, SAST, Playwright, ZAP, deployment/security contracts
  or mandatory PR checks to accelerate progress. Required full
  quality-gate acceptance remains a **before-merge** requirement,
  distinct from the targeted **before-next-step** gate.
- [ ] **No auto-merge.** No silent TrueNAS app mutations, data
  migrations, public endpoints, secret rotation or Bababou ingestion.
  Preserve rollback, version pinning and authoritative runtime evidence.

### Critical path — close started work first

| Gate | Priority | Work | Exit condition |
| --- | --- | --- | --- |
| A1 | P0 | Stabilize pre-commit YAML/executable hooks and autonomous local-first validation | Targeted agent checks executed; final L3 state tracked |
| A2 | P0 | Diagnose and repair Gatus STOPPED/restart exit 2 without SQLite loss | Correct root cause; HTTP 8085, persistence and history accepted |
| A3 | P0 | Confirm pfSense/CrowdSec DNS/memory stability; close runtime-vs-reboot acceptance on DSOMM, Sentry, Scrutiny, Pi-hole | Critical risk isolated; status declarations reconcile with proof |
| B1 | P1 | Complete `/mnt/cpool/secrets/runtime/<app>/` migration and Vaultwarden recovery per active service | Manifest/path, identity, consumer, restart/rollback proof |
| B2 | P1 | Backstage descriptors, catalog v2 parity/ownership/exposure, prepare FastAPI/Site consumers | Semantic parity and no duplicated authority |
| B3 | P1 | Coordinated `nabla-compose` → `fastapi-sample` → `nabla-site-alban` cutover | Cross-repo contract, runtime/health and reboot proof before legacy deletion |
| C1 | P2 | Cyberbro HTTP, IoC and MCP/LiteLLM least-privilege acceptance | Bounded functional and auth smoke |
| C2 | P2 | Shared Docling for OpenRAG + Open WebUI; version-verified OpenRAG search API/MCP | PDF/table/OCR extraction, known route and ACL |
| C3 | P2 | Private Bababou dataset POC via reviewed read-only subset | Measured retrieval/citation quality and no data leakage |

**Explicitly defer** Karmada/multi-cluster federation, broad image
upgrades, Trivy Operator, new observability daemons, Garage/MinIO/AIStor
consolidation and destructive legacy cleanup until the path above is
sufficiently accepted. Keep outage-driven urgent security fixes eligible
for reprioritization.

**Current proof:** DSOMM 12 tests/22 subtests + HTTP 200 + Docker
capability; Sentry diagnostic 14 OK; Scrutiny healthy web/InfluxDB and
four SMART devices; Pi-hole DNS sync healthy. Gatus was STOPPED with
restart exit 2 and HTTP 8085 unavailable. The canonical source for
the private Bababou dataset has not been located or mounted for indexing.
**Full local pre-push green has not been demonstrated in the provided
evidence.**

## PR #251 — Shared Docling, OpenRAG API/MCP, Open WebUI and Bababou POC (2026-10-10)

Implementation and security gates: [`docs/runbooks/rag-bababou-poc-architecture.md`](./runbooks/rag-bababou-poc-architecture.md).
This is a **planned** architecture, not evidence of runtime deployment or ingestion.

- [x] **Architecture decision** : keep Open WebUI for chat and per-user
  Knowledge; use OpenRAG + shared Langflow + OpenSearch as the
  independently callable RAG service. LiteLLM is the LLM/embedding
  gateway, **not** the RAG retrieval service.
- [x] **Existing declared integration** : `apps/docling/compose.yml`
  already defines a reusable Docling Serve at `docling:5001` /
  `172.17.0.24:5001`, and OpenRAG already sets
  `DOCLING_SERVE_URL=http://docling:5001`. Open WebUI currently has
  no Docling extraction config and no explicit `intranet` network;
  **shared Docling is not yet fully integrated or runtime-proven**.
- [ ] **P0 — common Docling acceptance** : verify actual TrueNAS
  App/image/health, OpenRAG extraction; connect Open WebUI to
  the same Docling endpoint using version-supported settings
  (`CONTENT_EXTRACTION_ENGINE=docling`, `DOCLING_SERVER_URL`),
  network, trust boundary and PDF/table/OCR smoke. One Docling
  runtime; independent document stores and ACL.
- [ ] **P1 — OpenRAG connector** : on the running pinned OpenRAG
  `0.7.1`, inspect supported API and whether MCP `/mcp` exists;
  do **not** assume documentation from `main` applies to 0.7.1.
  Prefer least-privilege MCP for Open WebUI when supported,
  otherwise REST/OpenAPI adapter. Restrict tools to read/search
  and scope by authorized corpus.
- [ ] **P1 — fastapi-sample integration** : consume the same
  restricted OpenRAG search API with separate service identity;
  keep inference/embeddings behind TrueNAS LiteLLM with explicit
  GPU workstation `172.17.0.57:4000/v1` proxy routing.
  Do not expose OpenSearch/Docling/Langflow or a raw MCP endpoint
  publicly. An external `fastapi-sample.fastapicloud.dev` caller
  requires a reviewed Cloudflare Access/service-token boundary,
  permission tests, rate limits and redacted telemetry.
- [ ] **P2 — Bababou RAG POC** : locate and confirm the actual
  `/mnt/cpool` dataset containing the previous Google Drive
  Bababou extraction (exact path not yet verified); inventory
  metadata first, use a **read-only** and authorized subset of
  10–20 documents in separate `bababou-poc` index. Keep PII,
  legal correspondence and private evidence away from Git,
  public endpoints, default traces and externally hosted models.
- [ ] **P2 — evaluation** : with identical documents, embeddings
  and LLMs, compare Open WebUI Knowledge vs OpenRAG on
  recall@5, MRR@10, citation page accuracy, faithfulness,
  latency p95, indexing duration and CPU/RAM/GPU. Include
  access-control, prompt-injection and deletion/erasure tests.
  Store only redacted metrics and synthetic evaluation examples
  in Git; do not commit corpus, chunks or derived private index.
- [ ] **P3** : promote one RAG integration based on benchmark
  evidence, wire Open WebUI plus fastapi-sample, monitor via
  existing Langfuse/Prometheus with private prompts/chunks
  excluded, then rehearse recovery and rollback.

## PR #251 — Gatus crash, Sentry/Scrutiny accepted and secret/catalog cutover (2026-10-10)

- [x] **Sentry** : TrueNAS `diagnose-sentry.sh --check`
  returned **exit 0 / 14 OK / 0 failures / 0 warnings** on
  2026-10-10. This validates its diagnostic contract now,
  but an end-to-end persisted event and reboot recovery remain
  separate acceptance gates.
- [x] **Scrutiny** : TrueNAS app RUNNING (web + collector);
  web healthy with zero restarts and HTTP `/api/health` 200,
  InfluxDB v2.9.1 reachable, collector sees
  `/dev/sda` through `/dev/sdd`. Canonical runtime secret exists
  at `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets` (mode
  600, v2 token scope); **/dev/sde permission denied** is
  a bounded hardware/permission debt. Avoid widening privileges
  until the device's expected SMART support is known.
- [ ] **Gatus P1 incident** : TrueNAS app STOPPED; Docker
  `gatus` restarting with exit **2**, host port 8085 refused.
  Dataset `/mnt/cpool/gatus` and `gatus.db` are
  `root:root 770`; possible denial to a non-root container
  (not yet demonstrated). First inspect bounded restart logs,
  effective UID/GID and config mount permissions. Preserve
  SQLite DB; do not `chmod 777`, delete it or blindly restart.
- [x] **Pre-commit YAML regression** : operator L3 stopped before
  tests at `.pre-commit-config.yaml` line 470, invalid YAML.
  Converted the long inline Compose hook to a named Bash script
  `scripts/quality/check-compose-config.sh`; added a YAML/syntax
  regression test. Isolated local Bash smoke passes both success
  and failing Compose cases. Full L3 on TrueNAS remains pending.
- [ ] **Secret migration** : `config/secrets/manifest.json`
  contains a DSOMM manual baseline `GH_TOKEN` mapping
  and Scrutiny InfluxDB v2 token mappings; **no Gatus or
  Sentry manifest entries currently identified**.
  Sentry Compose already uses canonical
  `/mnt/cpool/secrets/runtime/sentry/{.env.secrets,
  .env.migrator.secrets}` paths but this alone does not prove
  Vaultwarden source materialization. Audit non-secret key names,
  manifest coverage, and bootstrap recovery; do not import values
  or rotate keys automatically.
- [ ] **Canonical catalog** : `catalog/services.json` is generated
  from declarative Compose. DSOMM is still declared
  `status: planned` despite successful runtime check; Gatus
  has no explicit status despite STOPPED. Reconcile intent,
  rollout phase and observed state independently. Update
  `x-nabla` only following approved runtime acceptance, then
  regenerate topology and downstream service consumers; never
  hand-edit `catalog/services.json`.
- [ ] **Execution order** : L3 YAML validation -> Gatus
  read-only crash triage -> Gatus permission/config fix (if
  proven) -> secrets manifest gap analysis -> Backstage/Compose
  canonical entity status reconciliation -> fresh runtime
  acceptance for Sentry/Scrutiny -> reboot test when planned.

## PR #251 — DSOMM runtime accepted, index Git ownership, next Gatus/Sentry/Scrutiny (2026-10-10)

- [x] **DSOMM runtime acceptance (operator)** : `pytest -q
  tests/test_dsomm_contract.py` **12 passed, 22 subtests** ;
  `deploy-dsomm.sh --check` confirms seed DSOMM 5.0.2
  (22 activities, 22 evidences), image 4.4.1, Compose, catalog,
  dataset, effective `NET_BIND_SERVICE` and HTTP readiness ;
  independent `curl` reports **HTTP 200** on
  `http://172.17.0.24:31088/`. **Runtime accepted**;
  reboot/persistence acceptance is **not** yet established.
  No app restart or `--apply` needed.
- [x] **Git permission root cause** : TrueNAS operator is
  `uid=1000(albandrieu)`; `.git` is `albandrieu:apps 755`,
  but `.git/index` is `root:apps 644`. Correct only that index's
  ownership back to `albandrieu:apps` (preserve mode 644);
  do not run Git as root or recursively chown the checkout.
- [ ] **P0 L3** : verify shebang of the exact executable indexed
  `scripts/workstation/openclaw-ops.sh`, update the local branch
  safely and run `just pre-push` on clean committed HEAD. No bypass.
- [ ] **P1 Gatus** : read-only TrueNAS App state/containers,
  HTTP `172.17.0.24:8085`, dataset `/mnt/cpool/gatus`,
  database presence, configuration group permissions. Determine
  migration status before deploying.
- [ ] **P1 Sentry** : execute
  `sudo bash scripts/truenas/diagnose-sentry.sh --check`,
  inspect edge/Relay/Kafka/Snuba with no secret values;
  do not redeploy while inspecting.
- [ ] **P1 Scrutiny** : execute
  `sudo bash scripts/truenas/diagnose-scrutiny.sh --check`,
  inspect collector, InfluxDB and canonical secret metadata;
  avoid `--capture-startup` and state changes.
- [ ] **DSOMM evidence in Git** : the reviewed seeds are already
  versioned. If runtime assessments must be committed, prepare
  a reviewed/redacted export; never copy raw
  `/mnt/cpool/dsomm/state` into a public repository automatically.

## PR #251 — DSOMM CAP_ normalized, Git index permissions and evidence versioning (2026-10-10)

- [x] **DSOMM effective runtime** : operator `docker inspect` reported
  `state=running`, `project=ix-dsomm`,
  `service=dsomm`, `CapAdd=["CAP_NET_BIND_SERVICE"]`,
  `CapDrop=["ALL"]`, new container created 2026-10-10.
  The deployer incorrectly accepted only `NET_BIND_SERVICE`;
  its runtime check now accepts Docker's normalized
  `CAP_NET_BIND_SERVICE` as well. HTTP readiness and uptime
  remain to be confirmed via `--check` (no new `--apply`).
- [x] **Git state source separation** : version-controlled DSOMM
  `config/team-progress.seed.yaml`,
  `config/team-evidence.seed.yaml`,
  `config/seed-activities.yaml` and
  `config/model-activity-index.json` are reviewed templates,
  whereas `/mnt/cpool/dsomm/state/{model,team-progress,team-evidence}.yaml`
  are outside the repository and may include live assessment
  evidence. Import only a reviewed and scrubbed snapshot if
  versioning it is required; preserve separate writable runtime data.
- [ ] **Git permission incident** : `git ls-files` and
  `git status` report `.git/index: Permission denied` on
  TrueNAS; diagnose index ownership and parent directory access,
  correct *only* incorrect ownership/permissions and avoid
  `sudo git`, blanket recursive chmod or disabling pre-commit.
  Reconfirm the executable shebang from the synced HEAD.
- [ ] **Service acceptance** : DSOMM `--check`, port 31088,
  Gatus runtime, Sentry E2E and Scrutiny read-only checks in order.

## PR #251 — pre-push shebang et DSOMM après app.update (2026-10-10)

- [x] **Hook shebang** : `openclaw-ops.sh` possède désormais
  `#!/usr/bin/env bash` au HEAD distant, mais l'opérateur a constaté
  `check-executables-have-shebangs` en échec au HEAD
  `f5b67697ea4d`. Le journal compact ne donne pas le chemin exact ;
  ne pas affirmer que l'échec porte sur ce script sans la liste des
  fichiers incriminés. Contrôler le journal privé `/tmp/tmp.1UY6kFZI9X`
  et les modes Git indexés, puis relancer L3 après `git pull`.
- [x] **DSOMM --apply exécuté sur TrueNAS** : seed, image,
  Compose, catalogue, stockage, modèle existant préservé et direct
  smoke Docker ont réussi ; `app.update` et `app.start` ont répondu
  succès. **L'acceptation a échoué** : conteneur réel sans
  `NET_BIND_SERVICE`, malgré un Compose rendu valide. L'App n'est
  donc pas considérée réparée.
- [x] **Diagnostic durci** : le déployeur relève maintenant, en cas
  de divergence de capacité, l'identité et la date de création Docker,
  le projet/service Compose, l'exit code, les redémarrages et les
  capacités appliquées, sans afficher l'environnement des secrets.
  Ce diagnostic différencie une Custom App non réconciliée et un
  conteneur ancien/orphelin ; il ne change pas l'état du système.
- [ ] **DSOMM action prioritaire** : confirmer la provenance du
  conteneur et la définition persistée TrueNAS, en ne révélant pas
  les valeurs `Config.Env`, `custom_compose_config` ou secrets.
  Comparer `Created`, `com.docker.compose.project`,
  `com.docker.compose.service`, `HostConfig.CapAdd` et
  `app.query`. Ne pas répéter `--apply` aveuglément.
- [x] **Pourquoi préserver un état DSOMM** : Git versionne les
  fichiers seed/config du dépôt, pas les trois fichiers runtime
  `/mnt/cpool/dsomm/state/` (modèle externe pinné et preuves
  utilisateur pouvant évoluer). Sauvegarder cet état avant les
  mutations TrueNAS évite la perte de travaux d'évaluation.
- [ ] **Gatus/Sentry/Scrutiny** : poursuivre les diagnostics en
  lecture seule dans le runbook, sans démarrer de services depuis
  la boucle de correction du pre-push.

## PR #251 — OpenClaw ShellCheck et préparation DSOMM/Gatus/Sentry/Scrutiny (2026-10-10)

- [x] **P0** : l'opérateur a confirmé `15 passed / 22 subtests`
  sur OpenClaw backup + DSOMM. Le `just pre-push` a ensuite convergé
  sur les droits exécutables de `openclaw-ops.sh`, mais ShellCheck
  SC2250 bloquait les références `$mode`, `$id`, `$ROOT`,
  `$value`. Les variables régulières ont été mises en forme
  `${...}` dans le script. Le strict ShellCheck reste actif.
- [ ] **P0** : sur le HEAD commité, exécuter
  `shellcheck -x -P SCRIPTDIR scripts/workstation/openclaw-ops.sh`,
  les tests ciblés OpenClaw/DSOMM puis `just pre-push`. Sans
  exécution locale du vrai ShellCheck dans le conteneur agent,
  ne pas déclarer L3 vert avant preuve opérateur.
- [x] **DSOMM correctif prêt** : le déployeur fait le direct smoke
  avec `--cap-drop ALL --cap-add NET_BIND_SERVICE`, refuse un
  Compose rendu dépourvu de la capacité et contrôle le `HostConfig`
  effectif. Désormais, un `--apply` réutilise le `model.yaml`
  existant si sa version et ses UUID sont valides ; il ne le remplace
  plus systématiquement. Les fichiers team-progress/evidence existants
  restent inchangés. Contrat ajouté, validation runtime à effectuer.
- [ ] **DSOMM intervention** : sauvegarder et vérifier empreintes
  de `model.yaml`, `team-progress.yaml` et `team-evidence.yaml`,
  inspecter l'App existante, puis exécuter explicitement
  `sudo bash scripts/truenas/deploy-dsomm.sh --apply` lorsque
  la gate et les préconditions sont vertes. L'outil peut appeler
  `app.update` puis `app.start` : il s'agit d'une mutation.
  Vérifier ensuite `NET_BIND_SERVICE`, `RUNNING`, HTTP 31088
  et SHA256 des trois fichiers ; ne pas utiliser `docker restart`.
- [x] **Pi-hole DNS Sync** : accepté `healthy`, sessions 16 ;
  pas de réparation à faire au vu des preuves actuelles.
- [ ] **Gatus**, puis **Sentry**, puis **Scrutiny** :
  diagnostics runtime et acceptation en lecture seule via
  [le runbook](./runbooks/2026-10-10-platform-services-acceptance.md) ;
  redémarrer seulement les App pour lesquelles un incident est
  établi et un rollback existe.

## PR #251 — DNS Pi-hole accepté, DSOMM pas encore redémarrable (2026-10-10)

- [x] **Pi-hole DNS Sync** : `sudo bash scripts/truenas/verify-pihole-dns-sync.sh`
  a répondu `OK: Pi-hole DNS sync healthy`. Résolution du
  `docker-socket-proxy` fonctionnelle (adresse IPv6 Docker
  `fdd0:0:0:30::2`), synchronisation initiale achevée, sessions
  API = **16**. `restart_count=1` reste un warning historique à
  surveiller, non un défaut actuel. Pas de redémarrage requis.
- [x] **Quality P0** : `tests/test_homelab_external_services_contract.py`
  **4 passed** ; `just pre-push` a appliqué les droits exécutable
  de `scripts/workstation/openclaw-cron-runs-summary.py`, convergé
  en deux passes, puis buté sur
  `test_openclaw_backup_contract.py::test_rejects_backup_when_gateway_active`
  (**1 failed / 333 passed / 1 skipped / 154 subtests**).
  Le test a été rendu hermétique vis-à-vis des variables d'environnement
  exportées, `BASH_ENV` et des hooks utilisateur, en conservant
  le refus strict de sauvegarde lorsque Gateway est actif.
  **L'assertion exacte de cet échec reste non fournie** ; confirmer le
  test ciblé sur TrueNAS avant de conclure à la cause.
- [x] **DSOMM garde-fou applicatif** : le Compose versionné inclut
  `cap_add: NET_BIND_SERVICE`, mais le conteneur actuel en est dépourvu ;
  les logs montrent `exec /usr/bin/caddy: operation not permitted`.
  Le déployeur vérifie maintenant la présence de cette capacité dans
  le Compose rendu *avant* réconciliation et dans
  `docker inspect` *après* attente d'un App RUNNING ; refuse de
  déclarer le runtime sain sans capacité. Test de régression ajouté.
- [ ] **DSOMM intervention distincte** : ne pas se limiter à
  `docker restart dsomm` ou `app.start` (l'ancien HostConfig resterait
  inchangé). Avant `deploy-dsomm.sh --apply`, vérifier la définition
  Custom App TrueNAS, documenter un rollback, sauvegarder le modèle et
  les deux fichiers d'évidence sans les divulguer, et contrôler l'effet
  de `--apply` sur `model.yaml` (script actuellement susceptible de
  le réinstaller). Réconciliation explicite seulement après ces vérifications.
- [ ] **P0 L3** : tests OpenClaw et DSOMM ciblés puis `just pre-push`
  à l'issue du pull sur HEAD propre. La validation locale de chaque
  sous-contrat ne vaut pas acceptation L3 complète.
- [ ] **P1 suivant** : Gatus, Sentry, Scrutiny après stabilisation
  et qualification DSOMM.

## PR #251 — parallèle qualité / DSOMM / Pi-hole (2026-10-10)

- [x] **P0 catalogue** : `test_active_operator_truenas_services_are_projected`
  s'arrêtait après **204 tests réussis**. Cause : `Plumber` et
  `Vaultwarden` existaient dans `homelab-services.json` mais sans
  `id` canonique alors que `catalog/services.json` les déclare
  `truenas-app`, `presentationRole: service`. Les IDs ont été
  ajoutés et un test protège unicité et noms. Aucun endpoint n'a
  été changé.
- [ ] **Plumber inventaire** : la ligne historique pointe vers
  `172.17.0.57:3001` tandis que la nouvelle déclaration Compose
  annonce `172.17.0.24:31070`. Ne pas modifier la cible
  opérationnelle par hypothèse ; confirmer la migration/runtime et
  ajuster le catalogue seulement après preuve.
- [ ] **P0 validation** : `pytest -q
  tests/test_homelab_external_services_contract.py`, puis
  `just pre-push` sur le HEAD propre. Ne considérer la gate L3
  réussie que lorsque toutes les étapes passent.
- [ ] **P1 DSOMM parallèle (diagnostic en lecture seule)** :
  le Compose versionné contient `NET_BIND_SERVICE`, mais le
  conteneur existant a `CapAdd=null`, `CapDrop=["ALL"]`,
  `no-new-privileges:true`, exit 255 et `exec /usr/bin/caddy:
  operation not permitted`. Relever seulement `HostConfig.CapAdd`
  / `HostConfig.CapDrop`, état Docker et configuration déclarée
  TrueNAS **sans les secrets**. Proposer ensuite une réconciliation
  limitée de la Custom App (pas `privileged:true`), avec sauvegarde
  métadonnées, contrôle des fichiers d'état, smoke et rollback ;
  **aucun apply automatique**.
- [ ] **P1 Pi-hole DNS parallèle (diagnostic en lecture seule)** :
  `verify-pihole-dns-sync.sh` vérifie le DNS du proxy Docker,
  la stabilité du synchroniseur, `Initial sync done`,
  `api_seats_exceeded`, la limite d'API 16 et son ENV.
  Vérifier l'état réel via ce script et le réseau `intranet` ;
  ne pas augmenter arbitrairement la limite de sessions, ne pas
  donner le socket Docker brut au synchroniseur, ne pas redémarrer
  Docker. Si le réseau ou la résolution est défaillant, rétablir
  uniquement la connectivité proxy ↔ intranet avant une reprise
  contrôlée du service.
- [ ] **P1 ensuite** : Gatus, Sentry et Scrutiny un service à la fois,
  en continuant les validations P0 indépendamment.

## PR #251 — Pi-hole DNS sync et contrôles délégués (2026-10-10)

- [x] Échec L3 identifié : `test_pihole_dns_sync_acceptance_contract`,
  après **191 tests réussis, 1 ignoré et 91 sous-tests réussis**.
  Le test demandait la chaîne `getent hosts` dans
  `verify-pihole-dns-sync.sh`, alors que le script appelle
  `probe_container_dns_success` et `probe_container_dns_records`.
  L'implémentation `docker exec ... getent hosts` appartient au
  helper partagé `scripts/lib/probe.sh`.
- [x] Test modifié pour vérifier la source du helper, ses deux appels
  avec les paramètres bornés et l'instruction `getent hosts` dans le
  helper réel. Aucun contournement du DNS, des erreurs Pi-hole
  `api_seats_exceeded` ou du contrôle `webserver.api.max_sessions`.
- [x] Reproduction locale isolée de l'ancienne assertion : **1 échec** ;
  même fixture après correction : **1 succès**. Le test du checkout
  complet exact-HEAD n'a pas été exécuté localement.
- [ ] P0 : relancer le test de contrat puis `just pre-push` sur TrueNAS,
  traiter le prochain échec sans ignorer de hook. P1 service :
  DSOMM `STOPPED` et Caddy `execve EPERM` sur une configuration
  runtime dépourvue de `NET_BIND_SERVICE` ; diagnostiquer sa
  définition TrueNAS avant toute réconciliation.

## PR #251 — Smoke FastAPI/Pyroscope et dérive runtime DSOMM (2026-10-10)

- [x] **P0 test de contrat FastAPI** : `just pre-push` a dépassé les
  contrats Docling (**2 passed** après pull), puis a bloqué au premier
  échec de la suite globale :
  `test_fastapi_observability_smoke_covers_error_trace_and_profile`
  (**1 failed, 187 passed, 1 skipped, 91 subtests**).
  L'assertion `"Pyroscope readiness"` était un libellé de log obsolète.
  Le script réel vérifie `probe_http_success` sur la racine, l'exposition
  `/metrics` puis `/querier.v1.QuerierService/Series` et refuse les
  profils absents. Le test a été aligné sur ces **contrôles fonctionnels**
  sans contourner l'exigence de profils.
- [ ] **Validation P0** : relancer le test ciblé FastAPI, puis
  `just pre-push` depuis un checkout propre. Le prochain échec éventuel
  doit être corrigé avant les modifications de services.
- [x] **DSOMM état/runtime** : `docker inspect` reproduit
  `CapAdd=null`, `CapDrop=["ALL"]`, `no-new-privileges:true`,
  avec **1121 redémarrages** ; le dépôt exige
  `cap_add: NET_BIND_SERVICE`. Logs précédents :
  `exec /usr/bin/caddy: operation not permitted`.
  La configuration effective du conteneur est donc différente de la
  configuration canonique. L'état des fichiers d'évidence doit rester
  préservé.
- [ ] **DSOMM action suivante** : inspecter la configuration persistée
  TrueNAS sans divulguer de secrets, puis planifier une réconciliation
  bornée de la Custom App seulement après P0 vert. Mesurer
  `CapAdd` et santé HTTP `172.17.0.24:31088` après correction.
  Ne pas utiliser `privileged:true` ni assouplir les ACL de l'état.
- [ ] **Ordre P1** : DSOMM → Gatus → Sentry → Scrutiny ; P2 Scanopy,
  Joplin, AutoKuma ; P3 Docling/OpenRAG/LiteLLM.

## PR #251 — Docling contract et DSOMM Caddy EPERM (2026-10-10)

- [x] **P0 Docling** : le service déclare un port Compose sous forme
  structurée `{name: web, target: 5001, published: "5001",
  host_ip: "172.17.0.24", protocol: tcp, app_protocol: http}`. Le
  test attendait l'ancienne chaîne `172.17.0.24:5001:5001`, d'où
  `1 failed, 154 passed, 1 skipped, 64 subtests`. Contrat actualisé
  sans toucher au service ni à son exposition réseau.
- [ ] **L3** : rejouer `python3 -m pytest -q
  tests/test_docling_joplin_contract.py --tb=short`, puis
  `just pre-push` sur le HEAD actuel. L'agent a exécuté une
  reproduction isolée de l'assertion de ports : 1 passed ; cela
  ne remplace pas le test du dépôt complet.
- [x] **DSOMM — cause runtime corroborée** : conteneur actuel
  `dsomm` `restarting`, `ExitCode=255`, `OOMKilled=false`,
  `RestartCount=1109`, `CapDrop=["ALL"]`, `CapAdd=null`,
  `SecurityOpt=["no-new-privileges:true"]`. Logs :
  `exec /usr/bin/caddy: operation not permitted`. Le Compose
  canonique *déclare* `cap_add: NET_BIND_SERVICE` ; le conteneur
  inspecté ne l'a pas. C'est une divergence de posture **déclarée
  versus appliquée**, pas un problème démontré de permissions sur
  les datasets (`700` et `600 root:root`).
- [ ] **DSOMM — prochaine étape explicite** : confronter
  `docker compose -f apps/dsomm/compose.yml config --format json`
  et les métadonnées sans secrets de `docker inspect dsomm`, puis
  revoir la définition Custom App persistée dans TrueNAS. Contrôler
  la conservation du jeu de données avant de réconcilier le runtime
  via une opération `--apply` **distincte, planifiée et surveillée**.
  Ne pas ouvrir `privileged`, retirer `no-new-privileges` ou
  réinitialiser les états pour masquer le problème.
- [ ] **Suite P1** : Gatus puis Sentry puis Scrutiny, un par un
  après résolution du P0 et revue explicite DSOMM.

## PR #251 — quality gate L3 et DSOMM restart 255 (2026-10-10)

- [x] `tests/test_truenas_deploy_output_contract.py` : **8 passed** sur
  TrueNAS. Le gate a également confirmé les contrats pfSense/CrowdSec,
  les primitives runtime et les projections Homarr/Gatus/AutoKuma.
- [x] Échec L3 suivant : `test_agent_error_excerpt_limits_remain_configurable`
  dans `tests/test_agent_offline_check.py`, **1 failed, 6 passed,
  1 skipped** (journal privé : `/tmp/tmp.CFWSNgh4sq`). Cause établie :
  attentes obsolètes `QUALITY_LOG_TAIL:-32` et
  `QUALITY_SUMMARY_LINES:-12`, valeurs réelles `12` et `10`.
  Le test suit maintenant les valeurs publiées sans désactiver le
  contrôle de bornage ni supprimer les diagnostics privés.
- [ ] **P0 L3** : confirmer le contrat ciblé puis `just pre-push`
  sur le dernier HEAD. Ne déclarer L3 vert qu'après un passage complet.
- [x] **DSOMM runtime** : `app.query` indique `STOPPED`,
  `active_workloads.containers=0`, tandis que `docker ps -a`
  montre un conteneur `dsomm Restarting (255)`. État de fichiers :
  dossier `/mnt/cpool/dsomm/state` `700 root:root`, `model.yaml`,
  `team-progress.yaml` et `team-evidence.yaml` en
  `600 root:root`. Cela établit l'existence des données, pas la santé
  de l'application ni l'origine de l'exit code 255.
- [ ] **DSOMM analyse ciblée et lecture seule** : obtenir
  `docker inspect` avec `State.Error`, `ExitCode`, `OOMKilled`,
  `RestartCount`, `Config.User`, `SecurityOpt`, `CapAdd`,
  `CapDrop`, `HostConfig.Privileged` et les dernières lignes de logs,
  sans valeurs d'environnement ni secrets. Vérifier les mounts en
  mode metadata uniquement. Une défaillance Caddy/file-capability
  `execve EPERM` a déjà été observée dans l'incident précédent :
  **hypothèse prioritaire à revérifier**, sans conclure qu'elle cause
  cette occurrence. Ne pas lancer `docker restart`, `app.start`,
  `--apply` ni changer les ACL avant le diagnostic.
- [ ] **P1 services** : ne reprendre Gatus puis Sentry et Scrutiny
  qu'après traitement P0 et une décision explicite sur DSOMM.

## PR #251 — preuve opérateur DSOMM et provenance Git (2026-10-10)

- [x] Vérifications TrueNAS : `pytest -q tests/test_opencre_contract.py`
  **5 tests réussis**. `just pre-push` a convergé en une passe et validé
  la régénération des projections, puis s'est arrêté au contrat
  `test_checkout_provenance_is_local_and_non_blocking` :
  **1 échec, 33 tests réussis** dans le groupe pfSense/CrowdSec.
  Journal privé : `/tmp/tmp.srBqJeenIk`.
- [x] Renforcer le test de provenance du checkout : inspecter uniquement
  `truenas_repo_provenance()`, refuser les opérations Git réseau/mutantes
  (`fetch/pull/push/checkout/switch/reset`), expliciter les contrats
  manquants. La fonction de production n'a pas été modifiée.
  **L'assertion exacte de l'échec d'origine n'a pas été fournie** ;
  ne pas attribuer rétroactivement une cause non démontrée.
- [x] `sudo bash scripts/truenas/deploy-dsomm.sh --check` a établi :
  seed DSOMM 5.0.2 cohérente (22 activités et 22 preuves),
  image `wurstbrot/dsomm:4.4.1` présente,
  Compose et projections synchronisés, dataset `cpool/dsomm`
  présent et non vide ; provenance `HEAD=f1773f969679`,
  `tree=clean`, upstream synchronisé.
- [ ] **DSOMM App STOPPED** : le `--check` a correctement refusé de
  démarrer l'application. Ce n'est ni une erreur de seed ni une preuve
  de disponibilité HTTP. Diagnostiquer `app.query`, workloads, jobs
  et persistance avant une opération explicite `--apply`.
  Ne pas supprimer, écraser ou réinitialiser `/mnt/cpool/dsomm`.
- [ ] **P0** : exécuter le test de provenance ciblé puis
  `just pre-push` sur la branche à jour. Ne pas entamer d'autres
  changements fonctionnels tant que L3 est rouge.
- [ ] **P1** : une fois L3 validé, ordre d'acceptation :
  DSOMM STOPPED → Gatus → Sentry → Scrutiny
  (voir [runbook](./runbooks/2026-10-10-platform-services-acceptance.md)).

## PR #251 — OpenCRE gate + acceptation séquentielle des services (2026-10-10)

- [x] Corriger le test `opencre-contract` : le déployeur exécutable a
  légitimement le shebang `#!/usr/bin/env bash` ; confirmer
  `bash -n` plutôt qu'imposer `not text.startswith("#!")`.
  Le contrôle du mode exécutable et la politique de refus des images
  mutables restent actifs.
- [x] Publier le runbook de vérification **lecture seule** :
  [DSOMM → Gatus → Sentry → Scrutiny](./runbooks/2026-10-10-platform-services-acceptance.md).
- [ ] P0 : sur TrueNAS, vérifier `pytest -q tests/test_opencre_contract.py`
  puis `just pre-push` sur le HEAD commité ; les 9 tests DSOMM, les
  5 tests des audits Cloudflare et `just loop` ont été rapportés verts
  par l'opérateur, mais **pas** le contrôle L3 complet.
- [ ] P1, **une App à la fois** : DSOMM `--check` → preuve de
  persistance/HTTP ; Gatus → historique SQLite et endpoints ; Sentry →
  diagnostic edge/Relay/Kafka/Snuba ; Scrutiny → diagnostic Web,
  collector, InfluxDB et provenance des secrets. Ne pas exécuter de
  `--apply`, `--capture-startup` ou redéploiement sans preuve.
- [ ] P2 : Scanopy/Joplin/AutoKuma puis Docling/OpenRAG/LiteLLM après
  les acceptations de priorité P1.

## PR #251 — Node.js absent du PATH TrueNAS (2026-10-10)

- [x] Diagnostiquer le faux échec de validation Cloudflare : le test
  `test_all_committed_audit_json_passes_vendored_cloudflare_validators`
  échoue avant de lire les audits lorsque `shutil.which("node") is None`.
  **Ce constat ne démontre aucune corruption du JSON d'audit.**
- [x] Étendre `scripts/truenas/bootstrap-dev-tools.sh` : installer
  `node@24.18.1` via `mise --no-config` sous le HOME opérateur et publier
  l'exécutable dans `~/.cache/nabla-compose/dev-venv/bin/node`. Le gate
  réutilise ce venv en tête de `PATH`. Aucun `apt` ni privilège Docker.
- [x] Contrat de régression : `tests/test_agent_quality_gate_contract.py`
  atteste la version pin et le lien vers le binaire utilisateur.
- [ ] **Operator local-first L1/L3** : exécuter
  `bash scripts/truenas/bootstrap-dev-tools.sh` uniquement si Node n'est
  pas déjà accessible ; vérifier `command -v node` et `node --version`
  dans le venv et relancer `pytest -q tests/test_security_audit_skill_contract.py`.
  Poursuivre `just loop` puis `just pre-push` seulement après
  convergence sur un HEAD commité, sans `SKIP` ou `--no-verify`.
- [ ] La roadmap services (DSOMM, Gatus, Sentry, Scrutiny, Scanopy et
  Docling/OpenRAG) reprend seulement quand le P0 L3 passe.

## PR #251 — DSOMM gate recovery and service acceptance (2026-10-10)

- [x] Repair stale **DSOMM test contracts** without weakening deployment security:
  `DSOMM_BASELINE_SUMMARY_OUTPUT` is a configurable Compose expression whose
  default is `/reports/dsomm-baseline.md`; the DSOMM model path is constructed
  from `state_root` and `model_file`, not embedded as one literal string.
  Pinned model/image, manual baseline profile, secret-backed configuration and
  fail-closed custom-app deployment remain unchanged.
- [ ] **P0 quality gate** — run exact `python3 -m pytest -q
  tests/test_dsomm_contract.py --tb=short`; then `just loop` and
  `just pre-push` on a clean, committed HEAD, resolving each reported hook
  before proceeding. The agent's isolated source-contract reproduction is
  partial L1 evidence only, **not** the full suite or L3.
- [ ] **P1 DSOMM service** — first run the read-only
  `sudo bash scripts/truenas/deploy-dsomm.sh --check`. Before any
  `--apply`, inspect storage prerequisites, immutable assessment seeds,
  supported TrueNAS Custom App configuration and image availability. Runtime
  `RUNNING`, HTTP 31088 and persisted evidence are required before claiming
  acceptance or changing `x-nabla.status: planned`.
- [ ] **P1 platform recovery** — triage Gatus and canonical Sentry/Scrutiny
  secrets read-only; do not infer successful migration from passing contracts.
  Confirm live service/secret provenance one service at a time, with rollback.
- [ ] **P2 subsequent services** — resume the planned Scanopy/Joplin/AutoKuma
  first-wave runtime-env migration, then bounded Docling health/conversion and
  OpenRAG/LiteLLM GPU integration. Do not deploy or restart these as a side
  effect of fixing the CI.

## Local-first quality gate compact diagnostics — 2026-10-10

- [x] Keep complete security/lint/test coverage, but print only failed
  pre-commit hook identifiers and pytest failure summaries by default.
  Preserve complete private `mktemp` logs (mode 0600) on failure; successful
  logs are removed. The fallback tail is used only if no structured failure
  lines are found. `QUALITY_LOG_TAIL` and `QUALITY_SUMMARY_LINES` remain
  operator overrides.
- [x] Fix stale agent contract tests: native ShellCheck no longer uses
  docker.sock; aggregate hooks across both `repo: local` sections; align
  the gate's changed-file message and canonical pre-push policy assertions.
- [x] Restore syntactically valid CrowdSec scripts: remove duplicated tail
  and repair the truncated secret check; restore Loki `curl` line
  continuations. Validate with `bash -n` and the existing
  `test_agent_quality_gate_contract.py` syntax preflight.
- [ ] Operator: pull the branch after safely committing any indexed local
  work, run `python -m pytest -q tests/test_agent_quality_gate_contract.py`,
  and rerun pre-commit plus the strict local gate. Do not bypass pre-push
  and do not stage the unrelated `fastapi-sample` gitlink.

## TrueNAS local ShellCheck pre-commit incident — 2026-10-10

- [x] Root cause: official `shellcheck-precommit` hook invokes Docker;
  non-privileged TrueNAS operator cannot access
  `unix:///var/run/docker.sock`, so the commit fails *before* shell
  linting. **Do not add operator to `docker` group, run hooks with
  `sudo`, disable ShellCheck, or bypass pre-push**.
- [x] Replace Docker-based hook with `repo: local`, `language: system`,
  `entry: shellcheck`, preserving `-x -P SCRIPTDIR` and exclusions.
  Existing `bootstrap-dev-tools.sh` installs pinned ShellCheck 0.11.0
  under the operator's home via `mise`/venv. Contract test added.
- [ ] Operator: `command -v shellcheck && shellcheck --version`;
  install in home using the documented TrueNAS tool bootstrap only
  if absent. Re-run `pre-commit run shellcheck --files` for the
  four executable scripts before retrying the permission commit.
- [ ] Re-run bounded local gate, resolve actual ShellCheck diagnostics,
  reconcile remote HEAD with `git fetch`, then push without
  `--no-verify`, `sudo git` or `--force`.

## Consumer hook and stash hygiene — 2026-10-10

- [x] Repair `scripts/quality/check-service-consumers.sh`: prior
  `git ... || cd ... && pwd` executed `pwd` even when Git succeeded,
  yielding two newline-separated roots and breaking `cd` at pre-commit.
  An explicit `if/else` now selects exactly one path; isolated
  checkout/archive test added.
- [ ] Operator: after pulling this fix, rerun staged pre-commit and
  complete the generated-only commit; never stage the unrelated
  `fastapi-sample` gitlink.
- [ ] Keep a **stash-free active workflow** after acceptance. First
  inspect `git stash list`; then drop only the two recent
  generated-catalog stashes by message, preferably by stash object ID
  after verifying them. The older stashes (other branches) may contain
  unrelated unrecovered work and must not be cleared automatically.
- [ ] Confirm the five generated assets pass both generator `--check`
  commands and the consumer quality hook on the same checkout/HEAD.

## Operator follow-up: Git-generated files and DSOMM check (2026-10-10)

- [x] Operator repaired Git index ownership in the superproject and nested
  submodules; ordinary `git status` now works without `sudo`. Preserve
  unrelated `fastapi-sample` submodule HEAD drift.
- [x] Both catalog generators and `--check` commands passed on TrueNAS.
  Generated topology, services, Gatus, Homarr and AutoKuma changes are
  **uncommitted**; preserve them while updating the source branch.
- [ ] To integrate upstream changes without losing local artifacts:
  `git stash push -m "pre-pull generated catalogs" --` for **only**
  the five generated paths, followed by
  `git -c pull.rebase=false pull --ff-only origin
  fix/agent-compose-gate-offline-followup`; regenerate and re-check.
  Keep the stash for rollback, do not pop stale generated outputs on
  top of newer inputs. Inspect/commit the regenerated diff separately.
- [x] DSOMM direct Docker smoke now uses the same minimal
  `NET_BIND_SERVICE` exception as Compose; `--check` fails fast when
  the TrueNAS App is STOPPED instead of waiting the entire timeout.
- [ ] Validate DSOMM `--apply` only after reviewing the fresh generated
  catalog diff, then accept actual health and stable restart count.
- [ ] Gatus config mode fix (`0640` and group ID) is in PR but the
  observed `0600` regeneration was from older local HEAD. Confirm
  TrueNAS `apps` group GID and active file ownership, update generator
  and Compose, reconcile Gatus only after checking runtime group access.

## Post-reboot LIGHT profile and runtime acceptance (2026-10-10)

- [x] Define explicit optional app set in
  `config/truenas/restore-optional-apps.txt` (Graylog, Zabbix,
  Transmission and the *arr family). Default restore behavior excludes
  this final optional wave even if an older restore list requests it.
- [x] Add `restore-optional-apps.sh --check|--stop|--start`.
  It uses exact TrueNAS App IDs, refuses protected foundation services
  and refuses interruption of in-flight `DEPLOYING` Apps.
- [x] Add bounded read-only `triage-post-reboot-apps.sh` for
  non-RUNNING Apps and problematic containers.
- [ ] On TrueNAS, verify the actual App IDs and update optional list;
  check that no required service depends on an optional workload.
- [ ] Run read-only triage first; distinguish intentionally STOPPED
  optional Apps from `DEPLOYING`/`CRASHED` core applications.
- [ ] **DSOMM:** validate seeds, runtime image and canonical storage with
  `deploy-dsomm.sh --check`; apply only after an exact failing
  precondition is understood, then prove healthy HTTP and saved state.
- [ ] **Cyberbro:** verify two Compose services, diagnostics and canonical
  env materialization with `diagnose-cyberbro.sh` and
  `bootstrap-cyberbro-env.sh --check`. Only reconcile/redeploy after
  identifying failed dependency, permission, secret contract or readiness.
- [ ] **Secrets:** take a global read-only
  `bootstrap-repository-env-files.sh --check` inventory, then stage and
  finalize each App separately using the canonical Vaultwarden manifest.
  Never overwrite existing nonempty `.env.secrets`, never print values,
  preserve rollback and never finalize a failing runtime.
- [ ] Reboot acceptance: foundation RUNNING, no core App stuck
  DEPLOYING/STARTING, no unauthorized optional auto-start, and all
  previously accepted secrets/loadable integrations unchanged.

Commands and safety boundary:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/triage-post-reboot-apps.sh
sudo bash scripts/truenas/restore-optional-apps.sh --check
sudo bash scripts/truenas/restore-app-set.sh --check --apps-file config/truenas/restore-foundation-apps.txt
sudo bash scripts/truenas/deploy-dsomm.sh --check
sudo bash scripts/truenas/diagnose-cyberbro.sh
sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check
```

Stop optional apps only by explicit operator action:
`sudo bash scripts/truenas/restore-optional-apps.sh --stop`.
Later opt in to the final optional wave by
`sudo bash scripts/truenas/restore-optional-apps.sh --start`.
A `restore-app-set.sh --apply` defaults to LIGHT unless
`--include-optional` is passed. Do not treat STOPPED optional Apps
as a platform recovery failure.

## Targeted post-reboot incident follow-up (2026-10-10)

Runbook: [Git/DSOMM/Gatus/Vaultwarden/Scrutiny incident](./incidents/2026-10-10-post-reboot-git-dsomm-gatus-vaultwarden.md).

- [x] Identify `dsomm` exit 255 as Caddy `execve EPERM`,
  consistent with the upstream file-capability versus `cap_drop: ALL`
  issue; source fix adds only `NET_BIND_SERVICE` back to the bounding
  set. **Runtime validation pending**, not yet a confirmed repair.
- [ ] Correct Gatus read access to `apps/gatus/config/config.yml`
  using the **actual** container UID and TrueNAS path ACL. Do not
  loosen all dataset permissions or modify application data.
- [ ] Correct `bitwarden-api`'s persisted `http://vaultwarden`
  Bitwarden CLI server URL; tracked Compose already specifies HTTPS.
  Check old Doco-CD adapter consumers, back up only the affected
  CLI config and verify TLS before its isolated restart.
- [ ] Repair the TrueNAS operator's `.git/index` ownership/access
  without `sudo git` or reset/clean on the nested
  `fastapi-sample` submodule.
- [ ] Reconcile Scrutiny after operator removed its repository-local
  legacy file and commented a possible old InfluxDB token in the
  canonical file. Do not uncomment unverified credentials, restage,
  finalize or rotate as a batch. Missing `dotenv` under system Python
  requires the existing **user-space venv**.
- [ ] Confirm DSOMM/Gatus/Vaultwarden acceptance via runtime health and
  exact-HEAD generator/quality gate checks before closing the incident.

## Runtime evidence — 2026-10-10, post-reboot (user-provided)

- [x] LIGHT review: `emby`, `graylog`, `lidarr`,
  `transmission`, `zabbix` are STOPPED; the remaining optional
  `*arr` names in the configured list are ABSENT. This is **expected**,
  not a recovery failure. Do not bulk start them.
- [x] Cyberbro: TrueNAS App `RUNNING`, two Compose containers running,
  web healthy, MCP HTTP 400 reachable (not a standalone TrueNAS App),
  zero restarts and canonical Cyberbro `.env`/`.env.secrets` contract
  accepted. No Cyberbro redeploy required.
- [ ] DSOMM: TrueNAS `STOPPED`, Docker `dsomm` restarting exit 255.
  Seed check passed (22 activities/22 evidence), pinned image exists and
  Compose validation passed. Fix catalog generator defect first (orphan
  `openwebui-pipelines` icon + missing `subprocess` import; source fixes
  in this PR), regenerate the catalog/consumers, then capture **bounded
  DSOMM logs** and TrueNAS app job errors. Do **not** assume a catalog
  error caused the Docker restart loop. Do not blindly redeploy.
- [ ] Gatus: TrueNAS `STOPPED` but container `Restarting (2)`.
  Diagnose its startup/config and regenerate Pipelines-derived monitors
  before a controlled restart; do not classify as intentional LIGHT.
- [ ] `bitwarden-api`: Docker restart exit 1; inspect owning project,
  active consumers and its logs separately. Avoid rotating Vaultwarden
  or upstream tokens without evidence.
- [ ] Docling: `ABSENT` (not `DEPLOYING`); schedule explicit install
  only once prior state and resources are verified.
- [ ] Scrutiny secrets: **hard conflict** between
  `/mnt/cpool/scrutiny/.env.secrets`, repository-local
  `apps/scrutiny/.env.secrets`, and canonical
  `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets`.
  Compare **key names and semantic equality without printing values**,
  preserve historical InfluxDB token and do not issue `--restage` or
  `--finalize` until source authority is reconciled.
- [ ] `.env.secrets` global inventory: 8 declared missing-source apps,
  empty placeholders including AutoKuma, CrowdSec, Joplin, PostgreSQL and
  Scanopy, plus numerous staged/finalize-pending apps. Treat
  intentionally disabled/not-installed services separately; no empty
  secret placeholders accepted as production credentials. Finalize
  individually after the runtime consumer passes.

Safe next TrueNAS commands (bounded output, no raw secret values):

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/triage-post-reboot-apps.sh
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check scrutiny
sudo python3 scripts/secrets/compare_dotenv_sources.py --app scrutiny \
  --left /mnt/cpool/scrutiny/.env.secrets \
  --right /mnt/cpool/compose/nabla-compose/apps/scrutiny/.env.secrets
sudo docker logs --tail 50 dsomm 2>&1 | tail -50
sudo docker logs --tail 40 gatus 2>&1 | tail -40
sudo docker logs --tail 40 bitwarden-api 2>&1 | tail -40
```

**Quality gate distinction:** generator source defects fixed in PR; output
catalog, topology, Gatus, Homarr and AutoKuma projections still require
canonical regeneration and L3 exact-HEAD validation. No runtime changes
have been made by the agent.

## Restart context — 2026-10-10

État de reprise canonique pour un nouveau chat/agent :

- PR active : `#251`, branche `fix/agent-compose-gate-offline-followup`; ne jamais merger automatiquement.
- Local-first obligatoire : corriger le premier échec déterministe avant toute nouvelle amélioration, puis rejouer `bash scripts/agent-pre-push.sh`.
- OpenClaw : le test backup `Gateway active` est désormais compatible TrueNAS `/tmp noexec`; `openclaw-ops.sh` doit rester `100755` avec shebang Bash explicite.
- Vaultwarden : RCA confirmée. Un Host Override pfSense
  `vaultwarden.albandrieu.com -> 172.17.0.24` génère
  `/var/unbound/host_entries.conf`. Le supprimer côté pfSense et conserver, si nécessaire, un nom privé séparé `vaultwarden.int.albandrieu.com`.
- pfSense syslog : émission RFC5424 réelle prouvée
  `172.17.0.1:514 -> 172.17.0.24:1514`; Alloy/Loki valident deux runs consécutifs `exit=0 ok=10`.
- CrowdSec central TrueNAS : `crowdsecurity/crowdsec:v1.8.1`, healthy, LAPI `:8084`, metrics `:6060`, scénario `firewallservices/pf-scan-multi_ports` désactivé.
- CrowdSec Loki acquisition : événements pfSense réels visibles ; `cs_lokisource_hits_total` confirmé et croissant (174 → 180 → 287). Étapes pfSense→Alloy→Loki→CrowdSec terminées.
- Bouncer pfSense : encore sur LAPI local `http://172.17.0.1:8089`; ne pas basculer vers `172.17.0.24:8084` tant que credential/registration/last_pull ne sont pas validés.
- Syslog legacy : `172.17.0.57:1514` est une ancienne cible workstation à retirer ; la cible canonique doit rester `172.17.0.24:1514`.
- Bitwarden/secrets : explicitement différés jusqu'après stabilisation du bouncer. Ne pas bloquer la chaîne observabilité dessus.
- Quality gate actuelle : le dernier blocage observé est le contrat shebang/executable OpenClaw ; corriger sans `--no-verify`, puis relancer la gate complète.
- Git local : préserver tout commit local non poussé ; si la branche distante avance, inspecter `HEAD...@{upstream}` et merger/rebaser sans reset destructif.

Prochain ordre de travail :

1. obtenir une gate locale L3 verte sur le HEAD courant ;
2. supprimer l'Host Override public Vaultwarden et valider public Cloudflare + privé `.int` ;
3. nettoyer la cible syslog workstation `.57` ;
4. préparer/valider le credential et la registration du bouncer central ;
5. basculer le bouncer pfSense vers `172.17.0.24:8084` ;
6. exiger `last_pull` non vide et décisions visibles avant acceptation ;
7. seulement ensuite reprendre Bitwarden/secrets.

### P0 evidence update — skill review and LiteLLM (2026-10-10, PR #253)

- [x] Classify failed OpenClaw cron runs without printing virtual-key prefixes or content: `scripts/workstation/openclaw-cron-runs-summary.py`.
- [x] Add a CLI-only read-only entry point for the failing main skill review: `bash scripts/workstation/openclaw-ops.sh --skill-review`.
- [ ] Resolve actual `openclaw-main` key-budget exhaustion (10.046146 / 10.0): inspect LiteLLM usage/reset period and reduce job usage, do not override budget or treat shared-key model fallback as recovery.
- [ ] Verify main `skill-collection-review` actually succeeds after budget resets; one retained run failed after 272541 ms, five consecutive failures reported by the job status.
- [ ] Separately resolve embedding provider 401 and paused main/cron vector indexes, preserving backup and secret isolation.

See [the OpenClaw remediation runbook](./runbooks/2026-10-10-openclaw-workstation-remediation.md) for source evidence, commands, acceptance and rollback.

## OpenClaw personal assistant — workstation stabilization

**Scope:** OpenClaw manages personal Gmail/WhatsApp triage and proposed replies
(read-only by default); Hermes manages development/cloud/cybersecurity. Their
secrets, memory, tokens and tools must remain isolated. No private message
contents or tokens may enter Git, logs or CI artifacts.

- [ ] **P0 read-only audit:** from the repo on the workstation run
  `bash scripts/workstation/diagnose-openclaw.sh`. Codes 0=clean,
  2=warnings (including preserved foreign `/usr` destination), 1=failure.
  This intentionally does not invoke `openclaw doctor`, which has been
  observed installing a plugin even with `--non-interactive`.
- [ ] **P0 recovery gate:** run `bash scripts/workstation/backup-openclaw.sh --check`.
  Stop/quiesce the user Gateway **manually** during maintenance; create an
  offline archive via `--create` (refuses a running service), then separately
  run `--verify ARCHIVE` and `--restore-test ARCHIVE`. Only then restart the
  Gateway manually. Backup is private (0600), its directory 0700, and is not
  uploaded to Git. The restore-test checks archive safety and readability,
  **not** full application-level restoration or session compatibility.
  Backup omits symlinks/sockets; inventory those separately if used.
- [ ] **P0 Node divergence:** run
  `bash scripts/workstation/prepare-openclaw-systemd.sh` to **print only**
  an override for the observed systemd unit using `/usr/bin/node`, while
  the CLI uses mise Node 24.18.1. It refuses unfamiliar service flags; it
  neither installs the override nor restarts the Gateway. Preserve any
  separately owned `/usr/lib/node_modules/openclaw` package.
- [ ] **P1 application:** after validated rollback, align systemd runtime
  and npm prefix, then run update dry-run and controlled update; repair
  Slack state migration, inspect SQLite sessions (29 warnings), reconcile
  WhatsApp plugin version/reconnect, review cron errors and migrate
  cleartext tokens to SecretRefs. Reverify channels, sessions and Gateway
  after restart and reboot; do not declare 2026.9.9 installed based on dry-run.
- [ ] **P2 personal workflows:** test Gmail and WhatsApp with synthetic data
  in read-only mode; require explicit approval for any sending, deletion,
  archiving or labeling, including cron-triggered actions.
- [ ] **P3 TrueNAS:** only after workstation acceptance, stage isolated,
  pinned Compose/ZFS/secret-backed deployment; prove restore with all
  personal connectors disabled; coordinate single-owner cutover and failback.
- [ ] **Quality gate:** run
  `python -m pytest -q tests/test_openclaw_workstation_contract.py`
  and `bash -n scripts/workstation/*openclaw*.sh` locally, no GitHub Actions.

Observed workstation baseline (2026-10-09): OpenClaw 2026.9.5,
CLI mise Node 24.18.1, Gateway service /usr/bin/node, target 2026.9.9
**dry-run only**. No direct access to workstation from this repository
change; acceptance requires its actual runtime evidence.

## Current execution order

1. **P0 runtime closure:** stabilize the pfSense edge-memory/DNS regression,
   then complete the TrueNAS acceptance queue above.
2. **P0 agent engineering:** improve the local-first agent loop, evaluate Dagger
   as portable execution and add Context7 for current version-specific external
   documentation.
3. **P1 dependency automation:** finish hosted Mend Renovate acceptance without
   depending on GitHub Actions runners for routine updates.
4. **P2 catalog/security:** advance Backstage/catalog v2 and accept already
   declared security/inventory tools before adding more always-on services.
5. **P3 observability/runtime:** migrate Grafana before
   Mimir / Loki / Tempo / Alloy, then reconcile Prometheus and cross-signal
   observability.
6. **P4 Kubernetes/federation:** finish the single-cluster storage/security/
   ingress baseline before Karmada/workstation/cloud GPU federation.
7. **P5 cleanup/identity:** only after the runtime foundation above is stable.

## Accepted platform baseline

Keep detailed proof in incidents/runbooks. Current accepted foundations are:

- Talos `v1.13.9` / Kubernetes `v1.36.3` is 3/3 Ready after controlled
  recovery; Docker/IPAM and VM autostart are proven;
- `materialize-reboot-bundle.sh` and the controlled reboot transaction are
  accepted; the historical CSI orphan was **successfully removed** after
  **complete quiesce**;
- TrueNAS CSI dynamic provisioning, cross-worker RWX and fresh reclaim
  postconditions are accepted;
- Sentry end-to-end ingestion and Suricata `br0` capture/EVE are established
  baseline evidence;
- canonical storage/config/runtime-secret separation and value-blind migration
  tooling are implemented;
- local-first agent gates, Betterleaks, Just/Mise, shared Compose discovery,
  JSON Schema secret validation and shared TrueNAS/Docker/probe primitives are
  repository-owned.

## P0 — runtime/storage/secrets closure

### P0.1 — TrueNAS lifecycle and DNS

- [ ] Continue reducing `no topology mapping`; declare `runtime.appId` only
  when ownership is genuinely ambiguous.
- [ ] Move service-specific readiness into declarative lifecycle metadata where
  it removes duplicated policy.
- [ ] Keep current + previous known-good reboot bundles until another normal
  reboot cycle passes.
- [ ] **pfSense edge-memory / DNS resilience regression:** repeated FreeBSD
  reclaim/OOM kills on 2026-10-08 removed Unbound at 02:10 and 11:03 and killed
  `php_pfb` at 19:00. Current evidence points to combined edge-capacity pressure
  rather than native Unbound caches alone: Unbound Python DNSBL, Snort, the
  generated PHP-FPM pool and a broken CrowdSec event path can overlap on the
  memory-constrained Netgate 1100.
  - [x] Set pfBlockerNG `ASN Reporting=disabled` while `asn.mmdb`/`asn.csv`
    are absent and no IPinfo token is configured; verify the repeated IPinfo
    download attempts stop.
  - [x] Stop the CrowdSec engine after `firewallservices/pf-scan-multi_ports`
    accumulated millions of failed event-send attempts; keep the firewall
    bouncer independent while the engine is isolated.
  - [x] Diagnose CrowdSec event backpressure without restarting the engine.
    Workstation evidence on 2026-10-10 shows 19,213 stuck lines,
    `max_failed_sent=19,899,999`, `max_attempts=19,900,000` and
    `max_sigclosed=0`: a live `pf-scan-multi_ports` leaky bucket is spinning
    internally while the independent firewall bouncer remains healthy. Treat
    this as a major CPU/memory-pressure contributor, not sole-cause proof for
    every OOM.
  - [ ] Complete the pfSense Small cutover in two independent gates:
    first reconcile CrowdSec 1.8.1 centrally on TrueNAS with
    `deploy-crowdsec.sh --check` then explicit `--apply`; require
    `diagnose-crowdsec-cutover.sh --runtime` to prove image, LAPI/listeners,
    Loki acquisition and removal of `firewallservices/pf-scan-multi_ports`.
    A missing bouncer credential does not block this central-runtime repair.
    Only after the canonical credential is materialized, require
    `diagnose-crowdsec-cutover.sh --check` before the pfSense change and
    `--accept` afterwards. The central engine must reuse the existing
    Alloy/Loki pfSense stream `{job="pfsense",device="pfsense"}`; do not add a
    second syslog receiver or depend on nonexistent `/mnt/cpool/logs/pfsense`
    files. Keep the local pfSense Security Engine stopped; do not restart it
    merely to collect metrics.
  - [ ] Correlate the Snort 02:09 rule-update job with the 02:10 OOM before
    changing its schedule; keep optional restart/reload churn bounded meanwhile.
  - [ ] Measure the generated PHP-FPM `pm.max_children=8` pool under normal
    traffic before any supported persistent tuning; do not hand-edit generated
    runtime config. Keep detailed tuning in
    [`pfsense-php-fpm-hardening.md`](./pfsense-php-fpm-hardening.md).
  - [x] Reduce untrusted WebConfigurator/API ingress: WAN TCP/10443 now uses
    `PFSENSE_ADMIN_WAN` (one reviewed public source) followed immediately by
    an explicit `any -> WAN address:10443` block. The block matched untrusted
    traffic immediately and sampled public `root`/`admin` PHP-FPM
    authentication failures stopped afterwards.
  - [x] Remove the malformed legacy `ExternalOffice` alias after resolving its
    rule references. It contained one office address plus all 256 LAN /24
    addresses expanded individually; the replacement admin alias resolves only
    to `80.15.4.233`.
  - [x] Repair the rejected pfSense exporter credential: create dedicated
    `pfsense_exporter`, rotate the stale key, prove HTTP 200 for
    `status/system`, `status/gateways` and `status/services`, then restore
    the exporter and obtain real pfSense metrics. Keep the identity lifecycle
    repository-managed and separate from FastAPI/admin identities.
  - [x] Observe multiple normal 300-second Prometheus cycles after rotation:
    the last `172.17.0.24` authentication failure was observed at
    `2026-10-09 20:41:24`, with no recurrence across the following 20:xx/21:xx
    checks. Exporter credential regression is closed.
  - [ ] Revalidate TrueNAS/HAProxy TCP/7000 source policy separately after the
    legacy alias removal; do not use the FastAPI Cloud public hostname as a
    source identity because ingress DNS does not prove stable cloud egress.
  - [ ] Keep Unbound out of Service Watchdog during OOM remediation; reassess
    guarded recovery only after the memory policy is stable, rather than hiding
    a kill/restart loop.
  - [ ] Exit gate: sustained observation with no new allocation/reclaim kills,
    stable Unbound/Kea DNS/DHCP, no ASN retry spam, and bounded
    Unbound/Snort/PHP-FPM/CrowdSec RSS plus free-memory headroom under normal
    WebGUI/API traffic. Incident evidence:
    [`2026-10-08-pfsense-unbound-oom-wan-exposure.md`](./incidents/2026-10-08-pfsense-unbound-oom-wan-exposure.md).
- [ ] DNS maintenance acceptance: only after the edge-memory exit gate, stop
  Pi-hole during a controlled window, rerun pfSense posture + Talos
  ResolverStatus/DNSUpstream checks and prove public registry resolution through
  pfSense/Unbound.
- [ ] Keep the TrueNAS LXC GitHub Actions runner dormant until a concrete need
  justifies operating it.

### P0.2 — CSI

- [x] Dynamic provisioning, publishContext, RWX and reclaim postconditions.
- [x] Restricted-style smoke Pod hardening and appliance-side reclaim proof.
- [ ] Replace deprecated `auth.login_with_api_key` before TrueNAS 27; a
  TrueNAS CSI version bump alone does not close this authentication debt.

### P0.3 — TrueNAS storage + runtime secret normalization

Target runtime path remains:

```text
/mnt/cpool/secrets/runtime/<service>/
```

Vaultwarden bootstrap remains independently recoverable under:

```text
/mnt/cpool/secrets/bootstrap/vaultwarden/
```

Open work:

- [ ] close the immediate DSOMM/Sentry/Scrutiny/Code queue above;
- [ ] after DSOMM runtime acceptance, pilot importing one existing Custom App
  into `truenas_app.custom_compose` with the existing OpenTofu/Terragrunt
  stack. Require an empty post-import plan plus a no-op apply before replacing
  repository deploy scripts; keep those scripts as recovery tooling until
  reboot/rollback acceptance. Evaluate provider v3.x separately from the
  currently pinned `PjSalty/truenas ~> 2.4.1` so a major provider upgrade is
  not mixed with the first App-state migration.
- [ ] accept Scanopy/Joplin/AutoKuma and Sample one service at a time;
- [ ] convert remaining explicit legacy `env_file` declarations to canonical
  runtime paths, keeping compatibility paths until restart/reboot acceptance;
- [ ] classify repository-local ignored `.env*`: secrets → Vaultwarden,
  non-secret config → tracked config, obsolete → remove only after consumer proof;
- [ ] review Apps-preset drift without recreating non-empty datasets;
- [ ] continue Vaultwarden waves only for `active` services by default:
  foundation/state → platform/network/observability → AI/RAG;
- [ ] preserve migration-critical values during path cutover; rotate only after
  runtime + reboot acceptance;
- [ ] reconcile live Doco-CD against canonical Compose and retire the inactive
  1Password bootstrap dependency only after its remaining consumers are mapped.

## P0.4 — AI agent and local-first engineering

Accepted local loop:

```text
just context
  -> just preflight
  -> targeted contract
  -> just loop
  -> commit logical batch
  -> just pre-push
  -> one push
  -> inspect existing remote checks
```

Evidence levels remain L0 static, L1 targeted, L2 changed-file convergence and
L3 full local publication. Only L3 means the complete local gate is green.

- [x] Prevent offline source checks from passing on a failed Git comparison;
  parse Python sources in one interpreter, retain an opt-in scope limit and
  keep error excerpts bounded without truncating forensic logs.
- [x] Define exact-HEAD GitHub-connector/source-snapshot recovery in the
  `local-first-quality` skill; use already-existing artifacts only and never
  treat source-only verification as a full Git publication proof.
- [x] Keep bounded agent context operational when a cached Git base exists
  but has unrelated history; never fetch merely to print changed-path context.
- [ ] Demonstrate L3 on the PR's exact checkout with cached dependencies;
  report first actionable failure only, and preserve security/formatter checks.

### Dagger — portable local/CI execution

Dagger remains a **beta parity PoC**, not a second source of quality policy.
The canonical publication evidence remains `agent-pre-push`.

- [x] Add a bounded `dagger.toml` workspace with
  `defaults_from_dotenv=false`, generated checks disabled for the PoC and
  sensitive/heavy source trees excluded.
- [x] Start with native concerns already owned by the repository:
  **ShellCheck + Biome**; module sources are commit-pinned.
- [x] Pin Dagger `0.21.10` in Mise/mise.lock and centralize the
  workspace/check surface in one non-secret Mise value,
  `DAGGER_WORKSPACE_RELEASE=v1.0.0-beta.15`; task commands reference only
  that value.
- [x] Make Biome reproducible before benchmarking:
  `@biomejs/biome=2.4.12` is exact in package.json/package-lock; the Dagger
  module is pinned to official commit
  `03db7bbf81087918657205c1eace20dfff7e29b3`, uses a digest-pinned Node
  image, forces npm and installs with `--ignore-scripts`.
- [x] Replace the legacy `detailyang/pre-commit-shell` wrapper with the
  official `koalaman/shellcheck-precommit@v0.11.0`; the native reference no
  longer depends on an unpinned system ShellCheck binary.
- [x] Align the relevant ShellCheck exclusion set with the native Pre-commit
  contract, including `biscuitcutter.sh`.
- [x] Make native Biome parity non-mutating: use the exact local
  `node_modules/.bin/biome check` after `npm ci --ignore-scripts`, not the Pre-commit
  `biome-check` hook because that hook runs with `--write`.
- [x] Keep the PoC credential-free:
  `defaults_from_dotenv=false`; Mise-loaded operator `.env*` values are not
  Dagger module settings/defaults. Any future credential must use an explicit
  Dagger `Secret` input and receive a separate security review.
- [x] Fail closed: `dagger-list`, `dagger-poc` and `dagger-bench` refuse
  execution until a reviewed `dagger.lock` exists.
- [x] Add mature OSS benchmark tooling instead of custom timing code:
  Hyperfine `2.0.0` is pinned through Mise; `just dagger-bench` compares
  the two stable recipes `just dagger-native-parity` and `just dagger-poc`
  using one warmup + three runs.
- [ ] Run `just dagger-sync` on a supported container runtime, review/commit
  the generated `dagger.lock`, and verify that the official ShellCheck
  module's internal `koalaman/shellcheck-alpine` lookup is resolved
  immutably. If not, stop promotion rather than adding a local wrapper.
- [ ] Run `just dagger-list`, then `just dagger-native-parity` and
  `just dagger-poc` on the same exact HEAD. Compare findings, scope and
  failure readability; parity must be understood before performance matters.
- [ ] Run `just dagger-bench` for warm-cache comparison. Record cold-start
  behavior only from a naturally cold/fresh environment; never clear shared
  Docker/Dagger caches just to generate a benchmark.
- [ ] Decide whether measured cache reuse and failure readability remove enough
  CI glue to justify promotion. If not, keep Dagger experimental or remove it.
- [ ] **Pytest deferred:** do not invent root project metadata solely for
  Dagger. Add Pytest only after a clean root Python project marker and native
  Python project metadata are intentionally normalized, or a durable module
  measurably reduces orchestration code.
- [x] Native Ruff configuration is standalone; keep Ruff outside Dagger unless
  an official module or broader reusable module removes measurable code.
- [ ] Keep GitHub Actions unchanged during the PoC. Only after reproducibility,
  parity and performance acceptance may a later PR make Actions a thin
  `dagger check` trigger.
- [ ] Promote Dagger out of the experimental skill section only after those
  runtime criteria pass.

References: <https://docs.dagger.io/reference/config-files/dagger-toml/>,
<https://docs.dagger.io/cli/checking/>,
<https://docs.dagger.io/reference/modules/shellcheck/> and
<https://docs.dagger.io/reference/modules/js/biome/>.

### Context7 — current documentation for coding agents

Context7 is documentation-only: it improves version/API accuracy for external
libraries but never replaces repository/runtime evidence.

- [x] Register the hosted Context7 MCP endpoint without credentials/headers in
  `.mcp.json`, `.cursor/mcp.json` and OpenCode V2
  `opencode.json -> mcp.servers.context7`. OpenCode keeps
  `codemode=true` so the server stays grouped rather than expanding every MCP
  tool directly into the native tool list.
- [x] Add `context7-docs` as an on-demand skill with an anonymous CLI fallback
  (`ctx7 library` → versioned library ID → `ctx7 docs`) and telemetry disabled
  in the documented CLI path.
- [x] Route external/version-specific library questions through Context7 from
  `AGENTS.md` and `local-first-quality`, while keeping repository files,
  lockfiles and runtime diagnostics authoritative.
- [x] Add a Pre-commit contract that rejects a required
  `CONTEXT7_API_KEY` in the project MCP configuration and verifies the
  free-first/on-demand boundaries.
- [ ] Runtime-smoke the anonymous endpoint from the primary OpenCode client
  (`opencode mcp list` + one version-specific lookup). If the anonymous quota
  is insufficient, prefer OpenCode OAuth/free login before any paid tier.
- [ ] Keep `CONTEXT7_API_KEY` optional and outside Git; reserve it for
  non-interactive automation or higher free-plan limits only.
- [x] Route every `dagger.toml` change through both `local-first-quality`
  and `context7-docs`, so future Dagger edits automatically request current
  external API documentation. Runtime Context7 lookup remains acceptance-gated
  by the OpenCode smoke above.
- [x] Keep an official-doc/web fallback for environments where Context7 is not
  connected, lacks the required library/version or is rate-limited. The current
  API-only agent used that fallback to validate the Dagger/OpenCode contracts
  without pretending the Context7 runtime smoke had passed.

Reference: <https://context7.com/docs/overview> and
<https://context7.com/docs/clients/cli>.

### Code/debt reduction policy

- [ ] Continue replacing repeated policy with canonical metadata/schema or mature
  OSS libraries only when maintenance surface measurably shrinks.
- [ ] Continue centralizing bounded TrueNAS middleware/readiness helpers in
  `scripts/lib/` and generic Python behavior in `scripts/nabla_ops/`.
- [x] Compose discovery is shared through `nabla_ops.compose_paths`.
- [x] Dotenv parsing delegates to `python-dotenv`; secret manifest structure
  uses Draft 2020-12 JSON Schema + `jsonschema`/`check-jsonschema`.
- [ ] Evaluate Typer only for genuinely complex/repetitive operator CLIs; keep
  `argparse` for small appliance-safe scripts where a dependency adds no value.
- [ ] Move code-server startup-time packages/extensions into a derived immutable,
  versioned, digest-pinned image before removing current runtime provisioning.
- [x] Anti-duplication gates protect migrated runtime primitives.
- [x] `planned`/`disabled` services stay catalog-visible without generating
  false Gatus/AutoKuma runtime expectations.

### CrowdSec / pfSense cutover evidence — 2026-10-10 21:17 CEST

- [x] TrueNAS central runtime remains healthy: CrowdSec `v1.8.1`, LAPI
  `172.17.0.24:8084`, metrics `:6060`, problematic
  `firewallservices/pf-scan-multi_ports` absent.
- [x] Canonical pfSense Loki acquisition is live; operator observed
  `cs_lokisource_hits_total=8563`.
- [ ] Canonical runtime secret is still absent:
  `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`.
- [ ] CrowdSec secret rendering is currently blocked by the known Vaultwarden
  public split-DNS: TrueNAS resolves `vaultwarden.albandrieu.com` to
  `172.17.0.24` through the historical pfSense/Unbound Host Override and
  therefore receives local HTTPS `404` instead of traversing Cloudflare.
  Correct the Host Override first; do not bypass by copying secrets between
  hosts.
- [ ] Central bouncer `PFSENSE_FIREWALL` exists but `last_pull=<none>`;
  therefore the remote LAPI cutover has **not** happened.
- [x] Workstation-side pfSense proof: local Security Engine absent, firewall
  bouncer running, PF tables exist with 31,513 IPv4 + 586 IPv6 entries.
- [x] Workstation preflight is now accepted: pfSense reaches central LAPI TCP
  `172.17.0.24:8084`, local Security Engine is absent, firewall bouncer is
  running, and PF tables contain 32,099 entries.
- [ ] pfSense bouncer still points to legacy local LAPI
  `http://172.17.0.1:8089`; strict `--accept` correctly fails until the
  bouncer is reconfigured to `http://172.17.0.24:8084`.
- [ ] Operator TrueNAS checkout used for this evidence was
  `ffdf66e43ad8`, dirty and behind 25 commits. Runtime observations remain
  useful, but code-level acceptance must be repeated after synchronizing PR
  #253 without discarding local work.
- [ ] Next transaction: render the existing CrowdSec bouncer key directly from
  Vaultwarden into the canonical TrueNAS runtime file; run workstation
  `verify-crowdsec-pfsense.sh --preflight`; only then change pfSense CrowdSec
  package settings through the workstation/operator path and require both
  TrueNAS `--accept` + workstation `--accept`.
- [x] Trust boundary stays explicit: TrueNAS never SSHes/API-calls pfSense and
  no runtime secret is copied from TrueNAS to the workstation.

## P1 — dependency automation and infrastructure secrets

### Renovate / Mend

- [ ] Install hosted Mend Renovate for `nabla-compose` and `fastapi-sample`.
- [ ] Grant read access to Dependabot alerts and prove one real vulnerability
  remediation path.
- [ ] Disable Dependabot Security Updates only after Renovate is proven as the
  single security-fix PR producer; keep Dependabot Alerts enabled.
- [ ] Remove the self-hosted Renovate Actions workflow after hosted acceptance.
- [ ] Keep routine concurrency bounded and no automerge without authoritative
  green required checks.

### Infrastructure secrets

- [ ] OpenTofu/Terragrunt + Garage backend credentials.
- [ ] Dedicated TrueNAS infrastructure automation identity; never reuse the
  FastAPI observer.
- [ ] Nexus automation credentials.
- [ ] Talos/Kubernetes/CSI machine credentials.
- [ ] Keep root-owned `0600` runtime materializations and encrypted recovery.
- [ ] Move long-lived machine secrets to Vault/OpenBao only after persistence,
  rollback and recovery are proven.

## P2 — service catalog and security platform

Catalog-v2 detail remains in
[`service-catalog-v2-normalization.md`](./service-catalog-v2-normalization.md).

- [ ] preparation/parity: deterministic identities, schemas and no duplicate
  ownership;
- [ ] pilot representative services and provider-outage behavior;
- [ ] bulk service descriptor/BIA/PRA migration, coupled with touched secret
  migrations;
- [ ] prepare FastAPI/site/operational consumers;
- [ ] coordinated v1 → Backstage cutover;
- [ ] remove legacy compatibility only after runtime/reboot/consumer acceptance.

Security-tooling acceptance:

- [ ] accept Plumber, NetBox, OCS Inventory, Dependency-Track, DefectDojo and
  Neo4j before treating declarations as deployed;
- [ ] add Dependency-Check as reproducible SCA evidence feeding DefectDojo;
- [ ] evaluate ArcherySec/Faraday only as bounded complements, not competing
  systems of record;
- [ ] keep Cartography/OpenSSF Scorecard as explicit/manual jobs where intended;
- [ ] OpenCRE: create/verify storage, pin immutable image, prove health,
  useful correlation and reboot persistence;
- [ ] DSOMM: after runtime deployment, publish/merge repository-assessment
  producers for `nabla-compose`, `fastapi-sample`, `nabla-site-alban` and
  `nabla-site-bababou`, then require complete-source aggregation before using
  it as portfolio review evidence;
- [ ] complete manual DSOMM Security Champions/IAM/Agentic AI/Identity/process
  review and close/accept GitHub branch-protection gaps;
- [ ] keep source-first security audit validation local and close the Scanopy
  daemon-bootstrap lead with passive runtime evidence.

## P3 — runtime and observability

### Grafana native → Compose migration

Do this before enabling/reconciling Mimir / Loki / Tempo / Alloy.

- [ ] run `sudo bash scripts/truenas/diagnose-grafana-migration.sh --check`;
- [ ] inventory `grafana.db` read-only and snapshot the actual backing ZFS
  dataset;
- [ ] preserve `/mnt/cpool/grafana/data` and plugin state;
- [ ] remove only the native App wrapper, never its preserved data;
- [ ] start repository Grafana on `:30037`, verify `/api/health` and compare
  representative dashboard/datasource identities;
- [ ] keep rollback snapshot/material until acceptance;
- [ ] only then reconcile Mimir / Loki / Tempo / Alloy.

### Remaining observability/runtime

- [ ] Prometheus DOWN-target reconciliation: canonical database telemetry is
  **PostgreSQL, Redis, ClickHouse, InfluxDB and OpenSearch**; **Sybase is
  excluded**.
- [ ] finish FastAPI Sentry transaction/span persistence acceptance.
- [ ] correlate FastAPI Sentry + Prometheus/Grafana + Loki/Tempo + Pyroscope with
  stable service/environment/release/route/trace/span identities.
- [ ] prove Suricata `eve.json` downstream consumption.
- [ ] restore pfSense NetFlow → Cloudflare Network Analytics.
- [ ] restore repository-owned Uptime Kuma, then enable/reconcile AutoKuma.
- [ ] finish Scrutiny SMART + workstation collector acceptance.
- [ ] deploy/accept Joplin and its dedicated shared-PostgreSQL role/database.
- [ ] make Homarr first-run initialization idempotent/secret-backed.
- [ ] keep native PostgreSQL and AdGuard Home until explicit migration
  backup/rollback/consumer plans exist.
- [ ] defer NPM/OpenArchiver/Paperless migration until inventory/rollback
  contracts are ready.
- [ ] Akvorado ingestion/query acceptance and later ntopng reconciliation.
- [ ] Pi-hole post-reboot DNS/UI/API/sync/exporter acceptance.
- [ ] Docling API/health + one bounded conversion, then OpenRAG ↔ workstation
  LiteLLM/GPU ingest/retrieve acceptance.
- [ ] Cyberbro free-engine baseline, then provider onboarding in bounded
  least-privilege batches; resolve Vaultwarden token-refresh/icon TLS debt.

### Local-first follow-up after merged PR #250 (2026-10-10)

- [x] Trigger topology and Homarr/Gatus/AutoKuma generator checks for
  nested `apps/*/compose.yml` edits, not only files directly under `apps/`.
- [x] Fail closed when local quality-gate Git path collection errors;
  never interpret a broken `git diff` as zero changed files.
- [ ] Regenerate and validate any stale Pipelines catalog, topology,
  Gatus, Homarr or AutoKuma projections from the merged source change
  using the canonical generators; preserve deterministic diffs.
- [ ] Run exact-HEAD L3 after obtaining a full verified checkout/cache.
  Offline L1 and source-level assertions remain limited evidence; do not
  rerun GitHub Actions merely to discover the next error.

## P3.1 — AI stack upgrades and service consolidation (planning only)

Execution plan: [AI stack upgrade and consolidation](./ai-stack-upgrade-consolidation-plan.md).
**No runtime upgrade, redeploy, migration, deletion or secret rotation is
authorized by this entry.** Declared Compose versions are not runtime proof.

- [x] Inventory the declared OpenRAG, Open WebUI, Langflow, Docling,
  LiteLLM, Langfuse, OpenSearch and storage dependencies; record available
  upstream releases and identify candidate integration/duplication areas.
- [x] Define bounded upgrade waves, stop conditions, compatibility
  evidence, rollback/restore gates and conditional service additions.
- [ ] Capture TrueNAS exact image digests, Docker networks, bucket/index
  owners, and recent backups in a **read-only** runtime audit.
- [x] Remove unused Open WebUI Pipelines service from Compose and its
  Backstage component (operator confirmed). Runtime retirement and generated
  catalog/Gatus/Homarr/AutoKuma reconciliation still require acceptance.
- [x] Prepare the existing `hello.int.albandrieu.com` Traefik router:
  explicitly pin Docker network `traefik_network` and backend port `80`,
  and add regression contract (source-only; **not runtime cutover**).
- [ ] Run the read-only hello ingress preflight and accept actual TrueNAS
  routing, pfSense HAProxy, DNS/TLS, headers and expected response before
  retiring the NPM test; see [hello cutover](./hello-traefik-migration.md).
- [ ] Canary `hello.int.albandrieu.com` with CrowdSec LAPI bouncer,
  real-client-IP trust and optional staged AppSec WAF;
  avoid migrating pfSense HAProxy or Cloudflare routes implicitly.
- [ ] Confirm NPMplus has **no active proxy hosts or callers**, then
  disable the TrueNAS app and only subsequently delete app + data if
  unused. NPM is a test too: migrate any other configured routes
  explicitly and remove NPM only after consumer-free evidence.
- [ ] Confirm AIStor has no buckets, consumers or data, stop the app,
  observe Langfuse/MinIO health, then delete AIStor after backup review.
- [ ] Add Trivy Operator as a scoped Talos/Kubernetes **planned service**,
  then export its reports using DefectDojo's `Trivy Operator Scan`
  parser and its reimport-scan API, avoiding duplicate findings.
- [ ] Compare Databasus (PostgreSQL PITR, MongoDB/MySQL backups) against
  Restic (general files/ZFS exports): choose complementary roles or one
  minimal stack, then pilot offsite encrypted backup and restore.
- [ ] Reconcile NPM/NPMplus trial ingress ownership after the canary;
  do not delete their data before reviewing host/cert/port consumers.
- [ ] Evaluate reuse of Docling by Open WebUI and Langfuse/Alloy tracing,
  then retire Pipelines only after equivalent Function/MCP coverage.
- [ ] Qualify Open WebUI 0.11.4 independently before upgrading the
  coordinated OpenRAG 0.8.0 / Langflow / OpenSearch bundle.
- [ ] Preserve isolated security data, S3 buckets, RAG indices, DNS
  authority and ingress ownership until an explicit migration is accepted.
- [ ] Add a new service only after documenting a missing capability and
  verifying reuse of the existing stack is insufficient.

## P3 — Deferred shared data-network and Redis credential hardening (planning only)

**Deferred; no runtime network change, credential rotation or restart is authorized by this item.**

- [ ] Design a persistent, least-privilege Docker network for shared data services (PostgreSQL/Redis), rather than depending on PostgreSQL's current host-wide `0.0.0.0:5432` publication. Inventory every consumer, network, TrueNAS app lifecycle and firewall rule; plan a canary, rollback and cold-reboot acceptance before changing connectivity. Keep DefectDojo's initial rollout independent of this migration.
- [ ] Audit the effective Redis password **without printing it** and inventory all clients and Redis DB/ACL ownership. The Redis Compose currently uses `${REDIS_AUTH:-myredissecret}` in command interpolation but does not export `REDIS_AUTH` into the container; an in-container `$REDIS_AUTH` lookup is therefore not authoritative. Preserve the current credential; do not rotate it during DefectDojo onboarding.
- [ ] Register the existing Redis credential in Vaultwarden and materialize a root-only canonical runtime secret at `/mnt/cpool/secrets/runtime/redis/.env.secrets`; migrate the Redis deployment and exporter to consume it without leaking the password through Compose rendering, command-line arguments, environment inspection or logs. Remove the insecure fallback only after all consumers are accepted.
- [ ] Repair Redis readiness checks to authenticate safely (and check actual `PONG`, not merely process health), then verify the PostgreSQL shared service's startup/reboot readiness checks and dependent-service ordering. Include a cold-reboot acceptance runbook, not only Docker's `restart: unless-stopped` behavior.

## P4 — Kubernetes and multi-cluster

- [ ] Vault/OpenBao after single-cluster storage/recovery acceptance.
- [ ] Falco after infrastructure baseline stabilizes.
- [ ] Kubara + Traefik ingress with explicit bare-metal exposure.
- [ ] FastAPI Kubernetes immutable-image smoke through
  `test.int.albandrieu.com`.

Karmada remains outside the bootstrap critical path:

- [ ] define cluster identity/labels, GPU/power/cost/workload classes;
- [ ] build an always-on small Karmada management cluster/VM on TrueNAS;
- [ ] register `nabla-talos` first and prove one bounded stateless propagation;
- [ ] build/register intermittent `workstation-gpu`, with offline state treated
  as expected capacity loss rather than home-platform failure;
- [ ] select cloud GPU capacity only after SKU/network/storage/startup/
  scale-to-zero/cost comparison;
- [ ] keep mandatory state/quorum off intermittent nodes and do not assume
  transparent cross-cluster networking or TrueNAS NFS reachability;
- [ ] final smoke: home stateless workload, workstation GPU workload when online,
  workstation shutdown without mandatory-service degradation, then cloud GPU.

## P5 — identity, policy and bounded cleanup

- [ ] Keycloak/GitHub SSO after network/storage stability.
- [ ] Vault/OpenBao human authentication after infrastructure secrets.
- [ ] Continue NIST CSF 2.0 mapping and Restricted Pod Security migration with
  explicit infrastructure exceptions.
- [ ] archive accepted reboot evidence and retain current + previous known-good
  bundles.
- [ ] remove only owner-reviewed zero-endpoint Docker networks; never blanket
  `docker network prune` / `docker system prune`.
- [ ] keep weekly bounded dangling-image cleanup separate from Git sync; accept
  the documented TrueNAS cron and record the next cold-start convergence.
- [ ] review old unmanaged/exited containers/build cache only after the bounded
  cleanup policy is established.

## Ordering rule

```text
MERGED PR #240, runtime still pending
  -> DSOMM / Sentry / Scrutiny / Code checks + one-service acceptance
  -> Scanopy / Joplin / AutoKuma / Sample runtime-env closure
  -> local-first agent improvements (Dagger PoC + Context7 PoC)
  -> hosted Renovate acceptance
  -> service intent / catalog-v2 preparation and security-tool runtime acceptance
  -> Vaultwarden waves for active services only
  -> Grafana native -> Compose
  -> Prometheus canonical target reconciliation
  -> Mimir / Loki / Tempo / Alloy
  -> FastAPI cross-signal observability
  -> Suricata downstream + pfSense NetFlow
  -> Uptime Kuma / AutoKuma
  -> Docling / OpenRAG-LiteLLM
  -> Kubernetes ingress + smoke
  -> Karmada/workstation/cloud GPU federation
  -> infrastructure secrets / Vault / Falco
  -> bounded cleanup + remaining deferred services
```

When restarting a ChatGPT/agent discussion, begin from **Restart context** and
the first unchecked item in **Immediate TrueNAS acceptance queue**. Do not
reconstruct completed history from chat memory when the repository runbook or
current runtime evidence can answer it.

### pfSense runtime evidence — 2026-10-17 23:47 CEST

Operator ran `scripts/pfsense/diagnose-memory-pflow.sh --check` and `scripts/pfsense/audit-posture.sh` on workstation. pfSense uptime 13d, Unbound 1.26.1 PID 18989 uptime 816s RSS 123744 KiB, memory available 233580 KiB (free 219640 + inactive 13940), swap used 0, DNS public and private DefectDojo/S3 PASS. Kernel last OOM timestamp remains 2026-10-17 02:11:32+02:00 (historical, not a new OOM). Snort RSS 60896 KiB, pfBlocker helper 51268 KiB. pfBlocker Python loader 11809988 bytes, last DNSBL PASSED 225631 at 00:04:29; RAM swap gate missing WARN, loaded entries 0 WARN with legacy-counter semantics. pflow TrueNAS domain 1 to 172.17.0.24:2055 FAIL, Cloudflare domain 2 to 162.159.65.1:2055 FAIL, connected exporters 0 WARN. Zabbix agent stopped WARN. No services restarted.

Next: confirm desired pflow destinations and whether UDP/2055 collectors exist before any pflow configuration change. Collect a second memory baseline after 24h and compare OOM timestamps. Investigate pfBlockerNG guard without package patching or DNSBL rebuild. Read-only pflow inspection reported no interfaces, but this alone cannot establish whether collector or exporter configuration is the root cause.

### pfSense pflow investigation — 2026-10-17 23:53 CEST

Operator evidence: pfSense Plus 26.07 FreeBSD 16.0-CURRENT arm64, `/boot/kernel/pflow.ko` present (62984 bytes) but `kldstat` shows no pflow module and `ifconfig -l` shows no pflow interface. `pflowctl -v -l` fails `pflow.ko is not loaded`. TrueNAS Akvorado 2026.8.0 inlet publishes UDP 172.17.0.24:2055; inlet logs over last 15 minutes were empty. These establish missing pfSense exporter, not Akvorado ingestion health or the reason for missing module.

- [ ] Inspect read-only pfSense pflow configuration and boot persistence, confirm native pflow support on installed pfSense Plus build and available rollback before any `kldload`.
- [ ] Validate Akvorado inlet container health, receiver settings and counters without generating artificial traffic.
- [ ] Review pflow TrueNAS destination first; keep Cloudflare domain 2 export disabled until recipient and data privacy requirements confirmed.
- [ ] After explicit approval, activate in a controlled window with baseline memory/DNS and rollback checks. Do not start softflowd or restart Unbound.


### 2026-10-20 — Simplification des consommateurs du catalogue (PR #265)

- [x] Backstage `catalog-info.yaml` pour l'identité et `com.albandrieu.nabla.entity-ref` pour relier Compose.
- [x] Gatus YAML natif **unique** (`config/monitoring/gatus-endpoints.yml`) ; 85 sondes projetées vers Gatus et AutoKuma, sans second inventaire de cibles.
- [x] Homarr construit depuis Backstage + routage Compose ; suppression de `catalog/service-consumers.static.yml` au profit des paramètres réseau du Compose Homarr ; 80 entrées v2 matérialisées, contre 143 entrées historiques **non comparables sans migration des descripteurs**.
- [x] Projections standard Backstage/CycloneDX générées, validation `--check` intégrée au quality gate.
- [ ] Étendre Backstage aux identités/relations restantes et aux environnements sans deviner de valeur métier.
- [ ] Migrer les lecteurs FastAPI Sample, nabla-site-alban et les scripts TrueNAS, puis retirer définitivement les fichiers/catalogues v1.
- [ ] Recette des secrets runtime via Vaultwarden sur TrueNAS, non exécutée depuis GitHub.
