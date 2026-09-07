---
name: pfsense-api-debugging
description: >-
  Diagnose pfSense networking, HAProxy, firewall/NAT, Snort, pfBlockerNG,
  Unbound/Kea, pflow/IPFIX and REST API v2 safely, with copy/paste-safe
  pfSense csh/tcsh shell conventions.
---

# pfSense API and network debugging

## Cross-chat portability and trigger

This skill is the self-contained pfSense operational contract shared by the
Nabla repositories. Load it whenever a task touches pfSense/Netgate, PF,
HAProxy, Snort, pfBlockerNG, Unbound, Kea, pflow/IPFIX, softflowd, the pfSense
REST API, or an Internet-to-homelab path that traverses pfSense.

Do not rely on facts remembered from another chat. Separate:

- **policy/invariants** in this skill, which are reusable;
- **observed runtime facts**, which can become stale after an upgrade, reboot,
  package change, VLAN change, DHCP event, or service restart.

Revalidate volatile facts with the narrowest read-only command before acting.
Examples include current PIDs, RSS, free memory, interface names, pflow
exporters, firewall tables, service status, WAN source addresses and generated
package configuration.

When this file changes in one Nabla repository, keep the corresponding
`.agents/skills/pfsense-api-debugging/SKILL.md` in the other repository
semantically aligned. The portable operational sections should remain
byte-for-byte identical whenever practical.

Use this skill for pfSense routing, firewall, NAT, HAProxy, interface, TLS, Snort/PF attribution and REST API v2 diagnostics in the Nabla homelab.

Prefer read-only evidence first. Do not change firewall/NAT/HAProxy/Snort/API configuration unless the task explicitly requests a mutation and the intended exposure policy is understood.

## Known Nabla topology

Current pfSense shell/runtime facts validated on pfSense 26.07-RELEASE:

- shell: `csh`/`tcsh` semantics, not Bourne/bash assignment syntax;
- WAN real interface: `mvneta0.4090`;
- LAN real interface: `mvneta0.4091`;
- pfSense API/admin HTTPS endpoint currently consumed by FastAPI Sample: `https://home.albandrieu.com:10443`;
- TrueNAS public HTTPS/API listener: `https://truenas.albandrieu.com:7000` through pfSense HAProxy;
- TrueNAS backend: `172.17.0.24:7000`;
- public TrueNAS path: `FastAPI Cloud -> pfSense WAN:7000 -> HAProxy TLS termination -> TLS re-encryption -> TrueNAS:7000`.

