# OpenCode build adapter — compact execution loop

`AGENTS.md` is the **canonical repository policy**; this file only describes
the short execution path for the smaller OpenCode build agent. It is explicitly
referenced by `.opencode/agents/build.md`, **not** auto-loaded by OpenCode.
Do not pre-read all skills, archives, logs, generated files or live `.env` files.

1. Check the current PR state, exact HEAD, dirty paths and nearest tests.
   Reuse a compatible open PR; never write to `master`.
2. Select capabilities before tools: `AGENT_EXECUTION_MODE=workstation` only
   with a real local checkout, toolchain and LAN access. Otherwise stay
   `offline`; never infer host reachability from documentation.
3. Run `mise run agent-context` **only on a workstation with mise**; otherwise
   inspect bounded GitHub refs/diffs. Load one matching skill on demand.
4. Apply a bounded patch and run the narrowest available L1 contract.
   Workstation: `mise run agent-loop` → `mise run agent-fix` → commit →
   `mise run agent-pre-push`. Repeat the gate after any autofix commit.
5. Remote/API-only: run only available offline tests; mark missing L2/L3
   and runtime checks `NOT_RUN`. Use a Draft PR and an exact-SHA ref update.
6. Never bypass hooks, read secrets, mutate the runtime without authorization
   or claim a `PASS` without an observed test.

Skill router: Compose/catalogue → `docker-compose-orchestration` and
`nabla-service-catalog`; secrets → `homelab-secrets`; pfSense →
`pfsense-api-debugging`; CI/PR → `local-first-quality`. Security audit
→ `security-audit` only when explicitly requested.

Detailed procedures: [execution modes](docs/agent-execution-modes.md) and
[conditional playbook](docs/agent-execution-playbook.md).
