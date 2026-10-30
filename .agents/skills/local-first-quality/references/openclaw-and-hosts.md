# OpenClaw and execution hosts

Read this reference only for OpenClaw, LiteLLM or host-specific runtime work.

## Choose the host first

| Host | Canonical checkout | TrueNAS operations |
| --- | --- | --- |
| TrueNAS | `/mnt/cpool/compose/nabla-compose` | local `sudo -n python3 scripts/truenas/...` |
| Ubuntu workstation | `~/w/nabla-compose` | existing SSH alias `truenas` on port 9922 |

Do not call `ssh truenas` from TrueNAS. Do not assume port 22 or a workstation
forward on TrueNAS. Run offline Python tests on the workstation by default;
reserve TrueNAS for evidence that depends on Docker, PostgreSQL or runtime keys.

For `openclaw-truenas-virtual-keys-plan|apply|status`, use
`scripts/truenas/dispatch-openclaw-litellm-keys.py`. It selects local Docker on
TrueNAS and SSH from the workstation. `status` is read-only.

## OpenClaw diagnostics and updates

- For `global-install-failed`, use `just openclaw-update-npm-triage`. Report
  fixed error categories, prefix state and versions; never copy a raw npm log.
- Separate npm exit failures, OpenClaw configuration errors, plugin cooldowns
  and model HTTP 429 responses.
- For an active Gateway, prefer native `config.get` + `config.patch` with
  `baseHash`. Fail without mutation when that contract is unavailable.
- In Python helpers, resolve mutable path constants at call time (`path=None`),
  not in default arguments captured before fixture patches.
- Unit tests must never run `npm install -g`, `openclaw update`, `doctor --fix`
  or restart the Gateway.
- Keep the `openclaw-embeddings` key and 768-dimension indexes independent from
  chat-agent changes.

A diagnostic or compilation is not proof of a successful live update. Report
live state only from bounded read-only runtime evidence.
