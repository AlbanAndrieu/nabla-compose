# ARR, VPN and security integration roadmap

Last reviewed: 2026-09-13. ARR/VPN/storage scope moved to `arr-media-library-roadmap.md` on 2026-11-07.

This document is the detailed analysis behind the concise items tracked in `docs/roadmap.md`. It is intentionally architectural: each service must still be introduced through a reviewed `apps/<service>/compose.yml`, `x-nabla` topology metadata, runtime-secret materialization and bounded acceptance checks before deployment.

## Primary references

### ARR / media automation

- Servers@Home *Arr Stack: https://wiki.serversatho.me/en/arr-stack
- Servers@Home folder structure / TrueNAS hardlink layout: https://wiki.serversatho.me/Folder-Structure
- Awesome *Arr catalogue: https://github.com/Ravencentric/awesome-arr
- Servarr documentation: https://wiki.servarr.com/
- Servarr VPN guidance: https://wiki.servarr.com/vpn
- TRaSH Guides: https://trash-guides.info/

These links are analysis inputs, not configuration sources of truth. Image tags, paths, permissions, secrets, exposure and health checks must be reviewed against the current Nabla contracts before adoption.

### Traefik / CrowdSec / Dozzle reference implementation

- SimpleHomelab Docker-Traefik: https://github.com/SimpleHomelab/Docker-Traefik/tree/main
- CrowdSec guide index in that repository: https://github.com/SimpleHomelab/Docker-Traefik#readme
- Dozzle documentation: https://dozzle.dev/
- Dozzle MCP: https://dozzle.dev/guide/mcp

### Security candidates

- CVE MCP server: https://github.com/mukul975/cve-mcp-server
- CyberStrike: https://github.com/CyberStrikeus/CyberStrike
- SysWarden: https://syswarden.io/
- World Intelligence MCP: https://github.com/marc-shade/world-intel-mcp

## 1–4. ARR, storage and VPN — superseded

Sections 1–4 (ARR inventory, target baseline, hardlink storage and the download VPN boundary)
were superseded on 2026-11-07 by the canonical
[`arr-media-library-roadmap.md`](arr-media-library-roadmap.md), which also owns the DNS
strategy, the phased installation order and the anonymity acceptance tests. Do not
re-add ARR planning here.

## 5. CrowdSec + Traefik reconciliation

Current Nabla design is already stronger than a simple single-host tutorial in several areas:

- `apps/crowdsec/compose.yml` is the central CrowdSec Security Engine/LAPI;
- pfSense consumes decisions through a remediation-only bouncer model;
- Suricata `eve.json` is an intended CrowdSec acquisition source;
- Prometheus has a CrowdSec metrics relationship.

The SimpleHomelab repository is therefore a pattern source, not a stack to copy wholesale.

### Changes worth porting

1. **Traefik HTTP bouncer/middleware path**
   - add a reviewed CrowdSec middleware/bouncer between exposed Traefik routers and applications;
   - make middleware chaining explicit (`CrowdSec -> rate limit -> headers -> auth` where appropriate);
   - avoid protecting internal-only health endpoints in a way that breaks monitoring.

2. **Traefik access/error logs as acquisition sources**
   - ensure Traefik writes structured access logs to a repository-defined host path or supported stream;
   - feed those logs into CrowdSec with the appropriate Traefik/http collections/parsers;
   - prove a synthetic abusive request produces an acquisition event and decision path.

3. **Separate decision and remediation responsibilities**
   - keep one central LAPI/decision engine;
   - use pfSense for edge/network remediation and Traefik bouncer/middleware for HTTP-layer remediation;
   - avoid multiple independent CrowdSec engines making divergent decisions unless a multi-server architecture is explicitly designed.

4. **Cloudflare bouncer: evaluate, do not enable automatically**
   - useful only for publicly proxied DNS/HTTP names where blocking at Cloudflare edge adds value;
   - Cloudflare Access/Tunnel policies remain separate controls and should not be conflated with CrowdSec decisions.

### Do not copy

