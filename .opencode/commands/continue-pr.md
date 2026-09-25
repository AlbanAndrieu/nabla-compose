---
description: Resume the current PR from bounded local context
agent: build
---

Resume the current pull-request work without broad repository exploration.

1. Run `mise run agent-context`.
2. Read `AGENTS.md` and `agent.md`.
3. Inspect the current diff and only the roadmap section(s) directly related to
   those changed paths.
4. Load only the skill(s) indicated by the task/path evidence.
5. Pick one finishable, highest-leverage unresolved item that belongs to the
   current PR scope.
6. State the exact files and validation command you intend to touch/run.
7. Implement the smallest safe patch.
8. Run the narrowest contract first, then `mise run agent-fix`.
9. Do not use remote CI as the edit loop and do not broaden the PR merely because
   another roadmap item exists.
