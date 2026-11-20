# GitHub App installation scope — isolated OpenTofu state

This stack manages only the selected repositories of the **existing** read-only
`nabla-github-app` installation. It does not register the App, grant its
permissions, issue keys, or install it for the first time. Bootstrap:
[manifest and operator consent](../../docs/github-app-defectdojo.md).

1. Create the App with the versioned manifest, approve Selected repositories:
   fastapi-sample, nabla-compose, nabla-site-alban, nabla-site-bababou.
2. Materialize the private key via Vaultwarden on TrueNAS and run
   `discover-github-app-installation.py --apply` to verify all four repositories
   belong to the same selected, read-only installation. Use the **installation
   ID**, not App ID, from the private metadata; IDs themselves are not secrets.
3. On a workstation with the authorized owner identity, export
   `NABLA_ARTIFACT_APP_INSTALLATION_ID` with this verified value. Supply a
   short-lived authorized user credential via `GITHUB_TOKEN` (not a collector
   installation token). Clear inherited GITHUB_APP_* auth variables to avoid
   the provider 6.13 app-auth precedence issue. Never put a PAT, PEM or JWT in
   HCL/state. The runtime collector itself remains read-only, with no PAT.
4. Validate and plan independently from the ruleset stack:

   ```bash
   mise exec -- tofu -chdir=terraform/github-artifact-app fmt -check
   mise exec -- tofu -chdir=terraform/github-artifact-app init -backend=false
   mise exec -- tofu -chdir=terraform/github-artifact-app validate
   scripts/infra/terragrunt-safe.sh infrastructure/github-artifact-app plan
   ```

   Expect an import and no changes when the exact four repos are already
   selected. **Do not apply** if the installation identity is unverified or
   plan removes/adds unexpected repositories. This resource is authoritative
   and may remove extra repositories. Before any apply verify the intended
   installation on GitHub. After adoption keep the ID configured; do not
   destroy the resource (prevent_destroy). Use state rm after review to stop
   managing it without changing GitHub.

Provider 6.13 source: https://github.com/integrations/terraform-provider-github/blob/v6.13.0/github/resource_github_app_installation_repositories.go
Known auth issue: https://github.com/integrations/terraform-provider-github/issues/3531

CODED only; provider init/validate/plan/apply and actual App creation/install
NOT_RUN. No other GitHub governance settings are managed here.
