# FastAPI Cloud -> pfSense / TrueNAS access

This document records the operational access model used by FastAPI Sample when it runs on FastAPI Cloud and needs to observe both TrueNAS and pfSense.

## Constraint

FastAPI Cloud must retain access to:

- `82.66.4.247:7000` — pfSense HAProxy -> TrueNAS HTTPS/API;
- `82.66.4.247:10443` — pfSense HTTPS REST API / administration listener.

The FastAPI Cloud deployment currently does not expose a user-controlled outbound tunnel or a user-controlled static egress gateway. Observed runtime source addresses have changed over time, including `52.1.10.241`, `54.164.107.133`, and `34.200.20.162`.

Therefore do not create a permanent firewall allowlist from one observed FastAPI Cloud address, and do not allow a whole AWS allocation as a substitute for workload identity.

Until FastAPI Cloud offers a controllable stable source identity, direct WAN reachability of `7000` and `10443` from the FastAPI Cloud runtime is an accepted, explicitly tracked security exception. Risk must instead be reduced with TLS verification, least-privilege API identities, REST API read-only mode, Snort/PF filtering, and independent negative reachability tests.

## Source-aware exposure policy

The desired policy is not a global `reachable=true` or `reachable=false` flag. It is source-aware:

| Probe origin | `7000/tcp` TrueNAS | `10443/tcp` pfSense | Expected result |
| --- | --- | --- | --- |
| FastAPI Cloud production runtime | reachable | reachable | allow |
| Approved office/VPN administration source | reachable if required | reachable | allow |
| Generic untrusted Internet vantage point | blocked | blocked | deny |

A successful probe from FastAPI Cloud proves only the positive path. It does not prove that the listener is restricted from the rest of the Internet. The negative policy must be tested from an independent, untrusted source.

If an office source has a stable public IPv4 or a controlled DDNS FQDN, use a named pfSense alias for that source. A FQDN alias resolves to IP addresses; it is not cryptographic workload identity and should not be used for cloud hostnames whose egress addresses rotate independently of the hostname.

## Dedicated pfSense API identities

FastAPI Sample uses two different pfSense API credentials. Both pfSense user objects must remain **enabled**. Do not check `This user cannot login`: pfREST validates that the API-key owner is an enabled user, so disabling the user also invalidates API-key authentication.

API keys themselves cannot be used for webConfigurator or SSH authentication. Harden the service users by keeping them out of the `admins` group and withholding `WebCfg - All pages`, `page-all`, shell access and every unnecessary privilege.

The production FastAPI Cloud environment was migrated to the split identities on 2026-09-02. The generic `PFSENSE_API_KEY` has been removed and must not be reintroduced as the normal configuration.

### Posture identity

pfSense user:

```text
fastapi-pfsense-posture
```

Purpose: read-only platform/DNS/service posture.

Required REST API privileges:

```text
REST API - /api/v2/system/version GET
REST API - /api/v2/system/dns GET
REST API - /api/v2/status/services GET
REST API - /api/v2/services/dns_resolver/settings GET
```

The corresponding FastAPI Cloud environment is:

```text
PFSENSE_API_URL=https://home.albandrieu.com:10443
PFSENSE_API_VERIFY_SSL=true

PFSENSE_POSTURE_API_KEY=<dedicated posture key>
PFSENSE_POSTURE_API_URL=https://home.albandrieu.com:10443
PFSENSE_POSTURE_API_VERIFY_SSL=true
```

`PFSENSE_POSTURE_API_URL` and `PFSENSE_POSTURE_API_VERIFY_SSL` are optional when they are identical to the shared `PFSENSE_API_URL` / `PFSENSE_API_VERIFY_SSL` transport settings.

Do not store the password or API key in this repository.

Validated behavior on 2026-09-02:

```text
GET /api/v2/system/version                       -> 200
GET /api/v2/system/dns                           -> 200
GET /api/v2/status/services                      -> 200
GET /api/v2/services/dns_resolver/settings       -> 200
GET /api/v2/diagnostics/table?id=snort2c         -> 403
```

The `403` on `snort2c` is intentional. It proves the posture identity does not have the security-observer privilege.

### Security/Snort identity

pfSense user:

```text
fastapi-pfsense-security
```

Purpose: read-only attribution of an observed FastAPI Cloud egress block to the `snort2c` PF table.

Its only required REST API privilege is:

```text
REST API - /api/v2/diagnostics/table GET
```

The target FastAPI Cloud environment is:

