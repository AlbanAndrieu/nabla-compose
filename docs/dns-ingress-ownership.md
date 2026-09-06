# DNS and ingress ownership

This document separates DNS publication from request routing. A DNS component
decides **where a hostname resolves**. HAProxy and Traefik decide **what happens
after a client has connected**; they do not publish DNS records.

## Internal `*.int.albandrieu.com`

The repository-managed internal DNS path is:

```text
Traefik Docker labels
        |
        v
pihole-dns-sync
  DOMAIN_SUFFIX=int.albandrieu.com
  TARGET_IP=172.17.0.24
        |
        v
Pi-hole LAN DNS
        |
        v
hello.int.albandrieu.com -> 172.17.0.24
        |
        v
Traefik :443 -> service container
```

For example, `hello.int.albandrieu.com` is declared by the nginx Traefik
router. `pihole-dns-sync` is the component intended to make that hostname
resolvable on the LAN. AutoXpose is not the authoritative publisher for this
`*.int` namespace in the current repository.

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

Do not make general LAN DNS availability depend on Pi-hole running on TrueNAS.
Clients should keep using pfSense/Unbound as their normal resolver. The target
design is for pfSense to remain able to resolve public DNS independently and to
serve or forward only the private `int.albandrieu.com` zone through a
failure-contained mechanism.

Because the current `*.int` Traefik endpoints normally converge on
`172.17.0.24`, evaluate making pfSense/Unbound authoritative for the critical
internal zone (for example through reviewed host/local-zone data generated from
the repository). Pi-hole can then remain an optional synchronized consumer for
filtering and convenience rather than a single point of failure for all DNS.

If TrueNAS is down, services hosted on TrueNAS are unavailable anyway; that
failure must not prevent clients from resolving unrelated public domains.

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
