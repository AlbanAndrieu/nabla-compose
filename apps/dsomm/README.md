# OWASP DSOMM

Repository-owned deployment of the OWASP DevSecOps Maturity Model UI plus a
manual, pinned `tweag/dsomm-baseline` evidence runner.

## Assessment-context model

DSOMM `teams` represent **maturity assessment boundaries**, not repositories,
containers or individual services.

The default model intentionally uses only two contexts:

- **Nabla Platform** — `nabla-compose`, TrueNAS/Talos/Kubernetes, network,
  observability and shared security/platform services;
- **Nabla Applications** — FastAPI Sample and the Nabla web applications while
  they share the same delivery/security process.

The baseline still scans repositories individually so evidence remains
traceable. `config/repository-contexts.yaml` only routes that evidence to the
assessment context.

Create another context only when ownership, SDLC/security controls, risk model,
release/operations lifecycle or review evidence is materially different enough
to justify an independent maturity score. Do **not** create one context per
PostgreSQL/Grafana/Scanopy/DSOMM service or per repository by default.

## Reviewed assessment seed

The repository now carries a conservative DSOMM **5.0.2** seed:

```text
config/seed-activities.yaml
config/team-progress.seed.yaml
config/team-evidence.seed.yaml
```

The seed was derived on 2026-10-04 from:

- current `nabla-compose` catalog/topology and operator documentation;
- GitHub repository/workflow evidence for `nabla-compose`, `fastapi-sample`,
  `nabla-site-alban` and `nabla-site-bababou`;
- the TrueNAS BIA/PRA evidence in the catalog and
  `docs/homelab-reboot-runbook.md`;
- reviewed Notion control documentation, notably **Nabla — Système
  opérationnel DevSecOps sur 90 jours**, **Annexe F — Continuité d’activité,
  PRA/DRP et tests de résilience**, **Annexe D — OWASP SAMM** and the
  **Cybersecurity Checklist**.

Only evidence that can be traced to a repository, GitHub configuration or
reviewed control document is seeded. The two contexts remain governance
boundaries, not inventory entries.

The initial seed is deliberately conservative:

- `Version control` is the only seeded activity at `Fully implemented` for
  both contexts;
- most repository/runtime controls are `Started` or `Partly implemented`;
- the TrueNAS PRA/BCDR evidence is only `Partly implemented`: recovery
  succeeded after a manual power-cycle, the one-hour RTO was breached and the
  one-hour RPO was not exercised;
- GitHub reports `master` as **unprotected** and returns no repository
  rulesets, so Require-PR / required-status-check / force-push controls are not
  marked implemented;
- Security Champions/training, DSOMM 5 Agentic AI/Identity activities and
  organization/process controls requiring interviews remain human-review scope.

`scripts/dsomm/validate-seed.py` validates this subset offline against the
reviewed UUID/name set. It checks contexts, progression ordering, evidence UUIDs
and evidence/progress consistency without downloading the full upstream model.

On the first `deploy-dsomm.sh --apply`, the seed is copied into the protected
runtime state with mode `0600`. Existing runtime progress/evidence files are
**never overwritten** by later deploys.

## Repository assessment aggregation

Portable producer contract: `config/repository-assessment.schema.json`.
The consumer test suite locks its enums/constants to the manual fail-closed
validator so producer and portfolio semantics cannot silently diverge.

`nabla-compose` can ingest repository-owned
`nabla.dsomm.repository-assessment/v1` documents without turning missing data
into a negative score. The context mapping remains
`config/repository-contexts.yaml`; repository assessments keep their own
activity UUID, basis commit, confidence and evidence provenance.

The importer is deliberately separate from the reviewed runtime seed:

```bash
# Validate a producer without writing portfolio state
python scripts/dsomm/aggregate-repository-assessments.py \
  --source AlbanAndrieu/nabla-site-alban=/path/to/nabla-dsomm-assessment.json \
  --check

# Future portfolio acceptance once all configured producers are published
python scripts/dsomm/aggregate-repository-assessments.py \
  --source AlbanAndrieu/nabla-compose=/path/to/nabla-compose-assessment.json \
  --source AlbanAndrieu/fastapi-sample=/path/to/fastapi-assessment.json \
  --source AlbanAndrieu/nabla-site-alban=/path/to/site-alban-assessment.json \
  --source AlbanAndrieu/nabla-site-bababou=/path/to/site-bababou-assessment.json \
  --check --require-complete-sources

# Aggregate reviewed producer documents
python scripts/dsomm/aggregate-repository-assessments.py \
  --source AlbanAndrieu/nabla-site-alban=/path/to/nabla-dsomm-assessment.json \
  --output /mnt/cpool/dsomm/reports/repository-assessment.aggregate.json
```

