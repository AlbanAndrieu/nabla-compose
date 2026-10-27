# DNS and ingress ownership

> **Conflit de politique S3 constaté le 27 octobre 2026 :**
> `config/public-int-dns-exceptions.txt` classe `s3.int.albandrieu.com`
> comme interne, alors que la présente architecture et
> `apps/garage/compose.yml` décrivent encore un accès WAN direct.
> Cette divergence **n'est pas résolue** et ne doit pas être
> considérée comme une exception approuvée. Consulter
> [l'audit d'exposition multi-couche](runbooks/pfsense-ingress-exposure-policy.md)
> et `config/ingress-access-policy.json` avant toute publication,
> suppression de DNS ou modification HAProxy/PF/Traefik.

This document separates DNS publication from request routing. A DNS component
decides **where a hostname resolves**. HAProxy and Traefik decide **what happens
after a client has connected**; they do not publish DNS records.

## Resolver architecture and precedence

The validated LAN resolver contract is:

```text
TrueNAS / LAN client
  resolver #1: pfSense Unbound 172.17.0.1
  resolver #2: Quad9 9.9.9.9       (public fallback only)
  resolver #3: Cloudflare 1.1.1.1  (public fallback only)
          |
          v
pfSense / Unbound 172.17.0.1:53
  Forwarding Mode: disabled
  Outgoing Network Interfaces: All
          |
          +-- public names -----------------> recursive DNS resolution
          |
          `-- int.albandrieu.com override --> Pi-hole 172.17.0.24:53
                                                |
                                                `--> explicit private A records
                                                     generated from Traefik labels
```

On TrueNAS the persistent resolver order is configured in **System -> Network ->
Network Configuration -> Settings** and currently materializes as:

```text
nameserver 172.17.0.1
nameserver 9.9.9.9
nameserver 1.1.1.1
```

The order matters. `9.9.9.9` and `1.1.1.1` cannot resolve the private
`*.int.albandrieu.com` namespace and must not precede pfSense. They are public
fallback resolvers, not split-DNS authorities. Private-name availability therefore
requires pfSense/Unbound; public DNS remains recoverable through the fallback
resolvers when appropriate.

Do not configure TrueNAS itself to use its locally hosted Pi-hole as the primary
system resolver. Pi-hole runs on TrueNAS, so doing so would introduce a circular
boot/runtime dependency. TrueNAS and normal LAN clients use pfSense/Unbound;
Unbound selectively delegates only the private zone to Pi-hole.

### pfSense / Unbound

Unbound is the normal LAN resolver. **DNS Forwarder/dnsmasq is not part of this
path.** Keep Unbound recursive mode enabled by leaving **Forwarding Mode disabled**.
The private zone is configured as a Domain Override:

```text
int.albandrieu.com -> 172.17.0.24
```

The generated Unbound configuration also contains `private-domain` and
`domain-insecure` handling for this split zone. **Outgoing Network Interfaces must
include the LAN path; the validated setting is `All`.** A previous `WAN`-only
setting caused Unbound to know the correct forwarder while timing out every query
to `172.17.0.24`. `unbound-control lookup` exposed the forwarder as `expired`.
Changing the outgoing interface policy to `All` and flushing the Unbound infra
cache restored the private path.

Useful layer-specific diagnostics are:

```bash
# Pi-hole authority / private records
dig +time=2 +tries=1 @172.17.0.24 sample.int.albandrieu.com A

# LAN resolver / Domain Override
dig +time=2 +tries=1 @172.17.0.1 sample.int.albandrieu.com A

# system resolver as applications actually see it
getent hosts sample.int.albandrieu.com

# Unbound runtime forwarding decision (on pfSense)
unbound-control -c /var/unbound/unbound.conf lookup sample.int.albandrieu.com
```

These checks deliberately test different layers and must not be collapsed into a
single `getent` result.

## Internal `*.int.albandrieu.com`

The repository-managed internal DNS publication path is:

```text
Traefik Docker labels
        |
        v
pihole-dns-sync
  DOMAIN_SUFFIX=int.albandrieu.com
  TARGET_IP=172.17.0.24
        |
        v
Pi-hole 172.17.0.24:53
        |
        v
sample.int.albandrieu.com -> 172.17.0.24
        |
        v
pfSense/Unbound Domain Override exposes that answer to LAN clients
        |
        v
Traefik :443 -> service container
```

