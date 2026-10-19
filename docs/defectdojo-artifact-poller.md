# DefectDojo — collecteur GitHub Actions sur TrueNAS, sans runner

## 19 octobre 2026 — collecteur unique et formats SARIF

Le collecteur **unique** `scripts/security/poll-defectdojo-gh-artifacts.py`
dans `nabla-compose` référence aujourd'hui `alban`, `bababou`
et `fastapi-sample` via son registre `SOURCES`. La commande Cron
TrueNAS existante ne change pas et reste limitée à `alban` par défaut.
FastAPI exige une activation explicite `DEFECTDOJO_FASTAPI_PULL_APPROVED=YES`
avec `--source fastapi-sample --pull`. L'import automatique
`--pull-and-import` pour FastAPI reste interdit avant les tests RBAC.

**Le collecteur ne nécessite pas de nouveau conteneur Compose** :
une Cron native TrueNAS déclarée/contrôlée depuis `nabla-compose`
suffit à exécuter ce code dans le LAN sans ouvrir DefectDojo sur Internet.

`fastapi-sample/scripts/security/export_defectdojo_collector_trivy.py`
n'est pas un collecteur mais un exporteur **côté producteur**. Il
prépare une projection Trivy `uv.lock` HIGH/CRITICAL sans captures
de requêtes, secrets ni inventaire complet. Le workflow GitHub qui
publierait cet artefact doit encore être conçu et vérifié ; aucune
publication, collecte ou ingestion réelle n'est prouvée.

**Double format possible** sans second scan : `fastapi-sample` peut
produire `trivy.json` + `trivy.sarif` via l'option `--sarif`.
Le JSON natif est préféré pour le parseur DefectDojo `Trivy Scan`.
CodeQL produit du SARIF et se charge avec `CodeQL Scan` ;
le parseur générique `SARIF` reste **non autorisé par défaut**
dans les `producers[].allow`, bien que le veto global SARIF soit retiré.
Ne pas importer les deux représentations du même finding dans deux
Tests différents sans stratégie de déduplication. SARIF brut, SBOM,
evidence de secrets et DAST détaillé restent exclusivement privés.

Tests hors réseau ajoutés ; activation Cron, jetons GitHub App, import
Celery et contrôle WAN restent non attestés.

---


**Préparation uniquement, aucune activation de cron ni upload appliqué.**
Source de vérité : `config/security/defectdojo-allowed-imports.json`.
Aucun compte GitHub self-hosted runner n'est nécessaire : TrueNAS interroge
sortant l'API REST de GitHub Actions puis utilise l'API LAN de DefectDojo.
DefectDojo OSS n'aspire pas seul les artefacts GitHub Actions.

## Chaîne et modèle de confiance

```text
GitHub Actions nabla-site-alban / master / workflow success
       | token GH Actions:read, dépôt unique
       v
TrueNAS cron -> poll-defectdojo-gh-artifacts.py (stdlib only, root host)
       | selected run ID / SHA / workflow / event / artifact exact
       v
pull-site-alban-security-report.py
       | API GitHub HTTPS -> signed ZIP HTTPS (Authorization NOT forwarded)
       | 10 MB archive / 8 MB extracted / no arbitrary filename
       | HIGH/CRITICAL Trivy+Nuclei or HIGH ZAP
       v
/mnt/cpool/defectdojo/imports/site-alban (root 0700 / files 0600)
       | optional explicit --pull-and-import gate + dedicated engagement ID
       v
import-scan-defectdojo.sh -> http://172.17.0.24:31085/api/v2/reimport-scan/
       | root-only scoped import token; no public Cloudflare tunnel
       v
DefectDojo Product/Engagement 'nabla-site-alban' (asynchronous acceptance)
```

GitHub: https://docs.github.com/en/rest/actions/artifacts .
App authentication: [dedicated policy](github-app-defectdojo.md).
TrueNAS cron: https://api.truenas.com/v25.10/api_methods_cronjob.create.html .
DefectDojo API: https://docs.defectdojo.com/automation/api/api-v2-docs/ .

## Secrets bootstrap UI

Existing canonical item: `nabla/prod/defectdojo` in the TrueNAS
Vaultwarden folder. On **first initialization**, the initial UI identity is
`nabla` and the password is CSPRNG-generated (`secrets.token_urlsafe(48)`).
`scripts/secrets/bootstrap_defectdojo_admin.py --check` is offline.
`--apply` runs as an unlocked Vaultwarden **non-root** operator. It creates
an absent item or fills missing login credentials without overwriting
database/Redis fields, refuses duplicates and never rotates an existing
password. It does **not** inspect or reset an already-initialized database.
No password is printed or committed.

