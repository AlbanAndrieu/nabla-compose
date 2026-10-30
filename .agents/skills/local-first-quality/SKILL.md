---
name: local-first-quality
description: Converge formatter, lint, generated artifacts and targeted contracts locally, then run one complete publication gate before updating a PR.
---

# Local-first quality

Use this skill for quality failures, PR continuation, formatter/linter fixes and
publication work. Keep remote CI as an independent safety net, not an edit loop.

## Invariants

- Resolve the user-selected PR, its state, branch and exact remote HEAD before
  editing. A merged or closed PR cannot receive a new diff; branch from the
  current protected base and create a Draft successor instead.
- Never write to `master`, bypass hooks, force-push, weaken a quality/security
  rule or claim a gate passed on another SHA.
- Work in one dedicated worktree. Preserve unrelated changes and staged
  submodule gitlinks.
- Use the first deterministic failure and the narrowest relevant test. Do not
  reload a complete log or roadmap when a bounded excerpt answers the decision.
- Distinguish repository validation from live TrueNAS, workstation or hardware
  acceptance. Repository work does not authorize runtime mutation.

## Evidence levels and commands

```text
L0 static       just context && just preflight
L1 targeted     exact failing test or config check
L2 convergence mise run agent-loop; then mise run agent-fix
L3 publication commit; mise run agent-pre-push
```

- **L0 · static** verifies branch/base/destructive-diff/exec-bit safety before
  dependency or build work.
- **L1 · targeted** reproduces the named failure, including a negative case
  when the behavior is fail-closed.
- **L2 · convergence** applies deterministic fixes and changed-file contracts.
  `agent-loop` sees only the current uncommitted batch. `agent-fix` sees the
  complete branch delta and runs branch-wide targeted contracts. Neither is
  the complete repository gate.
- **L3 · publication** runs the full repository tests and canonical
  formatter/linter/security gate exactly once on the committed HEAD. Only L3
  may be reported as the complete local quality gate.

Aliases are available when preferred:

```bash
just context
just preflight
just loop
just pre-push
```

## Iteration

1. Run `just context` and `just preflight`.
2. Run the narrowest test that can falsify the proposed patch.
3. Apply one bounded edit batch.
4. Run `mise run agent-loop` (or `just loop`).
5. Fix the first non-autofixable failure. Do not repeat an unchanged command.
6. Run `mise run agent-fix` once before commit. Review every generated or
   formatter diff; it deliberately defers the complete suite.
7. Commit the logical batch.
8. Run `mise run agent-pre-push`. This is the single authoritative complete
   gate and requires a clean superproject.
9. Push once, compare the remote HEAD, and keep the PR Draft while iterating.

If `QG_FIX_STALLED` appears, inspect the compact failure and its private log.
If `QG_AUTOFIX_APPLIED` appears, review and amend only those deterministic
changes, then rerun `agent-pre-push`.

## Remote CI policy

Remote checks are evidence, not an editor.

- Do not manually rerun CI to discover a local formatter, lint or unit failure.
- With constrained credits, use the accepted `[skip ci]` convention and keep
  the PR Draft; never disable required security controls.
- Inspect status, then the first failing job/step, then bounded logs. Expand
  only when the smaller evidence is inconclusive.
- API-only fallback must disclose that the local gate did not run. Use an
  optimistic file update with the expected blob SHA for every GitHub write.

## Conditional references

Read only the reference selected by the task:

- OpenClaw or host-specific runtime work: [openclaw-and-hosts.md](references/openclaw-and-hosts.md).
- Python/Node worktrees, dependency setup or hook isolation:
  [development-environments.md](references/development-environments.md).
- Git bootstrap, reboot, YubiKey or persistent operator recovery:
  [operator-recovery.md](references/operator-recovery.md).
- Permissions, noexec, disconnected/API-only work, Dagger or shell UX:
  [advanced-diagnostics.md](references/advanced-diagnostics.md).

## Exécution opérateur : reprise et persistance

This is conditional operator-recovery work. Read
[operator-recovery.md](references/operator-recovery.md) before proposing any
bootstrap, reboot or hardware-dependent command. Keep one action per step and
write diagnostics in clear French without exposing secrets.

## Skills externes : contrôle local avant installation

`AGENTS.md` and `docs/agent-skills-architecture.md` remain authoritative.
Obtain the user's accord explicite before installing each external skill, then
run `just agent-skills-check`. For multi-repository security work, batch one
logical tree per repository, use expected-HEAD updates, preserve all security
gates and distinguish static readiness from CI and runtime acceptance.