Treat interface names and public source IPs as observed facts, not immutable constants. Re-resolve interfaces after upgrades/VLAN changes and re-observe FastAPI Cloud egress instead of treating a previously seen address as a stable contract.

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
setenv PFSENSE_POSTURE_API_KEY "<redacted posture key>"
setenv PFSENSE_SECURITY_API_KEY "<redacted security key>"
```

On a bash/zsh workstation use normal `export` instead. Never echo the actual key values.

### Copy/paste-safe command contract

The interactive pfSense shell is `tcsh`/csh. Commands sent to an operator in
chat must be safe to paste into that shell.

Rules:

- Prefer **one command per code block**.
- Prefer **single-line commands** for loops, compound tests and pipelines.
- Do not send a multiline single-quoted `/bin/sh -c '...'` body unless the user
  explicitly asks for a script file.
- Avoid trailing `\` continuations in operator-facing commands when an
  equivalent one-liner is reasonable; pasted newlines and duplicated fragments
  are a recurring failure mode.
- When Bourne/POSIX syntax is useful, run it explicitly through
  `/bin/sh -c '...'`.
- Remember that unmatched globs in `tcsh` fail with `No match`; use
  `/bin/sh -c` plus `2>/dev/null` for optional paths.
- Never concatenate several independent commands into one pasted block when a
  typo could transform a pathname (for example `/conf/config.xmlsed`).
- For read-only discovery, use bounded output such as `tail`, targeted
  `grep`, and filtered `tcpdump` rather than dumping entire logs/rulesets.

Portable loop example for pfBlockerNG feed sizing:

```csh
/bin/sh -c 'for f in /var/db/pfblockerng/dnsblorig/*; do [ -f "$f" ] || continue; lines=$(wc -l < "$f"); bytes=$(stat -f %z "$f"); printf "%10d lines %10d bytes  %s\n" "$lines" "$bytes" "$(basename "$f")"; done'
```

Equivalent processed-list inventory:

```csh
/bin/sh -c 'for f in /var/db/pfblockerng/dnsbl/*; do [ -f "$f" ] || continue; lines=$(wc -l < "$f"); bytes=$(stat -f %z "$f"); printf "%10d lines %10d bytes  %s\n" "$lines" "$bytes" "$(basename "$f")"; done'
```

## Netgate 1100 memory and service-safety contract

The current edge appliance is a memory-constrained Netgate 1100 with roughly
1 GiB of RAM and no swap. Treat the firewall as a critical appliance first and
an analytics host second.

Before restarting several services or running a heavy pfBlockerNG reload,
capture evidence first:

```csh
date
```

```csh
dmesg | egrep -i 'killed|failed to reclaim|waited too long|out of swap' | tail -80
```

```csh
ps axo pid,rss,vsz,pcpu,pmem,command | sort -nr -k2 | head -25
```

```csh
vmstat 2
```

Stop `vmstat` after a bounded sample. Do not interpret one successful daemon
restart as proof that the system is healthy if the kernel is still reclaiming
aggressively or killing processes.

Observed failure signatures that indicate global memory pressure include:

```text
was killed: failed to reclaim memory
was killed: a thread waited too long to allocate a page
out of swap
```

Service restoration priority after an OOM is normally:

1. PF/routing and DNS/DHCP prerequisites;
2. Unbound and Kea;
3. HAProxy and required security helpers;
4. Snort only after memory headroom is stable;
5. monitoring agents such as Zabbix;
6. optional analytics.

Do not start ntopng on this appliance. Keep legacy softflowd disabled when
native pflow is providing the required exports.

### Repository regression audit

When a workstation checkout of `nabla-compose` is available, prefer the
versioned audit over manually reconstructing the complete posture from chat
history:

```bash
scripts/pfsense/audit-posture.sh --ssh admin@172.17.0.1
```

Use `--json` for automation and `--strict` when warnings should fail a
scheduled check. The script emits the `nabla.pfsense.posture.v1` JSON schema.

A partial API-only view is available without SSH:

```bash
scripts/pfsense/audit-posture.sh --api https://fastapi-sample.fastapicloud.dev
```

Treat API-mode `SKIP` rows as an explicit capability boundary, not success.
The current FastAPI observer does not expose appliance-local DNSBL files,
`config.xml`, Unbound RSS, Snort generated configuration or `pflowctl`.

### Unbound and pfBlockerNG DNSBL

Current stable design uses pfBlockerNG DNSBL Python mode:

```text
dnsbl_mode = dnsbl_python
module-config: "python validator iterator"
python-script: pfb_unbound.py
```

Revalidate before relying on this:

```csh
grep -nEi '<dnsbl_mode>|<pfb_tld>|<regdhcp>|<regdhcpstatic>' /conf/config.xml
```

```csh
grep -nE 'module-config|python-script|msg-cache-size|rrset-cache-size' /var/unbound/unbound.conf
```

Do not assume a high Unbound RSS is caused by the native rrset/message caches.
Measure them:

```csh
unbound-control -c /var/unbound/unbound.conf stats_noreset | egrep '^mem\.'
```

The Python DNSBL data structures can dominate process RSS even when the source
text is much smaller on disk. A validated 2026-09-07 state with about 923k
DNSBL entries produced Unbound RSS above 300 MiB and was associated with
kernel OOM kills during reload/rebuild activity. Treat this as an observed
capacity warning, not as a universal hard threshold.

Before a Force Reload:

- keep PHP `memory_limit` at 128M unless a separately justified test requires
  a temporary change;
- do not use 256M/512M as a permanent workaround for oversized feeds;
- check current Unbound RSS and free memory;
- check for recent kernel OOM evidence;
- inventory feed sizes/line counts;
- reduce unnecessary feeds before forcing a rebuild;
- temporarily keep Snort stopped when memory headroom is marginal;
- verify the final pfBlockerNG completion marker and absence of new OOM kills.

The UT1 `adult` category was disabled after an oversized source triggered PHP
memory exhaustion. `Talos_BL_v4` is a Cisco Talos threat-intelligence feed;
it is unrelated to Sidero Labs Talos Linux/Kubernetes. A failed/403 Cisco Talos
feed can be disabled without affecting the Talos Kubernetes cluster.

Prefer disabling a broken or disproportionate **source/category** over
disabling an entire provider when useful categories remain.

Do not estimate memory savings by subtracting one processed feed's current line
count. pfBlockerNG deduplicates across feeds, so disabling one source can cause
domains previously attributed to it to reappear under another source. Also do
not sum every file in `dnsblorig`: helper artifacts such as `.md5.raw` are
not independent active domain sets.

A validated 2026-09-07 example illustrates this: `UT1_malware` contributed
about 672k of 923k processed entries, while `UT1_phishing.orig` contained
about 688k source lines but only about 621 processed entries because of heavy
overlap. Re-measure the **final processed total after each controlled feed
change** instead of predicting the new total from subtraction alone.

### Snort memory posture

Run only the required WAN Snort instance on the Netgate 1100. The WAN HTTP
Inspect memcap was reduced from roughly 144 MiB to 32 MiB; validate the
generated configuration rather than hand-editing it.

```csh
grep -n 'http_inspect: global' -A8 /usr/local/etc/snort/snort_56408_mvneta0.4090/snort.conf
```

A configured preprocessor memcap is a ceiling, not proof of resident usage.
Measure actual RSS with `ps`.

If Unbound/pfBlockerNG is under memory pressure, stopping Snort temporarily is
an acceptable diagnostic/headroom measure. Restore Snort only after
`vmstat`, process RSS and kernel logs show stable headroom.

### Kea and Zabbix after memory incidents

Do not trust a stale UI status alone. Confirm process state and recent logs.

Kea:

```csh
pgrep -af kea-dhcp4
```

```csh
tail -80 /var/log/dhcpd.log
```

Service Watchdog may restart Kea after a memory incident, so a later running
PID does not disprove an earlier outage.

Zabbix is monitoring, not a routing/DNS prerequisite. If memory is constrained,
leave it stopped until core services are stable:

```csh
ps axww | grep '[z]abbix'
```

```csh
/bin/sh -c 'ls -l /var/run/zabbix-agent/zabbix_agentd.pid 2>/dev/null'
```

### Native pflow/IPFIX offload

Prefer pfSense Plus native Packet Flow Data / pflow over running ntopng or
softflowd locally for flow analytics.

Read-only runtime inventory:

```csh
pflowctl -v -l
```

The validated dual-export design is:

```text
pflow0: IPFIX domain 1, 172.17.0.1 -> 172.17.0.24:2055 (TrueNAS/Akvorado)
pflow1: IPFIX domain 2, WAN -> 162.159.65.1:2055 (Cloudflare Network Flow)
```

Revalidate these values because exporter IDs/source addresses can change.

WAN proof for Cloudflare:

```csh
tcpdump -ni mvneta0.4090 -c 20 'udp and dst host 162.159.65.1 and dst port 2055'
```

TrueNAS-side proof uses the actual host interface selected by its route to
pfSense; in the current topology this has been `br0`:

```bash
sudo tcpdump -ni br0 -c 30 'udp dst port 2055 and src host 172.17.0.1'
```

Do not run softflowd and pflow for the same destination without an explicit
migration/comparison reason.

## REST API v2 authentication

FastAPI Sample production uses two dedicated identities over shared transport defaults:

- base URL: `PFSENSE_API_URL`;
- posture key: `PFSENSE_POSTURE_API_KEY`;
- security/Snort key: `PFSENSE_SECURITY_API_KEY`;
- TLS verification: `PFSENSE_API_VERIFY_SSL`, default `true`;
- optional per-identity URL/TLS overrides: `PFSENSE_POSTURE_API_URL`, `PFSENSE_POSTURE_API_VERIFY_SSL`, `PFSENSE_SECURITY_API_URL`, `PFSENSE_SECURITY_API_VERIFY_SSL`;
- authentication header: `X-API-Key`;
- JSON response header: `Accept: application/json`.

The historical generic `PFSENSE_API_KEY` was removed from FastAPI Cloud on 2026-09-02 after both dedicated identities were validated. FastAPI Sample may temporarily retain code-level migration fallback, but do not recommend restoring the generic shared key or merging the two privilege sets.

Never print, echo, commit or paste either dedicated API key into diagnostics.

### Posture/liveness identity

Use the posture key for the lightweight liveness endpoint:

```csh
curl -fsS \
  -H "X-API-Key: $PFSENSE_POSTURE_API_KEY" \
  -H 'Accept: application/json' \
  "$PFSENSE_API_URL/api/v2/system/version" | jq .
