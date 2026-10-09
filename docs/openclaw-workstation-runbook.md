# OpenClaw workstation stabilization — operator runbook

Status: **workstation not yet accepted**. The local Gateway is reported healthy
on OpenClaw 2026.9.5, but that is not a completed update nor a verified recovery.

## Functional separation

- **OpenClaw**: personal Gmail/WhatsApp prioritization, summaries and proposed
  replies. Read-only first; no automatic sending, deletion or archiving.
- **Hermes**: development, cloud, DevSecOps and cybersecurity. Separate identity,
  storage, permissions, memory, logs and service credentials; no access to personal
  Gmail/WhatsApp by default.
- Never persist message contents, contacts, access tokens or attachments in Git,
  CI artifacts, Prometheus labels or shared technical-agent workspaces.

## Known workstation state, 2026-10-09

- CLI under `~/.local/share/mise/installs/node/24.18.1`, npm 12.2.0.
- Gateway user unit launches **/usr/bin/node**, but its JavaScript entrypoint
  is the OpenClaw package under the mise Node 24.18.1 directory.
- Package destination `/usr/lib/node_modules/openclaw` is a separate installation
  and is **not owned by the selected Gateway**; never overwrite it.
- Loopback-only Gateway `127.0.0.1:18789` was reachable in the supplied log.
- Update to 2026.9.9 was a **dry-run only**.
- No successful backup recorded. Doctor reported Slack migration pending,
  29 session SQLite issues, WhatsApp version drift/reconnect and plaintext
  secret fields. `doctor --non-interactive` was observed installing Firecrawl,
  so it **must not be used as a read-only audit**.

## Stage 0: read-only preflight

Run as the regular desktop user; **do not run as root**:

```bash
bash scripts/workstation/diagnose-openclaw.sh
```

The script returns 0 (clean), 2 (warnings) or 1 (errors), and avoids printing
private environment, process commandlines or OpenClaw configuration values.
Existing `/usr` installation and the Gateway service are untouched.

## Stage 1: backup and runtime convergence (operator-gated)

1. Record the current unit and effective runtime privately, excluding
   `Environment` and tokens. Prepare a versioned backup with `openclaw backup
   create`, verify the resulting artifact and prove an **isolated restore**.
   Keep permissions 0700 for directories and 0600 for backups. Do not save
   backup material into the repository.
2. Review the systemd user unit ownership and any managed `EnvironmentFile`.
   Make a reversible systemd user override pointing ExecStart at the **mise
   Node executable and existing mise package**. Preserve actual heap flags,
   port, runtime environment and service semantics. Do not replace the unit
   blindly with `openclaw gateway install --force`.
3. Reload user systemd and restart only within an operator-approved maintenance
   window; verify service and websocket health, then run the preflight again.
4. Align the global npm destination in the *operator shell* for an update:
   `PATH="$HOME/.local/share/mise/installs/node/24.18.1/bin:$PATH"`,
   `NPM_CONFIG_PREFIX="$HOME/.local/share/mise/installs/node/24.18.1"`.
   Confirm `npm prefix -g` and the resolved executable before and after.
5. Preview updates and run the actual update only after backup and the Node
   alignment. Recheck the latest stable version before pinning a target.
   **Never install into /usr** to silence a foreign-destination warning.

## Stage 2: app migration and personal messaging acceptance

- Dry-run session SQLite migration and inspect 29 reported issues, retaining
  the original index/transcripts. Fix Slack migration via `update repair`
  only after the backup and owner review, then controlled `doctor --fix`.
- Synchronize WhatsApp plugin with the chosen Gateway version and verify
  reconnection, channel probe and a harmless synthetic test. Test Gmail scopes
  and messages with a synthetic corpus before touching real personal messages.
- Move cleartext config tokens into SecretRefs, verify with `openclaw secrets
  audit --check`, then conduct `openclaw security audit --deep` privately.
- Limit mail/WhatsApp tools to least privilege and require explicit approval
  before drafts/labels, archiving, sending, deletion or forwarding. Untrusted
  message content must not become agent instructions.
- Inspect cron jobs in backoff and explicit LiteLLM overrides. Prevent cron
  duplicates, unexpected cross-agent routing and private payloads in telemetry.
- Measure functionality: service and model connectivity, channel stability,
  private digest accuracy, no unauthorized modifications/sends, successful
  restart, backup/restore and documented rollback.

## Stage 3: TrueNAS only after workstation acceptance

Build a separately isolated, version-pinned Compose deployment with ZFS
persistence, protected runtime secrets, bounded egress and no concurrent
ownership of WhatsApp/Gmail sessions. Rehearse restore offline, then plan
quiesce → final encrypted backup → transfer → single-owner cutover → reboot
verification → failback. Hermes technical credentials and workspace stay
distinct. **Do not start two active personal Gateway instances**.

**Acceptance**: workstation package/service Node alignment, no foreign
destination update attempts, tested recovery, no unresolved migration
breakage, stable authorized Gmail/WhatsApp workflows, and strict personal/
technical trust boundary.
