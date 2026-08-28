# Copilot repository instructions

`AGENTS.md` is the canonical policy for this repository. Apply it before making or publishing changes, including its security, quality-gate, tool-discovery, CI/log, polling, and context-efficiency rules.

This repository is the Nabla homelab/Docker Compose orchestrator, not the `fastapi-sample` application. Do not apply FastAPI, Poetry, SQLAlchemy, Vue, Datadog, or other sibling-project conventions unless the task explicitly targets content that actually uses them.

Keep repository inspection targeted. Load specialized `.agents/skills/**` guidance only when its task trigger applies. For Compose service changes, the `nabla-service-catalog` skill remains mandatory as specified by `AGENTS.md`.

Do not duplicate the canonical policy here; update `AGENTS.md` for cross-agent behavior changes.
