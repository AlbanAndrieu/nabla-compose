include "root" { path = find_in_parent_folders("root.hcl") }

terraform { source = find_in_parent_folders("terraform/github-artifact-app") }

inputs = {
  # Non-secret ID, checked by discover-github-app-installation.py first.
  # Keep this supplied for every plan after adoption; prevent_destroy guards removal.
  installation_id = get_env("NABLA_ARTIFACT_APP_INSTALLATION_ID", "")
}
