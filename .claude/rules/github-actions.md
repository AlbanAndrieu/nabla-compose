# GitHub Actions tasks

Apply only when editing `.github/workflows/**` or CI configuration.

- Keep PR gates minimal: pre-commit, MegaLinter and Compose validation when relevant.
- Prefer `paths` filters and `concurrency.cancel-in-progress: true`.
- Pin third-party actions to full commit SHAs; let Renovate update pins.
- Use `persist-credentials: false` and least-privilege `permissions`.
- Avoid duplicate scanners/workflows that enforce the same rule.
- Heavy repository-wide security scans should be scheduled/manual unless they are required as a PR gate.
- Read the failing job/step logs before changing CI; do not infer the failure from the workflow alone.
