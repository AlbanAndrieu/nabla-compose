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

### Authentication lockout guard

REST API KeyAuth failures can feed pfSense REST API Login Protection and its
`sshguard` table. This matters because a stale 64-character key can initially
produce normal HTTP `401 AUTH_AUTHENTICATION_FAILED` responses and, after
several attempts, the same workstation can observe HTTPS and SSH connection
timeouts even though nginx/WebConfigurator remains healthy for another source.

The helper therefore performs a single posture-key preflight against
`/api/v2/system/version`. If it returns HTTP 401, the remaining authenticated
posture and security matrices are skipped. Do not repeatedly rerun the helper
with a rejected key.

Observed incident sequence on 2026-10-04:

1. UI hostname and LAN probes returned HTTP 200;
2. three posture API calls with the stale workstation key returned HTTP 401;
3. subsequent API calls and SSH from that source timed out;
4. a separate LAN request still returned HTTP/2 200 from nginx.

This pattern is source-specific and is compatible with Login Protection/
`sshguard`; it is not evidence of a global WebConfigurator outage. Confirm an
exact source address in the `sshguard` table from an unblocked management path
before deleting anything. The recovery helper intentionally never removes
`sshguard` entries automatically.

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

The helper discovers FastAPI Cloud egress from `/api/runtime/topology` and
falls back to the shared `/api/health-board` runtime projection when that route
is not exposed by the active deployment. A failed egress discovery never removes
the explicit LAN observer sources.

Authenticated matrices are fail-fast: a first `401` stops further KeyAuth
requests, including the second identity, to avoid feeding REST API Login
Protection/sshguard. Transport output uses a non-whitespace field separator so
an empty curl `remote_ip` remains `peer=unknown` instead of shifting latency
fields.


## API-key bootstrap and rotation

`POST /api/v2/auth/key` is a configuration write even though the returned key is
only shown once. A service identity carrying `User - Config: Deny Config Write`
cannot persist that key. The safe rotation sequence is therefore:

1. temporarily remove `User - Config: Deny Config Write` from the service identity;
2. temporarily grant only `api-v2-auth-key-post`;
3. create the key through `POST /api/v2/auth/key` using that identity's Basic
   credentials; do not enable global BasicAuth merely for this endpoint;
4. verify that the SSH redacted inventory contains the expected owner, byte
   length, hash algorithm and description;
5. remove `api-v2-auth-key-post` and restore `User - Config: Deny Config Write`;
6. run the posture/security `200/403` matrix again.

A key returned to the caller is not sufficient persistence evidence when pfSense
logged `Save config permission denied`. The inventory and subsequent KeyAuth
matrix are the acceptance evidence.

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
