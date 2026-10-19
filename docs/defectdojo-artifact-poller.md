# DefectDojo — collecteur GitHub Actions sur TrueNAS, sans runner

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

Github: https://docs.github.com/en/rest/actions/artifacts .
TrueNAS cron: https://api.truenas.com/v25.10/api_methods_cronjob.create.html .
DefectDojo API: https://docs.defectdojo.com/automation/api/api-v2-docs/ .

## Secrets bootstrap UI

Existing canonical item: `nabla/prod/defectdojo` in the TrueNAS
Vaultwarden folder. On **first initialization**, the admin identity is
`admin` and the password is CSPRNG-generated (`secrets.token_urlsafe(48)`).
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

- Store a fine-grained GitHub token with **Actions:read** on only
  `AlbanAndrieu/nabla-site-alban`, without `contents:write` or any Dojo
  permission. Vaultwarden is the durable source; materialize to
  `/mnt/cpool/secrets/runtime/defectdojo/github-read-token`,
  `root:root 0600`, outside Git.
- Keep a separate DefectDojo **import-only** identity and token at
  `/mnt/cpool/secrets/runtime/defectdojo/import-token` (also 0600).
  Configure an existing isolated Product and Engagement; never allow
  the poller to auto-create Product or Engagement.
- Metadata and downloads are restricted to exactly three named successful
  workflows on `master`; never PR/fork/failed/pending runs or expired ZIPs.
  GitHub API token is sent to **api.github.com only**. Subsequent signed ZIP
  retrieval has **no token header** and an HTTPS host allowlist.
- Scheduled polling is IO-bound and inexpensive. Suggested TrueNAS native
  cron (not GitHub CI): **06:20 and 18:20** appliance local time,
  command `/usr/bin/python3 /mnt/cpool/compose/nabla-compose/scripts/security/poll-defectdojo-gh-artifacts.py --pull`,
  user `root`, stdout/stderr suppressed or sent to secured local logs.
  Configure it as **disabled initially**, and enable only once the scoped
  GitHub credential, ACL and isolated Product are confirmed.
- `--check` requires no credentials, network, or scheduler and leaves
  both products untouched. `--pull` downloads filtered artifacts only.
  `--pull-and-import` additionally requires
  `DEFECTDOJO_IMPORT_APPROVED=YES` and a validated
  `DEFECTDOJO_SITE_ALBAN_ENGAGEMENT_ID`, plus the import-only token. It
  never implicitly enables recurring writes. An already staged report is
  not reuploaded: verify/import it separately if needed.
- The API consumer cannot select other repos or workflows via environment
  variables. Poll only the latest 100 GitHub Actions runs, no extra scans,
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
python3 -m unittest tests.test_defectdojo_admin_bootstrap tests.test_defectdojo_artifact_collector -v
python3 scripts/security/poll-defectdojo-gh-artifacts.py --check
python3 scripts/secrets/bootstrap_defectdojo_admin.py --check
```