Pi-hole owns host port `53/tcp` and `53/udp` on TrueNAS. Docker's embedded DNS is
used inside Docker networks and does not own the TrueNAS LAN `:53` listener.
The existing AdGuard Home application maps its container DNS port to host port
`553`, not `53`, so it is not in the normal LAN resolver path. Kubernetes/CoreDNS
is likewise a cluster service and is not the authority for this LAN private zone.

For example, `sample.int.albandrieu.com` and the direct S3 exception
`s3.int.albandrieu.com` resolve to `172.17.0.24` on the private path. `pihole-dns-sync` derives private records from eligible Traefik
Docker labels. AutoXpose is not the authoritative publisher for this `*.int`
namespace.

The legacy Traefik Cloudflare companion explicitly excludes the `int`
subdomain tree so it must not publish `*.int.albandrieu.com` into public
Cloudflare DNS. AutoXpose must not be attached to services whose only Traefik
hostname is under `*.int.albandrieu.com`.

Public Cloudflare DNS entries under `*.int.albandrieu.com` are configuration
drift by default. Historical records created before the companion exclusion was
fixed must be inventoried and removed unless the service has a documented,
temporary direct-exposure exception. New public services must use a non-`.int`
hostname and an explicit Cloudflare Tunnel/Access or direct-ingress contract.

### DNS resilience

Incident de référence : [`incidents/2026-09-27-pfsense-dns-truenas-dependency.md`](./incidents/2026-09-27-pfsense-dns-truenas-dependency.md) documente le cycle de dépendance Talos → Pi-hole/TrueNAS révélé lors du reboot du 27 septembre 2026, ainsi que le retour au resolver LAN pfSense/Unbound `172.17.0.1`.

General LAN DNS availability must not depend on every query traversing Pi-hole.
pfSense/Unbound resolves public DNS independently and delegates only
`int.albandrieu.com` to Pi-hole. If Pi-hole or TrueNAS is unavailable, private
services hosted there are expected to be unavailable, but unrelated public DNS
must remain resolvable by Unbound/public fallback paths.

Because the current `*.int` Traefik endpoints normally converge on
`172.17.0.24`, a future resilience improvement may make pfSense/Unbound
authoritative for a small set of critical internal names using reviewed
`local-zone`/`local-data` or host overrides generated from the repository. Pi-hole
can then remain the dynamic synchronized publisher without being the only source
for critical infrastructure names.

### Verification contract

`scripts/ingress/verify-sample-exposure.sh` separates the layers intentionally:

1. direct Pi-hole DNS must resolve the private hostname to `172.17.0.24`;
2. pfSense/Unbound must return the same answer through its Domain Override;
3. the system resolver view is reported separately so resolver-order drift is
   visible;
4. internal TLS/SNI and FastAPI health are tested through Traefik;
5. public DNS, Cloudflare TLS and Cloudflare Access/Tunnel are tested separately.

Authoritative/split-DNS failures are blocking because they violate the private
namespace contract. Environment-dependent observations that do not invalidate
the architecture can be emitted as warnings rather than hiding the healthy
layers behind one generic failure.

### Garage exposure boundary

Garage now has three distinct public-facing surfaces with two ingress classes:

```text
s3.int.albandrieu.com
  -> public DNS -> pfSense HAProxy :443 -> TLS re-encryption
  -> Traefik :443 -> Garage S3 :3900

garage.albandrieu.com
  -> Cloudflare Tunnel -> cloudflared
  -> 172.17.0.24:3909 -> Garage WebUI

garage-admin.albandrieu.com
  -> Cloudflare Tunnel -> cloudflared
  -> 172.17.0.24:3903 -> Garage Admin API
```

The WebUI and Admin API tunnel origins deliberately bypass Traefik. Their
TrueNAS host ports stay bound to `172.17.0.24`; the tunnel is outbound-established
by `cloudflared`, so those hostnames need no parallel WAN HAProxy route.

The former `garage.int.albandrieu.com` and
`garage-admin.int.albandrieu.com` Traefik routes are retired and must not be
published publicly. Only the S3 root endpoint retains the temporary direct
`*.int` public exception. The OpenTofu backend sets `use_path_style=true`,
so public `*.s3.int.albandrieu.com` bucket DNS is not required. Remove the S3
exception once every state writer uses a trusted LAN/VPN/WARP path.

