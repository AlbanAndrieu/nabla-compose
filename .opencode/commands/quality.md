---
description: Converge the Nabla local quality gate before publication
agent: build
---

Apply the local-first publication workflow from `AGENTS.md` and `agent.md`.

1. Run `mise run agent-context`.
2. Identify the narrowest test/hook for the changed paths and run it first.
3. Fix the first deterministic failure; do not widen to unrelated suites.
4. Run `mise run agent-fix`.
5. If `QG_FIX_STALLED` or another non-autofixable failure appears, inspect that
   failure instead of repeating the same command.
6. Use the `reviewer` subagent for a read-only regression/security pass over the
   resulting diff.
7. Review every deterministic generator/formatter change.
8. Once the logical batch is committed, run `mise run agent-pre-push`.
9. If `QG_AUTOFIX_APPLIED` appears, review and commit/amend only those
   deterministic changes and rerun `mise run agent-pre-push`.
10. Do not push until the gate is green. Never use `--no-verify`, force-push,
    weaken a quality/security rule, or use GitHub Actions as the edit loop.
