---
description: Converge the Nabla local quality gate before publication
agent: build
---

Apply the repository local-first publication workflow from `AGENTS.md`.

Run `mise run agent-fix`, inspect every deterministic change, and fix the first
non-autofixable failure. Once the logical batch is committed, run
`mise run agent-pre-push`.

If `QG_AUTOFIX_APPLIED` appears, review and commit/amend only those deterministic
changes, then rerun the same local command. Do not push until the gate is green.
Never use `--no-verify`, never weaken a quality/security rule, and never use
GitHub Actions as the formatting/linting feedback loop.
