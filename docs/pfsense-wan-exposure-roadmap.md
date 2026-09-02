# pfSense WAN exposure roadmap

This roadmap tracks the remaining pfSense WAN-policy work that affects the `nabla-compose` homelab and the FastAPI Sample external observability path.

## P0 — replace the broad WAN Easy Rule

The current broad pfSense Easy Rule must be removed and replaced with explicit listener/source policy. Evidence collected on 2026-09-02 showed observed FastAPI Cloud sources establishing states to both the intended TrueNAS HAProxy listener on `82.66.4.247:7000` and the pfSense administration/API listener on `82.66.4.247:10443`.

FastAPI Cloud currently requires both listeners and the deployment does not provide a user-controlled static egress gateway or outbound tunnel. The target is therefore **source-aware**, not a global public/private boolean:

- `7000/tcp` — TrueNAS via pfSense HAProxy must remain reachable from the FastAPI Cloud production runtime and any explicitly approved administration source. Generic untrusted Internet origins must remain denied.
- `10443/tcp` — pfSense REST API/administration must remain reachable from the FastAPI Cloud production runtime and explicitly approved administration sources because FastAPI Sample needs read-only posture and security telemetry. Generic untrusted Internet origins must remain denied.
- `9922/tcp` and `22/tcp` — external SSH reachability remains forbidden.
- `443/tcp` and every other intentional public listener must have an explicit service/rule owner rather than inheriting a generic WAN pass.
- Prefer named pfSense aliases for stable office/VPN/DDNS administration sources. Do **not** automatically populate an alias from the currently observed FastAPI Cloud egress IP, and do not allow an entire AWS allocation as a shortcut.

FastAPI Cloud egress addresses observed during the investigation included `52.1.10.241`, `54.164.107.133`, and `34.200.20.162`. These observations prove only where a particular request originated; they are not a stable FastAPI Cloud egress contract.

Until the platform offers a user-controlled stable network identity, direct WAN access from FastAPI Cloud to `7000` and `10443` remains an explicitly tracked security exception. Compensating controls are mandatory: verified TLS, dedicated least-privilege API identities, global pfSense REST API read-only mode during steady state, Snort/PF monitoring, and independent negative reachability tests.

Acceptance tests after the Easy Rule is replaced:

1. FastAPI Cloud can still reach the intentional TrueNAS `:7000` endpoint and complete the required TLS/HTTPS/WebSocket/API path.
2. FastAPI Cloud can still reach pfSense `:10443` and authenticate with the dedicated GET-only posture/security identities.
3. An independent untrusted Internet vantage point cannot establish the intended application path to `:7000` or `:10443`; an HTTP `401`/`403` from that vantage still proves the listener is network-reachable and does not satisfy an L3/L4 source-restriction requirement.
4. `/sickz` reports both `7000` and `10443` as `trusted_sources_only`, expected reachable from the FastAPI Cloud vantage, with a default-deny/negative-probe requirement for other origins.
5. The HAProxy TrueNAS backend remains `UP`, `L7OK`, and HTTP `200`.
6. No broad WAN pass remains that makes the explicit listener/source rules ineffective.

## P1 — security-engine attribution

Keep pfSense/PF, Snort, pfBlockerNG, and CrowdSec as distinct filtering layers. A running security service is not proof that it blocked a request.

For an observed external source:

- use PF state/log evidence for firewall attribution;
- use `snort2c` plus the corresponding Snort alert/SID for Snort attribution;
- distinguish pfBlockerNG IP-feed/alias filtering from DNSBL;
- use CrowdSec decisions for CrowdSec attribution;
- re-enable filtering engines one at a time when isolating an intermittent block;
- never create an automatic allowlist from FastAPI Sample's currently observed cloud egress IP.

FastAPI Sample may expose sanitized service-state badges for these layers and may enrich an observed IP with RDAP/ASN/cloud-prefix metadata, but repository automation must not mutate firewall aliases from that telemetry.

