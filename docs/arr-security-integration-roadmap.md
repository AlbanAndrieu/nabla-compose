# ARR, VPN and security integration roadmap

Last reviewed: 2026-09-13.

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

## 1. Current ARR state and migration gap

### Already represented in the repository

`truenas-file-structure.sh` already contains an older generated stack/layout for at least:

- Prowlarr;
- Radarr;
- Sonarr;
- Bazarr;
- qBittorrent;
- Seerr-family configuration;
- Dozzle.

The service catalogue also contains Prowlarr, Radarr, Sonarr and Lidarr runtime-facing definitions. This proves prior intent/runtime exposure, but the generated shell implementation must not become the new canonical deployment mechanism.

### Already canonical under `apps/`

- `apps/dozzle/compose.yml` exists and is repository-owned.
- `apps/crowdsec/compose.yml` exists and is repository-owned.
- Existing media/runtime services such as Plex or Lidarr must be checked individually before migration; presence in the service catalogue or TrueNAS Apps UI is not equivalent to having a canonical `apps/<service>/compose.yml`.

### TrueNAS-native / legacy runtime migration candidates

The next inventory pass must reconcile live TrueNAS Apps against `apps/*/compose.yml`. Priority media candidates from the current homelab inventory include:

- Lidarr — previously running as a native TrueNAS App; migrate only after preserving its config/database and media paths.
- Transmission — previously retained but stopped; decide whether to migrate it or retire it in favour of qBittorrent + VPN rather than running two torrent clients without a defined reason.
- Plex — preserve native runtime until storage/GPU/transcoding/device mappings and metadata backup/restore are proven in Compose.
- Tracearr — useful companion for media playback observability; migrate after Plex/Jellyfin ownership is clear.
- Wizarr — optional invitation workflow; migrate only if still needed after the request/user-management choice.
- Emby — previously stopped; explicitly decide retain/retire instead of migrating by default.
- Scrutiny — already tracked elsewhere for completing disk visibility including the workstation; keep it in the native-to-Compose migration inventory.
- Grafana — already explicitly tracked in the main roadmap as native -> Compose and remains a precedent for safe config/data preservation.

The inventory must be generated from live TrueNAS state plus repository ownership before implementation; do not infer canonical ownership from a historical runtime snapshot alone.

## 2. Target ARR baseline

The initial target should stay intentionally smaller than the full Awesome *Arr list.

### Phase A — core acquisition and organization

1. **Prowlarr** — single indexer manager for Sonarr/Radarr/Lidarr and compatible applications.
2. **Radarr** — movies.
3. **Sonarr** — TV/series.
4. **Lidarr** — music, migrating the existing TrueNAS-native instance rather than creating a second instance.
5. **Bazarr** — subtitles for Radarr/Sonarr.
6. **qBittorrent** — preferred torrent client candidate behind a dedicated VPN namespace.
7. **Seerr/Jellyseerr** — request/discovery layer only if the current media-server choice justifies it.
8. **Recyclarr** — synchronize reviewed TRaSH profiles/custom formats into Sonarr/Radarr; configuration must be versioned and reviewed because it can materially change download/quality policy.

### Phase B — useful supporting services

- **Cleanuparr** — clean dead/malicious/stalled torrent state after download-client integration is stable.
- **Maintainerr** — retention/library cleanup only after deletion policies are explicit and reversible.
- **Tdarr** — transcoding/health analytics; schedule after storage and hardware acceleration are defined because it can create substantial CPU/GPU and I/O load.
- **Scraparr or Exportarr** — Prometheus telemetry for ARR services; prefer one metrics path, not both, unless their coverage materially differs.
- **Unpackerr** — only if archive extraction is actually needed by the selected download sources.
- **Notifiarr** — optional; n8n may already cover enough notification/orchestration use cases.

### Defer / evaluate instead of installing blindly

Awesome *Arr is a discovery catalogue, not an installation checklist. Defer overlapping or specialised tools such as Jackett when Prowlarr is selected, multiple request frontends, duplicate cleaners, alternative Radarr/Sonarr managers, FlareSolverr-style bypass tooling, and adult-media-specific managers unless there is an explicit use case.

## 3. Storage design: hardlinks before containers

The Servers@Home and TRaSH model is correct in one important respect: downloads and final media that need hardlinks must live on the same filesystem/dataset boundary.

