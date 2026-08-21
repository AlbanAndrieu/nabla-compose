# Security tasks

Apply only to security-sensitive changes.

- Never add real credentials, tokens, passwords or private keys to examples or Compose defaults.
- Prefer secrets/env references and least privilege.
- Treat direct Docker socket access, privileged containers, host networking, broad capabilities and writable host mounts as high-risk changes requiring explicit justification.
- Preserve SHA pinning for GitHub Actions and deterministic image references where available.
- Use existing deterministic scanners (pre-commit, Gitleaks, Zizmor, Checkov) before asking the model to manually audit large trees.
- Report a suspected secret without reproducing its value.