- host paths or Proxmox assumptions;
- `latest` tags;
- direct Docker socket mounts where the existing Docker Socket Proxy can be used;
- global middleware chains without assessing internal traffic and Cloudflare Access paths;
- firewall-bouncer ownership that conflicts with pfSense/PF ownership.

## 6. Dozzle on TrueNAS

Dozzle is not Proxmox-specific. It talks to the **Docker Engine API**. On TrueNAS SCALE where Apps are Docker/Compose-backed, it can inspect the containers visible to the Docker daemon exactly as it can on a generic Linux Docker host.

The SimpleHomelab pattern is useful because it avoids mounting `/var/run/docker.sock` directly into Dozzle and uses a Docker Socket Proxy. Nabla currently mounts the socket read-only **but also enables Dozzle actions and shell**, which raises the privilege value of the socket significantly.

Current Nabla features are useful:

- persistent Dozzle instance on TrueNAS;
- remote agent support for the workstation (`DOZZLE_REMOTE_AGENT`);
- MCP endpoint enabled;
- Traefik integration;
- simple authentication and no analytics.

Recommended hardening:

1. replace the direct Docker socket bind with the existing `docker-socket-proxy` where the required endpoints are supported;
2. default `DOZZLE_ENABLE_ACTIONS=false` and `DOZZLE_ENABLE_SHELL=false` unless an operator explicitly enables break-glass mode;
3. keep MCP disabled from untrusted/external networks and treat it as an administrative capability;
4. use Dozzle agents for remote Docker engines rather than exposing Docker TCP sockets;
5. expose Dozzle only on the internal Traefik path/Access policy; never public anonymous access;
6. add audit/observability around action/shell enablement.

The SimpleHomelab use of Proxmox describes its host topology, not a Dozzle requirement.

## 7. Security service candidates

### CVE MCP Server

Repository: https://github.com/mukul975/cve-mcp-server

**Fit:** high for the existing MCP/LLM security toolchain. It provides CVE lookup/triage using NVD, EPSS, CISA KEV and other intelligence sources and can expose Streamable HTTP.

**Integration plan:**

- package as `apps/cve-mcp-server/compose.yml` using its non-root Dockerfile;
- bind only to an internal network;
- expose to LiteLLM/OpenWebUI/agent infrastructure only if the consumer supports the MCP transport directly or through the existing MCP gateway pattern;
- store API keys through `/mnt/cpool/secrets/runtime/...`;
- persist its SQLite cache on application-owned storage if useful;
- pin release/image/build SHA.

**Compatibility caveat:** there is an open dependency issue around an unbounded `mcp>=1.7.0` allowing MCP 2.x incompatibility. Pin a known-working MCP dependency/release during packaging and test the advertised tool schemas rather than trusting README examples blindly.

### CyberStrike

Repository: https://github.com/CyberStrikeus/CyberStrike

**Fit:** useful but intentionally high risk. It is an offensive-security agent/harness with shell execution, browser automation and exploitation tooling.

**Hard boundary:** its own security documentation states that the agent is **not sandboxed**. Do not deploy it as a normal privileged TrueNAS application with access to the homelab management network, Docker socket, secrets dataset or production credentials.

Recommended deployment options, in order:

1. isolated disposable VM on the workstation/Talos lab network;
2. strongly restricted container inside an isolated VM;
3. never host-networked on TrueNAS.

Use explicit target allowlists, no automatic Internet-facing UI, dedicated LLM credentials, outbound controls, and retain operator approval for intrusive actions. Cloudflare Tunnel can protect its web UI transport, but it does not provide execution isolation.

### SysWarden

Site: https://syswarden.io/

**Fit:** **not a TrueNAS container candidate.** SysWarden is a host-local AMD64 Linux security orchestrator that owns authoritative `nftables` policy. Its current supported matrix is native Linux packages (Debian/Ubuntu/Fedora/Alma/Alpine) and it explicitly treats firewall ownership as a host-level boundary.

Potential fit:

- dedicated Ubuntu 24.04 LXC/VM or future trusted Linux runner/utility host;
- not TrueNAS host OS;
- not pfSense (FreeBSD/PF);
- not inside a container expected to enforce the parent host firewall.

