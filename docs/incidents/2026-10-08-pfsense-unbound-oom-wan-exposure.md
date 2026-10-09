# pfSense Unbound OOM and WAN WebConfigurator exposure — 2026-10-08

## Scope

This incident records the runtime evidence and mitigations for the 2026-10-08
Netgate 1100 memory/DNS failures and the concurrent exposure of the pfSense
WebConfigurator/API listener on TCP/10443.

Current policy and remaining actions stay in
[`pfsense-wan-exposure-roadmap.md`](../pfsense-wan-exposure-roadmap.md),
[`pfsense-php-fpm-hardening.md`](../pfsense-php-fpm-hardening.md) and
[`roadmap.md`](../roadmap.md).

## Proven kernel memory failures

FreeBSD recorded repeated global allocation/reclaim failures on 2026-10-08:

```text
02:10:07 php      killed: failed to reclaim memory
02:10:07 unbound  killed: failed to reclaim memory
02:10:07 netstat  killed: failed to reclaim memory

11:03:23 netstat  killed: failed to reclaim memory
11:03:28 unbound  killed: failed to reclaim memory

19:00:59 php_pfb   killed: a thread waited too long to allocate a page
```

This proves the resolver outages were caused by appliance-wide memory pressure,
not by a native Unbound cache crash alone.

After the mitigations below, Unbound was again listening on IPv4/IPv6 TCP/UDP
53 and a local `drill @127.0.0.1 cloudflare.com` returned `NOERROR` in about
20 ms. A later `vmstat 2` sample was normally around 224–230 MiB free with
zero page-out, while still showing short-lived pressure dips; the appliance
therefore remained capacity-constrained rather than fully remediated.

## pfBlockerNG ASN retry loop

The appliance had no local ASN database:

```text
/usr/local/share/GeoIP/asn.mmdb  absent
/usr/local/share/GeoIP/asn.csv   absent
```

pfBlockerNG repeatedly logged IPinfo database download attempts while no
`asn_token` was configured. The persisted configuration was changed from
periodic ASN reporting to:

```xml
<asn_reporting>disabled</asn_reporting>
<asn_token></asn_token>
```

The last observed `Downloading [ IPinfo databases ]` line was at 19:00:14;
no later retry was observed after the UI change. Do not re-enable ASN reporting
without an intentional IPinfo/database contract.

## CrowdSec isolation

The CrowdSec engine had previously reached roughly 95 MiB RSS and high CPU while
`firewallservices/pf-scan-multi_ports` accumulated millions of failed event
send attempts. The engine was stopped as a controlled isolation test.

The firewall bouncer remained resident independently at low CPU/RSS. Do not
restart the CrowdSec engine until the event backpressure failure is understood
and a bounded CPU/RSS acceptance sample is available.

