# pfSense diagnosis and bounded recovery

`nabla-compose` owns pfSense operational diagnostics and recovery. `fastapi-sample`
consumes read-only pfSense evidence but must not own appliance administration or
recovery logic.

## Normal read-only check

From the workstation:

```bash
scripts/pfsense/diagnose-recover.sh --check
```

The helper first validates the HTTPS/UI and REST API v2 control paths, then tries
to collect deeper appliance evidence over SSH. A failed SSH connection does not
discard successful HTTPS/API evidence in `--check` mode.

If SSH is intentionally filtered or unavailable, use:

```bash
scripts/pfsense/diagnose-recover.sh --api-only
```

The read-only API key is taken from `PFSENSE_POSTURE_API_KEY`. It is written to a
mode-0600 temporary curl header file so the key is not placed on the curl command
line, is never sent through SSH, and is not printed in the report.

The API contract covers:

- `/api/v2/system/version`;
- `/api/v2/status/services`;
- `/api/v2/services/dns_resolver/settings`;
- `/api/v2/system/dns`.

The helper probes both the configured hostname path and the direct LAN address.
The direct IP probe intentionally disables certificate hostname validation because
it is transport comparison evidence; the hostname probe remains the TLS-trust
proof.

## SSH is a separate capability

A successful `/api/v2/status/services` row showing `sshd` as running proves the
daemon state reported by pfSense. It does **not** prove that TCP/22 is reachable
from the workstation. Firewall policy, interface binding, or a non-default SSH
port may still make `172.17.0.1:22` time out.

Do not assume port 22. Prefer an existing workstation SSH alias, or set the port
explicitly:

```bash
scripts/pfsense/diagnose-recover.sh --check --target root@172.17.0.1 --port PORT
```

The existing posture auditor remains useful for capacity/posture regression work:

```bash
scripts/pfsense/audit-posture.sh --ssh home.albandrieu.com
```

## Mutation boundary

`--apply` requires a successful SSH control path. It only performs the bounded
recovery actions implemented by the helper: restart PHP-FPM/webConfigurator and,
when Unbound was not proven healthy, restart the resolver. Dynamic Snort or
pfBlockerNG host entries are removed only with the additional explicit
`--unblock-sources` opt-in and only for exact source-address matches.

Never widen firewall policy or flush PF tables merely to make a diagnostic pass.
