# Operator scripts

`scripts/` contains executable operator workflows. Keep entry points stable and
move reusable implementation details into `scripts/lib/` instead of copying
helpers between platform directories.

## Local-first task entry points

`justfile` is a lightweight interface alongside the unchanged legacy `Makefile`.
Install pinned tools using `mise install` (Just 1.58.0; Betterleaks 1.9.0),
then use:

```bash
just --list
just quality
just fix
just pre-push
just tooling-test
just secrets
```

`just quality` delegates to `mise run agent-quality`, while `just fix` uses
the existing deterministic autofix gate. `just pre-push` performs the strict
publication checks without pushing or merging. `just secrets` scans the current
worktree with Betterleaks, `just secrets-staged` scans staged diffs and
`just secrets-history` is an explicit, potentially expensive full-history scan.
Outputs are redacted; no online credential validation is requested.

Betterleaks v1.9.0 is the sole active Pre-commit secret scanner; the existing
`.gitleaks.toml` is intentionally retained as its compatibility policy during
migration. Historical `gitleaks:allow` comments are still understood by
Betterleaks. The old MegaLinter Gitleaks linter remains disabled.

The `Makefile` is retained for legacy targets. Avoid its default `make`
build/cleanup cycle when only validation is intended.

## Ownership

- `scripts/truenas/`: TrueNAS lifecycle, diagnostics, deployment and recovery.
- `scripts/talos/`: Talos/Kubernetes installation, validation and smoke tests.
- `scripts/pfsense/`: pfSense posture, diagnosis and recovery.
- `scripts/secrets/`: metadata-driven secret rendering and validation.
- `scripts/observability/`: monitoring/telemetry helpers.
- `scripts/lib/`: small side-effect-free shell primitives shared by operator
  entry points.

## Refactor rules

1. Preserve existing operator entry-point paths while extracting shared code.
2. Keep generic primitives in `scripts/lib/`; keep platform behavior in the
   owning platform directory.
3. Do not create a library for a helper used by only one script.
4. Shared libraries must not mutate infrastructure when sourced.
5. Immutable bundles must explicitly include and checksum every sourced file.
6. New shell code must pass `bash -n`, shfmt and ShellCheck; Bashate is a
   complementary style check, not a second semantic linter.

The long-term target is fewer entry points with explicit modes, thin wrappers
for compatibility, and domain libraries only where duplication is proven.
