# Claude repository adapter

Read `AGENTS.md` first and treat it as the canonical repository policy for safety, validation, publishing, tools, and context efficiency.

This repository is the Nabla homelab/Docker Compose orchestrator. Do not infer FastAPI application conventions from sibling repositories or checked-out submodules.

For Claude-specific routing, use `.claude/CLAUDE.md`. Load `.claude/rules/**` and `.agents/skills/**` only when the current task matches their scope; do not preload every rule or skill.

Do not duplicate policy here. If cross-agent behavior changes, update `AGENTS.md` and keep this file as a small adapter.