An explicit HTTPS URL can be used instead of a local path once a producer is
published, for example its `/.well-known/nabla/dsomm-assessment.json` mirror.
HTTP URLs are rejected, redirects must remain HTTPS and each imported document
is capped at 1 MiB before JSON parsing.

Aggregation rules are fail-closed:

- producer and portfolio DSOMM `version` **and** `sourceCommit` must match;
- import identity uses the vendored 249-activity index derived from upstream
  `generated/model.yaml` at the pinned DSOMM 5.0.2 commit; the smaller
  22-activity runtime seed remains only the conservative Nabla prefill;
- claims join only by upstream `activityUuid`, with canonical name, dimension
  and level checked against that full identity index;
- `not-applicable` is excluded from the average;
- a missing repository or missing activity claim remains `not-assessed`, never
  zero;
- a context gets a `recommendedDsommState` only when **every configured
  repository** has assessed that activity or declared it not applicable;
- repository evidence is retained with a namespaced `producerRef`.

The generated portfolio JSON is a review/aggregation artifact, not an automatic
mutation of `team-progress.yaml`. This prevents one well-instrumented repository
from silently raising the maturity of the whole `Nabla Applications` context.
Restricted evidence retains its visibility marker; a future public UI must not
assume that such evidence is publicly readable.

## Architecture

- `dsomm`: frontend-only OWASP DSOMM UI on `172.17.0.24:31088`.
- `config/meta.yaml`: default Nabla assessment contexts.
- `dsomm-baseline`: manual profile; queries GitHub using `gh` and writes a
  CSV under `/mnt/cpool/dsomm/reports`.
- The baseline report is **evidence**, not a maturity verdict. Upstream explicitly
  leaves many activities as manual/interview/process checks.

DSOMM stores assessment data in YAML and browser localStorage. Do not place
sensitive evidence directly in Git. Export reviewed progress/evidence from the
browser and store it in an approved protected location before relying on it as
assessment evidence.

The TrueNAS deployment mounts protected runtime state instead of the image's
sample files:

```text
/mnt/cpool/dsomm/state/team-progress.yaml
/mnt/cpool/dsomm/state/team-evidence.yaml
```

`deploy-dsomm.sh --apply` creates these files only when absent, initializing
them from the reviewed repository seed and enforcing mode `0600`. It never
overwrites an existing assessment. When you export progress/evidence from the browser, copy
the reviewed YAML into these runtime paths (not the repository), preserve
`0600`, then reload/redeploy DSOMM.

## Runtime secret

Create:

```text
/mnt/cpool/secrets/runtime/dsomm/.env.secrets
```

with at least:

```dotenv
GH_TOKEN=<dedicated GitHub token>
```

Start with the least privilege that lets the selected checks read repository
metadata/security settings. The upstream baseline README mentions broader
write/admin permissions; do not grant them by default. Checks that require
unavailable organization/admin APIs should remain unavailable/manual instead of
expanding token privilege without review.

## Deploy UI

The UI follows the TrueNAS Custom App lifecycle used by the rest of the
repository. From the canonical TrueNAS checkout:

```bash
sudo bash scripts/truenas/deploy-dsomm.sh --check
sudo bash scripts/truenas/deploy-dsomm.sh --apply
```

The first `--check` is expected to fail with a clear missing-App message before
initial registration, but still validates Compose and generated contracts.
`--apply` reconciles the Custom App through TrueNAS middleware, waits for
`RUNNING`, then requires the HTTP endpoint to answer.

DSOMM remains `x-nabla.status: planned` until that runtime acceptance has been
reviewed. After acceptance, change the UI service to `status: active`, regenerate
catalog/consumers and rerun the local quality gate. This prevents Gatus/AutoKuma
from reporting a service as DOWN before it is actually deployed.

The frontend image and the assessment model are pinned independently.

The repository previously referenced `wurstbrot/dsomm:5.0.0`, but that tag is
not published by the Docker Hub repository used by the upstream installation
instructions. The deployment therefore uses the published versioned frontend
tag `wurstbrot/dsomm:4.4.1` instead of following mutable `latest`.