OpenWebUI uses an outbound Cloudflare Tunnel without Traefik. Desired
canonical route in PR #273:
`openwebui.albandrieu.com -> Cloudflare Tunnel + Access -> cloudflared ->
172.17.0.24:31028`. The previously deployed
`open-webui.albandrieu.com` is a **legacy hostname**, to be retained until
the new DNS record, Tunnel public hostname, Access policy and browser flow
are proven. Changing Compose metadata does not change Cloudflare remotely.
See [the migration runbook](runbooks/openwebui-homeassistant-canonical-rename.md).

### Anti-pattern: hostname public tunnelé réécrit vers le LAN

Incident de référence :
[`incidents/2026-10-10-vaultwarden-public-split-dns.md`](./incidents/2026-10-10-vaultwarden-public-split-dns.md).

Le 10 octobre 2026, `vaultwarden.albandrieu.com` était correctement publié par
Cloudflare Tunnel vers `http://172.17.0.24:30032`, mais pfSense/Unbound
répondait `172.17.0.24` aux clients LAN pour ce même hostname public. TrueNAS
contactait donc `172.17.0.24:443` directement et recevait un `404`, tandis
qu'une workstation utilisant la résolution Cloudflare obtenait `200`.

Un hostname public appartenant à Cloudflare Tunnel ne doit pas être réécrit vers
une IP LAN simplement pour optimiser le chemin interne. Ce split-DNS bypass le
contrôle d'ingress public et peut diriger le client vers un port/frontend qui
n'implémente pas le même contrat.

Avant d'accuser Cloudflare ou l'application, comparer systématiquement :

```bash
getent ahostsv4 <hostname-public>
dig +short A <hostname-public> @172.17.0.1
dig +short A <hostname-public> @1.1.1.1
curl -sv https://<hostname-public>/... -o /dev/null 2>&1 |
  grep -E 'Trying |Connected to|< HTTP|server:|cf-ray:'
```

Si un accès LAN direct est souhaité, utiliser de préférence un nom distinct sous
`*.int.albandrieu.com` avec son propre contrat Traefik/service.

## Public `*.albandrieu.com`

There is not one universal publication mechanism for every public hostname.
The homelab currently has several exposure classes:

1. **Cloudflare Tunnel + Access** for services whose exposure contract says they
   are tunneled.
2. **Direct pfSense HAProxy -> Traefik** for deliberately direct hostnames.
3. **Cloudflare Tunnel + Access** for protected public services such as
   `sample.albandrieu.com`, which maps to the private origin
   `http://172.17.0.24:8091`.
4. **AutoXpose -> Cloudflare DNS / NPM** for other Docker services explicitly
   assigned to AutoXpose ownership.
5. Legacy DDNS / Traefik Cloudflare companion services that remain in the
   Traefik stack and should be consolidated over time.

`cloudflared` is therefore not equivalent to "the DNS manager for all
`*.albandrieu.com`". A Cloudflare Tunnel can create/use DNS records for its
own tunnel hostnames, but direct HAProxy/Traefik hostnames still require a
normal DNS record pointing at the public edge.

## pfSense HAProxy

HAProxy does **not** create either public or internal DNS records. Its role is
request routing after DNS resolution:

```text
client -> resolved IP -> pfSense HAProxy :443 -> Traefik :443 -> service
```

For a direct public hostname intentionally using pfSense, the DNS record must
resolve to the pfSense WAN address and HAProxy must have a host ACL/backend path
that forwards the hostname to Traefik while preserving the HTTP Host.

`sample.albandrieu.com` is no longer in that category: its target architecture
is Cloudflare Access -> Cloudflare Tunnel -> `http://172.17.0.24:8091`.

For a LAN-only `*.int.albandrieu.com` hostname resolving directly to
`172.17.0.24`, a LAN client can reach Traefik without traversing the WAN
HAProxy path. A public `*.int` record is forbidden by default. Any temporary
legacy exception must be declared explicitly, monitored as security debt and
migrated to a non-`.int` public hostname.

## Garage S3 and Vaultwarden legacy public-DNS retirement (2026-10-12)

The approved exception list now keeps only the deliberate Hello direct-ingress canary.
`s3.int.albandrieu.com` and `vaultwarden.int.albandrieu.com` are **not** approved for public DNS or WAN HAProxy/NAT exposure. Garage S3 still needs an internal `https://s3.int.albandrieu.com` LAN/VPN path, including OpenTofu callers.

