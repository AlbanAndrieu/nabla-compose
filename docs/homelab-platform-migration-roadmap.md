# Homelab platform migration roadmap

This roadmap consolidates the remaining migration from legacy/native TrueNAS Apps and ixVolumes to repository-managed Docker Compose services with explicit datasets under `/mnt/cpool`, then layers secrets management and centralized identity on top.

The goal is not merely to make containers start. A migration is complete only when data, runtime health, monitoring, rollback, secrets, and authentication are all controlled deliberately.

## Restart point — 2026-08-28

- Working pull request: `AlbanAndrieu/nabla-compose#59`, branch `feat/crowdsec-central-lapi`.
- Baseline commit `9d7374d3a269e09f7c76b10c9a08dd0fd8cf3e4f` passed Compose Validate, Service Consumers, Pre-commit and MegaLinter.
- Public PR CI must remain on `ubuntu-latest` without private homelab access or `infra-runners`.
- TrueNAS intentionally remains on `26.0.0-BETA.2`; keep `truenas/api_client` pinned to the matching `TS-26.0.0-BETA.2` tag and do not upgrade either side independently. Talos/OpenTofu preparation is static and must not mutate the homelab from PR CI.
- Secret target: Vaultwarden folder `TrueNAS`, then a restricted organization collection for unattended access; per-service TrueNAS `.env` files are only a compatibility layer.
- Immediate next execution: inventory variable names, migrate N8N as the canary, validate Doco-CD secret resolution, then continue the TrueNAS/Talos bootstrap checklist.
- TrueNAS/Talos manual bootstrap progressed through the first reviewed create plan: `br0` survived reboot, SSH was rebound to `br0`, bootstrap-critical SMB/NFS/iSCSI/TrueNAS/Garage/Traefik listeners were verified, Garage state read/write/delete passed, and the repeated TrueNAS plan remains `15 to add, 0 to change, 0 to destroy`. The resource apply completed successfully with 15 resources created and no changes/destructions. `taloscp01` has been started for first-boot DHCP discovery; Talos machine configuration remains a workstation-driven step after its stable IP and real install disk are confirmed.
- Talos control-plane maintenance discovery completed: `taloscp01` is reachable at `172.17.0.50:50000`, runs Talos `v1.13.9`, exposes `ens2` with the planned MAC, and reports the target install disk as `/dev/vda` (34 GB VirtIO).
- [x] Talos boot-device normalization plan reviewed with all Talos VMs stopped: `0 to add, 6 to change, 0 to destroy`. The only actions are three DISK orders `1001 -> 1000` and three CDROM orders `1000 -> 1001`; NIC order remains `1002`.
- [x] **Reboot persistence validated 2026-09-05:** `br0` retained `172.17.0.24/24`, `enp10s0` remained a forwarding member without IPv4, the default route remained on `br0`, and direct HTTPS validation still succeeded without `-k`. SSH required changing **Bind Interfaces** from `enp10s0` to `br0`; audit other explicitly bound services before the first VM apply.
- Current supervised bootstrap uses the existing `TRUENAS_USER=albandrieu` API-key owner. A dedicated least-privilege `tofu_truenas` service identity remains a hardening task before unattended/recurring infrastructure automation.

- [x] **Talos/Kubernetes bootstrap reached:** `taloscp01` is installed on `/dev/vda`, reboots from disk, authenticates with RBAC, etcd and kubelet are healthy, Kubernetes API is reachable at `172.17.0.50:6443`, and workers `.51`/`.52` are already registered with flannel/kube-proxy running;
- [ ] confirm all three Kubernetes nodes transition from the initial `NotReady` state to `Ready`; if not, inspect node conditions/events before any machine-config reapply;
- [ ] decide whether to keep Talos-generated stable Kubernetes node names or introduce explicit HostnameConfig patches in a separately reviewed change before production workloads;
- [x] **Talos base cluster complete:** all three nodes are `Ready`, flannel reports `NetworkUnavailable=False`, worker kubelets are healthy, and the single expected etcd member is healthy on `172.17.0.50`;
- [x] add `scripts/talos/validate-cluster.sh` as a read-only health gate for Talos RBAC, kubelet/etcd health, node count/readiness and single-control-plane etcd membership;
- [ ] validate Kubernetes DNS and pod-to-pod / pod-to-service networking with an explicit smoke workload before adding persistent storage;
- [ ] introduce TrueNAS-backed persistent storage as a separate democratic-csi change after network/DNS validation;
- [ ] bootstrap GitOps only after storage behavior and rollback are proven;
### TrueNAS FastAPI observer boundary — 2026-09-06

The internal FastAPI production observer now uses a dedicated TrueNAS identity:

```text
fastapi_observer
  -> fastapi-observer group
  -> APPS_READ only
  -> dedicated user-linked API key
```