Recommended logical layout (final pool/dataset names must follow the existing TrueNAS storage contract):

```text
media/
  downloads/
    torrents/
  movies/
  tv/
  music/

configs/
  prowlarr/
  radarr/
  sonarr/
  lidarr/
  bazarr/
  qbittorrent/
  seerr/
  recyclarr/
```

Nabla-specific constraints:

- application config/data follows `docs/truenas-runtime-layout.md` and repository ownership rules;
- secrets never live inside tracked Compose or media datasets;
- keep one consistent container path (for example `/data`) across qBittorrent and ARR services so paths are identical from every container's point of view;
- do not split downloads and final media across filesystems if hardlinks are required;
- validate UID/GID/ACL behaviour against TrueNAS before importing an existing library;
- test hardlink behaviour explicitly (`stat` inode/link count) before declaring the storage design accepted.

## 4. VPN design for download clients

Reference: https://wiki.servarr.com/vpn

The Servarr applications themselves should **not** all be forced through a VPN. Their documentation recommends keeping Radarr/Sonarr/Prowlarr-style applications on normal networking and placing the download client behind the VPN when required. This avoids broken LAN callbacks, authentication/captcha issues, rate limiting and difficult inter-container routing.

### Preferred pattern

Use a dedicated VPN gateway container, preferably **Gluetun**, and attach only the download client network namespace to it:

```text
Internet
  |
  v
Gluetun / ProtonVPN
  |
  +-- qBittorrent

Prowlarr/Radarr/Sonarr/Lidarr/Bazarr
  |
  +-- normal internal Docker networking -> qBittorrent exposed through Gluetun service ports
```

Acceptance must prove:

- kill-switch behaviour: qBittorrent has no internet egress if the VPN tunnel is down;
- LAN/API reachability remains available only through explicit Gluetun firewall rules;
- DNS does not leak outside the VPN namespace;
- external IP from the qBittorrent namespace is ProtonVPN, not the ISP WAN;
- torrent listening port follows ProtonVPN port-forwarding state where enabled;
- health failure of the VPN blocks qBittorrent rather than silently failing open.

### ProtonVPN assessment

**Compatible candidate.** Gluetun has native WireGuard support for ProtonVPN, and ProtonVPN supports P2P plus NAT-PMP port forwarding on compatible paid/P2P servers. The main operational caveat is that the forwarded port can change after reconnects, so qBittorrent's listening port needs automatic reconciliation.

Do not route Traefik, CrowdSec, ARR managers, Plex/Jellyfin, or management traffic through this VPN namespace.

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
| Prowlarr/Radarr/Sonarr/Lidarr/Bazarr | Compatible | shared paths, UID/GID, API keys, hardlinks |
| qBittorrent + Gluetun + ProtonVPN | Compatible | kill switch, LAN API, dynamic NAT-PMP forwarded port |
| Transmission + qBittorrent | Avoid duplicate by default | overlapping download-client role |
| Recyclarr | Compatible | configuration can materially alter quality/custom-format policy |
| Tdarr | Compatible with capacity review | GPU/CPU/I/O load and device passthrough |
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

1. **Inventory and storage first**
   - live TrueNAS Apps vs `apps/*/compose.yml` diff;
   - choose media dataset and hardlink-safe paths;
   - snapshot/export configs for every native service to be migrated.
2. **VPN/download boundary**
   - add Gluetun + ProtonVPN with kill-switch tests;
   - deploy/migrate qBittorrent; decide Transmission retirement.
3. **Core ARR**
   - Prowlarr -> Radarr/Sonarr -> migrate Lidarr -> Bazarr -> Seerr/Jellyseerr.
4. **Policy automation**
   - Recyclarr with reviewed config; then optional cleanup/notification tools.
5. **Observability**
   - add Scraparr or Exportarr Prometheus telemetry;
   - reconcile Dozzle to Docker Socket Proxy and safe remote-agent mode.
6. **Security edge**
   - Traefik access logs -> CrowdSec acquisition;
   - Traefik CrowdSec bouncer/middleware;
   - validate pfSense + Traefik remediation without duplicate ownership.
7. **Security MCPs**
   - CVE MCP first; World Intelligence MCP second.
8. **Isolated offensive security**
   - CyberStrike only in a dedicated disposable VM/segment.
9. **Host security evaluation**
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