```

Do **not** use `/api/v2/status/system` as the synchronous FastAPI liveness gate. It collects live platform, BIOS, temperature, CPU/load, memory, swap and filesystem information and can exceed a short health timeout. Use it only for on-demand detailed diagnosis.

Validated posture endpoints:

```text
GET /api/v2/system/version
GET /api/v2/status/services
GET /api/v2/services/dns_resolver/settings
GET /api/v2/system/dns
```

Example:

```csh
foreach path ( \
  /api/v2/system/version \
  /api/v2/status/services \
  /api/v2/services/dns_resolver/settings \
  /api/v2/system/dns \
)
  echo "=== $path ==="
  curl -fsS \
    -H "X-API-Key: $PFSENSE_POSTURE_API_KEY" \
    -H 'Accept: application/json' \
    "$PFSENSE_API_URL$path" | jq .
end
```

The posture account should receive `403` for `GET /api/v2/diagnostics/table?id=snort2c`; that negative test proves privilege separation.

### Security/Snort identity

The security identity should have only the GET privilege required for:

```text
GET /api/v2/diagnostics/table?id=snort2c
```

Read-only check:

```csh
curl -fsS \
  -H "X-API-Key: $PFSENSE_SECURITY_API_KEY" \
  -H 'Accept: application/json' \
  "$PFSENSE_API_URL/api/v2/diagnostics/table?id=snort2c" | jq .
