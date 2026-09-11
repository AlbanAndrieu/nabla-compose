# Operator scripts

`scripts/` contains executable operator workflows. Keep entry points stable and
move reusable implementation details into `scripts/lib/` instead of copying
helpers between platform directories.

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
