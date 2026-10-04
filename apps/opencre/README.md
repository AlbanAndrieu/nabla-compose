# OWASP OpenCRE

Repository-owned deployment intent for [OWASP OpenCRE](https://github.com/OWASP/OpenCRE).

OpenCRE correlates **common security requirements** across standards and
guidelines. In Nabla it is a reference/mapping capability:

- DSOMM remains the DevSecOps maturity assessment and evidence workflow;
- OpenCRE helps navigate equivalent/related requirements across OWASP, NIST,
  CIS, ISO and other supported mappings;
- `x-nabla`/Backstage remains authoritative for service identity and topology.

## Deployment contract

The upstream project currently documents:

```text
ghcr.io/owasp/opencre/opencre:latest
port 5000
```

and currently publishes no GitHub release. Therefore this service remains
`status: planned` while the default image is floating. **Before activation,
replace `latest` with a reviewed immutable version/digest.**

The default Nabla profile is deliberately read-mostly:

- `CRE_ENABLE_HEALTH=1`;
- `CRE_ALLOW_IMPORT=0`;
- `CRE_ENABLE_MYOPENCRE=0`;
- `CRE_ENABLE_LOGIN=0`;
- `NO_LOGIN=1`;
- persistent SQLite database at `/mnt/cpool/opencre/db/db.sqlite`.

MyOpenCRE/import/login are separate later decisions and must not be enabled
merely to make the base service reachable.

## Storage

The Compose bind mount declares application-owned state:

```text
/mnt/cpool/opencre/db
```

The generic repository storage bootstrap therefore discovers the
`cpool/opencre` dataset automatically:

```bash
sudo bash scripts/truenas/bootstrap-repository-storage.sh --check opencre
sudo bash scripts/truenas/bootstrap-repository-storage.sh --apply opencre
sudo bash scripts/truenas/bootstrap-repository-storage.sh --check opencre
```

No separate explicit dataset exception is required.

## Operator workflow

The repository-owned TrueNAS wrapper validates Compose, generated catalog
contracts and storage before touching the Custom App:

```bash
sudo bash scripts/truenas/deploy-opencre.sh --check
```

`--apply` is fail-closed when `OPENCRE_IMAGE` is mutable. The preferred
activation path is an immutable digest:

```bash
sudo env \
  OPENCRE_IMAGE='ghcr.io/owasp/opencre/opencre@sha256:<reviewed-digest>' \
  bash scripts/truenas/deploy-opencre.sh --apply
```

For a deliberately bounded PoC only, a mutable image can be authorized
explicitly with `OPENCRE_ALLOW_MUTABLE_IMAGE=1`. That override does **not**
satisfy production/runtime acceptance and the catalog remains `planned`.

## Acceptance before activation

1. pin `OPENCRE_IMAGE` to a reviewed immutable version/digest;
2. create/check `cpool/opencre` and record backup/rollback;
3. validate Compose locally;
4. deploy as an internal-only TrueNAS Custom App;
5. require `GET /rest/v1/health == 200` after initial upstream synchronization;
6. verify at least one useful DSOMM/SAMM/NIST/CIS/ISO correlation;
7. reboot/redeploy and prove the SQLite state survives;
8. only then change catalog/runtime intent from `planned` to `active`.

Neo4j/gap-analysis and custom imports are deliberately deferred until the base
read-only correlation service is accepted.
