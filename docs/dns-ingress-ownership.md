# DNS and ingress ownership

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

OpenWebUI is another tunnel-origin example:
`open-webui.albandrieu.com -> Cloudflare Tunnel -> cloudflared ->
172.17.0.24:31028`. It does not traverse Traefik.

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