### Proven Snort -> `snort2c` -> PF block on the TrueNAS path

A controlled A/B test on 2026-09-02 established Snort/PF as the cause of the intermittent FastAPI Cloud -> TrueNAS failure.

Terminology used in this incident:

- `82.66.4.247` — **homelab WAN endpoint / pfSense WAN public IPv4**. This is the public address that accepts the intentional `:7000` listener before HAProxy forwards to TrueNAS.
- `34.200.20.162` — **observed FastAPI Cloud egress/source IPv4** during the failing test. Earlier requests were observed from other cloud addresses (`52.1.10.241`, `54.164.107.133`), so this address must not be treated as a stable FastAPI Cloud contract.
- `172.17.0.24` — internal TrueNAS address behind HAProxy.

TCP establishment must complete before TLS can begin:

```text
FastAPI Cloud                         pfSense / HAProxy
34.200.20.162                         82.66.4.247:7000
      |                                      |
      | SYN                                  |
      |------------------------------------->|  request to open TCP
      |                                      |
      | SYN,ACK                              |
      |<-------------------------------------|  listener accepts TCP
      |                                      |
      | ACK                                  |
      |------------------------------------->|  TCP established
      |                                      |
      | TLS ClientHello ...                  |
      |------------------------------------->|  TLS starts only now
```

Interpretation:

- `SYN` — request to establish a TCP connection.
- `SYN,ACK` — destination accepted the TCP connection.
- `ACK` — client confirms the connection; TCP is established.
- `RST` — connection was explicitly refused/reset.
- repeated `SYN` packets without `SYN,ACK` or `RST` usually indicate a silent firewall/filter drop before TLS.

With Snort WAN enabled in Legacy Mode, `Block Offenders` enabled, `Kill States` enabled, and `Which IP to Block = BOTH`, the observed cloud source became a member of `snort2c`:

```sh
pfctl -t snort2c -T test 34.200.20.162
# 1/1 addresses match.
```

PF also had explicit bidirectional rules generated for the table:

```text
block drop log quick from <snort2c> to any
block drop log quick from any to <snort2c>
```

At that point the WAN capture showed only repeated inbound `SYN` packets from `34.200.20.162` to `82.66.4.247:7000`, with no `SYN,ACK` response. HAProxy and TLS were therefore never reached.

Snort alerts immediately preceding the block were HTTP Inspect preprocessor events on the same flow:

```text
[120:3]  (http_inspect) NO CONTENT-LENGTH OR TRANSFER-ENCODING IN HTTP RESPONSE
[120:18] (http_inspect) PROTOCOL-OTHER HTTP server response before client request
```

The WAN Snort configuration included `7000` in the `http_inspect_server` port list even though the public `82.66.4.247:7000` hop carries TLS to HAProxy. HTTP Inspect runs before HAProxy terminates TLS and therefore cannot reliably parse the encrypted application stream as clear-text HTTP. These alerts are consequently consistent with false-positive protocol classification on this path.

The causal A/B test was:

1. stop **Snort WAN only**;
2. delete only the observed cloud source from `snort2c`:

   ```sh
   pfctl -t snort2c -T delete 34.200.20.162
   ```

3. capture the same flow again.

Immediately afterwards the capture showed `SYN -> SYN,ACK -> ACK`, followed by bidirectional application data and clean TCP close packets. The FastAPI Cloud -> `82.66.4.247:7000` path therefore recovered as soon as the Snort-generated PF block was removed.

Operational conclusion:

```text
Snort HTTP Inspect false positive on TLS :7000
        -> Block Offenders
        -> observed cloud source inserted in snort2c
        -> PF block/drop rules
        -> Kill States / subsequent SYN silently dropped
        -> HAProxy and TrueNAS no longer reached
```

Remediation target:

- keep Snort enabled, but remove `7000` from the WAN **HTTP Inspect** server-port list;
- optionally add `7000` to the Snort SSL/TLS preprocessor port list if that preprocessor is enabled and supported by the deployed Snort package;
- do not suppress all `120:*` alerts globally merely to hide the symptom;
- do not add rotating FastAPI Cloud/AWS egress addresses to a permanent Snort Pass List;
- after changing preprocessors, clear only the test source from `snort2c`, restart Snort WAN, and repeat the `SYN -> SYN,ACK -> ACK` plus `/api/homelab/status` validation;
- retain `Block Offenders` and `Kill States` only after the false-positive protocol classification is corrected and validated.

## P1 — source-IP enrichment contract

Add a shared, read-only enrichment contract so FastAPI Sample and infrastructure diagnostics can explain an observed WAN source address without turning reputation data into firewall policy.

For an address such as `52.1.10.241`, collect when available:

- RDAP/WHOIS registered network owner and allocation;
- BGP origin ASN and routed prefix;
- organization/ASN name and country metadata;
- reverse DNS/PTR hostname;
- cloud-provider ownership from published prefix feeds;
- cloud service/region only when the provider publishes that mapping;
- observation timestamp, enrichment timestamp, data sources, and a confidence level.

Operational requirements:

- FastAPI Sample may also expose its currently observed outbound public IP using a bounded, cached external echo probe so it can be correlated with pfSense states/captures.
- Cache all external lookups and use strict timeouts/rate limits; an enrichment provider outage must never break `/healthz`, `/sickz`, or homelab health.
- Keep source-IP enrichment informational. Do not automatically create/update `FASTAPI_CLOUD_EGRESS` or any other pfSense alias from the observed IP, ASN, provider, or prefix.
- A cloud-provider match proves network ownership, not workload identity. Correlate with synchronized application requests plus PF/HAProxy/IDS evidence before attributing the source to the current FastAPI Cloud deployment.

## P1 — cross-repository observability contract

FastAPI Sample is the external read-only observer and `nabla-compose` is the infrastructure/deployment source of truth. Keep these responsibilities separate:

- `nabla-compose` documents intended exposure and owns service/catalog topology;
- pfSense owns actual packet-filter/NAT/HAProxy policy;
- FastAPI Sample `/api/homelab/health`, `/api/homelab/status`, `/healthz`, and `/sickz` provide sanitized observed evidence;
- TrueNAS runtime state must not be treated as proof that the public WAN path is accepted;
- HAProxy backend health must not be treated as proof that pfSense/Snort/pfBlockerNG/CrowdSec will accept a specific source.

The broad WAN Easy Rule removal remains a hardening task even while current TrueNAS health is green.

## P4 — optional HAProxy → Traefik TLS backend verification

Very low priority. The current direct Garage ingress has now been proven as:

`client HTTPS -> HAProxy TLS termination -> TLS re-encryption -> Traefik :443 -> Garage`

HAProxy currently encrypts the backend hop to Traefik, but backend certificate verification should remain deferred until the TrueNAS-hosted Traefik certificate lifecycle is understood and proven stable.

Before changing `verify none`, first determine from the deployed TrueNAS/Traefik configuration:

- which certificate Traefik presents on the internal `:443` listener;
- whether that certificate is stable across TrueNAS App/container upgrades and redeployments;
- whether it chains to a CA that pfSense/HAProxy can trust cleanly;
- whether SNI/server-name verification can be configured without coupling HAProxy to a fragile container-generated certificate;
- whether TrueNAS or the current Traefik deployment provides an authoritative, maintainable mechanism for certificate rotation.

Only if those points are proven should HAProxy backend verification be hardened from encrypted-but-unverified TLS to verified TLS. Do not switch to TLS passthrough merely to avoid certificate-management uncertainty; passthrough is a separate architectural choice that would remove HAProxy HTTP/L7 inspection on this path.