The assessment content remains DSOMM **5.0.2**: `deploy-dsomm.sh --apply`
downloads `generated/model.yaml` from the already-reviewed upstream commit
`a2c1b7e6c7cc22de0d478027d76fd8d02c41fd7a`, validates its declared version
and activity UUID presence, stores it under
`/mnt/cpool/dsomm/state/model.yaml`, and mounts that exact file as
`/srv/assets/YAML/default/model.yaml`. Existing assessment progress/evidence
remain separate and are never overwritten.

`deploy-dsomm.sh` also verifies that the configured frontend image is either
already local or resolvable by the Docker registry before mutating/starting the
TrueNAS App. Override `DSOMM_IMAGE` only with another reviewed version/digest.

## Run the GitHub baseline

The runner is deliberately not always-on. Export `DSOMM_GITHUB_TOKEN` securely
in the current shell, then materialize it through the canonical Vaultwarden
workflow:

```bash
bash scripts/truenas/prepare-security-tooling-secrets.sh --import-env dsomm
bash scripts/truenas/prepare-security-tooling-secrets.sh --import-env-apply dsomm
sudo -E bash scripts/truenas/prepare-security-tooling-secrets.sh --apply dsomm
sudo -E bash scripts/truenas/prepare-security-tooling-secrets.sh --verify-vaultwarden dsomm
```

Then build and run the bounded baseline:

```bash
mkdir -p /mnt/cpool/dsomm/reports
chmod 700 /mnt/cpool/dsomm/reports

docker compose -f apps/dsomm/compose.yml --profile manual build dsomm-baseline

DSOMM_BASELINE_REPOS=AlbanAndrieu/nabla-compose \
  docker compose -f apps/dsomm/compose.yml --profile manual \
  run --rm dsomm-baseline
```

By default the runner checks four repositories and maps them into the two contexts configured in `meta.yaml`:

```text
AlbanAndrieu/nabla-compose,AlbanAndrieu/fastapi-sample,AlbanAndrieu/nabla-site-alban,AlbanAndrieu/nabla-site-bababou
```

Override `DSOMM_BASELINE_REPOS` with any comma-separated repository set for a
bounded assessment run.

The default reports are:

```text
/mnt/cpool/dsomm/reports/dsomm-baseline.csv
/mnt/cpool/dsomm/reports/dsomm-baseline.md
```

The Markdown file separates detected automated evidence, automated gaps and
manual DSOMM activities so the human assessment can be completed without
mistaking the GitHub baseline for the final maturity score. It also maps each
default repository to the matching DSOMM context using
`config/repository-contexts.yaml`; this is a review aid, not automatic
progress/evidence mutation.

Use supported findings to seed the human assessment. For every
`Not Supported - Manual Process` row, add human evidence only after checking
the corresponding DSOMM activity and current repository/runtime/process
evidence.

## Initial review aid

Before entering maturity states, review
[`INITIAL_REVIEW.md`](./INITIAL_REVIEW.md). It inventories concrete candidate
evidence visible in the four Nabla repositories and deliberately separates
detected repository controls from manual/unverified DSOMM activities.

## Baseline coverage limit

The pinned Tweag baseline commit predates **DSOMM 5.0**. Its automated check
catalog therefore remains a partial evidence helper for the older activity set;
it does **not** automatically assess the new DSOMM 5.0 dimensions such as
**Agentic AI** and **Identity**. Those dimensions, and every activity that the
baseline marks unsupported/manual, must be reviewed directly in the DSOMM 5.0
UI.

Do not convert the baseline's `LEVELx Score` or `Total Score` into the Nabla
maturity verdict. Use those numbers only as upstream scanner diagnostics and
attach the underlying concrete evidence to the matching DSOMM activity after
human review.

## Upstream

- DSOMM install: https://github.com/devsecopsmaturitymodel/DevSecOps-MaturityModel/blob/main/INSTALL.md
- DSOMM activities: https://github.com/devsecopsmaturitymodel/DevSecOps-MaturityModel-data
- Baseline extension: https://github.com/tweag/dsomm-baseline

The baseline image is pinned to commit
`3255561bc9162e335d2c79b72e12b1478075e610` by default. Its two upstream
Python dependencies are also pinned locally to `PyYAML==6.0.3` and
`tabulate==0.10.0` so rebuilding that commit does not silently change the
runtime.