Upstream analysis narrows the meaning of the warning: `failed_sent` /
`attempts` are counters from CrowdSec's internal leaky-bucket event delivery,
not bouncer/LAPI network-send counters. The producer performs a non-blocking
send to the scenario bucket and immediately retries when the channel is not
ready. This busy-spin pattern was reported in
[crowdsecurity/crowdsec#1519](https://github.com/crowdsecurity/crowdsec/issues/1519)
and is still visible in the
[v1.8.1 `manager_run.go`](https://github.com/crowdsecurity/crowdsec/blob/v1.8.1/pkg/leakybucket/manager_run.go).
On this memory-constrained appliance, millions of attempts therefore provide a
credible direct explanation for the observed high CrowdSec CPU, while remaining
only contributor evidence for the system-wide OOM.

## WAN TCP/10443 exposure diagnosis

The pfSense WebConfigurator nginx listener was bound directly on `*:10443`.
There was no NAT/RDR rule for TCP/10443 and HAProxy did not reference 10443 as a
backend, so public authentication attempts were reaching the WebConfigurator
through PF policy rather than through HAProxy or port forwarding.

Before correction, PHP-FPM logged repeated Internet authentication attempts such
as `root`/`admin` from public scanner ranges including `77.91.71.0/24` and
`138.226.239.0/24`.

The legacy `ExternalOffice` host alias was also malformed for its intended
purpose. It contained:

```text
80.15.4.233
172.17.0.0
172.17.0.1
...
172.17.0.255
```

That is one public office address plus all 256 addresses of the LAN /24 expanded
individually, matching the observed PF table size `<ExternalOffice:257>`.

The alias was referenced by pfSense/TrueNAS access rules, so it could not be
deleted until those dependencies were repointed or removed.

## WAN correction

A dedicated source alias now owns pfSense WAN administration:

```text
PFSENSE_ADMIN_WAN
  80.15.4.233
```

The effective WAN order is:

```text
PASS   PFSENSE_ADMIN_WAN -> WAN address:10443
BLOCK  any               -> WAN address:10443
```

The explicit block immediately began matching untrusted traffic (58 packets in
the first observed sample). The allow rule showed `<PFSENSE_ADMIN_WAN:1>`,
which proves the admin source set had collapsed from the prior 257-entry alias
to one address.

The legacy `ExternalOffice` alias was then removed successfully; a later
`pfctl -t ExternalOffice -T show` returned `Table does not exist`, while
`pfctl -t PFSENSE_ADMIN_WAN -T show` returned only `80.15.4.233`.

Do not replace this source alias with
`fastapi-sample.fastapicloud.dev`: a public service hostname describes ingress
to the cloud application and is not proof of a stable outbound/egress identity.
If direct external observer access is ever reintroduced, model it separately
from human administration and require a reviewed stable source identity.

## Validation after the WAN block

The last observed public WebConfigurator authentication failure in the supplied
sample was at 20:29:05. From 20:31 onward, the sampled authentication failures
were only the internal TrueNAS source `172.17.0.24` calling:

```text
/api/v2/status/system/index.php
/api/v2/status/gateways/index.php
/api/v2/status/services/index.php
```

at roughly five-minute intervals with user `unknown`.

This is strong runtime evidence that the new WAN block prevents the observed
Internet scanners from reaching PHP-FPM. The remaining `172.17.0.24`
authentication failures are a separate local observer credential/configuration
problem and must not be treated as proof that WAN TCP/10443 is still exposed.

## Internal observer attribution

Repository/runtime policy identifies `pfsense-exporter` as the source of the
remaining five-minute authentication failures:

- Prometheus scrapes the exporter exactly every `300s`;
- the steady-state exporter configuration enables exactly three serialized
  collectors: `system`, `gateways` and `service`;
- those collectors match the three pfSense endpoints observed in the logs:
  `/api/v2/status/system`, `/api/v2/status/gateways` and
  `/api/v2/status/services`;
- the exporter runs on TrueNAS and pfSense therefore observes the host-side
  source `172.17.0.24`.

This proves emitter attribution but not yet the exact credential defect. The
runtime file `/mnt/cpool/prometheus/secrets/pfsense-exporter.yml` can still
contain a stale/revoked key or a key whose owning user lacks an exporter endpoint
privilege.

A dedicated fail-fast diagnostic now performs exactly one authenticated request
to `/api/v2/status/services` without printing the key or response body:

```bash
sudo bash scripts/truenas/diagnose-pfsense-exporter-auth.sh
```

Interpretation is deliberately narrow: HTTP 401 means the runtime key was
rejected, HTTP 403 means authentication succeeded but authorization is
insufficient, and HTTP 200 proves the service collector credential path. Do not
loop the diagnostic because rejected REST API credentials participate in pfSense
Login Protection.

The existing exporter hardener now also rejects the literal
`REPLACE_WITH_DEDICATED_PFSENSE_EXPORTER_API_KEY` placeholder instead of
preserving it as a non-empty credential.

## Follow-up evidence — 2026-10-09

No new OOM/reclaim incident was observed during the reported 2026-10-09
observation window while the CrowdSec engine remained stopped. Snort and
Unbound remained up. This materially strengthens CrowdSec as a major memory/CPU
pressure contributor, but does not prove it was the sole cause because the
pfBlockerNG ASN/IPinfo retry loop was also active during the 2026-10-08
failures and was disabled during the same remediation window.

CrowdSec logs from 2026-10-08 show repeated
`firewallservices/pf-scan-multi_ports` backpressure with failed-send counters
reaching many millions before the engine was stopped. The engine must remain
isolated until that path is understood and bounded.

The stale Prometheus exporter credential was also repaired on 2026-10-09:

- a single-request preflight returned HTTP 401 with the old runtime key;
- dedicated user `pfsense_exporter` was created with only GET privileges for
  `status/system`, `status/gateways` and `status/services`;
- the rotated key returned HTTP 200 for all three endpoints;
- `pfsense-exporter` restarted successfully and a supervised `/metrics`
  scrape returned pfSense gateway/service metrics.

Exporter acceptance is now complete: the last observed
`172.17.0.24` authentication failure was at `2026-10-09 20:41:24`, and no
new failure appeared across multiple following 300-second Prometheus cycles
covering the 20:xx and 21:xx observation windows.

## Remaining actions

- keep CrowdSec engine stopped until its failed-send loop is diagnosed;
- keep Unbound out of Service Watchdog while OOM remains plausible;
- correlate the Snort 02:09 rule-update job with the 02:10 OOM before changing
  its schedule;
- measure PHP-FPM/Unbound/Snort memory under the reduced WAN load before applying
  any persistent PHP-FPM tuning;
- revalidate the TCP/7000 TrueNAS source policy independently after removing the
  legacy `ExternalOffice` alias;
- preserve negative WAN reachability tests for 10443.