After all canonical DB/Redis and encryption keys exist in the same
Vaultwarden item, materialize via
`scripts/truenas/prepare-security-tooling-secrets.sh --apply defectdojo`.
The existing Compose already reads **both**
`/mnt/cpool/secrets/runtime/defectdojo/.env` and
`/mnt/cpool/secrets/runtime/defectdojo/.env.secrets`.
Materialization is `root:root 0600`. The initializer only consumes these
settings when run; Vaultwarden provisioning alone is not a deployed account.

## Polling: no runner, no gh CLI

- Register the one shared **GitHub App** described in
  [github-app-defectdojo.md](github-app-defectdojo.md) and install it on the explicitly selected Nabla repositories
  (`nabla-compose`, `fastapi-sample`, `nabla-site-alban`,
  `nabla-site-bababou`). Each token is still scoped to one repository. Materialize its private key separately
  from DefectDojo's Compose env. The collector mints a ≤1h Actions:read
  installation token per job; **no persistent PAT**.
- Keep a separate DefectDojo **import-only** identity and token at
  `/mnt/cpool/secrets/runtime/defectdojo/import-token` (also 0600).
  Configure an existing isolated Product and Engagement; never allow
  the poller to auto-create Product or Engagement.
- Metadata and downloads are restricted to exactly three named successful
  workflows on `master`; never PR/fork/failed/pending runs or expired ZIPs.
  GitHub API token is sent to **api.github.com only**. Subsequent signed ZIP
  retrieval has **no token header** and an HTTPS host allowlist.
- Scheduled polling is IO-bound and inexpensive. Native TrueNAS
  cron (not GitHub CI): **06:50 daily** appliance local time,
  command `/usr/bin/python3 /mnt/cpool/compose/nabla-compose/scripts/security/poll-defectdojo-gh-artifacts.py --pull`,
  user `root`, stdout/stderr suppressed or sent to secured local logs.
  The repo-owned `scripts/truenas/reconcile-defectdojo-artifact-cron.py`
  validates the exact native cron definition and creates the task as
  **disabled** via `midclt call cronjob.create` on TrueNAS. Its
  `--enable` mode requires `DEFECTDOJO_GH_POLL_APPROVED=YES`, validates the
  root-owned GitHub App key and installation metadata, and refuses drift.
  `--disable` is an explicit rollback. No Linux root crontab mutation.
  Initial activation remains gated by the scoped GitHub credential, ACL and
  isolated Product.
- `--check` requires no credentials, network, or scheduler and leaves
  both products untouched. `--pull` downloads filtered artifacts only.
  `--pull-and-import` additionally requires
  `DEFECTDOJO_IMPORT_APPROVED=YES` and a validated
  `DEFECTDOJO_SITE_ALBAN_ENGAGEMENT_ID`, plus the import-only token. It
  never implicitly enables recurring writes. An already staged report is
  not reuploaded: verify/import it separately if needed.
- The API consumer cannot select other repos or workflows via environment
  variables. Bababou only permits existing `Production DAST` ZAP HIGH
  without request or response evidence. Poll only the latest 100 GitHub Actions runs, no extra scans,
  and report NOT_OBSERVED instead of treating missing evidence as zero findings.

## Privacy and limits

Do not route DefectDojo publicly or let it enumerate GH organizations.
BetterLeaks/GitGuardian raw findings, secret values, unrestricted SARIF,
license reports, SBOM and PII are excluded. Full ZAP/Nuclei artifacts
created by another project may contain credentials or sensitive request
captures: **do not publish them unencrypted in a public repo**.
Sanitize or encrypt at the producer before publication; until verified,
keep automated import disabled and review the filtered file.

Do not duplicate Site Alban scans: its ZAP baseline and weekly bounded
Nuclei run remain authoritative. No new GitHub Actions scan cadence.
The final DefectDojo HTTP 200/201/202 only acknowledges delivery: validate
asynchronous parser processing, deduplication and Product RBAC separately.

### Offline quality contract

```bash
python3 -m unittest tests.test_defectdojo_admin_bootstrap tests.test_defectdojo_artifact_collector tests.test_defectdojo_artifact_cron tests.test_github_app_auth -v
python3 scripts/security/poll-defectdojo-gh-artifacts.py --check
python3 scripts/secrets/bootstrap_defectdojo_admin.py --check
python3 scripts/truenas/reconcile-defectdojo-artifact-cron.py --check
```

## Contrat réel des artefacts Site Alban — réconciliation du 19 octobre 2026

