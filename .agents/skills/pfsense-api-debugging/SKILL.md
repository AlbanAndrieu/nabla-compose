---
name: pfsense-api-debugging
description: Diagnose pfSense networking, HAProxy, firewall paths and REST API v2 access safely, with pfSense csh/tcsh shell conventions.
---

# pfSense API and network debugging

Use this skill for pfSense routing, firewall, NAT, HAProxy, interface, TLS and REST API v2 diagnostics in the Nabla homelab.

Prefer read-only evidence first. Do not change firewall/NAT/HAProxy/API configuration unless the task explicitly requests a mutation and the intended exposure policy is understood.

## Known Nabla topology

Current pfSense shell/runtime facts validated on pfSense 26.07-RELEASE:

- shell: `csh`/`tcsh` semantics, not Bourne/bash assignment syntax;
- WAN real interface: `mvneta0.4090`;
- LAN real interface: `mvneta0.4091`;
- pfSense API/admin HTTPS endpoint currently consumed by FastAPI Sample: `https://home.albandrieu.com:10443`;
- TrueNAS public HTTPS/API listener: `https://truenas.albandrieu.com:7000` through pfSense HAProxy;
- TrueNAS backend: `172.17.0.24:7000`.

Treat the interface names as observed facts, not immutable constants. Re-resolve them before packet capture after upgrades, VLAN changes or interface reassignment.

## pfSense shell: csh/tcsh rules

Do **not** use Bourne syntax such as:

```sh
WAN_IF="$(command)"
```

On pfSense `csh`/`tcsh`, this can fail with:

```text
Illegal variable name.
```

Use backticks with `set` for shell variables:

```csh
set WAN_IF = `php -r 'require_once("/etc/inc/interfaces.inc"); echo get_real_interface("wan");'`
set LAN_IF = `php -r 'require_once("/etc/inc/interfaces.inc"); echo get_real_interface("lan");'`

echo "WAN=$WAN_IF"
echo "LAN=$LAN_IF"
```

Or resolve both without storing them:

```csh
php -r 'require_once("/etc/inc/interfaces.inc"); echo "WAN=", get_real_interface("wan"), PHP_EOL, "LAN=", get_real_interface("lan"), PHP_EOL;'
```

Important: every `php -r` invocation is a new PHP process. Load `interfaces.inc` and call `get_real_interface()` in the **same invocation**. Separate commands do not share loaded functions.

For environment variables in `csh`/`tcsh`, use `setenv`:

```csh
setenv PFSENSE_API_URL "https://home.albandrieu.com:10443"
setenv PFSENSE_API_KEY "<redacted>"
```

On a bash/zsh workstation use normal `export` instead.

## REST API v2 authentication

FastAPI Sample currently uses:

- base URL: `PFSENSE_API_URL`;
- API key: `PFSENSE_API_KEY`;
- TLS verification: `PFSENSE_API_VERIFY_SSL`, default `true`;
- authentication header: `X-API-Key`;
- JSON response header: `Accept: application/json`.

Never print, echo, commit or paste the actual API key into diagnostics.

Read-only connectivity check:

```csh
curl -fsS \
  -H "X-API-Key: $PFSENSE_API_KEY" \
  -H 'Accept: application/json' \
  "$PFSENSE_API_URL/api/v2/status/system" | jq .
```

If the certificate is expected to be publicly trusted, keep verification enabled. Use `-k` only as a temporary diagnostic to distinguish CA/hostname failures from transport/API failures; never make insecure verification the permanent fix.

## Validated read-only API endpoints

These endpoints have been observed returning HTTP 200 from the current pfSense API v2 deployment:

```text
GET /api/v2/status/system
GET /api/v2/status/services
GET /api/v2/services/dns_resolver/settings
GET /api/v2/system/dns
```

Examples:

```csh
foreach path ( \
  /api/v2/status/system \
  /api/v2/status/services \
  /api/v2/services/dns_resolver/settings \
  /api/v2/system/dns \
)
  echo "=== $path ==="
  curl -fsS \
    -H "X-API-Key: $PFSENSE_API_KEY" \
    -H 'Accept: application/json' \
    "$PFSENSE_API_URL$path" | jq .
end
```

For API mutations, first inspect the API's current schema/documentation and read the existing object. Never infer a POST/PATCH/DELETE payload from a GET response alone. Preserve a rollback path and re-read the resource after the change.

## FastAPI Sample observer

The external observer can be checked from any workstation:

```bash
curl -fsS https://fastapi-sample.fastapicloud.dev/healthz | jq '.checks.pfsense'
curl -fsS https://fastapi-sample.fastapicloud.dev/api/homelab/health | jq .
```

Interpret external reachability separately from security policy. A successful pfSense API response from an external PaaS proves reachability; it does **not** by itself prove that exposing the administration API to that source is intended.

## HAProxy configuration inspection

HAProxy's generated runtime configuration is typically available at:

```text
/var/etc/haproxy/haproxy.cfg
```

Read it before guessing frontend/backend behavior:

```csh
sed -n '1,260p' /var/etc/haproxy/haproxy.cfg
```

Find frontends/backends and the TrueNAS listener:

```csh
grep -nE '^(frontend|backend)|7000|truenas|freenas' /var/etc/haproxy/haproxy.cfg
```

Find configured HAProxy log destinations:

```csh
grep -nE '^[[:space:]]*log[[:space:]]' /var/etc/haproxy/haproxy.cfg
```

HAProxy normally sends logs to syslog; it does not inherently write `/var/log/haproxy.log`. An empty file does not prove HAProxy is not handling traffic. Inspect the configured syslog destination before assuming a log path.

Useful syslog discovery:

```csh
grep -RniE 'haproxy|local[0-7]' \
  /etc/syslog.conf /var/etc/syslog.conf /var/etc/syslog.d 2>/dev/null
```

## TrueNAS :7000 path diagnostics

Current intended path:

```text
Internet/client
  -> pfSense WAN :7000
  -> HAProxy frontend
  -> TLS re-encryption
  -> TrueNAS 172.17.0.24:7000
```

A basic HTTPS test from outside pfSense:

```bash
curl -v --http1.1 --max-time 15 https://truenas.albandrieu.com:7000/
```

A WebSocket upgrade returning `101 Switching Protocols` proves the HTTP upgrade reached a WebSocket-capable backend. A later `curl --max-time` timeout is expected if no WebSocket JSON-RPC frames are sent; it is not by itself an HAProxy tunnel failure.

Do not manually inject HAProxy `Upgrade` headers merely because WebSockets are used. HAProxy HTTP mode can proxy a valid WebSocket upgrade natively; first prove an actual upgrade failure.

## Packet capture

Always resolve the real interfaces first:

```csh
set WAN_IF = `php -r 'require_once("/etc/inc/interfaces.inc"); echo get_real_interface("wan");'`
set LAN_IF = `php -r 'require_once("/etc/inc/interfaces.inc"); echo get_real_interface("lan");'`
```

Capture the public listener on WAN:

```csh
tcpdump -ni "$WAN_IF" tcp port 7000
```

Capture HAProxy-to-TrueNAS traffic on LAN:

```csh
tcpdump -ni "$LAN_IF" host 172.17.0.24 and tcp port 7000
```

For a specific external source, narrow the capture:

```csh
tcpdump -ni "$WAN_IF" host <SOURCE_IP> and tcp port 7000
```

Compare WAN and LAN captures to answer three different questions:

1. did the client reach pfSense WAN?;
2. did HAProxy initiate the backend connection to TrueNAS?;
3. which side sent FIN/RST or stopped responding?

Do not capture broadly for long periods when a host/port filter can answer the question.

## Firewall/NAT state inspection

Safe read-only commands include:

```csh
pfctl -sr
pfctl -sn
pfctl -ss | grep -E '(:7000|172\.17\.0\.24)'
```

For large rulesets, filter the output rather than pasting the entire ruleset into an issue or chat. Preserve rule labels and IDs when available so a UI rule can be mapped back to runtime behavior.

## Diagnostic sequence

When a public service behind pfSense/HAProxy fails, use this order:

1. resolve DNS from the actual client context;
2. test TCP/TLS/HTTP from that same context;
3. inspect the HAProxy frontend/backend generated config;
4. inspect HAProxy/syslog evidence;
5. resolve WAN/LAN real interfaces;
6. capture WAN and LAN simultaneously if the fault domain is still unclear;
7. inspect firewall/NAT states and rule logs;
8. test the backend directly from the LAN while preserving hostname/SNI where relevant;
9. only then change firewall, NAT, HAProxy or TLS configuration.

A LAN hairpin/NAT-reflection success does not prove a true Internet-to-WAN path. For external failures, test from a genuinely external source as well.

## TLS interpretation

TLS certificates authenticate hostnames, not TCP ports. For example, the certificate name is checked against:

```text
truenas.albandrieu.com
```

not against:

```text
truenas.albandrieu.com:7000
```

However, omitting `:7000` changes the destination listener from TCP 7000 to the HTTPS default TCP 443. Different listeners can present different certificates, which can create an apparent hostname mismatch even though the real bug is the wrong target port.

## Safety rules

- Default to read-only API calls and inspection commands.
- Never expose or log `PFSENSE_API_KEY`.
- Never commit API keys, passwords, certificates/private keys or cookies.
- Do not disable TLS verification as a permanent workaround.
- Do not expose the pfSense admin/API listener merely to simplify monitoring.
- Do not edit `/conf/config.xml` directly for ordinary configuration changes; prefer supported UI/API mechanisms and preserve rollback.
- Do not install or alter FreeBSD/pfSense packages unless the task explicitly requires it and compatibility is verified.
- Treat firewall/NAT/HAProxy mutations as potentially connectivity-breaking; inspect current state before writing.
- After every mutation, re-run the read-only checks that motivated the change.

## Evidence to capture in a bug report

Prefer a compact bundle:

```text
pfSense version
resolved WAN/LAN interface names
client source/network context (LAN hairpin vs true external)
target hostname:port
HTTP/TLS result
relevant HAProxy frontend/backend excerpts
relevant firewall/NAT rule labels
WAN/LAN tcpdump outcome (not full unrelated captures)
REST endpoint + HTTP status, with credentials redacted
```

This is normally enough to localize the failure without exposing sensitive configuration.