A repository list change is **not** deletion of an existing Cloudflare DNS record, HAProxy frontend/backend, NAT rule or cached DNS result. Verify and retire the active public records/routes under separate reviewed changes; check OpenTofu state connectivity and rollback before any WAN routing changes. Use public DNS and an independent outside-in HTTP/SNI probe to confirm absence of exposure, while LAN FastAPI/TrueNAS TCP checks continue independent of `external=false`. Lack of a DNS answer alone does not prove a protected origin.

The observed S3 XML `AccessDenied` at `garage.albandrieu.com` means that hostname currently routes to an S3 API response. The declared WebUI is the separate `garage-webui` service on port 3909, while port 3903 is the Garage Admin API and 3900 is the S3 API. Audit Cloudflare Tunnel public hostname origin mapping before changing the displayed WebUI URL; do not presume that the Admin API hostname is a browser UI.


### Garage UI access policy and terminology (2026-10-13)

| Canonical service | Origin declared | Intended purpose | Exposure policy |
| --- | --- | --- | --- |
| Garage S3 API (`garage`) | `172.17.0.24:3900` | S3 object and bucket API, including state clients | LAN/VPN only |
| Garage Admin API (`garage-admin`) | `172.17.0.24:3903` | Garage administration REST API | Restricted; do not conflate with browser UI |
| Garage Web UI (`garage-webui`) | `172.17.0.24:3909` | Separate `khairul169/garage-webui` browser app | Temporarily reachable remotely with protection; eventually LAN/VPN only |

The user has confirmed that `https://garage-admin.albandrieu.com/` currently displays a browser UI, while `https://garage.albandrieu.com/` has returned an S3-style XML `AccessDenied`. This **does not establish the active Cloudflare Tunnel origin ports**. The declared configuration associates `garage-admin` with :3903 and `garage` with the WebUI :3909; compare actual Cloudflare public-hostname origin settings, deployment, and redirects before any rewrite. A UI response does not itself identify the backend origin.

Long-term, Garage Web UI should be private. Keep temporary remote access for now, preferably behind Cloudflare Access, until a reversible and convenient private-access mechanism (Tailscale/WireGuard or equivalent with least-privilege ACLs and MFA) is accepted. Preserve the independence of the S3 API and the Admin API; never assume private intent means proven lack of WAN access.

## 2026-10-17 — Unbound private-zone regression and pfSense posture audit

Workstation SSH alias `home.albandrieu.com` resolves to user `admin`, port `9922`, identity `~/.ssh/id_ed25519`; `scripts/pfsense/audit-posture.sh` now defaults to this alias in SSH mode. Explicit `--ssh`, `--port`, `--api` and `--local` remain supported. The workstation successfully ran the read-only audit.

Operator's pfSense DNS Resolver entries:

| Host | Domain | Address | Comment |
| --- | --- | --- | --- |
| bitwarden | albandrieu.com | 172.17.0.24 | For bitwarden api intenal acces |
| vaultwarden | int.albandrieu.com | 172.17.0.24 | Override for internal use of vaultwarden |

These are **Host Overrides** (host + domain + IP), not the intended **Domain Override** forwarding all `int.albandrieu.com` queries to Pi-hole. Do not change the `vaultwarden` comment alone expecting zone forwarding, and do not delete either entry without validating its consumers. Confirm whether a separate Domain Override exists in the pfSense UI and the persisted configuration. Active generated Unbound configuration contains no `int.albandrieu.com` forwarding directive; `defectdojo.int.albandrieu.com` is resolved via public Cloudflare nameservers. Reestablish the canonical split zone only after checking Pi-hole upstream to avoid a forwarding loop. Do not publish DefectDojo publicly or add a WAN HAProxy route.

The 2026-10-17 read-only posture audit reported Unbound running, RSS 131604 KiB, available memory 212312 KiB, and kernel OOM evidence at 02:11:32 local time (`unbound` killed by memory reclaim). Native Unbound cache counters were ~4.97 MiB; they do not account for all process RSS. DNSBL loaded entries and RAM hot-swap guard remain WARN. The audit also reported **two separate FAIL checks**: missing pflow exporter domain 1 -> `172.17.0.24:2055` and domain 2 -> `162.159.65.1:2055`, with zero connected exporters. These are unrelated to DefectDojo DNS and should be tracked independently; do not alter pflow during DNS recovery. Zabbix agent remains stopped (WARN). No pfSense configuration change or restart was performed.

## 2026-10-17 23:33 — pfSense recovery accepted and configuration backups

