# Compose tasks

Apply this guidance only to Compose work.

- Inspect the target Compose file and directly referenced local files only.
- Do not recursively inspect app directories or submodules without a concrete need.
- Prefer pinned image versions/digests over floating tags where practical; leave updates to Renovate.
- Do not mount `/var/run/docker.sock` directly when the existing socket-proxy pattern can satisfy the requirement.
- Preserve TrueNAS paths, external networks and deployment-specific environment variables unless the task explicitly changes them.
- For every new or materially reconnected Compose service, apply `.agents/skills/nabla-service-catalog/SKILL.md`: add service-local `x-nabla` metadata, model evidenced dependency relations, and regenerate the catalog contracts.
- Validate each changed Compose file with `docker compose --project-directory "$(dirname FILE)" -f FILE config --quiet --no-interpolate --no-env-resolution`.
- Do not run `docker compose up` as a formatting/configuration check.