```

Do not grant or use DELETE/POST/PATCH/PUT for runtime monitoring. Keep pfSense REST API global read-only mode enabled during normal operation.

If the certificate is expected to be publicly trusted, keep verification enabled. Use `-k` only as a temporary diagnostic to distinguish CA/hostname failures from transport/API failures; never make insecure verification the permanent fix.

For API mutations explicitly requested by the user, first inspect the API's current schema/documentation and read the existing object. Never infer a POST/PATCH/DELETE payload from a GET response alone. Preserve a rollback path and re-read the resource after the change.

## FastAPI Sample observer

The external observer can be checked from any workstation:

```bash
curl -fsS https://fastapi-sample.fastapicloud.dev/healthz | jq '.checks.pfsense'
curl -fsS https://fastapi-sample.fastapicloud.dev/api/homelab/health \
  | jq '.pfsense.dns | {configured, reachable, policy_state, error_stage, ingress_block, security_filters}'
curl -fsS https://fastapi-sample.fastapicloud.dev/api/homelab/status \
  | jq '.providerCredentials | {pfsense, pfsense_security}'
```

Interpret external reachability separately from security policy. The current contract is source-aware:

- FastAPI Cloud production is expected to reach `7000` and `10443`;
- approved administration sources may reach them as documented;
- generic untrusted Internet origins must be denied.

A successful FastAPI Cloud probe proves only the approved positive path. It does not prove that unrelated Internet sources are blocked.

## Snort / PF attribution on WAN :7000

A controlled 2026-09-02 A/B test proved this failure chain:

```text
TLS traffic on WAN :7000 incorrectly classified by HTTP Inspect
  -> http_inspect 120:3 / 120:18 alerts
  -> Block Offenders
  -> FastAPI Cloud source inserted into snort2c
  -> PF quick block + Kill States
  -> repeated inbound SYN without SYN,ACK
  -> HAProxy/TLS/TrueNAS never reached
```

The public `:7000` hop carries TLS **before** HAProxy termination. Do not configure TCP 7000 as a WAN `http_inspect_server` clear-text HTTP port. The remediation target is to remove `7000` from WAN HTTP Inspect and, if appropriate for the deployed package, classify it under the SSL/TLS preprocessor instead.

Do not globally suppress all `120:*` events to hide the symptom and do not add rotating FastAPI Cloud/AWS egress addresses to a permanent Snort Pass List.

Direct block evidence:

```csh
pfctl -t snort2c -T show
```

For one observed source:

```csh
pfctl -t snort2c -T test <SOURCE_IP>
```

`1/1 addresses match` proves membership in `snort2c`; `0/1` means that exact IP is not currently in the table. A running Snort service alone is not proof that Snort blocked a request.

When isolating an intermittent failure, correlate:

1. current source IP on WAN capture;
2. `snort2c` membership;
3. matching Snort alert/SID;
4. PF log/rule evidence;
5. TCP handshake outcome.

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
  -> HAProxy frontend / public TLS termination
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
tcpdump -nni "$WAN_IF" 'tcp port 7000'
```