Runtime validation proves `system.version` and `app.query` (86 apps) with the
native TrueNAS 26.0.0-BETA.2 client. The earlier WebSocket denial was not RBAC:
TrueNAS applies `system.general.ui_allowlist` to the WebSocket source address
before method authorization.

- [x] create `fastapi_observer` with no shell/home, group `fastapi-observer`,
  role `APPS_READ` and a dedicated API key;
- [x] prove the least-privilege identity can call `system.version` and
  `app.query` but does not inherit administrator roles;
- [x] add `scripts/security/verify-truenas-observer-access.sh` as a read-only
  preflight for container source IP, `ui_allowlist`, canonical credential
  variable selection, HTTPS version discovery and authenticated WebSocket
  calls;
- [ ] remove legacy `TRUENAS_USER=albandrieu` from the FastAPI Sample runtime
  after confirming only `TRUENAS_API_USERNAME=fastapi_observer` remains;
- [x] pin FastAPI Sample to `172.16.55.9` on the production
  `172.16.55.0/24` intranet by default (override with
  `FASTAPI_SAMPLE_OBSERVER_IP` only together with a reviewed allowlist
  change), so a recreate cannot silently change the TrueNAS WebSocket source;
- [x] document `172.16.55.9/32` as the current Docker-origin TrueNAS UI/API
  allowlist entry required by FastAPI Sample;
- [ ] evaluate a dedicated observer Docker network as a later isolation
  improvement if other trusted-LAN observers need their own source identities;
- [ ] restore `TRUENAS_API_VERIFY_SSL=true` after validating the
  `truenas.albandrieu.com` certificate chain from inside the container;
- [ ] never widen `ui_allowlist` to all of `172.16.55.0/24` merely to avoid
  container-address management.

### Post-reboot runtime cleanup — 2026-09-05

Track these independently from the Talos bridge/bootstrap:

- [x] Alertmanager configuration is now tracked in `apps/prometheus/alertmanager.yml`, mounted read-only, and integrated from Prometheus; repository rule files are also mounted and loaded. Configure a real notification receiver before depending on alert delivery;
- [x] Native Scrutiny recovered functionally before cutover: InfluxDB `/health` and Scrutiny `/api/health` returned HTTP 200 and SMART collection ran. The native app is now stopped and the user created the target Scrutiny dataset; complete the repository-managed migration below before retiring native data;
- [x] `opensearch-security`: data ownership corrected to UID/GID `1000:1000`; `_cluster/health` is green and Docker health is healthy;
- [x] Open WebUI: healthy after reboot;
- [x] Docker socket proxy: the TrueNAS-managed proxy that published
  `0.0.0.0:2375` is stopped; AutoXpose and Doco-CD now use the repository
  `docker-socket-proxy:2375` over the shared `intranet` network, with no
  host-published Docker API port;
- [ ] uninstall the stopped native TrueNAS Docker Socket Proxy app after one
  final consumer inventory confirms no rollback dependency remains;
- [ ] Tailscale: unused; leave stopped and clean up later rather than treating it as a Talos prerequisite.


### Pi-hole native App -> repository Compose migration — 2026-09-07

The Pi-hole cutover is now promoted because the internal DNS synchronizer exposed
two coupled runtime faults:

- the native Pi-hole API hit `webserver.api.max_sessions=16`, preventing even
  administrator login with `api_seats_exceeded`;
- `pihole-dns-sync` could authenticate but could not resolve
  `docker-socket-proxy`, because its deployment ownership/networking was split
  from the repository-managed Docker proxy. The resulting restart loop repeatedly
  allocated API sessions without completing useful Docker/Traefik discovery.

Target ownership:

```text
apps/pihole/compose.yml
  +-- pihole
  +-- pihole-dns-sync
  +-- pihole-exporter

shared intranet
  +-- docker-socket-proxy
  +-- pihole
  +-- pihole-dns-sync
  +-- pihole-exporter
```

- [x] make `apps/pihole/compose.yml` the migration target and pin the official
  Pi-hole image instead of tracking `latest`;
- [x] move `pihole-dns-sync` out of `apps/traefik/compose.yml` so DNS
  synchronization is owned beside Pi-hole;
- [x] attach the synchronizer to `intranet` so
  `docker-socket-proxy:2375` resolves without publishing the Docker API on the
  host/LAN;
- [x] keep `webserver.api.max_sessions=16` as the normal budget; do not mask a
  restart/authentication loop by permanently raising the limit;
- [x] preserve LAN compatibility ports `53`, `20720`, `30132` and exporter
  `9617`, while normalizing Pi-hole container web ports to `80/443`;
- [x] add `apps/pihole/README.md` with mount discovery, data copy, secret
  preservation, cutover, acceptance and rollback steps;
- [ ] inventory the exact native `ix-pihole-pihole-1` mounts and image version
  before copying any data;
