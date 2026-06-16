# Nexus

OpenTofu configuration for [Sonatype Nexus Repository Manager](https://www.sonatype.com/products/sonatype-nexus-repository), the artifact proxy/registry running on the NAS.

## Manual Bootstrap

Before running `terragrunt apply` for the first time, you need to manually:

1. Delete all default repositories that ship with Nexus
2. Create a user with admin privileges for OpenTofu to authenticate with

## What it manages

- **Repositories** - local, remote and groups
- **Roles:**
- **Users:**
- **Security realms** — `NexusAuthenticating`, `DockerToken`, `NpmToken`, `TerraformToken`
- **1Password items** — credentials for all managed users are automatically stored in the `Automation` vault
