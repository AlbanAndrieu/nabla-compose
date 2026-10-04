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

Two independent least-privilege identities are evaluated when their keys are
present in the caller environment:

- `PFSENSE_POSTURE_API_KEY`: the four posture GET endpoints must return `200`
  and `/api/v2/diagnostics/table?id=snort2c` must return `403`;
- `PFSENSE_SECURITY_API_KEY`: the Snort table endpoint must return `200` and
  `/api/v2/status/services` must return `403`.

Each key is written to its own mode-0600 temporary curl header file so no secret
is placed on the curl command line, sent through SSH, or printed in the report.
A `401` is therefore an authentication result, a `403` can be an expected
least-privilege result, while `http=000` is reported with the curl exit code and
transport timings instead of being collapsed into an authentication failure.

The SSH evidence also reports, without secret material:

- REST API enabled/read-only/login-protection/auth-method settings;
- whether `fastapi_posture` and `fastapi_security` exist, are enabled and are
  outside the `admins` group;
- exact privileges, including missing or unexpected grants;
- API-key owner, byte length, hash algorithm, description, hash presence and key
  count. The key value and stored hash are never emitted.

The helper probes both the configured hostname path and the direct LAN address.
The direct IP probe intentionally disables certificate hostname validation because
it is transport comparison evidence; the hostname probe remains the TLS-trust
proof.

## SSH is a separate capability

A successful `/api/v2/status/services` row showing `sshd` as running proves the
daemon state reported by pfSense. It does **not** prove that TCP/22 is reachable
from the workstation. Firewall policy, interface binding, or a non-default SSH
port may still make `172.17.0.1:22` time out.

Do not assume port 22. Prefer the existing workstation SSH alias. The currently
validated workstation contract resolves as `admin@home.albandrieu.com:9922`:

```bash
ssh -G home.albandrieu.com | grep -E '^(hostname|user|port) '
```

The recovery helper therefore defaults to `home.albandrieu.com` and lets
`~/.ssh/config` supply the user and port. Explicit overrides remain available:

```bash
scripts/pfsense/diagnose-recover.sh --check --target admin@home.albandrieu.com --port 9922
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

The read-only attribution also inspects the pfSense `sshguard` table used by
Login Protection. An exact match is reported as `LOGIN_PROTECTION_MATCH`, but
the helper deliberately never deletes `sshguard` entries: authentication
lockouts require separate operator review.

Never widen firewall policy or flush PF tables merely to make a diagnostic pass.
