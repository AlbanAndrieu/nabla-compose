# Public attack surface: Nuclei, anti-spoofing, TCP and TLS

## Scope, provenance, limitations

- HTTP Nuclei inventory: config/security/external-attack-surface.txt.
- Email-apex inventory: config/security/public-mail-domains.json.
- Owned domains currently reviewed: albandrieu.com, albanandrieu.com,
  bababou.com. Enumerating their apex does not prove every outbound mail
  subdomain was checked. Do not add third-party fastapicloud.dev.
- Outside-in WAN: 82.66.4.247, explicitly scoped, not the internal LAN.
- No scans, remediation or permission changes are run from a PR.
- CODED is not SCANNED. A missing report or timeout is UNVERIFIED.

Nuclei (weekly/manual) is limited to HTTP panel/exposure/misconfiguration
templates. The GitHub artifact is now projected to hostname, severity,
template ID and matcher only. Raw curl commands, extracted environment
values, HTTP response content and URL paths must not enter a public artifact.
If projection rejects a finding, the upload fails closed.

The public DNS job runs read-only queries for SPF, DMARC (p, sp and pct),
configured DKIM selectors, MTA-STS DNS signal and SMTP TLS-RPT. Actual
message alignment, DKIM signing by each provider, and the MTA-STS HTTPS
policy are different tests. Missing DKIM selectors = UNVERIFIED, never PASS.
Before recommending p=reject or sp=reject, inventory legitimate sending
providers and review aggregate DMARC reports. For no-mail domains consider
null MX, SPF -all and DMARC reject after classification. No DNS changes.

The TCP/TLS job is intentionally manual because pfSense Netgate 1100
experienced severe eMMC and boot instability on 17 November 2026.
It scans only 36 common TCP ports of the reviewed WAN IP with Nmap
TCP connect and a low rate: no full 1-65535 scan, UDP, scripts,
aggressive probes or credentials. TLS uses a verified Python/OpenSSL
handshake on five reviewed public SNI names (443 and TrueNAS 7000).
Those checks do NOT constitute a complete cipher-suite evaluation.
A CDN or Access-protected endpoint may be measured instead of the origin.

## Next security probes: check metadata, not secret contents

Use Nuclei's bounded exposure/config templates for /.env, /.git/config,
terraform.tfstate, terraform.tfstate.backup, /metrics, /api,
/openapi.json, /swagger-ui/, /wp-login.php, /wp-admin/,
and /server-status. Before treating an HTTP 200 as a finding, test an
impossible path and distinguish the login portal / SPA fallback.
401/403 and Cloudflare Access redirects do not prove origin isolation.
Do not put response bodies, authenticated URLs, extracted .env or
Terraform state data into GitHub artifacts or public DefectDojo API calls.

## Deeper TLS and full port scan from an approved external vantage

With a separately installed, reviewed testssl.sh binary:

    ./testssl.sh --warnings batch --jsonfile manager-tls.json manager.albandrieu.com:443
    ./testssl.sh --warnings batch --jsonfile truenas-tls.json truenas.albandrieu.com:7000

Qualys SSL Labs: https://www.ssllabs.com/ssltest/
Use the public hostname's standard HTTPS port, with the private-results
option where available; it must not be assumed to assess :7000.
Keep raw reports encrypted/private with short retention.

After replacing/stabilizing Netgate, an authorized outside-in full
inventory can use:

    nmap -sT -Pn -n --max-retries 1 --max-rate 10 -p- \
      --host-timeout 2h -oX full-wan-ports.xml 82.66.4.247

The 36-port scan is an initial inventory, not proof that the other
65,499 TCP ports are closed. Compare with pfSense/NAT/HAProxy baselines.

## OSS options

Prowler: AWS/Azure/GCP/Kubernetes CSPM, most appropriate Wiz-like OSS pilot.
Kubescape: Talos/Kubernetes-specific posture and misconfiguration.
OpenEASD or reNgine: outside-in EASM orchestration.
Greenbone Community Edition: vulnerability scanning (not a full CNAPP).
Amass, Subfinder, httpx, Naabu, Nmap, Nuclei, testssl.sh and
Global Cyber Alliance Domain Security Scanner / checkdmarc supply the
individual discovery, DNS, TLS and email checks. Nothing is installed
or deployed automatically by this runbook.

## Manual bounded disclosure-path proof

The workflow_dispatch TCP/TLS job also performs an unauthenticated HTTPS
HEAD-only probe on the reviewed virtual hosts for .env, .git, Terraform
state, Prometheus /metrics, OpenAPI, WordPress login and common admin paths.
It never sends a GET, follows redirects, reads bodies or uses credentials.
A negative-control missing path helps distinguish SPA fallback 200 from a
path needing review. Results are classifications, not proof of leaked secrets.

## Manual workflow dispatch scope

Choose `scan_profile=mail` (the safe default), `nuclei`, `network`, or
`all`. The schedule executes only mail and Nuclei; no TCP/port scan is
scheduled. Choosing `network` avoids Nuclei's HTTP workload while the
Netgate remains unstable. A combined `all` run requires deliberate operator
selection and is not the safe default.
