# Local agent runbook

> `AGENTS.md` is the canonical repository policy. This file is an execution
> runbook for smaller local models; it must never override or duplicate the
> policy in `AGENTS.md`.

## Start every implementation task

Run:

```bash
mise run agent-context
```

Use the output to identify the current branch, changed paths, likely skills and
the smallest useful validation scope. Then read `AGENTS.md` and load only the
skills relevant to the current task through OpenCode's native `skill` tool.

Do not recursively read the repository to "understand everything". Verify paths
with Git/search before assuming that a file, script, service or test exists.

## Task routing

| Task evidence | Load these skills first | Prefer these repository entry points |
| --- | --- | --- |
| `.env`, `.env.secrets`, `env_file`, Vaultwarden | `homelab-secrets`, `docker-compose-orchestration`, `nabla-service-catalog` | `scripts/check-service-migration-bundle.py`, `scripts/truenas/bootstrap-repository-runtime.sh` |
| Compose service/runtime/dependency | `docker-compose-orchestration`, `nabla-service-catalog` | Compose config validation, topology/consumer generators |
| Backstage/catalog/security graph | `nabla-service-catalog` | `scripts/audit-service-catalog-v2-parity.py`, `scripts/generate-catalog-v2-artifacts.py` |
| TrueNAS runtime acceptance | matching service skills + `homelab-runtime-status` | repository `scripts/truenas/*` helpers |
| pfSense / HAProxy / PF / Snort / pfBlockerNG | `pfsense-api-debugging` | repository diagnostic scripts before appliance mutation |
| Quality/CI failure | no broad skill preload | failing local test/hook first, then `mise run agent-fix` |

If several rows match, load the union of the named skills but do not preload
unrelated skills.

## Small-model execution loop

1. **Observe** — run `mise run agent-context`; inspect `git status`, current
   diff and the exact task.
2. **Route** — load the matching skill(s); read only directly relevant files.
3. **Plan one bounded batch** — state the intended files and acceptance check
   before editing.
4. **Edit minimally** — preserve existing patterns; do not refactor unrelated
   code.
5. **Validate narrowly** — run the closest unit/contract/config test first.
6. **Converge locally** — run `mise run agent-fix`.
7. **Review the deterministic diff** — do not blindly accept generated changes.
8. **Commit only the logical batch**.
9. **Publication gate** — run `mise run agent-pre-push`; push only after it is
   green and the branch is not `master`.

If a check fails without producing a deterministic change, inspect and fix the
first concrete error. Do not repeat the same command hoping for a different
result, and do not switch to GitHub Actions as the edit loop.

## Hard stop rules

- Never read, print, source, grep or paste live secret values from `.env*`.
- Never invent a file, test, endpoint, service relation or command; prove it from
  the repository/runtime first.
- Never modify `master` directly.
- Never use `git push --no-verify`, force push, `git reset --hard` or
  `git clean -fd`.
- Never weaken tests, security gates or schema validation to get green output.
- Never bulk-finalize secret migrations; acceptance remains one service at a
  time.
- Never claim a local gate passed unless its command actually completed green.

## OpenCode helpers

- `/continue-pr` — resume the current PR from bounded Git context and roadmap
  evidence.
- `/migrate-service <service>` — execute the combined P0.3 + Backstage bundle.
- `/review` — ask the read-only reviewer subagent to inspect the current diff.
- `/quality` — converge and run the local publication workflow.