```text
PFSENSE_SECURITY_API_KEY=<dedicated snort2c key>
PFSENSE_SECURITY_PATH_MODE=shared_wan
```

The security observer reuses these shared transport values by default:

```text
PFSENSE_API_URL=https://home.albandrieu.com:10443
PFSENSE_API_VERIFY_SSL=true
```

It can be separated later with:

```text
PFSENSE_SECURITY_API_URL=https://home.albandrieu.com:10443
PFSENSE_SECURITY_API_VERIFY_SSL=true
```

FastAPI Sample uses this identity only to read:

```text
GET /api/v2/diagnostics/table?id=snort2c
```

No write privilege is required. FastAPI Sample still contains temporary migration/rollback compatibility for the historical generic key, but production intentionally no longer sets `PFSENSE_API_KEY`. Do not collapse the two dedicated identities back into one shared secret.

`PFSENSE_SECURITY_PATH_MODE=shared_wan` documents that the security observer reaches pfSense through the same WAN `:10443` path that Snort/PF may block. A transport failure on this path is a telemetry blind spot, not proof that Snort caused the failure.

## REST API read-only mode

Keep the pfSense REST API in global read-only mode during normal operation.

Creating an API key requires a temporary write operation:

```text
POST /api/v2/auth/key
```

When global read-only mode is enabled, pfSense correctly rejects that bootstrap request with `405 ENDPOINT_METHOD_NOT_ALLOWED_IN_READ_ONLY_MODE`.

Safe bootstrap sequence:

1. keep the target technical user limited to the intended API privileges;
2. temporarily disable global REST API read-only mode;
3. create the API key;
4. save the generated key in the target secret store / FastAPI Cloud environment;
5. immediately re-enable global REST API read-only mode;
6. remove any temporary API-key-creation privilege if one was granted;
7. validate all required GET endpoints and at least one forbidden endpoint.

Normal FastAPI Sample health and Snort telemetry require GET requests only, so global read-only mode is compatible with the target runtime design.

## Validation

For ad-hoc shell validation, use a temporary shell variable. `PFSENSE_POSTURE_KEY` below is intentionally **not** the FastAPI Cloud variable name; the application variable is `PFSENSE_POSTURE_API_KEY`.

```sh
export PFSENSE_POSTURE_KEY='<temporary local copy of posture key>'

for path in \
  /api/v2/system/version \
  /api/v2/system/dns \
  /api/v2/status/services \
  /api/v2/services/dns_resolver/settings
do
  curl --fail-with-body -sS \
    -o /dev/null \
    -w '%{http_code}\n' \
    -H "X-API-Key: ${PFSENSE_POSTURE_KEY}" \
    "https://home.albandrieu.com:10443${path}"
done
```

Expected: four `200` responses.

Negative privilege validation:

```sh
curl -sS \
  -o /dev/null \
  -w '%{http_code}\n' \
  -H "X-API-Key: ${PFSENSE_POSTURE_KEY}" \
  'https://home.albandrieu.com:10443/api/v2/diagnostics/table?id=snort2c'
```

Expected: `403`.

Security identity validation:

```sh
export PFSENSE_SECURITY_KEY='<temporary local copy of security key>'

curl --fail-with-body -sS \
  -o /dev/null \
  -w '%{http_code}\n' \
  -H "X-API-Key: ${PFSENSE_SECURITY_KEY}" \
  'https://home.albandrieu.com:10443/api/v2/diagnostics/table?id=snort2c'
```

Expected: `200`.

Then remove the temporary shell values:

```sh
unset PFSENSE_POSTURE_KEY PFSENSE_SECURITY_KEY
```

Network-policy validation must use at least two vantage points:

1. approved FastAPI Cloud runtime: `7000` and `10443` must succeed;
2. independent untrusted Internet source: `7000` and `10443` must fail before authenticated application access.

An HTTP `401` or `403` from the independent untrusted source still proves the TCP/TLS listener is reachable. If the requirement is L3/L4 source restriction, the expected negative result is a connection timeout/drop/refusal before HTTP authorization.

## Secret handling

- never commit API keys, passwords, hashes, or exported pfSense configuration containing credentials;
- use separate keys for posture and Snort/PF telemetry;
- rotate any key that was pasted into chat, logs, tickets, shell history, or other uncontrolled locations;
- keep TLS verification enabled for both identities;
- prefer a future stable egress/tunnel/private-path capability if FastAPI Cloud makes one available, but do not weaken the current runtime simply to emulate that feature.