Operator confirms that after changing DNS Resolver **Outgoing Network Interfaces** from `WAN` to `All` (while keeping Domain Override `int.albandrieu.com -> 172.17.0.24`), `dig @172.17.0.1` returned `172.17.0.24` for `defectdojo.int.albandrieu.com`, `vaultwarden.int.albandrieu.com`, and `hello.int.albandrieu.com`. This closes the immediate LAN DNS regression; a post-change memory/Unbound posture check remains prudent due to the prior OOM incident. Pi-hole returned an authoritative (`aa`) DefectDojo A record before the correction.

The operator made a pfSense XML backup (not stored in Git):

- `/media/backup/lab/infra/pfsense/2026-10/config-pfsense.albandrieu.com-20261017233344.xml`
- comparison: `/media/backup/lab/infra/pfsense/2026-09/config-pfsense.albandrieu.com-20260907184207-memory-optimized.xml`
- comparison: `/media/backup/lab/infra/pfsense/2026-09/config-pfsense.albandrieu.com-20260908172552-unbound-php-crash-pfsense-exporter-too-agressif.xml`

These backups can contain credentials, API tokens, certificates, and private keys. Never commit them or attach them to public CI logs. Compare locally using a redacted/semantic configuration diff, focusing on Unbound outgoing interfaces, Domain/Host Overrides, pfBlockerNG, and memory-related settings. Existence, integrity and contents of these local backup files have not been independently verified by the agent.

The operator also removed a public Cloudflare DNS record named `int.albandrieu.com`, which they had expected to behave as a wildcard. This change is distinct from the private pfSense Domain Override and must not be reversed for private services. A DNS record at `int.albandrieu.com` does not wildcard `*.int.albandrieu.com`; an explicit wildcard record would be needed for that public behavior, which is prohibited by the private-zone policy. The remaining public Hello exception must be reviewed separately. Re-run the Cloudflare DNS inventory to establish whether the prior unexpected record finding is cleared.

Cloudflare DNS configuration should be managed through reviewed OpenTofu/Terraform infrastructure as code, with imports of existing resources before changes, a read-only drift audit, least-privilege scoped API token sourced from a secret store, explicit protected exceptions, and CI `plan` without automatic `apply`. Never place Terraform state containing secrets in Git; use a protected remote backend. No Cloudflare API modification has been performed by this documentation update.

### Cloudflare inventory follow-up — 2026-10-17 23:39 CEST

Read-only `scripts/security/audit-public-int-dns.sh --check` returned exit 3, identifying exactly one unexpected record:

| Public Cloudflare record | Type | Target | Classification |
| --- | --- | --- | --- |
| `hello.int.albandrieu.com` | A | `82.66.4.247` | TEMPORARY-EXCEPTION (allowed) |
| `s3.int.albandrieu.com` | CNAME | `albandrieu.com` | UNEXPECTED (not allowlisted) |

Cloudflare record ID for the unexpected S3 alias: `8ed02a21a1b0b9e4cab48cea079962c7`. The operator has already removed the separate `int.albandrieu.com` record. **Do not add S3 to the public exceptions allowlist**: `config/public-int-dns-exceptions.txt` explicitly requires Garage S3 to remain internal. First inventory any external S3 clients and their dependencies, confirm internal `dig @172.17.0.1 s3.int.albandrieu.com A` and internal HTTPS/S3 operations, then remove the public CNAME through a reviewed change and rerun the audit. DNS publication does not by itself prove the S3 API is reachable through public ingress; test separately. No Cloudflare DNS record was modified by this documentation update.

### Cloudflare S3 cleanup accepted — 2026-10-17 23:42 CEST

Operator verified `dig +time=2 +tries=1 @172.17.0.1 s3.int.albandrieu.com A` returned `NOERROR` with `172.17.0.24` (TTL 0). They then removed the public Cloudflare CNAME `s3.int.albandrieu.com -> albandrieu.com`. A subsequent `bash scripts/security/audit-public-int-dns.sh --check` returned **exit=0, failed=0, warnings=1** with the expected finding `Only reviewed temporary public .int DNS exceptions remain`. This confirms the unexpected public `.int` record inventory is clean according to the audit's allowlist, not that every external ingress path has been independently penetration-tested. The temporary public Hello exception remains by policy. No further Cloudflare changes are needed for this specific finding. Evidence report: `/tmp/audit-public-int-dns-20261017-234223.697obp.log` (workstation-local, not checked into Git).