- [ ] back up and copy the native `/etc/pihole` dataset into
  `/mnt/cpool/pihole/config` without guessing the ixVolume source path;
- [ ] migrate legacy `/etc/dnsmasq.d` only when the native mount contains
  meaningful custom configuration;
- [ ] validate the current UI/API password with the repository-managed container
  without rotating it during cutover;
- [ ] start the Compose replacement only after the native app is stopped and
  ports `53/20720/30132/9617` are free;
- [x] prove `pihole-dns-sync` stays running, resolves
  `docker-socket-proxy`, and no longer grows API sessions continuously;
- [x] prove Pi-hole answers `sample.int.albandrieu.com -> 172.17.0.24` on
  UDP/TCP 53 and that pfSense/Unbound forwards `int.albandrieu.com` to
  `172.17.0.24`;
- [x] fix pfSense Unbound split-DNS forwarding by keeping **Forwarding Mode**
  disabled and allowing **Outgoing Network Interfaces = All**. The previous
  WAN-only setting made Unbound mark the Pi-hole forwarder as expired even
  though direct `dig @172.17.0.24` queries succeeded;
- [x] configure TrueNAS resolver precedence persistently through **System ->
  Network -> Network Configuration -> Settings** as `172.17.0.1` primary,
  `9.9.9.9` secondary and `1.1.1.1` tertiary. pfSense/Unbound is therefore the
  normal resolver and public resolvers are fallback-only; TrueNAS does not
  depend directly on its locally hosted Pi-hole for system DNS;
- [x] prove the TrueNAS system resolver returns both
  `sample.int.albandrieu.com` and `garage.int.albandrieu.com` as `172.17.0.24`
  while public `example.com` remains resolvable;
- [x] prove `https://sample.int.albandrieu.com/health` works from TrueNAS
  without `--resolve`; the observed FastAPI health status is `healthy`;
- [x] run the dual-path FastAPI exposure test: private Pi-hole ->
  pfSense/Unbound -> Traefik succeeds, while public `sample.albandrieu.com`
  resolves through Cloudflare and Cloudflare Access enforces authentication;
- [ ] repeat the public path with `CF_ACCESS_CLIENT_ID` and
  `CF_ACCESS_CLIENT_SECRET` to prove an authenticated request reaches the
  Tunnel origin, not only that Access challenges unauthenticated requests;
- [ ] keep the native Pi-hole app stopped but recoverable until the Compose
  replacement survives a normal observation window;
- [ ] uninstall the native Pi-hole app only after rollback is no longer required.


### Internal DNS resilience and public `*.int` cleanup

The private namespace contract is now:

```text
*.int.albandrieu.com -> LAN/VPN only
public service       -> non-.int hostname + explicit exposure policy
```

Live Cloudflare DNS inventory on 2026-09-06 found historical public records for
`code`, `dozzle`, `drawio`, `garage-admin`, `garage`, `hello`,
`languagetool`, `ollama`, `s3`, `*.s3`, `vaultwarden` and a legacy
`nexus-albanandrieu` host under `*.int.albandrieu.com`. These records were
created before the Traefik Cloudflare companion excluded the `int` tree and
must not be treated as evidence that the services are intentionally public.

- [x] prevent the legacy Traefik Cloudflare companion from publishing the
  `int` subdomain tree;
- [x] remove AutoXpose labels from LAN-only Ollama and Hello so a private
  Traefik route cannot also create a public DNS record;
- [ ] delete public `*.int` records that have no explicit exposure exception,
  beginning with Ollama, Hello, Code, Dozzle, Drawio and LanguageTool;
- [ ] review the legacy `nexus-albanandrieu.int` record and remove it if no
  current consumer requires it;
- [x] narrow the Garage public exception to the single S3 root endpoint
  `s3.int.albandrieu.com`; OpenTofu sets `use_path_style=true`, so public
  `*.s3.int.albandrieu.com` bucket subdomains are not required;
- [ ] delete the live Cloudflare DNS records for
  `garage.int.albandrieu.com`, `garage-admin.int.albandrieu.com` and
  `*.s3.int.albandrieu.com`, while retaining internal Traefik routes where
  needed for LAN administration;
- [ ] migrate the remaining Garage S3 state endpoint to a private runner/VPN/WARP
  path once all OpenTofu/Terragrunt writers are proven to run inside the trusted
  network, then remove the final public `.int` S3 exceptions;
- [ ] migrate any workstation dependency on
  `vaultwarden.int.albandrieu.com` away from public `.int` DNS. Prefer a
  private VPN/WARP route for normal Bitwarden/Vaultwarden client protocols.
  Cloudflare Access Service Auth is appropriate only for automation that can
  explicitly send `CF-Access-Client-Id` and `CF-Access-Client-Secret`;
  do not assume stock clients can add those headers.
