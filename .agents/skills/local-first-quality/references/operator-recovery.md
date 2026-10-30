# Operator recovery and persistent Git state

Read this reference only for reboot recovery, exact-SHA operator runners,
YubiKey procedures or a checkout that must survive restart.

- `/tmp` is ephemeral and may be `noexec`. Never use it as the persistent Git
  base or claim it survives reboot.
- Store the bare repository under
  `$HOME/.local/share/nabla/git/nabla-compose.git` or an explicitly persistent
  `$NABLA_AGENT_STATE_DIR`.
- Resolve the remote PR HEAD with `git ls-remote`. Fetch only a missing object;
  never rely on shared `FETCH_HEAD` as authority.
- Create a private unique detached worktree at the pinned SHA. Serialize shared
  Git metadata operations with `flock`.
- Never run automatic `git pull`, `reset --hard`, `clean -fd`, worktree prune,
  GC or force-push in an operator recovery flow.
- If the remote advances, keep testing the pinned SHA and verify fast-forward
  ancestry separately. Never transfer a bootstrap expected-SHA variable into
  nested synthetic repositories.
- Preserve a dirty temporary worktree and report its path. Remove only a clean
  worktree created by the current execution.
- Put multi-command operator procedures in one versioned Bash script or Bash
  child. Never apply `set -euo pipefail` to the interactive parent shell.
- Stop at the first blocking step and report the exit code and private log path.

For PR #274 compatibility use
`scripts/workstation/run-pr274-local-quality.sh` and
`docs/runbooks/2026-10-24-pr274-local-quality-one-shot.md`. For YubiKey PIV82
recovery read `docs/runbooks/yubikey-piv82-postmerge-diagnostics.md`.

Do not turn a repository validation into a reboot, key generation, SOPS
rotation, Docker lifecycle action or hardware mutation without explicit user
authorization.