Capture HAProxy-to-TrueNAS traffic on LAN:

```csh
tcpdump -nni "$LAN_IF" 'host 172.17.0.24 and tcp port 7000'
```

For a specific external source, narrow the capture:

```csh
tcpdump -nni "$WAN_IF" "host <SOURCE_IP> and tcp port 7000"
```

Compare WAN and LAN captures to answer three different questions:

1. did the client reach pfSense WAN?;
2. did HAProxy initiate the backend connection to TrueNAS?;
3. which side sent FIN/RST or stopped responding?

Interpretation:

- `SYN -> SYN,ACK -> ACK` means TCP established and TLS may start;
- repeated inbound SYN with no SYN,ACK/RST usually means a silent filter/drop before TLS;
- RST is an explicit reject/reset;
- a completed handshake followed by failure moves the fault domain toward TLS/HAProxy/backend/application.

Do not capture broadly for long periods when a host/port filter can answer the question.

## Firewall/NAT state inspection

Safe read-only commands include:

```csh
pfctl -sr
pfctl -sn
pfctl -ss | grep -E '(:7000|:10443|172\.17\.0\.24)'
pfctl -sr -vv | grep -B4 -A6 snort2c
```

For large rulesets, filter the output rather than pasting the entire ruleset into an issue or chat. Preserve rule labels and IDs when available so a UI rule can be mapped back to runtime behavior.

The broad WAN Easy Rule remains P0 security debt. Do not remove or rewrite it while isolating another failure unless that firewall change is the explicit task; changing several security layers at once destroys causality.

## Diagnostic sequence

When a public service behind pfSense/HAProxy fails, use this order:

1. resolve DNS from the actual client context;
2. identify the actual current client/source IP when cloud egress can rotate;
3. test TCP/TLS/HTTP from that same context;
4. inspect `snort2c` and relevant Snort/PF evidence before blaming HAProxy;
5. inspect the HAProxy frontend/backend generated config and runtime backend status;
6. inspect HAProxy/syslog evidence;
7. resolve WAN/LAN real interfaces;
8. capture WAN and LAN simultaneously if the fault domain is still unclear;
9. inspect firewall/NAT states and rule logs;
10. test the backend directly from the LAN while preserving hostname/SNI where relevant;
11. only then change firewall, NAT, HAProxy, Snort or TLS configuration.

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

On WAN `:7000`, Snort sees encrypted TLS records before HAProxy terminates TLS. Do not interpret HTTP Inspect anomalies on that ciphertext as evidence that the TrueNAS application generated malformed clear-text HTTP.

## Safety rules

- Default to read-only API calls and inspection commands.
- Never expose or log `PFSENSE_POSTURE_API_KEY` or `PFSENSE_SECURITY_API_KEY`.
- Do not reintroduce the generic `PFSENSE_API_KEY` as production configuration.
- Never commit API keys, passwords, certificates/private keys or cookies.
- Do not disable TLS verification as a permanent workaround.
- Do not make `10443` generally public merely to simplify monitoring; it is a tracked `trusted_sources_only` exception and requires an independent negative Internet probe.
- Do not edit `/conf/config.xml` directly for ordinary configuration changes; prefer supported UI/API mechanisms and preserve rollback.
- Do not install or alter FreeBSD/pfSense packages unless the task explicitly requires it and compatibility is verified.
- Treat firewall/NAT/HAProxy/Snort mutations as potentially connectivity-breaking; inspect current state before writing.
- Never automatically mutate firewall aliases or Snort pass lists from observed FastAPI Cloud egress IPs.
- After every mutation, re-run the read-only checks that motivated the change.

## Evidence to capture in a bug report

Prefer a compact bundle:

```text
pfSense version
resolved WAN/LAN interface names
client source/network context and current source IP
target hostname:port
HTTP/TLS result
snort2c membership and matching alert/SID when relevant
relevant HAProxy frontend/backend excerpts
relevant firewall/NAT rule labels
WAN/LAN tcpdump outcome (not full unrelated captures)
REST endpoint + HTTP status, with credentials redacted
```

This is normally enough to localize the failure without exposing sensitive configuration.
