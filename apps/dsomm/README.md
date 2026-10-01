# OWASP DSOMM

Repository-owned deployment of the OWASP DevSecOps Maturity Model UI plus a
manual, pinned `tweag/dsomm-baseline` evidence runner.

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

The upstream INSTALL currently documents `wurstbrot/dsomm:latest`. Override
`DSOMM_IMAGE` with a reviewed immutable digest when one is selected.

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

Multiple repositories are comma-separated, for example:

```text
AlbanAndrieu/nabla-compose,AlbanAndrieu/fastapi-sample,AlbanAndrieu/nabla-site-alban,AlbanAndrieu/nabla-site-bababou
```

The default reports are:

```text
/mnt/cpool/dsomm/reports/dsomm-baseline.csv
/mnt/cpool/dsomm/reports/dsomm-baseline.md
```

The Markdown file separates detected automated evidence, automated gaps and
manual DSOMM activities so the human assessment can be completed without
mistaking the GitHub baseline for the final maturity score.

Use supported findings to seed the human assessment. For every
`Not Supported - Manual Process` row, add human evidence only after checking
the corresponding DSOMM activity and current repository/runtime/process
evidence.

## Upstream

- DSOMM install: https://github.com/devsecopsmaturitymodel/DevSecOps-MaturityModel/blob/main/INSTALL.md
- DSOMM activities: https://github.com/devsecopsmaturitymodel/DevSecOps-MaturityModel-data
- Baseline extension: https://github.com/tweag/dsomm-baseline

The baseline image is pinned to commit
`3255561bc9162e335d2c79b72e12b1478075e610` by default.