Potential conflict: do not let SysWarden own nftables on a Linux host where Kubernetes/CNI, Docker or another firewall manager has unreviewed overlapping rule ownership. A dedicated security gateway/utility VM is safer.

### World Intelligence MCP

Repository: https://github.com/marc-shade/world-intel-mcp

**Fit:** good as an intelligence enrichment MCP, not an enforcement component. It covers geopolitical, cyber, market, climate and other public data sources and can optionally use Qdrant and Ollama.

Integration plan:

- package as a low-privilege internal service;
- prefer Streamable HTTP if supported by the selected deployment path, otherwise keep stdio behind a local MCP gateway;
- reuse the workstation Ollama endpoint only through an explicit URL and scoped network route;
- evaluate the optional Qdrant vector feature against the existing data-service footprint before creating another persistent datastore;
- rate-limit public API use and cache responses;
- do not feed untrusted intelligence text directly into an autonomous offensive/security action without an approval boundary.

## 8. Compatibility matrix

| Component | Status | Main compatibility concern |
| --- | --- | --- |
| ARR / qBittorrent / Gluetun / media | See `arr-media-library-roadmap.md` | owned by the canonical media roadmap |
| CrowdSec central LAPI + pfSense bouncer | Already intended | preserve one decision engine and PF ownership |
| CrowdSec + Traefik bouncer | Compatible / recommended | middleware order, real client IP, Cloudflare/Tunnel headers |
| CrowdSec + Suricata | Already intended | prove `eve.json` acquisition end-to-end |
| Dozzle + TrueNAS Docker | Compatible | Docker API privilege; prefer socket proxy |
| Dozzle shell/actions + direct docker.sock | High risk | effectively administrative Docker capability |
| CVE MCP + LiteLLM/agents | Compatible after pinning | MCP dependency/schema drift, API secrets |
| World Intel MCP + agent stack | Compatible | untrusted external data, optional Qdrant footprint |
| CyberStrike + main TrueNAS host | Incompatible security boundary | no sandbox; offensive shell/exploitation capability |
| CyberStrike isolated VM | Compatible with guardrails | strict target/network/credential isolation |
| SysWarden + TrueNAS/pfSense | Incompatible target | Linux AMD64 host-local nftables ownership only |
| SysWarden + dedicated Linux VM | Potentially compatible | avoid firewall ownership conflict with Docker/K8s/CNI |

## 9. Recommended implementation order

1. **ARR, storage, VPN and media services** — follow the phases of
   [`arr-media-library-roadmap.md`](arr-media-library-roadmap.md).
2. **Observability**
   - ARR telemetry (Exportarr or Scraparr) is tracked in the media roadmap;
   - reconcile Dozzle to Docker Socket Proxy and safe remote-agent mode.
3. **Security edge**
   - Traefik access logs -> CrowdSec acquisition;
   - Traefik CrowdSec bouncer/middleware;
   - validate pfSense + Traefik remediation without duplicate ownership.
4. **Security MCPs**
   - CVE MCP first; World Intelligence MCP second.
5. **Isolated offensive security**
   - CyberStrike only in a dedicated disposable VM/segment.
6. **Host security evaluation**
   - SysWarden only on a dedicated supported Linux host if there is a clear firewall-ownership use case.

## 10. Acceptance criteria for every new Compose service

- tracked `apps/<service>/compose.yml` with pinned version/digest policy;
- complete `x-nabla` metadata, criticality, relations and monitoring contract;
- canonical secret path under `/mnt/cpool/secrets/runtime/<service>`;
- no implicit project `.env` containing secrets;
- application data dataset/path documented and backed up before migration;
- `docker compose config` / repository quality gate clean;
- health/readiness check is functional, not only container-running state;
- no direct WAN publication unless explicitly required and protected;
- Traefik/Cloudflare/CrowdSec roles are non-overlapping and documented;
- Prometheus/logging coverage added when useful;
- rollback path to the previous TrueNAS App/runtime state documented until acceptance is complete.