Le collecteur est **préparé mais non activé** : aucune installation de la
GitHub App, aucun Cron ni import réel n'est prouvé par ces commits.

| Source (workflow `master`) | ZIP et fichier GitHub | Fichier dans l'inbox TrueNAS | Import |
| --- | --- | --- | --- |
| `Supply Chain Security (Trivy)` | `trivy-master-<sha>` / `trivy-security.json` | `site-alban-<run>-trivy.json` : uniquement CVE npm lockfile High/Critical | `Trivy Scan`, JSON |
| `Nuclei public DAST (Site Alban)` | `nuclei-public-<run>` / `nuclei-results/nuclei.jsonl` ; projection réduite à la source dans Site #236 | `site-alban-<run>-nuclei.json` : JSONL minimal, URL limitée à l'origine HTTPS | `Nuclei Scan`, JSONL |
| `Production DAST` | `zap-production-report` / `report_json.json` | `site-alban-<run>-zap.xml` : conversion locale privée **JSON → XML** avec seuls plugin ID, titre, sévérité 3 et origine HTTPS | `ZAP Scan`, XML |

**Point de compatibilité important** : le parser OSS `ZAP Scan`
accepte le rapport **XML** de ZAP, pas le JSON de `action-baseline`.
Le collecteur transforme ce JSON dans l'inbox privée et l'importeur envoie
`application/xml`. Ne pas changer `scan_type` pour masquer une erreur
de format. Sans test effectif de la version DefectDojo installée, ce
contrat n'est **pas** une preuve d'ingestion réussie.

Le poll recherche chaque workflow par **fichier identifié** et branche
`master` avec dix dernières exécutions sans filtre `status=success`.
La dernière exécution échouée, annulée ou incomplète ne doit **jamais**
laisser importer un succès plus ancien. Un run absent vaut `NOT_OBSERVED`,
pas `PASS`.

Les rapports minimisés excluent requêtes/réponses HTTP, cookies, tokens,
paramètres d'URL, détails de topologie, licences et SBOM. Trivy ne fournit
dans ce parcours que des vulnérabilités de `package-lock.json`. Aucun
rapport vide ou sans finding admissible ne doit être importé.

**Gate de confidentialité ZAP non levée** : l'action GitHub ZAP de Site
Alban téléverse actuellement son propre rapport brut. La conversion
dans TrueNAS ne rend **pas rétroactivement privé** cet artefact GitHub ;
celui-ci peut inclure des requêtes/authentifications de scan. Avant de
rendre ZAP automatique, remplacer ce dépôt brut par une sortie
pré-expurgée ou lancer ce scan dans l'environnement privé. Vérifier la
version du parser OSS sur l'instance et l'absence d'en-tête de bypass.
Ce point reste ouvert, sans changer la fréquence des scans.

## Site Bababou integration (2026-10-19)

`poll-defectdojo-gh-artifacts.py --source bababou --check` displays
the approved read-only workflow without fetching anything.
The default `--source all --pull` stages Site Alban reports and
Bababou's existing master `Production DAST` ZAP report.
Site Bababou has a separate inbox `.../imports/site-bababou` and requires
`DEFECTDOJO_SITE_BABABOU_ENGAGEMENT_ID` for explicit import.
No speculative Nuclei source or new DAST workflow is added.
See [shared App GitOps architecture](github-app-defectdojo.md).

## Quatrième producteur : nabla-compose

Le workflow `defectdojo-compose-handoff.yml` est séparé du gate CRITICAL
sur PR : il génère **une seule fois par semaine sur master** un Trivy fs JSON
puis applique `export-defectdojo-compose-trivy.py`, qui ne conserve que les
vulnérabilités HIGH/CRITICAL liées aux fichiers de verrouillage. L'artefact
`defectdojo-compose-trivy-<sha>` ne contient que le rapport JSON réduit
et son manifeste de provenance SHA-256. Les rapports bruts, licences, SBOM,
preuves HTTP et findings Secrets sont exclus. Le collecteur vérifie
le dernier run, l'identité du workflow, les deux membres ZIP, le SHA
et les champs autorisés avant stockage en zone privée.

`--source all --check` doit afficher les **quatre** dépôts : alban,
bababou, fastapi-sample, compose. Le Cron utilise le loader
`run-nabla-github-app-cron.py` avec `.env.secrets` root-only et les
jetons temporaires de l'App. Une source dont le workflow n'existe pas
encore sur `master` est **NOT_OBSERVED**, jamais « zéro finding ».
L'acceptation DefectDojo et le déploiement TrueNAS restent séparés.
