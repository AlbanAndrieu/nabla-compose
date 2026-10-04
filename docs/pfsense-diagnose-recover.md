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


## REST API service identities

The canonical service accounts are deliberately split:

| Identity | Steady-state privileges | Purpose |
| --- | --- | --- |
| `fastapi_posture` | `api-v2-system-version-get`, `api-v2-status-services-get`, `api-v2-services-dns-resolver-settings-get`, `api-v2-system-dns-get`, `user-config-readonly` | pfSense service/DNS posture |
| `fastapi_security` | `api-v2-diagnostics-table-get`, `user-config-readonly` | exact Snort/PF table evidence |

Neither identity should belong to a named privilege-bearing group such as
`admins`. The only normal group membership is pfSense's implicit `all`
group.

Audit both accounts, privileges and persisted key metadata without exercising
KeyAuth:

```bash
bash scripts/pfsense/diagnose-recover.sh --check-identities
```

If either user is missing, create/reconcile both accounts to the steady-state
contract with one-line password files. Existing users keep their current
passwords; the files are used only to create missing users.

```bash
umask 077
printf '%s\n' '<posture-password>' > /tmp/pfsense-posture.password
printf '%s\n' '<security-password>' > /tmp/pfsense-security.password

PFSENSE_POSTURE_PASSWORD_FILE=/tmp/pfsense-posture.password \
PFSENSE_SECURITY_PASSWORD_FILE=/tmp/pfsense-security.password \
  bash scripts/pfsense/diagnose-recover.sh --apply-identities

rm -f /tmp/pfsense-posture.password /tmp/pfsense-security.password
```

The helper sends password material only through the encrypted SSH stdin stream;
it does not put plaintext passwords on the SSH command line or in the recovery
report.

## API-key bootstrap and rotation

`POST /api/v2/auth/key` first generates a key, then persists its hash through
pfSense configuration write logic. `User - Config: Deny Config Write`
(`user-config-readonly`) is therefore incompatible with **key creation**:
pfREST can generate and return a key while pfSense rejects the configuration
write.

Observed on 2026-10-04: after removing `User - Config: Deny Config Write`
from `fastapi_posture` while keeping `api-v2-auth-key-post`, the generated key
became visible on `/system_restapi_key.php`. This confirms the failed
configuration-write gate was `user-config-readonly`, not the key-generation
privilege. The remaining `api-v2-auth-key-post` grant is still temporary and
must be removed after rotation.

The evidence must be interpreted precisely:

- if a key for the service identity is visible in
  **System → REST API → Keys** (`/system_restapi_key.php`), that key record is
  persisted in pfSense configuration;
- a key returned once by `POST /api/v2/auth/key` is not persistence evidence
  when pfSense logged `Save config permission denied`;
- seeing a persisted key record does not recover its plaintext value. If the
  deployed plaintext produces HTTP `401`, rotate it;
- `api-v2-auth-key-post` is a **temporary rotation privilege** and must not
  remain in the steady-state role after a successful rotation.

The helper models the two explicit states.

Prepare one identity for rotation:

```bash
bash scripts/pfsense/diagnose-recover.sh --prepare-key-rotation posture
# or:
bash scripts/pfsense/diagnose-recover.sh --prepare-key-rotation security
```

This operation keeps only the role-specific GET privilege(s), removes
`User - Config: Deny Config Write`, and grants
`api-v2-auth-key-post`. It does **not** create a key or print a secret.

Create the key with the selected service user's own Basic credentials. For the
security identity:

```bash
curl -ksS \
  --user fastapi_security \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -X POST \
  'https://172.17.0.1:10443/api/v2/auth/key' \
  -d '{
    "length_bytes": 24,
    "hash_algo": "sha256",
    "descr": "FastAPI security observer"
  }'
```

Do not paste the response into tickets, chat or logs: `data.key` is the
one-time plaintext secret. Store it in the appropriate runtime secret source,
then confirm that the new key is visible in **System → REST API → Keys**.

Finalize the identity:

```bash
bash scripts/pfsense/diagnose-recover.sh --finalize-key-rotation security
```

Finalization refuses to proceed when pfSense has zero persisted keys for the
selected user. On success it removes `api-v2-auth-key-post` and restores
`user-config-readonly`.

Then verify the steady state again:

```bash
bash scripts/pfsense/diagnose-recover.sh --check-identities
```

Finally run the KeyAuth matrix only with the new plaintext values. The expected
least-privilege contract is:

- posture GET endpoints: HTTP `200`;
- posture `diagnostics/table?id=snort2c`: HTTP `403`;
- security `diagnostics/table?id=snort2c`: HTTP `200`;
- security `status/services`: HTTP `403`.

If a rotation temporarily leaves more than one persisted key, validate the new
key first and then remove the superseded key explicitly from the REST API Keys
page. The helpers never guess which persisted key should be deleted.

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
