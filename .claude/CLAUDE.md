# nabla-compose

Read `AGENTS.md` first and treat it as the canonical repository policy.

This is a homelab/Compose repository. Keep context narrow: inspect changed/relevant files first and avoid recursive reads of submodules, generated output, reports, caches and lockfiles.

Load specialized instructions only when the task needs them:
- Compose: `.claude/rules/compose.md`
- GitHub Actions: `.claude/rules/github-actions.md`
- Security: `.claude/rules/security.md`

Prefer deterministic tools over model reasoning for formatting and validation. Run pre-commit on changed files before committing and the pre-push hook before pushing. Never start the complete homelab stack merely to validate configuration.
