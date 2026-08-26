# GitHub required checks policy

`master` is the deployment source of truth and must not be merged while validation is absent or failing.

## Required pull-request checks

Configure a GitHub repository ruleset for `master` that requires pull requests and the following status checks when they are applicable:

- `Compose Validate` for Docker Compose changes;
- `Pre-commit` for repository quality, generated service catalog synchronization and JSON/YAML validation;
- `MegaLinter` for repository-wide lint/security validation;
- `Terragrunt CI` for OpenTofu/Terragrunt changes.

Do not bypass the ruleset solely because a check has not started. A missing expected check is a release-blocking condition until its trigger or repository Actions configuration is understood.

## Generated catalog invariant

Changes to Compose `x-nabla`, `catalog/service-icons.json`, `catalog/service-topology.static.json`, or the generator must leave both generated contracts synchronized:

```bash
python scripts/generate-service-topology.py
python scripts/generate-service-topology.py --check
python -m json.tool catalog/services.json >/dev/null
python -m json.tool catalog/service-topology.json >/dev/null
```

The generated files are:

- `catalog/services.json`;
- `catalog/service-topology.json`.

Never hand-edit these contracts as the primary source of truth. Update Compose `x-nabla` or the static overlay and regenerate them.

## Merge safety

Before merging a pull request that changes CI policy itself:

1. verify the expected workflows are attached to the PR HEAD;
2. verify the generated contracts parse as JSON;
3. verify `scripts/quality-gate.sh` contains no temporary diagnostics;
4. verify `.pre-commit-config.yaml` contains no temporary synchronization markers;
5. only then allow merge.
