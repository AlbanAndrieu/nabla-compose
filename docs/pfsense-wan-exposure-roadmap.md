# pfSense WAN exposure roadmap

This roadmap tracks the remaining pfSense WAN-policy work that affects the `nabla-compose` homelab and the FastAPI Sample external observability path.

## P0 — replace the broad WAN Easy Rule

The current broad pfSense Easy Rule must be removed and replaced with explicit listener/source policy. Evidence collected on 2026-09-02 showed the observed FastAPI Cloud source `52.1.10.241` establishing states to both the intended TrueNAS HAProxy listener on `82.66.4.247:7000` and the pfSense administration listener on `82.66.4.247:10443`.

Target policy:

- `10443/tcp` — pfSense administration is reachable only from trusted LAN/VPN administration paths and explicitly approved office aliases; an Internet/FastAPI Cloud connection is a failure.
- `7000/tcp` — keep the dedicated HAProxy -> TrueNAS path only for explicitly approved source aliases once stable FastAPI Cloud egress addresses/CIDRs have been verified. Do not treat one observed AWS address as a permanent FastAPI Cloud contract and do not allow an entire AWS allocation as a shortcut.
- `9922/tcp` and `22/tcp` — external SSH reachability remains forbidden.
- `443/tcp` and every other intentional public listener must have an explicit service/rule owner rather than inheriting a generic WAN pass.
- Prefer named pfSense aliases such as `FASTAPI_CLOUD_EGRESS`, `TRUSTED_WORK_EGRESS`, and `TRUSTED_ADMIN_EGRESS` over duplicated literal addresses.

Acceptance tests after the Easy Rule is replaced:

1. FastAPI Sample can still reach the intentional TrueNAS `:7000` endpoint from an approved source.
2. FastAPI Cloud and another generic Internet vantage point cannot establish TCP `10443`.
3. `/sickz` reports the reviewed public-port policy consistently with pfSense.
4. The HAProxy TrueNAS backend remains `UP`, `L7OK`, and HTTP `200`.
5. No broad WAN pass remains that makes the explicit management/source rules ineffective.

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
